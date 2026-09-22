# -*- coding: utf-8 -*-
"""
test_finalizar_botao_pagamento.py - botao Pagamento desabilitado (operacao aberta por outro
usuario no Smart): o finalizador espera ele liberar e, se nao liberar, falha dizendo o
motivo, em vez de morrer num "Locator.click: Timeout 15000ms" que nao explica nada.

Por que existe: em 22/09/2026 a 65854 deu esse timeout a tarde inteira, e a 65877 as
15:45. O README ja dizia que a tela pode travar ~90 s.

Sem navegador: o botao e um duble. Nenhum teste fala com o Smart.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"


@pytest.fixture
def mp(monkeypatch):
    monkeypatch.setenv("DEBUG_DIR_R7", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"))
    for p in (str(RAIZ), str(PACOTE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    mod = importlib.import_module("mapear_pagamento")
    monkeypatch.setattr(mod, "_INTERVALO_BTN_PAGAMENTO_S", 0.01)
    return mod


class _Botao:
    def __init__(self, desabilitado_por):
        self.restam = desabilitado_por     # quantas leituras ainda vem desabilitado
        self.leituras = 0

    def is_disabled(self):
        self.leituras += 1
        if self.restam is None:
            return True
        if self.restam > 0:
            self.restam -= 1
            return True
        return False


def test_botao_habilitado_segue_sem_esperar(mp, monkeypatch):
    monkeypatch.setattr(mp.cfg, "ESPERA_BTN_PAGAMENTO_S", 5)
    botao = _Botao(0)
    mp._esperar_botao_pagamento(botao, "65879", log=lambda m: None)
    assert botao.leituras == 1


def test_botao_que_libera_durante_a_espera(mp, monkeypatch):
    monkeypatch.setattr(mp.cfg, "ESPERA_BTN_PAGAMENTO_S", 5)
    mensagens = []
    mp._esperar_botao_pagamento(_Botao(3), "65877", log=mensagens.append)
    assert any("liberou" in m for m in mensagens)


def test_botao_que_nao_libera_falha_dizendo_o_motivo(mp, monkeypatch):
    monkeypatch.setattr(mp.cfg, "ESPERA_BTN_PAGAMENTO_S", 0.05)
    with pytest.raises(RuntimeError) as erro:
        mp._esperar_botao_pagamento(_Botao(None), "65854", log=lambda m: None)
    assert "aberta por outro usuario" in str(erro.value)
