# -*- coding: utf-8 -*-
"""
atualizar_contas.py - regrava contas_carteiras.json a partir do Smart.

A tela "Gerar Remessa" embute no JS um mapa `var carteira = {"<conta>": "<options>"}`
com as carteiras validas de cada conta, alem do <select> de contas. Este script le
os dois por HTTP e salva em contas_carteiras.json, que o robo usa p/ resolver
--conta por nome e p/ escolher a carteira certa de cada conta.

RODE QUANDO ABRIREM OU FECHAREM CONTA NO SMART. Enquanto o arquivo estiver
desatualizado, `--todas-contas` percorre a lista velha: conta nova nao entra na
rodada (e ninguem avisa), conta fechada gera um ciclo perdido.

Uso (dentro do container):
    python /app/src/processors/web/remessa_cobranca/atualizar_contas.py
    python .../atualizar_contas.py --cdp     # sobre a janela ja aberta no VNC
"""
import argparse
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from playwright.sync_api import sync_playwright  # noqa: E402

import _sessao                                    # noqa: E402
import login as autenticacao                      # noqa: E402
import remessa_config as cfg                      # noqa: E402

SAIDA = os.path.join(_AQUI, "contas_carteiras.json")


def _bloco_json(texto, marca):
    """Recorta o objeto {...} que vem depois de `marca` (equilibrando chaves)."""
    i = texto.find(marca)
    if i < 0:
        return None
    j = texto.index("{", i)
    prof = 0
    for k in range(j, len(texto)):
        if texto[k] == "{":
            prof += 1
        elif texto[k] == "}":
            prof -= 1
            if prof == 0:
                return texto[j:k + 1]
    return None


def extrair(html):
    """Devolve (contas, carteiras) lidos do HTML da tela Gerar Remessa."""
    contas = {}
    m = re.search(r"<select[^>]*name\s*=\s*[\"']?contaCorrente.*?</select>",
                  html, re.S | re.I)
    if m:
        for v, t in re.findall(
                r"<option[^>]*value\s*=\s*[\"']?([^\"'>\s]*)[\"']?[^>]*>(.*?)</option>",
                m.group(0), re.S | re.I):
            rotulo = re.sub(r"<[^>]+>|\s+", " ", t).strip()
            if v and v != "0" and rotulo:
                contas[v] = rotulo

    carteiras = {}
    bruto = _bloco_json(html, "var carteira")
    if bruto:
        for conta, opts_html in json.loads(bruto).items():
            opts = re.findall(
                r"<option[^>]*value\s*=\s*['\"]?(-?\d+)['\"]?[^>]*>",
                opts_html.replace("\\/", "/"), re.I)
            carteiras[conta] = [v for v in opts if v != "-1"]
    return contas, carteiras


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Regrava contas_carteiras.json.")
    ap.add_argument("--cdp", action="store_true",
                    help="usa um Chrome JA ABERTO (dev/VNC)")
    args = ap.parse_args()

    with sync_playwright() as p:
        try:
            with _sessao.sessao(p, usar_cdp=args.cdp, log=print) as ctx:
                r = ctx.request.get(cfg.URL_GERAR_REMESSA, timeout=60_000)
                html = r.body().decode("iso-8859-1", errors="replace")
        except RuntimeError as e:
            print(f"ERRO: {e}")
            return 1

    if autenticacao.parece_deslogado(html):
        print("ERRO: a tela Gerar Remessa voltou deslogada.")
        return 2

    contas, carteiras = extrair(html)
    if not contas:
        print("ERRO: nenhuma conta lida — a tela mudou? Nao vou sobrescrever "
              "o arquivo bom com um vazio.")
        return 3

    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump({"contas": contas, "carteiras": carteiras}, f,
                  ensure_ascii=False, indent=2)

    alvo = sum(1 for r in contas.values()
               if r.lower().startswith(cfg.PREFIXO_CONTAS.lower()))
    print(f"{len(contas)} conta(s), {len(carteiras)} com carteiras mapeadas")
    print(f"{alvo} casam com o prefixo {cfg.PREFIXO_CONTAS!r} (o que --todas-contas percorre)")
    print(f"salvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
