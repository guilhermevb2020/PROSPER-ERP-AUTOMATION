# -*- coding: utf-8 -*-
"""Classificacao, parsing da listagem e renome dos documentos do Doc2You.

Portado VERBATIM do robô standalone (apenas trocado `import config` por uma
constante de ambiente). A LISTAGEM (POST /documento/documentos) traz 1 linha por
documento + uma linha escondida <tr id='partes<CHK>'> com a sub-tabela das partes.
Como ha TABELA ANINHADA, o parser fatia por ancora.

Regras de nome:
  aditivo          -> "Aditivo <operacao>"
  nota_promissoria -> "Nota Promissoria <operacao>"
  duplicata        -> "Duplicata <operacao> <nota>"
  carta_cessao     -> "Carta de Cessao <operacao> <cnpj_sacado>"   (CNPJ lido do PDF)
  letra_cambio     -> "Letra de Cambio <operacao> <cnpj_sacado>"
  contrato_master  -> "Contrato Mae <cnpj_cedente>"
  recibo           -> "Recibo <operacao>"
"""
import io
import os
import re
import unicodedata

# CNPJ da SECURITIZADORA (a propria licenca) — usado pra NAO confundir com o CNPJ do
# cedente/sacado ao ler de dentro do PDF. Default = Prosper Vetor (troque via env).
SECURITIZADORA_CNPJ = os.getenv("DOC2YOU_SECURITIZADORA_CNPJ", "37.557.110/0001-69")

# subpasta por tipo (decisao do usuario: "pasta por tipo")
PASTA_TIPO = {
    "aditivo": "Aditivos",
    "nota_promissoria": "Notas Promissorias",
    "duplicata": "Duplicatas",
    "carta_cessao": "Cartas de Cessao",
    "letra_cambio": "Letras de Cambio",
    "contrato_master": "Contratos Mae",
    "recibo": "Recibos",
    "outro": "Outros",
}

# tipos cujo nome leva o CNPJ do SACADO (carta de cessao e letra de cambio)
TIPOS_COM_SACADO = ("carta_cessao", "letra_cambio")

RE_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
RE_MAIN = re.compile(r"name='chk'\s+id='chk\d+'\s+value='(\d+)'", re.I)
RE_PARTES = re.compile(r"id='partes(\d+)'", re.I)
RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")

# papeis das PARTES que representam o sacado/devedor (letra: ele aceita/assina)
PAPEIS_SACADO = ("sacado", "aceitante", "devedor")
# operacao-placeholder das linhas de Contrato Mae (contrato do cedente, sem operacao)
OP_CONTRATO_MAE = "2147483647"


# ---------------------------------------------------------------- utils
def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c))


def _limpa(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).replace("\xa0", " ").strip()


def nome_seguro(nome: str) -> str:
    """Tira acentos, o que o filesystem nao aceita, e troca ESPACOS por '_'."""
    nome = _sem_acento(nome)
    nome = re.sub(r'[\\/:*?"<>|]', "", nome)
    nome = re.sub(r"\s+", "_", nome.strip())
    return nome.strip("_")


# ---------------------------------------------------------------- tipo real
def tipo_real(td3: str, td6: str) -> str:
    t = _sem_acento(td3 or "").lower()
    d = _sem_acento(td6 or "").lower()
    if "contrato master" in t or "contrato master" in d:
        return "contrato_master"
    if "letra de cambio" in t or "letra de cambio" in d or "letra cambio" in (t + " " + d):
        return "letra_cambio"
    if "duplicata" in t:
        return "duplicata"
    if "nota promiss" in t:
        return "nota_promissoria"
    if "recibo" in t or "recibo" in d:
        return "recibo"
    if "aditivo de secur" in d or d.startswith("aditivo"):
        return "aditivo"
    if "carta de cess" in d:
        return "carta_cessao"
    if "nota promiss" in d:
        return "nota_promissoria"
    if "duplicata" in d:
        return "duplicata"
    return "outro"


# ---------------------------------------------------------------- listagem -> linhas
def max_pagina(html: str):
    """Le o maior numero da barra <ul class='pagination'> (data-page='N'), ou None."""
    m = re.search(r"<ul[^>]*class=['\"][^'\"]*pagination[^'\"]*['\"][^>]*>(.*?)</ul>",
                  html, re.I | re.S)
    if not m:
        return None
    nums = [int(x) for x in re.findall(r"data-page=['\"](\d+)['\"]", m.group(1))]
    return max(nums) if nums else None


def parse_listagem(html: str) -> list:
    """Devolve [{chk, tipo, operacao, nota, cedente, descricao, status, partes}].
    partes = [(papel, cnpj, nome)]. Fatia por ancora (tabela aninhada)."""
    mains = [(m.start(), m.group(1)) for m in RE_MAIN.finditer(html)]
    partes_pos = {m.group(1): m.start() for m in RE_PARTES.finditer(html)}
    docs = []
    for i, (pos, chk) in enumerate(mains):
        mstart = html.rfind("<tr", 0, pos)
        prox_main = mains[i + 1][0] if i + 1 < len(mains) else len(html)
        pstart = partes_pos.get(chk, prox_main)
        main_html = html[mstart:pstart]
        nxt = html.rfind("<tr", 0, prox_main) if i + 1 < len(mains) else len(html)
        partes_html = html[pstart:nxt]

        tds = [_limpa(t) for t in RE_TD.findall(main_html)]
        if len(tds) < 13:
            continue
        td3, td5, td6 = tds[3], tds[5], tds[6]
        partes = []
        for r in re.findall(r"<tr\b[^>]*>(.*?)</tr>", partes_html, re.S):
            c = [_limpa(x) for x in RE_TD.findall(r)]
            if len(c) >= 6 and c[1] and re.search(r"\d", c[1]):
                partes.append((c[5], c[1], c[0]))   # papel, cnpj, nome
        operacao = tds[11].strip() if len(tds) > 11 else ""
        tipo = tipo_real(td3, td6)
        if tipo == "outro" and operacao == OP_CONTRATO_MAE:
            tipo = "contrato_master"
        ms = re.search(r"data-statusdocumento=['\"]([^'\"]*)['\"]", main_html)
        docs.append({
            "chk": chk,
            "tipo": tipo,
            "operacao": operacao,
            "nota": tds[12].strip() if len(tds) > 12 else "",
            "cedente": td5,
            "descricao": td6,
            "status": ms.group(1) if ms else "",
            "partes": partes,
        })
    return docs


# ---------------------------------------------------------------- CNPJ (do PDF)
def texto_pdf(pdf_bytes: bytes, paginas: int = 2) -> str:
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join((p.extract_text() or "") for p in r.pages[:paginas])
    except Exception:
        return ""


def cnpj_sacado_do_pdf(pdf_bytes: bytes) -> str:
    """Carta de cessao: o SACADO e o destinatario no topo ('A <nome> CNPJ/CPF: ...')."""
    txt = texto_pdf(pdf_bytes, 1)
    m = re.search(r"CNPJ\s*/?\s*CPF\s*:?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2})",
                  txt, re.I)
    if m:
        return m.group(1)
    for mm in RE_CNPJ.finditer(txt):
        if mm.group(0) != SECURITIZADORA_CNPJ:
            return mm.group(0)
    return ""


def cnpj_sacado(doc: dict, pdf_bytes: bytes = b"") -> str:
    """CNPJ do sacado p/ carta de cessao e letra de cambio.
    1) tenta nas PARTES (papel Sacado/Aceitante/Devedor); 2) senao, le do PDF."""
    for papel, cnpj, _nome in doc.get("partes", []):
        p = _sem_acento(papel).lower()
        if any(k in p for k in PAPEIS_SACADO) and cnpj:
            return cnpj
    return cnpj_sacado_do_pdf(pdf_bytes)


def cnpj_cedente_do_pdf(pdf_bytes: bytes) -> str:
    """Contrato Mae: o cedente e a '1a ALIENANTE (SECURITIZADO)' no topo do PDF."""
    txt = texto_pdf(pdf_bytes, 2)
    for mm in RE_CNPJ.finditer(txt):
        if mm.group(0) != SECURITIZADORA_CNPJ:
            return mm.group(0)
    return ""


# ---------------------------------------------------------------- nome final
def nome_final(tipo: str, operacao: str = "", nota: str = "", cnpj_sacado: str = "") -> str:
    op = (operacao or "").strip()
    if tipo == "aditivo":
        base = f"Aditivo {op}"
    elif tipo == "nota_promissoria":
        base = f"Nota Promissoria {op}"
    elif tipo == "duplicata":
        base = f"Duplicata {op} {nota}".rstrip()
    elif tipo == "carta_cessao":
        cnpj = (cnpj_sacado or "").replace("/", "-")
        base = f"Carta de Cessao {op} {cnpj}".rstrip()
    elif tipo == "letra_cambio":
        cnpj = (cnpj_sacado or "").replace("/", "-")
        base = f"Letra de Cambio {op} {cnpj}".rstrip()
    elif tipo == "contrato_master":
        cnpj = (cnpj_sacado or "").replace("/", "-")   # aqui = CNPJ do cedente
        base = f"Contrato Mae {cnpj}".rstrip()
    elif tipo == "recibo":
        base = f"Recibo {op}"
    else:
        base = f"Documento {op}".rstrip()
    return nome_seguro(base)
