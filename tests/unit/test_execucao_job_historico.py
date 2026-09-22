# -*- coding: utf-8 -*-
"""O historico dos CSVs no banco (erp_008) e a memoria de eventos de operacao, pelo
cliente: listar_md5 une as duas tabelas quando a erp_008 existe, historico_carregado diz
se o CSV ainda precisa ser lido, e a carga recusa dado torto antes de tocar no banco.
Sem banco: duble que responde por trecho de SQL."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.common.clients import execucao_job as ej
from test_execucao_job import _Conn, _Cursor


class _CursorRespostas(_Cursor):
    def fetchall(self):
        for trecho, linhas in self._conn.respostas.items():
            if trecho in self._ultimo:
                return linhas
        return []


class _ConnRespostas(_Conn):
    def __init__(self):
        super().__init__()
        self.respostas = {}

    def cursor(self):
        return _CursorRespostas(self)


@pytest.fixture
def banco(monkeypatch):
    conn = _ConnRespostas()
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    for var in ("HUB_RUN_ID", "HUB_TASK_NOME", "ERP_AUTOMATION_REVISION"):
        monkeypatch.delenv(var, raising=False)
    return conn


def _ex(ensaio=True):
    return ej.abrir_execucao("retorno_cobranca", "processar_retorno_cobranca_cnab_400",
                             flag_ensaio=ensaio, obrigatoria=not ensaio, log=lambda m: None)


def _silencio(m):
    pass


def test_listar_md5_une_o_historico_quando_a_erp_008_existe(banco):
    banco.respostas = {"to_regclass": [(True,)], "SELECT md5 FROM erp_automation.arquivo": [("AAAA",)]}
    assert ej.listar_md5(_ex(), "retorno_bb", log=_silencio) == {"aaaa"}
    sql, params = banco.comandos[-1]
    assert "UNION SELECT md5 FROM erp_automation.arquivo_historico" in sql
    assert params == ("retorno_bb", "retorno_bb")


def test_listar_md5_sem_a_erp_008_le_so_arquivo(banco):
    banco.respostas = {"to_regclass": [(False,)], "SELECT md5 FROM erp_automation.arquivo": [("AAAA",)]}
    assert ej.listar_md5(_ex(), "retorno_bb", log=_silencio) == {"aaaa"}
    sql, params = banco.comandos[-1]
    assert "arquivo_historico" not in sql and params == ("retorno_bb",)


def test_historico_carregado_distingue_sem_tabela_sem_linhas_e_sem_banco(banco, monkeypatch):
    banco.respostas = {"to_regclass": [(False,)]}
    assert ej.historico_carregado(_ex(), ["retorno_bb"], log=_silencio) is False
    banco.respostas = {"to_regclass": [(True,)], "SELECT EXISTS": [(False,)]}
    assert ej.historico_carregado(_ex(), ["retorno_bb"], log=_silencio) is False
    banco.respostas = {"to_regclass": [(True,)], "SELECT EXISTS": [(True,)]}
    ex = _ex()
    assert ej.historico_carregado(ex, ("retorno_bb", "retorno_cobranca_cnab_400"), log=_silencio) is True
    assert banco.comandos[-1][1] == (["retorno_bb", "retorno_cobranca_cnab_400"],)
    assert ej.historico_carregado(None, ["retorno_bb"]) is None
    banco.falhar_em = "to_regclass"
    assert ej.historico_carregado(_ex(ensaio=False), ["retorno_bb"], log=_silencio) is None
    with pytest.raises(ValueError):
        ej.historico_carregado(ex, ["exportacao_csv"])


def test_listar_historico_devolve_o_detalhe_como_dicionario(banco):
    quando = datetime(2026, 8, 21, 13, 0, tzinfo=timezone.utc)
    banco.respostas = {"to_regclass": [(True,)],
                       "FROM erp_automation.arquivo_historico": [
                           ("retorno_bb", "ABCD", "x.ret", quando, json.dumps({"processado": True})),
                           ("retorno_cobranca_cnab_400", "ef01", "y.RET", None, {"nomes_smart": ["Y"]})]}
    linhas = ej.listar_historico(_ex(), ["retorno_bb", "retorno_cobranca_cnab_400"], log=_silencio)
    assert linhas[0] == {"tipo_arquivo": "retorno_bb", "md5": "abcd", "nome_arquivo": "x.ret",
                         "tratado_em": quando, "detalhe": {"processado": True}}
    assert linhas[1]["detalhe"] == {"nomes_smart": ["Y"]}
    banco.respostas = {"to_regclass": [(False,)]}
    assert ej.listar_historico(_ex(), "retorno_bb", log=_silencio) == []


def test_listar_eventos_operacao_filtra_por_tipo_e_por_op(banco):
    quando = datetime(2026, 9, 22, 16, 50, tzinfo=timezone.utc)
    banco.respostas = {"FROM erp_automation.operacao_evento": [
        (65879, "documentos_baixados", "OK", quando, {"resumo_ok": True})]}
    ex = _ex()
    eventos = ej.listar_eventos_operacao(ex, ("documentos_baixados", "etapa_movida"),
                                         ops=["65879", "x", 65880], log=_silencio)
    assert eventos == [{"id_operacao": 65879, "tipo_evento": "documentos_baixados",
                        "resultado": "OK", "ocorrido_em": quando, "detalhe": {"resumo_ok": True}}]
    sql, params = banco.comandos[-1]
    assert "id_operacao = ANY(%s)" in sql and "ORDER BY ocorrido_em, id" in sql
    assert params == (["documentos_baixados", "etapa_movida"], [65879, 65880])
    assert ej.listar_eventos_operacao(ex, "aviso_enviado", ops=["nada"]) == []
    assert ej.listar_eventos_operacao(None, "aviso_enviado") is None
    with pytest.raises(ValueError):
        ej.listar_eventos_operacao(ex, "evento_que_nao_existe")


def test_listar_eventos_sem_banco_devolve_none(banco):
    banco.falhar_em = "FROM erp_automation.operacao_evento"
    assert ej.listar_eventos_operacao(_ex(ensaio=False), "aviso_enviado", ops=[1],
                                      log=_silencio) is None


def test_carga_recusa_dado_torto_antes_de_tocar_no_banco(banco):
    ex = _ex(ensaio=False)
    ok = {"tipo_arquivo": "retorno_bb", "md5": "0" * 32, "nome_arquivo": "a", "origem": "c.csv"}
    for torto, erro in (({**ok, "tipo_arquivo": "exportacao_csv"}, "sem historico"),
                        ({**ok, "md5": "nao-e-md5"}, "md5 invalido"),
                        ({**ok, "origem": ""}, "origem obrigatoria")):
        with pytest.raises(ValueError, match=erro):
            ej.carregar_historico_arquivos(ex, [ok, torto])
    evento = {"id_operacao": 1, "tipo_evento": "documentos_baixados",
              "ocorrido_em": datetime.now(timezone.utc), "detalhe": {"origem": "c.csv"}}
    with pytest.raises(ValueError, match="origem"):
        ej.carregar_historico_eventos(ex, [{**evento, "detalhe": {}}])
    with pytest.raises(ValueError, match="tipo_evento"):
        ej.carregar_historico_eventos(ex, [{**evento, "tipo_evento": "outro"}])
    assert not any("historico" in c[0] or "INSERT INTO erp_automation.operacao_evento" in c[0]
                   for c in banco.comandos)
    assert ej.carregar_historico_arquivos(ex, []) == 0 and ej.carregar_historico_eventos(ex, []) == 0


def test_carga_exige_execucao_com_banco(banco, monkeypatch):
    with pytest.raises(ej.ErroDeRegistro):
        ej.carregar_historico_arquivos(None, [])
    monkeypatch.setattr(ej, "_conectar", lambda job: (_ for _ in ()).throw(RuntimeError("fora")))
    ex = ej.abrir_execucao("controle", "carregar_historico_csv", flag_ensaio=True, log=_silencio)
    with pytest.raises(ej.ErroDeRegistro):
        ej.carregar_historico_eventos(ex, [])
