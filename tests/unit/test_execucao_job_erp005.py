# -*- coding: utf-8 -*-
"""
test_execucao_job_erp005.py - o que o cliente ganhou com a erp_005, sem banco.

operador/motivo na abertura (e o INSERT repetido sem eles onde a migration ainda nao
chegou), a execucao "atual" do processo, as anotacoes que vao para o fechamento, a
busca de arquivo por chave e as duas variantes que faltavam: evento de arquivo ESTRITO
(intencao antes do POST) e evento de operacao como FATO (credito). O banco de verdade
e provado em tests/integration/test_erp_005_controle.py.
"""
from __future__ import annotations

import pytest

from src.common.clients import execucao_job as ej
from test_execucao_job import _Conn, _Cursor  # o mesmo duble da suite do cliente


class UndefinedColumn(Exception):
    """O nome que o psycopg2 da ao erro 42703; o cliente reconhece pelo nome."""


class _CursorSemErp005(_Cursor):
    def execute(self, sql, params=None):
        if "INSERT INTO erp_automation.job_execucao" in sql and "operador" in sql:
            self._conn.comandos.append((" ".join(sql.split()), params))
            raise UndefinedColumn('column "operador" of relation "job_execucao" does not exist')
        return super().execute(sql, params)


class _ConnSemErp005(_Conn):
    def cursor(self):
        return _CursorSemErp005(self)


@pytest.fixture
def banco(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.setattr(ej, "_ATUAL", None)
    for v in ("HUB_RUN_ID", "HUB_TASK_NOME", "ERP_OPERADOR", "ERP_MOTIVO"):
        monkeypatch.delenv(v, raising=False)
    return conn


def _insert_execucao(conn):
    sql, params = next(c for c in conn.comandos if "INSERT INTO erp_automation.job_execucao" in c[0])
    colunas = sql.split("(")[1].split(")")[0].replace(" ", "").split(",")
    return dict(zip(colunas, params))


# --------------------------------------------------------------------------- #
# operador e motivo
# --------------------------------------------------------------------------- #
def test_manual_registra_operador_e_motivo_do_ambiente(banco, monkeypatch):
    monkeypatch.setenv("ERP_OPERADOR", "guilherme")
    monkeypatch.setenv("ERP_MOTIVO", "reprocessar o retorno de 21/09")
    ex = ej.abrir_execucao("controle", "comparar_controle_csv_banco", flag_ensaio=False, log=lambda m: None)
    campos = _insert_execucao(banco)
    assert campos["gatilho"] == "manual"
    assert campos["operador"] == "guilherme"
    assert campos["motivo"] == "reprocessar o retorno de 21/09"
    assert ex.avisos == [], "com operador e motivo nao ha o que avisar"


def test_manual_real_sem_operador_abre_e_avisa(banco):
    """Desde que o hub se identifica (22/09/2026), manual e so quem rodou a mao: sem
    ERP_OPERADOR/ERP_MOTIVO em modo real a auditoria fica sem autor — avisa, nao barra."""
    ex = ej.abrir_execucao("controle", "comparar_controle_csv_banco", flag_ensaio=False, log=lambda m: None)
    assert ex.id == 101
    assert _insert_execucao(banco)["operador"] is None
    assert any("ERP_OPERADOR" in a for a in ex.avisos)


def test_manual_em_ensaio_nao_avisa(banco):
    ex = ej.abrir_execucao("controle", "comparar_controle_csv_banco", flag_ensaio=True, log=lambda m: None)
    assert ex.avisos == []


def test_cron_nao_tem_operador_mesmo_com_variavel(banco, monkeypatch):
    monkeypatch.setenv("HUB_RUN_ID", "123")
    monkeypatch.setenv("ERP_OPERADOR", "alguem")
    ex = ej.abrir_execucao("controle", "comparar_controle_csv_banco", flag_ensaio=False, log=lambda m: None)
    campos = _insert_execucao(banco)
    assert campos["gatilho"] == "cron" and campos["operador"] is None
    assert ex.avisos == []


def test_sem_erp_005_o_insert_repete_sem_operador_e_avisa(monkeypatch):
    conn = _ConnSemErp005()
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.setenv("ERP_OPERADOR", "guilherme")
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    ex = ej.abrir_execucao("controle", "comparar_controle_csv_banco", flag_ensaio=True,
                           obrigatoria=True, log=lambda m: None)
    inserts = [c for c in conn.comandos if "INSERT INTO erp_automation.job_execucao" in c[0]]
    assert len(inserts) == 2, "primeiro com operador (falha), depois sem"
    assert "operador" in inserts[0][0] and "operador" not in inserts[1][0]
    assert ex.id == 101 and ex.registra
    assert any("erp_005" in a for a in ex.avisos)


# --------------------------------------------------------------------------- #
# execucao atual e anotacoes
# --------------------------------------------------------------------------- #
def test_atual_nasce_ao_abrir_e_some_ao_fechar(banco):
    assert ej.atual() is None
    ex = ej.abrir_execucao("credito", "analisar_credito_operacao", flag_ensaio=True, log=lambda m: None)
    assert ej.atual() is ex
    ej.fechar_execucao(ex, "sucesso", codigo_saida=0, log=lambda m: None)
    assert ej.atual() is None


def test_anotacoes_entram_no_detalhe_do_fechamento(banco):
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400", flag_ensaio=True,
                           log=lambda m: None)
    ej.anotar(ex, "remessas_perdidas", {"id": 26381, "motivo": "download do Smart falhou"})
    ej.anotar(ex, "remessas_perdidas", {"id": 26390, "motivo": "download do Smart falhou"})
    ej.fechar_execucao(ex, "sucesso", codigo_saida=0, detalhe={"contas": 52}, log=lambda m: None)
    sql, params = next(c for c in banco.comandos if "UPDATE erp_automation.job_execucao" in c[0])
    detalhe = next(p for p in params if isinstance(p, tuple) and p[0] == "json")[1]
    assert detalhe == {"remessas_perdidas": [{"id": 26381, "motivo": "download do Smart falhou"},
                                             {"id": 26390, "motivo": "download do Smart falhou"}],
                       "contas": 52}


def test_anotar_sem_execucao_e_inofensivo():
    ej.anotar(None, "x", 1)


# --------------------------------------------------------------------------- #
# busca de arquivo e os tipos novos
# --------------------------------------------------------------------------- #
def test_buscar_arquivo_por_id_no_smart(banco):
    ex = ej.abrir_execucao("remessa_cobranca", "cancelar_remessa_recusada_cnab_400", flag_ensaio=True,
                           log=lambda m: None)
    assert ej.buscar_arquivo(ex, "remessa_cobranca_cnab_400", id_no_smart=26381) == 102
    sql, params = banco.comandos[-1]
    assert "WHERE tipo_arquivo = %s AND id_no_smart = %s" in sql
    assert params == ("remessa_cobranca_cnab_400", "26381")
    with pytest.raises(ValueError):
        ej.buscar_arquivo(ex, "remessa_cobranca_cnab_400")


def test_tipos_novos_de_evento_sao_aceitos(banco):
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400", flag_ensaio=True,
                           log=lambda m: None)
    for tipo in ("intencao_envio", "descartado", "cancelado", "movido"):
        assert ej.registrar_evento_arquivo(ex, 7, tipo, log=lambda m: None) is not None
    for tipo in ("documentos_baixados", "etapa_movida"):
        assert ej.registrar_evento_operacao(ex, 65071, tipo, fato=True, log=lambda m: None) is not None
    with pytest.raises(ValueError):
        ej.registrar_evento_arquivo(ex, 7, "apagado", log=lambda m: None)


# --------------------------------------------------------------------------- #
# estrito x fato consumado
# --------------------------------------------------------------------------- #
def test_evento_de_arquivo_estrito_levanta_e_o_padrao_avisa(banco):
    ex = ej.abrir_execucao("retorno_cobranca", "processar_retorno_bb", flag_ensaio=False,
                           obrigatoria=True, log=lambda m: None)
    banco.falhar_em = "arquivo_evento"
    with pytest.raises(ej.ErroDeRegistro):
        ej.registrar_evento_arquivo(ex, 7, "intencao_envio", estrito=True, log=lambda m: None)
    assert ej.registrar_evento_arquivo(ex, 7, "processado", log=lambda m: None) is None
    assert any("fato ja consumado" in a for a in ex.avisos)


def test_evento_de_operacao_como_fato_nao_derruba(banco):
    ex = ej.abrir_execucao("credito", "analisar_credito_operacao", flag_ensaio=False,
                           obrigatoria=True, log=lambda m: None)
    banco.falhar_em = "operacao_evento"
    with pytest.raises(ej.ErroDeRegistro):
        ej.registrar_evento_operacao(ex, 65071, "finalizar_clicado", log=lambda m: None)
    assert ej.registrar_evento_operacao(ex, 65071, "documentos_baixados", fato=True,
                                        log=lambda m: None) is None
    assert any("fato ja consumado" in a for a in ex.avisos)
