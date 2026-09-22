# -*- coding: utf-8 -*-
"""Prova a erp_006 contra um Postgres real: duas execucoes de job com o MESMO run_id.

O wrapper do retorno abre uma execucao por pasta dentro do mesmo run do hub; com o
HUB_RUN_ID injetado, o unico da erp_004 recusaria a segunda — e em modo real o job
nao age sem registro. Pula sozinho sem bancada.
"""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

psycopg2 = pytest.importorskip("psycopg2")
from src.common.clients import execucao_job  # noqa: E402

ADMIN = os.environ.get("BANCADA_ADMIN_DSN")
RUNTIME = os.environ.get("ERP_BANCADA_DSN")
pytestmark = pytest.mark.skipif(
    not (ADMIN and RUNTIME),
    reason="sem bancada: rode scripts/bancada_pg.sh subir && eval \"$(scripts/bancada_pg.sh env)\"")


def _ler(sql, params=()):
    with psycopg2.connect(ADMIN) as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_duas_execucoes_do_mesmo_run_do_hub_sao_aceitas(monkeypatch):
    monkeypatch.setenv("ERP_EXECUCAO_DSN", RUNTIME)
    monkeypatch.setenv("HUB_RUN_ID", "2885157")            # o run do hub das 08:50 de 22/09
    monkeypatch.setenv("HUB_TASK_NOME", "processar_retorno_cobranca_cnab_400")
    abertas = []
    for pasta in ("21/MoneyPlus", "22/MoneyPlus"):
        ex = execucao_job.abrir_execucao("retorno_cobranca", "processar_retorno_cobranca_cnab_400",
                                         flag_ensaio=True, obrigatoria=True, ambiente="sandbox",
                                         detalhe={"pasta": pasta})
        assert ex.registra, "a segunda execucao do mesmo run tem de abrir"
        abertas.append(ex)
    linhas = _ler("select gatilho, task_nome from erp_automation.job_execucao where run_id = %s "
                  "and id in %s", ("2885157", tuple(e.id for e in abertas)))
    assert linhas == [("cron", "processar_retorno_cobranca_cnab_400")] * 2, \
        "com HUB_RUN_ID/HUB_TASK_NOME o gatilho vira cron e a task fica registrada"
    (indices,), = _ler("select string_agg(indexname, ',' order by indexname) from pg_indexes "
                       "where schemaname='erp_automation' and tablename='job_execucao' "
                       "and indexname in ('uq_job_execucao_run_id','ix_job_execucao_run_id')")
    assert indices == "ix_job_execucao_run_id"
    for ex in abertas:
        execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0)
