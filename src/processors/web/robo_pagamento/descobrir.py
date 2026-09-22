# -*- coding: utf-8 -*-
"""
descobrir.py - FASE 0: mapeia a tela "Gerar Remessa" do Pagamento BMP Money Plus.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Quando foi escrito, nenhum endpoint da arvore de pagamento estava mapeado neste
repo — so os de COBRANCA. Ele resolveu isso: em 21/08/2026, pelo sandbox do
host, mapeou a arvore inteira (`financeiro/pagtobmp/`), os campos do form e o
`GerarMultipag` do JS. O resultado esta em `pagamento_config.py` e em
`docs/README.md`; o HTML cru que o sustenta, em `DEBUG_DIR`.

Continua util depois disso: tela de ERP muda, e reconferir o contrato e mais
barato (e mais honesto) do que descobrir pelo robo quebrando em producao.

DIVISAO DE TRABALHO (a mesma do retorno_cobranca)
---------------------------------------------
    analise.py     PURO (so stdlib) -> tem os testes, roda no host
    descobrir.py   rede e sessao    -> nao tem logica para testar

Este arquivo so busca HTML, salva no debug e imprime o que o `analise.py`
concluiu. Toda a leitura de tela mora la, e e la que o pytest bate.

O QUE ELE NAO FAZ, E POR QUE
----------------------------
**Nao varre o Smart sozinho.** Em ERP, link de menu e tela, mas link de grade as
vezes E ACAO — um GET cego numa sessao autenticada de producao pode efetivar
coisa. Por isso:

  - o padrao so LISTA os links achados, sem visitar nenhum;
  - visitar exige `--url` explicito ou `--seguir`, que e opt-in e vai um nivel so;
  - o UNICO POST possivel e o `--filtrar`, e ele e cercado (ver abaixo).

O `--filtrar` e a excecao, e ela foi ganha por medicao
------------------------------------------------------
Este modulo nasceu com "nunca faz POST. Nenhum." Caiu em 21/08/2026, contra a
tela real: a grade da `pagtobmp` NAO aparece no GET — `pagtobmpgrid.php` sem
submit devolve o mesmo formulario de pesquisa, vazio. Sem submeter o filtro nao
ha o que descobrir.

Entao o POST existe, mas cercado, e as travas vivem no modulo puro (portanto tem
teste): `analise.montar_filtro` recusa qualquer form que nao tenha o campo
`pesquisar`, e NUNCA inclui campo de botao — o navegador so manda o botao que
foi clicado, e numa tela de PAGAMENTO um desses botoes gera remessa.

O ponto de partida da varredura NAO e uma tela de trabalho: medido, elas nao
carregam o menu (a de remessa de cobranca tem 4 links). O menu esta no PAINEL
(`smartsecurities.php`, 80 links) — e la que a arvore aparece, sob o nome
`financeiro/pagtobmp/`, que nao contem a palavra "pagamento".

USO (dentro do container)
-------------------------
    # 1) que telas de pagamento existem?
    sh /app/src/processors/web/robo_pagamento/run_descoberta.sh --links pagamento

    # 2) abre UMA delas e despeja tudo que o robo vai precisar
    sh .../run_descoberta.sh --url https://wvw.smartsecurities.com.br/smart/<tela>.php

    # 3) sobre uma janela que voce ja logou no VNC (nao gasta CapSolver)
    python .../descobrir.py --cdp --links pagamento

O HTML cru de cada pagina visitada fica em DEBUG_DIR — e a evidencia que sustenta
o robo depois, e o que permite reler sem repetir a visita.
"""
import argparse
import os
import re
import sys
import urllib.parse
from datetime import datetime

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from playwright.sync_api import sync_playwright        # noqa: E402

import analise                                         # noqa: E402
import pagamento_config as cfg                         # noqa: E402
from src.common.clients import smart_sessao            # noqa: E402

SAIU_OK = 0
SAIU_SEM_NAVEGADOR = 1
SAIU_SEM_SESSAO = 2
SAIU_SMART_MUDO = 3
SAIU_NADA_ACHADO = 7


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# rede e disco
# --------------------------------------------------------------------------- #
def buscar(ctx, url, timeout=60_000):
    """GET autenticado. Retorna (status, html) — html None se nao deu.

    `parece_deslogado` aqui nao e zelo: sessao morta responde HTTP 200 com um
    redirect JS para `expira.php`, e sem esta checagem toda pagina viraria
    "tela vazia" e a descoberta terminaria dizendo que a tela nao existe.
    """
    try:
        r = ctx.request.get(url, timeout=timeout)
    except Exception as e:                                          # noqa: BLE001
        log(f"  ERRO ao buscar {url}: {e}")
        return None, None
    corpo = r.body().decode("iso-8859-1", errors="replace")
    if smart_sessao.parece_deslogado(corpo):
        log(f"  {url}: a resposta diz DESLOGADO (expira.php) — nao e tela vazia")
        return r.status, None
    return r.status, corpo


def salvar(html, apelido):
    """Grava o HTML cru no DEBUG_DIR e devolve o caminho."""
    cfg.ensure_dirs()
    seguro = re.sub(r"[^A-Za-z0-9._-]", "_", apelido)[:80]
    caminho = os.path.join(cfg.DEBUG_DIR,
                           f"{datetime.now():%Y%m%d-%H%M%S}_{seguro}.html")
    with open(caminho, "w", encoding="utf-8", errors="replace") as f:
        f.write(html)
    return caminho


# --------------------------------------------------------------------------- #
# relatorio
# --------------------------------------------------------------------------- #
def relatar_tela(url, html, arquivo):
    info = analise.analisar(html, url)
    molde, motivo = analise.classificar(info)

    log("=" * 70)
    log(f"TELA: {url}")
    log(f"HTML cru salvo em: {arquivo}")
    log(f"MOLDE: {molde.upper()} — {motivo}")
    log("=" * 70)

    if info["ajax"]:
        log(f"AJAX ({len(info['ajax'])}):")
        for u in info["ajax"]:
            log(f"    {u}")
    if info["acoes"]:
        log(f"ACOES no JS ({len(info['acoes'])}):")
        for a in info["acoes"]:
            log(f"    {a}")

    for f in info["forms"]:
        log("-" * 70)
        log(f"FORM name={f['nome']}  method={f['method']}")
        log(f"     action={f['action']}")
        for c in f["campos"]:
            if c["elem"] == "select":
                log(f"     select {c['nome']!r} ({len(c['opcoes'])} opcoes)")
                for valor, rotulo in c["opcoes"][:12]:
                    log(f"         {valor!r:>10} = {rotulo}")
                if len(c["opcoes"]) > 12:
                    log(f"         ... mais {len(c['opcoes']) - 12}")
            elif c["nome"]:
                extra = f" = {c['valor']!r}" if c.get("valor") else ""
                marca = " [marcado]" if c.get("marcado") else ""
                log(f"     {c['tipo']:9} {c['nome']!r}{extra}{marca}")

    if molde == analise.MOLDE_INDEFINIDO:
        achados = analise.frames(html, url)
        if achados:
            log("-" * 70)
            log(f"FRAMES ({len(achados)}) — rode --url em cada um:")
            for u in achados:
                log(f"    {u}")

    # Os links DA PROPRIA tela. Medido em 21/08/2026: a arvore de pagamento nao
    # aparece na tela de trabalho nem no painel sob o nome "pagamento" — ela e
    # `financeiro/pagtobmp/`. Sem listar os vizinhos, cada salto custa um run
    # inteiro (e um CapSolver, porque a sessao do Smart nao sobrevive ao
    # fechamento do Chrome). Listar aqui e o que faz uma visita render.
    vizinhos = {u: r for u, r in info["links"].items() if u != url}
    if vizinhos:
        log("-" * 70)
        log(f"LINKS nesta tela ({len(vizinhos)}):")
        for u, r in sorted(vizinhos.items())[:40]:
            log(f"    {r or '(sem rotulo)':34} {u}")
        if len(vizinhos) > 40:
            log(f"    ... mais {len(vizinhos) - 40}")
    return info


def relatar_links(links, termo):
    alvo = (termo or "").lower()
    casam = {u: r for u, r in links.items()
             if alvo in u.lower() or alvo in (r or "").lower()}
    log("=" * 70)
    log(f"{len(links)} link(s) .php na pagina | {len(casam)} casam com {termo!r}")
    log("=" * 70)
    for u, r in sorted(casam.items()):
        log(f"  {r or '(sem rotulo)':38} {u}")
    if not casam:
        log("  Nenhum. A arvore de pagamento pode nao estar embutida nesta pagina.")
        log("  Abra a tela pelo VNC (display :94), copie a URL da barra e rode")
        log("  com --url. Se a tela viver num frame, a URL certa e a do FRAME.")
    return casam


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def montar_parser():
    ap = argparse.ArgumentParser(
        description="Fase 0: mapeia a tela de Gerar Remessa do Pagamento BMP.")
    ap.add_argument("--links", nargs="?", const="pagamento", metavar="TERMO",
                    help="lista os links .php da semente que casam com TERMO "
                         "(padrao: 'pagamento'). NAO visita nenhum.")
    ap.add_argument("--url", help="analisa ESTA tela (a unica forma de visitar "
                                  "algo que nao seja a semente)")
    ap.add_argument("--seguir", action="store_true",
                    help="com --links: visita tambem os links que casaram "
                         "(um nivel, so GET). Opt-in de proposito.")
    ap.add_argument("--semente", default=cfg.URL_SEMENTE,
                    help=f"ponto de partida (padrao: {cfg.URL_SEMENTE})")
    ap.add_argument("--filtrar", action="store_true",
                    help="submete o form de BUSCA da tela de --url (unico POST "
                         "do modulo; so passa em form que tenha `pesquisar`)")
    ap.add_argument("--conta", default="",
                    help="com --filtrar: valor de IdContaBancaria")
    ap.add_argument("--status", default="",
                    help="com --filtrar: valor de pagtobmp (P/G/R)")
    ap.add_argument("--baixar", default="", metavar="ID",
                    help="baixa o arquivo `mandarsispag.php?file=ID` e relata o "
                         "layout. So leitura — download nao gera nada.")
    ap.add_argument("--gerar", action="store_true",
                    help="fluxo fechado: pesquisa PENDENTE, monta o POST de "
                         "geracao e (com --pra-valer) gera e baixa o arquivo")
    ap.add_argument("--pra-valer", action="store_true",
                    help="com --gerar: ENVIA. Sem isto, so mostra o corpo.")
    ap.add_argument("--cdp", action="store_true",
                    help="usa um Chrome JA ABERTO (dev/VNC) em vez de subir o proprio")
    return ap


def filtrar(ctx, url, valores, log=print):
    """GET na tela, monta o SUBMIT DE BUSCA do form dela e posta. So isso.

    E o unico ponto de todo o `descobrir.py` que faz POST, e so roda com
    `--filtrar` explicito. Existe porque a grade da `pagtobmp` nao aparece no
    GET: sem submeter o filtro, a tela devolve o mesmo formulario vazio (medido
    em 21/08/2026 — `pagtobmpgrid.php` no GET = a tela de pesquisa).

    Quem decide o que vai no corpo e `analise.montar_filtro`, que recusa
    qualquer form sem o campo `pesquisar` e nunca inclui botao — ver as tres
    travas la.
    """
    status, html = buscar(ctx, url)
    if not html:
        log(f"nao consegui ler a tela (status={status}).")
        return None, None
    info = analise.analisar(html, url)
    formularios = [f for f in info["forms"] if any(c["nome"] for c in f["campos"])]
    if not formularios:
        log("a tela nao tem form com campos — nada a filtrar.")
        return None, None
    form = formularios[0]
    try:
        corpo, campos = analise.montar_filtro(form, valores)
    except ValueError as e:
        log(f"RECUSADO: {e}")
        return None, None

    log(f"POST (busca) -> {form['action']}")
    for k, v in sorted(campos.items()):
        log(f"     {k} = {v!r}")
    try:
        r = ctx.request.post(
            form["action"], data=corpo,
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=120_000)
    except Exception as e:                                          # noqa: BLE001
        log(f"  ERRO no POST: {e}")
        return None, None
    corpo_resp = r.body().decode("iso-8859-1", errors="replace")
    if smart_sessao.parece_deslogado(corpo_resp):
        log("  a resposta do POST diz DESLOGADO — nao e grade vazia")
        return None, None
    return form["action"], corpo_resp


def baixar(ctx, ident, log=print):
    """GET no arquivo que a grade linka. SO LEITURA — download nao gera nada.

    Serve para MEDIR o layout do arquivo antes de a Fase 1 existir: sem isto, o
    validador do robo teria de supor CNAB-240 (o usual em pagamento) contra os
    CNAB-400 da cobranca — e supor layout e como se grava pagina de erro com
    nome de .REM.
    """
    url = f"{cfg.URL_DOWNLOAD}?file={ident}"
    log(f"GET {url}")
    try:
        r = ctx.request.get(url, timeout=90_000)
    except Exception as e:                                          # noqa: BLE001
        log(f"  ERRO: {e}")
        return None
    dados = r.body()
    cd = r.headers.get("content-disposition", "")
    nome = analise.nome_do_arquivo(cd, padrao=f"arquivo_{ident}.REM")

    info = analise.inspecionar_arquivo(dados)
    log("=" * 70)
    log(f"ARQUIVO file={ident}")
    log(f"  status={r.status}  bytes={len(dados)}")
    log(f"  content-type={r.headers.get('content-type', '?')}")
    log(f"  content-disposition={cd or '(nenhum)'}")
    log(f"  nome sugerido={nome}")
    log(f"  LAYOUT: {info['layout']}  linhas={info['linhas']}  "
        f"comprimentos={info['comprimentos']}")
    log(f"  ok={info['ok']} ({info['motivo']})")
    log(f"  header: {info['header']!r}")
    log("=" * 70)

    cfg.ensure_dirs()
    destino = os.path.join(cfg.DEBUG_DIR, nome)
    with open(destino, "wb") as f:
        f.write(dados)
    log(f"  salvo em {destino}")
    return info


def executar(ctx, args):
    if getattr(args, "gerar", False):
        # O fluxo de producao mora em `gerar.py`. Rodar `--gerar` daqui e rodar
        # EXATAMENTE o que o robo agendado roda — se fosse copia, testar aqui
        # deixaria de testar o que vai para producao.
        import gerar as ger                                        # noqa: E402
        r = ger.ciclo(ctx, getattr(args, "conta", "") or None,
                      dry_run=not getattr(args, "pra_valer", False), log=log)
        log(f"resultado: {r}")
        return SAIU_OK if (r["gerou"] or not r["pendentes"]
                           or r["motivo"] == "DRY_RUN") else SAIU_NADA_ACHADO

    if getattr(args, "baixar", ""):
        return SAIU_OK if baixar(ctx, args.baixar, log=log) else SAIU_NADA_ACHADO

    if getattr(args, "filtrar", False):
        alvo = args.url or (cfg.URL_GERAR or "")
        if not alvo:
            log("ERRO: --filtrar precisa de --url (a tela cujo form sera submetido).")
            return SAIU_NADA_ACHADO
        valores = {}
        if getattr(args, "conta", ""):
            valores["IdContaBancaria"] = args.conta
        if getattr(args, "status", ""):
            valores["pagtobmp"] = args.status
        url_post, pagina = filtrar(ctx, alvo, valores, log=log)
        if not pagina:
            return SAIU_NADA_ACHADO
        relatar_tela(url_post, pagina, salvar(pagina, "grade_filtrada"))
        return SAIU_OK

    if args.url:
        status, html = buscar(ctx, args.url)
        if not html:
            log(f"nao consegui ler a tela (status={status}).")
            return SAIU_NADA_ACHADO
        relatar_tela(args.url, html, salvar(html, urllib.parse.urlparse(args.url).path))
        return SAIU_OK

    termo = args.links or "pagamento"
    log(f"semente: {args.semente}")
    status, html = buscar(ctx, args.semente)
    if not html:
        log(f"a semente nao respondeu util (status={status}).")
        return SAIU_NADA_ACHADO
    log(f"HTML da semente salvo em: {salvar(html, 'semente')}")
    casam = relatar_links(analise.coletar_links(html, args.semente), termo)
    if not casam:
        return SAIU_NADA_ACHADO
    if not args.seguir:
        log("")
        log("Escolha uma e rode com --url <url>, ou repita com --seguir para")
        log("visitar todas de uma vez (GET, um nivel).")
        return SAIU_OK

    for u in sorted(casam):
        status, pagina = buscar(ctx, u)
        if not pagina:
            log(f"  {u}: sem resposta util (status={status})")
            continue
        relatar_tela(u, pagina, salvar(pagina, urllib.parse.urlparse(u).path))
    return SAIU_OK


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                               # noqa: BLE001
        pass

    args = montar_parser().parse_args()
    if cfg.ping_provisorio():
        log("AVISO: URL_PING_PAG ainda e a semente. Isso valida a SESSAO, nao a")
        log("       permissao na tela de pagamento — que e justamente o que esta")
        log("       descoberta serve para resolver.")

    with sync_playwright() as p:
        try:
            with smart_sessao.sessao(p, cfg, usar_cdp=args.cdp, log=log) as ctx:
                estado = smart_sessao.sessao_viva(ctx, cfg, log=log)
                if estado == "deslogado":
                    log("ERRO: a sessao do Smart nao esta logada.")
                    return SAIU_SEM_SESSAO
                if estado is None:
                    log("ERRO: nao consegui falar com o Smart. Rede? Smart fora? "
                        "(isto NAO quer dizer deslogado)")
                    return SAIU_SMART_MUDO
                log("sessao do Smart OK (logada).")
                return executar(ctx, args)
        except smart_sessao.SmartIndisponivel as e:
            log(f"ERRO: {e}")
            return SAIU_SMART_MUDO
        except smart_sessao.SemSessao as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_SESSAO
        except smart_sessao.SemNavegador as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_NAVEGADOR


if __name__ == "__main__":
    sys.exit(main())
