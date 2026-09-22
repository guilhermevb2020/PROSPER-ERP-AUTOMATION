# -*- coding: utf-8 -*-
"""listar_md5: a memoria de idempotencia lida do banco, sem banco (duble com fetchall)."""
from __future__ import annotations

import pytest

from src.common.clients import execucao_job as ej
from test_execucao_job import _Conn, _Cursor


class _CursorLinhas(_Cursor):
    def fetchall(self):
        if "SELECT md5 FROM erp_automation.arquivo" in self._ultimo:
            return [("AAAA",), ("bbbb",), (None,)]
        return []


class _ConnLinhas(_Conn):
    def cursor(self):
        return _CursorLinhas(self)


@pytest.fixture
def banco(monkeypatch):
    conn = _ConnLinhas()
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    return conn


def test_devolve_os_md5_em_minusculas_sem_nulos(banco):
    ex = ej.abrir_execucao("retorno_pagamento", "processar_retorno_pagamento_cnab_240",
                           flag_ensaio=True, log=lambda m: None)
    assert ej.listar_md5(ex, "retorno_pagamento_cnab_240", log=lambda m: None) == {"aaaa", "bbbb"}
    sql, params = banco.comandos[-1]
    assert "WHERE tipo_arquivo = %s AND md5 IS NOT NULL" in sql and params == ("retorno_pagamento_cnab_240",)


def test_sem_execucao_ou_degradada_devolve_none(banco, monkeypatch):
    assert ej.listar_md5(None, "retorno_pagamento_cnab_240") is None
    monkeypatch.setattr(ej, "_conectar", lambda job: (_ for _ in ()).throw(RuntimeError("sem banco")))
    ex = ej.abrir_execucao("retorno_pagamento", "processar_retorno_pagamento_cnab_240",
                           flag_ensaio=True, log=lambda m: None)
    assert not ex.registra
    assert ej.listar_md5(ex, "retorno_pagamento_cnab_240", log=lambda m: None) is None


def test_falha_da_consulta_e_fato_consumado_mesmo_em_modo_estrito(banco):
    ex = ej.abrir_execucao("retorno_pagamento", "processar_retorno_pagamento_cnab_240",
                           flag_ensaio=False, obrigatoria=True, log=lambda m: None)
    banco.falhar_em = "SELECT md5"
    assert ej.listar_md5(ex, "retorno_pagamento_cnab_240", log=lambda m: None) is None
    assert any("fato ja consumado" in a for a in ex.avisos)
    with pytest.raises(ValueError):
        ej.listar_md5(ex, "tipo_que_nao_existe")
