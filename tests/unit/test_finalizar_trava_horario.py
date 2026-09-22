# -*- coding: utf-8 -*-
"""
test_finalizar_trava_horario.py - R7_HORA_LIMITE_FINALIZAR fecha o clique em Finalizar
depois da hora, em QUALQUER caminho, e o processar() nem registra a intencao de clique.

Por que existe: a remessa de pagamento sai a cada 5 min ate 18:55 e exige vencimento =
hoje. Operacao finalizada depois do limite so entra na remessa de amanha, com o
vencimento de ontem. Pendencia do README desde 21/09/2026; fechada em 22/09/2026 ao
tirar o job do DRY.

Sem navegador: grade, botao, Smart e doc2you sao dubles. Nenhum teste fala com o Smart.
"""
from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"


def _importar(monkeypatch, dry="0", limite="18:30"):
    """Importa `finalizar` (e deixa `finalizar_operacao` importavel) com o ambiente dado."""
    monkeypatch.setenv("R7_DRY_RUN", dry)
    if limite is None:
        monkeypatch.delenv("R7_HORA_LIMITE_FINALIZAR", raising=False)
    else:
        monkeypatch.setenv("R7_HORA_LIMITE_FINALIZAR", limite)
    monkeypatch.setenv("DEBUG_DIR_R7", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"))
    for p in (str(RAIZ), str(PACOTE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for nome in ("finalizar_operacao", "finalizar", "r7_config"):
        sys.modules.pop(nome, None)
    return importlib.import_module("finalizar")


def _relogio(fin, monkeypatch, hhmm):
    h, m = hhmm.split(":")
    monkeypatch.setattr(fin.cfg, "_agora", lambda: datetime(2026, 9, 22, int(h), int(m)))


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

    def close(self):
        pass


def _preparar(fin, monkeypatch, botao):
    grade = _Grade(botao)
    monkeypatch.setattr(fin, "_frame_com", lambda pg, sel, timeout_s=None: grade)
    monkeypatch.setattr(fin, "_confirmar_no_smart", lambda pg, op: (True, "duble: finalizada"))
    monkeypatch.setattr(fin.time, "sleep", lambda s: None)
    return grade


# --------------------------------------------------------------------------- #
# a funcao pura
# --------------------------------------------------------------------------- #
def test_janela_pura(monkeypatch):
    fin = _importar(monkeypatch)
    cfg = fin.cfg
    assert cfg.dentro_da_janela_de_finalizacao(datetime(2026, 9, 22, 8, 0))[0] is True
    assert cfg.dentro_da_janela_de_finalizacao(datetime(2026, 9, 22, 18, 30))[0] is True
    assert cfg.dentro_da_janela_de_finalizacao(datetime(2026, 9, 22, 18, 30, 59))[0] is False
    dentro, motivo = cfg.dentro_da_janela_de_finalizacao(datetime(2026, 9, 22, 18, 31))
    assert dentro is False and "18:31" in motivo and "18:30" in motivo


# --------------------------------------------------------------------------- #
# finalizar_da_grade(): o ponto do clique
# --------------------------------------------------------------------------- #
def test_depois_do_limite_o_botao_habilitado_NAO_e_clicado(monkeypatch):
    fin = _importar(monkeypatch)
    assert fin.cfg.DRY_RUN is False, "o teste precisa do DRY desligado para provar a trava de hora"
    _relogio(fin, monkeypatch, "18:31")
    botao = _Botao()
    grade = _preparar(fin, monkeypatch, botao)

    r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)

    assert r["situacao"] == "fora_da_janela" and r["ok"] is False
    assert botao.cliques == 0, "passou das 18:30 e o botao foi clicado"
    assert grade.saidas == 1, "a trava fica DEPOIS das checagens do botao, como o DRY"
    assert "65071" in r["detalhe"] and "18:31" in r["detalhe"]


def test_ate_o_limite_o_clique_acontece(monkeypatch):
    fin = _importar(monkeypatch)
    for hhmm in ("08:00", "14:45", "18:29", "18:30"):
        _relogio(fin, monkeypatch, hhmm)
        botao = _Botao()
        _preparar(fin, monkeypatch, botao)
        r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)
        assert botao.cliques == 1 and r["situacao"] == "finalizada", hhmm


def test_limite_vazio_desliga_a_trava(monkeypatch):
    fin = _importar(monkeypatch, limite="")
    _relogio(fin, monkeypatch, "23:59")
    botao = _Botao()
    _preparar(fin, monkeypatch, botao)
    r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)
    assert botao.cliques == 1 and r["situacao"] == "finalizada"


def test_limite_invalido_fecha_a_porta(monkeypatch):
    """Configuracao errada nunca abre a porta de uma acao irreversivel."""
    fin = _importar(monkeypatch, limite="18h30")
    _relogio(fin, monkeypatch, "09:00")
    botao = _Botao()
    _preparar(fin, monkeypatch, botao)
    r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)
    assert r["situacao"] == "fora_da_janela" and botao.cliques == 0
    assert "invalido" in r["detalhe"]


def test_dry_vem_antes_da_janela(monkeypatch):
    fin = _importar(monkeypatch, dry="1")
    _relogio(fin, monkeypatch, "18:31")
    botao = _Botao()
    _preparar(fin, monkeypatch, botao)
    r = fin.finalizar_da_grade(_Pagina(), "65071", log=lambda m: None)
    assert r["situacao"] == "dry" and botao.cliques == 0


def test_o_caminho_antigo_finalizar_tambem_respeita_a_janela(monkeypatch):
    fin = _importar(monkeypatch)
    _relogio(fin, monkeypatch, "18:31")
    botao = _Botao()
    monkeypatch.setattr(fin, "_abrir_resumir", lambda pg, op, log=print: _Grade(botao))
    r = fin.finalizar(_Pagina(), "65071", dry=False, log=lambda m: None)
    assert r["situacao"] == "fora_da_janela" and botao.cliques == 0


# --------------------------------------------------------------------------- #
# processar(): fora da janela nao ha nem a intencao de clique registrada
# --------------------------------------------------------------------------- #
class _Ctx:
    def new_page(self):
        return _Pagina()


def _docs_ok(ctx, op, tipos, nome_cedente=None):
    return {"ok": True, "pendencias": [], "observacoes": [], "exigidos": ["contrato"],
            "encontrados": {"contrato": {"assinados": 1, "total": 1}}}


def _grade_ok(pg, op, log=print):
    return {"ok": True, "pendencias": [], "linhas": [
        {"_linha": "1", "tipo": "PIX", "cta_origem": "mp prospere", "favorecido": "F",
         "vencto": "22/09/2026", "sp": "X", "valor": "10,00"}]}


def _armar_processar(monkeypatch, hhmm):
    fin = _importar(monkeypatch)
    job = importlib.import_module("finalizar_operacao")
    assert job.fin is fin and job.cfg is fin.cfg
    _relogio(fin, monkeypatch, hhmm)
    monkeypatch.setattr(job, "_dados_da_operacao", lambda ctx, op: (["DUR"], "CEDENTE X", 1000.0))
    monkeypatch.setattr(job.checagem_docs, "conferir", _docs_ok)
    monkeypatch.setattr(job.checagem_docs, "_ROTULO", {"contrato": "Contrato"})
    monkeypatch.setattr(job.checagem_pagamento, "conferir", _grade_ok)
    monkeypatch.setattr(job.cfg, "PAGAMENTO_SO_APOS_ASSINATURAS", True)
    monkeypatch.setattr(job, "_etapa_da_operacao", lambda ctx, op: "Aguardando Ass.")
    cliques, eventos = [], []
    monkeypatch.setattr(job.fin, "finalizar_da_grade",
                        lambda pg, op, aceitar_dialogos=None, log=print: (cliques.append(str(op)) or
                        {"ok": True, "situacao": "finalizada", "detalhe": "Smart confirma", "dialogos": []}))
    monkeypatch.setattr(job.execucao_job, "registrar_evento_operacao",
                        lambda ex, op, tipo, **kw: eventos.append(tipo))
    monkeypatch.setattr(job, "_avisar_finalizacao",
                        lambda op, cedente, valor, detalhes, confirmacao, execucao=None: None)
    return job, cliques, eventos


def test_processar_fora_da_janela_nao_clica_nem_registra_intencao(monkeypatch):
    job, cliques, eventos = _armar_processar(monkeypatch, "18:31")
    laudo = job.processar(_Ctx(), "65071", executar=True, execucao=object())
    assert cliques == [] and eventos == [], "fora da janela nao pode haver finalizar_clicado"
    assert laudo["acao"] == "finalizaria (fora da janela de horario)"
    assert laudo["erro"] is None and laudo["pendencias"] == []
    assert job._veredito(laudo) == "FINALIZARIA", "a op passou; so o clique ficou para amanha"


def test_processar_dentro_da_janela_clica_e_registra(monkeypatch):
    job, cliques, eventos = _armar_processar(monkeypatch, "14:45")
    laudo = job.processar(_Ctx(), "65071", executar=True, execucao=object())
    assert cliques == ["65071"] and eventos == ["finalizar_clicado", "finalizada"]
    assert laudo["acao"] == "finalizada"
