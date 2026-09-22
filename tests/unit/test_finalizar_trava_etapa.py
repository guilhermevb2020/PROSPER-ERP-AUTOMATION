# -*- coding: utf-8 -*-
"""
test_finalizar_trava_etapa.py - o finalizador so abre a grade e clica em operacao que
o Smart mostra na etapa de entrada ("Aguardando Ass."). Etapa diferente, ou etapa que
nao deu para ler, fecha a porta: nada de grade, clique ou evento finalizar_clicado.

Por que existe: a fila vem da consulta do Smart, que le a tabela 1,5 s depois de
Pesquisar. Quando o Smart demora, ela le a tabela que ja estava na tela - as ~10
operacoes mais recentes, das duas securitizadoras e de qualquer etapa. Medido 3x em
22/09/2026 (11:00, 14:30 e 15:00), no dia em que o clique foi ligado.

A etapa vem do HTML da tela de edicao (a mesma que o job ja baixa por HTTP). Pelo DOM
nao serve: o form mora no frame 'stage', e o Resumir e a grade abrem nesse mesmo
frame - a primeira versao desta trava leu o DOM depois da grade e barrou a op 65879,
pronta, em 22/09 15:31.

Sem navegador: tela, doc2you, grade e banco sao dubles. Nenhum teste fala com o Smart.
"""
from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"

# recorte do HTML real da tela de edicao (op 65879, 22/09/2026), sem dados da operacao
_HTML_REAL = """
<div class="flex flex-col w-full"> <label for="etapaOperacao" class="inline-block font-bold">Etapa</label>
<select name="etapaOperacao" id="etapaOperacao" class="relative inline-block w-full nl_select select-caret" onchange="changeEtapa(this);">
  <option value="10">An&aacute;lise Home</option>
  <option value="2">Análise de crédito</option>
  <option value="16">Enviar Digitais</option>
  <option value="15" selected>Aguardando Ass.</option>
  <option value="18">Feedback Analise ROB</option>
</select>
<script> desabilitar("pFator", disabledFator); desabilitar("etapaOperacao", false); </script>
"""


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
    monkeypatch.setattr(mod.cfg, "PAGAMENTO_SO_APOS_ASSINATURAS", True)
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
    def __init__(self):
        self.paginas = 0

    def new_page(self):
        self.paginas += 1
        return _Pagina()


def _docs_ok(ctx, op, tipos, nome_cedente=None):
    return {"ok": True, "pendencias": [], "observacoes": [], "exigidos": ["contrato"],
            "encontrados": {"contrato": {"assinados": 1, "total": 1}}}


def _armar(job, monkeypatch, etapa):
    monkeypatch.setattr(job, "_dados_da_operacao", lambda ctx, op: (["DUR"], "CEDENTE X", 1000.0))
    monkeypatch.setattr(job.checagem_docs, "conferir", _docs_ok)
    monkeypatch.setattr(job.checagem_docs, "_ROTULO", {"contrato": "Contrato"})
    grades = []

    def _grade_ok(pg, op, log=print):
        grades.append(str(op))
        return {"ok": True, "pendencias": [], "linhas": [
            {"_linha": "1", "tipo": "PIX", "cta_origem": "mp prospere", "favorecido": "F",
             "vencto": "22/09/2026", "sp": "X", "valor": "10,00"}]}

    monkeypatch.setattr(job.checagem_pagamento, "conferir", _grade_ok)
    monkeypatch.setattr(job, "_etapa_da_operacao", lambda ctx, op: etapa)
    cliques, eventos = [], []
    monkeypatch.setattr(job.fin, "finalizar_da_grade",
                        lambda pg, op, aceitar_dialogos=None, log=print: (cliques.append(str(op)) or
                        {"ok": True, "situacao": "finalizada", "detalhe": "Smart confirma", "dialogos": []}))
    monkeypatch.setattr(job.execucao_job, "registrar_evento_operacao",
                        lambda ex, op, tipo, **kw: eventos.append(tipo))
    monkeypatch.setattr(job, "_registrar_finalizada", lambda op, cedente: None)
    monkeypatch.setattr(job, "_avisar_finalizacao",
                        lambda op, cedente, valor, detalhes, confirmacao, execucao=None: None)
    return cliques, eventos, grades


# --------------------------------------------------------------------------- #
# processar(): a porta
# --------------------------------------------------------------------------- #
def test_fora_da_etapa_nao_abre_grade_nem_clica_nem_registra_intencao(job, monkeypatch):
    cliques, eventos, grades = _armar(job, monkeypatch, "Análise de crédito")
    ctx = _Ctx()
    laudo = job.processar(ctx, "65871", executar=True, execucao=object())
    assert grades == [] and ctx.paginas == 0, "fora da etapa nem a grade e aberta"
    assert cliques == [] and eventos == [], "fora da etapa nao pode haver finalizar_clicado"
    assert laudo["etapa"] == "Análise de crédito"
    assert laudo["acao"] == "fora da etapa (nao finaliza)"
    assert laudo["pagamento_conferido"] is False
    assert job._veredito(laudo) == "BARRADA"
    assert any("Análise de crédito" in p and "Aguardando Ass." in p for p in laudo["pendencias"])


def test_etapa_ilegivel_fecha_a_porta(job, monkeypatch):
    cliques, eventos, grades = _armar(job, monkeypatch, None)
    laudo = job.processar(_Ctx(), "65871", executar=True, execucao=object())
    assert grades == [] and cliques == [] and eventos == []
    assert laudo["etapa"] is None and job._veredito(laudo) == "BARRADA"
    assert any("nao consegui ler a etapa" in p for p in laudo["pendencias"])


@pytest.mark.parametrize("etapa", ["Aguardando Ass.", "AGUARDANDO ASS", "  aguardando   ass. "])
def test_na_etapa_de_entrada_o_clique_acontece(job, monkeypatch, etapa):
    cliques, eventos, grades = _armar(job, monkeypatch, etapa)
    laudo = job.processar(_Ctx(), "65871", executar=True, execucao=object())
    assert grades == ["65871"] and cliques == ["65871"]
    assert eventos == ["finalizar_clicado", "finalizada"]
    assert laudo["acao"] == "finalizada"


def test_em_dry_a_etapa_tambem_barra(job, monkeypatch):
    """No DRY o veredito precisa ser o mesmo do modo real: fora da etapa e BARRADA."""
    cliques, _, _ = _armar(job, monkeypatch, "Finalizada")
    laudo = job.processar(_Ctx(), "65871", executar=False, execucao=None)
    assert cliques == [] and job._veredito(laudo) == "BARRADA"


def test_etapa_vai_para_a_avaliacao_registrada(job, monkeypatch):
    registros = []
    monkeypatch.setattr(job.execucao_job, "registrar_evento_operacao",
                        lambda ex, op, tipo, **kw: registros.append((tipo, kw)))
    job._registrar_avaliacao(object(), {"op": "1", "pendencias": ["x"], "etapa": "Finalizada",
                                         "detalhes": {}})
    assert registros[0][0] == "avaliada" and registros[0][1]["detalhe"]["etapa"] == "Finalizada"


# --------------------------------------------------------------------------- #
# leitura: do HTML da tela de edicao
# --------------------------------------------------------------------------- #
def test_etapa_do_html_real(job):
    assert job._etapa_do_html(_HTML_REAL) == "Aguardando Ass."


@pytest.mark.parametrize("html, esperado", [
    (_HTML_REAL.replace("<option value=\"15\" selected>", "<option value=\"15\" selected=\"selected\">"),
     "Aguardando Ass."),
    (_HTML_REAL.replace(" selected>Aguardando", ">Aguardando")
               .replace("<option value=\"10\">", "<option value=\"10\" SELECTED>"), "Análise Home"),
    (_HTML_REAL.replace(" selected>", ">"), None),                                  # nada marcado
    (_HTML_REAL.replace("<option value=\"2\">", "<option value=\"2\" selected>"), None),  # duas marcadas
    ("<label for=\"etapaOperacao\">Etapa</label> desabilitar(\"etapaOperacao\", false);", None),
    ("<html><body>expira.php</body></html>", None),
    ("", None),
    (None, None),
])
def test_etapa_do_html_casos(job, html, esperado):
    assert job._etapa_do_html(html) == esperado


def _smart_falso(monkeypatch, resposta=None, levanta=False):
    pedidos = []

    class _S:
        def get(self, url, timeout=None):
            pedidos.append(url)
            if levanta:
                raise RuntimeError("socket hang up")
            return resposta

    monkeypatch.setitem(sys.modules, "smart_session",
                        types.SimpleNamespace(Smart=types.SimpleNamespace(attach=lambda ctx: _S())))
    monkeypatch.setitem(sys.modules, "classe_risco_tool",
                        types.SimpleNamespace(URL_EDIT="https://smart/edit?op={op}"))
    return pedidos


def test_etapa_da_operacao_le_a_tela_de_edicao(job, monkeypatch):
    pedidos = _smart_falso(monkeypatch, resposta=(200, _HTML_REAL))
    assert job._etapa_da_operacao(object(), "65879") == "Aguardando Ass."
    assert pedidos == ["https://smart/edit?op=65879"]


@pytest.mark.parametrize("resposta, levanta", [((500, _HTML_REAL), False), (None, True),
                                               ((200, "<html>expira.php</html>"), False)])
def test_etapa_da_operacao_sem_leitura_devolve_none(job, monkeypatch, resposta, levanta):
    _smart_falso(monkeypatch, resposta=resposta, levanta=levanta)
    assert job._etapa_da_operacao(object(), "65879") is None


def test_mesma_etapa(job):
    assert job._mesma_etapa("Aguardando Ass.", "Aguardando Ass.")
    assert job._mesma_etapa("AGUARDANDO ASS", "Aguardando Ass.")
    assert not job._mesma_etapa("Aguardando Assinatura Cedente", "Aguardando Ass.")
    assert not job._mesma_etapa("Enviar Digitais", "Aguardando Ass.")
    assert not job._mesma_etapa(None, "Aguardando Ass.")
    assert not job._mesma_etapa("", "Aguardando Ass.")
    assert not job._mesma_etapa("...", "Aguardando Ass.")
