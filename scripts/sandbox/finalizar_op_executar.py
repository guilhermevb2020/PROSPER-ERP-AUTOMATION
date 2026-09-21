#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalizar_op_executar.py - FINALIZA DE VERDADE as operacoes aprovadas.

⚠️⚠️ ESTE SCRIPT CLICA EM "FINALIZAR" NO SMART. A acao e IRREVERSIVEL pelo robo:
desfazer exige gente mexendo no ERP. Ele e separado do `finalizar_op.py` de
proposito - aquele monitora e NUNCA finaliza, e essa garantia so vale se o
caminho perigoso morar em outro arquivo, com outro nome, e exigir uma flag
propria.

QUEM APARECE NA TRILHA: a conta do `SANDBOX_EMAIL` (config/sandbox.env) fica
registrada no Smart como quem finalizou. Hoje e `operacional2` - o login de uma
PESSOA. Toda finalizacao automatica vai parecer feita por ela.

O QUE ELE FINALIZA: so operacoes que passam nas DUAS checagens, exatamente as
mesmas regras do monitor. Uma op barrada nunca e tocada.

Uso:
    V="PYTHONPATH=$PWD .venv-sandbox/bin/python"

    # 1) ENSAIO (padrao): mostra o que faria, nao clica em nada
    $V scripts/sandbox/finalizar_op_executar.py

    # 2) uma operacao especifica, de verdade
    $V scripts/sandbox/finalizar_op_executar.py --ops 65071 --confirmar

    # 3) a fila toda, de verdade
    $V scripts/sandbox/finalizar_op_executar.py --confirmar

⛔ NAO rode junto com o `finalizar_op.py --loop`: os dois usam o mesmo perfil de
   Chrome e disputam o lock (§1 do COMO_SUBIR_UM_ROBO). Pare o loop antes.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def log(msg: str = "") -> None:
    print(msg, flush=True)


OK = 0
SEM_CREDENCIAL = 2
SEM_SESSAO = 3
ERRO_TRABALHO = 6
FINALIZOU_PARCIAL = 7      # clicou em alguma e falhou em outra: precisa de gente


def main() -> int:
    ap = argparse.ArgumentParser(
        description="FINALIZA operacoes no Smart (irreversivel). Padrao = ensaio.")
    ap.add_argument("--ops", default="",
                    help="ops especificas (virgula). Vazio = todas as aprovadas da fila")
    ap.add_argument("--confirmar", action="store_true",
                    help="CLICA EM FINALIZAR DE VERDADE. Sem isso e so ensaio.")
    ap.add_argument("--ver-navegador", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    from playwright.sync_api import sync_playwright

    from scripts.sandbox import _ambiente, finalizar_op as base

    modo = "EXECUTAR (FINALIZA DE VERDADE)" if args.confirmar else "ENSAIO (nao clica)"
    log("=" * 66)
    log(f"  ROBO FINALIZAR OPERACAO | {modo}")
    log("=" * 66)

    try:
        _ambiente.garantir_env(log=log)
        base._preparar_pacote(log=log)
        # No CONTAINER as EVOLUTION_* ja estao no ambiente; no host quem as
        # publica (de config/sandbox.env) e o harness. Sem isto, o aviso de
        # finalizacao do robo falharia fechado no sandbox.
        base._publicar_evolution(log=log)
    except _ambiente.SandboxSemCredencial as e:
        log(f"ERRO: {e}")
        return SEM_CREDENCIAL
    except Exception as e:  # noqa: BLE001
        log(f"ERRO ao preparar: {type(e).__name__}: {e}")
        return ERRO_TRABALHO

    if args.confirmar:
        import os
        log(f"\n  ⚠️  A conta {os.environ.get('BOLETO_EMAIL', '?')} vai constar no "
            f"Smart como quem finalizou.")

    import robo_finalizar as robo

    ops = [o.strip() for o in args.ops.split(",") if o.strip()] or None
    log(f"  alvo: {', '.join(ops) if ops else 'todas as aprovadas da fila'}\n")

    with sync_playwright() as p:
        try:
            headless = False if args.ver_navegador else None
            with _ambiente.sessao(p, headless=headless, log=log) as ctx:
                try:
                    laudos = robo.ciclo(ctx, ops=ops, executar=args.confirmar,
                                        mandar_email=False)
                except Exception as e:  # noqa: BLE001
                    log(f"ERRO no ciclo: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    return ERRO_TRABALHO
        except _ambiente.SandboxSemSessao as e:
            log(f"ERRO: {e}")
            return SEM_SESSAO

    # Registra como o monitor faz, para o placar e as contas nao ficarem furados
    if laudos:
        base._gravar(laudos)
        base._gravar_contas(laudos, log=log)

    finalizadas = [l for l in laudos if l.get("acao") == "finalizada"]
    passariam = [l for l in laudos if base._veredito(l) == "FINALIZARIA"]
    falhas = [l for l in laudos
              if (l.get("acao") or "").startswith("falha ao finalizar")]

    log(f"\n{'=' * 66}")
    if args.confirmar:
        log(f"  FINALIZADAS: {len(finalizadas)}"
            + (f" -> {', '.join(l['op'] for l in finalizadas)}" if finalizadas else ""))
        if falhas:
            log(f"  FALHAS: {len(falhas)} -> "
                f"{', '.join(l['op'] + ' (' + str(l.get('acao')) + ')' for l in falhas)}")
    else:
        log(f"  ENSAIO: {len(passariam)} operacao(oes) SERIAM finalizadas"
            + (f" -> {', '.join(l['op'] for l in passariam)}" if passariam else ""))
        log("  Nada foi clicado. Use --confirmar para valer.")
    log(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    log("=" * 66)

    if falhas:
        return FINALIZOU_PARCIAL
    return OK


if __name__ == "__main__":
    sys.exit(main())
