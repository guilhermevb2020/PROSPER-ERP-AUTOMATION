# -*- coding: utf-8 -*-
"""
test_finalizar_notificar.py - os avisos do finalizador: SMTP pelo broker do Guardian,
aviso SO quando os documentos estao ok e o pagamento trava, espacamento entre avisos.

Por que existe: ate 22/09/2026 o notificar lia a senha SMTP de um email_config.json da
maquina Windows de origem, que nao existe no servidor - nenhum e-mail tinha saido daqui.
E o desenho avisava tambem "falta assinatura", que e o estado normal da etapa: o
operacional seria cobrado a cada ciclo por algo que nao depende dele. O aviso de
pagamento sai por WhatsApp e/ou e-mail, cada canal com a sua chave.

Sem rede: SMTP e WhatsApp sao dubles. Nenhum teste manda mensagem.
"""
from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "src" / "processors" / "web" / "finalizar_operacao"


def _importar(monkeypatch, nome):
    monkeypatch.setenv("DEBUG_DIR_R7", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"))
    for p in (str(RAIZ), str(PACOTE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for m in ("finalizar_operacao", "notificar", "finalizar", "r7_config"):
        sys.modules.pop(m, None)
    return importlib.import_module(nome)


@pytest.fixture
def n(monkeypatch, tmp_path):
    for k, v in {"SMTP_SERVER": "guardian", "SMTP_PORT": "2525", "SMTP_USER": "robo",
                 "SMTP_PASSWORD": "", "EMAIL_FROM": "remetente@exemplo.test"}.items():
        monkeypatch.setenv(k, v)
    for k in ("R7_SMTP_SERVER", "R7_SMTP_PORT", "R7_SMTP_USER", "R7_SMTP_SENHA",
              "R7_SMTP_REMETENTE", "R7_SMTP_STARTTLS"):
        monkeypatch.delenv(k, raising=False)
    mod = _importar(monkeypatch, "notificar")
    monkeypatch.setattr(mod.cfg, "ARQ_AVISOS", str(tmp_path / "avisos.csv"))
    monkeypatch.setattr(mod.cfg, "EMAIL_ATIVO", True)
    monkeypatch.setattr(mod.cfg, "WHATSAPP_ATIVO", True)
    monkeypatch.setattr(mod.cfg, "AVISO_PENDENCIA_CANAIS", ["email"])
    monkeypatch.setattr(mod.cfg, "EMAIL_DESTINO", ["operacional@exemplo.test"])
    monkeypatch.setattr(mod.cfg, "WHATSAPP_DESTINO_PENDENCIA", ["5500000000000"])
    mod._wpp_enviados = []
    mod._wpp_falhar = False

    def _wpp(texto, destinos=None, provider=None):
        if mod._wpp_falhar:
            return 0, [(d, False, "evolution fora") for d in destinos]
        mod._wpp_enviados.append((texto, list(destinos)))
        return len(destinos), [(d, True, "enviado") for d in destinos]

    monkeypatch.setattr(mod.notificar_whatsapp, "enviar", _wpp)
    return mod


class _SMTPFalso:
    instancias = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.tls = self.logou = False
        self.enviados = []
        self.falhar = _SMTPFalso.falhar
        _SMTPFalso.instancias.append(self)

    def starttls(self):
        self.tls = True

    def login(self, user, senha):
        self.logou = True

    def sendmail(self, de, para, msg):
        if self.falhar:
            raise OSError("broker fora")
        self.enviados.append((de, list(para), msg))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def smtp(n, monkeypatch):
    _SMTPFalso.instancias, _SMTPFalso.falhar = [], False
    monkeypatch.setattr(n.smtplib, "SMTP", _SMTPFalso)
    return _SMTPFalso


# --------------------------------------------------------------------------- #
# transporte
# --------------------------------------------------------------------------- #
def test_smtp_vem_do_ambiente_do_guardian(n):
    c = n._smtp_config()
    assert (c["server"], c["port"], c["remetente"], c["senha"]) == (
        "guardian", 2525, "remetente@exemplo.test", "")
    assert not hasattr(n.cfg, "EMAIL_CONFIG_JSON"), "a config do Windows nao pode voltar"


def test_envio_pelo_broker_sem_auth_e_sem_tls(n, smtp):
    ok, motivo = n._enviar_email("assunto", "corpo", ["a@exemplo.test"])
    s = smtp.instancias[0]
    assert ok and motivo == "ok"
    assert (s.host, s.port, s.tls, s.logou) == ("guardian", 2525, False, False)
    assert s.enviados[0][0] == "remetente@exemplo.test" and s.enviados[0][1] == ["a@exemplo.test"]


def test_com_senha_e_starttls_configurados_usa_os_dois(n, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setenv("R7_SMTP_STARTTLS", "1")
    assert n._enviar_email("a", "b", ["a@exemplo.test"])[0]
    assert smtp.instancias[0].tls and smtp.instancias[0].logou


def test_falha_do_broker_vira_motivo_e_nao_levanta(n, smtp):
    smtp.falhar = True
    ok, motivo = n._enviar_email("a", "b", ["a@exemplo.test"])
    assert not ok and "falha SMTP" in motivo and "broker fora" in motivo


def test_sem_servidor_nao_tenta(n, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "")
    ok, motivo = n._enviar_email("a", "b", ["a@exemplo.test"])
    assert not ok and "SMTP_SERVER" in motivo and smtp.instancias == []


# --------------------------------------------------------------------------- #
# o aviso de pagamento
# --------------------------------------------------------------------------- #
_PEND = ["Pagamento: Vencto = 21/09/2026, deveria ser a data de hoje"]
_CTX = {"valor": "R$ 12.659,99", "linhas_pagamento": [
    {"_linha": "1", "tipo": "PIX", "cta_origem": "mp prospere", "vencto": "2026-09-21", "sp": "NAO"}]}


def test_corpo_diz_o_que_travou_e_o_que_fazer(n):
    corpo = n.montar_corpo_pagamento("65879", "SPEED PACK", _PEND, _CTX)
    for trecho in ("Todos os documentos da operacao 65879 estao assinados", _PEND[0], "SPEED PACK",
                   "R$ 12.659,99", "vencimento 21/09/2026", "SP NAO marcado", "Resumir > Pagamento"):
        assert trecho in corpo, trecho


def test_sem_canal_ligado_nao_tenta(n, smtp, monkeypatch):
    monkeypatch.setattr(n.cfg, "EMAIL_ATIVO", False)
    r = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)
    assert not r["enviado"] and not r["tentou"] and "nenhum canal" in r["motivo"]
    assert smtp.instancias == [] and n._wpp_enviados == []
    monkeypatch.setattr(n.cfg, "AVISO_PENDENCIA_CANAIS", [])
    monkeypatch.setattr(n.cfg, "EMAIL_ATIVO", True)
    assert not n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)["tentou"], \
        "R7_AVISO_PENDENCIA_CANAIS vazio desliga o aviso de pendencia"


def test_so_whatsapp_como_em_producao(n, smtp, monkeypatch):
    """Producao em 22/09: e-mail desligado (o relay recusa na saida), WhatsApp ligado."""
    monkeypatch.setattr(n.cfg, "AVISO_PENDENCIA_CANAIS", ["whatsapp", "email"])
    monkeypatch.setattr(n.cfg, "EMAIL_ATIVO", False)
    r = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)
    assert r["enviado"] and list(r["canais"]) == ["whatsapp"] and smtp.instancias == []
    texto, destinos = n._wpp_enviados[0]
    assert destinos == ["5500000000000"]
    for trecho in ("Operação 65879 pronta, mas o pagamento trava", "SPEED PACK",
                   "todos assinados", "Vencto = 21/09/2026, deveria ser a data de hoje"):
        assert trecho in texto, trecho
    assert "Pagamento: Vencto" not in texto, "o prefixo 'Pagamento:' so atrapalha no celular"


@pytest.mark.parametrize("pendencia, curta", [
    ("Pagamento: SP nao esta marcado", "SP nao esta marcado"),
    ("Pagamento (linha 2): campo 'CC' esta VAZIO", "linha 2: campo 'CC' esta VAZIO"),
    ("Forma de pagamento: NAO ha nenhuma linha registrada", "NAO ha nenhuma linha registrada"),
    ("Etapa: outra coisa", "Etapa: outra coisa"),
])
def test_pendencia_curta_no_whatsapp(n, pendencia, curta):
    assert n._pendencia_curta(pendencia) == curta


def test_um_canal_que_falha_nao_impede_o_outro(n, smtp, monkeypatch):
    monkeypatch.setattr(n.cfg, "AVISO_PENDENCIA_CANAIS", ["whatsapp", "email"])
    smtp.falhar = True
    r = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)
    assert r["enviado"] and r["canais"]["whatsapp"]["ok"] and not r["canais"]["email"]["ok"]


def test_todos_os_canais_falhando_nao_conta_como_aviso(n, smtp, monkeypatch):
    monkeypatch.setattr(n.cfg, "AVISO_PENDENCIA_CANAIS", ["whatsapp", "email"])
    smtp.falhar, n._wpp_falhar = True, True
    r = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)
    assert r["tentou"] and not r["enviado"] and "nenhum canal entregou" in r["motivo"]
    smtp.falhar, n._wpp_falhar = False, False
    assert n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)["enviado"]


def test_espacamento_entre_avisos_e_zerar_quando_muda(n, smtp):
    r1 = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)
    assert r1["enviado"] and r1["destinatarios"] == ["operacional@exemplo.test"]
    assert "PAGAMENTO impede" in smtp.instancias[0].enviados[0][2]
    r2 = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)
    assert not r2["tentou"] and "espacamento" in r2["motivo"], "mesmo aviso de novo, na hora, nao"
    r3 = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND + ["Pagamento: SP nao marcado"], _CTX)
    assert r3["enviado"], "pendencia nova e cobranca nova"


def test_falha_de_envio_nao_conta_como_aviso(n, smtp):
    smtp.falhar = True
    r = n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)
    assert r["tentou"] and not r["enviado"]
    smtp.falhar = False
    assert n.avisar_pagamento_pendente("65879", "SPEED PACK", _PEND, _CTX)["enviado"], \
        "sem registro da falha, o proximo ciclo tenta de novo"


# --------------------------------------------------------------------------- #
# quem decide avisar: o processar()
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
def robo(monkeypatch):
    monkeypatch.setenv("R7_DRY_RUN", "0")
    mod = _importar(monkeypatch, "finalizar_operacao")
    monkeypatch.setattr(mod.cfg, "PAGAMENTO_SO_APOS_ASSINATURAS", True)
    monkeypatch.setattr(mod.cfg, "_agora", lambda: datetime(2026, 9, 22, 10, 0))
    monkeypatch.setattr(mod, "_dados_da_operacao", lambda ctx, op: (["DMR"], "SPEED PACK", 12659.99))
    monkeypatch.setattr(mod, "_etapa_da_operacao", lambda ctx, op: "Aguardando Ass.")
    monkeypatch.setattr(mod.checagem_docs, "_ROTULO", {"aditivo": "Aditivo"})
    return mod


def _armar(robo, monkeypatch, docs_pend, pag_pend, resposta=None):
    monkeypatch.setattr(robo.checagem_docs, "conferir", lambda ctx, op, tipos, nome_cedente=None: {
        "ok": not docs_pend, "pendencias": list(docs_pend), "observacoes": [],
        "exigidos": ["aditivo"], "encontrados": {"aditivo": {"assinados": 1, "total": 1}}})
    monkeypatch.setattr(robo.checagem_pagamento, "conferir", lambda pg, op, log=print: {
        "ok": not pag_pend, "pendencias": list(pag_pend), "linhas": _CTX["linhas_pagamento"]})
    avisos, eventos = [], []

    def _avisar(op, cedente, pendencias, contexto=None, destinatarios=None):
        avisos.append((op, list(pendencias)))
        return resposta or {"enviado": True, "tentou": True, "motivo": "enviado",
                            "destinatarios": ["operacional@exemplo.test"],
                            "canais": {"whatsapp": {"ok": True, "detalhe": "OK"}}}

    monkeypatch.setattr(robo.notificar, "avisar_pagamento_pendente", _avisar)
    monkeypatch.setattr(robo.execucao_job, "registrar_evento_operacao",
                        lambda ex, op, tipo, **kw: eventos.append((tipo, kw)))
    monkeypatch.setattr(robo.fin, "finalizar_da_grade",
                        lambda *a, **k: pytest.fail("com pendencia nao ha clique"))
    return avisos, eventos


def test_esperando_assinatura_nao_avisa(robo, monkeypatch):
    avisos, eventos = _armar(robo, monkeypatch, ["Aditivo: falta assinatura"], [])
    laudo = robo.processar(_Ctx(), "65879", executar=True, mandar_email=True, execucao=object())
    assert avisos == [] and eventos == []
    assert laudo["acao"] == "aguardando assinatura"


def test_documentos_ok_e_pagamento_travando_avisa_e_registra(robo, monkeypatch):
    avisos, eventos = _armar(robo, monkeypatch, [], _PEND)
    laudo = robo.processar(_Ctx(), "65879", executar=True, mandar_email=True, execucao=object())
    assert avisos == [("65879", _PEND)]
    assert laudo["acao"] == "avisado"
    tipo, kw = eventos[0]
    assert tipo == "aviso_enviado" and kw["resultado"] == "ok"
    assert kw["detalhe"]["motivo_aviso"] == "pagamento_pendente"
    assert kw["detalhe"]["canais"] == {"whatsapp": {"ok": True, "detalhe": "OK"}}
    assert kw["detalhe"]["pendencias"] == _PEND


def test_sem_email_no_comando_nao_avisa(robo, monkeypatch):
    avisos, eventos = _armar(robo, monkeypatch, [], _PEND)
    laudo = robo.processar(_Ctx(), "65879", executar=True, mandar_email=False, execucao=object())
    assert avisos == [] and eventos == [] and laudo["acao"] == "avisar"


def test_aviso_segurado_pelo_espacamento_nao_vira_evento(robo, monkeypatch):
    avisos, eventos = _armar(robo, monkeypatch, [], _PEND, resposta={
        "enviado": False, "tentou": False, "motivo": "aguardando espacamento",
        "destinatarios": ["operacional@exemplo.test"]})
    laudo = robo.processar(_Ctx(), "65879", executar=True, mandar_email=True, execucao=object())
    assert len(avisos) == 1 and eventos == [] and laudo["acao"] == "avisar"
