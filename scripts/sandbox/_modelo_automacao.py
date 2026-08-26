#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_modelo_automacao.py - ESQUELETO de uma automação nova no sandbox.

Copie este arquivo e escreva SÓ a função `trabalho()`. O login (CapSolver),
o perfil de Chrome, a detecção de sessão morta e o vídeo/trace já vêm de
`_ambiente.sessao`. Você NUNCA reimplementa login — a regra 3 do CLAUDE.md.

    cp scripts/sandbox/_modelo_automacao.py scripts/sandbox/minha_automacao.py
    # troque `trabalho()` e rode:
    PYTHONPATH=$PWD .venv-sandbox/bin/python scripts/sandbox/minha_automacao.py

Guia completo: scripts/sandbox/COMO_CRIAR_AUTOMACAO.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def log(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# ⬇⬇⬇ ISTO É O QUE VOCÊ ESCREVE. O resto do arquivo não precisa mudar. ⬇⬇⬇
# --------------------------------------------------------------------------- #
def trabalho(ctx, args, log=print) -> dict:
    """Recebe um `ctx` JÁ LOGADO no Smart. Faz o trabalho por HTTP e retorna.

    `ctx.request.get/post` já saem autenticados (cookies da sessão). Não clique
    em tela: fale com os .php direto, como os robôs de produção fazem.
    """
    from src.common.clients.smart_sessao import parece_deslogado

    # EXEMPLO: lê a tela de emissão e conta as contas do dropdown.
    # Troque pela SUA tela e pela SUA lógica.
    url = "https://wvw.smartsecurities.com.br/smart/financeiro/impriboleto.php?Via=1"
    r = ctx.request.get(url, timeout=30_000)
    html = (r.body() or b"").decode("iso-8859-1", errors="replace")

    # REGRA: cheque isto em TODO ponto que lê resposta do Smart.
    # Sessão morta responde 200 com corpo que redireciona p/ expira.php; corpo
    # vazio também conta como deslogado.
    if not html.strip() or parece_deslogado(html):
        raise RuntimeError("sessão caiu ao ler a tela (não é 'sem trabalho')")

    n_contas = html.lower().count("<option")
    log(f"  a tela respondeu {len(html)} bytes, ~{n_contas} <option> no form")

    # Em dry-run (padrão), NÃO dispare nada que tenha efeito. Só com --confirmar.
    if args.confirmar:
        log("  --confirmar ligado: aqui iria o POST que TEM efeito (emitir/enviar/etc.)")
        # r2 = ctx.request.post(...); if parece_deslogado(...): ...
    else:
        log("  dry-run: nada com efeito foi disparado. Use --confirmar para valer.")

    return {"ok": True, "bytes": len(html)}
# --------------------------------------------------------------------------- #
# ⬆⬆⬆ FIM da parte que você escreve. ⬆⬆⬆
# --------------------------------------------------------------------------- #


# Exit codes — dê um código próprio para "fez pela metade".
OK = 0
SEM_CREDENCIAL = 2
SEM_SESSAO = 3
ERRO_TRABALHO = 6


def main() -> int:
    ap = argparse.ArgumentParser(description="Automação do sandbox (modelo).")
    ap.add_argument("--confirmar", action="store_true",
                    help="liga o efeito real (sem isto é dry-run)")
    ap.add_argument("--ver-navegador", action="store_true",
                    help="mostra o Chrome (precisa de display :90 — ver README)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright
    from scripts.sandbox import _ambiente

    # ORDEM CRÍTICA: publica as envs do sandbox ANTES de qualquer import de
    # `boletos.*`/`smart_sessao` (o _config resolve credencial no import).
    try:
        _ambiente.garantir_env(log=log)
    except _ambiente.SandboxSemCredencial as e:
        log(f"ERRO: {e}")
        return SEM_CREDENCIAL

    with sync_playwright() as p:
        try:
            headless = False if args.ver_navegador else None
            with _ambiente.sessao(p, headless=headless, log=log) as ctx:
                try:
                    resultado = trabalho(ctx, args, log=log)
                except Exception as e:                              # noqa: BLE001
                    log(f"ERRO no trabalho: {type(e).__name__}: {e}")
                    return ERRO_TRABALHO
                log(f"\nresultado: {resultado}")
                return OK
        except _ambiente.SandboxSemSessao as e:
            log(f"ERRO: {e}")
            return SEM_SESSAO


if __name__ == "__main__":
    sys.exit(main())
