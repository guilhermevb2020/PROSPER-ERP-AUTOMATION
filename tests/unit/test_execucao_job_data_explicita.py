# -*- coding: utf-8 -*-
"""registrado_em/ocorrido_em explicitos: so a carga historica informa; o resto nao muda."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.common.clients import execucao_job as ej
from test_execucao_job import _Conn

QUANDO = datetime(2026, 8, 10, 18, 5, 33, tzinfo=timezone.utc)


@pytest.fixture
def banco(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    return conn


def _insert(conn, tabela):
    return next(c for c in conn.comandos if f"INSERT INTO erp_automation.{tabela} (" in c[0])


def test_sem_data_o_insert_nao_cita_a_coluna(banco):
    ex = ej.abrir_execucao("controle", "carregar_remessas_historicas", flag_ensaio=True, log=lambda m: None)
    arq = ej.registrar_arquivo(ex, "remessa_cobranca_cnab_400", "gerado", nome_arquivo="a.REM",
                               conteudo=b"x", log=lambda m: None)
    ej.registrar_evento_arquivo(ex, arq, "gerado", log=lambda m: None)
    assert "registrado_em" not in _insert(banco, "arquivo")[0]
    assert "ocorrido_em" not in _insert(banco, "arquivo_evento")[0]


def test_com_data_a_coluna_entra_no_fim_com_o_valor(banco):
    ex = ej.abrir_execucao("controle", "carregar_remessas_historicas", flag_ensaio=False,
                           obrigatoria=True, log=lambda m: None)
    arq = ej.registrar_arquivo(ex, "remessa_cobranca_cnab_400", "gerado", nome_arquivo="a.REM",
                               conteudo=b"x", registrado_em=QUANDO, log=lambda m: None)
    sql, params = _insert(banco, "arquivo")
    assert sql.split("(")[1].split(")")[0].replace(" ", "").endswith(",registrado_em")
    assert params[-1] == QUANDO
    ej.registrar_evento_arquivo(ex, arq, "enviado", resultado="/nc/a.REM", ocorrido_em=QUANDO,
                                log=lambda m: None)
    sql, params = _insert(banco, "arquivo_evento")
    assert sql.split("(")[1].split(")")[0].replace(" ", "").endswith(",ocorrido_em") and params[-1] == QUANDO
