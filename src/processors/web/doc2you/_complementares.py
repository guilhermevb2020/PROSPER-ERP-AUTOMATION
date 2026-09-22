# -*- coding: utf-8 -*-
"""Documentos COMPLEMENTARES (aba "Outros documentos" / ANEXAR DOCUMENTOS) de uma
operação no Smart — versão ASYNC p/ o robô do doc2you.

Mesma mecânica HTTP do robô de crédito (`credito/op_docs.py`), portada pro
contexto async do doc2you (que já está logado no Smart). Não estão no Doc2You —
ficam na própria operação, aba Outros documentos:

  listar  : GET /smart/operacao/popupdocumentos.php?Op=<op>&Tipo=OUT   (iso-8859-1)
            → <a onclick="viewDoc(<idDoc>)">NOME.pdf</a>
  resolver: GET /smart/operacao/viewdoc.php?idDoc=<id>  → <iframe src="documento.php/...">
  baixar  : GET <src do iframe>  → bytes (%PDF / imagem)

Destino: CADASTRO/LASTRO DAS OPERACOES/documentos complementares operacoes/<op>/<doc>
(via NextcloudWebDAV compartilhado). Skip-existing: só sobe o que ainda não está lá.
"""
import os
import re

SMART = os.getenv("DOC2YOU_SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
URL_POPUP = SMART + "/smart/operacao/popupdocumentos.php"
URL_VIEW = SMART + "/smart/operacao/viewdoc.php"

# <td>DATA</td> <td> <a ... onclick="viewDoc(ID)">NOME</a>
_RE_DOC = re.compile(
    r"(\d{2}/\d{2}/\d{4}[\d :]*)</td>\s*<td[^>]*>\s*<a[^>]*viewDoc\((\d+)\)[^>]*>([^<]+)</a>",
    re.I | re.S)
_RE_DOC_FB = re.compile(r"viewDoc\((\d+)\)[^>]*>([^<]+)</a>", re.I)
_RE_SRC = re.compile(r"src=['\"]([^'\"]+)['\"]")


def _nome_seguro(nome: str) -> str:
    return re.sub(r"[\\/]+", "_", (nome or "").strip()).strip() or "documento"


async def _get_text(ctx, url: str):
    """GET autenticado na sessão do robô; Smart responde iso-8859-1 (não utf-8)."""
    r = await ctx.request.get(url, timeout=30000)
    body = await r.body()
    return r.status, body.decode("iso-8859-1", errors="replace")


async def listar(ctx, op: str) -> list:
    """[{idDoc, nome, data}] dos anexos da operação (aba Outros documentos)."""
    _st, html = await _get_text(ctx, f"{URL_POPUP}?Op={op}&Tipo=OUT")
    docs = []
    for m in _RE_DOC.finditer(html):
        docs.append({"data": m.group(1).strip(), "idDoc": m.group(2),
                     "nome": m.group(3).strip()})
    if not docs:  # fallback: só os viewDoc, se o pareamento com a data falhar
        for m in _RE_DOC_FB.finditer(html):
            docs.append({"data": "", "idDoc": m.group(1), "nome": m.group(2).strip()})
    return docs


async def obter_bytes(ctx, id_doc: str, nome: str = None):
    """(bytes, nome_com_ext) do anexo; (None, motivo) em falha. Não grava em disco."""
    _st, html = await _get_text(ctx, f"{URL_VIEW}?idDoc={id_doc}")
    m = _RE_SRC.search(html)
    if not m:
        return None, f"iframe não encontrado (status {_st})"
    src = m.group(1)
    url = src if src.startswith("http") else SMART + src
    r = await ctx.request.get(url, headers={"referer": URL_VIEW}, timeout=60000)
    b = await r.body()
    ct = (r.headers or {}).get("content-type", "")
    if not (b[:4] == b"%PDF" or "pdf" in ct or "image" in ct):
        return None, f"conteúdo inesperado (ct={ct}, inicio={b[:8]!r})"
    ext = ".pdf" if b[:4] == b"%PDF" else (".png" if b[:4] == b"\x89PNG" else ".jpg")
    nome = nome or f"doc_{id_doc}{ext}"
    if not os.path.splitext(nome)[1]:
        nome += ext
    return b, nome


async def baixar_op(ctx, op: str, uploader, subbase: str = "documentos complementares operacoes"):
    """Baixa os anexos da operação que ainda NÃO estão no Nextcloud e os sobe.

    Skip-existing: lista o que já existe em <subbase>/<op>/ e só baixa/sobe o que
    falta (pasta inexistente = baixa tudo). Best-effort: nunca levanta exceção.
    Retorna (subidos, pulados, erros)."""
    op = str(op).strip()
    if not op or not op.isdigit():
        return 0, 0, 0
    try:
        docs = await listar(ctx, op)
    except Exception as e:
        print(f"  [complementar op {op}] erro ao listar: {type(e).__name__}: {e}", flush=True)
        return 0, 0, 1
    if not docs:
        return 0, 0, 0

    subpasta = f"{subbase}/{op}"
    existentes = uploader.listar_nomes(subpasta)  # set (vazio se pasta não existe)
    subidos = pulados = erros = 0
    for d in docs:
        nome = _nome_seguro(d.get("nome") or f"doc_{d.get('idDoc')}")
        if nome in existentes:  # já está lá — não re-baixa nem sobrescreve
            pulados += 1
            continue
        try:
            b, nome_final = await obter_bytes(ctx, d["idDoc"], nome)
            if b is None:
                print(f"  [complementar op {op}] '{nome}' falhou: {nome_final}", flush=True)
                erros += 1
                continue
            nome_final = _nome_seguro(nome_final)
            if nome_final in existentes:  # a extensão adicionada bateu com um já existente
                pulados += 1
                continue
            st = uploader.enviar(b, subpasta, nome_final)
            if st in (201, 204):
                subidos += 1
                print(f"  complementar -> {subpasta}/{nome_final} ({len(b)}B)", flush=True)
            else:
                erros += 1
                print(f"  [complementar op {op}] '{nome_final}': Nextcloud http {st}", flush=True)
        except Exception as e:
            erros += 1
            print(f"  [complementar op {op}] doc {d.get('idDoc')} erro: {type(e).__name__}: {e}", flush=True)
    if subidos or erros:
        print(f"  [complementar op {op}] {subidos} novo(s), {pulados} já existia(m), "
              f"{erros} erro(s)", flush=True)
    return subidos, pulados, erros
