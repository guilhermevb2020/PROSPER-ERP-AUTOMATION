# -*- coding: utf-8 -*-
"""A carga do historico dos CSVs: o que cada familia vira no banco, a regra do fuso do
texto (UTC antes da recriacao do container, local depois) e o ensaio que nao grava."""
from __future__ import annotations

import csv
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.processors.db.controle import carregar_historico_csv as carga

RAIZ = Path(__file__).resolve().parents[2]


def test_texto_antes_da_virada_e_utc_e_depois_e_hora_local():
    antes = carga.instante_do_csv("2026-08-26 01:31:26")
    assert antes == datetime(2026, 8, 26, 1, 31, 26, tzinfo=timezone.utc)
    depois = carga.instante_do_csv("22/09/2026 16:50:45", "%d/%m/%Y %H:%M:%S")
    assert depois.utcoffset().total_seconds() == -3 * 3600
    assert carga.instante_do_csv("") is None and carga.instante_do_csv("ontem") is None


def test_retorno_uma_linha_por_md5_com_o_que_a_memoria_usa():
    linhas = [
        {"arquivo": "CB2108.RET", "nome_smart": "CB2108", "hash": "A" * 32, "conta": "291",
         "processado": "False", "motivo": "conta pausada", "quando": "2026-08-21 12:00:00"},
        {"arquivo": "CB2108.RET", "nome_smart": "CB2108", "hash": "a" * 32, "conta": "",
         "processado": "True", "motivo": "", "quando": "2026-08-21 13:00:00"},
        {"arquivo": "CBR1.ret", "nome_smart": "CBR1", "hash": "b" * 32, "conta": "395",
         "processado": "False", "motivo": "portao", "quando": "2026-09-22 10:00:00"},
        {"arquivo": "x", "nome_smart": "", "hash": "", "conta": "", "processado": "", "quando": ""}]
    saida, sem = carga.historico_retorno(linhas, "controle_processados.csv")
    assert sem == 1 and len(saida) == 2
    cb = next(s for s in saida if s["md5"] == "a" * 32)
    assert cb["tipo_arquivo"] == "retorno_cobranca_cnab_400"
    assert cb["detalhe"]["processado"] is True and cb["detalhe"]["linhas_csv"] == 2
    assert cb["detalhe"]["nomes_smart"] == ["CB2108"] and cb["origem"] == "controle_processados.csv"
    assert cb["tratado_em"] == datetime(2026, 8, 21, 13, tzinfo=timezone.utc)
    bb = next(s for s in saida if s["md5"] == "b" * 32)
    assert bb["tipo_arquivo"] == "retorno_bb" and bb["detalhe"]["processado"] is False


def test_retorno_de_pagamento_um_md5_por_arquivo():
    saida, sem = carga.historico_retorno_pagamento(
        [{"arquivo": "CP1.RET", "hash": "c" * 32, "status_http": "200", "quando": "2026-09-22 17:48:17"},
         {"arquivo": "CP1.RET", "hash": "C" * 32, "status_http": "200", "quando": "2026-09-22 17:49:00"},
         {"arquivo": "?", "hash": "zz", "status_http": "", "quando": ""}], "controle.csv")
    assert sem == 1 and len(saida) == 1
    assert saida[0]["tipo_arquivo"] == "retorno_pagamento_cnab_240"
    assert saida[0]["detalhe"]["quando_csv"] == "2026-09-22 17:49:00"


def test_credito_documentos_e_move_com_o_instante_do_csv():
    eventos, fora = carga.eventos_credito([
        {"id_operacao": "65001", "data_download": "03/07/2026 12:45:36", "arquivo_nfe": "nf.pdf",
         "arquivo_resumo": "r.pdf", "nfe_ok": "1", "resumo_ok": "1", "etapa_movida": "1"},
        {"id_operacao": "65002", "data_download": "22/09/2026 17:27:14", "arquivo_nfe": "",
         "arquivo_resumo": "r2.pdf", "nfe_ok": "0", "resumo_ok": "1", "etapa_movida": "0"},
        {"id_operacao": "abc", "data_download": "22/09/2026 17:27:14"}],
        "controle_downloads.csv", "Análise de crédito")
    assert fora == 1
    assert [(e["id_operacao"], e["tipo_evento"], e["resultado"]) for e in eventos] == [
        (65001, "documentos_baixados", "OK"), (65001, "etapa_movida", "Análise de crédito"),
        (65002, "documentos_baixados", "PARCIAL")]
    assert eventos[0]["ocorrido_em"] == datetime(2026, 7, 3, 12, 45, 36, tzinfo=timezone.utc)
    assert all(e["detalhe"]["origem"] == "controle_downloads.csv" for e in eventos)
    assert eventos[2]["detalhe"]["resumo_ok"] is True and eventos[2]["detalhe"]["nfe_ok"] is False


def test_rotulo_da_etapa_e_o_mesmo_do_job_credito(monkeypatch):
    pasta = str(RAIZ / "src" / "processors" / "web" / "credito")
    monkeypatch.syspath_prepend(pasta)
    sys.modules.pop("config", None)
    try:
        cfg = importlib.import_module("config")
        assert carga.ROTULO_ETAPA_CREDITO == cfg.ROTULO_ANALISE_CREDITO
    finally:
        sys.modules.pop("config", None)


def test_ensaio_le_e_conta_sem_gravar(tmp_path, monkeypatch, capsys):
    ret = tmp_path / "controle_processados.csv"
    with open(ret, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["arquivo", "nome_smart", "hash", "conta", "processado",
                                          "motivo", "quando"])
        w.writeheader()
        w.writerow({"arquivo": "a.RET", "nome_smart": "a", "hash": "d" * 32, "conta": "291",
                    "processado": "True", "motivo": "", "quando": "2026-09-01 10:00:00"})
    chamadas = []
    monkeypatch.setattr(carga.execucao_job, "abrir_execucao",
                        lambda *a, **k: chamadas.append(("abrir", k["flag_ensaio"])) or object())
    monkeypatch.setattr(carga.execucao_job, "fechar_execucao",
                        lambda ex, status, **k: chamadas.append(("fechar", status)))
    monkeypatch.setattr(carga.execucao_job, "anotar", lambda *a: None)
    monkeypatch.setattr(carga.execucao_job, "carregar_historico_arquivos",
                        lambda *a, **k: pytest.fail("ensaio nao grava"))
    assert carga.main(["--familia", "retorno", "--csv", f"retorno={ret}"]) == 0
    assert chamadas == [("abrir", True), ("fechar", "sucesso")]
    assert "1 md5" in capsys.readouterr().out


def test_pra_valer_exige_quem_e_por_que(monkeypatch):
    monkeypatch.delenv("ERP_OPERADOR", raising=False)
    monkeypatch.delenv("ERP_MOTIVO", raising=False)
    assert carga.main(["--pra-valer"]) == carga.SAIU_SEM_AUTOR
