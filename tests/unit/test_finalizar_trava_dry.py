# -*- coding: utf-8 -*-
"""
test_finalizar_trava_dry.py - R7_DRY_RUN=1 impede o clique em Finalizar em QUALQUER
caminho, inclusive quem chama finalizar_da_grade() direto com executar=True.

Por que existe: ate 21/09/2026 a trava do ambiente vivia so no main() do
finalizar_operacao.py; o scripts/sandbox/finalizar_op_executar.py --confirmar chamava
ciclo(executar=True) e clicava mesmo com R7_DRY_RUN=1. O clique e irreversivel.

Sem navegador: a grade e o botao sao dubles. Nenhum teste aqui fala com o Smart.
"""
from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"


@pytest.fixture
def fin(monkeypatch):
    """Importa o modulo `finalizar` do pacote, como o robo faz (pelo diretorio)."""
    monkeypatch.setenv("R7_DRY_RUN", "1")
    monkeypatch.setenv("DEBUG_DIR_R7", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"))
    if str(PACOTE) not in sys.path:
        sys.path.insert(0, str(PACOTE))
    for nome in ("finalizar", "r7_config"):
        sys.modules.pop(nome, None)
    fin = importlib.import_module("finalizar")
    # relogio fixo dentro da janela (a trava de horario tem teste proprio)
    monkeypatch.setattr(fin.cfg, "_agora", lambda: datetime(2026, 9, 22, 10, 0))
    return fin


class _Botao:
    def __init__(self, desabilitado=False):
        self.cliques = 0
        self._desabilitado = desabilitado

    def count(self):
        return 1

    def is_disabled(self):
        return self._desabilitado

    def click(self, timeout=None):
        self.cliques += 1


class _Sair:
    def __init__(self, grade):
        self._grade = grade

    def click(self, timeout=None):
        self._grade.saidas += 1


class _Grade:
    """Faz as vezes do frame: tem o botao Sair (#btConfirmar2) e o Finalizar."""

    def __init__(self, botao):
        self.saidas = 0
        self._botao = botao

    def locator(self, seletor):
        if seletor == "#btConfirmar2":
            return _Sair(self)
        return self._botao


class _Pagina:
    def on(self, *_a, **_k):
        pass


def _preparar(fin, monkeypatch, botao):
    grade = _Grade(botao)
    monkeypatch.setattr(fin, "_frame_com", lambda pg, sel, timeout_s=None: grade)
    monkeypatch.setattr(fin, "_confirmar_no_smart", lambda pg, op: (True, "dublê: finalizada"))
    monkeypatch.setattr(fin.time, "sleep", lambda s: None)
    return grade


def test_com_dry_run_ligado_o_botao_habilitado_NAO_e_clicado(fin, monkeypatch):
    monkeypatch.setattr(fin.cfg, "DRY_RUN", True)
    botao = _Botao()
    grade = _preparar(fin, monkeypatch, botao)

    r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)

    assert r["situacao"] == "dry" and r["ok"] is False
    assert botao.cliques == 0, "R7_DRY_RUN=1 e o botao foi clicado"
    assert grade.saidas == 1, "o DRY ainda precisa chegar ate o botao para dizer se clicaria"
    assert "65071" in r["detalhe"]


def test_com_dry_run_desligado_o_clique_acontece_uma_vez(fin, monkeypatch):
    monkeypatch.setattr(fin.cfg, "DRY_RUN", False)
    botao = _Botao()
    _preparar(fin, monkeypatch, botao)

    r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)

    assert botao.cliques == 1
    assert r["ok"] is True and r["situacao"] == "finalizada"


def test_botao_desabilitado_vem_antes_da_trava(fin, monkeypatch):
    """A trava nao esconde o diagnostico: botao desabilitado continua sendo reportado."""
    monkeypatch.setattr(fin.cfg, "DRY_RUN", True)
    botao = _Botao(desabilitado=True)
    _preparar(fin, monkeypatch, botao)

    r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)

    assert r["situacao"] == "botao_desabilitado"
    assert botao.cliques == 0
