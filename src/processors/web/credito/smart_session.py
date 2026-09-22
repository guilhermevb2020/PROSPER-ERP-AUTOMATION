# -*- coding: utf-8 -*-
"""
smart_session.py - base compartilhada para conectar na sessao VIVA do Smart
(janela do Chrome aberta pelos keep-alive sessao_raphael.py / sessao_boletos.py,
exposta via CDP) e fazer requisicoes autenticadas SEM navegar.

Por que existe:
  - Centraliza a conexao CDP num lugar so (DRY).
  - USA 127.0.0.1 e NAO 'localhost': 'localhost' resolve p/ IPv6 (::1) e o Chrome
    escuta so em IPv4 -> connect_over_cdp falha com ECONNREFUSED ::1:9222.
  - Centraliza o decode iso-8859-1 (as respostas do Smart NAO sao utf-8;
    r.text() quebra, r.body().decode('iso-8859-1') funciona).

Uso tipico:
    from smart_session import Smart, BASE
    with Smart() as s:
        if not s.logado():
            print("sessao deslogada - logue na janela"); return
        html = s.get(BASE + "/operacaoajax/web/...")
        resp = s.post(url, body)
"""
import os
import sys

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"          # IPv4 explicito (NAO use 'localhost')
# Mesmo backend, dominios/marcas diferentes: smartsecurities.com.br e
# smartfactor.com.br. Configurar pelo dominio em que a SESSAO esta logada:
#   $env:SMART_HOST="https://wvw.smartfactor.com.br"; $env:SMART_PING_PHP="smartfactor.php"
HOST = os.getenv("SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
BASE = HOST + "/smart"
URL_PING = BASE + "/" + os.getenv("SMART_PING_PHP", "smartsecurities.php")  # redireciona p/ login se deslogado


def utf8_stdout():
    """Garante stdout utf-8 no Windows (acentos nas respostas do Smart)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class Smart:
    """Context manager: conecta na sessao viva via CDP e expoe get/post autenticados."""

    def __init__(self, cdp=CDP):
        self.cdp = cdp
        self._p = None
        self.browser = None
        self.ctx = None
        self._attached = False   # True quando "anexado" a um ctx ja existente

    @classmethod
    def attach(cls, ctx):
        """Cria um Smart ANEXADO a um BrowserContext ja existente (ex.: o ctx do
        Robo 1, via launch_persistent_context) - SEM connect_over_cdp. Permite usar
        as funcoes que recebem `s` (titulos_da_op, listar_docs, baixar_doc,
        gravar_parecer) com a sessao propria do robo. Pode ser usado direto (sem
        `with`) ou em `with` (o __exit__ NAO solta o playwright do chamador)."""
        self = cls.__new__(cls)
        self.cdp = None
        self._p = None
        self.browser = None
        self.ctx = ctx
        self._attached = True
        return self

    def __enter__(self):
        if self._attached:
            return self
        self._p = sync_playwright().start()
        self.browser = self._p.chromium.connect_over_cdp(self.cdp)
        if not self.browser.contexts:
            raise RuntimeError("CDP conectou mas nao ha contexto/janela aberta.")
        self.ctx = self.browser.contexts[0]
        return self

    def __exit__(self, *exc):
        # NAO fecha o browser/ctx (e a janela viva do usuario). So solta o
        # playwright que ESTE objeto iniciou (nao mexe no do chamador se anexado).
        if not self._attached:
            try:
                self._p.stop()
            except Exception:
                pass
        return False

    # --- helpers de request autenticado (usam os cookies da sessao viva) ---
    def get(self, url, timeout=30_000):
        r = self.ctx.request.get(url, timeout=timeout)
        return r.status, r.body().decode("iso-8859-1", errors="replace")

    def post(self, url, body, timeout=60_000, headers=None):
        h = {"content-type": "application/x-www-form-urlencoded"}
        if headers:
            h.update(headers)
        r = self.ctx.request.post(url, data=body, headers=h, timeout=timeout)
        return r.status, r.body().decode("iso-8859-1", errors="replace")

    def logado(self):
        """True se a sessao esta autenticada (o ping NAO cai pra tela de login)."""
        try:
            status, html = self.get(URL_PING, timeout=20_000)
        except Exception:
            return False
        low = html.lower()
        # heuristica: pagina de login tem campos de usuario/senha/recaptcha
        deslogado = ("recaptcha" in low or "name=\"senha\"" in low
                     or "name='senha'" in low or "/smartsecurities/" in low and "login" in low)
        return status == 200 and not deslogado

    def nova_pagina(self):
        """Abre uma aba na sessao viva (com auto-accept de dialogos JS)."""
        pg = self.ctx.new_page()
        pg.on("dialog", lambda d: d.accept())
        return pg


def conectado(cdp=CDP):
    """Checagem rapida: da pra conectar no CDP? (nao garante login)."""
    try:
        with Smart(cdp) as s:
            return s.ctx is not None
    except Exception:
        return False
