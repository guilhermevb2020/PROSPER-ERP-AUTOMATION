# -*- coding: utf-8 -*-
"""Prova que o trecho de gravacao de ARQUIVO de cada job funciona contra um Postgres real.

POR QUE ESTE TESTE EXISTE
-------------------------
A conversao de 22/09/2026 pos os quatro jobs de arquivo a gravar no banco no mesmo ponto
em que gravam o CSV. Tres deles nunca exercitaram esse trecho em producao, porque as filas
estavam vazias quando foram rodados: `remessa_cobranca`, `remessa_pagamento` e
`retorno_pagamento`. Um erro de nome de campo ou de tipo ali so apareceria no dia em que
houvesse arquivo — e esse dia e sempre um dia em que alguem esta esperando o arquivo.

⚠️ Nao substitui a rodada real (LIC-034: o ensaio tem de entrar pela porta da producao).
O que este teste cobre e menor e bem delimitado: que a chamada de gravacao esta correta
contra o schema de verdade — colunas que existem, tipos que o banco aceita, CHECKs que
passam. Quem roda o job inteiro continua sendo a task.

Pula sozinho sem `BANCADA_ADMIN_DSN`/`ERP_BANCADA_DSN` (scripts/bancada_pg.sh).
"""
import os
import sys
import uuid
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


@pytest.fixture()
def execucao(monkeypatch):
    """Uma execucao aberta na bancada, em modo ESTRITO: falha de registro levanta.

    Estrito de proposito — o teste existe para ver o erro, nao para engoli-lo como o
    modo degradado faz em producao."""
    monkeypatch.setenv("ERP_EXECUCAO_DSN", RUNTIME)
    ex = execucao_job.abrir_execucao(
        "remessa_cobranca", "teste_gravacao_arquivo",
        flag_ensaio=True, obrigatoria=True, ambiente="sandbox")
    ex.estrito = True
    yield ex
    execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0)


def _unico(prefixo: bytes, tamanho: int = 400) -> bytes:
    """Conteudo unico por rodada.

    `registrar_arquivo` deduplica por (tipo_arquivo, sha256) — de proposito, e a mesma
    regra do `hash` no CSV. Conteudo fixo faz este teste colidir com o de outro arquivo
    da mesma suite e receber o id JA existente, e as asserções passam a olhar a linha
    errada. Medido em 22/09/2026: passava sozinho e falhava na suite inteira."""
    selo = uuid.uuid4().hex.encode()
    corpo = prefixo * tamanho
    return (corpo[:tamanho - len(selo)] + selo + b"\r\n")


def _ler(sql, params=()):
    with psycopg2.connect(ADMIN) as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_remessa_cobranca_grava_o_arquivo_gerado_e_os_dois_eventos(execucao, tmp_path):
    """O trecho de `processar()`: arquivo + evento `gerado` + evento `enviado`."""
    dados = _unico(b"0") + _unico(b"1")
    destino = tmp_path / "CB22090000123_dup071500.REM"
    destino.write_bytes(dados)

    arq_id = execucao_job.registrar_arquivo(
        execucao, "remessa_cobranca_cnab_400", "gerado",
        nome_arquivo="CB22090000123.REM", conteudo=dados, qtd_registros=14,
        conta_id="305", conta_label="mp prospere", destino_caminho=str(destino),
        detalhe={"md5": "abc123", "id_no_smart": 26487,
                 "nome_no_disco": destino.name})
    assert arq_id, "a remessa de cobranca precisa devolver o id do arquivo"
    assert execucao_job.registrar_evento_arquivo(execucao, arq_id, "gerado")
    assert execucao_job.registrar_evento_arquivo(
        execucao, arq_id, "enviado", resultado="FINANCEIRO/Remessas/CB22090000123.REM")

    (nome, sha, qtd_bytes, qtd_reg, conta, label), = _ler(
        "select nome_arquivo, sha256, qtd_bytes, qtd_registros, conta_id, conta_label "
        "from erp_automation.arquivo where id = %s", (arq_id,))
    assert nome == "CB22090000123.REM", "grava o nome do SMART, nao o `_dup` do disco"
    assert len(sha) == 64 and qtd_bytes == len(dados)
    assert (qtd_reg, conta, label) == (14, "305", "mp prospere")
    assert _ler("select count(*) from erp_automation.arquivo_evento where fk_arquivo = %s",
                (arq_id,))[0][0] == 2


def test_remessa_pagamento_grava_os_ids_da_grade_como_titulos(execucao, tmp_path):
    """O trecho de `_registrar_no_banco()`: os ids da grade viram arquivo_titulo."""
    caminho = tmp_path / "PG22090000456.REM"
    caminho.write_bytes(_unico(b"2", 240))
    ids = ["77001", "77002", "77003"]

    arq_id = execucao_job.registrar_arquivo(
        execucao, "remessa_pagamento_cnab_240", "gerado",
        nome_arquivo=caminho.name, caminho=str(caminho),
        qtd_registros=len(ids), conta_id="404", destino_caminho=str(caminho),
        detalhe={"md5": "def456", "qtd_pix": 3, "nome_do_smart": caminho.name},
        titulos=[{"numero_linha": i, "id_titulo": t} for i, t in enumerate(ids, start=1)])
    assert arq_id
    linhas = _ler("select numero_linha, id_titulo from erp_automation.arquivo_titulo "
                  "where fk_arquivo = %s order by numero_linha", (arq_id,))
    assert linhas == [(1, "77001"), (2, "77002"), (3, "77003")]


def test_retorno_pagamento_grava_o_recebido_e_o_evento_processado(execucao, tmp_path):
    """O trecho de `tratar()`: arquivo recebido + evento `processado` com o HTTP."""
    dados = _unico(b"3", 240)
    arq_id = execucao_job.registrar_arquivo(
        execucao, "retorno_pagamento_cnab_240", "recebido",
        nome_arquivo="RET22090000789.RET", conteudo=dados,
        origem_caminho="FINANCEIRO/Pagamentos-MoneyPlus/_RETORNOS",
        destino_caminho="_PROCESSADOS",
        detalhe={"md5": "ghi789", "status_http_etapa1": 200, "status_http_etapa2": 200})
    assert arq_id
    assert execucao_job.registrar_evento_arquivo(
        execucao, arq_id, "processado", resultado="200",
        detalhe={"resposta_etapa1": "x.html", "resposta_etapa2": "y.html"})
    (sentido, tipo), = _ler(
        "select sentido, tipo_evento from erp_automation.arquivo a "
        "join erp_automation.arquivo_evento e on e.fk_arquivo = a.id where a.id = %s",
        (arq_id,))
    assert (sentido, tipo) == ("recebido", "processado")


def test_retorno_cobranca_grava_os_titulos_detalhados(execucao, tmp_path):
    """O trecho de `_registrar_no_banco()` do retorno: titulos com ocorrencia e valor.

    Este e o unico caminho que JA rodou em producao (13 arquivos em 21/09), mas entra
    aqui para o conjunto cobrir os quatro e nao so os tres que faltavam."""
    caminho = tmp_path / "CP22090000321.RET"
    caminho.write_bytes(_unico(b"4"))
    arq_id = execucao_job.registrar_arquivo(
        execucao, "retorno_cobranca_cnab_400", "recebido",
        nome_arquivo=caminho.name, caminho=str(caminho), qtd_registros=2, conta_id="291",
        origem_caminho=str(caminho), destino_caminho=None,
        detalhe={"md5": "jkl012", "ocorrencias": {"refinan": 2}, "qtd_criticas": 0,
                 "divergencias": []},
        titulos=[{"numero_linha": 1, "id_titulo": "7021-001",
                  "codigo_ocorrencia": "06", "valor_titulo": "1.234,56"},
                 {"numero_linha": 2, "id_titulo": "7021-002",
                  "codigo_ocorrencia": "06", "valor_titulo": "78,90"}])
    assert arq_id
    linhas = _ler("select id_titulo, codigo_ocorrencia, valor_titulo "
                  "from erp_automation.arquivo_titulo where fk_arquivo = %s "
                  "order by numero_linha", (arq_id,))
    assert [(t, o, str(v)) for t, o, v in linhas] == [
        ("7021-001", "06", "1234.56"), ("7021-002", "06", "78.90")], \
        "o valor em pt-BR tem de virar numeric"


def test_o_mesmo_arquivo_duas_vezes_nao_duplica(execucao, tmp_path):
    """A idempotencia por CONTEUDO, que e a mesma regra do `hash` no CSV.

    Vale para os quatro jobs: reprocessar o mesmo arquivo devolve a linha existente."""
    dados = _unico(b"5")
    primeiro = execucao_job.registrar_arquivo(
        execucao, "retorno_cobranca_cnab_400", "recebido",
        nome_arquivo="REPETIDO.RET", conteudo=dados, qtd_registros=1)
    segundo = execucao_job.registrar_arquivo(
        execucao, "retorno_cobranca_cnab_400", "recebido",
        nome_arquivo="REPETIDO_outro_nome.RET", conteudo=dados, qtd_registros=1)
    assert primeiro == segundo, "mesmo conteudo tem de devolver o mesmo id"
    assert _ler("select count(*) from erp_automation.arquivo where sha256 = "
                "encode(sha256(%s), 'hex')", (dados,))[0][0] == 1
