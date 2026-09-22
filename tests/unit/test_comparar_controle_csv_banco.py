# -*- coding: utf-8 -*-
"""
test_comparar_controle_csv_banco.py - a paridade CSV x banco, sem banco.

O lado do banco e um dicionario; o lado do CSV sao arquivos temporarios com o cabecalho
REAL de cada controle. O que se prova: o filtro por dia, a chave por md5, o arquivo
re-entregue (linha nova no CSV, mesma linha no banco), a linha sem hash (contada, nao
comparada), o CSV ausente (marcado, nao confundido com "nada hoje") e o exit code.
"""
from __future__ import annotations

import pytest

from src.processors.db.controle import comparar_controle_csv_banco as cmp

DIA = "2026-09-22"


def _csv(tmp_path, nome, cabecalho, linhas):
    p = tmp_path / nome
    p.write_text("\n".join([cabecalho] + linhas) + "\n", encoding="utf-8")
    return str(p)


def test_le_so_as_linhas_do_dia_e_chaveia_por_hash(tmp_path):
    caminho = _csv(tmp_path, "controle_processados.csv",
                   "arquivo,nome_smart,hash,conta,titulos,ja_processado,processado,ocorrencias,criticas,divergencias,motivo,quando",
                   ["A.RET,A.RET,AAAA,291,3,False,True,liquidacao=3,0,,OK,2026-09-21 08:50:00",
                    "B.RET,B.RET,bbbb,291,1,False,True,liquidacao=1,0,,OK,2026-09-22 08:51:00",
                    "C.RET,C.RET,,291,1,False,False,,0,,sem hash,2026-09-22 08:52:00"])
    lado = cmp.ler_csv(caminho, "hash", "quando", DIA)
    assert lado.existe and lado.linhas_dia == 2
    assert lado.por_hash == {"bbbb": "B.RET"}, "so o dia pedido, hash em minusculas"
    assert lado.sem_hash == 1


def test_csv_ausente_e_marcado_nao_e_dia_vazio(tmp_path):
    lado = cmp.ler_csv(str(tmp_path / "nao_existe.csv"), "md5", "baixado_em", DIA)
    assert lado.existe is False and lado.por_hash == {}


def test_paridade_e_divergencia_por_lado():
    lado = cmp.LadoCsv(por_hash={"a1": "A.REM", "b2": "B.REM"})
    r = cmp.comparar("remessa", lado, {"a1": "A.REM", "b2": "B.REM"})
    assert r.paridade and cmp.codigo_de_saida([r]) == cmp.SAIU_OK
    r = cmp.comparar("remessa", lado, {"a1": "A.REM", "c3": "C.REM"})
    assert r.so_csv == [("b2", "B.REM")] and r.so_banco == [("c3", "C.REM")]
    assert not r.paridade and cmp.codigo_de_saida([r]) == cmp.SAIU_DIVERGENTE


def test_arquivo_reentregue_conta_pelo_evento_do_dia():
    """O portao BB recusa o mesmo .RET todo dia: linha nova no CSV, uma linha em `arquivo`
    (registrada no primeiro dia). O lado do banco inclui "com evento hoje", entao o
    dicionario que `ler_banco` devolve ja traz o arquivo — e a paridade fecha."""
    lado = cmp.LadoCsv(por_hash={"e5": "BBAPI0000031.RET"})
    assert cmp.comparar("retorno", lado, {"e5": "BBAPI0000031.RET"}).paridade


def test_ler_banco_pergunta_registrado_hoje_ou_evento_hoje():
    class _Cur:
        def __init__(self): self.sql = None; self.params = None
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params): self.sql, self.params = sql, params
        def fetchall(self): return [("A.RET", "aaaa"), ("B.RET", None), ("C.RET", "CCCC")]
    class _Conn:
        cur = _Cur()
        def cursor(self): return self.cur
    conn = _Conn()
    banco = cmp.ler_banco(conn, ("retorno_cobranca_cnab_400", "retorno_bb"), DIA)
    assert banco == {"aaaa": "A.RET", "CCCC": "C.RET"}, "sem md5 nao entra na comparacao"
    assert "arquivo_evento" in conn.cur.sql and "registrado_em AT TIME ZONE" in conn.cur.sql
    assert conn.cur.params["tipos"] == ["retorno_cobranca_cnab_400", "retorno_bb"]
    assert conn.cur.params["dia"] == DIA


def test_relatorio_diz_o_que_so_existe_de_um_lado():
    lado = cmp.LadoCsv(por_hash={"a1": "A.REM"}, sem_hash=1)
    r = cmp.comparar("remessa", lado, {"z9": "Z.REM"})
    texto = cmp.relatorio(DIA, [r])
    assert "DIVERGE" in texto and "so no CSV   : A.REM" in texto and "so no BANCO : Z.REM" in texto
    assert "1 linha(s) do dia sem hash" in texto
    assert cmp.resumo_json(DIA, [r])["familias"]["remessa"] == {
        "csv": 1, "banco": 1, "sem_hash": 1, "csv_existe": True,
        "so_csv": ["A.REM"], "so_banco": ["Z.REM"], "paridade": False}


def test_main_registra_a_execucao_e_devolve_o_exit(tmp_path, monkeypatch):
    for fam in cmp.FAMILIAS:
        monkeypatch.setenv(fam.csv_env, _csv(
            tmp_path, f"{fam.nome}.csv", f"arquivo,{fam.coluna_hash},{fam.coluna_quando}",
            [f"X_{fam.nome},ff{fam.nome[:2]},{DIA} 10:00:00"]))
    banco = {fam.nome: {f"ff{fam.nome[:2]}": f"X_{fam.nome}"} for fam in cmp.FAMILIAS}
    banco["pagamento"] = {}  # o banco nao tem a remessa de pagamento do dia
    chamadas = []
    monkeypatch.setattr(cmp, "ler_banco", lambda conn, tipos, dia, tz=None: next(
        banco[f.nome] for f in cmp.FAMILIAS if f.tipos == tipos))

    class _Conn:
        def close(self): chamadas.append("close")
    monkeypatch.setattr(cmp.execucao_job, "conexao_leitura", lambda job: _Conn())
    monkeypatch.setattr(cmp.execucao_job, "abrir_execucao",
                        lambda *a, **k: chamadas.append(("abrir", a, k)) or "EX")
    monkeypatch.setattr(cmp.execucao_job, "fechar_execucao",
                        lambda ex, status, **k: chamadas.append(("fechar", ex, status, k)))

    assert cmp.main(["--dia", DIA]) == cmp.SAIU_DIVERGENTE
    abrir = next(c for c in chamadas if c[0] == "abrir")
    assert abrir[1] == ("controle", "comparar_controle_csv_banco")
    assert abrir[2]["obrigatoria"] is False and abrir[2]["flag_ensaio"] is False
    fechar = next(c for c in chamadas if c[0] == "fechar")
    assert fechar[2] == "falha" and fechar[3]["codigo_saida"] == cmp.SAIU_DIVERGENTE
    assert fechar[3]["qtd_itens"] == 4
    assert fechar[3]["detalhe"]["familias"]["pagamento"]["so_csv"] == ["X_pagamento"]
    assert "close" in chamadas


def test_sem_banco_sai_com_erro_e_fecha_a_execucao(monkeypatch):
    chamadas = []
    monkeypatch.setattr(cmp.execucao_job, "abrir_execucao", lambda *a, **k: "EX")
    monkeypatch.setattr(cmp.execucao_job, "fechar_execucao",
                        lambda ex, status, **k: chamadas.append((status, k["codigo_saida"])))
    def _falha(job):
        raise RuntimeError("guardian fora")
    monkeypatch.setattr(cmp.execucao_job, "conexao_leitura", _falha)
    assert cmp.main(["--dia", DIA]) == cmp.SAIU_ERRO
    assert chamadas == [("falha", cmp.SAIU_ERRO)]
