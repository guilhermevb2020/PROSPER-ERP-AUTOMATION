# -*- coding: utf-8 -*-
"""ler_controle() da remessa de pagamento: csv (padrao), banco, banco indisponivel."""
from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
ROBO = RAIZ / "src/processors/web/remessa_pagamento"
_COLIDEM = ("_nextcloud", "_sessao", "login", "gerar", "analise", "pagamento_config",
            "gerar_remessa_pagamento")


@pytest.fixture
def robo(monkeypatch, tmp_path):
    for var, sub in (("ARQ_CONTROLE_PAG", "controle.csv"), ("PASTA_SAIDA_PAG", "saida"),
                     ("USER_DATA_DIR_PAG", "perfil"), ("DEBUG_DIR_PAG", "debug")):
        monkeypatch.setenv(var, str(tmp_path / sub))
    havia = {k: sys.modules.pop(k) for k in _COLIDEM if k in sys.modules}
    sys.path.insert(0, str(ROBO))
    try:
        cfg = importlib.import_module("pagamento_config")
        r = importlib.import_module("gerar_remessa_pagamento")
    finally:
        sys.path.remove(str(ROBO))
    linhas = []
    monkeypatch.setattr(r, "log", lambda m: linhas.append(m))
    r._linhas = linhas
    with open(cfg.ARQ_CONTROLE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arquivo", "bytes", "md5", "titulos", "ids", "pix", "quando"])
        w.writerow(["CP2209000409.REM", "1452", "6fa597", "1", "1001", "1", "2026-09-22 09:15:14"])
    yield r
    for k in _COLIDEM:
        sys.modules.pop(k, None)
    sys.modules.update(havia)


def test_padrao_e_csv(robo):
    assert robo.cfg.CONTROLE_FONTE == "csv"
    c = robo.ler_controle(execucao="EX")
    assert list(c) == ["6fa597"] and c["6fa597"]["arquivo"] == "CP2209000409.REM"


def test_banco_le_a_view_no_formato_do_csv(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    chamadas = []
    monkeypatch.setattr(robo.execucao_job, "listar_controle",
                        lambda ex, fam, chave, log=print: chamadas.append((ex, fam, chave)) or
                        {"ab12": {"arquivo": "CP2209000410.REM", "quando": "2026-09-22 10:00:00"}})
    c = robo.ler_controle(execucao="EX")
    assert c["ab12"]["arquivo"] == "CP2209000410.REM"
    assert chamadas == [("EX", "pagamento", "md5")]
    assert any("fonte BANCO (1 remessa" in l for l in robo._linhas)


def test_banco_indisponivel_volta_ao_csv_e_avisa(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: None)
    assert list(robo.ler_controle(execucao=None)) == ["6fa597"]
    assert any("indisponivel" in l for l in robo._linhas)
