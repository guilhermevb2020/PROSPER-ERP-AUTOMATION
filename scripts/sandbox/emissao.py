#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emissao.py - roda a EMISSAO de boletos no sandbox (host), contra o Smart REAL.

E o mesmo `_emissao_core.emitir_conta_http` que o container roda — aqui so
sobe num Chrome do host, loga com a credencial do sandbox e salva os PDFs.
Depois chama o conferidor e imprime o veredito: cada boleto saiu no nome que a
regra pede (conta BB -> securitizadora, conta 'mp ' -> cedente)?

FLUXO DE SEGURANCA (defaults SEGUROS, iguais aos do robo real)
--------------------------------------------------------------
    sem flag           -> LISTA (dry-run). Nenhum POST de impressao.
    --imprimir         -> imprime de verdade e salva o PDF.
    --num-doc X        -> escopa a UM titulo (recomendado para conferir o nome).
    --todas-contas     -> varre o dropdown inteiro (lote); sem isto, exige --conta.

⚠️ IMPRIMIR EMITE. Num titulo ja emitido gera 2a via (inofensivo, ideal para o
teste do nome). Num titulo nunca emitido, EMITE (consome nosso_numero, entra no
fluxo de remessa). Por isso --imprimir e passo separado e explicito.

Nao dispara e-mail para sacado: emissao e Via=1; o envio (Via=2) e outro robo.

USO (no host, com config/sandbox.env preenchido)
    # 1) so ver o que o filtro pega numa conta (nao imprime)
    python3 scripts/sandbox/emissao.py --conta 290 --num-doc 15652-001

    # 2) imprimir esse titulo e conferir o nome
    python3 scripts/sandbox/emissao.py --conta 290 --num-doc 15652-001 --imprimir

    # 3) lote inteiro, imprimindo (equivale ao que o cron faz)
    python3 scripts/sandbox/emissao.py --todas-contas --imprimir
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
if str(RAIZ / "scripts") not in sys.path:
    sys.path.insert(0, str(RAIZ / "scripts"))


def log(msg: str = "") -> None:
    print(msg, flush=True)


def _contas_alvo(ctx, args):
    """Lista de (value, label) a processar, conforme os filtros."""
    from src.processors.web.boletos._emissao_core import listar_contas_dropdown
    todas = listar_contas_dropdown(ctx)
    if args.conta:
        return [(v, l) for v, l in todas if v == args.conta]
    if args.todas_contas:
        return todas
    return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conta", default="", help="id da conta no dropdown (ex.: 290)")
    ap.add_argument("--todas-contas", action="store_true",
                    help="varre o dropdown inteiro (lote)")
    ap.add_argument("--num-doc", default="", help="escopa a UM titulo (NumDocumento)")
    ap.add_argument("--nop", default="", help="numero da operacao (escopa o cedente)")
    ap.add_argument("--imprimir", action="store_true",
                    help="IMPRIME de verdade e salva o PDF (sem isto, so lista)")
    ap.add_argument("--ver-navegador", action="store_true",
                    help="mostra o Chrome (headful); precisa de display grafico")
    ap.add_argument("--dia", default=date.today().isoformat(),
                    help="dia para o conferidor ler (padrao: hoje)")
    args = ap.parse_args()

    if not args.conta and not args.todas_contas:
        log("ERRO: escolha --conta <id> ou --todas-contas.")
        return 4

    from playwright.sync_api import sync_playwright
    from scripts.sandbox import _ambiente

    # ORDEM CRITICA: publicar as envs do sandbox ANTES de importar qualquer
    # `boletos.*` — o `_config` resolve credencial/URL/paths no import, e
    # importar antes disto pega tudo vazio (a pegadinha classica deste ERP).
    try:
        _ambiente.garantir_env(log=log)
    except _ambiente.SandboxSemCredencial as e:
        log(f"ERRO: {e}")
        return 2

    from src.processors.web.boletos._emissao_core import emitir_conta_http
    from src.processors.web.boletos import _emissao_config as ec

    dry = not args.imprimir
    log(f"── sandbox emissao | modo={'LISTAGEM (dry)' if dry else 'IMPRIMIR (real)'} ──")

    with sync_playwright() as p:
        try:
            # --ver-navegador forca headful (precisa de display: rode vnc.sh
            # antes e SANDBOX_DISPLAY=:90). Sem a flag, respeita SANDBOX_HEADLESS.
            headless = False if args.ver_navegador else None
            with _ambiente.sessao(p, headless=headless, log=log) as ctx:
                contas = _contas_alvo(ctx, args)
                if not contas:
                    log("nenhuma conta a processar (filtro nao casou).")
                    return 5
                log(f"contas: {len(contas)}")

                for value, label in contas:
                    grupo = ec.classificar_conta(label)
                    try:
                        r = emitir_conta_http(
                            ctx, conta_value=value, conta_label=label, grupo=grupo,
                            dry_run=dry,
                            num_doc=args.num_doc or None, nop=args.nop or None,
                        )
                    except Exception as e:                          # noqa: BLE001
                        log(f"  [{label}] ERRO: {type(e).__name__}: {e}")
                        continue
                    n = r.get("titulos", 0)
                    if dry:
                        log(f"  [{label}] grupo={grupo} radio={ec.CONFIG_GRUPO[grupo]['radio']} "
                            f"-> {n} titulo(s) {r.get('ids', [])}")
                    else:
                        marca = "PDF" if r.get("pdf") else "NAO-PDF"
                        log(f"  [{label}] grupo={grupo} -> {n} titulo(s) | {marca} "
                            f"| {r.get('evidencia') or '(nada salvo)'}")
        except _ambiente.SandboxSemCredencial as e:
            log(f"ERRO: {e}")
            return 2
        except _ambiente.SandboxSemSessao as e:
            log(f"ERRO: {e}")
            return 3

    if dry:
        log("\nLISTAGEM concluida (nada impresso). Repita com --imprimir para gerar os PDFs.")
        return 0

    # Conferir o que foi impresso
    log("\n── conferindo os nomes impressos ──")
    from conferir_emissao import conferir_pasta
    base = ec.EVIDENCIA_DIR
    linhas = conferir_pasta(f"{base}/{args.dia}")
    if not linhas:
        log("  (nenhuma evidencia encontrada para conferir)")
        return 0
    div = [l for l in linhas if l["situacao"] == "divergente"]
    for l in linhas:
        marca = {"ok": "OK", "divergente": "!!", "indeterminado": " ?"}[l["situacao"]]
        log(f"  {marca} {l['conta_label'][:30]:<30} pediu={l['radio_pedido']} "
            f"impresso='{(l.get('beneficiario') or '—')[:38]}'")
    log(f"\n  ok={len(linhas)-len(div)}  divergentes={len(div)}")
    for l in div:
        log(f"  !! {l['conta_label']}: {l['motivo']}")
        log(f"     {l['arquivo']}")
    return 2 if div else 0


if __name__ == "__main__":
    sys.exit(main())
