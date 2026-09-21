#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
conferir_emissao.py - o boleto saiu no nome que a gente pediu?

Le a pasta de evidencia que a emissao passou a gravar
(`data/boletos/emitidos/<AAAA-MM-DD>/`), abre cada PDF, extrai o campo
Beneficiario e compara com o que o manifesto diz que foi PEDIDO:

    grupo convencional (conta BB/SICOOB) -> ImprimirBoletoEmNome=f -> SECURITIZADORA
    grupo oculto       (conta 'mp ...')  -> ImprimirBoletoEmNome=c -> CEDENTE

POR QUE EXISTE
--------------
Em 21/08/2026 chegou um boleto do Banco do Brasil (carteira 17, que so existe
nas contas BB) impresso em nome do CEDENTE — MOREIRA METALURGICA. Pela regra,
conta BB imprime em nome da securitizadora. E o sacado, ao consultar no banco,
ve a Prosper: o nome no papel e o dono da conta nao batem, e ele se recusa a
pagar.

Nao havia como conferir isso em escala: o robo descartava o PDF. Agora guarda —
e este script transforma a pasta num veredito de uma tela.

ONDE RODA: **no host**, nao no container. `data/` e bind-mount e o `pdftotext`
(poppler-utils) esta instalado aqui. Nao precisa de Docker, nem de banco, nem
de sessao do Smart.

USO
    python3 scripts/conferir_emissao.py                 # pasta de hoje
    python3 scripts/conferir_emissao.py --dia 2026-08-24
    python3 scripts/conferir_emissao.py --dia 2026-08-24 --so-divergentes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date

# Pasta local (host). No container o mesmo lugar e /app/data/boletos/emitidos.
BASE_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "boletos", "emitidos",
)

# Como reconhecer a securitizadora no campo Beneficiario. Sobrescreva com
# --marcador se a razao social impressa for outra.
MARCADORES_SECURITIZADORA = ("PROSPER",)

# `NOME - 12.345.678/0001-99` -> beneficiario (o dash antes do CNPJ e a marca).
_RE_BENEFICIARIO = re.compile(
    r"^(?P<nome>[A-ZÀ-Ú0-9][^\n]{4,90}?)\s+-\s+(?P<cnpj>\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\s*$",
    re.MULTILINE,
)
# `NOME CNPJ: 12.345.678/0001-99` -> pagador (o template escreve 'CNPJ:').
_RE_PAGADOR = re.compile(
    r"^(?P<nome>[A-ZÀ-Ú0-9][^\n]{4,90}?)\s+CNPJ:\s*(?P<cnpj>\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\s*$",
    re.MULTILINE,
)
_RE_NOSSO_NUMERO = re.compile(r"\b(\d{17})\b")
_RE_VALOR = re.compile(r"^\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*$", re.MULTILINE)


def extrair_campos(texto: str) -> dict:
    """Le beneficiario, pagador, nosso numero e valor do texto do boleto.

    Regex e nao parser de PDF de proposito: o layout do Smart e estavel e o
    `pdftotext` entrega as linhas na mesma ordem. Campo que nao casar volta
    None — o script mostra 'indeterminado' em vez de inventar.
    """
    m_ben = _RE_BENEFICIARIO.search(texto or "")
    m_pag = _RE_PAGADOR.search(texto or "")
    m_nn = _RE_NOSSO_NUMERO.search(texto or "")
    m_val = _RE_VALOR.search(texto or "")
    return {
        "beneficiario": m_ben.group("nome").strip() if m_ben else None,
        "beneficiario_cnpj": m_ben.group("cnpj") if m_ben else None,
        "pagador": m_pag.group("nome").strip() if m_pag else None,
        "pagador_cnpj": m_pag.group("cnpj") if m_pag else None,
        "nosso_numero": m_nn.group(1) if m_nn else None,
        "valor": m_val.group(1) if m_val else None,
    }


def eh_securitizadora(nome: str | None, marcadores=MARCADORES_SECURITIZADORA) -> bool:
    if not nome:
        return False
    alvo = nome.upper()
    return any(m.upper() in alvo for m in marcadores)


def avaliar(beneficiario: str | None, grupo: str,
            marcadores=MARCADORES_SECURITIZADORA) -> tuple[str, str]:
    """Veredito de UM boleto. Retorna (situacao, motivo).

    situacao: 'ok' | 'divergente' | 'indeterminado'
    """
    if not beneficiario:
        return "indeterminado", "nao achei o campo Beneficiario no PDF"
    securitizadora = eh_securitizadora(beneficiario, marcadores)
    if grupo == "convencional":
        if securitizadora:
            return "ok", "conta convencional, impresso em nome da securitizadora"
        return ("divergente",
                f"conta CONVENCIONAL deveria imprimir a securitizadora, "
                f"mas saiu '{beneficiario}'")
    if grupo == "oculto":
        if securitizadora:
            return ("divergente",
                    "conta OCULTA deveria imprimir o cedente, mas saiu a securitizadora")
        return "ok", "conta oculta, impresso em nome do cedente"
    return "indeterminado", f"grupo desconhecido: {grupo!r}"


def texto_do_pdf(caminho: str) -> str:
    """Extrai texto com `pdftotext`. String vazia se nao der."""
    try:
        r = subprocess.run(["pdftotext", "-q", caminho, "-"],
                           capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", errors="replace")
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""


def conferir_pasta(pasta: str, marcadores=MARCADORES_SECURITIZADORA) -> list[dict]:
    """Um dict por evidencia encontrada, ja com o veredito."""
    saida: list[dict] = []
    if not os.path.isdir(pasta):
        return saida
    for nome in sorted(os.listdir(pasta)):
        if not nome.endswith(".json"):
            continue
        caminho_json = os.path.join(pasta, nome)
        try:
            with open(caminho_json, encoding="utf-8") as fh:
                man = json.load(fh)
        except (OSError, ValueError):
            continue
        # SEMPRE prefira o arquivo VIZINHO ao lado do .json — mesmo basename.
        # O `arquivo` do manifesto pode ser o caminho DE DENTRO DO CONTAINER
        # (/app/data/...), que nao existe no host onde este conferidor roda.
        # O .pdf/.html fisico esta ao lado do .json, seja quem tiver gravado.
        vizinho_pdf = os.path.join(pasta, nome[:-5] + ".pdf")
        vizinho_html = os.path.join(pasta, nome[:-5] + ".html")
        if os.path.exists(vizinho_pdf):
            doc = vizinho_pdf
        elif os.path.exists(vizinho_html):
            doc = vizinho_html
        else:
            doc = man.get("arquivo") or vizinho_pdf
        linha = {
            "manifesto": caminho_json,
            "arquivo": doc,
            "conta_label": man.get("conta_label", "?"),
            "grupo": man.get("grupo", "?"),
            "radio_pedido": man.get("radio_em_nome", "?"),
            "ids": man.get("ids_titulos") or [],
            "eh_pdf": bool(man.get("resposta_eh_pdf")),
        }
        if not linha["eh_pdf"] or not os.path.exists(doc):
            linha.update(situacao="indeterminado", beneficiario=None,
                         motivo="resposta nao era PDF" if not linha["eh_pdf"]
                                else "arquivo do documento nao encontrado")
            saida.append(linha)
            continue
        campos = extrair_campos(texto_do_pdf(doc))
        situacao, motivo = avaliar(campos["beneficiario"], linha["grupo"], marcadores)
        linha.update(campos)
        linha.update(situacao=situacao, motivo=motivo)
        saida.append(linha)
    return saida


_SIMBOLO = {"ok": "OK ", "divergente": "!! ", "indeterminado": " ? "}


def main() -> int:
    ap = argparse.ArgumentParser(description="Confere o nome impresso nos boletos emitidos.")
    ap.add_argument("--dia", default=date.today().isoformat(), help="AAAA-MM-DD (padrao: hoje)")
    ap.add_argument("--base", default=BASE_PADRAO, help="pasta de evidencia")
    ap.add_argument("--so-divergentes", action="store_true")
    ap.add_argument("--marcador", action="append", default=[],
                    help="texto que identifica a securitizadora (repetivel)")
    ap.add_argument("--json", action="store_true", help="saida em JSON")
    args = ap.parse_args()

    marcadores = tuple(args.marcador) or MARCADORES_SECURITIZADORA
    pasta = os.path.join(args.base, args.dia)
    linhas = conferir_pasta(pasta, marcadores)

    if args.json:
        print(json.dumps(linhas, ensure_ascii=False, indent=2))
        return 0

    if not linhas:
        print(f"nada em {pasta}")
        print("A emissao ainda nao rodou nesse dia, ou SALVAR_PDF_EMISSAO esta desligado.")
        return 1

    print(f"── {pasta} — {len(linhas)} emissao(oes) ──\n")
    print(f"{'':<4}{'conta':<32}{'grupo':<13}{'pediu':<7}{'beneficiario impresso':<42}{'tit.':>5}")
    print("─" * 103)
    for l in linhas:
        if args.so_divergentes and l["situacao"] == "ok":
            continue
        print(f"{_SIMBOLO[l['situacao']]:<4}{l['conta_label'][:31]:<32}{l['grupo']:<13}"
              f"{l['radio_pedido']:<7}{(l.get('beneficiario') or '—')[:41]:<42}"
              f"{len(l['ids']):>5}")

    div = [l for l in linhas if l["situacao"] == "divergente"]
    ind = [l for l in linhas if l["situacao"] == "indeterminado"]
    print("\n" + "─" * 103)
    print(f"ok: {len(linhas) - len(div) - len(ind)}   divergentes: {len(div)}   indeterminados: {len(ind)}")
    for l in div:
        print(f"\n!! {l['conta_label']}  ({len(l['ids'])} titulo(s): {', '.join(l['ids'][:6])})")
        print(f"   {l['motivo']}")
        print(f"   {l['arquivo']}")
    return 2 if div else 0


if __name__ == "__main__":
    sys.exit(main())
