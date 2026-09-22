# -*- coding: utf-8 -*-
"""
test_busca_consulta_etapa.py - a busca de operacoes por etapa (credito e finalizador) so
le a tabela depois que o frame de resultado RECARREGA, e so devolve a linha cuja coluna
Etapa e a pesquisada.

Por que existe: o Pesquisar faz POST de conoperacao.php no frame 'pesq'. Antes da 1a
pesquisa esse frame ja mostra as 10 operacoes mais recentes, de qualquer etapa e das duas
securitizadoras. Com a espera fixa de 1,5 s, quando o Smart demorava, a leitura pegava
essa tabela: 9x no job de credito em 22/09/2026, e ele processou 65854 e 65877, que
estavam em 'Aguardando Ass.' - trocou a classe de risco dos titulos, salvou e as moveu
para 'Analise de credito'. O finalizador leu a mesma tabela 3x no mesmo dia.

Sem navegador: pagina, frames e seletores sao dubles. Nenhum teste fala com o Smart.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CREDITO = RAIZ / "src" / "processors" / "web" / "credito"

# a tabela que a tela mostra ANTES da 1a pesquisa (medida em 22/09/2026 16:18)
_PADRAO = [("65903", "Feedback Analise ROB"), ("65902", "Nova"), ("65893", "Aguardando Ass."),
           ("65887", "Aguardando Ass."), ("65886", "Aguardando Ass."), ("65884", "Concluída"),
           ("65879", "Concluída"), ("65877", "Aguardando Ass."), ("65876", "Concluída"),
           ("65875", "Concluída")]


def _tabela(pares):
    return [{"num": n, "etapa": e} for n, e in pares]


@pytest.fixture
def b(monkeypatch):
    if str(CREDITO) not in sys.path:
        sys.path.insert(0, str(CREDITO))
    mod = importlib.import_module("_analisar_credito_base")
    monkeypatch.setattr(mod.config, "WAIT_MAX_PESQUISA", 0.4)
    monkeypatch.setattr(mod.config, "DEBUG", False)
    return mod


class _Locator:
    def __init__(self, frame, sel):
        self.f, self.sel = frame, sel

    def click(self, timeout=None):
        self.f.clicou(self.sel)

    def check(self):
        pass

    def select_option(self, value=None):
        self.f.etapa_valor = value

    def input_value(self):
        return self.f.etapa_valor

    def evaluate(self, js):
        if self.f.rotulo_quebra:
            raise RuntimeError("select sumiu")
        return self.f.rotulos.get(self.f.etapa_valor, "")


class _FramePesq:
    """O frame 'pesq': a marca da janela e a tabela. A recarga chega depois de N leituras."""

    def __init__(self, b, pares, tem_etapa=True):
        self.b, self.name = b, "pesq"
        self.marca, self.tabela, self.tem_etapa = None, _tabela(pares), tem_etapa
        self.pendente, self.leituras, self.leu_tabela = None, 0, []

    def agendar(self, depois_de, pares, tem_etapa=True):
        self.pendente, self.leituras = (depois_de, _tabela(pares), tem_etapa), 0

    def evaluate(self, js, arg=None):
        if "window.__buscaAntiga = m" in js:
            self.marca = arg
            return None
        if "window.__buscaAntiga !== m" in js:
            self.leituras += 1
            if self.pendente and self.leituras >= self.pendente[0]:
                _, self.tabela, self.tem_etapa = self.pendente
                self.pendente, self.marca = None, None      # documento novo: a marca sumiu
            return self.marca != arg
        if js == self.b._JS_LINHAS_CONSULTA:
            self.leu_tabela.append([l["num"] for l in self.tabela])
            return {"linhas": [dict(l) for l in self.tabela], "tem_etapa": self.tem_etapa}
        raise AssertionError(f"JS inesperado: {js[:50]}")


class _FrameForm:
    """O frame do filtro: radios, select de etapa e o Pesquisar."""

    def __init__(self, pesq, respostas, rotulos=None):
        self.name, self.pesq, self.respostas = "form", pesq, list(respostas)
        self.etapa_valor, self.rotulo_quebra = None, False
        self.rotulos = rotulos or {"15": "Aguardando Ass.", "10": "Análise Home"}

    def locator(self, sel):
        return _Locator(self, sel)

    def clicou(self, sel):
        if sel == "#Pesquisar" and self.respostas:
            self.pesq.agendar(*self.respostas.pop(0))

    def evaluate(self, js, arg=None):
        raise RuntimeError("o frame do filtro nao tem a tabela")


class _Pagina:
    def __init__(self, form, pesq, com_pesq=True):
        self.form, self.pesq, self.com_pesq = form, pesq, com_pesq
        self.frames = [form, pesq]

    def frame(self, name=None):
        return self.pesq if (self.com_pesq and name == "pesq") else None


def _armar(b, monkeypatch, padrao, respostas, com_pesq=True, rotulos=None):
    pesq = _FramePesq(b, padrao)
    form = _FrameForm(pesq, respostas, rotulos)
    pagina = _Pagina(form, pesq, com_pesq)
    monkeypatch.setattr(b, "_pagina_busca", lambda ctx: pagina)

    def _frame_com(page, seletor, timeout=30.0):
        if seletor == b.config.SEL_TROCAR_LAYOUT:
            raise b.PWTimeout("layout ja esta certo")
        return form

    monkeypatch.setattr(b, "frame_com", _frame_com)
    invalidacoes = []
    monkeypatch.setattr(b, "_invalidar_busca", lambda: invalidacoes.append(1))
    monkeypatch.setattr(b, "esperar", lambda s, m="": None)
    return pesq, form, invalidacoes


# --------------------------------------------------------------------------- #
# a busca inteira
# --------------------------------------------------------------------------- #
def test_le_so_depois_da_recarga_e_nunca_a_tabela_padrao(b, monkeypatch):
    novo = [("65898", "Aguardando Ass."), ("65897", "Aguardando Ass."), ("65851", "Aguardando Ass.")]
    pesq, _, _ = _armar(b, monkeypatch, _PADRAO, [(3, novo)])
    nums = b._buscar_numeros_uma(None, "15", "Aguardando Ass./Home", b.config.SEL_RADIO_TIPO_HOME)
    assert nums == ["65898", "65897", "65851"]
    assert pesq.leu_tabela == [["65898", "65897", "65851"]], "a tabela padrao nunca pode ser lida"


def test_sem_recarga_nao_devolve_nada_e_invalida_a_aba(b, monkeypatch):
    """A pesquisa nao recarrega nem na 2a tentativa: nada volta, nada da tabela antiga."""
    pesq, _, invalidacoes = _armar(b, monkeypatch, _PADRAO, [])
    nums = b._buscar_numeros_uma(None, "15", "Aguardando Ass./Home", b.config.SEL_RADIO_TIPO_HOME)
    assert nums == [] and pesq.leu_tabela == []
    assert len(invalidacoes) == 2, "a busca tenta de novo UMA vez, recriando a aba"


def test_o_incidente_do_credito_nao_se_repete(b, monkeypatch):
    """22/09: a Analise Home leu a tabela padrao e o job pegou a 65877 (Aguardando Ass.).
    Mesmo que a tabela nova traga linha de outra etapa, so volta a da etapa pesquisada."""
    novo = [("65877", "Aguardando Ass."), ("65910", "Análise Home")]
    _armar(b, monkeypatch, _PADRAO, [(2, novo), (2, [])])
    assert b.buscar_proxima_operacao(None, "10", "Análise Home") == "65910"


def test_nenhuma_operacao_na_etapa(b, monkeypatch):
    _armar(b, monkeypatch, _PADRAO, [(2, []), (2, [])])
    assert b.buscar_proxima_operacao(None, "10", "Análise Home") is None


def test_sem_coluna_etapa_nada_e_devolvido(b, monkeypatch):
    """Sem a coluna Etapa nao da para conferir: quem consome muda etapa e grava, entao
    na duvida nada volta."""
    _armar(b, monkeypatch, _PADRAO, [(1, [("65910", None)], False)])
    assert b._buscar_numeros_uma(None, "10", "Análise Home/Home", b.config.SEL_RADIO_TIPO_HOME) == []


def test_rotulo_do_chamador_cobre_opcao_ilegivel(b, monkeypatch):
    _, form, _ = _armar(b, monkeypatch, _PADRAO, [(1, [("65851", "Aguardando Ass.")])])
    form.rotulo_quebra = True
    assert b._buscar_numeros_uma(None, "15", "Aguardando Ass./Smart",
                                 b.config.SEL_RADIO_TIPO_SMART) == ["65851"]


def test_sem_frame_de_resultado_cai_na_espera_fixa_mas_confere_a_etapa(b, monkeypatch):
    """Frame 'pesq' nao achado: nao da para esperar a recarga, mas a etapa segura."""
    pesq, _, _ = _armar(b, monkeypatch, _PADRAO, [], com_pesq=False)
    nums = b._buscar_numeros_uma(None, "15", "Aguardando Ass./Home", b.config.SEL_RADIO_TIPO_HOME)
    assert nums == ["65893", "65887", "65886", "65877"], "so as linhas em Aguardando Ass."


# --------------------------------------------------------------------------- #
# as funcoes puras
# --------------------------------------------------------------------------- #
def test_numeros_conferidos_na_tabela_padrao(b):
    nums, descartadas, motivo = b.numeros_conferidos(
        {"linhas": _tabela(_PADRAO), "tem_etapa": True}, ["Aguardando Ass.", ""])
    assert nums == ["65893", "65887", "65886", "65877"] and motivo is None
    assert {d["etapa"] for d in descartadas} == {"Feedback Analise ROB", "Nova", "Concluída"}


@pytest.mark.parametrize("etapa, alvo, casa", [
    ("Análise Home", "ANALISE HOME", True),
    ("Aguardando Ass.", "Aguardando Ass", True),
    ("  aguardando   ass. ", "Aguardando Ass.", True),
    ("Aguardando Assinatura", "Aguardando Ass.", False),
    ("Feedback Analise ROB", "Análise Home", False),
    (None, "Análise Home", False),
])
def test_normalizacao_da_etapa(b, etapa, alvo, casa):
    aceitas, _ = b.filtrar_por_etapa([{"num": "1", "etapa": etapa}], [alvo])
    assert bool(aceitas) is casa


def test_sem_alvo_nada_e_devolvido(b):
    nums, descartadas, motivo = b.numeros_conferidos(
        {"linhas": _tabela(_PADRAO), "tem_etapa": True}, ["", None])
    assert nums == [] and len(descartadas) == 10 and "rotulo" in motivo


def test_numero_repetido_sai_uma_vez(b):
    nums, _, _ = b.numeros_conferidos(
        {"linhas": _tabela([("1", "Nova"), ("1", "Nova"), ("2", "Nova")]), "tem_etapa": True}, ["Nova"])
    assert nums == ["1", "2"]


def test_esperar_recarga_tolera_contexto_destruido(b):
    class _F:
        def __init__(self):
            self.n = 0

        def evaluate(self, js, arg=None):
            self.n += 1
            if self.n < 3:
                raise RuntimeError("Execution context was destroyed")
            return True

    assert b._esperar_recarga(_F(), "m", limite_s=2, intervalo=0.01) is True
