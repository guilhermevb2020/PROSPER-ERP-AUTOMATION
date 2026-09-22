# -*- coding: utf-8 -*-
"""O controle dos downloads do credito mora no banco desde 22/09/2026: cada download e
cada move sao eventos em operacao_evento, e o controle e a soma deles. Nenhum CSV e lido
nem escrito. Sem banco: dubles do execucao_job."""
from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "src" / "processors" / "web" / "credito"


@pytest.fixture
def banco(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for p in (str(RAIZ), str(PASTA)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for m in ("banco", "config"):
        sys.modules.pop(m, None)
    mod = importlib.import_module("banco")
    from src.common.clients import execucao_job
    eventos, gravados = [], []

    def _listar(ex, tipos, *, ops=None, log=print):
        if mod._fora:
            return None
        alvo = None if ops is None else {int(o) for o in ops}
        return [e for e in eventos if e["tipo_evento"] in tipos
                and (alvo is None or e["id_operacao"] in alvo)]

    def _registrar(ex, op, tipo, **kw):
        gravados.append((op, tipo, kw))
        return len(gravados)

    mod._fora = False
    monkeypatch.setattr(execucao_job, "atual", lambda: object())
    monkeypatch.setattr(execucao_job, "listar_eventos_operacao", _listar)
    monkeypatch.setattr(execucao_job, "registrar_evento_operacao", _registrar)
    mod._eventos, mod._gravados = eventos, gravados
    return mod


def _ev(op, tipo, horas, **detalhe):
    return {"id_operacao": op, "tipo_evento": tipo, "resultado": None,
            "ocorrido_em": datetime(2026, 9, 22, 12, tzinfo=timezone.utc) + timedelta(hours=horas),
            "detalhe": detalhe}


def test_o_controle_e_a_soma_dos_eventos_e_um_ok_nao_se_desfaz(banco):
    banco._eventos += [
        _ev(65001, "documentos_baixados", 0, arquivo_nfe="nf.pdf", arquivo_resumo="r.pdf",
            nfe_ok=True, resumo_ok=True),
        _ev(65001, "documentos_baixados", 1, arquivo_nfe="", arquivo_resumo="", nfe_ok=False,
            resumo_ok=False),
        _ev(65002, "documentos_baixados", 0, arquivo_resumo="r2.pdf", nfe_ok=False, resumo_ok=True),
        _ev(65002, "etapa_movida", 1)]
    c = banco.carregar_controle(["65001", "65002"])
    assert c["65001"]["nfe_ok"] and c["65001"]["resumo_ok"], "o download ruim depois nao desmarca"
    assert c["65001"]["arquivo_nfe"] == "nf.pdf" and not c["65001"]["etapa_movida"]
    assert c["65002"]["etapa_movida"] and not c["65002"]["nfe_ok"]
    assert banco.pode_mover(c["65002"]) and not banco.ja_baixou(c["65002"])
    assert c["65001"]["data_download"].endswith(":00:00"), "o ultimo download, em hora local"


def test_so_as_ops_pedidas(banco):
    banco._eventos += [_ev(65001, "documentos_baixados", 0, resumo_ok=True),
                       _ev(65003, "documentos_baixados", 0, resumo_ok=True)]
    assert set(banco.carregar_controle(["65003"])) == {"65003"}


def test_sem_banco_nenhuma_op_e_movida(banco, capsys):
    banco._fora = True
    assert banco.carregar_controle(["65001"]) == {}
    assert "nenhuma op movida" in capsys.readouterr().out
    assert not banco.pode_mover(banco.carregar_controle(["65001"]).get("65001"))


def test_download_e_move_viram_eventos_do_que_aconteceu(banco):
    banco.registrar_download("65010", None, "/tmp/resumo.pdf")
    banco.marcar_etapa_movida("65010")
    banco.registrar_download("abc", "x", "y")              # op invalida: nada
    (op, tipo, kw), (op2, tipo2, kw2) = banco._gravados
    assert (op, tipo, kw["resultado"], kw["fato"]) == (65010, "documentos_baixados", "PARCIAL", True)
    assert kw["detalhe"] == {"arquivo_nfe": "", "arquivo_resumo": "/tmp/resumo.pdf",
                             "nfe_ok": False, "resumo_ok": True}
    assert (op2, tipo2, kw2["resultado"]) == (65010, "etapa_movida", banco.config.ROTULO_ANALISE_CREDITO)
    assert len(banco._gravados) == 2


def test_nenhum_csv_e_escrito(banco, tmp_path):
    banco.registrar_download("65010", "nf.pdf", "r.pdf")
    banco.marcar_etapa_movida("65010")
    banco.carregar_controle(["65010"])
    assert not list(tmp_path.rglob("*.csv"))
    assert not hasattr(banco, "_salvar_controle") and not hasattr(banco.config, "ARQ_CONTROLE_DOWNLOAD")


def test_fora_do_job_nao_ha_controle_nem_registro(banco, monkeypatch):
    from src.common.clients import execucao_job
    monkeypatch.setattr(execucao_job, "atual", lambda: None)
    assert banco.carregar_controle(["65001"]) == {}
    banco.registrar_download("65001", "a", "b")
    assert banco._gravados == []
