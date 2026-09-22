# -*- coding: utf-8 -*-
"""Prova a erp_008 contra um Postgres real: o historico que so existia nos CSVs de controle
entra em erp_automation.arquivo_historico com a identidade de runtime do ERP, uma vez por
(tipo, md5), e nao muda nem some depois. Pula sozinho sem bancada.
"""
import os
import secrets
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

#: a bancada guarda o que cada rodada gravou (append-only): md5 novo a cada rodada
MD5 = secrets.token_hex(16)


def _execucao(monkeypatch):
    monkeypatch.setenv("ERP_EXECUCAO_DSN", RUNTIME)
    for var in ("HUB_RUN_ID", "HUB_TASK_NOME"):
        monkeypatch.delenv(var, raising=False)
    ex = execucao_job.abrir_execucao("controle", "carregar_historico_csv", flag_ensaio=False,
                                     gatilho="manual", obrigatoria=True, ambiente="sandbox",
                                     operador="bancada", motivo="teste erp_008")
    assert ex.registra
    return ex


def test_runtime_insere_uma_vez_e_nao_altera(monkeypatch):
    ex = _execucao(monkeypatch)
    try:
        with psycopg2.connect(RUNTIME) as c, c.cursor() as cur:
            sql = ("INSERT INTO erp_automation.arquivo_historico "
                   "(fk_job_execucao, tipo_arquivo, md5, nome_arquivo, tratado_em, origem) "
                   "VALUES (%s, 'retorno_cobranca_cnab_400', %s, 'CB2108.RET', '2026-08-21 10:00-03', "
                   "'controle_processados.csv') ON CONFLICT (tipo_arquivo, md5) DO NOTHING RETURNING id")
            cur.execute(sql, (ex.id, MD5))
            assert cur.fetchone() is not None, "primeira carga entra"
            cur.execute(sql, (ex.id, MD5))
            assert cur.fetchone() is None, "o mesmo (tipo, md5) nao entra duas vezes"
        for comando in ("UPDATE erp_automation.arquivo_historico SET nome_arquivo = 'x' WHERE md5 = %s",
                        "DELETE FROM erp_automation.arquivo_historico WHERE md5 = %s"):
            with pytest.raises(psycopg2.Error):
                with psycopg2.connect(RUNTIME) as c, c.cursor() as cur:
                    cur.execute(comando, (MD5,))
        with pytest.raises(psycopg2.Error):
            with psycopg2.connect(RUNTIME) as c, c.cursor() as cur:
                cur.execute("INSERT INTO erp_automation.arquivo_historico "
                            "(fk_job_execucao, tipo_arquivo, md5, nome_arquivo, origem) "
                            "VALUES (%s, 'retorno_bb', 'nao-e-md5', 'x.ret', 'teste')", (ex.id,))
    finally:
        execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0)


def test_carga_em_lote_une_na_memoria_e_nao_duplica(monkeypatch):
    ex = _execucao(monkeypatch)
    try:
        md5_hist, md5_bb, md5_b, md5_d = (secrets.token_hex(16) for _ in range(4))
        linhas = [{"tipo_arquivo": "retorno_pagamento_cnab_240", "md5": md5_hist,
                   "nome_arquivo": "RET0108.RET", "tratado_em": "2026-08-01 09:00-03",
                   "origem": "controle.csv", "detalhe": {"status_http": "200"}},
                  {"tipo_arquivo": "retorno_bb", "md5": md5_bb, "nome_arquivo": "CBR.ret",
                   "origem": "controle_processados.csv",
                   "detalhe": {"processado": True, "nomes_smart": ["CBR"]}}]
        assert execucao_job.carregar_historico_arquivos(ex, linhas) == 2
        assert execucao_job.carregar_historico_arquivos(ex, linhas) == 0, "repetir nao duplica"
        assert execucao_job.historico_carregado(ex, "retorno_pagamento_cnab_240") is True
        assert md5_hist in execucao_job.listar_md5(ex, "retorno_pagamento_cnab_240")
        hist = execucao_job.listar_historico(ex, ["retorno_bb", "retorno_cobranca_cnab_400"])
        assert [(h["md5"], h["detalhe"]["processado"]) for h in hist if h["md5"] == md5_bb] == [
            (md5_bb, True)]
        with pytest.raises(psycopg2.Error):     # tudo ou nada: um md5 torto derruba o lote
            execucao_job.carregar_historico_arquivos(ex, [
                {**linhas[0], "md5": md5_b},
                {"tipo_arquivo": "retorno_bb", "md5": md5_d, "nome_arquivo": "x",
                 "origem": "c.csv", "detalhe": {}, "tratado_em": "nao e data"}])
        assert md5_b not in execucao_job.listar_md5(ex, "retorno_pagamento_cnab_240")
    finally:
        execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0)


def test_carga_de_eventos_com_instante_original_e_idempotente(monkeypatch):
    from datetime import datetime, timezone
    ex = _execucao(monkeypatch)
    try:
        quando = datetime(2026, 7, 3, 12, 45, 36, tzinfo=timezone.utc)
        op = 990000 + secrets.randbelow(9999)
        eventos = [{"id_operacao": op, "tipo_evento": "documentos_baixados", "resultado": "OK",
                    "ocorrido_em": quando,
                    "detalhe": {"origem": "controle_downloads.csv", "nfe_ok": True, "resumo_ok": True}},
                   {"id_operacao": op, "tipo_evento": "etapa_movida",
                    "resultado": "Análise de crédito", "ocorrido_em": quando,
                    "detalhe": {"origem": "controle_downloads.csv"}}]
        assert execucao_job.carregar_historico_eventos(ex, eventos) == 2
        assert execucao_job.carregar_historico_eventos(ex, eventos) == 0, "repetir nao duplica"
        lidos = execucao_job.listar_eventos_operacao(
            ex, ("documentos_baixados", "etapa_movida"), ops=[op])
        assert [(e["tipo_evento"], e["ocorrido_em"]) for e in lidos] == [
            ("documentos_baixados", quando), ("etapa_movida", quando)]
        assert lidos[0]["detalhe"]["resumo_ok"] is True
    finally:
        execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0)
