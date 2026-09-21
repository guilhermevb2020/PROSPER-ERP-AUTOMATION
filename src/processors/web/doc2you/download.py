# -*- coding: utf-8 -*-
"""Listagem + download dos documentos do Doc2You (ASYNC).

Portado do `baixar_documentos.py` standalone, convertido para async
(`await context.request.*`). O `context` aqui e o BrowserContext do Playwright
async; suas requisicoes (`context.request`) carregam os cookies da sessao logada
(Smart -> Doc2You SSO), entao funcionam sem reabrir o browser por documento.
"""
import asyncio
import base64
import io
import re
import zipfile

from . import classificar as C

DOC2YOU = "https://www.doc2you.com.br"
URL_DOCUMENTOS = DOC2YOU + "/documento/documentos"
URL_VISUALIZAR = DOC2YOU + "/documento/visualizar/0/D/"
URL_DOWNLOAD = DOC2YOU + "/documento/download/0/D/"
RE_CPFCNPJ = re.compile(r"id=['\"]cpfCnpj['\"][^>]*?value=['\"]([^'\"]+)['\"]", re.I)
RE_PDF_URL = re.compile(r"(?:https?://[^\"'\s]+)?/documentos/L\d+/M\d+/[^\"'\s?]+\.pdf", re.I)
MIN_PDF_BYTES = 1024


def _b64(s) -> str:
    return base64.b64encode(str(s).encode()).decode()


def _pdf_de(corpo: bytes) -> bytes:
    """O download vem como ZIP de 1 arquivo ou PDF cru."""
    if corpo[:2] == b"PK":
        zf = zipfile.ZipFile(io.BytesIO(corpo))
        nomes = [n for n in zf.namelist() if n.lower().endswith(".pdf")] or zf.namelist()
        return zf.read(nomes[0]) if nomes else corpo
    return corpo


def _filtros_b64(chk, data_ini, data_fim) -> str:
    filtros = ('{"page":"0","dataInicio":"%s","dataFinal":"%s","dataEmissaoIni":"",'
               '"dataEmissaoFim":"","dataVencimentoIni":"","dataVencimentoFim":"",'
               '"tipoDocumento":"","docParte":"","papel":"","numOperacao":"",'
               '"numDocumento":"","statusDocumento":"","docCedente":"","nomeCedente":"",'
               '"idCedente":""}') % (data_ini, data_fim or data_ini)
    return _b64(f"{chk}&filtrosAplicados={filtros}")


async def sessao_valida(context) -> bool:
    try:
        r = await context.request.get(URL_DOCUMENTOS, timeout=30000)
        return bool(RE_CPFCNPJ.search(await r.text()))
    except Exception:
        return False


async def listar_documentos(context, data_ini, data_fim, status_doc="C",
                            max_paginas=200, pagina_inicial=1, num_operacao="",
                            logger=None) -> list:
    """Pagina e devolve TODOS os documentos do periodo (1-indexada).

    num_operacao: quando informado, filtra a listagem por uma operacao especifica
    (campo numOperacao do Doc2You) — usado no retry de pendencias para recuperar
    so os docs daquela operacao, independente de qual data eles carregam."""
    def _log(msg):
        (logger.log if logger else print)(msg)

    todos, vistos_chk = [], set()
    page = max(1, pagina_inicial)
    while page <= max_paginas:
        form = {"page": str(page), "dataInicio": data_ini, "dataFinal": data_fim,
                "dataEmissaoIni": "", "dataEmissaoFim": "", "dataVencimentoIni": "",
                "dataVencimentoFim": "", "tipoDocumento": "", "docParte": "", "papel": "",
                "numOperacao": str(num_operacao or ""), "numDocumento": "",
                "statusDocumento": status_doc,
                "docCedente": "", "nomeCedente": "", "idCedente": ""}
        r = await context.request.post(
            URL_DOCUMENTOS, form=form,
            headers={"referer": URL_DOCUMENTOS, "origin": DOC2YOU}, timeout=60000)
        html = await r.text()
        docs = C.parse_listagem(html)
        if status_doc:
            docs = [d for d in docs if d.get("status", "") == status_doc]
        novos = [d for d in docs if d["chk"] not in vistos_chk]
        for d in novos:
            vistos_chk.add(d["chk"])
        todos.extend(novos)
        _log(f"[pag {page}] {len(docs)} doc(s), {len(novos)} novo(s) (acumulado {len(todos)})")
        if not docs or not novos:
            break
        page += 1
    return todos


async def _pdf_via_visualizar(context, chk, data_ini=None, data_fim=None) -> bytes:
    """Caminho do 'clicar no nome' (confiavel): visualizador -> URL do PDF cru."""
    b64s = []
    if data_ini:
        b64s.append(_filtros_b64(chk, data_ini, data_fim))
    b64s.append(_b64(chk))
    for b in b64s:
        try:
            vis = URL_VISUALIZAR + b
            rv = await context.request.get(vis, headers={"referer": URL_DOCUMENTOS}, timeout=60000)
            if rv.status != 200:
                continue
            m = RE_PDF_URL.search(await rv.text())
            if not m:
                continue
            url = m.group(0)
            if not url.lower().startswith("http"):
                url = DOC2YOU + url
            rp = await context.request.get(url, headers={"referer": vis}, timeout=120000)
            body = await rp.body()
            if rp.status == 200 and len(body) >= MIN_PDF_BYTES:
                return body
        except Exception:
            continue
    return b""


async def baixar_documento(context, chk: str, data_ini=None, data_fim=None, tentativas=4) -> bytes:
    """2 metodos: download direto (rapido) -> visualizador (confiavel). NUNCA salva 0 byte."""
    for t in range(tentativas):
        try:
            r = await context.request.get(URL_DOWNLOAD + _b64(chk),
                                          headers={"referer": URL_DOCUMENTOS}, timeout=120000)
            if r.status == 200:
                p = _pdf_de(await r.body())
                if len(p) >= MIN_PDF_BYTES:
                    return p
        except Exception:
            pass
        pdf = await _pdf_via_visualizar(context, chk, data_ini, data_fim)
        if pdf:
            return pdf
        await asyncio.sleep(0.6 * (t + 1))
    raise RuntimeError(f"download falhou (2 metodos) apos {tentativas} tentativas")


def resolver_cnpj(d: dict, pdf: bytes) -> str:
    """CNPJ que entra no nome: sacado (carta/letra) ou cedente (contrato mae)."""
    tipo = d["tipo"]
    if tipo in C.TIPOS_COM_SACADO:
        return C.cnpj_sacado(d, pdf)
    if tipo == "contrato_master":
        return C.cnpj_cedente_do_pdf(pdf)
    return ""
