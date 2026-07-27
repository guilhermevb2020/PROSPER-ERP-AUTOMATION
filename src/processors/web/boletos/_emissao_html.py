# -*- coding: utf-8 -*-
"""
Parsers HTML do form Smart usados pela emissao de boletos.

O Smart entrega o form em HTML CP1252 com inputs/select/textarea misturados.
Em vez de Playwright (lento + abre frames), parseamos o HTML cru com regex
(igual o robo local original — comprovado em producao).

Funcoes principais (chamadas pelo _emissao_core):
- text_response(resp)        -> str   (decoda response Smart usando CP1252)
- form_block(html, nome)     -> str   (extrai bloco <form name="X">...</form>)
- fields_from_form(html, X)  -> list[(name, value)]  (todos os campos do form)
- override_fields(fields,**) -> list  (substitui/adiciona campos antes do POST)
- ids_dos_titulos(html)      -> list[str]  (IDs dos checkImpressao na listagem)
- options_dropdown(html, X)  -> list[(value, texto)]  (opcoes de <select>)
"""

from __future__ import annotations

import html as _htmllib
import re

# regex de atributos HTML: nome="valor" / nome='valor' / nome=valor / nome (flag)
_RE_ATTR = re.compile(
    r"""([a-zA-Z][\w-]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+)))?"""
)


def text_response(resp) -> str:
    """Decoda body do response Smart (CP1252) — analogo ao _text_response do robo local."""
    body = resp.body() if callable(resp.body) else resp.body
    ct = (resp.headers.get("content-type") or "").lower() if hasattr(resp, "headers") else ""
    m = re.search(r"charset=([\w-]+)", ct)
    enc = (m.group(1) if m else None) or "cp1252"
    try:
        return body.decode(enc, errors="replace")
    except LookupError:
        return body.decode("cp1252", errors="replace")


def _attrs(s: str) -> dict:
    """Decompoe atributos de uma tag HTML em dict."""
    out = {}
    for m in _RE_ATTR.finditer(s):
        v = m.group(2) or m.group(3) or m.group(4) or ""
        out[m.group(1).lower()] = v
    return out


def form_block(html_text: str, form_name: str) -> str | None:
    """Extrai o conteudo entre <form name="X">...</form> (case-insensitive)."""
    m = re.search(
        rf'<form\s+[^>]*name=["\']{re.escape(form_name)}["\'][^>]*>(.*?)</form>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    return m.group(1) if m else None


def fields_from_form(html_text: str, form_name: str) -> list[tuple[str, str]]:
    """Retorna [(name, value)] de todos os campos do form indicado.

    Inclui inputs (text/hidden/checkbox-checked/radio-checked), selects
    (com value selected ou primeiro option) e textareas.
    """
    body = form_block(html_text, form_name)
    if body is None:
        return []
    out: list[tuple[str, str]] = []

    # <input ... />
    for m in re.finditer(r"<input\s+([^>]+?)/?>", body, re.IGNORECASE):
        a = _attrs(m.group(1))
        name = a.get("name")
        if not name:
            continue
        typ = (a.get("type") or "text").lower()
        if typ in ("submit", "button", "image", "reset", "file"):
            continue
        # Checkboxes/radios so contam se marcados
        if typ in ("checkbox", "radio") and "checked" not in a:
            continue
        out.append((name, _htmllib.unescape(a.get("value", ""))))

    # <select> — pega option selected ou primeiro
    for sm in re.finditer(r"<select\s+([^>]+?)>(.*?)</select>", body,
                          re.IGNORECASE | re.DOTALL):
        a = _attrs(sm.group(1))
        name = a.get("name")
        if not name:
            continue
        opts = list(re.finditer(r"<option\s*([^>]*)>([^<]*)</option>",
                                sm.group(2), re.IGNORECASE))
        if not opts:
            continue
        chosen = None
        for o in opts:
            oa = _attrs(o.group(1))
            if "selected" in oa:
                chosen = oa.get("value", _htmllib.unescape(o.group(2)))
                break
        if chosen is None:
            # default: primeiro option
            o0 = opts[0]
            chosen = _attrs(o0.group(1)).get("value", _htmllib.unescape(o0.group(2)))
        out.append((name, chosen))

    # <textarea>
    for tm in re.finditer(r"<textarea\s+([^>]+?)>(.*?)</textarea>", body,
                          re.IGNORECASE | re.DOTALL):
        a = _attrs(tm.group(1))
        if a.get("name"):
            out.append((a["name"], _htmllib.unescape(tm.group(2))))

    return out


def override_fields(fields: list[tuple[str, str]], **changes) -> list[tuple[str, str]]:
    """Substitui valores no list-of-tuples e anexa novos (mantem ordem).

    Para listas/tuplas em changes, gera multiplas entradas (ex.: sClasseRisco[]).
    """
    drop = set(changes.keys())
    kept = [(k, v) for k, v in fields if k not in drop]
    extra: list[tuple[str, str]] = []
    for k, v in changes.items():
        if isinstance(v, (list, tuple)):
            for vi in v:
                extra.append((k, str(vi)))
        else:
            extra.append((k, str(v)))
    return kept + extra


def ids_dos_titulos(html_text: str) -> list[str]:
    """Extrai IDs unicos dos <input name='checkImpressao' type='checkbox' value='X'>.

    Usado para descobrir quais titulos a 1a passada conseguiu emitir.
    """
    ids: list[str] = []
    for m in re.finditer(r'<input\s+([^>]+?)/?>', html_text, re.IGNORECASE):
        a = _attrs(m.group(1))
        if a.get("name") == "checkImpressao" and (a.get("type", "").lower() == "checkbox"):
            v = (a.get("value") or "").strip()
            if v:
                ids.append(v)
    # deduplica preservando ordem
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def options_dropdown(html_text: str, select_name: str) -> list[tuple[str, str]]:
    """Le opcoes do <select name='X'> dentro do form Financeiro.

    Retorna [(value, texto)] — usado para listar contaCorrente quando se
    quer rotear pela API HTTP sem usar Playwright (mais leve).
    """
    fm = form_block(html_text, "Financeiro") or html_text
    m = re.search(
        rf'<select\s+[^>]*name=["\']{re.escape(select_name)}["\'][^>]*>(.*?)</select>',
        fm,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    body = m.group(1)
    out: list[tuple[str, str]] = []
    for om in re.finditer(r"<option\s*([^>]*)>([^<]*)</option>", body, re.IGNORECASE):
        a = _attrs(om.group(1))
        out.append((a.get("value", ""), _htmllib.unescape(om.group(2)).strip()))
    return out
