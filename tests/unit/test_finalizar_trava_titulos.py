# -*- coding: utf-8 -*-
"""
test_finalizar_trava_titulos.py - sem os tipos dos titulos o finalizador nao confere
documentos nem clica: o veredito e ERRO.

Por que existe: documentos_exigidos([]) pede so Aditivo + Nota promissoria. Duplicata
e Letra de cambio dependem do tipo dos titulos (DUR/DSR/DMR, LCB). Ate 22/09/2026 um
titulo nao lido seguia com a lista vazia, e uma operacao com duplicatas SEM assinatura
passaria na checagem de documentos - no dia em que o clique foi ligado.

Sem navegador: tela, doc2you, grade e banco sao dubles. Nenhum teste fala com o Smart.
"""
from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"


@pytest.fixture
def job(monkeypatch):
    monkeypatch.setenv("R7_DRY_RUN", "0")
    monkeypatch.setenv("DEBUG_DIR_R7", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"))
    for p in (str(RAIZ), str(PACOTE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for nome in ("finalizar_operacao", "finalizar", "r7_config"):
        sys.modules.pop(nome, None)
    mod = importlib.import_module("finalizar_operacao")
    monkeypatch.setattr(mod.cfg, "_agora", lambda: datetime(2026, 9, 22, 10, 0))
    return mod


class _Pagina:
    def on(self, *a, **k):
        pass

    def close(self):
        pass

    def goto(self, *a, **k):
        pass


class _Ctx:
    def new_page(self):
        return _Pagina()


def _armar(job, monkeypatch, tipos):
    monkeypatch.setattr(job, "_dados_da_operacao", lambda ctx, op: (tipos, "CEDENTE X", 1000.0))
    chamadas = {"docs": 0, "pag": 0, "clique": 0}

    def _docs(ctx, op, tipos_titulos, nome_cedente=None):
        chamadas["docs"] += 1
        return {"ok": True, "pendencias": [], "observacoes": [], "exigidos": ["aditivo"],
                "encontrados": {}}

    def _pag(pg, op, log=print):
        chamadas["pag"] += 1
        return {"ok": True, "pendencias": [], "linhas": []}

    def _clique(pg, op, aceitar_dialogos=None, log=print):
        chamadas["clique"] += 1
        return {"ok": True, "situacao": "finalizada", "detalhe": "", "dialogos": []}

    monkeypatch.setattr(job.checagem_docs, "conferir", _docs)
    monkeypatch.setattr(job.checagem_docs, "_ROTULO", {"aditivo": "Aditivo"})
    monkeypatch.setattr(job.checagem_pagamento, "conferir", _pag)
    monkeypatch.setattr(job, "_etapa_da_operacao", lambda ctx, op: "Aguardando Ass.")
    monkeypatch.setattr(job.fin, "finalizar_da_grade", _clique)
    eventos = []
    monkeypatch.setattr(job.execucao_job, "registrar_evento_operacao",
                        lambda ex, op, tipo, **kw: eventos.append(tipo))
    monkeypatch.setattr(job, "_registrar_finalizada", lambda op, cedente: None)
    monkeypatch.setattr(job, "_avisar_finalizacao",
                        lambda op, cedente, valor, detalhes, confirmacao, execucao=None: None)
    return chamadas, eventos


@pytest.mark.parametrize("tipos", [[], ["", ""], [None]])
def test_titulos_nao_lidos_viram_erro_sem_conferir_nem_clicar(job, monkeypatch, tipos):
    chamadas, eventos = _armar(job, monkeypatch, tipos)
    laudo = job.processar(_Ctx(), "65871", executar=True, execucao=object())
    assert chamadas == {"docs": 0, "pag": 0, "clique": 0}
    assert eventos == []
    assert job._veredito(laudo) == "ERRO" and "tipos dos titulos" in laudo["erro"]


def test_com_titulos_lidos_o_fluxo_segue(job, monkeypatch):
    chamadas, eventos = _armar(job, monkeypatch, ["DMR"])
    laudo = job.processar(_Ctx(), "65871", executar=True, execucao=object())
    assert chamadas == {"docs": 1, "pag": 1, "clique": 1}
    assert laudo["acao"] == "finalizada"
