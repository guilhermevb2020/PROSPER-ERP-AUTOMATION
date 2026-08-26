#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes do entrypoint e do ciclo do robo de pagamento.

POR QUE ESTES TESTES EXISTEM
----------------------------
O `ciclo()` decide o que acontece com dinheiro, e os quatro desfechos dele nao
sao equivalentes:

    nada pendente          -> exit 0. E o caso da MAIORIA das rodadas de 30 min.
    gerou e gravou         -> exit 0, com md5 no controle.
    DRY_RUN                -> exit 0, e NADA pode ter sido enviado.
    POST foi, sem arquivo  -> exit 6. Os titulos JA sairam da fila, entao a
                              proxima rodada dira "nada pendente" e ninguem
                              percebe sozinho. Este e o unico que precisa de gente.

Confundir o primeiro com o ultimo e a falha que este projeto mais documenta:
rodada que termina com cara de sucesso sem ter feito o trabalho.

O `ctx` e um duble. Nao ha rede, nao ha login, nao ha Smart — gerar remessa de
pagamento move dinheiro e nao entra em teste automatico.

AMBIENTE: precisa de `playwright` importavel (o `gerar.py` puxa `smart_sessao`,
que nao o importa, mas o `robo_pagamento.py` sim). Roda sob `.venv-sandbox`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="rode sob .venv-sandbox")

RAIZ = Path(__file__).resolve().parents[2]
for caminho in (RAIZ, RAIZ / "src" / "processors" / "web" / "robo_pagamento"):
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))

SMART = "https://wvw.smartsecurities.com.br/smart"

TELA_PESQUISA = """
<form name="carteira" method="POST" action="pagtobmpgrid.php">
  <input type="hidden" name="pesquisar" value="1">
  <select name="IdContaBancaria"><option value="404">mp prospere</option></select>
  <select name="pagtobmp"><option value="P">Pendente</option></select>
</form>
"""

GRADE_PENDENTE = """
<form name="multipagForm" method="POST" action="pagtobmpgrid.php">
  <input type="hidden" name="processar" value="0">
  <input type="hidden" name="IdContaBancaria" value="404">
  <input type="hidden" name="checkeds" value=""><input type="hidden" name="checkedsPIX" value="">
  <input type="hidden" name="todosCheckeds" value=""><input type="hidden" name="temPIX" value="">
  <input type="hidden" name="acao" value="0">
  <input type="checkbox" name="ckTitulo" value="143" data-tipopix="0">
  <input type="checkbox" name="ckTitulo" value="144" data-tipopix="1">
</form>
<button onclick="GerarMultipag(this, 1)"><span>Gerar Pagamento BMP Money Plus</span></button>
"""

GRADE_VAZIA = GRADE_PENDENTE.replace(
    '<input type="checkbox" name="ckTitulo" value="143" data-tipopix="0">', ""
).replace('<input type="checkbox" name="ckTitulo" value="144" data-tipopix="1">', "")

GRADE_GERADO = GRADE_PENDENTE.replace("GerarMultipag(this, 1)", "GerarMultipag(this, 3)") \
    .replace("Gerar Pagamento", "Cancelar Pagamento")

EXPIRA = ("<script>top.location.href='https://wvw.smartsecurities.com.br"
          "/smart/php/expira.php';</script>")

CNAB = ("\n".join("X" * 240 for _ in range(10))).encode("latin-1")


class _Resp:
    def __init__(self, corpo, status=200, headers=None):
        self.status = status
        self._c = corpo if isinstance(corpo, bytes) else corpo.encode("latin-1", "replace")
        self.headers = headers or {}

    def body(self):
        return self._c


class _Req:
    """Duble: `gets` responde ao GET; `posts` e uma FILA consumida por POST."""

    def __init__(self, gets, posts):
        self.gets, self.posts = gets, list(posts)
        self.enviados = []

    def get(self, url, timeout=None):
        return _Resp(self.gets)

    def post(self, url, data=None, headers=None, timeout=None):
        self.enviados.append((url, data))
        return self.posts.pop(0)


class Ctx:
    def __init__(self, gets=TELA_PESQUISA, posts=()):
        self.request = _Req(gets, posts)


@pytest.fixture
def robo(tmp_path, monkeypatch):
    """Config e modulos recarregados com as pastas no tmp."""
    for chave, sub in (("USER_DATA_DIR_PAG", "perfil"), ("PASTA_SAIDA_PAG", "saida"),
                       ("ARQ_CONTROLE_PAG", "controle.csv"), ("DEBUG_DIR_PAG", "debug")):
        monkeypatch.setenv(chave, str(tmp_path / sub))
    monkeypatch.setenv("PAGAMENTO_ENV_FILE", "/dev/null")
    import pagamento_config
    importlib.reload(pagamento_config)
    import analise
    import gerar
    importlib.reload(analise)
    importlib.reload(gerar)
    import robo_pagamento
    importlib.reload(robo_pagamento)
    return robo_pagamento, gerar, tmp_path


# --------------------------------------------------------------------------- #
# 1. nada pendente NAO e falha — e a maioria das rodadas
# --------------------------------------------------------------------------- #
def test_nada_pendente_nao_gera_e_nao_envia_nada(robo):
    _rp, ger, _tmp = robo
    ctx = Ctx(posts=[_Resp(GRADE_VAZIA)])
    r = ger.ciclo(ctx, dry_run=False, log=lambda _m: None)
    assert r["pendentes"] == 0 and r["gerou"] is False
    assert r["motivo"] == "nada pendente"
    # so o POST da PESQUISA saiu; nenhum POST de geracao
    assert len(ctx.request.enviados) == 1
    assert "processar=1" not in ctx.request.enviados[0][1]


# --------------------------------------------------------------------------- #
# 2. dry-run nao pode enviar
# --------------------------------------------------------------------------- #
def test_dry_run_monta_mas_nao_envia(robo):
    _rp, ger, _tmp = robo
    ctx = Ctx(posts=[_Resp(GRADE_PENDENTE)])
    r = ger.ciclo(ctx, dry_run=True, log=lambda _m: None)
    assert r["pendentes"] == 2 and r["motivo"] == "DRY_RUN"
    assert r["gerou"] is False and r["enviado"] is False
    assert len(ctx.request.enviados) == 1        # so a pesquisa


# --------------------------------------------------------------------------- #
# 3. o caminho feliz
# --------------------------------------------------------------------------- #
def test_gera_grava_com_o_nome_real_e_registra(robo):
    rp, ger, tmp = robo
    ctx = Ctx(posts=[
        _Resp(GRADE_PENDENTE),
        _Resp(CNAB, headers={"content-disposition": 'attachment; filename="CP2108000003.REM"',
                             "content-type": "application/octet-stream"}),
    ])
    r = ger.ciclo(ctx, dry_run=False, log=lambda _m: None)
    assert r["gerou"] is True and r["arquivo"] == "CP2108000003.REM"
    assert (tmp / "saida" / "CP2108000003.REM").read_bytes() == CNAB
    # o POST de geracao levou a separacao PIX correta
    _url, corpo = ctx.request.enviados[1]
    assert "checkeds=143%2C" in corpo and "checkedsPIX=144%2C" in corpo
    assert "acao=1" in corpo and "processar=1" in corpo

    rp.gravar_controle({"arquivo": r["arquivo"], "bytes": len(CNAB), "md5": r["md5"],
                        "titulos": 2, "ids": "143,144", "pix": 1, "quando": "agora"})
    assert r["md5"] in rp.ler_controle()


# --------------------------------------------------------------------------- #
# 4. os dois desfechos perigosos
# --------------------------------------------------------------------------- #
def test_post_foi_e_nao_veio_arquivo_nao_vira_sucesso(robo):
    """Os titulos ja sairam da fila: a proxima rodada dira 'nada pendente'."""
    _rp, ger, _tmp = robo
    ctx = Ctx(posts=[
        _Resp(GRADE_PENDENTE),
        _Resp("<html>erro inesperado</html>"),   # geracao
        _Resp(GRADE_VAZIA),                      # recuperacao: nada em GERADO
    ])
    r = ger.ciclo(ctx, dry_run=False, log=lambda _m: None)
    assert r["enviado"] is True and r["gerou"] is False
    assert "CONFERIR" in r["motivo"]


def test_sessao_caida_aborta_em_vez_de_dizer_nada_pendente(robo):
    """A armadilha nº 1: deslogado responde HTTP 200 com o expira.php."""
    _rp, ger, _tmp = robo
    ctx = Ctx(gets=EXPIRA)
    with pytest.raises(ger.SessaoCaiu):
        ger.ciclo(ctx, dry_run=False, log=lambda _m: None)


def test_grade_deslogada_no_post_tambem_aborta(robo):
    _rp, ger, _tmp = robo
    ctx = Ctx(posts=[_Resp(EXPIRA)])
    with pytest.raises(ger.SessaoCaiu):
        ger.ciclo(ctx, dry_run=False, log=lambda _m: None)


def test_grade_de_GERADO_nunca_e_gerada(robo):
    """⛔ La o unico botao e CANCELAR — o POST difere por um digito."""
    _rp, ger, _tmp = robo
    ctx = Ctx(posts=[_Resp(GRADE_GERADO)])
    with pytest.raises(ValueError, match="nao oferece a acao 1"):
        ger.ciclo(ctx, dry_run=False, log=lambda _m: None)
    assert len(ctx.request.enviados) == 1        # nao enviou geracao


# --------------------------------------------------------------------------- #
# 5. recuperacao pela grade de GERADO
# --------------------------------------------------------------------------- #
def test_recupera_o_arquivo_quando_o_post_nao_devolve(robo):
    _rp, ger, tmp = robo
    grade_com_arquivo = GRADE_PENDENTE + (
        '<td><a href="../mandarsispag.php?file=31">CP2108000031.REM</a></td>')
    ctx = Ctx(posts=[
        _Resp(GRADE_PENDENTE),
        _Resp("<html>sem arquivo</html>"),
        _Resp(grade_com_arquivo),                # grade de GERADO
    ])
    # o GET do download devolve o CNAB
    ctx.request.get = lambda url, timeout=None: (
        _Resp(CNAB, headers={"content-disposition":
                             'attachment; filename="CP2108000031.REM"'})
        if "mandarsispag" in url else _Resp(TELA_PESQUISA))
    r = ger.ciclo(ctx, dry_run=False, log=lambda _m: None)
    assert r["gerou"] is True and r["motivo"] == "recuperado pela grade de GERADO"
    assert (tmp / "saida" / "CP2108000031.REM").exists()


# --------------------------------------------------------------------------- #
# 6. controle
# --------------------------------------------------------------------------- #
def test_controle_com_cabecalho_antigo_e_arquivado(robo, tmp_path):
    """Anexar colunas novas num CSV velho desalinharia o arquivo inteiro."""
    rp, _ger, tmp = robo
    velho = tmp / "controle.csv"
    velho.parent.mkdir(parents=True, exist_ok=True)
    velho.write_text("arquivo,md5\nx.REM,abc\n", encoding="utf-8")
    rp.gravar_controle({"arquivo": "y.REM", "bytes": 1, "md5": "def", "titulos": 1,
                        "ids": "1", "pix": 0, "quando": "agora"})
    import csv as _csv
    with open(velho, encoding="utf-8", newline="") as f:
        assert next(_csv.reader(f)) == rp.CABECALHO_CONTROLE
    assert list(tmp.glob("controle.csv.*.bak")), "o antigo tinha de ser arquivado"
