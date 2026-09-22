# -*- coding: utf-8 -*-
"""
boletos/_sessao.py nunca imprime uma excecao inteira: o "call log" do Playwright traz os
cabecalhos da requisicao, cookie de sessao incluido, e foi parar no manter_sessao.log
(22/09/2026, 8 linhas com PHPSESSID). O helper corta na primeira linha e antes de qualquer
"cookie:"; o gate de fonte garante que nenhum print voltou a usar `{e}` cru.
"""
from __future__ import annotations

import inspect
import re

from src.processors.web.boletos import _sessao


class _ErroPlaywright(RuntimeError):
    pass


def test_resumo_corta_o_call_log_e_o_cookie():
    e = _ErroPlaywright("APIRequestContext.get: Timeout 30000ms exceeded.\nCall log:\n"
                        "  - -> GET https://wvw.smartsecurities.com.br/x\n"
                        "    - cookie: device_id=abc; PHPSESSID=0123456789abcdef0123456789abcdef")
    r = _sessao._resumo_excecao(e)
    assert r == "_ErroPlaywright: APIRequestContext.get: Timeout 30000ms exceeded."
    assert "PHPSESSID" not in r and "device_id" not in r


def test_resumo_corta_cookie_mesmo_numa_linha_so_e_limita_o_tamanho():
    r = _sessao._resumo_excecao(ValueError("falhou; Cookie: PHPSESSID=segredo"))
    assert r == "ValueError: falhou;"
    assert len(_sessao._resumo_excecao(ValueError("x" * 500))) <= len("ValueError: ") + 160
    assert _sessao._resumo_excecao(RuntimeError("")) == "RuntimeError"


def test_nenhum_print_do_modulo_despeja_a_excecao_inteira():
    fonte = inspect.getsource(_sessao)
    cru = re.findall(r'print\(f"[^"\n]*\{e\}[^"\n]*"\)', fonte)
    assert cru == [], f"print com excecao inteira: {cru}"
    assert fonte.count("_resumo_excecao(e)") >= 7
