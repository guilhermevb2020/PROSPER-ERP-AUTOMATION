# -*- coding: utf-8 -*-
"""A carga historica das remessas: acha pelo sufixo, confere md5, pula o que ja esta,
so registra --pra-valer, e com a DATA de entao."""
from __future__ import annotations

import hashlib
from datetime import datetime

import pytest

from src.processors.db.controle import carregar_remessas_historicas as carga


def _arvore(tmp_path, arquivos):
    base = tmp_path / "Remessas" / "2026" / "08-Agosto" / "10" / "MoneyPlus"
    base.mkdir(parents=True)
    for nome, dados in arquivos.items():
        (base / nome).write_bytes(dados)
    return str(tmp_path / "Remessas")


class _Cliente:
    def __init__(self, existentes=()):
        self.existentes = set(existentes); self.chamadas = []; self.n = 300

    def buscar_arquivo(self, ex, tipo, **kw):
        self.chamadas.append(("busca", kw["sha256"]))
        return 7 if kw["sha256"] in self.existentes else None

    def registrar_arquivo(self, ex, tipo, sentido, **kw):
        self.chamadas.append(("arquivo", tipo, sentido, kw)); self.n += 1; return self.n

    def registrar_evento_arquivo(self, ex, arq, tipo, **kw):
        self.chamadas.append(("evento", arq, tipo, kw)); return 1


@pytest.fixture
def cenario(tmp_path, monkeypatch):
    a = b"0" * 400 + b"\r\n" + b"A" * 400 + b"\r\n"
    b = b"0" * 400 + b"\r\n" + b"B" * 400 + b"\r\n"
    arvore = _arvore(tmp_path, {"ANFEER INDUSTRIA - CB10080000026.REM": a,
                                "OUTRA EMPRESA - CB10080000027.REM": b"conteudo trocado"})
    linhas = [
        {"id": "25695", "arquivo": "CB10080000026.REM", "tipo": "mp anfeer Envio de cobranca registrado",
         "bytes": str(len(a)), "md5": hashlib.md5(a).hexdigest(), "titulos": "3", "baixado_em": "2026-08-10 18:05:33"},
        {"id": "25696", "arquivo": "CB10080000027.REM", "tipo": "mp x", "bytes": "1", "md5": hashlib.md5(b).hexdigest(),
         "titulos": "1", "baixado_em": "2026-08-10 18:06:00"},
        {"id": "25697", "arquivo": "CB10080000028.REM", "tipo": "mp y", "bytes": "1", "md5": "zzz",
         "titulos": "1", "baixado_em": "2026-08-10 18:07:00"},
    ]
    return arvore, linhas, a


def test_indice_pelo_sufixo_do_nome(cenario):
    arvore, _, _ = cenario
    indice = carga.indexar_arvore(arvore)
    assert set(indice) == {"CB10080000026.REM", "CB10080000027.REM"}


def test_ensaio_relata_sem_registrar(cenario, monkeypatch):
    arvore, linhas, _ = cenario
    cliente = _Cliente()
    monkeypatch.setattr(carga, "execucao_job", cliente)
    r = carga.carregar(linhas, carga.indexar_arvore(arvore), "EX", ensaio=True, log=lambda m: None)
    assert r.registradas == ["25695"]
    assert r.md5_diverge == [("25696", "CB10080000027.REM")]
    assert r.sem_arquivo == [("25697", "CB10080000028.REM")]
    assert not r.completa
    assert not any(c[0] in ("arquivo", "evento") for c in cliente.chamadas)


def test_pra_valer_registra_com_a_data_de_entao_e_pula_o_que_ja_esta(cenario, monkeypatch):
    arvore, linhas, a = cenario
    cliente = _Cliente()
    monkeypatch.setattr(carga, "execucao_job", cliente)
    r = carga.carregar(linhas[:1], carga.indexar_arvore(arvore), "EX", ensaio=False, log=lambda m: None)
    assert r.registradas == ["25695"] and r.completa
    (_, tipo, sentido, kw), (_, arq1, ev1, kw1), (_, arq2, ev2, kw2) = [c for c in cliente.chamadas if c[0] != "busca"]
    assert (tipo, sentido, kw["nome_arquivo"], kw["conteudo"]) == ("remessa_cobranca_cnab_400", "gerado", "CB10080000026.REM", a)
    assert kw["conta_label"].startswith("mp anfeer") and kw["qtd_registros"] == 3
    assert kw["detalhe"]["id_no_smart"] == "25695" and kw["detalhe"]["md5"] == hashlib.md5(a).hexdigest()
    esperado = datetime(2026, 8, 10, 18, 5, 33, tzinfo=carga.TZ)
    assert kw["registrado_em"] == esperado
    assert (ev1, kw1["ocorrido_em"]) == ("gerado", esperado) and (ev2, kw2["ocorrido_em"]) == ("enviado", esperado)
    assert kw2["resultado"].endswith("ANFEER INDUSTRIA - CB10080000026.REM")
    # segunda passada: o sha ja esta -> pula
    cliente2 = _Cliente(existentes={hashlib.sha256(a).hexdigest()})
    monkeypatch.setattr(carga, "execucao_job", cliente2)
    r2 = carga.carregar(linhas[:1], carga.indexar_arvore(arvore), "EX", ensaio=False, log=lambda m: None)
    assert r2.ja_estavam == ["25695"] and r2.registradas == []


def test_main_abre_execucao_de_controle_e_devolve_3_quando_incompleta(cenario, tmp_path, monkeypatch):
    arvore, linhas, _ = cenario
    csvp = tmp_path / "controle.csv"
    import csv as _csv
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=list(linhas[0].keys())); w.writeheader(); w.writerows(linhas)
    chamadas = []
    monkeypatch.setattr(carga.execucao_job, "abrir_execucao", lambda *a, **k: chamadas.append(("abrir", a, k)) or "EX")
    monkeypatch.setattr(carga.execucao_job, "fechar_execucao", lambda ex, status, **k: chamadas.append(("fechar", status, k)))
    monkeypatch.setattr(carga.execucao_job, "buscar_arquivo", lambda *a, **k: None)
    assert carga.main(["--csv", str(csvp), "--arvore", arvore, "--dias", "9999"]) == carga.SAIU_INCOMPLETO
    abrir = next(c for c in chamadas if c[0] == "abrir")
    assert abrir[1] == ("controle", "carregar_remessas_historicas") and abrir[2]["flag_ensaio"] is True
    assert chamadas[-1][1] == "falha" and chamadas[-1][2]["codigo_saida"] == 3
