# -*- coding: utf-8 -*-
"""
op_docs.py - documentos de uma OPERACAO do Smart (aba "Outros documentos"),
via HTTP na sessao viva. Consolida listar / baixar / anexar / excluir.

Mecanismo (mapeado 2026-05-25 na op 61065):
  popup        : operacao/popupdocumentos.php?Op=<op>&Tipo=OUT  (lista + form)
  cada doc     : <a onclick="viewDoc(<idDoc>)">NOME.pdf</a>
  visualizar   : operacao/viewdoc.php?idDoc=<id> -> HTML com <iframe src=...> que
                 aponta p/ documento.php/... (o PDF real, application/pdf)
  ANEXAR (POST): popupdocumentos.php  multipart/form-data
                 Op, Tipo=OUT, processar=1, MAX_FILE_SIZE=15728640,
                 arquivo no campo avatar_fileN[]   (aceita .pdf/.jpg/.png, <=15MB)
  EXCLUIR(POST): popupdocumentos.php  deletar=1, docs=<idDoc>, processar=1

Exemplos (PowerShell):
  python op_docs.py --op 61065 --acao listar
  python op_docs.py --op 61065 --acao baixar                       # baixa todos
  python op_docs.py --op 61065 --acao baixar --iddoc 17886
  python op_docs.py --op 61065 --acao anexar --arquivo contrato.pdf            # DRY
  python op_docs.py --op 61065 --acao anexar --arquivo contrato.pdf --executar # envia
"""
import argparse
import os
import re
import sys

from smart_session import BASE, HOST, Smart, utf8_stdout

URL_POPUP = BASE + "/operacao/popupdocumentos.php"
URL_VIEW = BASE + "/operacao/viewdoc.php"
MAX_FILE = 15728640
EXTS = {".pdf": "application/pdf", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".png": "image/png"}


def listar_docs(s, op):
    """Devolve [{idDoc, nome, data}] dos documentos anexados na op."""
    st, html = s.get(f"{URL_POPUP}?Op={op}&Tipo=OUT")
    docs = []
    # <td>...DATA</td> <td> <a ... onclick="viewDoc(ID)">NOME</a>
    for m in re.finditer(
            r"(\d{2}/\d{2}/\d{4}[\d :]*)</td>\s*<td[^>]*>\s*<a[^>]*viewDoc\((\d+)\)[^>]*>([^<]+)</a>",
            html, re.I | re.S):
        docs.append({"data": m.group(1).strip(), "idDoc": m.group(2), "nome": m.group(3).strip()})
    # fallback: so os viewDoc, se o pareamento com data falhar
    if not docs:
        for m in re.finditer(r"viewDoc\((\d+)\)[^>]*>([^<]+)</a>", html, re.I):
            docs.append({"data": "", "idDoc": m.group(1), "nome": m.group(2).strip()})
    return st, docs


def obter_doc_bytes(s, idDoc, nome=None):
    """Baixa o binario do documento e devolve (bytes, nome_com_extensao).
    Em falha devolve (None, motivo). NAO escreve em disco (uso: subir p/ Nextcloud)."""
    st, html = s.get(f"{URL_VIEW}?idDoc={idDoc}")
    m = re.search(r"src=['\"]([^'\"]+)['\"]", html)
    if not m:
        return None, f"iframe nao encontrado (status {st})"
    src = m.group(1)
    url = src if src.startswith("http") else HOST + src
    r = s.ctx.request.get(url, timeout=60_000)
    b = r.body()
    ct = r.headers.get("content-type", "")
    if not (b[:4] == b"%PDF" or "pdf" in ct or "image" in ct):
        return None, f"conteudo inesperado (ct={ct}, inicio={b[:8]!r})"
    ext = ".pdf" if b[:4] == b"%PDF" else (".png" if b[:4] == b"\x89PNG" else ".jpg")
    nome = nome or f"doc_{idDoc}{ext}"
    if not os.path.splitext(nome)[1]:
        nome += ext
    return b, nome


def baixar_doc(s, idDoc, nome=None):
    """Baixa o binario do documento e SALVA local. Retorna (ok, caminho/erro)."""
    b, nome = obter_doc_bytes(s, idDoc, nome)
    if b is None:
        return False, nome   # nome carrega o motivo do erro
    open(nome, "wb").write(b)
    return True, nome


def anexar_doc(s, op, caminho):
    """Upload de um arquivo na aba Outros documentos. Retorna (status, corpo)."""
    nome = os.path.basename(caminho)
    ext = os.path.splitext(nome)[1].lower()
    mime = EXTS.get(ext, "application/octet-stream")
    with open(caminho, "rb") as fh:
        data = fh.read()
    r = s.ctx.request.post(URL_POPUP, multipart={
        "MAX_FILE_SIZE": str(MAX_FILE),
        "Op": str(op),
        "Tipo": "OUT",
        "processar": "1",
        "avatar_fileN[]": {"name": nome, "mimeType": mime, "buffer": data},
    }, timeout=120_000)
    return r.status, r.body().decode("iso-8859-1", errors="replace")


def main():
    ap = argparse.ArgumentParser(description="Documentos da operacao Smart via HTTP.")
    ap.add_argument("--op", required=True)
    ap.add_argument("--acao", choices=["listar", "baixar", "anexar", "excluir"], default="listar")
    ap.add_argument("--iddoc", help="idDoc especifico (baixar/excluir). Sem ele, baixar pega TODOS")
    ap.add_argument("--arquivo", help="arquivo a anexar (.pdf/.jpg/.png)")
    ap.add_argument("--executar", action="store_true", help="anexar/excluir de verdade (sem isso = DRY-RUN)")
    args = ap.parse_args()

    utf8_stdout()
    with Smart() as s:
        if not s.logado():
            print("[ERRO] sessao DESLOGADA. Logue na janela do Chrome e tente de novo.")
            return 2

        if args.acao in ("listar", "baixar"):
            st, docs = listar_docs(s, args.op)
            print(f"=== op {args.op} | {len(docs)} documento(s) anexado(s) ===")
            for d in docs:
                print(f"  idDoc {d['idDoc']:>7} | {d['data']:<20} | {d['nome']}")
            if args.acao == "baixar":
                alvo = [d for d in docs if (not args.iddoc or d["idDoc"] == args.iddoc)]
                if not alvo:
                    print("\n[ERRO] nenhum doc p/ baixar (confira --iddoc).")
                    return 4
                print(f"\n>>> baixando {len(alvo)} doc(s):")
                for d in alvo:
                    ok, res = baixar_doc(s, d["idDoc"], f"op{args.op}_{d['nome']}")
                    print(f"  {'OK ' if ok else 'ERRO'} idDoc {d['idDoc']} -> {res}")
            return 0

        if args.acao == "anexar":
            if not args.arquivo:
                print("[ERRO] informe --arquivo")
                return 4
            if not os.path.exists(args.arquivo):
                print(f"[ERRO] arquivo nao encontrado: {args.arquivo}")
                return 4
            ext = os.path.splitext(args.arquivo)[1].lower()
            tam = os.path.getsize(args.arquivo)
            print(f"=== ANEXAR em op {args.op} | {'EXECUTAR' if args.executar else 'DRY-RUN'} ===")
            print(f"  arquivo: {args.arquivo}  ({tam} bytes, ext {ext})")
            if ext not in EXTS:
                print(f"  [ERRO] extensao nao aceita (use {', '.join(EXTS)})")
                return 4
            if tam > MAX_FILE:
                print(f"  [ERRO] excede o limite de {MAX_FILE} bytes")
                return 4
            if not args.executar:
                print("  [DRY-RUN] NADA enviado. Confira e rode com --executar.")
                return 0
            antes = len(listar_docs(s, args.op)[1])
            st, txt = anexar_doc(s, args.op, args.arquivo)
            depois_lst = listar_docs(s, args.op)[1]
            print(f"  >> POST status={st} | docs antes={antes} depois={len(depois_lst)}")
            if len(depois_lst) > antes:
                novo = depois_lst[0]
                print(f"  [OK] anexado: idDoc {novo['idDoc']} {novo['nome']} ({novo['data']})")
            else:
                print(f"  [?] contagem nao aumentou; trecho da resposta: {txt[:200].strip()}")
            return 0

        if args.acao == "excluir":
            if not args.iddoc:
                print("[ERRO] informe --iddoc")
                return 4
            print(f"=== EXCLUIR idDoc {args.iddoc} da op {args.op} | {'EXECUTAR' if args.executar else 'DRY-RUN'} ===")
            if not args.executar:
                print("  [DRY-RUN] NADA enviado. Rode com --executar p/ excluir.")
                return 0
            r = s.ctx.request.post(URL_POPUP, multipart={
                "Op": str(args.op), "Tipo": "OUT", "processar": "1",
                "deletar": "1", "docs": str(args.iddoc),
            }, timeout=60_000)
            print(f"  >> POST status={r.status}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
