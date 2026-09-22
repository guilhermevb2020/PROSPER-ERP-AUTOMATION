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
              "remessa_pagamento", "retorno_pagamento", "finalizar_operacao")
TIPOS_EVENTO_OPERACAO = ("avaliada", "finalizar_clicado", "finalizada", "finalizacao_falhou",
                         "finalizada_por_outro", "aviso_enviado")
TIPOS_EVENTO_ARQUIVO = ("gerado", "enviado", "recebido", "processado", "rejeitado", "retido")
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

    @property
    def registra(self) -> bool:
        """True quando ha banco e linha aberta; False = degradada."""
        return self._conn is not None and self.id is not None

    def _avisar(self, log, texto: str) -> None:
        # um aviso por motivo: o log do job nao vira uma parede de repeticoes
        if texto not in self.avisos:
            self.avisos.append(texto)
            log(f"  [execucao] AVISO: {texto}")


# --------------------------------------------------------------------------- #
# conexao
# --------------------------------------------------------------------------- #
def _parametros_conexao(job: str) -> dict:
    dsn = os.environ.get("ERP_EXECUCAO_DSN", "").strip()
    base = {"connect_timeout": CONNECT_TIMEOUT_S,
            "application_name": f"erp-automation:{job}"[:63]}
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
    """'18/09/2026' -> date. Qualquer outra coisa -> None (o bruto fica no detalhe_json)."""
    if isinstance(texto, date):
        return texto
    if not texto:
        return None
    try:
        return datetime.strptime(str(texto).strip()[:10], "%d/%m/%Y").date()
    except ValueError:
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
def abrir_execucao(automacao: str, job: str, *, flag_ensaio: bool, gatilho: str | None = None,
                   ambiente: str | None = None, task_nome: str | None = None,
                   run_id: str | None = None, apelido_credencial: str | None = None,
                   versao_codigo: str | None = None, detalhe: dict | None = None,
                   obrigatoria: bool = False, log=print) -> Execucao:
    """Abre a execucao. obrigatoria=True: sem banco, levanta; False: volta degradada."""
    if automacao not in AUTOMACOES:
        raise ValueError(f"automacao desconhecida: {automacao!r} (aceitas: {AUTOMACOES})")
    gatilho = gatilho or _gatilho_padrao()
    ambiente = ambiente or _ambiente_padrao()
    task_nome = task_nome or os.environ.get("HUB_TASK_NOME") or None
    run_id = run_id or os.environ.get("HUB_RUN_ID") or None
    versao_codigo = versao_codigo or os.environ.get("ERP_AUTOMATION_REVISION") or None
    apelido = apelido_seguro(apelido_credencial)

    ex = Execucao(id=None, automacao=automacao, job=job, flag_ensaio=flag_ensaio, estrito=obrigatoria)
    try:
        conn = _conectar(job)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO erp_automation.job_execucao "
                "(automacao, job, task_nome, run_id, gatilho, ambiente, flag_ensaio, "
                " apelido_credencial, versao_codigo, detalhe_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (automacao, job, task_nome, run_id, gatilho, ambiente, flag_ensaio,
                 apelido, versao_codigo, _json(detalhe or {})))
            ex.id = int(cur.fetchone()[0])
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


def _executar(ex: Execucao, log, descricao: str, sql: str, params: tuple, *, devolve=False):
    """Roda um comando na execucao. Degradada: avisa e devolve None. Estrita: levanta."""
    if not ex.registra:
        ex._avisar(log, "registro nao feito: execucao sem banco (o ensaio segue; em modo real isto levanta)")
        return None
    try:
        with ex._conn.cursor() as cur:
            cur.execute(sql, params)
            if devolve:
                linha = cur.fetchone()
                return int(linha[0]) if linha else None
        return True
    except Exception as e:  # noqa: BLE001
        if ex.estrito:
            raise ErroDeRegistro(f"{descricao} falhou: {type(e).__name__}: {str(e)[:160]}") from e
        ex._avisar(log, f"{descricao} falhou ({type(e).__name__}: {str(e)[:120]})")
        return None


def registrar_evento_operacao(ex: Execucao, id_operacao, tipo_evento: str, *,
                              resultado: str | None = None, cedente: str | None = None,
                              valor_liquido=None, pendencias=None, detalhe: dict | None = None,
                              linhas_pagamento: list | None = None, log=print) -> int | None:
    """Um fato sobre a operacao. Devolve o id do evento (None se nao registrou)."""
    if tipo_evento not in TIPOS_EVENTO_OPERACAO:
        raise ValueError(f"tipo_evento desconhecido: {tipo_evento!r}")
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


def registrar_arquivo(ex: Execucao, tipo_arquivo: str, sentido: str, *, nome_arquivo: str,
                      conteudo: bytes | None = None, caminho: str | None = None,
                      qtd_registros: int | None = None, valor_total=None,
                      conta_id: str | None = None, conta_label: str | None = None,
                      origem_caminho: str | None = None, destino_caminho: str | None = None,
                      detalhe: dict | None = None, titulos: list | None = None,
                      log=print) -> int | None:
    """Registra um arquivo pelo conteudo (sha256). O mesmo conteudo nao entra duas vezes:
    devolve o id ja existente. titulos: [{numero_linha, id_titulo, id_operacao, ...}]."""
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
    arquivo_id = _executar(
        ex, log, f"arquivo {nome_arquivo}",
        "INSERT INTO erp_automation.arquivo "
        "(fk_job_execucao, tipo_arquivo, sentido, nome_arquivo, sha256, qtd_bytes, qtd_registros, "
        " valor_total, conta_id, conta_label, origem_caminho, destino_caminho, detalhe_json) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (tipo_arquivo, sha256) DO NOTHING RETURNING id",
        (ex.id, tipo_arquivo, sentido, nome_arquivo, sha, len(conteudo), qtd_registros,
         decimal_br(valor_total), conta_id, conta_label, origem_caminho, destino_caminho,
         _json(detalhe or {})),
        devolve=True)
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
                             log=print) -> int | None:
    if tipo_evento not in TIPOS_EVENTO_ARQUIVO:
        raise ValueError(f"tipo_evento desconhecido: {tipo_evento!r}")
    if fk_arquivo is None:
        ex._avisar(log, f"evento {tipo_evento} sem arquivo registrado")
        return None
    return _executar(
        ex, log, f"evento {tipo_evento} do arquivo #{fk_arquivo}",
        "INSERT INTO erp_automation.arquivo_evento (fk_arquivo, fk_job_execucao, tipo_evento, "
        " resultado, detalhe_json) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (fk_arquivo, ex.id, tipo_evento, resultado, _json(detalhe or {})), devolve=True)


def fechar_execucao(ex: Execucao, status: str, *, codigo_saida: int | None = None,
                    qtd_itens: int | None = None, detalhe: dict | None = None, log=print) -> bool:
    """Fecha UMA vez. status: sucesso|falha|abandonada. Fecha a conexao sempre."""
    if status not in ("sucesso", "falha", "abandonada"):
        raise ValueError("status de fechamento e sucesso|falha|abandonada")
    ok = False
    try:
        r = _executar(
            ex, log, f"fechamento da execucao #{ex.id}",
            "UPDATE erp_automation.job_execucao SET terminado_em = now(), status = %s, "
            " codigo_saida = %s, qtd_itens = %s, detalhe_json = detalhe_json || %s "
            "WHERE id = %s AND status = 'ativa'",
            (status, codigo_saida, qtd_itens, _json(detalhe or {}), ex.id))
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
