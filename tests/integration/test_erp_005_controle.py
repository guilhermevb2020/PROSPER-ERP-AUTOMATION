# -*- coding: utf-8 -*-
"""Prova a erp_005 contra um Postgres real (scripts/bancada_pg.sh).

O que a migration promete e o que o codigo precisa: colunas geradas md5/id_no_smart
preenchidas a partir do JSON e encontraveis por `buscar_arquivo`; eventos novos aceitos;
operador/motivo gravados na abertura e imutaveis no fechamento; automacao `controle`;
as views de controle devolvendo as colunas do CSV; e a consulta do job de paridade.

Pula sozinho sem BANCADA_ADMIN_DSN/ERP_BANCADA_DSN.
"""
import hashlib
import os
import sys
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

psycopg2 = pytest.importorskip("psycopg2")
from src.common.clients import execucao_job  # noqa: E402
from src.processors.db.controle import comparar_controle_csv_banco as cmp  # noqa: E402

ADMIN = os.environ.get("BANCADA_ADMIN_DSN")
RUNTIME = os.environ.get("ERP_BANCADA_DSN")
pytestmark = pytest.mark.skipif(
    not (ADMIN and RUNTIME),
    reason="sem bancada: rode scripts/bancada_pg.sh subir && eval \"$(scripts/bancada_pg.sh env)\"")


def _ler(sql, params=()):
    with psycopg2.connect(ADMIN) as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _unico(prefixo: bytes, tamanho: int = 400) -> bytes:
    selo = uuid.uuid4().hex.encode()
    corpo = prefixo * tamanho
    return corpo[:tamanho - len(selo)] + selo + b"\r\n"


@pytest.fixture()
def execucao(monkeypatch):
    monkeypatch.setenv("ERP_EXECUCAO_DSN", RUNTIME)
    monkeypatch.delenv("HUB_RUN_ID", raising=False)
    monkeypatch.setenv("ERP_OPERADOR", "teste-bancada")
    monkeypatch.setenv("ERP_MOTIVO", "prova da erp_005")
    ex = execucao_job.abrir_execucao("remessa_cobranca", "teste_erp_005",
                                     flag_ensaio=True, obrigatoria=True, ambiente="sandbox")
    ex.estrito = True
    yield ex
    if ex._conn is not None:
        execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0)


def test_operador_e_motivo_ficam_na_execucao_e_nao_mudam_no_fechamento(execucao):
    (operador, motivo, gatilho), = _ler(
        "select operador, motivo, gatilho from erp_automation.job_execucao where id = %s", (execucao.id,))
    assert (operador, motivo, gatilho) == ("teste-bancada", "prova da erp_005", "manual")
    with pytest.raises(psycopg2.Error):
        _ler("update erp_automation.job_execucao set operador = 'outro', status = 'sucesso', "
             "terminado_em = now() where id = %s returning id", (execucao.id,))


def test_automacao_controle_e_aceita(monkeypatch):
    monkeypatch.setenv("ERP_EXECUCAO_DSN", RUNTIME)
    ex = execucao_job.abrir_execucao("controle", "comparar_controle_csv_banco",
                                     flag_ensaio=False, obrigatoria=True, ambiente="sandbox")
    assert ex.registra
    execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0)


def test_md5_e_id_no_smart_sao_gerados_do_json_e_encontraveis(execucao):
    dados = _unico(b"5")
    md5 = hashlib.md5(dados).hexdigest()
    arq_id = execucao_job.registrar_arquivo(
        execucao, "remessa_cobranca_cnab_400", "gerado", nome_arquivo="CB2209000001.REM",
        conteudo=dados, qtd_registros=3, conta_id="291", conta_label="mp cast",
        detalhe={"md5": md5, "id_no_smart": 26381, "nome_no_disco": "CB2209000001.REM"})
    (g_md5, g_id), = _ler("select md5, id_no_smart from erp_automation.arquivo where id = %s", (arq_id,))
    assert (g_md5, g_id) == (md5, "26381")
    assert execucao_job.buscar_arquivo(execucao, "remessa_cobranca_cnab_400", id_no_smart=26381) == arq_id
    assert execucao_job.buscar_arquivo(execucao, "remessa_cobranca_cnab_400", md5=md5) == arq_id
    assert execucao_job.buscar_arquivo(execucao, "remessa_cobranca_cnab_400", id_no_smart="nao-existe") is None


def test_eventos_novos_e_a_view_de_remessa(execucao):
    dados = _unico(b"6")
    arq_id = execucao_job.registrar_arquivo(
        execucao, "remessa_cobranca_cnab_400", "gerado", nome_arquivo="CB2209000002.REM",
        conteudo=dados, qtd_registros=60, conta_id="404", conta_label="mp prospere",
        detalhe={"md5": hashlib.md5(dados).hexdigest(), "id_no_smart": "26382"})
    assert execucao_job.registrar_evento_arquivo(execucao, arq_id, "descartado", resultado="linha com 401 bytes")
    assert execucao_job.registrar_evento_arquivo(execucao, arq_id, "cancelado", resultado="sumiu da grade",
                                                 detalhe={"conta": "404"})
    (id_, tipo, titulos, ultimo, resultado), = _ler(
        "select id, tipo, titulos, ultimo_evento, ultimo_resultado from erp_automation.vw_controle_remessa "
        "where arquivo_id = %s", (arq_id,))
    assert (id_, tipo, titulos, ultimo, resultado) == ("26382", "mp prospere", 60, "cancelado", "sumiu da grade")


def test_intencao_de_envio_estrita_e_a_view_de_retorno(execucao):
    dados = _unico(b"7")
    md5 = hashlib.md5(dados).hexdigest()
    arq_id = execucao_job.registrar_arquivo(
        execucao, "retorno_bb", "recebido", nome_arquivo="BBAPI0000099.RET", conteudo=dados,
        qtd_registros=2, conta_id="395", detalhe={"md5": md5, "nome_smart": "BBAPI0000099.RET"})
    assert execucao_job.registrar_evento_arquivo(execucao, arq_id, "intencao_envio", estrito=True,
                                                 detalhe={"tentativa": "t1"})
    assert execucao_job.registrar_evento_arquivo(
        execucao, arq_id, "processado", resultado="OK",
        detalhe={"ocorrencias": {"liquidacao": 2}, "qtd_criticas": 0, "divergencias": []})
    (hash_, conta, titulos, processado, ocorr, criticas, motivo), = _ler(
        "select hash, conta, titulos, processado, ocorrencias, criticas, motivo "
        "from erp_automation.vw_controle_retorno where arquivo_id = %s", (arq_id,))
    assert (hash_, conta, titulos, processado, criticas, motivo) == (md5, "395", 2, True, 0, "OK")
    assert ocorr == {"liquidacao": 2}, "o que aconteceu no processamento vem do EVENTO"


def test_evento_de_operacao_do_credito(execucao):
    assert execucao_job.registrar_evento_operacao(
        execucao, 65071, "documentos_baixados", resultado="PARCIAL",
        detalhe={"nfe_ok": False, "resumo_ok": True}, fato=True)
    assert execucao_job.registrar_evento_operacao(execucao, 65071, "etapa_movida",
                                                  resultado="Análise de crédito", fato=True)
    tipos = [t for (t,) in _ler("select tipo_evento from erp_automation.operacao_evento "
                                "where fk_job_execucao = %s order by id", (execucao.id,))]
    assert tipos == ["documentos_baixados", "etapa_movida"]


def test_view_da_ultima_execucao_e_do_arquivo_do_dia(execucao):
    dados = _unico(b"8")
    arq_id = execucao_job.registrar_arquivo(
        execucao, "remessa_pagamento_cnab_240", "gerado", nome_arquivo="CP2209000409.REM",
        conteudo=dados, qtd_registros=1, conta_id="404", detalhe={"md5": hashlib.md5(dados).hexdigest(), "qtd_pix": 1},
        titulos=[{"numero_linha": 1, "id_titulo": "1001"}])
    execucao_job.registrar_evento_arquivo(execucao, arq_id, "gerado")
    (ids, pix), = _ler("select ids, pix from erp_automation.vw_controle_pagamento where arquivo_id = %s", (arq_id,))
    assert (ids, pix) == ("1001", 1)
    (job, ultimo), = _ler("select job, ultimo_evento from erp_automation.vw_arquivo_dia where arquivo_id = %s", (arq_id,))
    assert (job, ultimo) == ("teste_erp_005", "gerado")
    (status,), = _ler("select status from erp_automation.vw_job_execucao_ultima where job = 'teste_erp_005'")
    assert status == "ativa"


def test_consulta_da_paridade_acha_o_arquivo_do_dia(execucao):
    dados = _unico(b"9")
    md5 = hashlib.md5(dados).hexdigest()
    execucao_job.registrar_arquivo(
        execucao, "retorno_pagamento_cnab_240", "recebido", nome_arquivo="CP2209000494.RET",
        conteudo=dados, detalhe={"md5": md5})
    hoje = cmp.hoje()
    with psycopg2.connect(RUNTIME) as conn:
        banco = cmp.ler_banco(conn, ("retorno_pagamento_cnab_240",), hoje)
    assert banco.get(md5) == "CP2209000494.RET"


def test_listar_md5_devolve_a_memoria_de_idempotencia(execucao):
    """Fase 2, passo 1: o retorno de pagamento pergunta ao banco o que ja tratou."""
    hashes = set()
    for prefixo in (b"a", b"b"):
        dados = _unico(prefixo)
        md5 = hashlib.md5(dados).hexdigest()
        hashes.add(md5)
        execucao_job.registrar_arquivo(execucao, "retorno_pagamento_cnab_240", "recebido",
                                       nome_arquivo=f"CP2209_{prefixo.decode()}.RET", conteudo=dados,
                                       detalhe={"md5": md5})
    lidos = execucao_job.listar_md5(execucao, "retorno_pagamento_cnab_240")
    assert hashes <= lidos, "os md5 recem-registrados estao na memoria lida do banco"
