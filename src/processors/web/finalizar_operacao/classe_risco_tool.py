# -*- coding: utf-8 -*-
"""
classe_risco_tool.py - troca a CLASSE DE RISCO de titulos de uma operacao do
Smart 100% por HTTP na sessao viva (CDP 9222) - SEM abrir aba/tela nenhuma.

DOIS CAMINHOS (o Smart tem endpoints diferentes conforme o estado da operacao):

A) via FINANCEIRO - titulos JA EFETIVADOS (o caso comum; e o que a tela
   "Titulos em aberto" usa). Validado em producao 2026-08-27 (op 55823,
   titulo 824063, T->P->T, resposta {"resultado":"OK"}):
     - listar : POST financeiro/grid.php  (Pesquisar=1&NatOperacao=AR&NumOperacao=<op>)
                -> botoes id="classeRisco<i>" (classe atual) e
                   selecionaClasseRisco('<classe>','<i>','<numTitulo>')
     - aplicar: POST financeiro/atualizaclasseriscotitulo.php
                corpo: ClasseRisco=<classe>&NumTitulo=<numTitulo>
                resposta JSON {"resultado":"OK","classeRisco":"..."}
   Simples: SO precisa da classe e do numTitulo (sem sessionId/tokens).

B) via OPERACAO - operacao ainda EM ANALISE (mesmo caminho do credito V4):
     - GET  novatelaoperacao.php?action=edit&op=<op> -> sessionId + id_operacao
            + JSON `dadosTOP` (todos os campos de cada titulo)
     - POST controladoroperacaoajax.php acao=SALVAR_TITULOS ... titulos=<GeraString>
   ATENCAO: em operacao JA EFETIVADA esse POST responde 200 com corpo VAZIO e
   NAO persiste - por isso o padrao e --via auto (tenta A, cai p/ B).

Mecanismo (revertido 2026-08-27 do JS oficial do Smart):
  1. GET  operacaoajax/web/novatelaoperacao.php?action=edit&op=<op>
     -> extrai sessionId (JS global), id_operacao (hidden), NumCedente (hidden)
        e o JSON `dadosTOP` com TODOS os campos de cada titulo (inclusive a
        classeRisco atual).
  2. POST operacaoajax/web/controladoroperacaoajax.php
        acao=SALVAR_TITULOS&numOperacao=..&numCedente=..&titulos=<GeraString>
        &sessionId=..&id_operacao_session=..
     `titulos` e a serializacao GeraString() da linha (14 campos separados por @):
        numTitulo@tipo@leitora@numDoc@sacado@venc@valorFace@empenho@nota@numLinha@@@@classe
     Encoding do body = escape() legado do JS: '@' '/' '.' '-' '_' '*' '+' ficam
     literais; resto vira %XX (latin-1). (Mesmo formato do op_tool/REJEITAR.)

ATENCAO: SALVAR_TITULOS regrava o titulo com os campos enviados. A ferramenta
reenvia EXATAMENTE o que o dadosTOP devolveu, mudando so a classe - mas na
PRIMEIRA execucao real confira o titulo na UI depois.

DRY-RUN por padrao: mostra o que faria; so envia com --executar.

AS 10 CLASSES DE RISCO (menu "Classe de risco" do Smart; cor = badge na tela):
  P   Operação padrão            (verde)
  E   Boleto especial            (amarelo)
  T   Operação em tranche        (roxo)
  C   Operação comissária        (vermelho)
  B   Boleto especial + Tranche  (azul)
  BG  Boleto garantido           (cinza)
  CL  Operação Clean             (laranja)
  CE  Comissária com Escrow      (verde-água)
  I   Intercompany               (verde)
  BA  Barter                     (marrom)

Exemplos (PowerShell, rodar da RAIZ):
  python operacoes/classe_risco_tool.py --acao classes
  python operacoes/classe_risco_tool.py --op 62007 --acao listar
  python operacoes/classe_risco_tool.py --op 62007 --acao aplicar --classe B            # DRY
  python operacoes/classe_risco_tool.py --op 62007 --acao aplicar --classe B --executar
  python operacoes/classe_risco_tool.py --op 62007 --acao aplicar --classe T --linhas 2,3 --executar
  python operacoes/classe_risco_tool.py --op 62007 --acao aplicar --classe B --titulos 902017 --executar
  python operacoes/classe_risco_tool.py --op 62007 --acao aplicar --classe B --sacado WEERULIN --executar
"""
import argparse
import json
import re
import sys

from smart_session import BASE, Smart, utf8_stdout

URL_EDIT = BASE + "/operacaoajax/web/novatelaoperacao.php?action=edit&op={op}"
URL_POST = BASE + "/operacaoajax/web/controladoroperacaoajax.php"
# Tela do FINANCEIRO (titulos ja efetivados): endpoint dedicado, so ClasseRisco+NumTitulo
URL_FIN = BASE + "/financeiro/atualizaclasseriscotitulo.php"
URL_GRID = BASE + "/financeiro/grid.php"

# AS 10 CLASSES DE RISCO DO SMART (menu "Classe de risco", conferido na UI em
# 2026-08-27). Ordem = a mesma do menu. A cor e a do badge na tela.
CLASSES_INFO = [
    ("P",  "Operação padrão",           "verde"),
    ("E",  "Boleto especial",           "amarelo"),
    ("T",  "Operação em tranche",       "roxo"),
    ("C",  "Operação comissária",       "vermelho"),
    ("B",  "Boleto especial + Tranche", "azul"),
    ("BG", "Boleto garantido",          "cinza"),
    ("CL", "Operação Clean",            "laranja"),
    ("CE", "Comissária com Escrow",     "verde-água"),
    ("I",  "Intercompany",              "verde"),
    ("BA", "Barter",                    "marrom"),
]
CLASSES = {c for c, _, _ in CLASSES_INFO}
CLASSES_NOME = {c: n for c, n, _ in CLASSES_INFO}

_SAFE = set("@*/+-._ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")


def js_escape(s):
    """Equivalente ao escape() legado do JS (latin-1): usado no body do ajax."""
    out = []
    for ch in str(s):
        if ch in _SAFE:
            out.append(ch)
        else:
            code = ord(ch)
            if code < 256:
                out.append(f"%{code:02X}")
            else:
                out.append(f"%u{code:04X}")
    return "".join(out)


def carregar_operacao(s, op):
    """GET da tela da operacao -> tokens + dadosTOP (lista de titulos)."""
    status, html = s.get(URL_EDIT.format(op=op), timeout=60_000)
    if status != 200:
        raise RuntimeError(f"GET operacao {op}: status {status}")
    m_sid = re.search(r'sessionId\s*=\s*"([0-9a-f]+)"', html)
    m_ios = re.search(r"name=['\"]id_operacao['\"][^>]*value=['\"](\d+)['\"]", html)
    if not m_ios:
        m_ios = re.search(r"id_operacao\D{0,40}?(\d{6,})", html)
    m_ced = re.search(r"id=['\"]NumCedente['\"][^>]*value=['\"]([^'\"]*)['\"]", html)
    if not m_ced:
        m_ced = re.search(r"name=['\"]NumCedente['\"][^>]*value=['\"]([^'\"]*)['\"]", html)
    m_top = re.search(r"dadosTOP\s*=\s*(\[.*?\]);", html, re.S)
    m_tf = re.search(r"id=['\"]tipoFinanceiro['\"][^>]*value=['\"]([^'\"]*)['\"]", html)
    if not (m_sid and m_ios and m_top):
        faltou = [n for n, m in (("sessionId", m_sid), ("id_operacao", m_ios), ("dadosTOP", m_top)) if not m]
        raise RuntimeError(f"op {op}: nao extraiu {faltou} (sessao deslogada? op inexistente?)")
    titulos = json.loads(m_top.group(1))
    for i, t in enumerate(titulos):
        t["numLinha"] = i + 1
    return {
        "sessionId": m_sid.group(1),
        "id_operacao_session": m_ios.group(1),
        "numCedente": m_ced.group(1) if m_ced else "",
        "tipoFinanceiro": m_tf.group(1) if m_tf else None,
        "titulos": titulos,
    }


def gera_string(t, classe):
    """Reproduz o GeraString() do novogridoperacao.js, trocando so a classe."""
    campos = [
        t.get("numTitulo", ""), t.get("tipoTitulo", ""), t.get("cmc7", ""),
        t.get("numDocumento", ""), t.get("sacado", ""), t.get("vencimento", ""),
        t.get("valorFace", ""), t.get("empenho", ""), t.get("numeroNota", ""),
        t.get("numLinha", ""), "", "", "", classe,
    ]
    return "@".join(str(c) for c in campos)


def titulos_do_financeiro(s, op):
    """Le o grid do FINANCEIRO (titulos ja efetivados) da operacao: numTitulo +
    classe atual, direto dos botoes classeRisco<i> / selecionaClasseRisco(...)."""
    body = ("Pesquisar=1&numPessoa=&HomeFactoring=0&caminho=1"
            f"&NatOperacao=AR&NumOperacao={op}")
    status, html = s.post(URL_GRID, body, timeout=120_000)
    if status != 200:
        raise RuntimeError(f"grid.php op {op}: status {status}")
    # classe atual: <a ... id="classeRisco<i>" ...>CLASSE</a>
    atuais = {i: c.strip() for i, c in re.findall(
        r'id="classeRisco(\d+)"[^>]*>\s*([A-Z]{1,2})\s*<', html)}
    # numTitulo de cada indice: selecionaClasseRisco('X','<i>','<numTitulo>')
    mapa = {}
    for cls, idx, tit in re.findall(
            r"selecionaClasseRisco\('([A-Z]{1,2})',\s*'(\d+)',\s*'(\d+)'\)", html):
        mapa[idx] = tit
    out = []
    for idx, tit in sorted(mapa.items(), key=lambda kv: int(kv[0])):
        d = {"numTitulo": int(tit), "classeRisco": atuais.get(idx, "?"),
             "numLinha": int(idx) + 1, "tipoTitulo": "", "vencimento": "",
             "valorFace": "", "nomeSacado": ""}
        d.update(_dados_da_linha(html, idx))
        out.append(d)
    return out


def _dados_da_linha(html, idx):
    """Best-effort: extrai sacado/vencimento/valor da <tr> que tem o classeRisco<idx>."""
    m = re.search(rf'id="classeRisco{idx}"', html)
    if not m:
        return {}
    ini = html.rfind("<tr", 0, m.start())
    fim = html.find("</tr>", m.start())
    if ini < 0 or fim < 0:
        return {}
    linha = html[ini:fim]
    celulas = [re.sub(r"<[^>]+>", " ", c) for c in re.findall(r"<td\b[^>]*>(.*?)</td>", linha, re.S)]
    celulas = [re.sub(r"\s+", " ", c).strip() for c in celulas]
    d = {}
    for c in celulas:
        if not d.get("vencimento"):
            mv = re.fullmatch(r"(\d{2}/\d{2}/\d{4})", c)
            if mv:
                d["vencimento"] = mv.group(1)
                continue
        if not d.get("valorFace") and re.fullmatch(r"[\d.]+,\d{2}", c):
            d["valorFace"] = c
            continue
        if not d.get("nomeSacado") and len(c) > 8 and re.search(r"[A-Za-z]{4}", c) \
                and not re.fullmatch(r"[\d./,\-\s]+", c) \
                and not re.search(r"classe de risco|opera\S+o padr|boleto especial", c, re.I):
            d["nomeSacado"] = c[:45]
    return d


def aplicar_financeiro(s, titulo, classe):
    """POST no endpoint dedicado do financeiro. Retorna (ok, texto)."""
    body = f"ClasseRisco={classe}&NumTitulo={titulo}"
    status, resp = s.post(URL_FIN, body, timeout=60_000, headers={
        "x-requested-with": "XMLHttpRequest",
        "referer": BASE + "/financeiro/grid.php",
    })
    txt = resp.strip()[:200]
    ok = status == 200 and '"OK"' in resp or "'OK'" in resp or '"resultado":"OK"' in resp.replace(" ", "")
    return ok, f"status={status} resp={txt!r}"


def selecionar(titulos, args):
    """Filtra titulos por --linhas / --titulos / --sacado (default: todos)."""
    sel = titulos
    if args.linhas:
        alvo = {int(x) for x in args.linhas.split(",")}
        sel = [t for t in sel if t["numLinha"] in alvo]
    if args.titulos:
        alvo = {x.strip() for x in args.titulos.split(",")}
        sel = [t for t in sel if str(t.get("numTitulo")) in alvo]
    if args.sacado:
        pat = args.sacado.strip().upper()
        sel = [t for t in sel if pat in (t.get("nomeSacado") or "").upper()]
    return sel


def mostrar(titulos):
    print(f"  {'lin':>3} {'numTitulo':>9} {'CR':>2} {'tipo':4} {'vencto':10} {'valor':>12}  sacado")
    for t in titulos:
        print(f"  {t['numLinha']:>3} {t.get('numTitulo', ''):>9} {t.get('classeRisco', '?'):>2} "
              f"{t.get('tipoTitulo', ''):4} {t.get('vencimento', ''):10} {t.get('valorFace', ''):>12}  "
              f"{(t.get('nomeSacado') or '')[:45]}")


def aplicar_lista(args):
    """Aplica a classe a uma LISTA de numTitulo (via financeiro), sem depender
    de operacao. Le um numTitulo por linha (ignora vazios e comentarios #)."""
    classe = (args.classe or "").upper()
    if classe not in CLASSES:
        print(f"[ERRO] --classe invalida; validas: {sorted(CLASSES)}")
        return 2
    with open(args.lista, encoding="utf-8") as f:
        titulos = [l.strip() for l in f
                   if l.strip() and not l.startswith("#")]
    if not titulos:
        print("[ERRO] lista vazia")
        return 1
    print(f"=== LISTA: {len(titulos)} titulo(s) -> classe '{classe}' "
          f"({CLASSES_NOME.get(classe, '?')}) ===")
    if not args.executar:
        print(f"  [DRY-RUN] enviaria {len(titulos)} POST(s) "
              f"atualizaclasseriscotitulo.php ClasseRisco={classe}&NumTitulo=<n>")
        print(f"  primeiros: {', '.join(titulos[:10])}"
              f"{' ...' if len(titulos) > 10 else ''}")
        print("  repita com --executar para aplicar.")
        return 0

    with Smart() as s:
        if not s.logado():
            print("[ERRO] sessao deslogada - logue na janela do Chrome (CDP 9222)")
            return 2
        ok = err = 0
        falhas = []
        for i, t in enumerate(titulos, 1):
            bom, info = aplicar_financeiro(s, t, classe)
            if bom:
                ok += 1
            else:
                err += 1
                falhas.append((t, info))
            print(f"  [{i:>3}/{len(titulos)}] titulo {t}: {'OK' if bom else 'ERRO ' + info}")
        print("")
        print(f"  aplicados={ok} erros={err}")
        if falhas:
            print("  FALHAS:")
            for t, info in falhas:
                print(f"    {t}: {info}")
    return 0 if not falhas else 1


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser(description="Troca classe de risco de titulos por HTTP (sem UI).")
    ap.add_argument("--op")
    ap.add_argument("--acao", choices=["listar", "aplicar", "classes"], default="listar")
    ap.add_argument("--classe", help="classe alvo (P,E,T,C,B,CE,I,CL,BA,BG)")
    ap.add_argument("--linhas", help="ex.: 2,3")
    ap.add_argument("--titulos", help="numTitulo(s), ex.: 902017,902041")
    ap.add_argument("--sacado", help="trecho do nome do sacado")
    ap.add_argument("--executar", action="store_true", help="envia de verdade (senao DRY-RUN)")
    ap.add_argument("--lista", help="arquivo com um numTitulo por linha "
                                    "(aplica via FINANCEIRO, sem precisar de --op)")
    ap.add_argument("--via", choices=["auto", "operacao", "financeiro"], default="auto",
                    help="auto: tenta financeiro (op efetivada) e cai p/ operacao (op em analise)")
    args = ap.parse_args()

    if args.acao == "classes":
        print("=== CLASSES DE RISCO DO SMART ===")
        for cod, nome, cor in CLASSES_INFO:
            print(f"  {cod:>2}  {nome:<26} ({cor})")
        return 0
    if args.lista:
        return aplicar_lista(args)

    if not args.op:
        print("[ERRO] --op e obrigatorio (exceto para --acao classes / --lista)")
        return 2

    with Smart() as s:
        if not s.logado():
            print("[ERRO] sessao deslogada - logue na janela do Chrome (CDP 9222)")
            return 2

        # --- via FINANCEIRO: titulos ja efetivados (endpoint dedicado, simples) ---
        if args.via in ("auto", "financeiro"):
            try:
                fin = titulos_do_financeiro(s, args.op)
            except Exception as e:
                fin = []
                if args.via == "financeiro":
                    print(f"[ERRO] grid do financeiro: {e}")
                    return 2
            if fin:
                print(f"=== op {args.op} | {len(fin)} titulo(s) efetivado(s) [via FINANCEIRO] ===")
                if args.acao == "listar":
                    mostrar(fin)
                    return 0
                if not args.classe or args.classe.upper() not in CLASSES:
                    print(f"[ERRO] --classe obrigatoria; validas: {sorted(CLASSES)}")
                    return 2
                classe = args.classe.upper()
                sel = selecionar(fin, args)
                if not sel:
                    print("[ERRO] nenhum titulo bate com o filtro")
                    return 1
                mudar = [t for t in sel if (t.get("classeRisco") or "").upper() != classe]
                if len(sel) != len(mudar):
                    print(f"  ({len(sel) - len(mudar)} titulo(s) ja em '{classe}' -> pulando)")
                if not mudar:
                    print("  nada a mudar.")
                    return 0
                print(f"  vai mudar {len(mudar)} titulo(s) para '{classe}':")
                mostrar(mudar)
                if not args.executar:
                    for t in mudar:
                        print(f"  [DRY] POST atualizaclasseriscotitulo.php "
                              f"ClasseRisco={classe}&NumTitulo={t['numTitulo']}")
                    print("\n  DRY-RUN: nada enviado. Repita com --executar.")
                    return 0
                ok = err = 0
                for t in mudar:
                    bom, det = aplicar_financeiro(s, t["numTitulo"], classe)
                    print(f"  [{'OK' if bom else 'ERRO'}] titulo {t['numTitulo']}: {det}")
                    ok += 1 if bom else 0
                    err += 0 if bom else 1
                print(f"\n  aplicados={ok} erros={err}")
                print("  conferindo (releitura do grid):")
                mostrar(selecionar(titulos_do_financeiro(s, args.op), args))
                return 0
            if args.via == "auto":
                print("  (sem titulos no grid do financeiro -> tentando via OPERACAO)")

        # --- via OPERACAO: op ainda em analise (SALVAR_TITULOS) ---
        info = carregar_operacao(s, args.op)
        titulos = info["titulos"]
        print(f"=== op {args.op} | {len(titulos)} titulo(s) [via OPERACAO] | cedente={info['numCedente']} "
              f"| sid={info['sessionId'][:8]}... ios={info['id_operacao_session']} ===")

        if args.acao == "listar":
            mostrar(titulos)
            return 0

        # aplicar
        if not args.classe or args.classe.upper() not in CLASSES:
            print(f"[ERRO] --classe obrigatoria p/ aplicar; validas: {sorted(CLASSES)}")
            return 2
        classe = args.classe.upper()
        sel = selecionar(titulos, args)
        if not sel:
            print("[ERRO] nenhum titulo bate com o filtro")
            return 1
        pular = [t for t in sel if (t.get("classeRisco") or "").upper() == classe]
        mudar = [t for t in sel if (t.get("classeRisco") or "").upper() != classe]
        if pular:
            print(f"  ({len(pular)} titulo(s) ja em '{classe}' -> pulando)")
        if not mudar:
            print("  nada a mudar.")
            return 0
        print(f"  vai mudar {len(mudar)} titulo(s) para classe '{classe}':")
        mostrar(mudar)

        ok = err = 0
        for t in mudar:
            linha = gera_string(t, classe)
            body = ("acao=SALVAR_TITULOS"
                    f"&numOperacao={js_escape(args.op)}"
                    f"&numCedente={js_escape(info['numCedente'])}"
                    f"&titulos={js_escape(linha)}"
                    f"&sessionId={info['sessionId']}"
                    f"&id_operacao_session={info['id_operacao_session']}")
            if info["tipoFinanceiro"] is not None:
                body += f"&tipoFinanceiro={js_escape(info['tipoFinanceiro'])}"
            if not args.executar:
                print(f"  [DRY] titulo {t['numTitulo']} (linha {t['numLinha']}): "
                      f"{t.get('classeRisco')} -> {classe}")
                print(f"        titulos={linha}")
                continue
            status, resp = s.post(URL_POST, body, timeout=60_000)
            resp1 = resp.strip().splitlines()[0][:160] if resp.strip() else "(vazio)"
            ruim = status != 200 or "SESSAO_INVALIDA" in resp or "ERRO" in resp[:200].upper()
            print(f"  [{'ERRO' if ruim else 'OK'}] titulo {t['numTitulo']}: status={status} resp: {resp1}")
            ok += 0 if ruim else 1
            err += 1 if ruim else 0
        if not args.executar:
            print(f"\n  DRY-RUN: nada enviado. Repita com --executar para aplicar.")
        else:
            print(f"\n  aplicados={ok} erros={err}")
            # confere relendo a operacao
            info2 = carregar_operacao(s, args.op)
            print("  classes apos aplicar:")
            mostrar(selecionar(info2["titulos"], args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
