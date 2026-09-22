# -*- coding: utf-8 -*-
"""
Encerramento administrativo de uma execucao abandonada (22/09/2026): a funcao do cliente
(o UPDATE que manda, com autor e motivo, so para o que a view lista) e a CLI
(ensaio por padrao; pra valer exige ERP_OPERADOR/ERP_MOTIVO e registra a propria execucao).
Sem banco: dubles.
"""
from __future__ import annotations

import pytest

from src.common.clients import execucao_job as ej
from src.processors.db.controle import encerrar_abandonada as cli


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
        self._ultimo = sql

    def fetchone(self):
        if "RETURNING id" in self._ultimo:
            if "job_execucao SET" in self._ultimo:      # o UPDATE administrativo
                return (self._conn.id_encerrado,) if self._conn.id_encerrado else None
            self._conn.proximo_id += 1                  # INSERT da execucao
            return (self._conn.proximo_id,)
        return self._conn.linha_alvo


class _Conn:
    def __init__(self, *, linha_alvo=None, id_encerrado=None):
        self.comandos = []
        self.proximo_id = 900
        self.fechada = False
        self.linha_alvo = linha_alvo
        self.id_encerrado = id_encerrado

    def cursor(self):
        return _Cursor(self)

    def close(self):
        self.fechada = True


ABANDONADA = (164, "remessa_cobranca", "gerar_remessa_cobranca_cnab_400", "cron", "ativa", "22/09 11:30", True)
FECHADA = (163, "retorno_cobranca", "processar_retorno_bb", "cron", "sucesso", "22/09 11:25", False)


@pytest.fixture
def banco(monkeypatch):
    conn = _Conn(id_encerrado=164)
    monkeypatch.setattr(ej, "_conectar", lambda job: conn)
    monkeypatch.setattr(ej, "_json", lambda v: ("json", v))
    for var in ("HUB_RUN_ID", "HUB_TASK_NOME", "ERP_AUTOMATION_REVISION", "ERP_OPERADOR", "ERP_MOTIVO"):
        monkeypatch.delenv(var, raising=False)
    return conn


# --------------------------------------------------------------------------- #
# a funcao do cliente
# --------------------------------------------------------------------------- #
def test_encerrar_manda_update_para_abandonada_com_autor_e_motivo(banco):
    ex = ej.abrir_execucao("controle", "encerrar_execucao_abandonada", flag_ensaio=False,
                           gatilho="manual", obrigatoria=True, operador="ana", motivo="fechamento perdido")
    assert ej.encerrar_abandonada(ex, 164, operador="ana", motivo="fechamento perdido") == 164
    sql, params = banco.comandos[-1]
    assert "UPDATE erp_automation.job_execucao SET terminado_em = now(), status = 'abandonada'" in sql
    assert "detalhe_json = detalhe_json ||" in sql
    assert "status = 'ativa'" in sql and "vw_job_execucao_abandonada" in sql and "RETURNING id" in sql
    assert "a.automacao = 'credito' AND a.iniciado_em > now() - interval '13 hours'" in sql  # regra da erp_007
    assert "sucesso" not in sql  # nunca promete o que nao prova
    assert params[1] == 164
    assert params[0] == ("json", {"encerramento_administrativo": {
        "operador": "ana", "motivo": "fechamento perdido", "por_execucao": ex.id}})


def test_encerrar_devolve_none_quando_a_view_nao_lista(banco):
    banco.id_encerrado = None
    ex = ej.abrir_execucao("controle", "encerrar_execucao_abandonada", flag_ensaio=False, obrigatoria=True)
    assert ej.encerrar_abandonada(ex, 163, operador="ana", motivo="x") is None


def test_encerrar_exige_operador_e_motivo(banco):
    ex = ej.abrir_execucao("controle", "encerrar_execucao_abandonada", flag_ensaio=False, obrigatoria=True)
    with pytest.raises(ValueError):
        ej.encerrar_abandonada(ex, 164, operador="", motivo="x")
    with pytest.raises(ValueError):
        ej.encerrar_abandonada(ex, 164, operador="ana", motivo="  ")
    assert not any("job_execucao SET" in c[0] for c in banco.comandos)


def test_encerrar_degradada_ou_sem_execucao_nao_faz_nada(monkeypatch):
    def _falha(job):
        raise RuntimeError("guardian fora")
    monkeypatch.setattr(ej, "_conectar", _falha)
    ex = ej.abrir_execucao("controle", "encerrar_execucao_abandonada", flag_ensaio=True, obrigatoria=False)
    assert ej.encerrar_abandonada(ex, 164, operador="ana", motivo="x") is None
    assert ej.encerrar_abandonada(None, 164, operador="ana", motivo="x") is None


# --------------------------------------------------------------------------- #
# a CLI
# --------------------------------------------------------------------------- #
@pytest.fixture
def cli_montada(monkeypatch):
    """conexao de leitura com o alvo; abrir/fechar/encerrar gravados num registro."""
    reg = {"abrir": [], "fechar": [], "encerrar": [], "leitura": _Conn(linha_alvo=ABANDONADA)}
    for var in ("ERP_OPERADOR", "ERP_MOTIVO"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli.execucao_job, "conexao_leitura", lambda job: reg["leitura"])

    def _abrir(*a, **k):
        reg["abrir"].append((a, k))
        return "EX"
    monkeypatch.setattr(cli.execucao_job, "abrir_execucao", _abrir)
    monkeypatch.setattr(cli.execucao_job, "fechar_execucao", lambda ex, status, **k: reg["fechar"].append((ex, status, k)))

    def _encerrar(ex, id_alvo, *, operador, motivo, log=print):
        reg["encerrar"].append((ex, id_alvo, operador, motivo))
        return id_alvo
    monkeypatch.setattr(cli.execucao_job, "encerrar_abandonada", _encerrar)
    return reg


def test_ensaio_mostra_a_linha_e_nao_grava_nem_abre_execucao(cli_montada, capsys):
    assert cli.main(["164"]) == cli.SAIU_OK
    saida = capsys.readouterr().out
    assert "#164 remessa_cobranca/gerar_remessa_cobranca_cnab_400" in saida and "ABANDONADA" in saida
    assert "ENSAIO" in saida and "--pra-valer" in saida
    assert cli_montada["abrir"] == [] and cli_montada["encerrar"] == [] and cli_montada["fechar"] == []
    assert cli_montada["leitura"].fechada
    assert cli_montada["leitura"].comandos[0][1] == {"id": 164, "tz": cli.TZ_PADRAO}
    assert "vw_job_execucao_abandonada" in cli_montada["leitura"].comandos[0][0]
    assert "interval '13 hours'" in cli_montada["leitura"].comandos[0][0]  # o mesmo criterio do UPDATE


def test_pra_valer_sem_operador_ou_motivo_sai_com_2_sem_tocar_no_banco(cli_montada, monkeypatch, capsys):
    assert cli.main(["164", "--pra-valer"]) == cli.SAIU_USO
    monkeypatch.setenv("ERP_OPERADOR", "ana")
    assert cli.main(["164", "--pra-valer"]) == cli.SAIU_USO
    assert "ERP_OPERADOR e ERP_MOTIVO" in capsys.readouterr().err
    assert cli_montada["leitura"].comandos == [] and cli_montada["encerrar"] == []


def test_pra_valer_encerra_e_registra_a_propria_execucao(cli_montada, monkeypatch, capsys):
    monkeypatch.setenv("ERP_OPERADOR", "ana")
    monkeypatch.setenv("ERP_MOTIVO", "fechamento perdido (BUG-702); remessas recarregadas na #176")
    assert cli.main(["164", "--pra-valer"]) == cli.SAIU_OK
    (a, k), = cli_montada["abrir"]
    assert a == ("controle", "encerrar_execucao_abandonada")
    assert k["flag_ensaio"] is False and k["obrigatoria"] is True and k["gatilho"] == "manual"
    assert k["operador"] == "ana" and k["motivo"].startswith("fechamento perdido") and k["detalhe"] == {"alvo": 164}
    assert cli_montada["encerrar"] == [("EX", 164, "ana", "fechamento perdido (BUG-702); remessas recarregadas na #176")]
    (ex, status, kw), = cli_montada["fechar"]
    assert (ex, status, kw["codigo_saida"], kw["qtd_itens"]) == ("EX", "sucesso", 0, 1)
    assert kw["detalhe"] == {"alvo": 164, "encerrada": True}
    assert "#164 encerrada como `abandonada` por ana" in capsys.readouterr().out


def test_alvo_que_nao_esta_abandonada_sai_com_3_sem_gravar(cli_montada, monkeypatch, capsys):
    monkeypatch.setenv("ERP_OPERADOR", "ana")
    monkeypatch.setenv("ERP_MOTIVO", "x")
    cli_montada["leitura"].linha_alvo = FECHADA
    assert cli.main(["163", "--pra-valer"]) == cli.SAIU_NAO_ABANDONADA
    assert "nao esta abandonada" in capsys.readouterr().out
    assert cli_montada["abrir"] == [] and cli_montada["encerrar"] == []


def test_alvo_inexistente_sai_com_3(cli_montada, capsys):
    cli_montada["leitura"].linha_alvo = None
    assert cli.main(["999"]) == cli.SAIU_NAO_ABANDONADA
    assert "nao existe" in capsys.readouterr().out


def test_corrida_alvo_fechado_entre_leitura_e_gravacao_sai_com_3_e_fecha_como_sucesso(cli_montada, monkeypatch):
    monkeypatch.setenv("ERP_OPERADOR", "ana")
    monkeypatch.setenv("ERP_MOTIVO", "x")
    monkeypatch.setattr(cli.execucao_job, "encerrar_abandonada", lambda ex, i, *, operador, motivo, log=print: None)
    assert cli.main(["164", "--pra-valer"]) == cli.SAIU_NAO_ABANDONADA
    (ex, status, kw), = cli_montada["fechar"]
    assert (status, kw["codigo_saida"], kw["qtd_itens"], kw["detalhe"]) == ("sucesso", 3, 0, {"alvo": 164, "encerrada": False})


def test_sem_banco_sai_com_1(cli_montada, monkeypatch, capsys):
    def _falha(job):
        raise RuntimeError("guardian fora")
    monkeypatch.setattr(cli.execucao_job, "conexao_leitura", _falha)
    assert cli.main(["164"]) == cli.SAIU_ERRO
    assert "sem banco" in capsys.readouterr().out


def test_pra_valer_sem_banco_para_registrar_nao_age(cli_montada, monkeypatch, capsys):
    monkeypatch.setenv("ERP_OPERADOR", "ana")
    monkeypatch.setenv("ERP_MOTIVO", "x")

    def _indisponivel(*a, **k):
        raise cli.execucao_job.ExecucaoIndisponivel("sem banco")
    monkeypatch.setattr(cli.execucao_job, "abrir_execucao", _indisponivel)
    assert cli.main(["164", "--pra-valer"]) == cli.SAIU_ERRO
    assert cli_montada["encerrar"] == [] and cli_montada["fechar"] == []


def test_erro_de_registro_no_update_sai_com_1_e_fecha_como_falha(cli_montada, monkeypatch, capsys):
    monkeypatch.setenv("ERP_OPERADOR", "ana")
    monkeypatch.setenv("ERP_MOTIVO", "x")

    def _erro(ex, i, *, operador, motivo, log=print):
        raise cli.execucao_job.ErroDeRegistro("gatilho recusou")
    monkeypatch.setattr(cli.execucao_job, "encerrar_abandonada", _erro)
    assert cli.main(["164", "--pra-valer"]) == cli.SAIU_ERRO
    (ex, status, kw), = cli_montada["fechar"]
    assert (status, kw["codigo_saida"]) == ("falha", 1)
