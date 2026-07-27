# -*- coding: utf-8 -*-
"""
Logica core da EMISSAO de boletos no Smart.

emitir_conta_http(ctx, conta_value, conta_label, grupo, dry_run) -> dict

Fluxo (3 POSTs):
  1) GET  URL_FORM_HTTP                          -> pega HTML do form Financeiro
  2) POST URL_LISTA_HTTP (lista titulos)         -> lista pendentes (ids)
  3) POST URL_PRINT_HTTP (printcobrancapdf)      -> manda imprimir (so se nao dry_run)

Reusa ctx.request do Playwright (sessao viva no CDP) — mesmo padrao do envio.
NAO depende de browser visivel; tudo via cookies/HTTP da sessao autenticada.
"""

from __future__ import annotations

from urllib.parse import urlencode

from src.processors.web.boletos import _emissao_config as ec
from src.processors.web.boletos._emissao_html import (
    fields_from_form,
    ids_dos_titulos,
    options_dropdown,
    override_fields,
    text_response,
)


def listar_contas_dropdown(ctx) -> list[tuple[str, str]]:
    """Le dropdown contaCorrente direto do form HTTP (mais rapido que Playwright).

    Retorna [(value, label)] excluindo 'Selecione a conta' e 'Titulos sem conta'.
    """
    r = ctx.request.get(ec.URL_FORM_HTTP, timeout=60_000)
    if r.status != 200:
        raise RuntimeError(f"GET impriboleto.php falhou: HTTP {r.status}")
    html = text_response(r)
    opts = options_dropdown(html, "contaCorrente")
    out: list[tuple[str, str]] = []
    for value, label in opts:
        label_lower = label.lower().strip()
        if not label or not value or value == "0":
            continue
        # mesmos placeholders do envio (titulos sem conta etc.)
        if any(ph in label_lower for ph in ec.CONTAS_PLACEHOLDER):
            continue
        out.append((value, label))
    return out


def emitir_conta_http(
    ctx,
    *,
    conta_value: str,
    conta_label: str,
    grupo: str,
    dry_run: bool = True,
    num_doc: str | None = None,
    nop: str | None = None,
) -> dict:
    """Roda 1 passada de emissao em UMA conta. Retorna dict com resultado.

    Estrutura do dict retornado:
        ok            : bool         (False = falha tecnica; True = read-only ou OK)
        dry           : bool         (True se nao chegou a POST de print)
        vazio         : bool         (True se 0 titulos pendentes na lista)
        titulos       : int          (qtd de checkImpressao detectados)
        ids           : list[str]    (IDs dos titulos)
        content_type  : str          (CT do response do print, se houver)
        pdf           : bool         (True se response do print eh PDF)
        erro          : str | None
        conta         : str (label)
        grupo         : str
    """
    cfg_grupo = ec.CONFIG_GRUPO[grupo]
    api = ctx.request

    # 1) GET form
    r1 = api.get(ec.URL_FORM_HTTP, timeout=60_000)
    if r1.status != 200:
        return {
            "ok": False, "conta": conta_label, "grupo": grupo,
            "erro": f"GET form: HTTP {r1.status}",
            "titulos": 0, "ids": [], "dry": True,
        }
    html_form = text_response(r1)
    fields_fin = fields_from_form(html_form, "Financeiro")
    if not fields_fin:
        return {
            "ok": False, "conta": conta_label, "grupo": grupo,
            "erro": "form 'Financeiro' nao encontrado no HTML",
            "titulos": 0, "ids": [], "dry": True,
        }

    # Overrides do form Financeiro
    # Filtro CIRURGICO opcional (emissao avulsa por titulo): NumDocumento + nop1/nop2 narram
    # a listagem ao titulo especifico (o endpoint honra, igual ao envio). override_fields
    # ADICIONA as chaves se nao existirem. A classe (sClasseRisco[]) continua excluindo o
    # que nao deve ser emitido (ex.: comissaria fora do set do grupo).
    filtros: dict[str, str] = {}
    if num_doc:
        filtros["NumDocumento"] = str(num_doc)
    if nop:
        filtros["nop1"] = str(nop)
        filtros["nop2"] = str(nop)
    fields_fin = override_fields(
        fields_fin,
        contaCorrente=str(conta_value),
        ImprimirBoletoEmNome=cfg_grupo["radio"],
        **{"sClasseRisco[]": list(cfg_grupo["classes"])},
        modalidadeS=ec.MODALIDADE_EMISSAO,
        **filtros,
    )
    body = urlencode(fields_fin, doseq=False)

    # 2) POST lista
    r2 = api.post(ec.URL_LISTA_HTTP, data=body, headers=ec.HDR_FORM, timeout=120_000)
    if r2.status != 200:
        return {
            "ok": False, "conta": conta_label, "grupo": grupo,
            "erro": f"POST lista: HTTP {r2.status}",
            "titulos": 0, "ids": [], "dry": True,
        }
    html_lista = text_response(r2)
    ids = ids_dos_titulos(html_lista)
    n = len(ids)

    # Dry-run: para aqui (read-only)
    if dry_run:
        return {
            "ok": True, "dry": True, "vazio": (n == 0),
            "conta": conta_label, "grupo": grupo,
            "titulos": n, "ids": ids,
            "classes": cfg_grupo["classes"],
            "radio": cfg_grupo["radio"],
        }

    # Vazio: nada a emitir
    if n == 0:
        return {
            "ok": True, "dry": False, "vazio": True,
            "conta": conta_label, "grupo": grupo,
            "titulos": 0, "ids": [],
            "classes": cfg_grupo["classes"],
            "radio": cfg_grupo["radio"],
        }

    # 3) POST print (emite de verdade)
    fields_lista = fields_from_form(html_lista, "ListaTitulosBoletos")
    if not fields_lista:
        return {
            "ok": False, "conta": conta_label, "grupo": grupo,
            "erro": "form 'ListaTitulosBoletos' nao encontrado",
            "titulos": n, "ids": ids, "dry": True,
        }
    checks = "+".join(ids) + "+"
    fields_lista = override_fields(
        fields_lista,
        Checks=checks,
        **ec.POST_PRINT_OVERRIDES,
    )
    body2 = urlencode(fields_lista, doseq=False)
    hdr2 = dict(ec.HDR_FORM)
    hdr2["Referer"] = ec.URL_LISTA_HTTP
    r3 = api.post(ec.URL_PRINT_HTTP, data=body2, headers=hdr2, timeout=180_000)
    if r3.status != 200:
        return {
            "ok": False, "conta": conta_label, "grupo": grupo,
            "erro": f"POST print: HTTP {r3.status}",
            "titulos": n, "ids": ids, "dry": False,
        }
    ct = (r3.headers.get("content-type") or "").lower()
    return {
        "ok": True, "dry": False, "vazio": False,
        "conta": conta_label, "grupo": grupo,
        "titulos": n, "ids": ids,
        "classes": cfg_grupo["classes"],
        "radio": cfg_grupo["radio"],
        "content_type": ct,
        "pdf": ("pdf" in ct),
    }


def emitir_por_documento(ctx, *, num_doc: str, nop: str | None = None,
                         dry_run: bool = True) -> dict:
    """Emissao CIRURGICA de UM titulo por NumDocumento (+NOP), fail-closed.

    Varre as contas listando (dry) so o que casa NumDocumento+NOP e SO emite se o total
    de pendentes for EXATAMENTE 1 (protege contra NumDocumento colidido entre cedentes —
    mesma logica do EXIGIR_UNICO do envio; NOP escopa o cedente). A classe do grupo
    continua excluindo o que nao deve ser emitido.

    Retorna dict com ``status`` in {nao_unico, seria_emitido (dry), emitido, erro_emissao}.
    """
    contas = listar_contas_dropdown(ctx)
    achados: list[tuple[str, str, str, list[str]]] = []  # (conta_value, label, grupo, ids)
    for value, label in contas:
        grupo = ec.classificar_conta(label)
        try:
            r = emitir_conta_http(
                ctx, conta_value=value, conta_label=label, grupo=grupo,
                dry_run=True, num_doc=num_doc, nop=nop,
            )
        except Exception as e:  # noqa: BLE001
            return {"status": "erro_emissao", "total": None, "erro": f"{label}: {e}"}
        if r.get("ok") and r.get("titulos", 0) > 0:
            achados.append((value, label, grupo, r["ids"]))

    total = sum(len(ids) for _, _, _, ids in achados)
    resumo = [(l, len(i)) for _, l, _, i in achados]
    if total != 1:
        # 0 = nunca emitido/nao encontrado; >1 = ambiguo (doc colidido) -> NAO emite
        return {"status": "nao_unico", "total": total, "achados": resumo}
    if dry_run:
        return {"status": "seria_emitido", "total": 1, "conta": achados[0][1]}

    value, label, grupo, _ids = achados[0]
    r = emitir_conta_http(
        ctx, conta_value=value, conta_label=label, grupo=grupo,
        dry_run=False, num_doc=num_doc, nop=nop,
    )
    ok = bool(r.get("ok")) and not r.get("erro")
    return {
        "status": "emitido" if ok else "erro_emissao",
        "total": 1, "conta": label, "pdf": r.get("pdf"), "erro": r.get("erro"),
    }
