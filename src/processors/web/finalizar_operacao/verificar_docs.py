# -*- coding: utf-8 -*-
"""
verificar_docs.py - VERIFICA os documentos digitais EMITIDOS de uma operacao,
consultando o doc2you (provedor de assinatura digital onde o Smart deposita
Aditivo/Nota Promissoria/Duplicata).

Endpoint (mapeado 2026-05-29 no pacote de origem, op 61270):
  POST https://www.doc2you.com.br/documento/documentos
  form: page=0, numOperacao=<op>, e varios filtros vazios.
  Resposta: HTML com uma tabela; cada documento e uma <tr> com:
    - checkbox chk (value=idDoc, data-statusdocumento=P/C/...)
    - td Tipo:    "Contrato" (=Aditivo de securitizacao) | "Nota promissoria" | "Duplicata"
    - td Cedente, td Descricao (link visualizar), td Status (Pendente/Concluido),
      td Geracao, td Emissao, td Vencimento, ... Nº operacao, Nº documento.

Usa uma sessao VIVA do Smart por CDP (no pacote de origem era a de outro job, porta 9223).

Uso (da raiz):
  python finalizar_operacao/verificar_docs.py 61270
  python finalizar_operacao/verificar_docs.py 61270 61256 61247      # varias ops
"""
import re
import sys

from playwright.sync_api import sync_playwright

URL = "https://www.doc2you.com.br/documento/documentos"
SSO_URL = "https://wvw.smartsecurities.com.br/smart/doc2you.php"
CDP = "http://127.0.0.1:9223"


def sso_doc2you(ctx):
    """Estabelece a sessao no doc2you (SSO via Smart). Necessario numa sessao
    nova/automatizada antes de consultar o doc2you, senao a consulta volta vazia.
    Abre a pagina doc2you.php (que faz o SSO e seta os cookies do doc2you)."""
    pg = ctx.new_page()
    try:
        pg.goto(SSO_URL, wait_until="domcontentloaded", timeout=60_000)
        pg.wait_for_timeout(3000)
        # alguns SSO redirecionam dentro de iframe/js; uma 2a navegacao garante
        try:
            pg.goto("https://www.doc2you.com.br/documento", wait_until="domcontentloaded", timeout=30_000)
            pg.wait_for_timeout(1500)
        except Exception:
            pass
    finally:
        try: pg.close()
        except Exception: pass

# tipos que nos interessam (como aparecem na coluna "Tipo" do doc2you)
TIPO_ADITIVO = "Contrato"          # descricao = "Aditivo de securitizacao <op>"
TIPO_NPP = "Nota promiss"          # "Nota promissoria"
TIPO_DUPLICATA = "Duplicata"


def _body(op):
    return {
        "page": "0", "dataInicio": "", "dataFinal": "", "dataEmissaoIni": "",
        "dataEmissaoFim": "", "dataVencimentoIni": "", "dataVencimentoFim": "",
        "tipoDocumento": "", "docParte": "", "papel": "", "numOperacao": str(op),
        "numDocumento": "", "statusDocumento": "", "docCedente": "",
        "nomeCedente": "", "idCedente": "",
    }


def _td_textos(tr_html):
    """Texto limpo de cada <td> de PRIMEIRO nivel do <tr> (ignora tags internas)."""
    tds = re.findall(r"<td[^>]*>(.*?)</td>", tr_html, re.I | re.S)
    out = []
    for td in tds:
        t = re.sub(r"<[^>]+>", "", td)            # tira tags
        t = re.sub(r"&nbsp;?", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        out.append(t)
    return out


def parse_documentos(html):
    """Devolve lista de docs: {idDoc, status_code, tipo, descricao, status,
    emissao, vencimento, num_doc}. Cada doc e uma <tr> com checkbox 'chk'."""
    docs = []
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", html, re.I | re.S):
        mchk = re.search(r"name='chk'[^>]*value='(\d+)'[^>]*data-statusdocumento='([^']*)'", tr, re.I)
        if not mchk:
            continue
        idDoc, status_code = mchk.group(1), mchk.group(2)
        tds = _td_textos(tr)
        # acha o tipo (primeiro td que casa um dos tipos conhecidos)
        tipo = ""
        for t in tds:
            if t in ("Contrato", "Duplicata") or t.lower().startswith("nota promiss"):
                tipo = t
                break
        # descricao = td com "de securit"/"Promiss"/"Duplicata ..."
        descricao = ""
        for t in tds:
            if re.search(r"securit|promiss|duplicata \d|referente ao aditivo", t, re.I):
                descricao = t
                break
        # status textual (Pendente/Concluido/...)
        status = ""
        for t in tds:
            if t in ("Pendente", "Concluído", "Concluido", "Cancelado", "Aguardando",
                     "Expirado", "Rejeitado"):
                status = t
                break
        # datas (dd/mm/aaaa) e numero do documento (ex 31954-001)
        datas = re.findall(r"\d{2}/\d{2}/\d{4}", tr)
        vencimento = ""
        mvenc = re.search(r"Vencimento (\d{2}/\d{2}/\d{4})", tr)
        if mvenc:
            vencimento = mvenc.group(1)
        num_doc = ""
        mnd = re.search(r"(\d{4,6}-\d{3})", tr)
        if mnd:
            num_doc = mnd.group(1)
        docs.append({
            "idDoc": idDoc, "status_code": status_code, "tipo": tipo,
            "descricao": descricao[:80], "status": status,
            "emissao": datas[1] if len(datas) > 1 else (datas[0] if datas else ""),
            "vencimento": vencimento, "num_doc": num_doc,
        })
    return docs


def verificar_op(ctx, op):
    """Consulta o doc2you e resume os documentos da op. Retorna dict."""
    r = ctx.request.post(URL, form=_body(op), timeout=60_000)
    html = r.body().decode("utf-8", errors="replace")
    docs = parse_documentos(html)
    aditivos = [d for d in docs if d["tipo"] == "Contrato"]
    npps = [d for d in docs if d["tipo"].lower().startswith("nota promiss")]
    dups = [d for d in docs if d["tipo"] == "Duplicata"]

    def _ok(lst):  # ha pelo menos 1 e nenhum cancelado/rejeitado
        return len(lst) > 0

    return {
        "op": str(op), "status_http": r.status, "total": len(docs),
        "tem_aditivo": _ok(aditivos), "tem_npp": _ok(npps), "tem_duplicata": _ok(dups),
        "n_aditivo": len(aditivos), "n_npp": len(npps), "n_duplicata": len(dups),
        "docs": docs,
    }


def _resumo(res):
    op = res["op"]
    def mark(b): return "OK " if b else "FALTA"
    print(f"\n=== op {op} | {res['total']} documento(s) no doc2you (HTTP {res['status_http']}) ===")
    print(f"  [{mark(res['tem_aditivo'])}] Aditivo (Contrato) : {res['n_aditivo']}")
    print(f"  [{mark(res['tem_npp'])}] Nota Promissoria    : {res['n_npp']}")
    print(f"  [{mark(res['tem_duplicata'])}] Duplicata           : {res['n_duplicata']}")
    # detalhe dos nao-duplicata (Aditivo/NPP) + contagem de status das duplicatas
    for d in res["docs"]:
        if d["tipo"] != "Duplicata":
            print(f"     - {d['tipo']:<16} | {d['status']:<10} | {d['descricao']}")
    by_status = {}
    for d in res["docs"]:
        if d["tipo"] == "Duplicata":
            by_status[d["status"]] = by_status.get(d["status"], 0) + 1
    if by_status:
        print("     - Duplicatas por status: " +
              ", ".join(f"{k}={v}" for k, v in by_status.items()))


def main():
    args = sys.argv[1:] or ["61270"]
    # --arquivo <path>: le ops (uma por linha; aceita CSV 'id_operacao;...' com cabecalho)
    ops = []
    i = 0
    while i < len(args):
        if args[i] in ("--arquivo", "-a") and i + 1 < len(args):
            with open(args[i + 1], encoding="utf-8") as fh:
                for ln in fh:
                    tok = ln.strip().split(";")[0].strip()
                    if tok.isdigit():
                        ops.append(tok)
            i += 2
        else:
            ops.append(args[i]); i += 1
    # dedup preservando ordem
    ops = list(dict.fromkeys(ops))
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    problemas = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        sso_doc2you(ctx)   # garante a sessao no doc2you antes de consultar
        for op in ops:
            try:
                res = verificar_op(ctx, op)
            except Exception as e:
                print(f"\n=== op {op} | ERRO ao consultar: {e} ===")
                problemas.append((op, "erro_consulta"))
                continue
            _resumo(res)
            falta = []
            if not res["tem_aditivo"]:
                falta.append("Aditivo")
            if not res["tem_npp"]:
                falta.append("NPP")
            if not res["tem_duplicata"]:
                falta.append("Duplicata")
            if falta:
                problemas.append((op, "falta " + "+".join(falta)))
    # SUMARIO FINAL
    print("\n" + "=" * 60)
    print(f"SUMARIO: {len(ops)} op(s) verificada(s)")
    if problemas:
        print(f"  >> {len(problemas)} op(s) COM PENDENCIA:")
        for op, motivo in problemas:
            print(f"     - {op}: {motivo}")
    else:
        print("  >> TODAS OK (Aditivo + NPP + Duplicata presentes em todas).")
    print("=" * 60)


if __name__ == "__main__":
    main()
