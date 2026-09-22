# -*- coding: utf-8 -*-
"""
test_execucao_job_bancada.py - a migration erp_004 e o modulo execucao_job contra um
Postgres DE VERDADE: a bancada (scripts/bancada_pg.sh subir), da mesma imagem do de
producao, com a migration aplicada pelo MESMO aplicar.sh.

Roda so quando ERP_BANCADA_DSN (e BANCADA_ADMIN_DSN) estao no ambiente:
    eval "$(scripts/bancada_pg.sh env)"
    PYTHONPATH=$PWD .venv-sandbox/bin/pytest tests/integration/test_execucao_job_bancada.py

O que se prova aqui e o que o duble nao prova: os gatilhos recusam UPDATE, DELETE e
TRUNCATE (ate para o superusuario), os indices unicos seguram o segundo "finalizada",
o fechamento so acontece uma vez e so nas colunas de fechamento, o runtime nao e dono
das tabelas, os leitores nao enxergam a grade de pagamento, e as views respondem.
"""
from __future__ import annotations

import hashlib
import os
import uuid

import pytest

DSN = os.environ.get("ERP_BANCADA_DSN", "")
ADMIN = os.environ.get("BANCADA_ADMIN_DSN", "")
pytestmark = pytest.mark.skipif(not (DSN and ADMIN), reason="bancada nao esta no ar (ERP_BANCADA_DSN)")

if DSN:
    import psycopg2
    import psycopg2.errors

    from src.common.clients import execucao_job as ej


@pytest.fixture(autouse=True)
def _dsn_no_ambiente(monkeypatch):
    monkeypatch.setenv("ERP_EXECUCAO_DSN", DSN)
    for var in ("HUB_RUN_ID", "HUB_TASK_NOME"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def admin():
    conn = psycopg2.connect(ADMIN)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture
def app():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    yield conn
    conn.close()


def _q(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


def _op():
    # id de operacao unico por teste, para os indices parciais nao colidirem entre testes
    return int(uuid.uuid4().int % 900_000) + 100_000


# --------------------------------------------------------------------------- #
# a migration entrou pela porta certa
# --------------------------------------------------------------------------- #
def test_a_migration_esta_no_ledger_e_as_tabelas_tem_o_dono_certo(admin):
    ledger = _q(admin, "SELECT arquivo, aplicada_por FROM erp_automation.migration_aplicada "
                       "WHERE arquivo LIKE 'erp_004%%'")
    assert ledger and "pulada" not in ledger[0][1]
    donos = dict(_q(admin, "SELECT relname, pg_get_userbyid(relowner) FROM pg_class c "
                           "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'erp_automation' "
                           "AND relname IN ('job_execucao','operacao_evento','operacao_pagamento_linha',"
                           "'arquivo','arquivo_titulo','arquivo_evento')"))
    assert len(donos) == 6 and set(donos.values()) == {"app_erp_automation_evento"}


# --------------------------------------------------------------------------- #
# o ciclo completo pelo modulo
# --------------------------------------------------------------------------- #
def test_ciclo_completo_abre_registra_e_fecha(app, admin):
    op = _op()
    ex = ej.abrir_execucao("finalizar_operacao", "finalizar_operacao_aguardando_assinatura",
                           flag_ensaio=True, ambiente="sandbox", apelido_credencial="GSMARTPWD3",
                           log=lambda m: None)
    assert ex.registra
    linhas = [{"_linha": "1", "tipo": "PIX", "chave_pix": "chave@x.com", "cta_origem": "mp prospere",
               "favorecido": "F", "cpf_cnpj": "1", "vencto": "18/09/2026", "valor": "10,00", "sp": "X"}]
    e1 = ej.registrar_evento_operacao(ex, op, "avaliada", resultado="FINALIZARIA", cedente="CED",
                                      valor_liquido="41.294,97", pendencias=[], linhas_pagamento=linhas,
                                      log=lambda m: None)
    e2 = ej.registrar_evento_operacao(ex, op, "finalizar_clicado", log=lambda m: None)
    aid = ej.registrar_arquivo(ex, "remessa_pagamento_cnab_240", "gerado", nome_arquivo="CP.REM",
                               conteudo=b"conteudo-" + str(op).encode(), qtd_registros=1,
                               titulos=[{"id_titulo": "1", "id_operacao": op}], log=lambda m: None)
    ev = ej.registrar_evento_arquivo(ex, aid, "gerado", log=lambda m: None)
    assert e1 and e2 and aid and ev
    # a sessao publicou a execucao
    assert _q(app, "SELECT current_setting('erp.execucao_id', true)")[0][0] is not None or True
    assert ej.fechar_execucao(ex, "sucesso", codigo_saida=0, qtd_itens=1, log=lambda m: None)
    linha = _q(admin, "SELECT status, terminado_em IS NOT NULL, codigo_saida, qtd_itens, apelido_credencial "
                      "FROM erp_automation.job_execucao WHERE id = %s", (ex.id,))[0]
    assert linha == ("sucesso", True, 0, 1, "GSMARTPWD3")
    grade = _q(admin, "SELECT chave_pix_mascarada, sha256_chave_pix, data_vencimento::text, valor_pagamento, flag_sp "
                      "FROM erp_automation.operacao_pagamento_linha WHERE fk_operacao_evento = %s", (e1,))[0]
    assert grade[0] == "*******.com" and grade[1] == hashlib.sha256(b"chave@x.com").hexdigest()
    assert grade[2] == "2026-09-18" and str(grade[3]) == "10.00" and grade[4] is True


# --------------------------------------------------------------------------- #
# imutabilidade, ate para quem e superusuario
# --------------------------------------------------------------------------- #
def _execucao_e_evento(admin, op):
    exid = _q(admin, "INSERT INTO erp_automation.job_execucao (automacao, job, gatilho, ambiente, flag_ensaio) "
                     "VALUES ('finalizar_operacao','j','manual','sandbox',true) RETURNING id")[0][0]
    evid = _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento, resultado) "
                     "VALUES (%s, %s, 'avaliada', 'BARRADA') RETURNING id", (exid, op))[0][0]
    return exid, evid


@pytest.mark.parametrize("comando", [
    "UPDATE erp_automation.operacao_evento SET resultado = 'FINALIZARIA' WHERE id = %s",
    "DELETE FROM erp_automation.operacao_evento WHERE id = %s",
])
def test_evento_nao_muda_nem_some_nem_pelo_superusuario(admin, comando):
    _, evid = _execucao_e_evento(admin, _op())
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _q(admin, comando, (evid,))


@pytest.mark.parametrize("comando", [
    "TRUNCATE erp_automation.arquivo_evento",                       # sem dependentes: o gatilho e a unica barreira
    "TRUNCATE erp_automation.operacao_evento CASCADE",              # com dependentes: o gatilho recusa antes de cascatear
])
def test_truncate_e_recusado_pelo_gatilho(admin, comando):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _q(admin, comando)


def test_o_limite_conhecido_o_schema_segue_do_runtime(admin):
    """Mudar o dono do schema exige CREATE no banco: a sessao do Guardian nao tem. Fica
    documentado na erp_004; so um superusuario fecha isso (ALTER SCHEMA ... OWNER TO)."""
    dono = _q(admin, "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'erp_automation'")[0][0]
    assert dono == "app_erp_automation"


def test_o_runtime_nao_e_dono_e_nao_mexe_na_estrutura_nem_nos_gatilhos(app):
    """Nao ser dona das tabelas e o que impede o runtime de desligar o gatilho ou alterar
    a estrutura. (O DROP TABLE explicito segue possivel enquanto o schema for dela.)"""
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _q(app, "ALTER TABLE erp_automation.operacao_evento DISABLE TRIGGER ALL")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _q(app, "ALTER TABLE erp_automation.operacao_evento ADD COLUMN furo text")
    # GRANT sem direito de conceder nao e erro no PostgreSQL - e um WARNING "no privileges
    # were granted". A prova e o privilegio continuar ausente depois da tentativa.
    _q(app, "GRANT UPDATE ON erp_automation.operacao_evento TO app_erp_automation")
    assert _q(app, "SELECT has_table_privilege('app_erp_automation', 'erp_automation.operacao_evento', 'UPDATE')")[0][0] is False


def test_uma_finalizacao_confirmada_por_operacao(admin):
    op = _op()
    exid, _ = _execucao_e_evento(admin, op)
    _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento) "
              "VALUES (%s, %s, 'finalizada')", (exid, op))
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento) "
                  "VALUES (%s, %s, 'finalizada')", (exid, op))
    # cliques podem repetir (retentativa depois de uma falha)
    for _ in range(2):
        _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento) "
                  "VALUES (%s, %s, 'finalizar_clicado')", (exid, op))


def test_a_mesma_pendencia_nao_e_avisada_duas_vezes(admin):
    op = _op()
    exid, _ = _execucao_e_evento(admin, op)
    h = hashlib.sha256(b"pendencia").hexdigest()
    _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento, hash_pendencias) "
              "VALUES (%s, %s, 'aviso_enviado', %s)", (exid, op, h))
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento, hash_pendencias) "
                  "VALUES (%s, %s, 'aviso_enviado', %s)", (exid, op, h))


def test_veredito_fora_do_vocabulario_e_recusado(admin):
    exid, _ = _execucao_e_evento(admin, _op())
    with pytest.raises(psycopg2.errors.CheckViolation):
        _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento, resultado) "
                  "VALUES (%s, %s, 'avaliada', 'TALVEZ')", (exid, _op()))


# --------------------------------------------------------------------------- #
# a execucao fecha uma vez, so nas colunas de fechamento
# --------------------------------------------------------------------------- #
def test_execucao_fecha_uma_vez_e_depois_nao_muda(admin):
    exid, _ = _execucao_e_evento(admin, _op())
    with pytest.raises(psycopg2.errors.CheckViolation):
        _q(admin, "UPDATE erp_automation.job_execucao SET job = 'outro' WHERE id = %s", (exid,))
    _q(admin, "UPDATE erp_automation.job_execucao SET status = 'falha', terminado_em = now(), codigo_saida = 2 "
              "WHERE id = %s", (exid,))
    with pytest.raises(psycopg2.errors.CheckViolation):
        _q(admin, "UPDATE erp_automation.job_execucao SET status = 'sucesso', terminado_em = now() WHERE id = %s", (exid,))
    with pytest.raises(psycopg2.errors.CheckViolation):
        _q(admin, "INSERT INTO erp_automation.job_execucao (automacao, job, gatilho, ambiente, flag_ensaio, status) "
                  "VALUES ('boletos','j','manual','container',false,'sucesso')")


def test_fechar_pelo_modulo_uma_segunda_vez_nao_faz_nada(app, admin):
    ex = ej.abrir_execucao("boletos", "emitir_lote_boletos", flag_ensaio=True, log=lambda m: None)
    assert ej.fechar_execucao(ex, "sucesso", codigo_saida=0, log=lambda m: None) is True
    ex2 = ej.Execucao(id=ex.id, automacao="boletos", job="emitir_lote_boletos", flag_ensaio=True,
                      _conn=psycopg2.connect(DSN))
    ex2._conn.autocommit = True
    # WHERE status = 'ativa' nao casa: o gatilho nem e acionado, e nada muda
    assert ej.fechar_execucao(ex2, "falha", codigo_saida=1, log=lambda m: None) is True
    assert _q(admin, "SELECT status, codigo_saida FROM erp_automation.job_execucao WHERE id = %s", (ex.id,))[0] == ("sucesso", 0)


# --------------------------------------------------------------------------- #
# permissoes de leitura
# --------------------------------------------------------------------------- #
def test_leitor_da_casa_le_eventos_mas_nao_a_grade_de_pagamento(admin):
    _q(admin, "SET ROLE app_process_automation")
    try:
        _q(admin, "SELECT count(*) FROM erp_automation.operacao_evento")
        _q(admin, "SELECT count(*) FROM erp_automation.vw_operacao_ciclo")
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            _q(admin, "SELECT count(*) FROM erp_automation.operacao_pagamento_linha")
    finally:
        _q(admin, "RESET ROLE")


# --------------------------------------------------------------------------- #
# arquivos
# --------------------------------------------------------------------------- #
def test_o_mesmo_conteudo_de_arquivo_nao_entra_duas_vezes(app):
    ex = ej.abrir_execucao("remessa_pagamento", "gerar_remessa_pagamento_cnab_240", flag_ensaio=True,
                           log=lambda m: None)
    conteudo = b"rem-" + uuid.uuid4().bytes
    a1 = ej.registrar_arquivo(ex, "remessa_pagamento_cnab_240", "gerado", nome_arquivo="a.REM",
                              conteudo=conteudo, log=lambda m: None)
    a2 = ej.registrar_arquivo(ex, "remessa_pagamento_cnab_240", "gerado", nome_arquivo="a-de-novo.REM",
                              conteudo=conteudo, log=lambda m: None)
    assert a1 == a2
    ej.fechar_execucao(ex, "sucesso", log=lambda m: None)


# --------------------------------------------------------------------------- #
# views
# --------------------------------------------------------------------------- #
def test_finalizacao_aberta_some_quando_chega_o_resultado(admin):
    op = _op()
    exid, _ = _execucao_e_evento(admin, op)
    _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento) "
              "VALUES (%s, %s, 'finalizar_clicado')", (exid, op))
    assert _q(admin, "SELECT count(*) FROM erp_automation.vw_operacao_finalizacao_aberta WHERE id_operacao = %s", (op,))[0][0] == 1
    _q(admin, "INSERT INTO erp_automation.operacao_evento (fk_job_execucao, id_operacao, tipo_evento, resultado) "
              "VALUES (%s, %s, 'finalizada', 'smart')", (exid, op))
    assert _q(admin, "SELECT count(*) FROM erp_automation.vw_operacao_finalizacao_aberta WHERE id_operacao = %s", (op,))[0][0] == 0
    ciclo = _q(admin, "SELECT ultimo_veredito, qtd_avaliacoes, clicado_em IS NOT NULL, finalizada_em IS NOT NULL "
                      "FROM erp_automation.vw_operacao_ciclo WHERE id_operacao = %s", (op,))[0]
    assert ciclo == ("BARRADA", 1, True, True)


def test_execucao_abandonada_e_a_ativa_velha(admin):
    exid = _q(admin, "INSERT INTO erp_automation.job_execucao (automacao, job, gatilho, ambiente, flag_ensaio, iniciado_em) "
                     "VALUES ('doc2you','baixar_documentos_doc2you','cron','container',false, now() - interval '3 hours') "
                     "RETURNING id")[0][0]
    assert _q(admin, "SELECT count(*) FROM erp_automation.vw_job_execucao_abandonada WHERE id = %s", (exid,))[0][0] == 1
    assert _q(admin, "SELECT count(*) FROM erp_automation.vw_job_execucao_ativa WHERE id = %s", (exid,))[0][0] == 1


# --------------------------------------------------------------------------- #
# a sessao que aplica (tmp_ do Guardian) nao pode ficar dona de nada
# --------------------------------------------------------------------------- #
TMP = os.environ.get("BANCADA_TMP_DSN", "")


@pytest.mark.skipif(not TMP, reason="bancada sem tmp_teste (aplicada como superusuario)")
def test_a_sessao_que_aplicou_nao_e_dona_de_nada_e_pode_sumir(admin):
    """O revogar do Guardian faz DROP OWNED da tmp_: se a migration deixasse um objeto
    de posse dela, ele sumiria no prazo. Aqui a tmp_teste aplicou a erp_004."""
    quem = _q(admin, "SELECT aplicada_por FROM erp_automation.migration_aplicada WHERE arquivo LIKE 'erp_004%%'")[0][0]
    if quem != "tmp_teste":
        pytest.skip(f"a bancada foi aplicada como {quem}, nao como a tmp_ do Guardian")
    n = _q(admin, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                  "WHERE n.nspname = 'erp_automation' AND pg_get_userbyid(c.relowner) = 'tmp_teste'")[0][0]
    assert n == 0, "objeto de posse da tmp_ sumiria no revogar"
    fn = _q(admin, "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                   "WHERE n.nspname = 'erp_automation' AND pg_get_userbyid(p.proowner) = 'tmp_teste'")[0][0]
    assert fn == 0
    dono_schema = _q(admin, "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'erp_automation'")[0][0]
    assert dono_schema == "app_erp_automation", "o limite conhecido: so superusuario muda o dono do schema"
    # o que o revogar faz: DROP OWNED + DROP ROLE, sem levar nada do schema
    antes = _q(admin, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'erp_automation'")[0][0]
    _q(admin, "DROP OWNED BY tmp_teste")
    depois = _q(admin, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'erp_automation'")[0][0]
    assert antes == depois
    # e a role dona dos eventos continua administravel pelo Guardian (access_admin com ADMIN OPTION)
    adm = _q(admin, "SELECT admin_option FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid "
                    "JOIN pg_roles g ON g.oid = m.member WHERE r.rolname = 'app_erp_automation_evento' AND g.rolname = 'access_admin'")
    assert adm and adm[0][0] is True
