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
    # sem a carga da erp_008 (o padrao destes testes): o historico vem do CSV congelado
    monkeypatch.setattr(r.execucao_job, "listar_historico", lambda ex, tipos, log=print: [])
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
    assert any("fonte BANCO (3 arquivo(s), 2 processados) + historico do CSV (0 so no CSV)" in l
               for l in robo._linhas)


def test_banco_soma_o_historico_do_csv(robo, monkeypatch):
    """O banco so conhece o que entrou desde 21/09/2026; um .RET antigo re-entregue, de mesmo
    nome, seria tratado como NOVO sem o historico do CSV (baixa em duplicidade)."""
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: {
        "dddd": {"nome_smart": "D.RET", "processado": "True"}})
    hashes, por_nome = robo.historico_controle(execucao="EX")
    assert hashes == {"dddd", "aaaa"}, "aaaa vem do CSV (processado=True); bbbb nao (False)"
    assert por_nome == {"D.RET": {"dddd"}, "A.RET": {"aaaa"}, "B.RET": {"bbbb"}}
    assert any("+ historico do CSV (1 so no CSV)" in l for l in robo._linhas)


def test_banco_indisponivel_volta_ao_csv_e_avisa(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: None)
    hashes, _ = robo.historico_controle(execucao=None)
    assert hashes == {"aaaa"}
    assert any("indisponivel" in l for l in robo._linhas)


def test_com_o_historico_no_banco_o_csv_nao_e_lido(robo, monkeypatch):
    """Depois da carga da erp_008 o historico vem de arquivo_historico: o CSV (aaaa/bbbb)
    nem e aberto, e a memoria continua completa."""
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: {
        "dddd": {"nome_smart": "D.RET", "processado": "True"}})
    pedidos = []
    monkeypatch.setattr(robo.execucao_job, "listar_historico", lambda ex, tipos, log=print: (
        pedidos.append(tuple(tipos)) or [
            {"md5": "eeee", "detalhe": {"processado": True, "nomes_smart": ["E.RET"]}},
            {"md5": "ffff", "detalhe": {"processado": False, "nomes_smart": ["E.RET", "F.RET"]}}]))
    monkeypatch.setattr(robo, "historico_controle_do_csv",
                        lambda: pytest.fail("com o historico no banco o CSV nao e lido"))
    hashes, por_nome = robo.historico_controle(execucao="EX")
    assert hashes == {"dddd", "eeee"}
    assert por_nome == {"D.RET": {"dddd"}, "E.RET": {"eeee", "ffff"}, "F.RET": {"ffff"}}
    assert pedidos == [("retorno_cobranca_cnab_400", "retorno_bb")]
    assert any("+ historico no banco (1 so no historico)" in l for l in robo._linhas)


def test_historico_sem_resposta_do_banco_le_o_csv(robo, monkeypatch):
    monkeypatch.setattr(robo.cfg, "CONTROLE_FONTE", "banco")
    monkeypatch.setattr(robo.execucao_job, "listar_controle", lambda ex, fam, chave, log=print: {})
    monkeypatch.setattr(robo.execucao_job, "listar_historico", lambda ex, tipos, log=print: None)
    hashes, _ = robo.historico_controle(execucao="EX")
    assert hashes == {"aaaa"} and any("historico do CSV" in l for l in robo._linhas)
