# -*- coding: utf-8 -*-
"""Levantamento (SO LISTAGEM) dos documentos do Doc2You por dia — analise de teto.

Lista TODOS os documentos (todos os status, nao so concluidos) de cada dia util do
intervalo e grava JSON com {chk, tipo, operacao, nota, cedente, status, partes}.
NAO baixa PDF, NAO toca o Nextcloud, NAO grava em stg.* — one-off de analise para
medir quantas Cartas de Cessao existem/concluem assinatura vs. o que o acervo tem.

Uso:
  docker exec -e DISPLAY=:98 -e PYTHONPATH=/app -w /app erp-automation \
    python scripts/levantamento_cartas_doc2you.py --de 2026-06-16 --ate 2026-06-30

Salva incrementalmente em /app/temp/levantamento_cartas_doc2you.json — um run
interrompido preserva os dias ja listados; re-rodar com --de ajustado continua.
"""
import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import date, timedelta

from playwright.async_api import async_playwright

from src.processors.web.doc2you import dias_uteis
from src.processors.web.doc2you import download as D
from src.processors.web.doc2you import _login as L
from src.processors.web.doc2you.baixar_dia import PERFIL, _credenciais, _sso

SAIDA_DEFAULT = "/app/temp/levantamento_cartas_doc2you.json"


def _parse_data(s: str) -> date:
    return date.fromisoformat(s.strip())


def _dias_uteis(de: date, ate: date):
    d = de
    while d <= ate:
        if dias_uteis.eh_dia_util(d):
            yield d
        d += timedelta(days=1)


def _carregar_parcial(saida: str) -> dict:
    if os.path.exists(saida):
        try:
            with open(saida, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"dias": {}}


def _salvar(saida: str, resultado: dict) -> None:
    tmp = saida + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False)
    os.replace(tmp, saida)


async def executar(de: date, ate: date, saida: str) -> None:
    usuario, senha = _credenciais()
    if not (usuario and senha):
        raise RuntimeError("sem credencial Smart (credentials.csv / DOC2YOU_LOGIN).")

    resultado = _carregar_parcial(saida)
    pendentes = [d for d in _dias_uteis(de, ate) if d.isoformat() not in resultado["dias"]]
    if not pendentes:
        print("[levantamento] todos os dias do intervalo ja listados — nada a fazer.", flush=True)
        return
    print(f"[levantamento] {len(pendentes)} dia(s) util(eis) a listar: "
          f"{pendentes[0]} .. {pendentes[-1]}", flush=True)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PERFIL, headless=False, channel="chrome",
            args=["--no-sandbox", "--disable-dev-shm-usage", "--start-maximized"],
            no_viewport=True)
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            print("[levantamento] login...", flush=True)
            logado = False
            for tent in range(1, 4):
                try:
                    if await L.login(ctx, page, usuario, senha):
                        logado = True
                        break
                except Exception as e:
                    print(f"[levantamento] login {tent}/3 erro: {type(e).__name__}: {e}", flush=True)
                if tent < 3:
                    await asyncio.sleep(8)
            if not logado:
                raise RuntimeError("auto-login falhou apos 3 tentativas.")
            print("[levantamento] logado. SSO Doc2You...", flush=True)
            if not await _sso(ctx):
                raise RuntimeError("Doc2You nao acessivel com essa conta.")

            for dia in pendentes:
                iso = dia.isoformat()
                docs = await D.listar_documentos(
                    ctx, iso, iso, status_doc="", max_paginas=200,
                    logger=type("Q", (), {"log": staticmethod(lambda m: None)})())
                resultado["dias"][iso] = [
                    {
                        "chk": d.get("chk"),
                        "tipo": d.get("tipo"),
                        "operacao": d.get("operacao"),
                        "nota": d.get("nota"),
                        "cedente": d.get("cedente"),
                        "status": d.get("status"),
                        "partes": d.get("partes"),
                    }
                    for d in docs
                ]
                _salvar(saida, resultado)
                cartas = [d for d in docs if d.get("tipo") == "carta_cessao"]
                st = Counter(d.get("status") or "?" for d in docs)
                st_cartas = Counter(d.get("status") or "?" for d in cartas)
                print(f"[{iso}] {len(docs)} doc(s) | status {dict(st)} | "
                      f"cartas {len(cartas)} {dict(st_cartas)}", flush=True)
        finally:
            await ctx.close()
    print(f"[levantamento] concluido — saida: {saida}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--de", required=True, help="YYYY-MM-DD")
    ap.add_argument("--ate", required=True, help="YYYY-MM-DD")
    ap.add_argument("--saida", default=SAIDA_DEFAULT)
    args = ap.parse_args()
    asyncio.run(executar(_parse_data(args.de), _parse_data(args.ate), args.saida))


if __name__ == "__main__":
    main()
