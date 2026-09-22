# -*- coding: utf-8 -*-
"""listar_controle: o controle de uma familia lido da view, no formato do CSV (duble)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.common.clients import execucao_job as ej
from test_execucao_job import _Conn, _Cursor

QUANDO = datetime(2026, 9, 22, 12, 15, 14, tzinfo=timezone.utc)   # 09:15:14 em Sao Paulo


class _CursorViews(_Cursor):
    def fetchall(self):
        if "vw_controle_pagamento" in self._ultimo:
            return [("CP2209000409.REM", 1452, "6FA597", 1, "1001", 1, QUANDO)]
        if "vw_controle_retorno" in self._ultimo:
            return [("A.RET", "A.RET", "AAAA", "291", 3, True, "OK", QUANDO),
                    ("B.RET", "B.RET", "bbbb", "291", 1, False, "RECUSADO PELO PORTAO", QUANDO),
                    ("C.RET", "C.RET", None, "291", 1, True, "OK", QUANDO)]
        return []


class _ConnViews(_Conn):
    def cursor(self):
        return _CursorViews(self)


@pytest.fixture
def ex(monkeypatch):
    conn = _ConnViews()
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    e = ej.abrir_execucao("remessa_pagamento", "gerar_remessa_pagamento_cnab_240",
                          flag_ensaio=True, log=lambda m: None)
    e._banco = conn
    return e


def test_pagamento_vem_como_o_csv_devolveria(ex):
    c = ej.listar_controle(ex, "pagamento", chave="md5", log=lambda m: None)
    assert c == {"6fa597": {"arquivo": "CP2209000409.REM", "bytes": "1452", "md5": "6FA597",
                            "titulos": "1", "ids": "1001", "pix": "1", "quando": "2026-09-22 09:15:14"}}
    sql, _ = ex._banco.comandos[-1]
    assert sql.startswith("SELECT arquivo, bytes, md5, titulos, ids, pix, quando FROM erp_automation.vw_controle_pagamento")


def test_retorno_chaveia_por_hash_minusculo_e_pula_sem_hash(ex):
    c = ej.listar_controle(ex, "retorno", chave="hash", log=lambda m: None)
    assert set(c) == {"aaaa", "bbbb"}
    assert c["aaaa"]["processado"] == "True" and c["bbbb"]["processado"] == "False"
    assert c["bbbb"]["motivo"] == "RECUSADO PELO PORTAO"


def test_familia_ou_chave_desconhecida_e_erro_de_programacao(ex):
    with pytest.raises(ValueError):
        ej.listar_controle(ex, "boletos", chave="md5")
    with pytest.raises(ValueError):
        ej.listar_controle(ex, "pagamento", chave="hash")


def test_sem_banco_devolve_none(ex):
    assert ej.listar_controle(None, "pagamento", chave="md5") is None
    ex._banco.falhar_em = "vw_controle_pagamento"
    assert ej.listar_controle(ex, "pagamento", chave="md5", log=lambda m: None) is None
