# -*- coding: utf-8 -*-
"""
test_contratos_fase3.py - Fase 3 de docs/PLANO_CONTROLE_NO_BANCO.md: as duas listas que o
process-automation manda para a remessa de cobranca (`cancelamentos.json`, `exclusoes.json`)
passam a poder vir de financeiro.remessa_*_apontad* (migration 543 do process-automation),
atras de CONTRATO_FONTE_REM=json|banco.

O que se prova, sem banco nem navegador:
- `execucao_job.ler_contrato` le a ULTIMA lista de PRODUCAO e devolve o payload (o mesmo JSON
  do arquivo); sem lista, sem banco ou com payload torto devolve None;
- a validade e a MESMA nas duas origens: `validar`/`validar_lista` sobre o dicionario dao o
  que `carregar`/`ler_lista` dao sobre o arquivo com o mesmo conteudo;
- a escolha da fonte: `json` nao toca no banco; `banco` usa o payload; banco indisponivel
  volta ao arquivo avisando; caminho explicito do cancelamento vale sobre a fonte.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="contratos_fase3_"))
for var, sub in (("ARQ_CONTROLE", "controle.csv"), ("PASTA_REMESSAS", "remessas"),
                 ("USER_DATA_DIR_REM", "perfil"), ("DEBUG_DIR_REM", "debug"),
                 ("ARQ_EXCLUSOES_REM", "exclusoes.json"), ("PASTA_FALHAS_REM", "falhas"),
                 ("ARQ_REMESSAS_GERADAS_REM", "remessas_geradas.json")):
    os.environ.setdefault(var, str(_TMP / sub))

RAIZ = Path(__file__).resolve().parents[2]
ROBO = RAIZ / "src/processors/web/remessa_cobranca"
_COLIDEM = ("gerar", "_nextcloud", "_sessao", "login", "cancelar", "falhas", "exclusoes", "analise")


def _importar_isolado():
    import importlib
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
exclusoes = robo.exclusoes
cancelar = robo.cancelar

from src.common.clients import execucao_job as ej  # noqa: E402

AGORA = datetime(2026, 9, 22, 18, 0, tzinfo=timezone(timedelta(hours=-3)))


def _lista_exclusoes(horas_atras=1, validade=30):
    gerado = AGORA - timedelta(hours=horas_atras)
    return {"versao": 1, "gerado_em": gerado.isoformat(), "validade_horas": validade,
            "titulos": {"934235": {"documento": "13274-001", "sacado_cnpj": "12.345.678/0001-90",
                                   "sacado": "TECNOMIDIA", "motivo": "endereco sem numero"}},
            "sacados": {"12345678000190": {"nome": "TECNOMIDIA"}}}


def _lista_cancelamentos(horas_atras=1, validade=12):
    gerado = AGORA - timedelta(hours=horas_atras)
    return {"versao": 1, "gerado_em": gerado.isoformat(), "validade_horas": validade,
            "remessas": {"26381": {"arquivo": "CB15090000021.REM", "tipo": "mp prospere",
                                   "motivo": "recusada pelo banco"}}}


# --------------------------------------------------------------------------- #
# ler_contrato
# --------------------------------------------------------------------------- #
class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.comandos.append((" ".join(sql.split()), params))
        self.ultimo = sql

    def fetchone(self):
        if "RETURNING id" in (self.ultimo or ""):
            self.conn.proximo_id += 1
            return (self.conn.proximo_id,)
        return (None,)

    def fetchall(self):
        return self.conn.linhas


class _Conn:
    def __init__(self, linhas):
        self.linhas = linhas
        self.comandos = []
        self.proximo_id = 500

    def cursor(self):
        return _Cursor(self)

    def close(self):
        pass


def _execucao(monkeypatch, linhas):
    conn = _Conn(linhas)
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    for var in ("HUB_RUN_ID", "HUB_TASK_NOME", "ERP_AUTOMATION_REVISION"):
        monkeypatch.delenv(var, raising=False)
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400",
                           flag_ensaio=False, gatilho="cron", obrigatoria=True)
    return ex, conn


def test_ler_contrato_devolve_o_payload_da_ultima_lista_de_producao(monkeypatch):
    lista = _lista_exclusoes()
    ex, conn = _execucao(monkeypatch, [(2, lista)])
    assert ej.ler_contrato(ex, "exclusoes") == lista
    sql, params = conn.comandos[-1]
    assert "FROM financeiro.remessa_exclusao_apontada" in sql
    assert "ambiente = 'producao'" in sql and "ORDER BY gerado_em DESC, id DESC LIMIT 1" in sql
    assert params == ()


def test_ler_contrato_do_cancelamento_le_a_tabela_dele(monkeypatch):
    ex, conn = _execucao(monkeypatch, [(1, _lista_cancelamentos())])
    assert ej.ler_contrato(ex, "cancelamentos")["remessas"]
    assert "FROM financeiro.remessa_cancelamento_apontado" in conn.comandos[-1][0]


def test_ler_contrato_aceita_payload_em_texto(monkeypatch):
    lista = _lista_exclusoes()
    ex, _ = _execucao(monkeypatch, [(2, json.dumps(lista))])
    assert ej.ler_contrato(ex, "exclusoes") == lista


def test_ler_contrato_sem_lista_payload_torto_ou_sem_execucao_devolve_none(monkeypatch):
    ex, conn = _execucao(monkeypatch, [])
    assert ej.ler_contrato(ex, "exclusoes") is None
    conn.linhas = [(3, "nao e json")]
    assert ej.ler_contrato(ex, "exclusoes") is None
    conn.linhas = [(4, ["lista", "e", "nao", "objeto"])]
    assert ej.ler_contrato(ex, "exclusoes") is None
    assert ej.ler_contrato(None, "exclusoes") is None


def test_ler_contrato_recusa_contrato_desconhecido(monkeypatch):
    ex, _ = _execucao(monkeypatch, [])
    with pytest.raises(ValueError):
        ej.ler_contrato(ex, "outra_coisa")


# --------------------------------------------------------------------------- #
# a validade e a mesma nas duas origens
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("horas_atras, esperado_valida", [(1, True), (29, True), (31, False)])
def test_exclusoes_validar_e_carregar_dao_o_mesmo_resultado(tmp_path, horas_atras, esperado_valida):
    lista = _lista_exclusoes(horas_atras=horas_atras)
    arq = tmp_path / "exclusoes.json"
    arq.write_text(json.dumps(lista), encoding="utf-8")
    msgs_arq, msgs_banco = [], []
    do_arquivo = exclusoes.carregar(str(arq), agora=AGORA, log=msgs_arq.append)
    do_banco = exclusoes.validar(lista, "financeiro.remessa_exclusao_apontada", agora=AGORA,
                                 log=msgs_banco.append)
    assert (do_arquivo is not None) is esperado_valida
    assert do_arquivo == do_banco
    if not esperado_valida:
        assert "IGNORADA" in msgs_arq[-1] and "IGNORADA" in msgs_banco[-1]


def test_exclusoes_validar_recusa_lista_sem_gerado_em():
    msgs = []
    assert exclusoes.validar({"titulos": {}}, "banco", agora=AGORA, log=msgs.append) is None
    assert "ilegivel em banco" in msgs[-1]


@pytest.mark.parametrize("horas_atras, executa", [(1, True), (11, True), (13, False)])
def test_cancelar_validar_lista_e_ler_lista_dao_o_mesmo_resultado(tmp_path, horas_atras, executa):
    lista = _lista_cancelamentos(horas_atras=horas_atras)
    arq = tmp_path / "cancelamentos.json"
    arq.write_text(json.dumps(lista), encoding="utf-8")
    do_arquivo = cancelar.ler_lista(str(arq), agora=AGORA)
    do_banco = cancelar.validar_lista(lista, agora=AGORA)
    assert do_arquivo == do_banco
    assert bool(do_banco[0]) is executa
    if not executa:
        assert "VENCIDA" in do_banco[1]


def test_cancelar_validar_lista_recusa_o_que_nao_e_objeto():
    remessas, motivo = cancelar.validar_lista(["torta"], agora=AGORA)
    assert remessas == {} and "formato inesperado" in motivo


# --------------------------------------------------------------------------- #
# a escolha da fonte na remessa
# --------------------------------------------------------------------------- #
@pytest.fixture
def fonte(monkeypatch):
    """Grava as chamadas; `payload` e o que o banco devolve (None = banco indisponivel)."""
    reg = {"ler_contrato": [], "carregar": 0, "ler_lista": [], "log": [], "payload": None}

    def _ler_contrato(ex, contrato, log=print):
        reg["ler_contrato"].append((ex, contrato))
        return reg["payload"]

    def _carregar(log=print):
        reg["carregar"] += 1
        return {"do": "arquivo"}

    def _ler_lista(caminho, agora=None):
        reg["ler_lista"].append(caminho)
        return {"do": "arquivo"}, ""

    monkeypatch.setattr(robo.execucao_job, "ler_contrato", _ler_contrato)
    monkeypatch.setattr(robo.execucao_job, "atual", lambda: "EX")
    monkeypatch.setattr(robo.exclusoes, "carregar", _carregar)
    monkeypatch.setattr(robo.cancelar, "ler_lista", _ler_lista)
    monkeypatch.setattr(robo, "log", reg["log"].append)
    return reg


def test_fonte_json_nao_toca_no_banco(fonte):
    assert robo.lista_de_exclusoes(fonte="json") == {"do": "arquivo"}
    assert robo.lista_de_cancelamentos(fonte="json") == ({"do": "arquivo"}, "")
    assert fonte["ler_contrato"] == [] and fonte["carregar"] == 1
    assert fonte["ler_lista"] == [robo.cancelar.ARQUIVO_PADRAO]


def test_fonte_banco_usa_o_payload_com_a_mesma_validade(fonte, monkeypatch):
    lista = _lista_exclusoes(horas_atras=1)
    fonte["payload"] = lista
    monkeypatch.setattr(robo.exclusoes, "validar",
                        lambda l, origem, agora=None, log=print: ("validada", origem, l))
    assert robo.lista_de_exclusoes(fonte="banco") == ("validada", "financeiro.remessa_exclusao_apontada", lista)
    assert fonte["ler_contrato"] == [("EX", "exclusoes")] and fonte["carregar"] == 0
    assert "exclusoes: fonte BANCO (financeiro.remessa_exclusao_apontada)" in fonte["log"]

    cancel = _lista_cancelamentos(horas_atras=1)
    fonte["payload"] = cancel
    monkeypatch.setattr(robo.cancelar, "validar_lista", lambda dados, agora=None: ("cancel-validada", dados))
    assert robo.lista_de_cancelamentos(fonte="banco") == ("cancel-validada", cancel)
    assert fonte["ler_contrato"][-1] == ("EX", "cancelamentos") and fonte["ler_lista"] == []


def test_fonte_banco_indisponivel_volta_ao_arquivo_avisando(fonte):
    fonte["payload"] = None
    assert robo.lista_de_exclusoes(fonte="banco") == {"do": "arquivo"}
    assert robo.lista_de_cancelamentos(fonte="banco") == ({"do": "arquivo"}, "")
    assert any("fonte BANCO indisponivel" in m for m in fonte["log"])
    assert fonte["carregar"] == 1 and fonte["ler_lista"] == [robo.cancelar.ARQUIVO_PADRAO]


def test_caminho_explicito_do_cancelamento_vale_sobre_a_fonte(fonte):
    fonte["payload"] = _lista_cancelamentos()
    assert robo.lista_de_cancelamentos("/tmp/outra.json", fonte="banco") == ({"do": "arquivo"}, "")
    assert fonte["ler_lista"] == ["/tmp/outra.json"] and fonte["ler_contrato"] == []


def test_fonte_desconhecida_usa_o_arquivo_e_avisa(fonte):
    assert robo.lista_de_exclusoes(fonte="planilha") == {"do": "arquivo"}
    assert any("desconhecida" in m for m in fonte["log"]) and fonte["ler_contrato"] == []


def test_a_chave_padrao_e_json():
    assert robo.cfg.CONTRATO_FONTE in ("json", "banco")
    assert os.environ.get("CONTRATO_FONTE_REM") or robo.cfg.CONTRATO_FONTE == "json"
