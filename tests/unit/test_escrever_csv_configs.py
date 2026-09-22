# -*- coding: utf-8 -*-
"""Fase 4: os quatro configs expoem ESCREVER_CSV, True por padrao, e obedecem a chave
propria (ESCREVER_CSV_<SUF>) e a global (ESCREVER_CSV)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CONFIGS = [
    ("retorno_cobranca", "retorno_config", "ESCREVER_CSV_RET"),
    ("retorno_pagamento", "retorno_pagamento_config", "ESCREVER_CSV_RETPAG"),
    ("remessa_pagamento", "pagamento_config", "ESCREVER_CSV_PAG"),
    ("remessa_cobranca", "remessa_config", "ESCREVER_CSV_REM"),
]
_ENV_TMP = {"ARQ_CONTROLE_RET": "controle.csv", "USER_DATA_DIR_RET": "p", "DEBUG_DIR_RET": "d", "PASTA_ENTRADA_RET": "e",
            "ARQ_CONTROLE_RETPAG": "c.csv", "USER_DATA_DIR_RETPAG": "p", "DEBUG_DIR_RETPAG": "d",
            "ARQ_CONTROLE_PAG": "c.csv", "PASTA_SAIDA_PAG": "s", "USER_DATA_DIR_PAG": "p", "DEBUG_DIR_PAG": "d",
            "ARQ_CONTROLE": "c.csv", "PASTA_REMESSAS": "r", "USER_DATA_DIR_REM": "p", "DEBUG_DIR_REM": "d",
            "ARQ_EXCLUSOES_REM": "x.json", "PASTA_FALHAS_REM": "f", "ARQ_REMESSAS_GERADAS_REM": "g.json"}


def _config(monkeypatch, tmp_path, pasta, modulo, extra):
    for k, v in _ENV_TMP.items():
        monkeypatch.setenv(k, str(tmp_path / v))
    for k, v in extra.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop(modulo, None)
    caminho = str(RAIZ / "src/processors/web" / pasta)
    sys.path.insert(0, caminho)
    try:
        return importlib.import_module(modulo)
    finally:
        sys.path.remove(caminho)
        sys.modules.pop(modulo, None)


@pytest.mark.parametrize("pasta,modulo,chave", CONFIGS)
def test_padrao_true_e_chaves(monkeypatch, tmp_path, pasta, modulo, chave):
    monkeypatch.delenv("ESCREVER_CSV", raising=False)
    monkeypatch.delenv(chave, raising=False)
    assert _config(monkeypatch, tmp_path, pasta, modulo, {}).ESCREVER_CSV is True
    assert _config(monkeypatch, tmp_path, pasta, modulo, {chave: "False"}).ESCREVER_CSV is False
    assert _config(monkeypatch, tmp_path, pasta, modulo, {"ESCREVER_CSV": "False"}).ESCREVER_CSV is False
    assert _config(monkeypatch, tmp_path, pasta, modulo, {"ESCREVER_CSV": "False", chave: "True"}).ESCREVER_CSV is True
