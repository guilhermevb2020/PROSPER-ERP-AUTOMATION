# -*- coding: utf-8 -*-
"""ler_controle()/_ler_controle() da remessa de cobranca: csv (padrao), banco, indisponivel.

Em `banco`, `ler_controle` e {id: linha} da vw_controle_remessa e `_ler_controle` (o do
cancelamento) reagrupa por arquivo, com varios ids por nome — o formato que
`cancelar.entrada_do_controle` espera. Sem `execucao`, usam a aberta no processo.
"""
from __future__ import annotations

import csv
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="remessa_fonte_"))
for var, sub in (("ARQ_CONTROLE", "controle.csv"), ("PASTA_REMESSAS", "remessas"),
                 ("USER_DATA_DIR_REM", "perfil"), ("DEBUG_DIR_REM", "debug"),
                 ("ARQ_EXCLUSOES_REM", "exclusoes.json"), ("PASTA_FALHAS_REM", "falhas"),
                 ("ARQ_REMESSAS_GERADAS_REM", "remessas_geradas.json")):
    os.environ.setdefault(var, str(_TMP / sub))

RAIZ = Path(__file__).resolve().parents[2]
ROBO = RAIZ / "src/processors/web/remessa_cobranca"
_COLIDEM = ("gerar", "_nextcloud", "_sessao", "login", "cancelar", "falhas", "exclusoes", "analise")


def _importar_isolado():
    havia = {k: sys.modules.pop(k) for k in _COLIDEM if k in sys.modules}
    sys.path.insert(0, str(ROBO))
    try:
        return importlib.import_module("gerar_remessa_cobranca")
    finally:
        sys.path.remove(str(ROBO))
        for k in _COLIDEM:
            sys.modules.pop(k, None)
        sys.modules.update(havia)


robo = _importar_isolado()


@pytest.fixture
def arquivos(monkeypatch, tmp_path):
    monkeypatch.setattr(robo.cfg, "ARQ_CONTROLE", str(tmp_path / "controle.csv"))
    monkeypatch.setattr(robo.cfg, "ARQ_REMESSAS_GERADAS", str(tmp_path / "remessas_geradas.json"))
    with open(robo.cfg.ARQ_CONTROLE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "arquivo", "tipo", "bytes", "md5", "titulos", "baixado_em"])
        w.writerow(["26381", "CB2109000010.REM", "mp prospere Envio de cobranca registrado", "24800", "abc", "60", "2026-09-15 18:05:00"])
    (tmp_path / "remessas_geradas.json").write_text(json.dumps(
        {"CB2109000010.REM": [{"id": "26381", "tipo": "mp prospere Envio de cobranca registrado", "baixado_em": "2026-09-15 18:05:00"}]}))
    linhas = []
    monkeypatch.setattr(robo, "log", lambda m: linhas.append(m))
    return linhas


def test_padrao_e_csv_e_json(arquivos):
    assert robo.cfg.CONTROLE_FONTE == "csv"
    assert list(robo.ler_controle()) == ["26381"]
    assert list(robo._ler_controle()) == ["CB2109000010.REM"]


def test_banco_le_a_view_e_o_cancelamento_reagrupa_por_arquivo(arquivos, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    view = {"26381": {"arquivo": "CB2109000010.REM", "tipo": "mp prospere Envio de cobranca registrado",
                      "baixado_em": "2026-09-15 18:05:00", "md5": "abc", "bytes": "24800", "titulos": "60"},
            "26390": {"arquivo": "CB2109000010.REM", "tipo": "mp wj moreira Envio de cobranca registrado",
                      "baixado_em": "2026-09-16 18:05:00", "md5": "def", "bytes": "400", "titulos": "1"}}
    chamadas = []
    monkeypatch.setattr(robo.execucao_job, "atual", lambda: "EX-ATUAL")
    monkeypatch.setattr(robo.execucao_job, "listar_controle",
                        lambda ex, fam, chave, log=print: chamadas.append((ex, fam, chave)) or dict(view))
    assert set(robo.ler_controle()) == {"26381", "26390"}
    por_arquivo = robo._ler_controle(execucao="EX")
    assert [c["id"] for c in por_arquivo["CB2109000010.REM"]] == ["26381", "26390"]
    entrada = robo.cancelar.entrada_do_controle(por_arquivo, "CB2109000010.REM", 26390)
    assert entrada["tipo"].startswith("mp wj moreira") and entrada["baixado_em"] == "2026-09-16 18:05:00"
    assert chamadas == [("EX-ATUAL", "remessa", "id"), ("EX", "remessa", "id")]
    assert any("fonte BANCO (2 remessa" in l for l in arquivos)


def test_banco_indisponivel_volta_aos_arquivos_e_avisa(arquivos, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "atual", lambda: None)
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: None)
    assert list(robo.ler_controle()) == ["26381"]
    assert list(robo._ler_controle()) == ["CB2109000010.REM"]
    assert sum("indisponivel" in l for l in arquivos) == 2
