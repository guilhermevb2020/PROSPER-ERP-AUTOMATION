# -*- coding: utf-8 -*-
"""
test_finalizar_registra_eventos.py - o finalizador registra a execucao e os eventos
na ORDEM certa, e em modo real nao clica sem registro.

Tudo e duble (Smart, doc2you, grade, banco): o que se prova e a sequencia -
avaliada por op, finalizar_clicado ANTES do clique, o resultado DEPOIS, o aviso
por ultimo - e que a execucao degradada em modo real impede o clique.
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
    monkeypatch.setenv("R7_DRY_RUN", "1")
    monkeypatch.setenv("DEBUG_DIR_R7", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"))
    for p in (str(RAIZ), str(PACOTE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for nome in ("finalizar_operacao", "r7_config"):
        sys.modules.pop(nome, None)
    mod = importlib.import_module("finalizar_operacao")
    monkeypatch.setattr(mod.cfg, "PAGAMENTO_SO_APOS_ASSINATURAS", True)
    # relogio fixo dentro da janela: a trava de horario (R7_HORA_LIMITE_FINALIZAR)
    # nao pode depender da hora em que a suite roda
    monkeypatch.setattr(mod.cfg, "_agora", lambda: datetime(2026, 9, 22, 10, 0))
    return mod


class _Registro:
    """Duble do execucao_job: guarda a ordem dos eventos."""

    def __init__(self, registra=True, estrito=False):
        self.eventos = []
        self.registra = registra
        self.estrito = estrito
        self.id = 7 if registra else None

    def registrar_evento_operacao(self, ex, op, tipo, **kw):
        if not self.registra and self.estrito:
            raise RuntimeError("ErroDeRegistro: sem banco em modo real")
        self.eventos.append((str(op), tipo, kw))
        return len(self.eventos) if self.registra else None


def _armar(job, monkeypatch, registro):
    monkeypatch.setattr(job.execucao_job, "registrar_evento_operacao", registro.registrar_evento_operacao)
    return registro


class _Pagina:
    def on(self, *a, **k):
        pass

    def close(self):
        pass


class _Ctx:
    def new_page(self):
        return _Pagina()


def _docs_ok(ctx, op, tipos, nome_cedente=None):
    return {"ok": True, "pendencias": [], "observacoes": [], "exigidos": ["contrato"],
            "encontrados": {"contrato": {"assinados": 1, "total": 1}}}


def _grade_ok(pg, op, log=print):
    return {"ok": True, "pendencias": [], "linhas": [
        {"_linha": "1", "tipo": "PIX", "cta_origem": "mp prospere", "favorecido": "F",
         "vencto": "18/09/2026", "sp": "X", "valor": "10,00"}]}


def _preparar_processar(job, monkeypatch, resultado_clique):
    monkeypatch.setattr(job, "_dados_da_operacao", lambda ctx, op: (["DUR"], "CEDENTE X", 1000.0))
    monkeypatch.setattr(job.checagem_docs, "conferir", _docs_ok)
    monkeypatch.setattr(job.checagem_docs, "_ROTULO", {"contrato": "Contrato"})
    monkeypatch.setattr(job.checagem_pagamento, "conferir", _grade_ok)
    monkeypatch.setattr(job, "_etapa_da_operacao", lambda ctx, op: "Aguardando Ass.")
    cliques = []

    def _finalizar(pg, op, aceitar_dialogos=None, log=print):
        cliques.append(str(op))
        return dict(resultado_clique)

    monkeypatch.setattr(job.fin, "finalizar_da_grade", _finalizar)
    avisos = []
    monkeypatch.setattr(job, "_avisar_finalizacao",
                        lambda op, cedente, valor, detalhes, confirmacao, execucao=None: avisos.append(str(op)))
    return cliques, avisos


def test_em_modo_real_o_clique_e_registrado_antes_e_o_resultado_depois(job, monkeypatch):
    reg = _armar(job, monkeypatch, _Registro())
    cliques, avisos = _preparar_processar(job, monkeypatch,
                                          {"ok": True, "situacao": "finalizada", "detalhe": "Smart confirma", "dialogos": []})
    laudo = job.processar(_Ctx(), "65071", executar=True, execucao=reg)
    assert laudo["acao"] == "finalizada" and cliques == ["65071"] and avisos == ["65071"]
    tipos = [t for _, t, _ in reg.eventos]
    assert tipos == ["finalizar_clicado", "finalizada"], tipos
    assert reg.eventos[1][2]["resultado"] == "finalizada"
    assert reg.eventos[0][2]["cedente"] == "CEDENTE X" and reg.eventos[0][2]["valor_liquido"] == 1000.0


def test_clique_que_falha_vira_finalizacao_falhou(job, monkeypatch):
    reg = _armar(job, monkeypatch, _Registro())
    cliques, avisos = _preparar_processar(job, monkeypatch,
                                          {"ok": False, "situacao": "nao_confirmou", "detalhe": "x", "dialogos": ["alert: y"]})
    laudo = job.processar(_Ctx(), "65071", executar=True, execucao=reg)
    assert laudo["acao"].startswith("falha ao finalizar") and avisos == []
    assert [t for _, t, _ in reg.eventos] == ["finalizar_clicado", "finalizacao_falhou"]
    assert reg.eventos[1][2]["detalhe"]["dialogos"] == ["alert: y"]


def test_operador_que_finalizou_antes_vira_finalizada_por_outro(job, monkeypatch):
    reg = _armar(job, monkeypatch, _Registro())
    _preparar_processar(job, monkeypatch,
                        {"ok": False, "situacao": "finalizada_por_outro", "detalhe": "ja estava", "dialogos": []})
    job.processar(_Ctx(), "65071", executar=True, execucao=reg)
    assert [t for _, t, _ in reg.eventos] == ["finalizar_clicado", "finalizada_por_outro"]


def test_em_dry_nao_ha_clique_nem_evento_de_clique(job, monkeypatch):
    reg = _armar(job, monkeypatch, _Registro())
    cliques, _ = _preparar_processar(job, monkeypatch, {"ok": False, "situacao": "dry", "detalhe": "", "dialogos": []})
    laudo = job.processar(_Ctx(), "65071", executar=False, execucao=reg)
    assert laudo["acao"] == "finalizaria (DRY)" and cliques == []
    assert reg.eventos == [], "em DRY o unico evento e a avaliacao, registrada pelo ciclo"


def test_em_modo_real_sem_registro_nao_ha_clique(job, monkeypatch):
    """Sem banco em modo estrito, registrar levanta ANTES do clique: o except de
    processar guarda o erro no laudo e o botao nunca e tocado."""
    reg = _armar(job, monkeypatch, _Registro(registra=False, estrito=True))
    cliques, avisos = _preparar_processar(job, monkeypatch,
                                          {"ok": True, "situacao": "finalizada", "detalhe": "", "dialogos": []})
    laudo = job.processar(_Ctx(), "65071", executar=True, execucao=reg)
    assert cliques == [] and avisos == []
    assert laudo["erro"] and "ErroDeRegistro" in laudo["erro"]


def test_ciclo_registra_uma_avaliacao_por_operacao_com_o_veredito(job, monkeypatch):
    reg = _armar(job, monkeypatch, _Registro())
    monkeypatch.setattr(job.listar_fila, "listar", lambda ctx: ["1", "2", "3"])
    monkeypatch.setattr(job.checagem_docs, "sso_doc2you", lambda ctx: True)
    laudos = {
        "1": {"op": "1", "pendencias": [], "erro": None, "acao": "finalizaria (DRY)", "cedente": "A",
              "valor": 10.0, "tipos": ["DUR"], "detalhes": {"linhas_pagamento": [{"_linha": "1"}]},
              "pagamento_conferido": True, "observacoes": []},
        "2": {"op": "2", "pendencias": ["Aditivo: falta"], "erro": None, "acao": "avisar", "cedente": "B",
              "valor": None, "tipos": [], "detalhes": {}, "pagamento_conferido": False, "observacoes": []},
        "3": {"op": "3", "pendencias": [], "erro": "checagem de documentos falhou: x", "acao": None,
              "cedente": None, "tipos": [], "observacoes": []},
    }
    monkeypatch.setattr(job, "processar", lambda ctx, op, executar, mandar_email, execucao=None: laudos[op])
    monkeypatch.setattr(job, "_resumo", lambda laudos, executar: None)
    saida = job.ciclo(_Ctx(), executar=False, execucao=reg)
    assert len(saida) == 3
    assert [(op, t, kw["resultado"]) for op, t, kw in reg.eventos] == [
        ("1", "avaliada", "FINALIZARIA"), ("2", "avaliada", "BARRADA"), ("3", "avaliada", "ERRO")]
    assert reg.eventos[0][2]["linhas_pagamento"] == [{"_linha": "1"}]
    assert reg.eventos[1][2]["pendencias"] == ["Aditivo: falta"]


def test_ciclo_sem_execucao_continua_funcionando(job, monkeypatch):
    """Quem chama ciclo() sem execucao (o sandbox) nao muda de comportamento."""
    monkeypatch.setattr(job.listar_fila, "listar", lambda ctx: ["1"])
    monkeypatch.setattr(job.checagem_docs, "sso_doc2you", lambda ctx: True)
    monkeypatch.setattr(job, "processar", lambda ctx, op, executar, mandar_email, execucao=None: {"op": op, "pendencias": []})
    monkeypatch.setattr(job, "_resumo", lambda laudos, executar: None)
    assert job.ciclo(_Ctx()) == [{"op": "1", "pendencias": []}]
