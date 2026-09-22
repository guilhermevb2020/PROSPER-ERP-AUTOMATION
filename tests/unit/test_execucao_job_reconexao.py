# -*- coding: utf-8 -*-
"""
test_execucao_job_reconexao.py - a conexao cai no meio da rodada (22/09/2026, #164).

Duble de conexao que MORRE depois de N comandos (levanta InterfaceError "connection
already closed" e fica closed=2, como o psycopg2). O que se prova: _executar reconecta e
repete uma vez; se a reconexao falha, o comportamento antigo (estrito levanta, fato
consumado avisa); erro que NAO e de conexao nao reconecta; fechar_execucao nunca levanta
e, com a conexao morta, reconecta e fecha; keepalive nos parametros.
"""
from __future__ import annotations

import pytest

from src.common.clients import execucao_job as ej
from test_execucao_job import _Conn, _Cursor


class InterfaceError(Exception):
    pass


class _CursorMortal(_Cursor):
    def execute(self, sql, params=None):
        self._conn.vistos += 1
        if self._conn.morre_apos is not None and self._conn.vistos > self._conn.morre_apos:
            self._conn.closed = 2
            raise InterfaceError("connection already closed")
        return super().execute(sql, params)


class _ConnMortal(_Conn):
    def __init__(self, morre_apos=None):
        super().__init__()
        self.morre_apos = morre_apos
        self.vistos = 0
        self.closed = 0

    def cursor(self):
        return _CursorMortal(self)

    def close(self):
        self.fechada = True
        self.closed = 1


@pytest.fixture
def cenario(monkeypatch):
    """A primeira conexao morre depois de 2 comandos (o INSERT da abertura + set_config);
    `_conectar` entrega uma nova, viva, a cada chamada."""
    conns = []

    def conectar(job):
        c = _ConnMortal(morre_apos=2 if not conns else None)
        conns.append(c)
        return c
    monkeypatch.setattr(ej, "_conectar", conectar)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    return conns


def test_queda_no_meio_reconecta_e_repete_o_comando(cenario):
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400", flag_ensaio=False,
                           obrigatoria=True, log=lambda m: None)
    assert len(cenario) == 1 and ex._conn is cenario[0]
    arq = ej.registrar_arquivo(ex, "remessa_cobranca_cnab_400", "gerado", nome_arquivo="a.REM",
                               conteudo=b"x", log=lambda m: None)
    assert arq is not None, "o registro saiu na conexao nova"
    assert len(cenario) == 2 and ex._conn is cenario[1] and cenario[0].fechada
    assert any("caiu" in a and "reconectada" in a for a in ex.avisos)
    assert any("set_config" in c[0] for c in cenario[1].comandos), "erp.execucao_id republicado"
    assert any("INSERT INTO erp_automation.arquivo" in c[0] for c in cenario[1].comandos)


def test_reconexao_que_falha_mantem_o_contrato_antigo(monkeypatch):
    chamadas = []

    def conectar(job):
        chamadas.append(job)
        if len(chamadas) == 1:
            return _ConnMortal(morre_apos=2)
        raise RuntimeError("guardian fora")
    monkeypatch.setattr(ej, "_conectar", conectar)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400", flag_ensaio=False,
                           obrigatoria=True, log=lambda m: None)
    with pytest.raises(ej.ErroDeRegistro):
        ej.registrar_evento_operacao(ex, 1, "avaliada", resultado="BARRADA", log=lambda m: None)
    assert any("reconexao falhou" in a for a in ex.avisos)
    assert ej.registrar_arquivo(ex, "remessa_cobranca_cnab_400", "gerado", nome_arquivo="a.REM",
                                conteudo=b"x", log=lambda m: None) is None, "fato consumado avisa"


def test_erro_que_nao_e_de_conexao_nao_reconecta(monkeypatch):
    conns = []

    def conectar(job):
        conns.append(_ConnMortal())
        return conns[-1]
    monkeypatch.setattr(ej, "_conectar", conectar)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400", flag_ensaio=True,
                           log=lambda m: None)
    conns[0].falhar_em = "arquivo_evento"           # RuntimeError do duble: nao e queda
    assert ej.registrar_evento_arquivo(ex, 7, "gerado", log=lambda m: None) is None
    assert len(conns) == 1 and not any("caiu" in a for a in ex.avisos)


def test_fechamento_com_conexao_morta_reconecta_e_fecha(cenario):
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400", flag_ensaio=False,
                           obrigatoria=True, log=lambda m: None)
    assert ej.fechar_execucao(ex, "sucesso", codigo_saida=0, qtd_itens=9, log=lambda m: None) is True
    assert any("UPDATE erp_automation.job_execucao" in c[0] for c in cenario[1].comandos)
    assert ex._conn is None and cenario[1].fechada


def test_fechamento_nunca_derruba_o_job(monkeypatch):
    def conectar(job):
        if not hasattr(conectar, "n"):
            conectar.n = 0
        conectar.n += 1
        if conectar.n == 1:
            return _ConnMortal(morre_apos=2)
        raise RuntimeError("guardian fora")
    monkeypatch.setattr(ej, "_conectar", conectar)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    ex = ej.abrir_execucao("remessa_cobranca", "gerar_remessa_cobranca_cnab_400", flag_ensaio=False,
                           obrigatoria=True, log=lambda m: None)
    assert ej.fechar_execucao(ex, "sucesso", codigo_saida=0, log=lambda m: None) is False
    assert any("fica ativa no banco" in a for a in ex.avisos)
    assert ex._conn is None


def test_keepalive_nos_parametros(monkeypatch):
    monkeypatch.delenv("ERP_EXECUCAO_DSN", raising=False)
    p = ej._parametros_conexao("x")
    assert p["keepalives"] == 1 and p["keepalives_idle"] == 60
    monkeypatch.setenv("ERP_EXECUCAO_DSN", "postgresql://u:p@h/db")
    p = ej._parametros_conexao("x")
    assert p["dsn"] and p["keepalives"] == 1
