# -*- coding: utf-8 -*-
"""Job diário do doc2you: loga 1x, baixa os documentos assinados de um dia e sobe
pro Nextcloud. Self-contained: abre o Chrome (isolado no :98), faz auto-login via
CapSolver, faz o SSO da ponte Doc2You (wvw), lista os docs CONCLUÍDOS do dia, baixa
cada um, classifica/nomeia e sobe DIRETO via WebDAV — depois FECHA. Sem keepalive.

Regra: só roda em DIA ÚTIL. Por padrão baixa o documento-alvo = 2 dias úteis pra trás
(o dia útil anterior ao último dia útil), dando tempo dos docs ficarem assinados.

Uso:
  docker exec -e DISPLAY=:98 -w /app erp-automation python -m src.processors.web.doc2you.baixar_dia
  ... --data 2026-06-19        # data específica (ignora a guarda de dia útil)
  ... --estrutura operacao|tipo|data
  ... --limite 5               # baixa só N (teste)
  ... --force                  # roda mesmo se hoje não for dia útil
"""
import argparse
import asyncio
import json
import os
import re
from datetime import date, timedelta

from playwright.async_api import async_playwright

from src.processors.web.doc2you import classificar as C
from src.processors.web.doc2you import download as D
from src.processors.web.doc2you import dias_uteis
from src.processors.web.doc2you import _login as L
from src.processors.web.doc2you import _nextcloud as NC

PERFIL = os.getenv("DOC2YOU_PERFIL", "/app/data/doc2you/perfil_chrome")
BRIDGE = os.getenv("DOC2YOU_URL", "https://wvw.smartsecurities.com.br/smart/doc2you.php")
ESTRUTURA = os.getenv("DOC2YOU_ESTRUTURA", "operacao")  # operacao | tipo | data
MIN_PDF_BYTES = 1024


def _credenciais():
    login, senha = os.getenv("DOC2YOU_LOGIN"), os.getenv("DOC2YOU_SENHA")
    if login and senha:
        return login, senha
    try:
        from src.common.core.config_loader import get_config_loader
        c = get_config_loader().get_credentials("baixar_documentos_doc2you")
        if c:
            return c.usuario, c.senha
    except Exception:
        pass
    return login, senha


def _parse_data(s: str) -> str:
    s = (s or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    raise ValueError(f"data inválida: {s!r}")


def _subpasta(d: dict, estrutura: str, data_iso: str) -> str:
    """Caminho relativo (dentro de DOCUMENTOS ASSINADOS) onde o PDF vai."""
    pt = C.PASTA_TIPO.get(d["tipo"], "Outros")
    if estrutura == "tipo":
        return pt
    if estrutura == "data":
        return f"{data_iso}/{pt}"
    op = (d.get("operacao") or "sem_operacao").strip() or "sem_operacao"
    return op  # "operacao" (padrão): todos os docs da operação juntos


async def _sso(ctx) -> bool:
    page = await ctx.new_page()
    try:
        try:
            await page.goto(BRIDGE, wait_until="domcontentloaded", timeout=40000)
        except Exception:
            pass
        await asyncio.sleep(3)
        return await D.sessao_valida(ctx)
    finally:
        await page.close()


def _conn_pg():
    """Conexão psycopg2 direta (sslmode=disable): o módulo SQLAlchemy do
    erp-automation exige SSL, que o postgres LOCAL não suporta."""
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432") or 5432),
        dbname=os.getenv("DB_NAME", "prosperedb"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
        sslmode="disable", connect_timeout=10)


def _gravar_execucao(data_iso: str, res: dict, sucesso: bool):
    """Grava o resumo do run em erp_automation.doc2you_execucao — os jobs de saúde e de
    verificação leem daqui. Falha aqui NÃO derruba o run (docs já estão salvos)."""
    try:
        conn = _conn_pg()
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO erp_automation.doc2you_execucao "
                "(data_alvo, listados, enviados, erros, sucesso, operacoes) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
                (data_iso, res.get("listados", 0), res.get("enviados", 0),
                 res.get("erros", 0), sucesso, json.dumps(sorted(res.get("operacoes", [])))))
        conn.close()
        print(f"[doc2you] run gravado em erp_automation.doc2you_execucao (sucesso={sucesso})", flush=True)
    except Exception as exc:
        print(f"[doc2you] aviso: falha ao gravar execucao: {exc}", flush=True)


# Quantos dias pra trás a re-listagem do retry varre (por operação, via numOperacao).
# Precisa cobrir a VIDA da operação, não só desde que ela entrou no backlog.
_RETRY_JANELA_DIAS = int(os.getenv("DOC2YOU_RETRY_JANELA_DIAS", "730") or 730)

# Janela (dias) da fase de NF: pega as operações com data_operacao >= hoje - N.
# N=1 => hoje + ontem (cobre operação formalizada tarde que só entrou no DWH depois).
_NF_JANELA_DIAS = int(os.getenv("DOC2YOU_NF_JANELA_DIAS", "1") or 1)

# Janela (dias) da fase de XML: notas de operação FINALIZADA entre hoje-N e hoje.
_XML_JANELA_DIAS = int(os.getenv("DOC2YOU_XML_JANELA_DIAS", "1") or 1)

# mapa: código de falta da verificação (process-automation) -> tipo do robô
_FALTA_TIPO = {
    "aditivo": "aditivo",
    "np": "nota_promissoria",
    "duplicata": "duplicata",
    "letra": "letra_cambio",
}


def _ler_pendencias() -> list:
    """Lê o backlog em aberto gravado pela verificação (operacional.doc2you_pendencia).

    Devolve [{operacao, data_alvo (date), faltas (dict)}] das operações ainda
    pendentes e dentro da janela DOC2YOU_RETRY_MAX_DIAS (dias). Best-effort:
    qualquer falha devolve [] (o run normal não é afetado)."""
    if os.getenv("DOC2YOU_RETRY_PENDENCIAS", "1") in ("0", "false", "False"):
        return []
    max_dias = int(os.getenv("DOC2YOU_RETRY_MAX_DIAS", "20") or 20)
    try:
        import psycopg2.extras
        conn = _conn_pg()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT operacao, data_alvo, faltas FROM operacional.doc2you_pendencia "
                "WHERE status = 'aberto' AND data_alvo >= (CURRENT_DATE - %s::int) "
                "ORDER BY data_alvo ASC",
                (max_dias,))
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        print(f"[doc2you] aviso: falha ao ler pendências: {exc}", flush=True)
        return []


def _operacoes_do_dia() -> list:
    """Operações do dia (DWH `bi.operacional_operacao_desagio`, `data_operacao` na
    janela `_NF_JANELA_DIAS`). Fonte AUTORITATIVA — independe de doc assinado no
    Doc2You (a NF existe desde a criação da operação). Best-effort: falha → []."""
    try:
        conn = _conn_pg()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT operacao_desagio_nk FROM bi.operacional_operacao_desagio "
                "WHERE data_operacao >= (CURRENT_DATE - %s::int) "
                "  AND operacao_desagio_nk ~ '^[0-9]+$' "
                "ORDER BY 1",
                (_NF_JANELA_DIAS,))
            ops = [r[0] for r in cur.fetchall()]
        conn.close()
        return ops
    except Exception as exc:
        print(f"[doc2you] aviso: falha ao ler operações do dia (DWH): {exc}", flush=True)
        return []


async def _processar_docs(ctx, docs: list, estrutura: str, data_iso: str, res: dict,
                          operacoes: set, usados: set, limite: int = 0,
                          dl_ini: str = None, dl_fim: str = None, err_key: str = "erros"):
    """Baixa, nomeia e sobe cada doc pro Nextcloud. Reusado pela fase normal e pelo
    retry. `usados` dedup nomes ENTRE as fases (nunca sobrescrever/perder doc).
    `err_key` separa erros do retry dos erros da fase normal (que decidem `sucesso`)."""
    alvo = docs[:limite] if limite else docs
    for i, d in enumerate(alvo, 1):
        try:
            pdf = await D.baixar_documento(ctx, d["chk"], dl_ini or data_iso, dl_fim or data_iso)
            if not pdf or len(pdf) < MIN_PDF_BYTES:
                res[err_key] += 1
                continue
            cnpj = D.resolver_cnpj(d, pdf)
            nome = C.nome_final(d["tipo"], d.get("operacao", ""), d.get("nota", ""), cnpj)
            sub = _subpasta(d, estrutura, data_iso)
            # colisão de nome (ex.: 2 cartas pro mesmo sacado, ou CNPJ vazio)?
            # desambigua com o id único do documento (chk), sem perder nenhum.
            if f"{sub}/{nome}" in usados:
                nome = f"{nome}_{d['chk']}"
            usados.add(f"{sub}/{nome}")
            status = NC.enviar(pdf, sub, f"{nome}.pdf")
            if status in (201, 204):
                res["enviados"] += 1
                op = str(d.get("operacao") or "sem_operacao").strip() or "sem_operacao"
                operacoes.add(op)
                if i <= 10 or limite:
                    print(f"  [{i}/{len(alvo)}] OK {sub}/{nome}.pdf ({len(pdf)}B)", flush=True)
            else:
                res[err_key] += 1
                print(f"  [{i}/{len(alvo)}] upload HTTP {status}: {sub}/{nome}.pdf", flush=True)
        except Exception as e:
            res[err_key] += 1
            print(f"  [{i}/{len(alvo)}] op{d.get('operacao')}: ERRO {type(e).__name__}: {e}", flush=True)


async def _retry_pendencias(ctx, estrutura: str, res: dict, operacoes: set, usados: set):
    """Re-baixa SÓ os docs que faltam de cada operação ainda pendente no backlog.
    Para cada pendência, re-lista a operação (numOperacao) na janela data_alvo..hoje
    com status C e baixa apenas os tipos faltantes (cartas: todas, overwrite idempotente)."""
    pend = _ler_pendencias()
    if not pend:
        print("[doc2you] retry: nenhuma pendência aberta no backlog.", flush=True)
        return
    hoje = date.today().isoformat()
    print(f"[doc2you] retry: {len(pend)} operação(ões) pendente(s) no backlog.", flush=True)
    for p in pend:
        op = str(p["operacao"])
        data_alvo = p.get("data_alvo")
        faltas = p.get("faltas") or {}
        tipos_falta = {_FALTA_TIPO[t] for t in (faltas.get("tipos") or []) if t in _FALTA_TIPO}
        quer_carta = bool(faltas.get("cartas"))
        if not tipos_falta and not quer_carta:
            continue
        # Janela de re-listagem: NÃO pode começar no data_alvo. Uma operação ANTIGA que
        # voltou pro backlog (ex.: 61200, criada em 27/05, cartas assinadas em 14/07) tem
        # os documentos originais (Aditivo/NP/Duplicata) datados MUITO ANTES do data_alvo
        # — com janela curta a listagem não acha nada e a pendência trava pra sempre.
        # Como o filtro numOperacao já restringe à operação, alargar é barato e seguro.
        _ini = min(data_alvo, date.today() - timedelta(days=_RETRY_JANELA_DIAS)) \
            if hasattr(data_alvo, "isoformat") else date.today() - timedelta(days=_RETRY_JANELA_DIAS)
        di = _ini.isoformat()
        try:
            docs = await D.listar_documentos(ctx, di, hoje, status_doc="C",
                                             max_paginas=50, num_operacao=op)
        except Exception as e:
            res["erros_retry"] += 1
            print(f"  [retry op{op}] listar ERRO {type(e).__name__}: {e}", flush=True)
            continue
        # guarda client-side: só docs DESTA op e dos tipos que faltam (caso o
        # filtro numOperacao seja ignorado pelo backend).
        sel = [d for d in docs
               if str(d.get("operacao") or "").strip() == op
               and (d["tipo"] in tipos_falta or (quer_carta and d["tipo"] == "carta_cessao"))]
        if not sel:
            print(f"  [retry op{op}] nada novo assinado ainda.", flush=True)
            continue
        print(f"  [retry op{op}] {len(sel)} doc(s) a recuperar (janela {di}..{hoje}).", flush=True)
        await _processar_docs(ctx, sel, estrutura, di, res, operacoes, usados,
                              dl_ini=di, dl_fim=hoje, err_key="erros_retry")


async def _abrir_sessao(p):
    """Lança o contexto persistente (:98), loga no Smart (3× retry — CapSolver às
    vezes falha) e valida o SSO Doc2You. Devolve o BrowserContext logado; o chamador
    é responsável por fechá-lo. Compartilhado pelo run normal e pelo teste de anexos."""
    usuario, senha = _credenciais()
    if not (usuario and senha):
        raise RuntimeError("sem credencial Smart (credentials.csv / DOC2YOU_LOGIN).")
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=PERFIL, headless=False, channel="chrome",
        args=["--no-sandbox", "--disable-dev-shm-usage", "--start-maximized"],
        no_viewport=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    print("[doc2you] login...", flush=True)
    logado = False
    for tent in range(1, 4):
        try:
            if await L.login(ctx, page, usuario, senha):
                logado = True
                break
        except Exception as e:
            print(f"[doc2you] login tentativa {tent}/3 erro: {type(e).__name__}: {e}", flush=True)
        if tent < 3:
            print(f"[doc2you] login tentativa {tent}/3 falhou — nova tentativa em 8s", flush=True)
            await asyncio.sleep(8)
    if not logado:
        await ctx.close()
        raise RuntimeError("auto-login falhou após 3 tentativas (CapSolver/Smart).")
    print("[doc2you] logado. SSO Doc2You...", flush=True)
    if not await _sso(ctx):
        await ctx.close()
        raise RuntimeError("Doc2You não acessível com essa conta.")
    return ctx


def _uploader_lastro():
    """Uploader Nextcloud com base LASTRO DAS OPERACOES — serve os anexos
    ('documentos complementares operacoes/<op>') e as NFs ('nf operacao'). Reusa o
    cliente compartilhado (mesmo do robô de crédito)."""
    from src.common.clients.nextcloud_webdav import NextcloudWebDAV
    return NextcloudWebDAV(
        dest_base=os.getenv("DOC2YOU_COMPL_NC_DEST", "CADASTRO/LASTRO DAS OPERACOES"),
        cred_env=os.getenv("DOC2YOU_NC_ENV", "/app/config/nextcloud.env"))


async def _baixar_complementares(ctx, ops: list, res: dict):
    """Para cada operação do dia, baixa os anexos (aba Outros documentos) que ainda
    NÃO estão no Nextcloud (skip-existing). Best-effort: nunca derruba o run.

    `ops` = operações do dia do DWH (`_operacoes_do_dia`), a MESMA fonte das NFs — não
    o conjunto de ops com doc assinado. Anexo existe desde a criação da operação, então
    varrer o dia inteiro garante que nenhum anexo passe despercebido."""
    from src.processors.web.doc2you import _complementares as CO
    up = _uploader_lastro()
    if not up.disponivel():
        print("[doc2you] complementares: sem credencial Nextcloud — pulando.", flush=True)
        return
    if not ops:
        return
    print(f"[doc2you] complementares: varrendo {len(ops)} operação(ões) do dia...", flush=True)
    novos = pulados = erros = 0
    for op in ops:
        n, pl, e = await CO.baixar_op(ctx, op, up)
        novos += n
        pulados += pl
        erros += e
    res["compl_novos"] = novos
    print(f"[doc2you] complementares FIM: {novos} novo(s), {pulados} já existia(m), "
          f"{erros} erro(s)", flush=True)


async def _baixar_nfs(ctx, ops: list, res: dict):
    """Rede de segurança: baixa a NF (DANFEs) de TODA operação do dia — `ops` vem do
    DWH (`_operacoes_do_dia`), não do que foi assinado no Doc2You — pra nenhuma NF passar
    despercebida. Skip-existing (pasta `nf operacao/` é flat → lista 1× e compara).
    Best-effort: nunca derruba o run."""
    from src.processors.web.doc2you import _nfs as NFS
    up = _uploader_lastro()
    if not up.disponivel():
        print("[doc2you] nfs: sem credencial Nextcloud — pulando.", flush=True)
        return
    if not ops:
        print("[doc2you] nfs: nenhuma operação do dia no DWH — pulando.", flush=True)
        return
    existentes = up.listar_nomes(NFS.NC_SUBPASTA)  # 1 PROPFIND na pasta flat
    print(f"[doc2you] nfs: {len(ops)} operação(ões) do dia (janela {_NF_JANELA_DIAS}d)...", flush=True)
    novos = pulados = sem_nf = erros = 0
    for op in ops:
        n, pl, sn, e = await NFS.baixar_op(ctx, op, up, existentes)
        novos += n
        pulados += pl
        sem_nf += sn
        erros += e
    res["nf_novos"] = novos
    print(f"[doc2you] nfs FIM: {novos} novo(s), {pulados} já existia(m), "
          f"{sem_nf} sem-NF, {erros} erro(s)", flush=True)


async def _baixar_xmls(ctx, res: dict):
    """Rede de segurança fiscal: baixa os XMLs das notas de operação FINALIZADA na
    janela (Financeiro → Monitoramento de Notas do Smart) → LASTRO DAS OPERACOES/
    xml operacao/nota<n>_op<op>.xml. 1 lote por dia (não itera operação). Skip-existing.
    Best-effort: nunca derruba o run."""
    from src.processors.web.doc2you import _xml_notas as XML
    up = _uploader_lastro()
    if not up.disponivel():
        print("[doc2you] xml: sem credencial Nextcloud — pulando.", flush=True)
        return
    hoje = date.today()
    ini = (hoje - timedelta(days=_XML_JANELA_DIAS)).isoformat()
    fim = hoje.isoformat()
    print(f"[doc2you] xml: notas de op finalizada {ini}..{fim}", flush=True)
    try:
        novos, pulados, erros = await XML.baixar_periodo(ctx, ini, fim, up)
    except Exception as e:
        print(f"[doc2you] xml: falha ({type(e).__name__}: {e}) — não derruba o run.", flush=True)
        return
    res["xml_novos"] = novos
    print(f"[doc2you] xml FIM: {novos} novo(s), {pulados} já existia(m), {erros} erro(s)", flush=True)


async def executar(data_iso: str, estrutura: str, limite: int = 0, retry: bool = False,
                   complementares: bool = False, nfs: bool = False, xmls: bool = False) -> dict:
    res = {"data": data_iso, "estrutura": estrutura, "listados": 0, "enviados": 0,
           "erros": 0, "erros_retry": 0, "compl_novos": 0, "nf_novos": 0, "xml_novos": 0}
    operacoes = set()  # operações processadas (entram no registro do run)
    async with async_playwright() as p:
        ctx = await _abrir_sessao(p)
        try:
            docs = await D.listar_documentos(ctx, data_iso, data_iso, status_doc="C", max_paginas=200)
            res["listados"] = len(docs)
            alvo_n = len(docs[:limite] if limite else docs)
            print(f"[doc2you] {len(docs)} doc(s) em {data_iso} | baixando {alvo_n} | estrutura={estrutura}", flush=True)

            usados = set()  # dedup de nome entre as fases — nunca sobrescrever/perder doc
            await _processar_docs(ctx, docs, estrutura, data_iso, res, operacoes, usados, limite=limite)

            # Fase de retry: re-baixa docs assinados tardiamente (backlog da verificação).
            if retry:
                await _retry_pendencias(ctx, estrutura, res, operacoes, usados)

            # Operações do dia (DWH): fonte ÚNICA de anexos E NFs — computada 1×, para
            # nenhum lastro passar despercebido (independe de doc assinado no Doc2You).
            ops_dia = _operacoes_do_dia() if (complementares or nfs) else []

            # Fase de complementares (só no run antecipado): anexos da operação (aba
            # Outros documentos do Smart) → LASTRO DAS OPERACOES/documentos complementares.
            if complementares:
                await _baixar_complementares(ctx, ops_dia, res)

            # Fase de NF (só no run antecipado): rede de segurança — NF de TODA operação
            # do dia → LASTRO DAS OPERACOES/nf operacao/NFE<op>.pdf.
            if nfs:
                await _baixar_nfs(ctx, ops_dia, res)

            # Fase de XML (só no run antecipado): XMLs das notas operadas no dia
            # (Smart Financeiro) → LASTRO DAS OPERACOES/xml operacao/nota<n>_op<op>.xml.
            if xmls:
                await _baixar_xmls(ctx, res)
        finally:
            await ctx.close()
    res["operacoes"] = sorted(operacoes)
    return res


async def _testar_complementares(op: str) -> None:
    """DEBUG/verificação: loga no Smart e lista + baixa os anexos de UMA operação."""
    from src.processors.web.doc2you import _complementares as CO
    up = _uploader_lastro()
    if not up.disponivel():
        raise SystemExit("sem credencial Nextcloud (config/nextcloud.env).")
    async with async_playwright() as p:
        ctx = await _abrir_sessao(p)
        try:
            docs = await CO.listar(ctx, str(op))
            print(f"[teste-compl] op {op}: {len(docs)} anexo(s) no Smart:", flush=True)
            for d in docs:
                print(f"   idDoc {d['idDoc']} | {d.get('data', ''):<18} | {d['nome']}", flush=True)
            n, pl, e = await CO.baixar_op(ctx, str(op), up)
            print(f"[teste-compl] resultado: {n} novo(s) subido(s), {pl} já existia(m), "
                  f"{e} erro(s)", flush=True)
        finally:
            await ctx.close()


async def _testar_nf(op: str) -> None:
    """DEBUG/verificação: loga no Smart e baixa a NF de UMA operação."""
    from src.processors.web.doc2you import _nfs as NFS
    up = _uploader_lastro()
    if not up.disponivel():
        raise SystemExit("sem credencial Nextcloud (config/nextcloud.env).")
    async with async_playwright() as p:
        ctx = await _abrir_sessao(p)
        try:
            existentes = up.listar_nomes(NFS.NC_SUBPASTA)
            n, pl, sn, e = await NFS.baixar_op(ctx, str(op), up, existentes)
            print(f"[teste-nf] op {op}: novo={n} pulado(já existia)={pl} sem_nf={sn} erro={e}", flush=True)
        finally:
            await ctx.close()


async def _testar_xml(data: str) -> None:
    """DEBUG/verificação: lista e baixa os XMLs das notas de op finalizada num dia."""
    from src.processors.web.doc2you import _xml_notas as XML
    up = _uploader_lastro()
    if not up.disponivel():
        raise SystemExit("sem credencial Nextcloud (config/nextcloud.env).")
    async with async_playwright() as p:
        ctx = await _abrir_sessao(p)
        try:
            notas = await XML.listar_notas(ctx, data, data)
            print(f"[teste-xml] {data}: {len(notas)} nota(s) no Smart", flush=True)
            n, pl, e = await XML.baixar_periodo(ctx, data, data, up)
            print(f"[teste-xml] resultado: {n} novo(s), {pl} já existia(m), {e} erro(s)", flush=True)
        finally:
            await ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="YYYY-MM-DD ou DD/MM/YYYY (padrão: 2 dias úteis atrás)")
    ap.add_argument("--estrutura", default=ESTRUTURA, choices=["operacao", "tipo", "data"])
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="roda mesmo se hoje não for dia útil")
    ap.add_argument("--no-retry", action="store_true",
                    help="não re-baixa as pendências do backlog (só a data-alvo)")
    ap.add_argument("--antecipado", action="store_true",
                    help="passada da NOITE: baixa os docs JÁ ASSINADOS de HOJE "
                         "(Duplicata/NP/Carta; Aditivo normalmente ainda não) + os "
                         "anexos das operações do dia. Não faz retry e NÃO grava execucao.")
    ap.add_argument("--complementares-op", default=None,
                    help="DEBUG: loga no Smart e baixa só os anexos (Outros documentos) "
                         "desta operação, depois sai. Para validar/testar.")
    ap.add_argument("--nf-op", default=None,
                    help="DEBUG: loga no Smart e baixa só a NF desta operação, depois sai.")
    ap.add_argument("--xml-dia", default=None,
                    help="DEBUG: lista e baixa os XMLs das notas de op finalizada nesse dia "
                         "(YYYY-MM-DD), depois sai.")
    args = ap.parse_args()

    if not NC.disponivel():
        raise SystemExit("sem credencial Nextcloud (config/nextcloud.env).")

    # Testes pontuais (não baixam docs do Doc2You).
    if args.complementares_op:
        asyncio.run(_testar_complementares(args.complementares_op))
        return
    if args.nf_op:
        asyncio.run(_testar_nf(args.nf_op))
        return
    if args.xml_dia:
        asyncio.run(_testar_xml(_parse_data(args.xml_dia)))
        return

    # Passada antecipada (ex.: 19:00): pega o que já está assinado no dia — a Carta de
    # Cessão sai a tempo da notificação do dia seguinte — E os anexos das operações do dia.
    # Não grava erp_automation.doc2you_execucao: saúde/verificação leem o run das 07:30 e não devem
    # verificar op do dia (sem Aditivo).
    if args.antecipado:
        # Mesma guarda do run canônico: em feriado/fim de semana não há operação, então
        # não adianta subir o browser e gastar login (e ainda gerar alerta de falha à toa).
        # Com isso, "0 doc(s)" num dia útil passa a ser sinal legítimo de problema.
        if not args.force and not dias_uteis.eh_dia_util(date.today()):
            print("[doc2you] hoje não é dia útil — antecipado não roda.", flush=True)
            return
        data_iso = date.today().isoformat()
        print(f"[doc2you] ANTECIPADO {data_iso}: docs assinados do dia + anexos + NFs + XMLs.", flush=True)
        try:
            res = asyncio.run(executar(data_iso, args.estrutura, args.limite,
                                       retry=False, complementares=True, nfs=True, xmls=True))
        except Exception as e:
            print(f"[doc2you] ANTECIPADO FALHOU {data_iso}: {type(e).__name__}: {e}", flush=True)
            raise
        print(f"[doc2you] FIM ANTECIPADO {data_iso}: "
              f"listados={res['listados']} enviados={res['enviados']} erros={res['erros']} "
              f"complementares_novos={res.get('compl_novos', 0)} nf_novos={res.get('nf_novos', 0)} "
              f"xml_novos={res.get('xml_novos', 0)}", flush=True)
        return

    if args.data:
        data_iso = _parse_data(args.data)
    else:
        if not args.force and not dias_uteis.eh_dia_util(date.today()):
            print("[doc2you] hoje não é dia útil — nada a fazer.", flush=True)
            return
        data_iso = dias_uteis.dia_alvo_download().isoformat()

    # Retry só no fluxo diário (sem --data/--limite) e se não desativado.
    retry = not (args.no_retry or args.data or args.limite)

    try:
        res = asyncio.run(executar(data_iso, args.estrutura, args.limite, retry=retry))
    except Exception as e:
        _gravar_execucao(data_iso, {"listados": 0, "enviados": 0, "erros": 1, "operacoes": []}, sucesso=False)
        print(f"[doc2you] FALHOU {data_iso}: {type(e).__name__}: {e}", flush=True)
        raise
    # `sucesso` reflete só a fase normal — erros do retry (best-effort) não a derrubam.
    _gravar_execucao(data_iso, res, sucesso=(res["erros"] == 0))
    print(f"\n[doc2you] FIM {res['data']} (estrutura={res['estrutura']}): "
          f"listados={res['listados']} enviados={res['enviados']} erros={res['erros']} "
          f"retry(enviados+/erros={res.get('erros_retry', 0)})", flush=True)


if __name__ == "__main__":
    main()
