# -*- coding: utf-8 -*-
"""
test_finalizar_rotina_avisos.py - a rotina de avisos do job finalizar_operacao: PIX confirmado pelo banco,
PIX recusado ou que nao saiu, op pronta depois do corte, assinaturas paradas e resumo do
dia. Cada aviso sai UMA vez, para o publico certo (gestao x operacional), no horario certo.

Por que existe: em 22/09/2026 o job avisava "finalizada" e ninguem confirmava o PIX; os
dois primeiros so sairam porque alguem gerou a remessa a mao durante a manutencao do hub.

Sem rede: o Nextcloud e o WhatsApp sao dubles; os retornos CNAB-240 sao montados aqui.
"""
from __future__ import annotations

import importlib
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"
HOJE = date(2026, 9, 22)
GESTAO, OPERACIONAL = ["5511000000001"], ["5511000000002"]


# --------------------------------------------------------------------------- #
# retorno CNAB-240 de mentira, nas posicoes do layout medido
# --------------------------------------------------------------------------- #
def _linha(campos):
    l = [" "] * 240
    for inicio, texto in campos:
        for i, c in enumerate(texto):
            l[inicio + i] = c
    return "".join(l)


def _seg_a(favorecido, seu_numero, valor, ocorrencia="00", data="22092026"):
    return _linha([(0, "27400013"), (13, "A"), (43, favorecido.ljust(30)[:30]),
                   (73, seu_numero.ljust(20)), (93, data), (119, f"{round(valor * 100):015d}"),
                   (230, ocorrencia.ljust(10))])


def _seg_b(documento, tipo="2"):
    return _linha([(0, "27400013"), (13, "B"), (17, tipo), (18, documento.rjust(14, "0"))])


def _retorno(*pagamentos):
    linhas = [_linha([(0, "27400000"), (7, "0")])]
    for fav, seu, valor, oc, doc in pagamentos:
        linhas += [_seg_a(fav, seu, valor, oc), _seg_b(doc)]
    linhas.append(_linha([(0, "27499999"), (7, "9")]))
    return "\r\n".join(linhas).encode("latin-1")


class _Nuvem:
    def __init__(self, arquivos):
        self.arquivos = arquivos         # {(sub, nome): bytes}
        self.baixados = []

    def listar_nomes(self, sub):
        return {n for s, n in self.arquivos if s == sub}

    def baixar(self, sub, nome):
        self.baixados.append(nome)
        return self.arquivos.get((sub, nome))


@pytest.fixture
def r(monkeypatch, tmp_path):
    monkeypatch.setenv("DEBUG_DIR_R7", str(tmp_path))
    if str(PACOTE) not in sys.path:
        sys.path.insert(0, str(PACOTE))
    for m in ("rotina_avisos", "pix_retorno", "r7_config", "notificar_whatsapp"):
        sys.modules.pop(m, None)
    mod = importlib.import_module("rotina_avisos")
    for nome, valor in {"ARQ_ROTINA": str(tmp_path / "rotina.json"),
                        "ARQ_FINALIZADAS_PIX": str(tmp_path / "finalizadas_pix.jsonl"),
                        "WHATSAPP_DESTINO": GESTAO, "WHATSAPP_DESTINO_OPERACIONAL": OPERACIONAL,
                        "RESUMO_ASSINATURAS_HORAS": ["11:00", "15:00"],
                        "RESUMO_ASSINATURAS_JANELA_MIN": 120, "RESUMO_DIA_HORA": "18:40",
                        "PIX_ATRASO_MIN": 30, "HORA_LIMITE_FINALIZAR": "18:30"}.items():
        monkeypatch.setattr(mod.cfg, nome, valor)
    mod._enviadas = []

    def _wpp(texto, destinos=None, provider=None):
        mod._enviadas.append((texto, list(destinos)))
        return len(destinos), [(d, True, "enviado") for d in destinos]

    monkeypatch.setattr(mod.notificar_whatsapp, "enviar", _wpp)
    return mod


def _finalizar(r, op, cedente, doc, valor, quando):
    r.registrar_finalizada(op, cedente, None,
                           [{"cpf_cnpj": doc, "valor": f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                             "favorecido": cedente}], quando=quando)


def _para(r, destino):
    return [t for t, d in r._enviadas if d == destino]


# --------------------------------------------------------------------------- #
# leitura do retorno
# --------------------------------------------------------------------------- #
def test_le_pagamentos_do_retorno(r):
    pags = r.pix_retorno.ler_pagamentos(_retorno(
        ("SPEED PACK INDUSTRIA", "951838", 12659.99, "00", "12345678000190")))
    assert pags == [{"seu_numero": "951838", "favorecido": "SPEED PACK INDUSTRIA",
                     "data": "2026-09-22", "valor": 12659.99, "ocorrencias": "00",
                     "documento": "12345678000190"}]
    assert r.pix_retorno.efetivado(pags[0])


def test_documento_normalizado_e_cpf(r):
    pr = r.pix_retorno
    assert pr.documento_normalizado("12.345.678/0001-90") == "12345678000190"
    assert pr.documento_normalizado("123.456.789-01") == "12345678901"
    assert pr.documento_normalizado("") == ""
    pags = pr.ler_pagamentos(("\r\n".join([_seg_a("PESSOA", "1", 10.0), _seg_b("12345678901", tipo="1")])))
    assert pags[0]["documento"] == "12345678901"


def test_so_le_retornos_de_hoje_e_nao_baixa_de_novo(r):
    nuvem = _Nuvem({("", "CP2209000510.RET"): _retorno(("A", "1", 1.0, "00", "1")),
                    ("_PROCESSADOS", "CP2209000505.RET"): _retorno(("B", "2", 2.0, "00", "2")),
                    ("_PROCESSADOS", "CP2109000400.RET"): _retorno(("C", "3", 3.0, "00", "3")),
                    ("", "_PROCESSADOS"): b""})
    lidos = r.pix_retorno.retornos_do_dia(nuvem, HOJE)
    assert sorted(lidos) == ["CP2209000505.RET", "CP2209000510.RET"]
    r.pix_retorno.retornos_do_dia(nuvem, HOJE, lidos)
    assert sorted(nuvem.baixados) == ["CP2209000505.RET", "CP2209000510.RET"], "lido nao se baixa de novo"


# --------------------------------------------------------------------------- #
# casamento op x retorno
# --------------------------------------------------------------------------- #
def test_um_pagamento_do_banco_casa_com_uma_linha_so(r):
    pags = [(("x", 0), {"documento": "111", "valor": 100.0, "ocorrencias": "00"})]
    f1 = {"op": "1", "linhas": [{"documento": "111", "valor": 100.0}]}
    f2 = {"op": "2", "linhas": [{"documento": "111", "valor": 100.0}]}
    usados = set()
    assert r.situacao_pix(f1, pags, usados)[0] == "liquidado"
    assert r.situacao_pix(f2, pags, usados)[0] == "sem_retorno", \
        "duas ops iguais do mesmo cedente nao podem ser confirmadas com um PIX so"


def test_valor_diferente_nao_casa(r):
    pags = [(("x", 0), {"documento": "111", "valor": 100.01, "ocorrencias": "00"})]
    f = {"op": "1", "linhas": [{"documento": "111", "valor": 100.0}]}
    assert r.situacao_pix(f, pags, set())[0] == "sem_retorno"


# --------------------------------------------------------------------------- #
# os avisos de PIX
# --------------------------------------------------------------------------- #
def test_pix_confirmado_vai_para_a_gestao_uma_vez(r):
    _finalizar(r, "65879", "SPEED PACK", "12.345.678/0001-90", 12659.99, datetime(2026, 9, 22, 15, 46))
    nuvem = _Nuvem({("_PROCESSADOS", "CP2209000505.RET"):
                    _retorno(("SPEED PACK", "951838", 12659.99, "00", "12345678000190"))})
    r.depois_do_ciclo([], nuvem, agora=datetime(2026, 9, 22, 16, 0))
    r.depois_do_ciclo([], nuvem, agora=datetime(2026, 9, 22, 16, 15))
    confirmados = _para(r, GESTAO)
    assert len(confirmados) == 1 and "PIX confirmado" in confirmados[0]
    assert "65879" in confirmados[0] and "R$ 12.659,99" in confirmados[0]
    assert _para(r, OPERACIONAL) == []


def test_pix_recusado_vai_para_o_operacional_com_o_motivo(r):
    _finalizar(r, "65880", "CEDENTE X", "11222333000144", 500.0, datetime(2026, 9, 22, 15, 0))
    nuvem = _Nuvem({("", "CP2209000506.RET"): _retorno(("CEDENTE X", "9", 500.0, "55", "11222333000144"))})
    r.depois_do_ciclo([], nuvem, agora=datetime(2026, 9, 22, 15, 20))
    avisos = _para(r, OPERACIONAL)
    assert len(avisos) == 1 and "recusado" in avisos[0] and "55 (chave PIX cadastrada errada)" in avisos[0]


def test_pix_sem_retorno_avisa_depois_do_atraso_e_na_ultima_chamada(r):
    _finalizar(r, "65881", "CEDENTE Y", "11222333000144", 700.0, datetime(2026, 9, 22, 17, 0))
    nuvem = _Nuvem({})
    r.depois_do_ciclo([], nuvem, agora=datetime(2026, 9, 22, 17, 15))
    assert _para(r, OPERACIONAL) == [], "antes do atraso nao se avisa"
    r.depois_do_ciclo([], nuvem, agora=datetime(2026, 9, 22, 17, 45))
    r.depois_do_ciclo([], nuvem, agora=datetime(2026, 9, 22, 18, 0))
    avisos = _para(r, OPERACIONAL)
    assert len(avisos) == 1 and "ainda não saiu" in avisos[0] and "17:00" in avisos[0]
    r.depois_do_ciclo([], nuvem, agora=datetime(2026, 9, 22, 18, 45))
    avisos = _para(r, OPERACIONAL)
    assert len(avisos) == 2 and "Última chamada" in avisos[1]


# --------------------------------------------------------------------------- #
# pronta depois do corte
# --------------------------------------------------------------------------- #
def test_corte_avisa_uma_vez_por_op_por_dia(r):
    registros = []
    reg = lambda *a: registros.append(a)  # noqa: E731
    assert r.avisar_corte("65873", "F4 MATERIAIS", 18420.0, registrar=reg,
                          agora=datetime(2026, 9, 22, 18, 35))
    assert not r.avisar_corte("65873", "F4 MATERIAIS", 18420.0, registrar=reg,
                              agora=datetime(2026, 9, 22, 18, 45))
    avisos = _para(r, OPERACIONAL)
    assert len(avisos) == 1 and "depois das 18:30" in avisos[0] and "18:50" in avisos[0]
    assert registros[0][:3] == ("65873", "pronta_depois_do_corte", True)


# --------------------------------------------------------------------------- #
# assinaturas paradas
# --------------------------------------------------------------------------- #
_ESPERANDO = [
    {"op": "65851", "cedente": "AMENDO LOVERS", "acao": "aguardando assinatura", "pendencias": [
        "Aditivo: falta assinatura de terceiro(s) -> AMENDO LOVERS [Contratante] Pendente; "
        "FULANO DE TAL [Avalista] Pendente",
        "Nota promissoria: 1 de 1 SEM assinatura -> Pendente (Nota promissória)",
        "Duplicata: 12 de 12 SEM assinatura -> Pendente (Duplicata 1)"]},
    {"op": "65900", "cedente": "CASTELLA", "acao": "aguardando assinatura", "pendencias": [
        "Nota promissoria: 1 de 1 SEM assinatura -> Pendente (Nota promissória)"]},
    {"op": "65879", "cedente": "SPEED PACK", "acao": "finalizada", "pendencias": []},
]


def test_resumo_de_assinaturas_no_horario_e_uma_vez(r):
    r.depois_do_ciclo(_ESPERANDO, None, agora=datetime(2026, 9, 22, 10, 45))
    assert _para(r, OPERACIONAL) == [], "antes das 11:00 nao"
    r.depois_do_ciclo(_ESPERANDO, None, agora=datetime(2026, 9, 22, 11, 0))
    r.depois_do_ciclo(_ESPERANDO, None, agora=datetime(2026, 9, 22, 11, 15))
    avisos = _para(r, OPERACIONAL)
    assert len(avisos) == 1
    texto = avisos[0]
    assert "2 operações esperando assinatura" in texto
    assert "AMENDO LOVERS [Contratante], FULANO DE TAL [Avalista]" in texto
    assert "documentos: Aditivo, Nota promissoria, Duplicata" in texto
    assert texto.index("65851") < texto.index("65900"), "quem espera ha mais tempo vem primeiro"
    assert "65879" not in texto


def test_resumo_atrasado_nao_sai_e_fila_vazia_nao_manda(r):
    r.depois_do_ciclo(_ESPERANDO, None, agora=datetime(2026, 9, 22, 13, 30))
    assert _para(r, OPERACIONAL) == [], "fora da janela do horario, resumo velho nao sai"
    r.depois_do_ciclo([_ESPERANDO[2]], None, agora=datetime(2026, 9, 22, 15, 0))
    r.depois_do_ciclo(_ESPERANDO, None, agora=datetime(2026, 9, 22, 15, 15))
    assert _para(r, OPERACIONAL) == [], "sem ninguem esperando, o horario fica dado e nao repete"


# --------------------------------------------------------------------------- #
# resumo do dia
# --------------------------------------------------------------------------- #
def test_resumo_do_dia_uma_vez_com_os_numeros(r):
    _finalizar(r, "65879", "SPEED PACK", "12345678000190", 12659.99, datetime(2026, 9, 22, 15, 46))
    nuvem = _Nuvem({("_PROCESSADOS", "CP2209000505.RET"):
                    _retorno(("SPEED PACK", "951838", 12659.99, "00", "12345678000190"))})
    # 65860 foi vista na fila de manha e saiu sem o job: o Smart diz Concluida
    r.depois_do_ciclo([{"op": "65860", "acao": "aguardando assinatura", "pendencias": ["x"]}],
                      None, agora=datetime(2026, 9, 22, 9, 0))
    fila = [dict(_ESPERANDO[0]), {"op": "65873", "cedente": "F4", "acao": "avisar",
                                  "pendencias": ["Pagamento: SP nao marcado"]}]
    etapas = {"65860": "Concluída"}
    r.depois_do_ciclo(fila, nuvem, etapa_de=lambda op: etapas.get(op),
                      agora=datetime(2026, 9, 22, 18, 45))
    r.depois_do_ciclo(fila, nuvem, etapa_de=lambda op: etapas.get(op),
                      agora=datetime(2026, 9, 22, 18, 50))
    resumos = [t for t in _para(r, GESTAO) if "resumo de 22/09" in t]
    assert len(resumos) == 1
    texto = resumos[0]
    assert "Finalizadas pela automação: 1 · R$ 12.659,99" in texto and "PIX confirmado" in texto
    assert "Finalizadas por operador: 1" in texto
    assert "esperando assinatura: 1" in texto and "pagamento travado: 1 (65873)" in texto


def test_valor_br_e_estado_podado(r):
    assert r.valor_br("12.659,99") == 12659.99 and r.valor_br("R$ 1.000,00") == 1000.0
    assert r.valor_br("") is None and r.valor_br(None) is None and r.valor_br(5) == 5.0
    est = r.carregar_estado()
    est["avisados"] = {"2026-09-21|corte|1": "x", "2026-09-22|corte|2": "y"}
    est["retornos"] = {"CP2109000001.RET": [], "CP2209000001.RET": []}
    r.podar(est, HOJE)
    assert list(est["avisados"]) == ["2026-09-22|corte|2"] and list(est["retornos"]) == ["CP2209000001.RET"]


# --------------------------------------------------------------------------- #
# ligacao no finalizador
# --------------------------------------------------------------------------- #
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


@pytest.fixture
def job(monkeypatch, tmp_path):
    monkeypatch.setenv("R7_DRY_RUN", "0")
    monkeypatch.setenv("DEBUG_DIR_R7", str(tmp_path))
    for p in (str(RAIZ), str(PACOTE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for m in ("finalizar_operacao", "rotina_avisos", "pix_retorno", "notificar", "finalizar", "r7_config"):
        sys.modules.pop(m, None)
    mod = importlib.import_module("finalizar_operacao")
    monkeypatch.setattr(mod.cfg, "PAGAMENTO_SO_APOS_ASSINATURAS", True)
    monkeypatch.setattr(mod, "_dados_da_operacao", lambda ctx, op: (["DMR"], "SPEED PACK", None))
    monkeypatch.setattr(mod, "_etapa_da_operacao", lambda ctx, op: "Aguardando Ass.")
    monkeypatch.setattr(mod.checagem_docs, "_ROTULO", {"aditivo": "Aditivo"})
    monkeypatch.setattr(mod.checagem_docs, "conferir", lambda ctx, op, tipos, nome_cedente=None: {
        "ok": True, "pendencias": [], "observacoes": [], "exigidos": ["aditivo"],
        "encontrados": {"aditivo": {"assinados": 1, "total": 1}}})
    monkeypatch.setattr(mod.checagem_pagamento, "conferir", lambda pg, op, log=print: {
        "ok": True, "pendencias": [], "linhas": [
            {"_linha": "1", "tipo": "PIX", "cta_origem": "mp prospere", "favorecido": "SPEED PACK",
             "cpf_cnpj": "12.345.678/0001-90", "vencto": "2026-09-22", "sp": "SIM",
             "valor": "12.659,99"}]})
    monkeypatch.setattr(mod.execucao_job, "registrar_evento_operacao", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_avisar_finalizacao", lambda *a, **k: None)
    return mod


def test_op_finalizada_entra_na_lista_do_pix(job, monkeypatch):
    monkeypatch.setattr(job.cfg, "_agora", lambda: datetime(2026, 9, 22, 15, 46))
    monkeypatch.setattr(job.fin, "finalizar_da_grade", lambda *a, **k: {
        "ok": True, "situacao": "finalizada", "detalhe": "Smart confirma", "dialogos": []})
    registros = []
    monkeypatch.setattr(job.rotina_avisos, "registrar_finalizada",
                        lambda op, cedente, valor, linhas: registros.append((op, cedente, linhas)))
    job.processar(_Ctx(), "65879", executar=True, mandar_email=True, execucao=object())
    assert registros and registros[0][0] == "65879"
    assert registros[0][2][0]["cpf_cnpj"] == "12.345.678/0001-90"


@pytest.mark.parametrize("mandar, esperado", [(True, 1), (False, 0)])
def test_pronta_depois_do_corte_avisa_so_com_avisar(job, monkeypatch, mandar, esperado):
    monkeypatch.setattr(job.cfg, "_agora", lambda: datetime(2026, 9, 22, 18, 35))
    monkeypatch.setattr(job.fin, "finalizar_da_grade", lambda *a, **k: pytest.fail("depois do corte nao clica"))
    cortes = []
    monkeypatch.setattr(job.rotina_avisos, "avisar_corte",
                        lambda op, cedente, valor, registrar=None: cortes.append((op, valor)))
    laudo = job.processar(_Ctx(), "65873", executar=True, mandar_email=mandar, execucao=object())
    assert laudo["acao"] == "finalizaria (fora da janela de horario)"
    assert len(cortes) == esperado
    if cortes:
        assert cortes[0] == ("65873", 12659.99), "sem valor no espelho, usa a soma da grade"


def test_rotina_da_rodada_nunca_derruba(job, monkeypatch):
    import src.common.clients.nextcloud_webdav as nc
    monkeypatch.setattr(nc, "NextcloudWebDAV", lambda **k: object())
    chamadas = []

    def _explode(*a, **k):
        chamadas.append(k)
        raise RuntimeError("Nextcloud fora")

    monkeypatch.setattr(job.rotina_avisos, "depois_do_ciclo", _explode)
    job._rotina_de_avisos(_Ctx(), [], execucao=None)       # nao levanta
    assert chamadas and chamadas[0]["registrar"] is None and chamadas[0]["anotar"] is None
    assert callable(chamadas[0]["etapa_de"])
