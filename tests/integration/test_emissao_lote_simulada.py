#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ensaio do lote de emissao INTEIRO, com um Smart falso — sem container.

O QUE ESTE TESTE COBRE, E QUE OS UNITARIOS NAO COBREM
------------------------------------------------------
A esteira ponta a ponta:

    emitir_conta_http()  ->  data/boletos/emitidos/<dia>/*.pdf + *.json
                         ->  scripts/conferir_emissao.py
                         ->  veredito por conta

Os unitarios provam pedaco por pedaco. Aqui roda tudo junto, com PDF de
verdade (montado a mao, stdlib pura) que o `pdftotext` consegue ler — que e
como o conferidor vai trabalhar na rodada real.

OS DOIS CENARIOS SAO AS DUAS HIPOTESES DO CASO REAL
----------------------------------------------------
Em 21/08/2026 apareceu um boleto do Banco do Brasil impresso em nome do CEDENTE
(MOREIRA METALURGICA), quando conta BB e grupo `convencional` e a regra manda
SECURITIZADORA. Ficou provado que o POST de impressao NAO reaplica o
`ImprimirBoletoEmNome` — mas nao se sabe o que o Smart faz com isso:

  `smart_obediente`      honra o parametro que mandamos na LISTAGEM.
                         Conta BB sai com a securitizadora -> nada a corrigir.

  `smart_sempre_cedente` ignora e imprime sempre o cedente.
                         Conta BB sai com o cedente -> reproduz o caso real.

O teste exige que o conferidor **separe os dois**: no primeiro, tudo `ok`; no
segundo, a conta BB aparece como `divergente` e a conta `mp ` continua `ok`.
E o que garante que a rodada de verdade nao vai passar batida.

Roda no HOST. Precisa de `pdftotext` (poppler-utils) para o cenario completo.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from conferir_emissao import conferir_pasta                        # noqa: E402
from src.processors.web.boletos import _emissao_config as ec       # noqa: E402
from src.processors.web.boletos._emissao_core import emitir_conta_http  # noqa: E402

SECURITIZADORA = "PROSPER FIDC MULTISSETORIAL - 11.222.333/0001-44"
CEDENTE = "MOREIRA METALURGICA INDUSTRIA E COMERCIO LTDA - 51.737.963/0001-03"
SACADO = "PLANTEC DISTRIBUIDORA DE PRODUTOS DE CNPJ: 09.262.527/0003-20"

CONTAS = [
    ("290", "Banco do Brasil - Ativos", "convencional"),
    ("396", "mp moreira metalurgica", "oculto"),
]


# --------------------------------------------------------------------------- #
# PDF minimo, stdlib pura — o pdftotext le
# --------------------------------------------------------------------------- #
def _pdf(linhas: list[str]) -> bytes:
    corpo = ["BT", "/F1 9 Tf", "40 800 Td", "11 TL"]
    for linha in linhas:
        esc = linha.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        corpo.append(f"({esc}) Tj T*")
    corpo.append("ET")
    stream = "\n".join(corpo).encode("latin-1", "replace")
    objetos = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
        b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
        b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream",
    ]
    saida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        saida += f"{off:010d} 00000 n \n".encode()
    saida += (f"trailer\n<</Size {len(objetos) + 1}/Root 1 0 R>>\n"
              f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(saida)


def _boleto(beneficiario: str) -> bytes:
    return _pdf([
        "001-9 Ficha de Compensacao",
        beneficiario,
        "Rua Martinho Vaz de Barros 47, Jd Pirajussara. Sao Paulo/SP",
        "21/08/2026 0386-7/00091665-X R$",
        "3.175,90",
        "34527370000513133 15652-001",
        SACADO,
    ])


# --------------------------------------------------------------------------- #
# Smart falso
# --------------------------------------------------------------------------- #
HTML_FORM = """
<form name="Financeiro">
  <input type="hidden" name="tipo" value="boleto">
  <select name="contaCorrente"><option value="0">Selecione a conta</option></select>
</form>
"""
HTML_LISTA = """
<form name="ListaTitulosBoletos">
  <input type="checkbox" name="checkImpressao" value="824060" checked>
  <input type="hidden" name="Checks" value="">
</form>
"""


class _Resposta:
    def __init__(self, corpo, content_type="text/html", status=200):
        self._corpo = corpo.encode("cp1252") if isinstance(corpo, str) else corpo
        self.status = status
        self.headers = {"content-type": content_type}

    def body(self):
        return self._corpo


class SmartFalso:
    """`modo='obediente'` honra o radio da listagem; `'sempre_cedente'` ignora."""

    def __init__(self, modo: str):
        self.modo = modo
        self.radio_recebido: str | None = None
        self.request = self

    def get(self, url, **_):
        return _Resposta(HTML_FORM)

    def post(self, url, data=None, **_):
        corpo = data or ""
        if url == ec.URL_LISTA_HTTP:
            for par in corpo.split("&"):
                if par.startswith("ImprimirBoletoEmNome="):
                    self.radio_recebido = par.split("=", 1)[1]
            return _Resposta(HTML_LISTA)
        if url == ec.URL_PRINT_HTTP:
            if self.modo == "obediente" and self.radio_recebido == "f":
                nome = SECURITIZADORA
            else:
                nome = CEDENTE
            return _Resposta(_boleto(nome), "application/pdf")
        return _Resposta("")


def _rodar_lote(modo: str, destino: Path, monkeypatch) -> list[dict]:
    """Emite as duas contas contra o Smart falso e devolve o veredito da pasta."""
    monkeypatch.setattr(ec, "EVIDENCIA_DIR", str(destino))
    monkeypatch.setattr(ec, "SALVAR_PDF", True)
    for conta_id, label, grupo in CONTAS:
        smart = SmartFalso(modo)
        r = emitir_conta_http(smart, conta_value=conta_id, conta_label=label,
                              grupo=grupo, dry_run=False)
        assert r["ok"] and r["pdf"], f"{label}: {r}"
    return conferir_pasta(str(destino / date.today().isoformat()))


# --------------------------------------------------------------------------- #
# Os dois cenarios
# --------------------------------------------------------------------------- #
def test_smart_obediente_nao_produz_divergencia(tmp_path, monkeypatch):
    linhas = _rodar_lote("obediente", tmp_path / "emitidos", monkeypatch)
    assert len(linhas) == 2
    assert {l["situacao"] for l in linhas} == {"ok"}


def test_smart_que_ignora_o_radio_reproduz_o_caso_moreira(tmp_path, monkeypatch):
    linhas = _rodar_lote("sempre_cedente", tmp_path / "emitidos", monkeypatch)
    por_grupo = {l["grupo"]: l for l in linhas}

    bb = por_grupo["convencional"]
    assert bb["situacao"] == "divergente"
    assert bb["radio_pedido"] == "f"                       # pedimos securitizadora
    assert "MOREIRA" in bb["beneficiario"]                 # saiu o cedente
    assert bb["ids"] == ["824060"]                         # e sabemos QUAL titulo

    mp = por_grupo["oculto"]
    assert mp["situacao"] == "ok"                          # oculta com cedente esta certo


def test_evidencia_guarda_o_corpo_enviado(tmp_path, monkeypatch):
    """O manifesto tem que provar o que foi ao Smart, nao so o que voltou."""
    _rodar_lote("sempre_cedente", tmp_path / "emitidos", monkeypatch)
    pasta = tmp_path / "emitidos" / date.today().isoformat()
    manifestos = [json.loads(p.read_text(encoding="utf-8")) for p in pasta.glob("*.json")]
    assert manifestos
    for m in manifestos:
        assert "Checks=824060%2B" in m["corpo_enviado"]
        # ...e a prova de que o radio NAO vai no POST de impressao:
        assert "ImprimirBoletoEmNome" not in m["corpo_enviado"]


@pytest.mark.skipif(
    subprocess.run(["which", "pdftotext"], capture_output=True).returncode != 0,
    reason="pdftotext (poppler-utils) nao instalado",
)
def test_cli_do_conferidor_sai_com_codigo_2_quando_ha_divergencia(tmp_path, monkeypatch):
    _rodar_lote("sempre_cedente", tmp_path / "emitidos", monkeypatch)
    r = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "conferir_emissao.py"),
         "--base", str(tmp_path / "emitidos"), "--dia", date.today().isoformat()],
        capture_output=True, text=True,
    )
    assert r.returncode == 2, r.stdout + r.stderr
    assert "divergentes: 1" in r.stdout
    assert "Banco do Brasil" in r.stdout
