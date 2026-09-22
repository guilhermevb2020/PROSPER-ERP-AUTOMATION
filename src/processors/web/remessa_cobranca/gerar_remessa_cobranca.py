# -*- coding: utf-8 -*-
"""
gerar_remessa_cobranca.py - gera as remessas CNAB no Smart e baixa os .REM.

Robo do ERP AUTOMATION. Roda DESATENDIDO: sobe o proprio Chrome no display :97,
loga via CapSolver, percorre as contas, gera a remessa de cada uma, baixa o
arquivo e fecha. Um login por run.

Fluxo por conta (ciclo_conta):
    filtro -> le o form da tela de confirmacao -> valida -> POST de geracao
           -> le os ids do resultado -> baixa cada .REM -> confere na pasta

Tudo por HTTP, sobre os cookies da sessao: nenhuma etapa depende de clicar em
tela. O envio ao banco NAO e deste robo (quem sobe para a API do BMP e o job
`enviar_remessas`, no process-automation).

SEGURANCA
---------
- DRY_RUN e o padrao (`DRY_RUN_REM`). Sem `--pra-valer` o robo monta o POST,
  mostra o que faria e NAO gera nada. Gerar consome sequencial e tira titulo da
  fila: nao e reversivel.
- Sessao caida ABORTA a rodada. Filtro vazio pode ser "sem titulo" ou "sessao
  morreu" — o robo confirma antes, senao a rodada termina com cara de sucesso
  tendo pulado contas que TINHAM remessa.
- POST que foi mas nao devolveu os ids NAO vira falha silenciosa: a remessa
  existe no Smart, entao o robo a recupera pela tela de listagem (senao ela
  fica orfa, o sequencial ja foi consumido e a proxima rodada dira "nada a
  fazer" porque os titulos sairam da fila). Vale TAMBEM quando o POST nao
  responde (timeout, conexao cortada): a duvida e a mesma, e por isso a
  excecao nao aborta a conta em silencio.
- Conta que ficou INCERTA (erro no meio do ciclo, ou recuperacao sem achar a
  remessa) faz a rodada sair != 0 mesmo que nenhuma outra conta tenha falhado.
  Rodada que pula conta e termina com exit 0 e o modo de falha mais caro: o
  hub marca sucesso e ninguem procura.
- Valida CNAB-400 antes de salvar (header `01REMESSA` + linhas de 400). Se a
  sessao cair no meio, o Smart devolve HTML — descarta em vez de gravar lixo
  com nome de .REM.
- Idempotente: `controle_remessas.csv` guarda id/arquivo/md5 e nao rebaixa.

Uso:
    # producao (o wrapper do hub chama isto)
    sh /app/src/processors/web/remessa_cobranca/run_agendado.sh

    # manual, dentro do container
    python /app/src/processors/web/remessa_cobranca/gerar_remessa_cobranca.py --gerar --todas-contas
    python .../gerar_remessa_cobranca.py --gerar --conta tigrao --pra-valer
    python .../gerar_remessa_cobranca.py --gerar --conta tigrao --simular    # so olha a fila
    python .../gerar_remessa_cobranca.py --listar --conta cast --dias 30
    python .../gerar_remessa_cobranca.py --contas
    python .../gerar_remessa_cobranca.py --ids 25521 25522

    # sobre uma janela que voce ja logou no VNC (desenvolvimento)
    python .../gerar_remessa_cobranca.py --cdp --listar
"""
import argparse
import base64
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from playwright.sync_api import sync_playwright  # noqa: E402

import _nextcloud as nuvem                        # noqa: E402
import _sessao                                    # noqa: E402
import gerar as ger                               # noqa: E402
import exclusoes                                  # noqa: E402
import falhas                                     # noqa: E402
import cancelar
import login as autenticacao                      # noqa: E402
import remessa_config as cfg                      # noqa: E402
from src.common.clients import execucao_job       # noqa: E402

# Tipos de remessa na chave de `idsSucesso` (a tela "Remessa gerada" agrupa o
# que gerou por tipo). A chave NAO e o codigo de ocorrencia do CNAB - esse fica
# nas posicoes 109-110 do registro de detalhe. O de-para abaixo foi MEDIDO nos
# arquivos gerados em 31/07/2026 (banco 274 BMP MONEY PLUS), lendo a ocorrencia
# dos proprios .REM:
#
#     Smart "1" -> ocorrencia 01  (4 titulos em mp atacadao)
#     Smart "2" -> ocorrencia 06  (1 titulo  em mp atacadao)
#     Smart "3" -> ocorrencia 02  (1 e 3 titulos em mp bindergraf / central do vale)
#
# O nome de cada ocorrencia vem do padrao CNAB-400 (o layout que o header
# `01REMESSA01COBRANCA` segue) - a tabela propria do BMP para REMESSA nao esta
# no acervo, so a de RETORNO. Se ela aparecer, confira antes de mudar isto.
TIPOS = {
    "1": "Envio de cobranca registrado",   # ocorrencia 01 - entrada de titulo
    "2": "Alteracao de vencimento",        # ocorrencia 06 - prorrogacao
    "3": "Quitacao ou cancelamento",       # ocorrencia 02 - pedido de baixa
}

CABECALHO_CONTROLE = ["id", "arquivo", "tipo", "bytes", "md5", "titulos", "baixado_em"]

# Codigos de saida (o hub-orchestration marca a execucao pelo exit code).
SAIU_OK = 0
SAIU_SEM_NAVEGADOR = 1
SAIU_SEM_SESSAO = 2
SAIU_RESULTADO_ILEGIVEL = 3
SAIU_SEM_TELA = 4
SAIU_CONTA_NAO_RESOLVIDA = 5
SAIU_RODADA_INCOMPLETA = 6


# --------------------------------------------------------------------------- #
# util
# --------------------------------------------------------------------------- #
def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _b64_para_dict(raw: str):
    """Decodifica o param `resultado` (base64 de um JSON). Aceita a URL inteira."""
    if "resultado=" in raw:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        raw = q.get("resultado", [""])[0]
    raw = urllib.parse.unquote(raw).strip()
    if not raw:
        return None
    try:
        pad = raw + "=" * (-len(raw) % 4)
        return json.loads(base64.b64decode(pad).decode("utf-8", errors="replace"))
    except Exception as e:
        log(f"  aviso: nao decodifiquei o resultado ({e})")
        return None


def validar_cnab(dados: bytes):
    """Confere que o corpo baixado e mesmo um CNAB-400 (e nao HTML de erro).
    Retorna (ok, mensagem, qtd_titulos)."""
    if not dados:
        return False, "resposta vazia", 0
    cabeca = dados[:200].lstrip()
    if cabeca[:1] in (b"<", b"{"):
        return False, "veio HTML/JSON (sessao caida ou id invalido?)", 0
    try:
        texto = dados.decode("latin-1")
    except Exception as e:
        return False, f"nao decodificou: {e}", 0
    linhas = [linha for linha in texto.splitlines() if linha.strip()]
    if not linhas:
        return False, "arquivo sem linhas", 0
    if not linhas[0].startswith("01REMESSA"):
        return False, f"header inesperado: {linhas[0][:40]!r}", 0
    fora = [i for i, linha in enumerate(linhas) if len(linha) != 400]
    if fora:
        return False, f"{len(fora)} linha(s) fora dos 400 chars (1a: linha {fora[0] + 1})", 0
    # BB usa tipo 7 para convenio de sete posicoes e tipo 1 no layout antigo.
    # Tipo 5 do BB e complemento (multa etc.), nao outro titulo. No MoneyPlus
    # permanece tipo 1; o complemento tipo 2 tambem nao entra na contagem.
    tipos_titulo = ("1", "7") if linhas[0][76:79] == "001" else ("1",)
    titulos = sum(1 for linha in linhas if linha.startswith(tipos_titulo))
    return True, f"CNAB-400 ok ({len(linhas)} registros)", titulos


# --------------------------------------------------------------------------- #
# controle (idempotencia)
# --------------------------------------------------------------------------- #
def ler_controle():
    if not os.path.exists(cfg.ARQ_CONTROLE):
        return {}
    with open(cfg.ARQ_CONTROLE, encoding="utf-8", newline="") as f:
        return {linha["id"]: linha for linha in csv.DictReader(f) if linha.get("id")}


def gravar_controle(registro):
    novo = not os.path.exists(cfg.ARQ_CONTROLE)
    os.makedirs(os.path.dirname(cfg.ARQ_CONTROLE) or ".", exist_ok=True)
    with open(cfg.ARQ_CONTROLE, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECALHO_CONTROLE)
        if novo:
            w.writeheader()
        w.writerow(registro)


def sessao_valida(ctx):
    """Ping autenticado. Mesma heuristica do login (trata o `expira.php` que o
    Smart devolve com status 200 — ver login.parece_deslogado)."""
    return autenticacao.esta_logado(ctx)


# --------------------------------------------------------------------------- #
# descoberta dos ids
# --------------------------------------------------------------------------- #
def listar_contas(ctx):
    """value -> rotulo do select de Conta ('mp cast', 'Banco do Brasil', ...)."""
    try:
        r = ctx.request.get(cfg.URL_DOWNLOAD_REMESSA, timeout=40_000)
        html = r.body().decode("iso-8859-1", errors="replace")
    except Exception as e:
        log(f"ERRO ao ler as contas: {e}")
        return {}
    contas = {}
    for m in re.finditer(r"<option[^>]*value\s*=\s*[\"']?(\d+)[\"']?[^>]*>(.*?)</option>",
                         html, re.I | re.S):
        rotulo = re.sub(r"<[^>]+>", "", m.group(2))
        rotulo = re.sub(r"\s+", " ", rotulo).strip()
        if rotulo and m.group(1) != "0":
            contas[m.group(1)] = rotulo
    return contas


def resolver_conta(ctx, texto):
    """Aceita o numero ('291') ou parte do nome ('cast'). Retorna (num, rotulo)."""
    texto = (texto or "").strip()
    contas = listar_contas(ctx)
    if texto.isdigit():
        return texto, contas.get(texto, "?")
    alvo = texto.lower()
    # match EXATO ganha do parcial ('cast' -> 'mp cast', nao 'mp madeiras castella')
    exatos = [(n, r) for n, r in contas.items()
              if r.lower() == alvo or r.lower().removeprefix("mp ").strip() == alvo]
    if len(exatos) == 1:
        return exatos[0]
    achados = [(n, r) for n, r in contas.items() if alvo in r.lower()]
    if len(achados) == 1:
        return achados[0]
    if not achados:
        log(f"ERRO: nenhuma conta casa com {texto!r}. Use --contas p/ ver a lista.")
    else:
        log(f"ERRO: {texto!r} e ambiguo -> {[r for _, r in achados[:8]]}")
    return None, None


def listar_remessas(ctx, conta, de, ate):
    """POST na tela de Download de Remessa -> lista de dicts com id/arquivo/data.

    A grade e um <table> simples; cada <tr> tem:
      radio value=<id> | <a href=mandarremessa.php?file=<id>&cc=<conta>>ARQ.REM</a>
      | botao detalhes | conta | dd/mm/aaaa hh:mm | tamanho
    """
    corpo = urllib.parse.urlencode({
        "form_submit": "1", "checks": "", "cancelamento": "0", "radioSel": "",
        "contaSelected": conta, "contaCorrente": conta,
        "periodo_inicial": de, "periodo_final": ate,
    })
    try:
        r = ctx.request.post(
            cfg.URL_DOWNLOAD_REMESSA, data=corpo,
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=60_000)
        html = r.body().decode("iso-8859-1", errors="replace")
    except Exception as e:
        log(f"ERRO na listagem: {e}")
        return []
    if r.status != 200 or autenticacao.parece_deslogado(html):
        log(f"ERRO: listagem sem resposta util (status={r.status}) - sessao caiu")
        return []

    achadas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        m_id = re.search(r"mandarremessa\.php\?file=(\d+)(?:&(?:amp;)?cc=(\d+))?", tr, re.I)
        if not m_id:
            continue
        celulas = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                   for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        arquivo = next((c for c in celulas if c.upper().endswith(".REM")), None)
        data = next((c for c in celulas if re.match(r"\d{2}/\d{2}/\d{4}", c)), "")
        tamanho = next((c for c in celulas if "byte" in c.lower()), "")
        rotulo = next((c for c in celulas
                       if c and c != arquivo and c != data and c != tamanho
                       and "detalhe" not in c.lower()), "")
        achadas.append({
            "id": int(m_id.group(1)), "cc": m_id.group(2) or conta,
            "arquivo": arquivo or f"remessa_{m_id.group(1)}.REM",
            "conta": rotulo, "data": data, "tamanho": tamanho,
        })
    return achadas


def descobrir_na_tela(ctx):
    """Procura a tela 'Remessa gerada' aberta na sessao e extrai (tipo, id).
    Retorna (lista_de_pares, url_encontrada)."""
    for pg in ctx.pages:
        try:
            frames = pg.frames
        except Exception:
            continue
        for f in frames:
            url = f.url or ""
            if "gridremessagerada" not in url:
                continue
            dados = _b64_para_dict(url)
            if not dados:
                continue
            pares = [(str(tipo), int(fid))
                     for tipo, fid in (dados.get("idsSucesso") or {}).items()]
            erros = dados.get("idsErro") or []
            if erros:
                log(f"  ATENCAO: a tela reporta idsErro={erros}")
            return pares, url
    return [], None


# --------------------------------------------------------------------------- #
# download
# --------------------------------------------------------------------------- #
def baixar_id(ctx, fid):
    """GET no endpoint de download. Retorna (nome_sugerido, bytes) ou (None, None).

    SEM `confirmar=1` de proposito: o link da tela e
    `mandarremessa.php?file=<id>&confirmar=1`; testado, o arquivo vem
    byte-identico sem o parametro, e nao foi confirmado se o `confirmar` marca a
    remessa como enviada no Smart. O robo nao arrisca.
    """
    url = f"{cfg.SMART_BASE}/financeiro/mandarremessa.php?file={fid}"
    try:
        r = ctx.request.get(url, timeout=90_000)
    except Exception as e:
        log(f"  id={fid}: ERRO na requisicao: {e}")
        return None, None
    if r.status != 200:
        log(f"  id={fid}: status {r.status}")
        return None, None
    dados = r.body()
    nome = None
    cd = r.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
    if m:
        nome = os.path.basename(m.group(1).strip())
    return nome or f"remessa_{fid}.REM", dados


# Sufixo que `processar` poe no nome quando dois .REM de conteudo DIFERENTE caem
# na pasta local com o MESMO nome: duas contas geraram o mesmo sequencial no
# mesmo dia, e a pasta e plana. Ele existe SO para o disco. No Nextcloud o
# caminho ja separa por empresa, e o nome tem de continuar o que o Smart deu
# (`CB<ddmm><seq7>.REM`): o `enviar_remessa_400` (process-automation) le o
# sequencial dos 7 ultimos digitos do NOME e recusa o arquivo quando nao bate
# com o header. Foi o que segurou a remessa da WJ MOREIRA em 08/09/2026
# (`CB08090000011_dup212306.REM` -> "sequencial do nome 1212306 difere").
_SUFIXO_DUP = re.compile(r"_dup\d{6}(?=\.REM$)", re.I)


def nome_para_nuvem(nome_local: str) -> str:
    """Nome com que o .REM sobe ao Nextcloud: o do Smart, sem o `_dup` do disco."""
    return _SUFIXO_DUP.sub("", nome_local)


def processar(ctx, itens, forcar=False, execucao=None):
    """Baixa, valida e salva cada item ({'id':..., 'rotulo':...}). Retorna quantos salvou."""
    controle = ler_controle()
    salvos = 0
    enviados_nc = falhas_nc = 0
    os.makedirs(cfg.PASTA_REMESSAS, exist_ok=True)

    for item in sorted(itens, key=lambda x: x["id"]):
        fid = item["id"]
        rotulo = item.get("rotulo") or "?"
        chave = str(fid)

        if chave in controle and not forcar:
            log(f"  id={fid} ({rotulo}): JA BAIXADO -> "
                f"{controle[chave]['arquivo']} (use --forcar p/ rebaixar)")
            continue

        nome, dados = baixar_id(ctx, fid)
        if dados is None:
            # O Smart ja considera os titulos despachados: sem rastro, eles somem.
            falhas.registrar(fid, conta=item.get("conta"), rotulo=rotulo, motivo="download do Smart falhou",
                             titulos=item.get("titulos_grade"), log=log)
            continue

        ok, msg, titulos = validar_cnab(dados)
        if not ok:
            reg = falhas.registrar(fid, conta=item.get("conta"), rotulo=rotulo, motivo=f"DESCARTADO - {msg}",
                                   dados=dados, titulos=item.get("titulos_grade"), nome_arquivo=nome, log=log)
            quem = "; ".join(f"{c['documento'] or '?'} ({c['bytes']} bytes: {c['motivo']})"
                             for c in (reg or {}).get("culpados") or [])
            log(f"  id={fid} ({rotulo}): DESCARTADO - {msg}" + (f" - culpado(s): {quem}" if quem else ""))
            continue

        destino = os.path.join(cfg.PASTA_REMESSAS, nome)
        if os.path.exists(destino) and not forcar:
            # mesmo nome ja no disco: so avisa se o conteudo for diferente
            with open(destino, "rb") as f:
                atual = f.read()
            if atual == dados:
                log(f"  id={fid} ({rotulo}): arquivo identico ja no disco -> {nome}")
            else:
                destino = os.path.join(
                    cfg.PASTA_REMESSAS,
                    f"{os.path.splitext(nome)[0]}_dup{datetime.now():%H%M%S}.REM")
                log(f"  id={fid}: ATENCAO conteudo diferente com o mesmo nome -> "
                    f"salvando como {os.path.basename(destino)}")
                with open(destino, "wb") as f:
                    f.write(dados)
        else:
            with open(destino, "wb") as f:
                f.write(dados)

        md5 = hashlib.md5(dados).hexdigest()
        log(f"  id={fid} ({rotulo}): OK {msg}, {titulos} titulo(s), "
            f"{len(dados)} bytes -> {os.path.basename(destino)}")

        # Nextcloud DEPOIS do disco, e nunca no lugar dele: a pasta local e o
        # controle continuam sendo a fonte de verdade da idempotencia. Falha
        # aqui e AVISO, nao falha de rodada - o arquivo ja esta salvo, e a
        # proxima subida o alcanca (`--subir-pendentes`).
        # Sobe com o nome do Smart (`nome`), NAO com o do disco: o `_dup` e
        # desambiguacao da pasta local, e com ele no nome o banco recusa.
        if cfg.ENVIAR_NEXTCLOUD:
            ok_nc, alvo_nc, detalhe_nc = nuvem.enviar(dados, nome)
            if ok_nc:
                enviados_nc += 1
                log(f"     -> Nextcloud: {alvo_nc}")
            else:
                falhas_nc += 1
                log(f"     -> Nextcloud FALHOU ({detalhe_nc}) - o arquivo esta "
                    f"no disco, nada foi perdido: {alvo_nc}")

        gravar_controle({
            "id": fid, "arquivo": os.path.basename(destino), "tipo": rotulo,
            "bytes": len(dados), "md5": md5, "titulos": titulos,
            "baixado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        # O mesmo fato no banco, ao lado do CSV (dupla escrita ate o corte). O nome
        # gravado e o do SMART, como no Nextcloud, nao o `_dup` do disco.
        _arq_id = execucao_job.registrar_arquivo(
            execucao, "remessa_cobranca_cnab_400", "gerado",
            nome_arquivo=nome, conteudo=dados, qtd_registros=titulos,
            conta_id=(str(item.get("conta")) if item.get("conta") else None),
            conta_label=rotulo, destino_caminho=destino,
            detalhe={"md5": md5, "id_no_smart": fid,
                     "nome_no_disco": os.path.basename(destino)}, log=log)
        if _arq_id:
            execucao_job.registrar_evento_arquivo(execucao, _arq_id, "gerado", log=log)
            if cfg.ENVIAR_NEXTCLOUD and ok_nc:
                execucao_job.registrar_evento_arquivo(
                    execucao, _arq_id, "enviado", resultado=alvo_nc, log=log)
        salvos += 1

    if falhas_nc:
        log(f"  ATENCAO Nextcloud: {enviados_nc} enviado(s), {falhas_nc} falha(s) "
            f"- rode `--subir-pendentes` depois de resolver")
    return salvos


# --------------------------------------------------------------------------- #
# ciclo completo por conta: gerar -> baixar -> conferir na pasta
# --------------------------------------------------------------------------- #
def carregar_contas_carteiras():
    """Mapa conta->carteiras extraido da tela Gerar Remessa (arquivo gerado por
    atualizar_contas.py). Se faltar, o robo cai no --conta/--carteira da linha."""
    caminho = os.path.join(_AQUI, "contas_carteiras.json")
    if not os.path.exists(caminho):
        return {}, {}
    with open(caminho, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("contas", {}), d.get("carteiras", {})


class SessaoCaiu(Exception):
    """Sessao do Smart morreu no meio da rodada -> abortar (nunca seguir).

    Sem isso o filtro vazio viraria 'essa conta nao tem titulo' e a rodada
    terminaria com cara de sucesso tendo pulado contas que TINHAM remessa.
    """


def guardar_tela(pagina, conta, rotulo, dias=7):
    """Guarda a tela de confirmacao como o Smart a devolveu (DEBUG_DIR, 7 dias).

    E a unica forma de ver a grade real — colunas, nomes e valores dos checkboxes —
    sem gerar nada: a grade so aparece quando ha titulo na fila, e a fila esvazia na
    rodada das 18:00. 17/09/2026: o valor do checkbox NAO e o id do titulo do ERP
    (911243 no controle do participante contra 948707 no titulo), entao excluir um
    titulo da remessa exige ler a linha da grade, e para isso e preciso te-la.
    ~36 KB por conta; o que passar de `dias` e apagado aqui mesmo.
    """
    try:
        os.makedirs(cfg.DEBUG_DIR, exist_ok=True)
        limite = time.time() - dias * 86400
        for nome in os.listdir(cfg.DEBUG_DIR):
            caminho = os.path.join(cfg.DEBUG_DIR, nome)
            if nome.startswith("form_") and os.path.getmtime(caminho) < limite:
                os.remove(caminho)
        dump = os.path.join(cfg.DEBUG_DIR,
                            f"form_{conta}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        with open(dump, "w", encoding="iso-8859-1", errors="replace") as fh:
            fh.write(pagina)
        log(f"  {rotulo}: tela de confirmacao guardada em {dump}")
    except OSError as e:                                            # noqa: BLE001
        log(f"  {rotulo}: nao guardei a tela ({e}) — segue sem ela")


def ciclo_conta(ctx, conta, rotulo, carteira, dry_run=True, forcar=False, execucao=None):
    """Gera a remessa de UMA conta e baixa os arquivos. Retorna dict do resultado."""
    saida = {"conta": conta, "rotulo": rotulo, "carteira": carteira,
             "titulos": 0, "gerou": False, "ids": [], "baixados": 0, "motivo": "",
             # "nao sei o que aconteceu no Smart" — diferente de "nao gerou".
             "incerto": False, "excluidos": 0, "retidos": []}

    pagina = ger.filtrar(ctx, conta, carteira)
    if pagina is None:
        # resposta vazia pode ser 2 coisas MUITO diferentes: sessao caida ou
        # tela com problema. Confirma antes de tratar como "sem titulo".
        if not sessao_valida(ctx):
            raise SessaoCaiu(f"sessao do Smart caiu ao processar {rotulo}")
        saida["motivo"] = "filtro nao respondeu (sessao ok - tela com problema?)"
        log(f"  {rotulo}: {saida['motivo']}")
        return saida

    guardar_tela(pagina, conta, rotulo)

    form = ger.ler_form(pagina)
    # O que o banco recusaria — sacado sem numero no endereco (lista do
    # process-automation) e entrada que vence hoje ou antes (MoneyPlus): desmarca
    # ANTES de validar, para "nenhum titulo selecionado" valer de verdade.
    afetados = exclusoes.aplicar(form, exclusoes.carregar(log=log), log=log)
    saida["excluidos"] = sum(1 for a in afetados if a["regra"] == "lista")
    saida["retidos"] = [a for a in afetados if a["regra"] == "vencimento"]
    # O que esta geracao vai levar, lido da grade: se o arquivo nao chegar ao banco,
    # e isto que fica despachado no Smart e precisa de rastro (falhas.py).
    marcados = falhas.titulos_do_form(form)
    r = form["resumo"]
    saida["titulos"] = r["titulos_marcados"]

    ok, motivo = ger.validar(form)
    if not ok:
        saida["motivo"] = motivo
        log(f"  {rotulo}: nada a fazer ({motivo})")
        return saida

    log(f"  {rotulo}: {r['titulos_marcados']}/{r['titulos_total']} titulo(s), "
        f"sequencial {r['NumSequencial']}")

    res = ger.gerar(ctx, form, dry_run=dry_run)
    if res["ok"] is None:
        saida["motivo"] = "DRY_RUN"
        log(f"  {rotulo}: DRY_RUN - NAO gerei. POST teria {len(res['corpo'])} bytes "
            f"({r['titulos_marcados']} titulos)")
        return saida
    if not res["ok"]:
        if not res.get("enviado"):
            saida["motivo"] = res["motivo"]
            log(f"  {rotulo}: FALHOU - {res['motivo']}")
            return saida

        # O POST FOI mas nao deu p/ ler os ids. A remessa provavelmente existe
        # no Smart: NAO pode virar orfa. Recupera pela tela de listagem, pegando
        # o que apareceu hoje nessa conta e ainda nao esta no controle.
        log(f"  {rotulo}: ATENCAO - {res['motivo']}")
        log(f"  {rotulo}: recuperando pela listagem...")
        hoje = datetime.now().strftime("%Y-%m-%d")
        achadas = listar_remessas(ctx, conta, hoje, hoje)
        controle = ler_controle()
        novas = [a for a in achadas if str(a["id"]) not in controle]
        if not novas:
            saida["incerto"] = True
            saida["motivo"] = (f"{res['motivo']} E a listagem nao mostrou remessa "
                               f"nova hoje - CONFERIR NO SMART")
            log(f"  {rotulo}: {saida['motivo']}")
            falhas.registrar(f"incerto-{conta}-{datetime.now(exclusoes.TZ_SP):%Y%m%d%H%M%S}", conta=conta,
                             rotulo=rotulo, motivo=saida["motivo"], titulos=marcados, log=log)
            return saida
        saida["gerou"] = True
        saida["ids"] = [a["id"] for a in novas]
        saida["motivo"] = "recuperado pela listagem"
        log(f"  {rotulo}: RECUPERADO -> ids {saida['ids']}")
        saida["baixados"] = processar(
            ctx, [{"id": a["id"], "rotulo": f"{rotulo} (recuperado)", "conta": conta} for a in novas],
            forcar, execucao=execucao)
        return saida

    saida["gerou"] = True
    saida["ids"] = [i for _, i in res["ids"]]
    log(f"  {rotulo}: GEROU -> ids {saida['ids']}"
        + (f"  ATENCAO idsErro={res['erros']}" if res["erros"] else ""))

    itens = [{"id": fid, "rotulo": f"{rotulo} {TIPOS.get(tipo, tipo)}", "conta": conta,
              # a grade so descreve as ENTRADAS (tipo 1); baixas vao pelo campo instrucoes
              "titulos_grade": marcados if str(tipo) == "1" else None}
             for tipo, fid in res["ids"]]
    saida["baixados"] = processar(ctx, itens, forcar, execucao=execucao)

    # confere que os arquivos existem mesmo na pasta
    controle = ler_controle()
    faltando = [i for i in saida["ids"]
                if str(i) not in controle
                or not os.path.exists(os.path.join(cfg.PASTA_REMESSAS,
                                                   controle[str(i)]["arquivo"]))]
    if faltando:
        saida["motivo"] = f"gerou mas NAO baixou ids {faltando}"
        log(f"  {rotulo}: ATENCAO - {saida['motivo']}")
    return saida


def janela(args):
    """A janela (de, ate) que a tela de Download de Remessa recebe.

    ⭐ Extraida do `executar()` em 21/09/2026, quando o cancelamento passou a
    precisar da MESMA janela: a remessa so aparece na grade dentro do periodo, e
    duas contas diferentes do mesmo intervalo produziriam ids que existem numa e
    nao na outra.
    """
    ate = args.ate or datetime.now().strftime("%Y-%m-%d")
    de = args.de or (datetime.now() - timedelta(days=args.dias)).strftime("%Y-%m-%d")
    return de, ate


def _ler_controle():
    """O `remessas_geradas.json` do robo — traz o `tipo`, de onde sai a conta do Smart."""
    try:
        with open(cfg.ARQ_REMESSAS_GERADAS, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def rodada_cancelamento(ctx, args, dry, execucao=None):
    """Cancela no Smart as remessas que o process-automation apontou. Exit code.

    ⛔ **A lista vem PRONTA, e este robo nao a discute.** Cancelar devolve a fila
    TODOS os titulos da remessa; um titulo que ja tenha boleto registrado no banco
    sairia de novo e o sacado receberia dois boletos do mesmo titulo. Quem sabe
    disso e quem pergunta ao banco — o process-automation, em
    `apontar_cancelamentos_remessa_400`. Varrer a tela e decidir aqui seria refazer
    essa conta sem os dados.

    ⭐ **Cada id e conferido DEPOIS do POST**, pela grade: HTTP 200 diz que o Smart
    respondeu, nao que cancelou. A remessa cancelada some da listagem, e e isso que
    confirma. Sem essa leitura o robo afirmaria um cancelamento que pode nao ter
    acontecido — e a rodada seguinte nao tentaria de novo.

    ⚠️ **Rodada com id incerto sai `SAIU_RODADA_INCOMPLETA`**, nao 0. E a licao do
    BUG-681: naquele dia dois timeouts fizeram duas contas serem puladas em
    silencio, com a task marcada como sucesso, e os titulos esperaram de sexta a
    segunda. Aqui o hub precisa saber que alguem tem de olhar.
    """
    caminho = args.cancelamentos_json or cancelar.ARQUIVO_PADRAO
    remessas, recusa = cancelar.ler_lista(caminho)
    if recusa:
        log(f"CANCELAMENTO: {recusa}")
        return SAIU_OK if "nao existe" in recusa else SAIU_RODADA_INCOMPLETA
    if not remessas:
        log("CANCELAMENTO: nada apontado — nenhuma remessa recusada esta liberada hoje.")
        return SAIU_OK

    contas_mapa, _carteiras = carregar_contas_carteiras()
    controle = _ler_controle()
    log(f"CANCELAMENTO {'(DRY_RUN - nao cancela nada)' if dry else '*** PRA VALER ***'}"
        f" | {len(remessas)} remessa(s) apontada(s)"
        + (f" | janela FIXA {janela(args)[0]} a {janela(args)[1]}" if (args.de or args.ate)
           else " | janela por remessa, da data em que o robo a baixou"))

    ja_feitos = cancelar.ler_feitos()
    pulados = [i for i in remessas if i in ja_feitos]
    if pulados:
        log(f"  {len(pulados)} remessa(s) ja cancelada(s) numa rodada anterior - pulando: "
            f"{pulados[:6]}{'...' if len(pulados) > 6 else ''}")
        remessas = {i: d for i, d in remessas.items() if i not in ja_feitos}
        if not remessas:
            log("CANCELAMENTO: tudo que estava apontado ja foi cancelado. Nada a fazer.")
            return SAIU_OK

    feitos = incertos = falhos = 0
    for smart_id, dados in sorted(remessas.items(), key=lambda kv: int(kv[0])):
        arquivo = dados.get("arquivo", "?")
        # ⛔ A conta do POST e a do SMART (287, 291, 298...), NUNCA o `numero_cedente`
        # do CNAB (1026716) — sao duas chaves que parecem a mesma. Mandar a errada
        # monta a grade de outra conta, o id nao aparece nela, e o cancelamento
        # silenciosamente nao acha nada.
        entrada = cancelar.entrada_do_controle(controle, arquivo, smart_id)
        tipo = entrada.get("tipo") if isinstance(entrada, dict) else None
        conta = cancelar.conta_do_smart(tipo, contas_mapa)
        # ⛔ A JANELA e por REMESSA, da data em que o robo a baixou. O job olha 45 dias
        # para tras e o padrao do robo e 7: em 21/09/2026, 18 das 21 remessas apontadas
        # ficavam FORA da janela, o POST nao alcancava a grade em que o id existe, e o
        # `sumiu_da_grade` — que lista a MESMA janela — confirmava que sumiu. Falso
        # sucesso em 18 de 21. `--de`/`--ate` explicitos mandam, para o caso manual.
        de, ate = cancelar.janela_da_remessa(entrada, de=args.de, ate=args.ate)
        excluir = dados.get("excluir_da_geracao") or []
        rotulo = f"id {smart_id} ({arquivo}, conta {conta}, grade {de}..{ate})"
        if not conta:
            falhos += 1
            log(f"  {rotulo}: SEM conta do Smart (tipo={tipo!r}) - pulando, nao adivinho conta")
            continue
        if excluir:
            docs = [e.get("documento") for e in excluir]
            # o corte e so do LOG: mostrar 5 e escrever "6" parece contradicao, entao diz.
            mostra = docs[:5] + (["..."] if len(docs) > 5 else [])
            log(f"  {rotulo}: ⚠️ {len(excluir)} titulo(s) NAO podem voltar a fila "
                f"(ja tem boleto no banco) — {mostra}")

        res = cancelar.cancelar_uma(ctx, smart_id, conta, de, ate, dry_run=dry)
        if res["ok"] is None:
            log(f"  {rotulo}: DRY_RUN — POST teria {len(res['corpo'])} bytes "
                f"| {dados.get('titulos_que_voltam', '?')} titulo(s) voltariam")
            continue
        if not res["ok"]:
            incertos += 1 if res.get("enviado") else 0
            falhos += 0 if res.get("enviado") else 1
            log(f"  {rotulo}: {res['motivo']}")
            continue

        sumiu, como = cancelar.sumiu_da_grade(ctx, smart_id, conta, de, ate, listar_remessas)
        if sumiu is True:
            feitos += 1
            log(f"  {rotulo}: CANCELADA ({como})")
            cancelar.registrar_feito(smart_id, arquivo)
        else:
            incertos += 1
            log(f"  {rotulo}: POST aceito mas {como} — CONFERIR no Smart")

    log(f"RESUMO CANCELAMENTO: {feitos} cancelada(s) | {incertos} incerta(s) | {falhos} falha(s)")
    if dry:
        log("(DRY_RUN: nada foi cancelado. Use --pra-valer quando quiser valer.)")
        return SAIU_OK
    return SAIU_RODADA_INCOMPLETA if (incertos or falhos) else SAIU_OK


def rodada_geracao(ctx, args, dry, execucao=None):
    """Percorre as contas alvo gerando e baixando. Retorna o exit code."""
    contas_mapa, carteiras_mapa = carregar_contas_carteiras()

    if args.todas_contas:
        prefixo = cfg.PREFIXO_CONTAS.lower()
        alvos = [(n, r) for n, r in contas_mapa.items()
                 if r.lower().startswith(prefixo)]
        alvos.sort(key=lambda x: x[1].lower())
        if not alvos:
            log(f"ERRO: contas_carteiras.json nao tem conta com prefixo "
                f"{cfg.PREFIXO_CONTAS!r}. Rode atualizar_contas.py.")
            return SAIU_CONTA_NAO_RESOLVIDA
    else:
        num, rot = resolver_conta(ctx, args.conta)
        if num is None:
            return SAIU_CONTA_NAO_RESOLVIDA
        alvos = [(num, rot)]

    log("=" * 66)
    log(f"GERACAO {'(DRY_RUN - nao envia nada)' if dry else '*** PRA VALER ***'}"
        f"  |  {len(alvos)} conta(s)  |  carteira {args.carteira}")
    log("=" * 66)

    resumo, abortou = [], False
    for num, rot in alvos:
        carts = carteiras_mapa.get(num) or []
        cart = args.carteira if (not carts or args.carteira in carts) else carts[0]
        if cart != args.carteira:
            log(f"  {rot}: carteira {args.carteira} nao existe nessa conta -> "
                f"usando {cart}")
        try:
            resumo.append(ciclo_conta(ctx, num, rot, cart, dry, args.forcar, execucao=execucao))
        except SessaoCaiu as e:
            log("!" * 66)
            log(f"ABORTANDO: {e}")
            log(f"Faltaram {len(alvos) - len(resumo)} conta(s). O controle evita "
                "rebaixar o que ja veio - basta rodar de novo.")
            log("!" * 66)
            abortou = True
            break
        except Exception as e:
            # Conta pulada por erro NAO e conta sem remessa: os titulos dela
            # podem estar esperando, e o POST pode ate ter sido processado.
            # `incerto` leva a rodada a sair != 0 para o hub alertar.
            log(f"  {rot}: ERRO no ciclo: {e}")
            resumo.append({"conta": num, "rotulo": rot, "titulos": 0,
                           "gerou": False, "ids": [], "baixados": 0,
                           "incerto": True, "motivo": f"erro: {e}"})

    log("=" * 66)
    com_titulo = [r for r in resumo if r["titulos"]]
    gerados = [r for r in resumo if r["gerou"]]
    baixados = sum(r["baixados"] for r in resumo)
    log(f"RESUMO: {len(alvos)} conta(s) | {len(com_titulo)} com titulo(s) | "
        f"{len(gerados)} gerada(s) | {baixados} arquivo(s) baixado(s)")
    for r in com_titulo:
        log(f"   {r['rotulo']:26} titulos={r['titulos']:<4} "
            f"ids={r['ids']} baixados={r['baixados']} {r['motivo']}"
            + (f" excluidos={r['excluidos']}" if r.get("excluidos") else "")
            + (f" retidos={len(r['retidos'])}" if r.get("retidos") else ""))
    falhas.exportar_controle(ler_controle(), log=log)
    # Retido fica na fila do Smart ate alguem prorrogar no ERP: tem de aparecer na
    # saida da task todo dia, inclusive quando a conta ficou sem nada para gerar.
    for r in resumo:
        for a in r.get("retidos") or []:
            log(f"RETIDO NA FILA: {r['rotulo']} {a['documento']} vence "
                f"{a['vencimento'][8:10]}/{a['vencimento'][5:7]}/{a['vencimento'][:4]} — "
                f"prorrogar no ERP (o MoneyPlus recusa com 16/92)")
    if dry:
        log("(DRY_RUN: nada foi gerado. Use --pra-valer quando quiser valer.)")
    else:
        log(f"arquivos em: {cfg.PASTA_REMESSAS}")

    # Conta gerada que NAO baixou e o caso que precisa de gente: os titulos ja
    # sairam da fila e o arquivo nao esta na pasta. Sai != 0 p/ o hub alertar.
    pendentes = [r for r in resumo if r["gerou"] and r["baixados"] == 0]
    incertas = [r for r in resumo if r.get("incerto")]
    if incertas:
        log(f"ATENCAO: {len(incertas)} conta(s) ficaram INCERTAS nesta rodada.")
    if abortou or pendentes or incertas:
        for r in pendentes:
            log(f"PENDENTE: {r['rotulo']} gerou ids={r['ids']} e nao baixou")
        for r in incertas:
            log(f"INCERTA: {r['rotulo']} - {r['motivo']}. PODE haver remessa "
                f"gerada no Smart sem arquivo aqui: conferir na tela de Download "
                f"de Remessa antes de rodar de novo.")
        return SAIU_RODADA_INCOMPLETA
    return SAIU_OK


# --------------------------------------------------------------------------- #
# subir para o Nextcloud o que ja esta no disco
# --------------------------------------------------------------------------- #
def subir_pendentes(limite=0):
    """Sobe para o Nextcloud os .REM que JA estao na pasta local.

    Nao abre navegador e nao fala com o Smart — le o disco e sobe. Serve para
    dois casos: o historico que ficou parado antes de este envio existir, e a
    segunda tentativa do que falhou numa rodada.

    Seguro de repetir: o caminho no Nextcloud e derivado do CONTEUDO (data de
    geracao e cedente saem do header do proprio arquivo), entao subir duas vezes
    sobrescreve o mesmo destino em vez de criar duplicata. O sufixo `_dup` que a
    pasta local usa para desempatar nome repetido NAO sobe (`nome_para_nuvem`).
    """
    if not nuvem.disponivel():
        log("ERRO: sem credencial do Nextcloud (/app/config/nextcloud.env).")
        return SAIU_RODADA_INCOMPLETA

    arquivos = sorted(f for f in os.listdir(cfg.PASTA_REMESSAS)
                      if f.upper().endswith(".REM"))
    if limite:
        log(f"LIMITE: {limite} de {len(arquivos)} arquivo(s) — o resto NAO sobe nesta rodada")
        arquivos = arquivos[:limite]
    log("=" * 66)
    log(f"SUBIR PENDENTES: {len(arquivos)} arquivo(s) de {cfg.PASTA_REMESSAS}")
    log(f"destino: {nuvem.DEST_BASE}/<ano>/<MM-Mes>/<dia>/<Banco>/")
    log("=" * 66)

    ok = falhou = 0
    for nome in arquivos:
        caminho_local = os.path.join(cfg.PASTA_REMESSAS, nome)
        try:
            with open(caminho_local, "rb") as f:
                dados = f.read()
        except OSError as e:
            falhou += 1
            log(f"  {nome}: nao li o arquivo ({e})")
            continue
        enviado, alvo, detalhe = nuvem.enviar(dados, nome_para_nuvem(nome))
        if enviado:
            ok += 1
            log(f"  OK   {nome} -> {alvo}")
        else:
            falhou += 1
            log(f"  FALHA {nome} ({detalhe}) -> {alvo}")

    log("=" * 66)
    log(f"RESUMO: {ok} enviado(s), {falhou} falha(s), de {len(arquivos)} arquivo(s)")
    return SAIU_OK if not falhou else SAIU_RODADA_INCOMPLETA


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def montar_parser():
    ap = argparse.ArgumentParser(
        description="Gera as remessas CNAB no Smart e baixa os .REM.")
    ap.add_argument("--conta", default=cfg.CONTA_PADRAO,
                    help=f"numero ou parte do nome da conta (padrao: {cfg.CONTA_PADRAO})")
    ap.add_argument("--dias", type=int, default=cfg.DIAS_PADRAO,
                    help=f"janela de busca em dias (padrao {cfg.DIAS_PADRAO})")
    ap.add_argument("--de", help="data inicial AAAA-MM-DD (sobrepoe --dias)")
    ap.add_argument("--ate", help="data final AAAA-MM-DD (sobrepoe --dias)")
    ap.add_argument("--listar", action="store_true",
                    help="so LISTA o que existe, sem baixar nada")
    ap.add_argument("--contas", action="store_true",
                    help="mostra as contas disponiveis e sai")
    ap.add_argument("--ids", nargs="+", type=int,
                    help="baixa ids especificos (ex.: --ids 25521 25522)")
    ap.add_argument("--resultado",
                    help="URL da tela 'Remessa gerada' ou so o param resultado (base64)")
    ap.add_argument("--da-tela", action="store_true",
                    help="pega os ids da tela 'Remessa gerada' aberta na sessao")
    ap.add_argument("--vigiar", action="store_true",
                    help="loop: fica olhando e baixa o que aparecer de novo")
    ap.add_argument("--intervalo", type=int, default=60,
                    help="segundos entre ciclos no modo --vigiar (padrao 60)")
    ap.add_argument("--forcar", action="store_true",
                    help="rebaixa mesmo se ja constar no controle")
    # --- cancelamento de remessa recusada pelo banco ---
    ap.add_argument("--cancelar", action="store_true",
                    help="CANCELA no Smart as remessas que o process-automation apontou "
                         "em cancelamentos.json. ⛔ So executa com --pra-valer.")
    ap.add_argument("--cancelamentos-json", default=None,
                    help="caminho da lista (padrao: o do bind compartilhado)")

    # --- geracao ---
    ap.add_argument("--gerar", action="store_true",
                    help="GERA a remessa (e baixa). Respeita DRY_RUN.")
    ap.add_argument("--todas-contas", action="store_true",
                    help=f"com --gerar: percorre todas as contas "
                         f"'{cfg.PREFIXO_CONTAS}*'")
    ap.add_argument("--carteira", default=cfg.CARTEIRA_PADRAO,
                    help=f"carteira usada na geracao (padrao {cfg.CARTEIRA_PADRAO})")
    ap.add_argument("--bb-api-convenio",
                    help="com --gerar: preserva a origem das remessas novas deste convenio BB")
    ap.add_argument("--bb-api-ambiente", choices=("producao", "homologacao"),
                    help="ambiente bancario de destino, obrigatorio com --bb-api-convenio")
    ap.add_argument("--bb-api-origem",
                    help="caixa de saida persistente; padrao PASTA_REMESSAS/bb_api")
    valer = ap.add_mutually_exclusive_group()
    valer.add_argument("--pra-valer", action="store_true",
                       help="desliga o DRY_RUN: GERA DE VERDADE no Smart")
    valer.add_argument("--simular", action="store_true",
                       help="forca o DRY_RUN mesmo com DRY_RUN_REM=false no ambiente "
                            "(no container o remessa_cobranca.env desliga o dry-run)")
    # --- nextcloud ---
    ap.add_argument("--subir-pendentes", action="store_true",
                    help="sobe para o Nextcloud os .REM que JA estao na pasta "
                         "local. Nao abre navegador e nao toca no Smart.")
    ap.add_argument("--limite", type=int, default=0,
                    help="com --subir-pendentes: sobe no maximo N arquivos "
                         "(0 = todos)")
    # --- sessao ---
    ap.add_argument("--cdp", action="store_true",
                    help="usa um Chrome JA ABERTO (dev/VNC) em vez de subir o proprio")
    ap.add_argument("--espera-manual", type=int, default=0,
                    help="segundos esperando login manual no VNC se o auto-login "
                         "falhar (0 = nao espera; use so em operacao assistida)")
    return ap


def executar(ctx, args, execucao=None):
    """O que fazer com um contexto ja logado. Retorna o exit code."""
    log(f"pasta de destino: {cfg.PASTA_REMESSAS}")
    log(f"controle        : {cfg.ARQ_CONTROLE}")

    if args.bb_api_convenio or args.bb_api_ambiente or args.bb_api_origem:
        import bb_geracao

        if (not args.gerar or not args.bb_api_convenio or not args.bb_api_ambiente
                or args.todas_contas or args.forcar or args.ids or args.resultado
                or args.da_tela or args.vigiar or args.listar or args.contas
                or args.subir_pendentes or args.de or args.ate):
            log("ERRO: BB API exige --gerar, convenio, ambiente e conta/carteira exatas; "
                "nao combina com listagem, historico, datas ou --forcar")
            return SAIU_RODADA_INCOMPLETA
        try:
            resultado = bb_geracao.executar(
                sys.modules[__name__], ctx, conta=args.conta, carteira=args.carteira,
                convenio=args.bb_api_convenio, ambiente=args.bb_api_ambiente,
                pasta=args.bb_api_origem or os.path.join(cfg.PASTA_REMESSAS, "bb_api"),
                dry_run=not args.pra_valer)
        except (bb_geracao.OrigemBBInconclusiva, OSError, ValueError) as exc:
            log(f"BB API pendente: {exc}")
            return SAIU_RODADA_INCOMPLETA
        log(f"BB API origem: {json.dumps(resultado, ensure_ascii=False)}")
        return SAIU_OK

    if args.contas:
        contas = listar_contas(ctx)
        log(f"{len(contas)} contas disponiveis:")
        for num, rotulo in sorted(contas.items(), key=lambda x: x[1].lower()):
            print(f"    {num:>5}  {rotulo}")
        return SAIU_OK

    if args.cancelar:
        # ⛔ O cancelamento NAO herda o DRY_RUN do ambiente, e essa e a unica acao
        # deste robo que nao herda. No container o `remessa_cobranca.env` poe
        # DRY_RUN_REM=false — e com isso `--gerar` sem flag GERA DE VERDADE (medido
        # em 08/09/2026, comentario logo abaixo). Gerar de novo e recuperavel:
        # a remessa sai e alguem a cancela. Cancelar NAO e: os titulos voltam a
        # fila e o sequencial daquela remessa morre. Por isso aqui a regra e
        # invertida — so executa com --pra-valer EXPLICITO.
        return rodada_cancelamento(ctx, args, dry=not args.pra_valer, execucao=execucao)

    if args.gerar:
        # --pra-valer manda; --simular forca a simulacao; sem os dois vale o
        # DRY_RUN_REM do ambiente. ATENCAO: no container o remessa_cobranca.env poe
        # DRY_RUN_REM=false (e o que a rodada agendada usa), entao `--gerar` SEM
        # flag nenhuma GERA DE VERDADE ali — medido em 08/09/2026.
        return rodada_geracao(ctx, args,
                              dry=(cfg.DRY_RUN or args.simular) and not args.pra_valer,
                              execucao=execucao)

    if args.ids:
        log(f"ids informados: {args.ids}")
        processar(ctx, [{"id": i, "rotulo": "id manual"} for i in args.ids], args.forcar,
                  execucao=execucao)
        return SAIU_OK

    if args.resultado:
        dados = _b64_para_dict(args.resultado)
        if not dados:
            log("ERRO: nao consegui ler o --resultado.")
            return SAIU_RESULTADO_ILEGIVEL
        itens = [{"id": int(i), "rotulo": TIPOS.get(str(t), f"tipo {t}")}
                 for t, i in (dados.get("idsSucesso") or {}).items()]
        log(f"resultado decodificado: {[(i['id'], i['rotulo']) for i in itens]}")
        processar(ctx, itens, args.forcar, execucao=execucao)
        return SAIU_OK

    if args.da_tela:
        pares, _url = descobrir_na_tela(ctx)
        if not pares:
            log("Nenhuma tela 'Remessa gerada' aberta na sessao.")
            return SAIU_SEM_TELA
        itens = [{"id": fid, "rotulo": TIPOS.get(tipo, f"tipo {tipo}")}
                 for tipo, fid in pares]
        log(f"achei na tela: {[(i['id'], i['rotulo']) for i in itens]}")
        processar(ctx, itens, args.forcar, execucao=execucao)
        return SAIU_OK

    # PADRAO: lista pela tela de Download de Remessa (conta + periodo)
    conta, rotulo_conta = resolver_conta(ctx, args.conta)
    if conta is None:
        return SAIU_CONTA_NAO_RESOLVIDA
    de, ate = janela(args)

    def um_ciclo():
        achadas = listar_remessas(ctx, conta, de, ate)
        if not achadas:
            log(f"nenhuma remessa em {rotulo_conta} entre {de} e {ate}.")
            return 0
        controle = ler_controle()
        novas = [a for a in achadas if str(a["id"]) not in controle]
        log(f"{len(achadas)} remessa(s) em {rotulo_conta} ({de} a {ate}) "
            f"- {len(novas)} nova(s)")
        for a in achadas:
            marca = "novo" if str(a["id"]) not in controle else "ja tenho"
            print(f"    [{marca:8}] id={a['id']:<7} {a['arquivo']:20} "
                  f"{a['data']:17} {a['tamanho']}")
        if args.listar:
            return 0
        alvo = achadas if args.forcar else novas
        if not alvo:
            return 0
        return processar(ctx, [{"id": a["id"],
                                "rotulo": f"{a['conta']} {a['data']}".strip()}
                               for a in alvo], args.forcar, execucao=execucao)

    if not args.vigiar:
        um_ciclo()
        return SAIU_OK

    log(f"modo VIGIAR: conferindo a cada {args.intervalo}s. Ctrl+C para parar.")
    while True:
        try:
            um_ciclo()
            time.sleep(args.intervalo)
        except KeyboardInterrupt:
            log("encerrado pelo usuario.")
            return SAIU_OK
        except Exception as e:
            log(f"aviso no ciclo: {e}")
            time.sleep(args.intervalo)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = montar_parser().parse_args()

    # Este modo le o DISCO: nao precisa de Smart nem de Chrome. Sai antes de
    # gastar um login (e a janela de horario do usuario no Smart).
    if args.subir_pendentes and not (args.bb_api_convenio or args.bb_api_ambiente
                                   or args.bb_api_origem):
        return subir_pendentes(args.limite)

    # A execucao no banco: em DRY pode faltar (degrada e avisa); PRA VALER e obrigatoria —
    # gerar ou cancelar remessa mexe na cobranca do sacado, entao sem registro nao se age.
    _dry = (cfg.DRY_RUN or args.simular) and not args.pra_valer
    try:
        execucao = execucao_job.abrir_execucao(
            "remessa_cobranca",
            # o nome tem de casar com a TASK que roda, senao a execucao no banco
            # aponta para o job errado: run_bb.sh e `gerar_remessa_bb`, nao o CNAB-400
            "cancelar_remessa_recusada_cnab_400" if args.cancelar
            else ("gerar_remessa_bb" if args.bb_api_convenio
                  else "gerar_remessa_cobranca_cnab_400"),
            flag_ensaio=_dry, obrigatoria=not _dry,
            apelido_credencial=os.environ.get("REMESSA_SENHA"),
            detalhe={"conta": args.conta, "todas_contas": bool(args.todas_contas),
                     "cancelar": bool(args.cancelar), "ids": args.ids or None,
                     "bb_api_convenio": args.bb_api_convenio})
    except execucao_job.ExecucaoIndisponivel as e:
        log(f"ERRO: {e}")
        return SAIU_SEM_SESSAO

    codigo = SAIU_SEM_NAVEGADOR
    try:
        codigo = _com_sessao(args, execucao)
    finally:
        execucao_job.fechar_execucao(
            execucao, "sucesso" if codigo == SAIU_OK else "falha",
            codigo_saida=codigo, log=log)
    return codigo


def _com_sessao(args, execucao):
    """O corpo que precisa do Chrome logado. Separado do main() so para o
    fecha-execucao ficar num finally unico, sem aninhar mais um try."""
    with sync_playwright() as p:
        try:
            with _sessao.sessao(p, usar_cdp=args.cdp,
                                espera_manual=args.espera_manual, log=log) as ctx:
                log("sessao do Smart OK (logada).")
                return executar(ctx, args, execucao=execucao)
        except _sessao.SemSessao as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_SESSAO
        except _sessao.SemNavegador as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_NAVEGADOR


if __name__ == "__main__":
    sys.exit(main())
