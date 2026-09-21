#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnostico_nome_boleto.py - QUEM sai no campo "Beneficiario" do boleto?

A pergunta que este script responde, com PDF na mao em vez de deducao:

  1) o `ImprimirBoletoEmNome` que mandamos no POST de LISTAGEM chega ao PDF,
     ou o POST de IMPRESSAO ignora e usa o default do Smart?
  2) o que o valor `r` imprime? E o valor que os templates do ENVIO carregam
     (`ImprimirBoletoEmNome=r` em listatitulos.txt, `BoletoEmNome=r` em
     envio.txt) e ninguem sabe o que significa.

COMO: para UM titulo, repete SO o POST de impressao variando o parametro do
nome, e SALVA cada resposta em disco. Abrindo os PDFs lado a lado ve-se qual
nome cada valor produz — que e a prova que o log de hoje nao consegue dar
(a emissao nao guarda os ids nem o PDF).

SEGURANCA — leia antes de rodar:
  * Sem `--confirmar` ele so LISTA. Nenhum POST de impressao e disparado.
  * `NumEmail=0` e `imprimirMultiplos=0` em todos os POSTs: nao dispara e-mail
    para sacado nenhum.
  * Fail-closed: recusa se a listagem trouxer != 1 titulo, para nao imprimir
    lote inteiro sem querer (use `--todos` para forcar, ciente do que faz).
  * ⚠️ O POST de impressao e o mesmo que EMITE. Num titulo que JA TEM boleto
    ele gera 2a via (inofensivo). Num titulo nunca emitido, ele EMITE. Por
    isso o script mostra o titulo e exige `--confirmar` em passo separado.

USO (dentro do container, onde vive a sessao do Chrome):

    # 1) so olhar qual titulo o filtro pega (nao imprime nada)
    docker exec erp-automation python /app/scripts/diagnostico_nome_boleto.py \\
        --conta 290 --num-doc 15652-001

    # 2) imprimir e salvar os PDFs, um por valor do parametro
    docker exec erp-automation python /app/scripts/diagnostico_nome_boleto.py \\
        --conta 290 --num-doc 15652-001 --confirmar

Saida: /app/data/boletos/diagnostico/<AAAA-MM-DD_HHMMSS>/
    <num_doc>_<valor>.pdf     um por valor testado (f, c, r)
    manifesto.json            o que foi enviado e o que voltou
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

from src.processors.web.boletos import _config as cfg
from src.processors.web.boletos import _emissao_config as ec
from src.processors.web.boletos._emissao_html import (
    fields_from_form,
    ids_dos_titulos,
    override_fields,
    text_response,
)
from src.processors.web.boletos._sessao import esta_logado, login_automatico_capsolver

# Os tres valores conhecidos do radio. `f` e `c` sao os que a emissao usa;
# `r` e o que os templates do envio carregam e ninguem documentou.
NOMES_PADRAO = ["f", "c", "r"]

SAIDA_BASE = os.environ.get("DIAG_SAIDA", "/app/data/boletos/diagnostico")


def log(msg: str = "") -> None:
    print(msg, flush=True)


def _conectar(p):
    """Reusa o Chrome vivo dos boletos (CDP 9222). Loga se a sessao caiu."""
    browser = p.chromium.connect_over_cdp(cfg.CDP_URL)
    ctx = browser.contexts[0]
    log(f"  conectado na sessao viva via CDP ({cfg.CDP_URL})")
    if not esta_logado(ctx):
        log("  sessao caida -> login automatico via CapSolver")
        if not login_automatico_capsolver(ctx):
            raise RuntimeError("login automatico falhou; logue via VNC (:99)")
        log("  login OK")
    return ctx


def listar(ctx, *, conta_value: str, conta_label: str, num_doc: str, nop: str | None):
    """POST de listagem. Devolve (html_da_lista, ids, grupo)."""
    grupo = ec.classificar_conta(conta_label)
    cfg_grupo = ec.CONFIG_GRUPO[grupo]

    r1 = ctx.request.get(ec.URL_FORM_HTTP, timeout=60_000)
    if r1.status != 200:
        raise RuntimeError(f"GET form: HTTP {r1.status}")
    fields = fields_from_form(text_response(r1), "Financeiro")
    if not fields:
        raise RuntimeError("form 'Financeiro' nao encontrado")

    filtros: dict[str, str] = {}
    if num_doc:
        filtros["NumDocumento"] = num_doc
    if nop:
        filtros["nop1"] = nop
        filtros["nop2"] = nop

    fields = override_fields(
        fields,
        contaCorrente=str(conta_value),
        ImprimirBoletoEmNome=cfg_grupo["radio"],
        **{"sClasseRisco[]": list(cfg_grupo["classes"])},
        modalidadeS=ec.MODALIDADE_EMISSAO,
        **filtros,
    )
    r2 = ctx.request.post(ec.URL_LISTA_HTTP, data=urlencode(fields, doseq=False),
                          headers=ec.HDR_FORM, timeout=120_000)
    if r2.status != 200:
        raise RuntimeError(f"POST lista: HTTP {r2.status}")
    html = text_response(r2)
    return html, ids_dos_titulos(html), grupo


def imprimir(ctx, html_lista: str, ids: list[str], nome: str):
    """POST de impressao com UM valor de nome. Devolve (bytes, content_type, body).

    Manda o parametro nas DUAS grafias — `ImprimirBoletoEmNome` (tela de
    emissao) e `BoletoEmNome` (tela de envio) — porque hoje o POST de
    impressao do robo nao reaplica nenhuma das duas: ele so reenvia o que o
    form `ListaTitulosBoletos` devolveu. Se o PDF mudar conforme este valor,
    esta provado que reaplicar resolve.
    """
    fields = fields_from_form(html_lista, "ListaTitulosBoletos")
    if not fields:
        raise RuntimeError("form 'ListaTitulosBoletos' nao encontrado")
    fields = override_fields(
        fields,
        Checks="+".join(ids) + "+",
        ImprimirBoletoEmNome=nome,
        BoletoEmNome=nome,
        **ec.POST_PRINT_OVERRIDES,   # boleto=1, carne=0, NumEmail=0, imprimirMultiplos=0
    )
    body = urlencode(fields, doseq=False)
    hdr = dict(ec.HDR_FORM)
    hdr["Referer"] = ec.URL_LISTA_HTTP
    r = ctx.request.post(ec.URL_PRINT_HTTP, data=body, headers=hdr, timeout=180_000)
    ct = (r.headers.get("content-type") or "").lower()
    return r.body(), ct, body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conta", required=True, help="id da conta no dropdown (ex.: 290)")
    ap.add_argument("--conta-label", default="", help="label da conta; se vazio, busca no dropdown")
    ap.add_argument("--num-doc", default="", help="NumDocumento do titulo (ex.: 15652-001)")
    ap.add_argument("--nop", default="", help="numero da operacao, para escopar o cedente")
    ap.add_argument("--nomes", default=",".join(NOMES_PADRAO),
                    help="valores do parametro a testar (padrao: f,c,r)")
    ap.add_argument("--todos", action="store_true",
                    help="permite listagem com mais de 1 titulo (imprime TODOS)")
    ap.add_argument("--confirmar", action="store_true",
                    help="dispara os POSTs de impressao e salva os PDFs")
    args = ap.parse_args()

    with sync_playwright() as p:
        try:
            ctx = _conectar(p)
        except Exception as e:                                      # noqa: BLE001
            log(f"ERRO: {e}")
            return 2

        label = args.conta_label
        if not label:
            from src.processors.web.boletos._emissao_core import listar_contas_dropdown
            achou = [l for v, l in listar_contas_dropdown(ctx) if v == args.conta]
            if not achou:
                log(f"ERRO: conta {args.conta} nao esta no dropdown")
                return 4
            label = achou[0]

        grupo_esperado = ec.classificar_conta(label)
        radio_esperado = ec.CONFIG_GRUPO[grupo_esperado]["radio"]
        log(f"conta   : {args.conta} | {label}")
        log(f"grupo   : {grupo_esperado} -> a emissao pede ImprimirBoletoEmNome={radio_esperado}")

        try:
            html_lista, ids, _ = listar(ctx, conta_value=args.conta, conta_label=label,
                                        num_doc=args.num_doc, nop=args.nop or None)
        except Exception as e:                                      # noqa: BLE001
            log(f"ERRO na listagem: {e}")
            return 3

        log(f"titulos : {len(ids)} -> {ids}")
        if not ids:
            log("nada a imprimir (filtro nao achou titulo pendente nesta conta)")
            return 5
        if len(ids) != 1 and not args.todos:
            log("ABORTADO: a listagem trouxe mais de 1 titulo. Refine --num-doc/--nop, "
                "ou passe --todos se for isso mesmo que voce quer.")
            return 6

        if not args.confirmar:
            log("")
            log("MODO LISTAGEM (nada foi impresso). Para gerar os PDFs, repita com --confirmar.")
            log("Lembre: o POST de impressao gera 2a via num titulo ja emitido — e EMITE um "
                "titulo que ainda nao tenha boleto.")
            return 0

        carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        saida = os.path.join(SAIDA_BASE, carimbo)
        os.makedirs(saida, exist_ok=True)
        manifesto = {
            "quando": carimbo,
            "conta_id": args.conta,
            "conta_label": label,
            "grupo": grupo_esperado,
            "radio_que_a_emissao_pede": radio_esperado,
            "num_doc": args.num_doc,
            "nop": args.nop,
            "ids": ids,
            "resultados": [],
        }

        base = (args.num_doc or ids[0]).replace("/", "-")
        for nome in [n.strip() for n in args.nomes.split(",") if n.strip()]:
            try:
                conteudo, ct, body = imprimir(ctx, html_lista, ids, nome)
            except Exception as e:                                  # noqa: BLE001
                log(f"  [{nome}] ERRO: {e}")
                manifesto["resultados"].append({"nome": nome, "erro": str(e)})
                continue
            ext = "pdf" if "pdf" in ct else "html"
            caminho = os.path.join(saida, f"{base}_{nome}.{ext}")
            with open(caminho, "wb") as fh:
                fh.write(conteudo)
            log(f"  [{nome}] {len(conteudo):>8} bytes | {ct[:40]:<40} -> {caminho}")
            manifesto["resultados"].append({
                "nome": nome, "content_type": ct, "bytes": len(conteudo),
                "arquivo": caminho, "corpo_enviado": body,
            })

        with open(os.path.join(saida, "manifesto.json"), "w", encoding="utf-8") as fh:
            json.dump(manifesto, fh, ensure_ascii=False, indent=2)

        log("")
        log(f"PDFs em {saida}")
        log("Abra os arquivos e compare o campo Beneficiario de cada um:")
        log("  - se os tres trouxerem o MESMO nome -> o parametro nao controla o PDF,")
        log("    e o nome vem do cadastro da conta/operacao no Smart (nao e o nosso codigo)")
        log("  - se mudarem -> o parametro manda, e o defeito e nosso: o POST de impressao")
        log("    nao reaplica o radio, e o envio manda 'r' fixo do template")
        return 0


if __name__ == "__main__":
    sys.exit(main())
