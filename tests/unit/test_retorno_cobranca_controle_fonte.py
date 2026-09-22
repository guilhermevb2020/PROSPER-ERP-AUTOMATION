# -*- coding: utf-8 -*-
"""historico_controle() do retorno de cobranca: csv (padrao), banco, banco indisponivel.

Do banco vem uma linha por arquivo (a view): `processado` = o ultimo evento foi
'processado'. O par devolvido e o mesmo do CSV: (hashes processados, nome -> {hashes}).
"""
from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
ROBO = RAIZ / "src/processors/web/retorno_cobranca"
_COLIDEM = ("retorno_config", "processar_retorno_cobranca")


@pytest.fixture
def robo(monkeypatch, tmp_path):
    monkeypatch.setenv("ARQ_CONTROLE_RET", str(tmp_path / "controle.csv"))
    monkeypatch.setenv("USER_DATA_DIR_RET", str(tmp_path / "perfil"))
    monkeypatch.setenv("DEBUG_DIR_RET", str(tmp_path / "debug"))
    monkeypatch.setenv("PASTA_ENTRADA_RET", str(tmp_path / "entrada"))
    havia = {k: sys.modules.pop(k) for k in _COLIDEM if k in sys.modules}
    sys.path.insert(0, str(ROBO))
    try:
        cfg = importlib.import_module("retorno_config")
        r = importlib.import_module("processar_retorno_cobranca")
    finally:
        sys.path.remove(str(ROBO))
    linhas = []
    monkeypatch.setattr(r, "log", lambda m: linhas.append(m))
    r._linhas = linhas
    with open(cfg.ARQ_CONTROLE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arquivo", "nome_smart", "hash", "conta", "titulos", "ja_processado", "processado",
                    "ocorrencias", "criticas", "divergencias", "motivo", "quando"])
        w.writerow(["A.RET", "A.RET", "aaaa", "291", "3", "False", "True", "", "0", "", "OK", "2026-09-22 08:50:00"])
        w.writerow(["B.RET", "B.RET", "bbbb", "291", "1", "False", "False", "", "0", "", "RECUSADO", "2026-09-22 08:51:00"])
    yield r
    for k in _COLIDEM:
        sys.modules.pop(k, None)
    sys.modules.update(havia)


def test_padrao_e_csv(robo):
    assert robo.cfg.CONTROLE_FONTE == "csv"
    hashes, por_nome = robo.historico_controle(execucao="EX")
    assert hashes == {"aaaa"} and por_nome == {"A.RET": {"aaaa"}, "B.RET": {"bbbb"}}


def test_banco_monta_o_mesmo_par_a_partir_da_view(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: {
        "aaaa": {"nome_smart": "A.RET", "processado": "True"},
        "bbbb": {"nome_smart": "B.RET", "processado": "False"},
        "cccc": {"nome_smart": "A.RET", "processado": "True"},   # mesmo nome, outro conteudo
    })
    hashes, por_nome = robo.historico_controle(execucao="EX")
    assert hashes == {"aaaa", "cccc"}
    assert por_nome == {"A.RET": {"aaaa", "cccc"}, "B.RET": {"bbbb"}}
    assert any("fonte BANCO (3 arquivo" in l and "2 processados" in l for l in robo._linhas)


def test_banco_indisponivel_volta_ao_csv_e_avisa(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: None)
    hashes, _ = robo.historico_controle(execucao=None)
    assert hashes == {"aaaa"}
    assert any("indisponivel" in l for l in robo._linhas)
