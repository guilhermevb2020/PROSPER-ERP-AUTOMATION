# -*- coding: utf-8 -*-
"""listar_md5.py: a memoria do banco para o wrapper — lista no stdout, 1 quando nao da."""
from __future__ import annotations

import pytest

from src.processors.db.controle import listar_md5 as cli


class _Cur:
    def __init__(self, linhas): self.linhas = linhas; self.sql = None; self.params = None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params): self.sql, self.params = sql, params
    def fetchall(self): return self.linhas


class _Conn:
    def __init__(self, linhas): self.cur = _Cur(linhas); self.fechada = False
    def cursor(self): return self.cur
    def close(self): self.fechada = True


def test_lista_ordenada_minuscula_sem_repetir(monkeypatch, capsys):
    conn = _Conn([("BBBB",), ("aaaa",), ("bbbb",), (None,)])
    monkeypatch.setattr(cli.execucao_job, "conexao_leitura", lambda job: conn)
    assert cli.main(["retorno_cobranca_cnab_400", "retorno_bb"]) == 0
    assert capsys.readouterr().out.split() == ["aaaa", "bbbb"]
    assert conn.cur.params == (["retorno_cobranca_cnab_400", "retorno_bb"],) and conn.fechada


def test_tipo_desconhecido_e_sem_banco_saem_com_1_e_stdout_vazio(monkeypatch, capsys):
    assert cli.main(["retorno_x"]) == 1
    assert cli.main([]) == 1
    def _falha(job):
        raise RuntimeError("guardian fora")
    monkeypatch.setattr(cli.execucao_job, "conexao_leitura", _falha)
    assert cli.main(["retorno_bb"]) == 1
    assert capsys.readouterr().out == ""
