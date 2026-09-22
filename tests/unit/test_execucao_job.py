# -*- coding: utf-8 -*-
"""
test_execucao_job.py - o registro de execucao e eventos, sem banco.

O banco e um duble que grava cada comando. O que se prova aqui e o CONTRATO do
modulo: o que ele manda para o banco, como degrada sem banco, como levanta em
modo estrito, e as normalizacoes (hash de pendencias, PIX mascarado, data e
valor em formato brasileiro). O comportamento do banco em si (gatilhos, unicos,
permissoes) e provado em tests/integration/test_execucao_job_bancada.py.
"""
from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

import pytest

from src.common.clients import execucao_job as ej


# --------------------------------------------------------------------------- #
# dubles
# --------------------------------------------------------------------------- #
class _Cursor:
    def __init__(self, conn):
        self._conn = conn
        self._ultimo = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._conn.comandos.append((" ".join(sql.split()), params))
        if self._conn.falhar_em and self._conn.falhar_em in sql:
            raise RuntimeError(f"duble: falha em {self._conn.falhar_em}")
        self._ultimo = sql

    def fetchone(self):
        if "RETURNING id" in self._ultimo or "SELECT id FROM" in self._ultimo:
            if self._conn.sem_retorno:
                return None
            self._conn.proximo_id += 1
            return (self._conn.proximo_id,)
        return (None,)


class _Conn:
    def __init__(self):
        self.comandos = []
        self.proximo_id = 100
        self.fechada = False
        self.falhar_em = None
        self.sem_retorno = False

    def cursor(self):
        return _Cursor(self)

    def close(self):
        self.fechada = True


@pytest.fixture
def banco(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    for var in ("HUB_RUN_ID", "HUB_TASK_NOME", "ERP_AUTOMATION_REVISION"):
        monkeypatch.delenv(var, raising=False)
    return conn


def _sql(conn, i):
    return conn.comandos[i][0]


# --------------------------------------------------------------------------- #
# abrir
# --------------------------------------------------------------------------- #
def test_abrir_grava_a_execucao_e_publica_o_id_na_sessao(banco):
    ex = ej.abrir_execucao("finalizar_operacao", "finalizar_operacao_aguardando_assinatura",
                           flag_ensaio=True, ambiente="sandbox", apelido_credencial="GSMARTPWD3",
                           log=lambda m: None)
    assert ex.id == 101 and ex.registra and not ex.estrito
    assert "INSERT INTO erp_automation.job_execucao" in _sql(banco, 0)
    params = banco.comandos[0][1]
    assert params[0:2] == ("finalizar_operacao", "finalizar_operacao_aguardando_assinatura")
    assert params[4] == "manual", "sem HUB_RUN_ID o gatilho e manual"
    assert params[5] == "sandbox" and params[6] is True
    assert params[7] == "GSMARTPWD3"
    assert "set_config('erp.execucao_id'" in _sql(banco, 1) and banco.comandos[1][1] == ("101",)


def test_abrir_nunca_grava_senha_como_apelido(banco):
    ex = ej.abrir_execucao("boletos", "emitir_lote_boletos", flag_ensaio=False,
                           apelido_credencial="MinhaSenhaReal123", log=lambda m: None)
    assert banco.comandos[0][1][7] is None
    assert ex.id == 101


def test_abrir_le_o_gatilho_do_hub_quando_ele_se_identifica(banco, monkeypatch):
    monkeypatch.setenv("HUB_RUN_ID", "abc123")
    monkeypatch.setenv("HUB_TASK_NOME", "finalizar_operacao_aguardando_assinatura")
    ej.abrir_execucao("finalizar_operacao", "finalizar_operacao_aguardando_assinatura",
                      flag_ensaio=True, log=lambda m: None)
    params = banco.comandos[0][1]
    assert params[2] == "finalizar_operacao_aguardando_assinatura" and params[3] == "abc123"
    assert params[4] == "cron"


def test_abrir_recusa_automacao_fora_do_vocabulario(banco):
    with pytest.raises(ValueError):
        ej.abrir_execucao("robo", "x", flag_ensaio=True)


def test_sem_banco_em_ensaio_degrada_e_avisa_uma_vez(monkeypatch):
    def _sem_banco(job):
        raise ConnectionError("duble: recusou")

    monkeypatch.setattr(ej, "_conectar", _sem_banco)
    avisos = []
    ex = ej.abrir_execucao("finalizar_operacao", "job", flag_ensaio=True, log=avisos.append)
    assert ex.id is None and not ex.registra
    assert ej.registrar_evento_operacao(ex, 1, "avaliada", resultado="BARRADA", log=avisos.append) is None
    assert ej.registrar_evento_operacao(ex, 2, "avaliada", resultado="BARRADA", log=avisos.append) is None
    assert ej.fechar_execucao(ex, "sucesso", log=avisos.append) is False
    assert sum("sem banco para registrar a execucao" in a for a in avisos) == 1
    # o aviso do registrar e um por motivo, nao um por chamada
    assert sum("registro nao feito: execucao sem banco" in a for a in avisos) == 1


def test_sem_banco_em_modo_real_levanta(monkeypatch):
    def _sem_banco(job):
        raise ConnectionError("duble: recusou")

    monkeypatch.setattr(ej, "_conectar", _sem_banco)
    with pytest.raises(ej.ExecucaoIndisponivel):
        ej.abrir_execucao("finalizar_operacao", "job", flag_ensaio=False, obrigatoria=True,
                          log=lambda m: None)


# --------------------------------------------------------------------------- #
# eventos de operacao
# --------------------------------------------------------------------------- #
def _aberta(banco, **kw):
    kw.setdefault("flag_ensaio", True)
    ex = ej.abrir_execucao("finalizar_operacao", "job", log=lambda m: None, **kw)
    banco.comandos.clear()
    banco.proximo_id = 100      # o proximo id devolvido pelo duble volta a ser 101
    return ex


def test_evento_avaliada_grava_veredito_pendencias_hash_e_linhas_da_grade(banco):
    ex = _aberta(banco)
    linhas = [{"_linha": "1", "tipo": "PIX", "tipo_pix": "Bco | Ag | C/C", "chave_pix": "001/1266/71149",
               "cta_origem": "mp prospere", "numero": "", "cta_destino": "METALURGICA | 001",
               "bco": "001", "agencia": "1266", "tipo_conta": "CC", "cc": "71149",
               "favorecido": "METALURGICA CONDU TREF", "cpf_cnpj": "12.345.678/0001-90",
               "id_transacao": "", "vencto": "18/09/2026", "valor": "2.705,36", "sp": "X"}]
    pend = ["Duplicata: 1 de 2 SEM assinatura", "Aditivo: falta assinatura"]
    eid = ej.registrar_evento_operacao(ex, "65071", "avaliada", resultado="BARRADA", cedente="CED",
                                       valor_liquido="41.294,97", pendencias=pend,
                                       linhas_pagamento=linhas, log=lambda m: None)
    assert eid == 101
    sql, params = banco.comandos[0]
    assert "INSERT INTO erp_automation.operacao_evento" in sql
    assert params[0] == ex.id and params[1] == 65071 and params[2] == "avaliada" and params[3] == "BARRADA"
    assert params[5] == Decimal("41294.97")
    assert params[6] == ("json", pend)
    assert params[7] == ej.hash_pendencias(pend)
    sql2, p2 = banco.comandos[1]
    assert "INSERT INTO erp_automation.operacao_pagamento_linha" in sql2
    assert p2[0] == 101
    colunas = sql2.split("(fk_operacao_evento, ")[1].split(")")[0].split(", ")
    linha = dict(zip(colunas, p2[1:]))
    assert linha["numero_linha"] == 1 and linha["favorecido"] == "METALURGICA CONDU TREF"
    assert linha["chave_pix_mascarada"] == "**********1149"
    assert linha["sha256_chave_pix"] == hashlib.sha256(b"001/1266/71149").hexdigest()
    assert linha["data_vencimento"] == date(2026, 9, 18)
    assert linha["valor_pagamento"] == Decimal("2705.36") and linha["flag_sp"] is True
    assert linha["numero_documento"] is None, "campo vazio da grade vira NULL, nao string vazia"


def test_hash_de_pendencias_ignora_ordem_e_vazio(banco):
    a = ej.hash_pendencias(["x", "y"])
    assert a == ej.hash_pendencias(["y", " x "]) and len(a) == 64
    assert ej.hash_pendencias([]) is None and ej.hash_pendencias(None) is None


def test_tipo_de_evento_fora_do_vocabulario_e_recusado_antes_do_banco(banco):
    ex = _aberta(banco)
    with pytest.raises(ValueError):
        ej.registrar_evento_operacao(ex, 1, "clicou")
    assert banco.comandos == []


def test_registrar_que_falha_em_modo_estrito_levanta_e_em_ensaio_so_avisa(banco):
    ex = _aberta(banco, flag_ensaio=False, obrigatoria=True)
    banco.falhar_em = "operacao_evento"
    with pytest.raises(ej.ErroDeRegistro):
        ej.registrar_evento_operacao(ex, 1, "finalizar_clicado", log=lambda m: None)
    ex2 = _aberta(banco)
    avisos = []
    assert ej.registrar_evento_operacao(ex2, 1, "finalizar_clicado", log=avisos.append) is None
    assert any("falhou" in a for a in avisos)


# --------------------------------------------------------------------------- #
# arquivos
# --------------------------------------------------------------------------- #
def test_arquivo_e_registrado_pelo_sha256_com_seus_titulos(banco, tmp_path):
    ex = _aberta(banco)
    conteudo = b"01REMESSA\r\n1TITULO\r\n9\r\n"
    arq = tmp_path / "CP2109000001.REM"
    arq.write_bytes(conteudo)
    aid = ej.registrar_arquivo(ex, "remessa_pagamento_cnab_240", "gerado", nome_arquivo=arq.name,
                               caminho=str(arq), qtd_registros=1, valor_total="1.234,50",
                               conta_id="404", conta_label="mp prospere",
                               titulos=[{"id_titulo": "934235", "id_operacao": 65071,
                                         "id_pagamento_smart": "146", "valor_titulo": "1.234,50", "flag_pix": True}],
                               log=lambda m: None)
    assert aid == 101
    sql, params = banco.comandos[0]
    assert "INSERT INTO erp_automation.arquivo" in sql and "ON CONFLICT (tipo_arquivo, sha256)" in sql
    assert params[4] == hashlib.sha256(conteudo).hexdigest() and params[5] == len(conteudo)
    assert params[7] == Decimal("1234.50")
    sql2, p2 = banco.comandos[1]
    assert "INSERT INTO erp_automation.arquivo_titulo" in sql2
    assert p2[:4] == (101, 1, "934235", 65071) and p2[6] == Decimal("1234.50") and p2[7] is True


def test_o_mesmo_conteudo_devolve_o_id_existente_sem_regravar_titulos(banco):
    ex = _aberta(banco)
    banco.sem_retorno = True          # o INSERT ... DO NOTHING nao devolve id: ja existia
    banco.proximo_id = 500
    aid = ej.registrar_arquivo(ex, "retorno_pagamento_cnab_240", "recebido", nome_arquivo="a.RET",
                               conteudo=b"x", titulos=[{"id_titulo": "1"}], log=lambda m: None)
    # o SELECT do existente tambem passa por fetchone; com sem_retorno ele devolve None
    assert aid is None
    assert not any("arquivo_titulo" in c[0] for c in banco.comandos), "titulo nao e regravado"


def test_evento_de_arquivo_sem_arquivo_registrado_nao_vai_ao_banco(banco):
    ex = _aberta(banco)
    avisos = []
    assert ej.registrar_evento_arquivo(ex, None, "enviado", log=avisos.append) is None
    assert banco.comandos == [] and avisos


# --------------------------------------------------------------------------- #
# fechar
# --------------------------------------------------------------------------- #
def test_fechar_grava_status_exit_e_contagem_e_fecha_a_conexao(banco):
    ex = _aberta(banco)
    assert ej.fechar_execucao(ex, "sucesso", codigo_saida=0, qtd_itens=3, detalhe={"fila": 3},
                              log=lambda m: None) is True
    sql, params = banco.comandos[0]
    assert "UPDATE erp_automation.job_execucao SET terminado_em = now(), status = %s" in sql
    assert "WHERE id = %s AND status = 'ativa'" in sql
    assert params[0] == "sucesso" and params[1] == 0 and params[2] == 3 and params[4] == ex.id
    assert banco.fechada and ex._conn is None and not ex.registra


def test_fechar_com_status_invalido_e_recusado(banco):
    ex = _aberta(banco)
    with pytest.raises(ValueError):
        ej.fechar_execucao(ex, "ok")


# --------------------------------------------------------------------------- #
# normalizacoes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bruto,esperado", [
    ("2.705,36", Decimal("2705.36")), ("R$ 795.974,88", Decimal("795974.88")),
    ("1234.5", Decimal("1234.5")), ("", None), (None, None), ("abc", None), (10, Decimal("10")),
])
def test_decimal_br(bruto, esperado):
    assert ej.decimal_br(bruto) == esperado


@pytest.mark.parametrize("bruto,esperado", [
    ("18/09/2026", date(2026, 9, 18)), ("18/09/2026 10:00", date(2026, 9, 18)),
    ("2026-09-18", None), ("", None), (None, None), (date(2026, 1, 2), date(2026, 1, 2)),
])
def test_data_br(bruto, esperado):
    assert ej.data_br(bruto) == esperado


def test_mascara_pix_mostra_so_os_ultimos_quatro():
    assert ej.mascarar_chave_pix("financeiro@empresa.com.br") == "*********************m.br"
    assert ej.mascarar_chave_pix("abcd") == "****" and ej.mascarar_chave_pix("") is None


def test_apelido_seguro_aceita_apelido_do_guardian_e_recusa_o_resto():
    assert ej.apelido_seguro("GSMARTPWD2") == "GSMARTPWD2"
    assert ej.apelido_seguro("__GUARDIAN_SANDBOX_CAPSOLVER_API_KEY__") == "__GUARDIAN_SANDBOX_CAPSOLVER_API_KEY__"
    assert ej.apelido_seguro("senha-de-verdade") is None and ej.apelido_seguro(None) is None
