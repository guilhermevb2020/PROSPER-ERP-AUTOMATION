#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes da evidencia da emissao — e do que o POST de impressao REALMENTE manda.

POR QUE ESTES TESTES EXISTEM
----------------------------
Em 21/08/2026 apareceu um boleto do Banco do Brasil impresso em nome do CEDENTE
(MOREIRA METALURGICA). Pela nossa regra isso nao deveria acontecer: conta BB e
grupo `convencional`, e convencional imprime em nome da SECURITIZADORA
(`ImprimirBoletoEmNome=f`). A conta ficou provada pela carteira 17, que so
existe nas contas BB (as contas `mp *` usam 1,2,4,6,9,10,16,19,28).

Nao havia como responder "foi a nossa automacao?": o log gravava contagem, nao
os IDs, e o PDF era descartado. Estes testes travam as duas correcoes:

1. a evidencia (PDF + manifesto) e gravada, com o radio e o corpo enviado;
2. **o que o robo de fato manda em cada POST** — que e onde mora a suspeita.

O QUE O TESTE 'radio_nao_vai_no_post_de_impressao' PROVA
--------------------------------------------------------
O `ImprimirBoletoEmNome` so entra no POST de LISTAGEM (passo 2). O POST de
IMPRESSAO (passo 3) monta o corpo a partir do form `ListaTitulosBoletos` da
resposta anterior e NAO reaplica o parametro. Logo: se aquele form nao devolver
o campo, nos nao controlamos o nome impresso no boleto — o Smart usa o default
dele. O teste fixa esse comportamento para que a correcao futura (reaplicar o
radio no passo 3) seja visivel como mudanca deliberada, e nao silenciosa.

RESTRICOES DE AMBIENTE (conferidas em 21/08/2026)
-------------------------------------------------
- Rodam no HOST. `_emissao_core`, `_emissao_config` e `_emissao_html` NAO
  importam playwright — o `ctx` e injetado, e aqui entra um dublê.
- `_emissao_config` puxa `_config`, que precisa de `python-dotenv`. E a unica
  dependencia externa destes testes.
- Nada aqui toca a rede, o Smart ou o banco.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl

import pytest

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.processors.web.boletos import _emissao_config as ec       # noqa: E402
from src.processors.web.boletos import emissao_evidencia as ev     # noqa: E402
from src.processors.web.boletos._emissao_core import emitir_conta_http  # noqa: E402


# --------------------------------------------------------------------------- #
# Dublê do ctx do Playwright — devolve HTML fixo e guarda o que foi enviado
# --------------------------------------------------------------------------- #
HTML_FORM = """
<html><body>
<form name="Financeiro">
  <input type="hidden" name="tipo" value="boleto">
  <input type="hidden" name="Via" value="1">
  <select name="contaCorrente">
    <option value="0">Selecione a conta</option>
    <option value="290">Banco do Brasil - Ativos</option>
    <option value="396">mp moreira metalurgica</option>
  </select>
  <input type="text" name="NumDocumento" value="">
</form>
</body></html>
"""

# Repara: este form NAO tem `ImprimirBoletoEmNome`. E o ponto do teste — e
# tambem o que se espera do Smart, ja que o radio vive na tela anterior.
HTML_LISTA = """
<html><body>
<form name="ListaTitulosBoletos">
  <input type="hidden" name="salvaInstrucoes" value="2">
  <input type="checkbox" name="checkImpressao" value="824060" checked>
  <input type="checkbox" name="checkImpressao" value="824061" checked>
  <input type="hidden" name="Checks" value="">
</form>
</body></html>
"""


class _Resposta:
    def __init__(self, corpo: str | bytes, content_type: str = "text/html", status: int = 200):
        self._corpo = corpo.encode("cp1252") if isinstance(corpo, str) else corpo
        self.status = status
        self.headers = {"content-type": content_type}

    def body(self):
        return self._corpo


class _Request:
    """Grava cada POST para o teste inspecionar o corpo enviado."""

    def __init__(self, resposta_print: _Resposta):
        self.enviados: list[tuple[str, str]] = []
        self._resposta_print = resposta_print

    def get(self, url, **_):
        return _Resposta(HTML_FORM)

    def post(self, url, data=None, **_):
        self.enviados.append((url, data or ""))
        if url == ec.URL_PRINT_HTTP:
            return self._resposta_print
        return _Resposta(HTML_LISTA)


class _Ctx:
    def __init__(self, resposta_print: _Resposta | None = None):
        self.request = _Request(resposta_print or _Resposta(b"%PDF-1.4 fake", "application/pdf"))


def _campos(corpo: str) -> list[tuple[str, str]]:
    return parse_qsl(corpo, keep_blank_values=True)


def _valor(corpo: str, chave: str):
    for k, v in _campos(corpo):
        if k == chave:
            return v
    return None


@pytest.fixture(autouse=True)
def _evidencia_em_tmp(tmp_path, monkeypatch):
    """Nenhum teste escreve em /app/data — cada um tem a sua pasta."""
    monkeypatch.setattr(ec, "EVIDENCIA_DIR", str(tmp_path / "emitidos"))
    monkeypatch.setattr(ec, "SALVAR_PDF", True)


# --------------------------------------------------------------------------- #
# 1) A regra do nome, por conta — o que o caso MOREIRA colocou em duvida
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "label, grupo, radio",
    [
        ("Banco do Brasil", "convencional", "f"),
        ("Banco do Brasil - Ativos", "convencional", "f"),
        ("Banco do Brasil Prospere", "convencional", "f"),
        ("SICOOB", "convencional", "f"),
        ("mp moreira metalurgica", "oculto", "c"),
        ("MP Moreira Metalurgica", "oculto", "c"),   # o prefixo e case-insensitive
        ("mp megaprot d", "oculto", "c"),
    ],
)
def test_conta_decide_o_nome_nao_a_classe(label, grupo, radio):
    """Quem manda no nome e a CONTA, nao a classe (confirmado com a Gerencia,
    31/07/2026). Conta BB -> securitizadora. Conta 'mp ' -> cedente."""
    assert ec.classificar_conta(label) == grupo
    assert ec.CONFIG_GRUPO[grupo]["radio"] == radio


def test_conta_que_apenas_contem_mp_nao_e_oculta():
    """`mp` no meio do nome nao torna a conta oculta — so o PREFIXO conta."""
    assert ec.classificar_conta("Banco do Brasil mp") == "convencional"
    assert ec.classificar_conta("empresa mp ltda") == "convencional"


# --------------------------------------------------------------------------- #
# 2) O que sai em cada POST
# --------------------------------------------------------------------------- #
def test_listagem_leva_o_radio_do_grupo():
    ctx = _Ctx()
    emitir_conta_http(ctx, conta_value="290", conta_label="Banco do Brasil - Ativos",
                      grupo="convencional", dry_run=False)
    url_lista, corpo_lista = ctx.request.enviados[0]
    assert url_lista == ec.URL_LISTA_HTTP
    assert _valor(corpo_lista, "ImprimirBoletoEmNome") == "f"
    assert _valor(corpo_lista, "contaCorrente") == "290"
    assert [v for k, v in _campos(corpo_lista) if k == "sClasseRisco[]"] == ["P", "T", "CL"]


def test_listagem_de_conta_mp_leva_cedente():
    ctx = _Ctx()
    emitir_conta_http(ctx, conta_value="396", conta_label="mp moreira metalurgica",
                      grupo="oculto", dry_run=False)
    _, corpo_lista = ctx.request.enviados[0]
    assert _valor(corpo_lista, "ImprimirBoletoEmNome") == "c"


def test_radio_nao_vai_no_post_de_impressao():
    """⚠️ COMPORTAMENTO ATUAL, fixado de proposito.

    O passo 3 nao reaplica `ImprimirBoletoEmNome`: ele so reenvia o que o form
    `ListaTitulosBoletos` devolveu. Como aquele form nao traz o campo, o nome
    impresso no boleto NAO e decidido por nos neste POST.

    Se um dia este teste falhar, foi porque alguem passou a reaplicar o radio —
    o que e a correcao desejada. Mude o teste junto, deliberadamente.
    """
    ctx = _Ctx()
    emitir_conta_http(ctx, conta_value="290", conta_label="Banco do Brasil - Ativos",
                      grupo="convencional", dry_run=False)
    url_print, corpo_print = ctx.request.enviados[1]
    assert url_print == ec.URL_PRINT_HTTP
    assert _valor(corpo_print, "ImprimirBoletoEmNome") is None
    assert _valor(corpo_print, "Checks") == "824060+824061+"
    assert _valor(corpo_print, "boleto") == "1"
    assert _valor(corpo_print, "NumEmail") == "0"      # nunca dispara e-mail aqui


def test_dry_run_nao_dispara_impressao():
    ctx = _Ctx()
    r = emitir_conta_http(ctx, conta_value="290", conta_label="Banco do Brasil",
                          grupo="convencional", dry_run=True)
    assert r["dry"] is True
    assert [u for u, _ in ctx.request.enviados] == [ec.URL_LISTA_HTTP]


# --------------------------------------------------------------------------- #
# 3) A evidencia
# --------------------------------------------------------------------------- #
def test_emissao_salva_pdf_e_manifesto():
    ctx = _Ctx()
    r = emitir_conta_http(ctx, conta_value="290", conta_label="Banco do Brasil - Ativos",
                          grupo="convencional", dry_run=False)
    assert r["pdf"] is True
    caminho = Path(r["evidencia"])
    assert caminho.exists() and caminho.suffix == ".pdf"
    assert caminho.read_bytes().startswith(b"%PDF")

    manifesto = json.loads(caminho.with_suffix(".json").read_text(encoding="utf-8"))
    assert manifesto["ids_titulos"] == ["824060", "824061"]
    assert manifesto["radio_em_nome"] == "f"          # o que PEDIMOS
    assert manifesto["conta_label"] == "Banco do Brasil - Ativos"
    assert manifesto["resposta_eh_pdf"] is True
    # o corpo enviado fica guardado: e a prova do que foi ao Smart
    assert "Checks=824060%2B824061%2B" in manifesto["corpo_enviado"]


def test_resposta_html_e_marcada_como_nao_pdf():
    """Smart responde HTTP 200 com pagina de erro. Antes virava status 'ok'."""
    ctx = _Ctx(_Resposta("<html>erro</html>", "text/html; charset=iso-8859-1"))
    r = emitir_conta_http(ctx, conta_value="290", conta_label="Banco do Brasil",
                          grupo="convencional", dry_run=False)
    assert r["pdf"] is False
    assert Path(r["evidencia"]).suffix == ".html"


def test_falha_ao_gravar_nao_derruba_a_emissao(monkeypatch):
    """Evidencia perdida e ruim; emissao derrubada e pior."""
    monkeypatch.setattr(ec, "EVIDENCIA_DIR", "/proc/nao/da/para/escrever")
    ctx = _Ctx()
    r = emitir_conta_http(ctx, conta_value="290", conta_label="Banco do Brasil",
                          grupo="convencional", dry_run=False)
    assert r["ok"] is True
    assert r["evidencia"] is None


def test_desligar_a_flag_nao_grava_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(ec, "SALVAR_PDF", False)
    ctx = _Ctx()
    r = emitir_conta_http(ctx, conta_value="290", conta_label="Banco do Brasil",
                          grupo="convencional", dry_run=False)
    assert r["evidencia"] is None


# --------------------------------------------------------------------------- #
# 4) O modulo puro
# --------------------------------------------------------------------------- #
def test_extensao_e_pdf():
    assert ev.extensao_de("application/pdf") == "pdf"
    assert ev.extensao_de("text/html; charset=iso-8859-1") == "html"
    assert ev.extensao_de("") == "bin"
    assert ev.eh_pdf("application/pdf") is True
    assert ev.eh_pdf("text/html") is False
    assert ev.eh_pdf(None) is False


def test_nome_e_pasta_sao_ordenaveis():
    q = datetime(2026, 8, 21, 9, 31, 5)
    assert ev.nome_base(conta_id="290", grupo="convencional", quando=q) == "093105_290_convencional"
    assert ev.pasta_do_dia("/base", q) == os.path.join("/base", "2026-08-21")


def test_limpar_antigos_respeita_o_prazo(tmp_path):
    base = tmp_path / "emitidos"
    for dia in ("2026-08-01", "2026-08-20", "2026-08-21"):
        (base / dia).mkdir(parents=True)
    (base / "nao-e-data").mkdir()
    apagadas = ev.limpar_antigos(str(base), dias=7, hoje=datetime(2026, 8, 21))
    assert apagadas == 1
    assert not (base / "2026-08-01").exists()
    assert (base / "2026-08-20").exists()
    assert (base / "nao-e-data").exists()


def test_limpar_antigos_com_prazo_zero_nao_apaga(tmp_path):
    base = tmp_path / "emitidos"
    (base / "2020-01-01").mkdir(parents=True)
    assert ev.limpar_antigos(str(base), dias=0, hoje=datetime(2026, 8, 21)) == 0
    assert (base / "2020-01-01").exists()
