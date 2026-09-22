# -*- coding: utf-8 -*-
"""
test_finalizar_sessao_propria.py - o robo de finalizar sobe a PROPRIA sessao do
Smart pelo modulo comum (src.common.clients.smart_sessao), como o remessa_pagamento.

Por que existe: ate 21/09/2026 o main() so anexava num Chrome ja aberto
(connect_over_cdp) e no container ninguem o abria - a 1a rodada em producao
morreu com "CDP 9228 nao responde" antes de logar.

Sem navegador: o Playwright e a sessao sao dubles. Nenhum teste fala com o Smart.
"""
from __future__ import annotations

import contextlib
import importlib
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"
MODULO_SESSAO = RAIZ / "src" / "common" / "clients" / "smart_sessao.py"


@pytest.fixture
def pacote(monkeypatch):
    monkeypatch.setenv("R7_DRY_RUN", "1")
    monkeypatch.setenv("DEBUG_DIR_R7", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"))
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))
    if str(PACOTE) not in sys.path:
        sys.path.insert(0, str(PACOTE))
    for nome in ("finalizar_operacao", "r7_config"):
        sys.modules.pop(nome, None)
    return importlib.import_module("finalizar_operacao")


def test_r7_config_cumpre_o_contrato_do_smart_sessao(pacote):
    """A lista sai do PROPRIO modulo comum: tudo que ele le de `cfg.` existe no r7_config."""
    fonte = MODULO_SESSAO.read_text(encoding="utf-8")
    exigidos = sorted(set(re.findall(r"\bcfg\.([A-Za-z_]+)", fonte)))
    assert exigidos, "o modulo comum deixou de ler cfg.* - o teste precisa ser revisto"
    faltam = [n for n in exigidos if not hasattr(pacote.cfg, n)]
    assert not faltam, f"r7_config nao tem o que o smart_sessao le: {faltam}"
    assert callable(pacote.cfg.ensure_dirs)
    assert pacote.cfg.DISPLAY.startswith(":")


class _CtxDuble:
    pass


@contextlib.contextmanager
def _playwright_duble():
    yield object()


def _preparar(pacote, monkeypatch, sessao):
    import playwright.sync_api
    from src.common.clients import smart_sessao

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", _playwright_duble)
    monkeypatch.setattr(smart_sessao, "sessao", sessao)
    chamadas = []
    monkeypatch.setattr(pacote, "ciclo",
                        lambda ctx, ops, executar, email, execucao=None: chamadas.append((ctx, ops, executar)) or [])
    monkeypatch.setattr(pacote, "_resumo", lambda laudos, executar: None)
    # o registro de execucao e duble: o main() nao pode tentar banco de verdade num teste
    ex = pacote.execucao_job.Execucao(id=None, automacao="finalizar_operacao", job="j", flag_ensaio=True)
    monkeypatch.setattr(pacote.execucao_job, "abrir_execucao", lambda *a, **k: ex)
    monkeypatch.setattr(pacote.execucao_job, "fechar_execucao", lambda *a, **k: False)
    return chamadas


def test_main_abre_a_propria_sessao_e_roda_o_ciclo_nela(pacote, monkeypatch):
    ctx = _CtxDuble()
    recebido = {}

    @contextlib.contextmanager
    def sessao(p, cfg, usar_cdp=False, logar=True, log=print):
        recebido.update(cfg=cfg, usar_cdp=usar_cdp, logar=logar)
        yield ctx

    chamadas = _preparar(pacote, monkeypatch, sessao)
    monkeypatch.setattr(sys, "argv", ["finalizar_operacao.py"])

    assert pacote.main() == 0
    assert chamadas == [(ctx, None, False)], "o ciclo tem de rodar no ctx da sessao, em DRY"
    assert recebido["cfg"] is pacote.cfg
    assert recebido["usar_cdp"] is False, "sem --cdp o robo sobe o proprio Chrome"
    assert recebido["logar"] is True


def test_flag_cdp_anexa_em_vez_de_subir(pacote, monkeypatch):
    recebido = {}

    @contextlib.contextmanager
    def sessao(p, cfg, usar_cdp=False, logar=True, log=print):
        recebido["usar_cdp"] = usar_cdp
        yield _CtxDuble()

    _preparar(pacote, monkeypatch, sessao)
    monkeypatch.setattr(sys, "argv", ["finalizar_operacao.py", "--cdp"])

    assert pacote.main() == 0
    assert recebido["usar_cdp"] is True


def test_sessao_que_falha_encerra_com_exit_2_sem_rodar_o_ciclo(pacote, monkeypatch):
    from src.common.clients import smart_sessao

    @contextlib.contextmanager
    def sessao(p, cfg, usar_cdp=False, logar=True, log=print):
        raise smart_sessao.SemSessao("dublê: auto-login falhou")
        yield  # noqa: unreachable - forma de contextmanager

    chamadas = _preparar(pacote, monkeypatch, sessao)
    monkeypatch.setattr(sys, "argv", ["finalizar_operacao.py"])

    assert pacote.main() == 2
    assert chamadas == [], "sem sessao o ciclo nao pode rodar"
