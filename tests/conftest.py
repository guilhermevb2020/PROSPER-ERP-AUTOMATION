# -*- coding: utf-8 -*-
"""
conftest.py - nenhum teste escreve nos arquivos de estado REAIS do finalizador.

Por que existe: os arquivos de estado do job finalizar_operacao (finalizadas, avisos, a rotina de avisos)
moram em src/processors/web/finalizar_operacao/, que e bind-mount do container de
producao. Em 22/09/2026 os testes que simulam uma finalizacao gravaram ops de mentira
(65071, "CEDENTE X") no finalizadas_pix.jsonl real - e a rodada seguinte do job teria
tentado conferir o PIX delas e avisado o WhatsApp. Aqui cada teste ganha uma pasta
temporaria para esses arquivos, por variavel de ambiente (lida quando o teste importa o
r7_config) e por atributo (se o r7_config ja estiver carregado).
"""
from __future__ import annotations

import sys

import pytest

_ARQUIVOS = {
    "R7_ARQ_ROTINA": ("ARQ_ROTINA", "rotina_avisos.json"),
    "R7_ARQ_FINALIZADAS_PIX": ("ARQ_FINALIZADAS_PIX", "finalizadas_pix.jsonl"),
    "R7_ARQ_AVISOS": ("ARQ_AVISOS", "avisos_enviados.csv"),
    "R7_ARQ_FINALIZADAS": ("ARQ_FINALIZADAS", "finalizadas.csv"),
    "R7_WHATSAPP_ARQUIVO": ("WHATSAPP_ARQUIVO_SAIDA", "whatsapp_enviados.txt"),
}


@pytest.fixture(autouse=True)
def _estado_do_finalizador_isolado(monkeypatch, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("estado_finalizador")
    for env, (atributo, nome) in _ARQUIVOS.items():
        caminho = str(pasta / nome)
        monkeypatch.setenv(env, caminho)
        carregado = sys.modules.get("r7_config")
        if carregado is not None and hasattr(carregado, atributo):
            monkeypatch.setattr(carregado, atributo, caminho)
    yield
