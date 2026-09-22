# -*- coding: utf-8 -*-
"""
execucao_job.py - registra a execucao de um job e os fatos que ela produz nas
tabelas do erp_automation (database/erp_004_execucao_e_eventos.sql).

POR QUE EXISTE: ate 09/2026 cada job guardava o que fez num CSV proprio, sem
chave comum entre eles e com o proprio job podendo reescrever o historico.
Aqui a execucao vira uma linha em job_execucao, e cada fato de negocio vira um
evento (operacao_evento, arquivo, arquivo_titulo, arquivo_evento) que nunca
muda - a imutabilidade e do banco (dono separado + gatilho), nao deste modulo.

VOCABULARIO (dicionario do Learn, 15-24/08/2026): job = a unidade que roda com
um comando; execucao = uma rodada, com inicio, fim e resultado; evento = fato de
negocio, nunca se apaga; gatilho = o que disparou (cron, manual, api).

DEGRADACAO: em ensaio (DRY) a falta do banco NAO derruba o job - a execucao
volta "degradada" (id None), cada registrar() avisa uma vez e devolve None. Em
modo real (obrigatoria=True) o banco e condicao: sem registro nao ha acao
irreversivel, e a falha vira ExecucaoIndisponivel/ErroDeRegistro para quem chama.

CONEXAO: as mesmas POSTGRES_* que boletos/_db.py usa (no container: host
guardian, senha vazia, identidade efemera). ERP_EXECUCAO_DSN sobrepoe tudo -
e a porta da bancada (scripts/bancada_pg.sh) e dos testes de integracao.

A sessao publica erp.execucao_id (set_config) para que um gatilho de auditoria
futuro (schema `auditoria`) saiba QUAL execucao alterou cada linha.

Uso:
    from src.common.clients import execucao_job as ej
    ex = ej.abrir_execucao("finalizar_operacao", "finalizar_operacao_aguardando_assinatura",
                           flag_ensaio=True)
    ej.registrar_evento_operacao(ex, 65071, "avaliada", resultado="FINALIZARIA", pendencias=[])
    ej.fechar_execucao(ex, "sucesso", codigo_saida=0, qtd_itens=1)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

AUTOMACOES = ("boletos", "doc2you", "credito", "remessa_cobranca", "retorno_cobranca",
              "remessa_pagamento", "retorno_pagamento", "finalizar_operacao",
              "controle")  # paridade CSV x banco e outras conferencias sem navegador (erp_005)
TIPOS_EVENTO_OPERACAO = ("avaliada", "finalizar_clicado", "finalizada", "finalizacao_falhou",
                         "finalizada_por_outro", "aviso_enviado",
                         # credito (erp_005): o que antes so o CSV local sabia
                         "documentos_baixados", "etapa_movida")
TIPOS_EVENTO_ARQUIVO = ("gerado", "enviado", "recebido", "processado", "rejeitado", "retido",
                        # erp_005: o que antes so existia em JSON no disco
                        "intencao_envio", "descartado", "cancelado", "movido")
TIPOS_ARQUIVO = ("remessa_cobranca_cnab_400", "retorno_cobranca_cnab_400",
                 "remessa_pagamento_cnab_240", "retorno_pagamento_cnab_240",
                 "remessa_bb", "retorno_bb", "exportacao_csv")

#: Apelido de credencial e o que se registra; senha, nunca. Um apelido do Guardian
#: tem esta forma; qualquer outra coisa e tratada como segredo e NAO e gravada.
_APELIDO_RE = re.compile(r"^(GSMARTPWD\d+|__GUARDIAN_[A-Z0-9_]+__)$")

CONNECT_TIMEOUT_S = 10


class ExecucaoIndisponivel(RuntimeError):
    """Nao foi possivel abrir a execucao no banco e o job exigiu registro."""


class ErroDeRegistro(RuntimeError):
    """Um registrar() falhou numa execucao estrita (modo real)."""


@dataclass
class Execucao:
    id: int | None
    automacao: str
    job: str
    flag_ensaio: bool
    estrito: bool = False
    _conn: Any = None
    avisos: list = field(default_factory=list)
    #: fatos sem tabela propria (remessa que nao baixou, cancelamento sem arquivo):
    #: entram em detalhe_json no fechamento — a tabela nao aceita UPDATE antes disso.
    anotacoes: dict = field(default_factory=dict)

    @property
    def registra(self) -> bool:
        """True quando ha banco e linha aberta; False = degradada."""
        return self._conn is not None and self.id is not None

    def _avisar(self, log, texto: str) -> None:
        # um aviso por motivo: o log do job nao vira uma parede de repeticoes
        if texto not in self.avisos:
            self.avisos.append(texto)
            log(f"  [execucao] AVISO: {texto}")


#: A execucao aberta por este processo. `abrir_execucao` a define e `fechar_execucao`
#: a limpa. Serve para quem esta fundo no job (credito/banco.py, bb_entrega.py) registrar
#: um fato sem receber `execucao` por quatro assinaturas. Um processo = um job = uma execucao.
_ATUAL: Execucao | None = None


def atual() -> Execucao | None:
    """A execucao aberta neste processo, ou None (fora do fluxo que abre uma)."""
    return _ATUAL


def conexao_leitura(job: str):
    """Uma conexao para LER as tabelas do erp_automation com a identidade do container
    (a mesma dos registros). Para jobs de conferencia, como a paridade CSV x banco."""
    return _conectar(job)


# --------------------------------------------------------------------------- #
# conexao
# --------------------------------------------------------------------------- #
def _parametros_conexao(job: str) -> dict:
    dsn = os.environ.get("ERP_EXECUCAO_DSN", "").strip()
    base = {"connect_timeout": CONNECT_TIMEOUT_S,
            "application_name": f"erp-automation:{job}"[:63],
            # A sessao fica OCIOSA enquanto o Chrome trabalha (a remessa das 18h leva 20 min):
            # keepalive de TCP evita que NAT/proxy derrubem a conexao parada. Nao e garantia
            # (o proxy pode fechar por politica): por isso tambem existe a reconexao.
            "keepalives": 1, "keepalives_idle": 60, "keepalives_interval": 15, "keepalives_count": 4}
    if dsn:
        return {"dsn": dsn, **base}
    return {
        "host": os.environ.get("POSTGRES_HOST", "postgres"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "prosperedb"),
        "user": os.environ.get("POSTGRES_USER", "app_erp_automation"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        **base,
    }


def _conectar(job: str):
    import psycopg2  # tardio: o modulo importa sem psycopg2 (testes com dubles)

    conn = psycopg2.connect(**_parametros_conexao(job))
    conn.autocommit = True
    return conn


def _json(valor):
    import psycopg2.extras

    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


# --------------------------------------------------------------------------- #
# defaults que vem do ambiente
# --------------------------------------------------------------------------- #
def _ambiente_padrao() -> str:
    return "container" if os.path.exists("/.dockerenv") else "sandbox"


def _gatilho_padrao() -> str:
    # O hub ainda nao injeta identificacao no docker exec; quando passar HUB_RUN_ID
    # (ou HUB_TASK_NOME), o gatilho vira cron sozinho.
    return "cron" if (os.environ.get("HUB_RUN_ID") or os.environ.get("HUB_TASK_NOME")) else "manual"


def apelido_seguro(valor: str | None) -> str | None:
    """Devolve o apelido se for apelido; None se parecer segredo."""
    if not valor:
        return None
    return valor if _APELIDO_RE.match(valor.strip()) else None


# --------------------------------------------------------------------------- #
# normalizacoes
# --------------------------------------------------------------------------- #
def hash_pendencias(pendencias) -> str | None:
    """sha256 das pendencias normalizadas (ordem nao importa). None se vazio."""
    itens = sorted(str(p).strip() for p in (pendencias or []) if str(p).strip())
    if not itens:
        return None
    return hashlib.sha256("\n".join(itens).encode("utf-8")).hexdigest()


def mascarar_chave_pix(chave: str | None) -> str | None:
    """Ultimos 4 caracteres visiveis; o resto vira *. A chave inteira vai so no sha256."""
    if not chave:
        return None
    c = str(chave).strip()
    if len(c) <= 4:
        return "*" * len(c)
    return "*" * (len(c) - 4) + c[-4:]


def sha256_texto(texto: str | None) -> str | None:
    if not texto:
        return None
    return hashlib.sha256(str(texto).strip().encode("utf-8")).hexdigest()


def data_br(texto) -> date | None:
    """'18/09/2026', '18-09-2026' ou '2026-09-18' -> date. Outra coisa -> None.

    A grade do Smart entrega o vencimento em ISO ('2026-09-02', medido no ciclo real de
    21/09/2026); o CSV do sandbox e a tela usam dd/mm/aaaa. Os tres formatos entram.
    """
    if isinstance(texto, date):
        return texto
    if not texto:
        return None
    bruto = str(texto).strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(bruto, formato).date()
        except ValueError:
            continue
    return None


def decimal_br(texto) -> Decimal | None:
    """'2.705,36' -> Decimal('2705.36'). Nao numerico -> None."""
    if texto is None or texto == "":
        return None
    if isinstance(texto, (int, float, Decimal)):
        return Decimal(str(texto))
    t = str(texto).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _flag(valor) -> bool | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "true", "sim", "s", "x", "on", "checked")


#: A grade do Smart, na ordem da tela (checagem_pagamento.conferir devolve estes nomes).
_MAPA_LINHA = {
    "tipo": "tipo_pagamento", "tipo_pix": "tipo_pix", "cta_origem": "conta_origem",
    "numero": "numero_documento", "cta_destino": "conta_destino", "bco": "banco",
    "agencia": "agencia", "tipo_conta": "tipo_conta", "cc": "conta_corrente",
    "favorecido": "favorecido", "cpf_cnpj": "cpf_cnpj_favorecido", "id_transacao": "id_transacao",
}


def linha_pagamento_normalizada(linha: dict, numero_linha: int) -> dict:
    """Uma linha da grade -> colunas de operacao_pagamento_linha, com PIX mascarado."""
    saida = {"numero_linha": int(linha.get("_linha") or numero_linha)}
    for origem, destino in _MAPA_LINHA.items():
        v = linha.get(origem)
        saida[destino] = (str(v).strip() or None) if v is not None else None
    chave = linha.get("chave_pix")
    saida["chave_pix_mascarada"] = mascarar_chave_pix(chave)
    saida["sha256_chave_pix"] = sha256_texto(chave)
    saida["data_vencimento"] = data_br(linha.get("vencto"))
    saida["valor_pagamento"] = decimal_br(linha.get("valor"))
    saida["flag_sp"] = _flag(linha.get("sp"))
    return saida


# --------------------------------------------------------------------------- #
# a API
# --------------------------------------------------------------------------- #
def _operador_padrao(gatilho: str) -> str | None:
    # So o que a pessoa declarou: dentro do container todo `docker exec` e root, entao
    # USER/LOGNAME nao dizem quem foi. Cron: o hub e o operador; fica nulo.
    if gatilho != "manual":
        return None
    return (os.environ.get("ERP_OPERADOR") or "").strip() or None


def _inserir_execucao(cur, campos: dict) -> int:
    """INSERT da execucao. Antes da erp_005 as colunas operador/motivo nao existem: o
    INSERT cai por UndefinedColumn e repete sem elas — o job nao para por causa de uma
    migration pendente, mas avisa (ver abrir_execucao)."""
    colunas = list(campos.keys())
    cur.execute(
        f"INSERT INTO erp_automation.job_execucao ({', '.join(colunas)}) "
        f"VALUES ({', '.join(['%s'] * len(colunas))}) RETURNING id",
        tuple(campos[c] for c in colunas))
    return int(cur.fetchone()[0])


def _e_coluna_inexistente(e: Exception) -> bool:
    return type(e).__name__ == "UndefinedColumn" or "column" in str(e).lower() and "does not exist" in str(e).lower()


def abrir_execucao(automacao: str, job: str, *, flag_ensaio: bool, gatilho: str | None = None,
                   ambiente: str | None = None, task_nome: str | None = None,
                   run_id: str | None = None, apelido_credencial: str | None = None,
                   versao_codigo: str | None = None, detalhe: dict | None = None,
                   operador: str | None = None, motivo: str | None = None,
                   obrigatoria: bool = False, log=print) -> Execucao:
    """Abre a execucao. obrigatoria=True: sem banco, levanta; False: volta degradada.

    operador/motivo (erp_005): quem disparou a mao e por que. Vem de ERP_OPERADOR e
    ERP_MOTIVO quando nao informados; no cron ficam nulos (o hub e o operador)."""
    global _ATUAL
    if automacao not in AUTOMACOES:
        raise ValueError(f"automacao desconhecida: {automacao!r} (aceitas: {AUTOMACOES})")
    gatilho = gatilho or _gatilho_padrao()
    ambiente = ambiente or _ambiente_padrao()
    task_nome = task_nome or os.environ.get("HUB_TASK_NOME") or None
    run_id = run_id or os.environ.get("HUB_RUN_ID") or None
    versao_codigo = versao_codigo or os.environ.get("ERP_AUTOMATION_REVISION") or None
    apelido = apelido_seguro(apelido_credencial)
    operador = (operador or "").strip() or _operador_padrao(gatilho)
    motivo = (motivo or "").strip() or (os.environ.get("ERP_MOTIVO") or "").strip() or None

    ex = Execucao(id=None, automacao=automacao, job=job, flag_ensaio=flag_ensaio, estrito=obrigatoria)
    _ATUAL = ex
    # Sem aviso quando faltam operador/motivo: o hub (22/09/2026) ainda nao injeta
    # HUB_RUN_ID/HUB_TASK_NOME no docker exec, entao TODA execucao dele chega como
    # "manual" e o aviso viraria ruido em cada job. Quando o hub passar a identificar-se,
    # o gatilho vira cron sozinho e o aviso para execucao manual sem autor passa a valer.
    campos = {"automacao": automacao, "job": job, "task_nome": task_nome, "run_id": run_id,
              "gatilho": gatilho, "ambiente": ambiente, "flag_ensaio": flag_ensaio,
              "apelido_credencial": apelido, "versao_codigo": versao_codigo,
              "detalhe_json": _json(detalhe or {}), "operador": operador, "motivo": motivo}
    try:
        conn = _conectar(job)
        with conn.cursor() as cur:
            try:
                ex.id = _inserir_execucao(cur, campos)
            except Exception as e:  # noqa: BLE001
                if not _e_coluna_inexistente(e):
                    raise
                # erp_005 ainda nao aplicada neste banco: registra sem operador/motivo
                campos.pop("operador"); campos.pop("motivo")
                ex.id = _inserir_execucao(cur, campos)
                ex._avisar(log, "erp_005 nao aplicada: operador/motivo nao registrados")
            # a sessao passa a dizer QUAL execucao esta escrevendo
            cur.execute("SELECT set_config('erp.execucao_id', %s, false)", (str(ex.id),))
        ex._conn = conn
        log(f"  [execucao] #{ex.id} aberta: {automacao}/{job} · {ambiente} · "
            f"{'ENSAIO' if flag_ensaio else 'REAL'} · gatilho {gatilho}")
    except Exception as e:  # noqa: BLE001 - a fronteira com o banco e o motivo do modulo
        if obrigatoria:
            raise ExecucaoIndisponivel(
                f"nao foi possivel abrir a execucao no banco ({type(e).__name__}: "
                f"{str(e)[:160]}). Em modo real, sem registro nao ha acao.") from e
        ex._avisar(log, f"sem banco para registrar a execucao ({type(e).__name__}: "
                        f"{str(e)[:120]}); seguindo em ensaio SEM registro")
    return ex


#: Erros que significam "a conexao morreu", nao "o comando esta errado": vale reconectar
#: e repetir UMA vez. Reconhecidos pelo nome da classe (psycopg2) e pelo texto, para o
#: modulo continuar importando sem psycopg2 (testes com dubles).
_ERROS_DE_CONEXAO = ("InterfaceError", "OperationalError")
_TEXTOS_DE_CONEXAO = ("connection already closed", "server closed the connection",
                      "terminating connection", "could not receive data", "connection not open",
                      "SSL connection has been closed", "connection reset")


def _e_queda_de_conexao(conn, e: Exception) -> bool:
    if getattr(conn, "closed", 0):
        return True
    return type(e).__name__ in _ERROS_DE_CONEXAO and any(t in str(e) for t in _TEXTOS_DE_CONEXAO)


def _reconectar(ex: Execucao, log, motivo: str) -> bool:
    """A conexao caiu no meio de uma rodada longa (22/09/2026, remessa das 11:30: o
    servidor fechou apos 12 min ociosos e os 5 registros seguintes se perderam, e o
    fechamento derrubou o job). Abre outra, republica erp.execucao_id e avisa. False se
    nao der: quem chama decide (estrito levanta; fato consumado avisa)."""
    try:
        conn = _conectar(ex.job)
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('erp.execucao_id', %s, false)", (str(ex.id),))
    except Exception as e:  # noqa: BLE001
        ex._avisar(log, f"conexao com o banco caiu ({motivo}) e a reconexao falhou "
                        f"({type(e).__name__}: {str(e)[:100]})")
        return False
    try:
        if ex._conn is not None:
            ex._conn.close()
    except Exception:  # noqa: BLE001
        pass
    ex._conn = conn
    ex._avisar(log, f"conexao com o banco caiu ({motivo}); reconectada")
    return True


def _rodar(ex: Execucao, log, descricao: str, sql: str, params: tuple, *, modo: str):
    """O acesso ao banco com UMA repeticao apos queda de conexao. modo: 'um' (fetchone ->
    int), 'todos' (fetchall) ou 'nada' (True). Levanta a excecao original se nao der."""
    try:
        with ex._conn.cursor() as cur:
            cur.execute(sql, params)
            if modo == "um":
                linha = cur.fetchone()
                return int(linha[0]) if linha else None
            if modo == "todos":
                return cur.fetchall()
            return True
    except Exception as e:  # noqa: BLE001
        if not _e_queda_de_conexao(ex._conn, e) or not _reconectar(ex, log, f"{type(e).__name__}: {str(e)[:80]}"):
            raise
    # segunda e ultima tentativa, na conexao nova. INSERT de arquivo tem ON CONFLICT
    # (sha256) — repetir nao duplica; evento repetido e append-only e inofensivo.
    with ex._conn.cursor() as cur:
        cur.execute(sql, params)
        if modo == "um":
            linha = cur.fetchone()
            return int(linha[0]) if linha else None
        if modo == "todos":
            return cur.fetchall()
        return True


def _executar(ex: Execucao, log, descricao: str, sql: str, params: tuple, *, devolve=False):
    """Roda um comando na execucao. Degradada: avisa e devolve None. Estrita: levanta.
    Queda de conexao no meio: reconecta e repete uma vez (ver _reconectar)."""
    if ex is None:
        # Sem execucao nenhuma: o job foi chamado fora do fluxo que a abre (teste de
        # unidade, uso manual de uma funcao interna). Nao ha o que registrar, e isto
        # nao e erro — quem exige registro usa `obrigatoria=True` no abrir_execucao.
        return None
    if not ex.registra:
        ex._avisar(log, "registro nao feito: execucao sem banco (o ensaio segue; em modo real isto levanta)")
        return None
    try:
        return _rodar(ex, log, descricao, sql, params, modo="um" if devolve else "nada")
    except Exception as e:  # noqa: BLE001
        if ex.estrito:
            raise ErroDeRegistro(f"{descricao} falhou: {type(e).__name__}: {str(e)[:160]}") from e
        ex._avisar(log, f"{descricao} falhou ({type(e).__name__}: {str(e)[:120]})")
        return None


def registrar_evento_operacao(ex: Execucao, id_operacao, tipo_evento: str, *,
                              resultado: str | None = None, cedente: str | None = None,
                              valor_liquido=None, pendencias=None, detalhe: dict | None = None,
                              linhas_pagamento: list | None = None, fato: bool = False,
                              log=print) -> int | None:
    """Um fato sobre a operacao. Devolve o id do evento (None se nao registrou).

    Estrito por padrao: e o registro de INTENCAO (o clique do finalizador). fato=True e
    para o que JA aconteceu (credito: documentos baixados, etapa movida) — falha de banco
    vira aviso, nunca derruba o job."""
    if ex is None:
        return None
    if tipo_evento not in TIPOS_EVENTO_OPERACAO:
        raise ValueError(f"tipo_evento desconhecido: {tipo_evento!r}")
    if fato:
        return _fato_consumado(ex, log, f"evento {tipo_evento} da op {id_operacao}", lambda: (
            registrar_evento_operacao(ex, id_operacao, tipo_evento, resultado=resultado,
                                      cedente=cedente, valor_liquido=valor_liquido,
                                      pendencias=pendencias, detalhe=detalhe,
                                      linhas_pagamento=linhas_pagamento, log=log)))
    evento_id = _executar(
        ex, log, f"evento {tipo_evento} da op {id_operacao}",
        "INSERT INTO erp_automation.operacao_evento "
        "(fk_job_execucao, id_operacao, tipo_evento, resultado, cedente, valor_liquido, "
        " pendencias_json, hash_pendencias, detalhe_json) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (ex.id, int(id_operacao), tipo_evento, resultado, cedente,
         decimal_br(valor_liquido), _json(list(pendencias)) if pendencias is not None else None,
         hash_pendencias(pendencias), _json(detalhe or {})),
        devolve=True)
    if evento_id and linhas_pagamento:
        for i, linha in enumerate(linhas_pagamento, start=1):
            n = linha_pagamento_normalizada(linha, i)
            colunas = list(n.keys())
            _executar(
                ex, log, f"linha de pagamento {n['numero_linha']} da op {id_operacao}",
                f"INSERT INTO erp_automation.operacao_pagamento_linha (fk_operacao_evento, "
                f"{', '.join(colunas)}) VALUES (%s, {', '.join(['%s'] * len(colunas))})",
                (evento_id, *[n[c] for c in colunas]))
    return evento_id


def _fato_consumado(ex: Execucao, log, descricao: str, fn):
    """Registro de algo que JA aconteceu (arquivo gerado, baixa dada, evento ocorrido).

    O modo estrito existe para o gate de ABERTURA — sem banco, o job nao age — e para
    registrar INTENCAO antes de agir (o `finalizar_clicado` do finalizador). Depois que a
    acao irreversivel aconteceu, levantar nao desfaz nada: so derruba o job com traceback
    e deixa os itens seguintes da fila sem processar. Aqui a falha vira aviso, sempre. O
    CSV de controle continua sendo escrito ao lado, entao a prova nao se perde.
    Achado da revisao de 22/09/2026, nos quatro jobs de arquivo."""
    try:
        return fn()
    except ErroDeRegistro as e:
        ex._avisar(log, f"{descricao}: {e} (fato ja consumado; o job segue)")
        return None


def registrar_arquivo(ex: Execucao, tipo_arquivo: str, sentido: str, *, nome_arquivo: str,
                      conteudo: bytes | None = None, caminho: str | None = None,
                      qtd_registros: int | None = None, valor_total=None,
                      conta_id: str | None = None, conta_label: str | None = None,
                      origem_caminho: str | None = None, destino_caminho: str | None = None,
                      detalhe: dict | None = None, titulos: list | None = None,
                      registrado_em: datetime | None = None, log=print) -> int | None:
    """Registra um arquivo pelo conteudo (sha256). O mesmo conteudo nao entra duas vezes:
    devolve o id ja existente. titulos: [{numero_linha, id_titulo, id_operacao, ...}].
    Fato consumado: falha de banco vira aviso, nunca derruba o job.
    registrado_em: SO para carga historica (a data em que o fato aconteceu, tirada do
    controle antigo); um job em curso nunca informa — o banco carimba o agora."""
    if ex is None:
        return None
    return _fato_consumado(ex, log, f"arquivo {nome_arquivo}", lambda: _registrar_arquivo(
        ex, tipo_arquivo, sentido, nome_arquivo=nome_arquivo, conteudo=conteudo,
        caminho=caminho, qtd_registros=qtd_registros, valor_total=valor_total,
        conta_id=conta_id, conta_label=conta_label, origem_caminho=origem_caminho,
        destino_caminho=destino_caminho, detalhe=detalhe, titulos=titulos,
        registrado_em=registrado_em, log=log))


def _registrar_arquivo(ex: Execucao, tipo_arquivo: str, sentido: str, *, nome_arquivo: str,
                       conteudo: bytes | None = None, caminho: str | None = None,
                       qtd_registros: int | None = None, valor_total=None,
                       conta_id: str | None = None, conta_label: str | None = None,
                       origem_caminho: str | None = None, destino_caminho: str | None = None,
                       detalhe: dict | None = None, titulos: list | None = None,
                       registrado_em: datetime | None = None, log=print) -> int | None:
    if tipo_arquivo not in TIPOS_ARQUIVO:
        raise ValueError(f"tipo_arquivo desconhecido: {tipo_arquivo!r}")
    if sentido not in ("gerado", "recebido"):
        raise ValueError("sentido e gerado|recebido")
    if conteudo is None:
        if not caminho:
            raise ValueError("informe conteudo ou caminho")
        with open(caminho, "rb") as fh:
            conteudo = fh.read()
    sha = hashlib.sha256(conteudo).hexdigest()
    colunas = ["fk_job_execucao", "tipo_arquivo", "sentido", "nome_arquivo", "sha256", "qtd_bytes",
               "qtd_registros", "valor_total", "conta_id", "conta_label", "origem_caminho",
               "destino_caminho", "detalhe_json"]
    valores = [ex.id, tipo_arquivo, sentido, nome_arquivo, sha, len(conteudo), qtd_registros,
               decimal_br(valor_total), conta_id, conta_label, origem_caminho, destino_caminho,
               _json(detalhe or {})]
    if registrado_em is not None:
        colunas.append("registrado_em"); valores.append(registrado_em)
    arquivo_id = _executar(
        ex, log, f"arquivo {nome_arquivo}",
        f"INSERT INTO erp_automation.arquivo ({', '.join(colunas)}) "
        f"VALUES ({', '.join(['%s'] * len(colunas))}) "
        "ON CONFLICT (tipo_arquivo, sha256) DO NOTHING RETURNING id",
        tuple(valores), devolve=True)
    if arquivo_id is None and ex.registra:
        # ja existia: devolve o id do que esta la (idempotente por conteudo)
        arquivo_id = _executar(
            ex, log, f"arquivo {nome_arquivo} (existente)",
            "SELECT id FROM erp_automation.arquivo WHERE tipo_arquivo = %s AND sha256 = %s",
            (tipo_arquivo, sha), devolve=True)
        return arquivo_id
    if arquivo_id and titulos:
        for i, t in enumerate(titulos, start=1):
            _executar(
                ex, log, f"titulo {t.get('id_titulo')} do arquivo {nome_arquivo}",
                "INSERT INTO erp_automation.arquivo_titulo (fk_arquivo, numero_linha, id_titulo, "
                " id_operacao, id_pagamento_smart, codigo_ocorrencia, valor_titulo, flag_pix) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (arquivo_id, int(t.get("numero_linha") or i),
                 (str(t["id_titulo"]) if t.get("id_titulo") is not None else None),
                 t.get("id_operacao"), t.get("id_pagamento_smart"), t.get("codigo_ocorrencia"),
                 decimal_br(t.get("valor_titulo")), _flag(t.get("flag_pix"))))
    return arquivo_id


def registrar_evento_arquivo(ex: Execucao, fk_arquivo: int | None, tipo_evento: str, *,
                             resultado: str | None = None, detalhe: dict | None = None,
                             estrito: bool = False, ocorrido_em: datetime | None = None,
                             log=print) -> int | None:
    """Evento de arquivo e fato consumado por padrao: falha de banco vira aviso.

    estrito=True e para INTENCAO (`intencao_envio` do BB, antes do POST): na execucao
    estrita a falha levanta ErroDeRegistro e o POST nao acontece — sem rastro nao ha
    acao irreversivel. Fora do modo real continua avisando."""
    if estrito:
        return _registrar_evento_arquivo(ex, fk_arquivo, tipo_evento, resultado=resultado,
                                         detalhe=detalhe, ocorrido_em=ocorrido_em, log=log)
    if ex is None:
        return None
    return _fato_consumado(
        ex, log, f"evento {tipo_evento} do arquivo #{fk_arquivo}",
        lambda: _registrar_evento_arquivo(ex, fk_arquivo, tipo_evento, resultado=resultado,
                                          detalhe=detalhe, ocorrido_em=ocorrido_em, log=log))


def _registrar_evento_arquivo(ex: Execucao, fk_arquivo: int | None, tipo_evento: str, *,
                              resultado: str | None = None, detalhe: dict | None = None,
                              ocorrido_em: datetime | None = None, log=print) -> int | None:
    if tipo_evento not in TIPOS_EVENTO_ARQUIVO:
        raise ValueError(f"tipo_evento desconhecido: {tipo_evento!r}")
    if fk_arquivo is None:
        ex._avisar(log, f"evento {tipo_evento} sem arquivo registrado")
        return None
    colunas = ["fk_arquivo", "fk_job_execucao", "tipo_evento", "resultado", "detalhe_json"]
    valores = [fk_arquivo, ex.id, tipo_evento, resultado, _json(detalhe or {})]
    if ocorrido_em is not None:                     # so carga historica (ver registrar_arquivo)
        colunas.append("ocorrido_em"); valores.append(ocorrido_em)
    return _executar(
        ex, log, f"evento {tipo_evento} do arquivo #{fk_arquivo}",
        f"INSERT INTO erp_automation.arquivo_evento ({', '.join(colunas)}) "
        f"VALUES ({', '.join(['%s'] * len(colunas))}) RETURNING id",
        tuple(valores), devolve=True)


def buscar_arquivo(ex: Execucao, tipo_arquivo: str, *, sha256: str | None = None,
                   md5: str | None = None, id_no_smart: str | None = None, log=print) -> int | None:
    """O id de um arquivo ja registrado, pela chave que se tem (sha256, md5 ou id do Smart).
    md5 e id_no_smart sao colunas geradas da erp_005. None quando nao ha, ou sem banco."""
    if ex is None:
        return None
    if tipo_arquivo not in TIPOS_ARQUIVO:
        raise ValueError(f"tipo_arquivo desconhecido: {tipo_arquivo!r}")
    if sha256:
        coluna, valor = "sha256", sha256
    elif md5:
        coluna, valor = "md5", md5
    elif id_no_smart is not None:
        coluna, valor = "id_no_smart", str(id_no_smart)
    else:
        raise ValueError("informe sha256, md5 ou id_no_smart")
    return _fato_consumado(ex, log, f"busca do arquivo por {coluna}", lambda: _executar(
        ex, log, f"busca do arquivo por {coluna}",
        f"SELECT id FROM erp_automation.arquivo WHERE tipo_arquivo = %s AND {coluna} = %s "
        "ORDER BY id DESC LIMIT 1", (tipo_arquivo, valor), devolve=True))


def _consultar(ex: Execucao, log, descricao: str, sql: str, params: tuple):
    """Como _executar, mas devolve TODAS as linhas (lista) — None se degradada."""
    if ex is None or not ex.registra:
        if ex is not None:
            ex._avisar(log, "consulta nao feita: execucao sem banco")
        return None
    try:
        return _rodar(ex, log, descricao, sql, params, modo="todos")
    except Exception as e:  # noqa: BLE001
        if ex.estrito:
            raise ErroDeRegistro(f"{descricao} falhou: {type(e).__name__}: {str(e)[:160]}") from e
        ex._avisar(log, f"{descricao} falhou ({type(e).__name__}: {str(e)[:120]})")
        return None


def listar_md5(ex: Execucao, tipo_arquivo: str, log=print) -> set | None:
    """Os md5 de todos os arquivos deste tipo ja registrados — a memoria de idempotencia
    que o CSV de controle guardava (Fase 2 de docs/PLANO_CONTROLE_NO_BANCO.md). None
    quando nao ha banco ou a consulta falha: quem chama decide o que fazer (o retorno de
    pagamento volta ao CSV e avisa). Fato consumado: nunca levanta."""
    if ex is None:
        return None
    if tipo_arquivo not in TIPOS_ARQUIVO:
        raise ValueError(f"tipo_arquivo desconhecido: {tipo_arquivo!r}")
    linhas = _fato_consumado(ex, log, f"lista de md5 de {tipo_arquivo}", lambda: _consultar(
        ex, log, f"lista de md5 de {tipo_arquivo}",
        "SELECT md5 FROM erp_automation.arquivo WHERE tipo_arquivo = %s AND md5 IS NOT NULL",
        (tipo_arquivo,)))
    if linhas is None:
        return None
    return {str(l[0]).lower() for l in linhas if l and l[0]}


#: As views de controle da erp_005: as colunas do CSV de cada familia, lidas do banco.
#: (nome da view, colunas na ordem em que o CSV as tem — o que o job espera encontrar.)
VIEWS_CONTROLE = {
    "retorno": ("vw_controle_retorno",
                ("arquivo", "nome_smart", "hash", "conta", "titulos", "processado", "motivo", "quando")),
    "remessa": ("vw_controle_remessa",
                ("id", "arquivo", "tipo", "conta", "bytes", "md5", "titulos", "baixado_em", "ultimo_evento")),
    "pagamento": ("vw_controle_pagamento",
                  ("arquivo", "bytes", "md5", "titulos", "ids", "pix", "quando")),
    "retorno_pagamento": ("vw_controle_retorno_pagamento",
                          ("arquivo", "hash", "status_http", "quando")),
}
_TZ_CASA = "America/Sao_Paulo"


def _texto_como_no_csv(valor) -> str:
    """O CSV so tem texto: bool vira True/False, data vira 'AAAA-MM-DD HH:MM:SS' local."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "True" if valor else "False"
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            from zoneinfo import ZoneInfo
            valor = valor.astimezone(ZoneInfo(_TZ_CASA))
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    return str(valor)


def listar_controle(ex: Execucao, familia: str, *, chave: str, log=print) -> dict | None:
    """O controle de uma familia lido do banco, no formato em que o job le o CSV:
    {chave: {coluna: texto}}. Fase 2 de docs/PLANO_CONTROLE_NO_BANCO.md — e o que permite
    trocar `ler_controle()` de fonte sem tocar em quem consome. None sem banco ou se a
    consulta falhar (fato consumado): quem chama volta ao CSV e avisa."""
    if ex is None:
        return None
    if familia not in VIEWS_CONTROLE:
        raise ValueError(f"familia desconhecida: {familia!r} (aceitas: {tuple(VIEWS_CONTROLE)})")
    view, colunas = VIEWS_CONTROLE[familia]
    if chave not in colunas:
        raise ValueError(f"chave {chave!r} nao e coluna de {view}")
    linhas = _fato_consumado(ex, log, f"controle {familia}", lambda: _consultar(
        ex, log, f"controle {familia}",
        f"SELECT {', '.join(colunas)} FROM erp_automation.{view}", ()))
    if linhas is None:
        return None
    controle = {}
    for linha in linhas:
        registro = {c: _texto_como_no_csv(v) for c, v in zip(colunas, linha)}
        k = registro.get(chave, "")
        if k:
            controle[k.lower() if chave in ("md5", "hash") else k] = registro
    return controle


def anotar(ex: Execucao, chave: str, valor) -> None:
    """Guarda um fato que nao tem tabela propria (remessa que nao baixou, cancelamento de
    remessa anterior ao registro). Vai para detalhe_json no fechamento, como lista."""
    if ex is None:
        return
    ex.anotacoes.setdefault(chave, []).append(valor)


def fechar_execucao(ex: Execucao, status: str, *, codigo_saida: int | None = None,
                    qtd_itens: int | None = None, detalhe: dict | None = None, log=print) -> bool:
    """Fecha UMA vez. status: sucesso|falha|abandonada. Fecha a conexao sempre.
    As anotacoes (`anotar`) entram em detalhe_json junto com `detalhe`."""
    global _ATUAL
    if ex is None:
        return False
    if ex.anotacoes:
        detalhe = {**ex.anotacoes, **(detalhe or {})}
    if _ATUAL is ex:
        _ATUAL = None
    if status not in ("sucesso", "falha", "abandonada"):
        raise ValueError("status de fechamento e sucesso|falha|abandonada")
    ok = False
    try:
        # O fechamento e FATO CONSUMADO: o job ja fez o que fez. Levantar aqui so troca o
        # exit de um trabalho terminado por um traceback e um "failed" no hub (22/09/2026,
        # execucao #164: 9 remessas geradas, hub marcou falha). Falha vira aviso; a linha
        # fica `ativa` e a vw_job_execucao_abandonada a mostra depois de 2 h.
        try:
            r = _executar(
                ex, log, f"fechamento da execucao #{ex.id}",
                "UPDATE erp_automation.job_execucao SET terminado_em = now(), status = %s, "
                " codigo_saida = %s, qtd_itens = %s, detalhe_json = detalhe_json || %s "
                "WHERE id = %s AND status = 'ativa'",
                (status, codigo_saida, qtd_itens, _json(detalhe or {}), ex.id))
        except ErroDeRegistro as e:
            ex._avisar(log, f"{e} (execucao fica ativa no banco; o job termina normalmente)")
            r = None
        ok = bool(r)
        if ok:
            log(f"  [execucao] #{ex.id} fechada: {status}"
                + (f" · exit {codigo_saida}" if codigo_saida is not None else "")
                + (f" · {qtd_itens} item(ns)" if qtd_itens is not None else ""))
    finally:
        if ex._conn is not None:
            try:
                ex._conn.close()
            except Exception:  # noqa: BLE001
                pass
            ex._conn = None
    return ok
