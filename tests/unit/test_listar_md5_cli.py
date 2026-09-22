# -*- coding: utf-8 -*-
"""listar_md5.py: a memoria do banco para o wrapper — lista no stdout, 1 quando nao da; com
--com-historico, 3 quando o historico dos CSVs (erp_008) ainda nao esta no banco."""
from __future__ import annotations

from src.processors.db.controle import listar_md5 as cli


class _Cur:
    def __init__(self, conn): self.conn = conn; self.sql = None
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def execute(self, sql, params=()):
        self.sql = sql
        self.conn.comandos.append((sql, params))

    def fetchone(self):
        if "to_regclass" in self.sql:
            return (self.conn.tem_tabela,)
        if "SELECT EXISTS" in self.sql:
            return (self.conn.tem_historico,)
        return None

    def fetchall(self): return self.conn.linhas


class _Conn:
    def __init__(self, linhas, tem_tabela=False, tem_historico=False):
        self.linhas, self.tem_tabela, self.tem_historico = linhas, tem_tabela, tem_historico
        self.comandos, self.fechada = [], False
    def cursor(self): return _Cur(self)
    def close(self): self.fechada = True


def test_lista_ordenada_minuscula_sem_repetir(monkeypatch, capsys):
    conn = _Conn([("BBBB",), ("aaaa",), ("bbbb",), (None,)])
    monkeypatch.setattr(cli.execucao_job, "conexao_leitura", lambda job: conn)
    assert cli.main(["retorno_cobranca_cnab_400", "retorno_bb"]) == 0
    assert capsys.readouterr().out.split() == ["aaaa", "bbbb"]
    sql, params = conn.comandos[-1]
    assert "arquivo_historico" not in sql and params == (["retorno_cobranca_cnab_400", "retorno_bb"],)
    assert conn.fechada


def test_com_a_erp_008_a_lista_une_o_historico(monkeypatch, capsys):
    conn = _Conn([("cccc",)], tem_tabela=True, tem_historico=True)
    monkeypatch.setattr(cli.execucao_job, "conexao_leitura", lambda job: conn)
    assert cli.main(["--com-historico", "retorno_bb"]) == 0
    sql, params = conn.comandos[-1]
    assert "UNION SELECT md5 FROM erp_automation.arquivo_historico" in sql
    assert params == (["retorno_bb"], ["retorno_bb"])
    assert capsys.readouterr().out.split() == ["cccc"]


def test_sem_historico_carregado_sai_3_so_quando_pedido(monkeypatch, capsys):
    for tem_tabela in (False, True):
        conn = _Conn([("dddd",)], tem_tabela=tem_tabela, tem_historico=False)
        monkeypatch.setattr(cli.execucao_job, "conexao_leitura", lambda job, c=conn: c)
        assert cli.main(["--com-historico", "retorno_bb"]) == cli.SAIU_SEM_HISTORICO
        assert capsys.readouterr().out.split() == ["dddd"], "a lista sai mesmo assim"
        assert cli.main(["retorno_bb"]) == 0, "o wrapper antigo nao pede e nao muda"
        capsys.readouterr()


def test_tipo_desconhecido_e_sem_banco_saem_com_1_e_stdout_vazio(monkeypatch, capsys):
    assert cli.main(["retorno_x"]) == 1
    assert cli.main([]) == 1
    assert cli.main(["--com-historico"]) == 1
    def _falha(job):
        raise RuntimeError("guardian fora")
    monkeypatch.setattr(cli.execucao_job, "conexao_leitura", _falha)
    assert cli.main(["retorno_bb"]) == 1
    assert capsys.readouterr().out == ""
