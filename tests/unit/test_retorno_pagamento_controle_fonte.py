# -*- coding: utf-8 -*-
"""
test_retorno_pagamento_controle_fonte.py - de onde vem o "ja tratei" (Fase 2, passo 1).

CONTROLE_FONTE_RETPAG=csv (padrao) le o controle.csv como sempre; =banco le os md5
registrados em erp_automation.arquivo pelo cliente de execucao, e volta ao CSV avisando
quando o banco nao responde. O cliente e um duble; o modulo do robo e importado de
verdade, com os caminhos apontando para uma pasta temporaria.
"""
from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
ROBO = RAIZ / "src/processors/web/retorno_pagamento"


#: Nomes curtos que existem em mais de um job (`_nextcloud`, `_sessao`, `login`...): se
#: outro teste os deixou em sys.modules, este modulo importaria o `_nextcloud` da remessa
#: de pagamento — medido em 22/09/2026 (sem `listar_pendentes`). Import isolado: o que
#: havia volta ao fim, o que este fixture trouxe sai.
_COLIDEM = ("_nextcloud", "_sessao", "login", "retorno_pagamento_config", "processar_retorno_pagamento")


@pytest.fixture
def robo(monkeypatch, tmp_path):
    monkeypatch.setenv("ARQ_CONTROLE_RETPAG", str(tmp_path / "controle.csv"))
    monkeypatch.setenv("USER_DATA_DIR_RETPAG", str(tmp_path / "perfil"))
    monkeypatch.setenv("DEBUG_DIR_RETPAG", str(tmp_path / "debug"))
    havia = {k: sys.modules.pop(k) for k in _COLIDEM if k in sys.modules}
    sys.path.insert(0, str(ROBO))
    try:
        cfg = importlib.import_module("retorno_pagamento_config")
        r = importlib.import_module("processar_retorno_pagamento")
    finally:
        sys.path.remove(str(ROBO))
    linhas = []
    monkeypatch.setattr(r, "log", lambda m: linhas.append(m))
    r._linhas = linhas
    with open(cfg.ARQ_CONTROLE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arquivo", "hash", "status_http", "quando"])
        w.writerow(["A.RET", "aaaa", "200", "2026-09-22 09:18:14"])
    yield r
    for k in _COLIDEM:
        sys.modules.pop(k, None)
    sys.modules.update(havia)


def test_padrao_e_csv(robo):
    assert robo.cfg.CONTROLE_FONTE == "csv"
    assert robo.hashes_ja_tratados(execucao="EX") == {"aaaa"}


def test_banco_le_os_md5_registrados(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    chamadas = []
    monkeypatch.setattr(robo.execucao_job, "listar_md5",
                        lambda ex, tipo, log=print: chamadas.append((ex, tipo)) or {"bbbb", "cccc"})
    assert robo.hashes_ja_tratados(execucao="EX") == {"bbbb", "cccc"}
    assert chamadas == [("EX", "retorno_pagamento_cnab_240")]
    assert any("fonte BANCO (2 hash" in l for l in robo._linhas)


def test_banco_indisponivel_volta_ao_csv_e_avisa(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_md5", lambda ex, tipo, log=print: None)
    assert robo.hashes_ja_tratados(execucao=None) == {"aaaa"}
    assert any("indisponivel" in l and "CSV de reserva" in l for l in robo._linhas)


def test_fonte_desconhecida_usa_o_csv_e_diz(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "xml")
    assert robo.hashes_ja_tratados() == {"aaaa"}
    assert any("desconhecida" in l for l in robo._linhas)


def test_a_rodada_passa_a_execucao_para_o_controle(robo, monkeypatch):
    """`rodada` e quem tem a execucao aberta; e ela que a entrega ao controle."""
    from types import SimpleNamespace
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_md5", lambda ex, tipo, log=print: {"aaaa"} if ex == "EX" else set())
    monkeypatch.setattr(robo.nuvem, "listar_pendentes", lambda: ["A.RET"])
    vistos = []
    monkeypatch.setattr(robo, "tratar", lambda ctx, nome, dry, feitos, execucao=None: vistos.append(feitos) or "ok")
    args = SimpleNamespace(arquivo=None, limite=None, listar=False)
    assert robo.rodada(object(), args, True, execucao="EX") == robo.SAIU_OK
    assert vistos == [{"aaaa"}]
