#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes das travas de configuracao do robo de pagamento.

POR QUE ESTES TESTES EXISTEM
----------------------------
Duas das tres armadilhas de "sucesso falso" documentadas em
`docs/COMO_SUBIR_UM_ROBO.md` sao de CONFIGURACAO, nao de codigo — e as duas
terminam com o hub verde e nada feito:

  - `DRY_RUN` ligado no `.env` e o comando agendado sem a flag: o robo sai com
    exit 0 e um resumo bonito, sem gerar nada. Aconteceu com o robo de remessa.
  - endpoint errado ou vazio: o POST volta erro, e erro aqui e indistinguivel de
    "nao ha pagamento a gerar".

Este robo nasce com a segunda travada de verdade (`exigir_tela()` levanta) e com
a primeira em padrao seguro (`DRY_RUN=True`). Os testes prendem as duas — e
prendem que o DEFAULT nao mudou por descuido, que e como esse tipo de regressao
entra.

RESTRICOES DE AMBIENTE
----------------------
`pagamento_config.py` so depende de stdlib (o `dotenv` esta em try/except), entao
importa no host. As envs vazam entre testes por serem resolvidas NO IMPORT — dai
o `reload` a cada caso.
"""
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "remessa_pagamento"))

# Sufixo das envs deste robo. Sem `_PAG`, ler `DISPLAY` puro pegaria o `:99` dos
# boletos que o compose define para todo processo do container.
ENVS = ("PAGAMENTO_ENV_FILE", "PAGAMENTO_EMAIL", "PAGAMENTO_SENHA",
        "URL_GERAR_PAG", "URL_LISTAR_PAG", "URL_PING_PAG", "URL_SEMENTE_PAG",
        "DRY_RUN_PAG", "CONTA_PAG", "DISPLAY_PAG", "CDP_PORT_PAG",
        "USER_DATA_DIR_PAG", "PASTA_SAIDA_PAG", "HEADLESS_PAG")


@pytest.fixture
def cfg(monkeypatch):
    """Recarrega o config com o ambiente limpo; aceita overrides por env."""
    def carregar(**env):
        for nome in ENVS:
            monkeypatch.delenv(nome, raising=False)
        # aponta o dotenv para o vazio: o teste nao pode ler o .env do servidor
        monkeypatch.setenv("PAGAMENTO_ENV_FILE", "/dev/null")
        for nome, valor in env.items():
            monkeypatch.setenv(nome, valor)
        import pagamento_config
        return importlib.reload(pagamento_config)
    return carregar


# --------------------------------------------------------------------------- #
# 1. sem o endpoint descoberto, o robo nao gera — ele FALHA
# --------------------------------------------------------------------------- #
def test_endpoints_sao_os_medidos_na_fase_0(cfg):
    """Medidos em 21/08/2026 pelo sandbox, contra o Smart real.

    A arvore NAO se chama "pagamento" — e `financeiro/pagtobmp/`. A primeira
    rodada da Fase 0 procurou por "pagamento" no menu e achou ZERO; e por isso
    que o nome real esta preso aqui.
    """
    c = cfg()
    assert c.URL_PESQUISA.endswith("/financeiro/pagtobmp/pagtobmppesquisa.php")
    assert c.URL_GERAR.endswith("/financeiro/pagtobmp/pagtobmpgrid.php")
    assert c.URL_DOWNLOAD.endswith("/financeiro/mandarsispag.php")
    c.exigir_tela()          # nao levanta: o endpoint e conhecido


def test_grade_e_o_mesmo_endpoint_para_listar_e_para_gerar(cfg):
    """A pegadinha da tela: `pesquisar=1` consulta, `processar=1`+`acao=1` gera.

    Um caractere entre consultar e mover dinheiro — daí o `montar_filtro`
    recusar qualquer form sem `pesquisar` e nunca mandar botao.
    """
    c = cfg()
    assert c.URL_LISTAR == c.URL_GERAR


def test_acoes_do_js_da_grade(cfg):
    """Lidos de `GerarMultipag(bt, acao)` no HTML da grade."""
    c = cfg()
    assert (c.ACAO_GERAR, c.ACAO_REENVIAR, c.ACAO_CANCELAR) == (1, 2, 3)


def test_url_gerar_apagada_no_env_falha_alto(cfg):
    """Sem endpoint, o POST iria para lugar nenhum e o erro viraria 'nada a gerar'."""
    c = cfg(URL_GERAR_PAG="")
    with pytest.raises(RuntimeError, match="URL_GERAR_PAG"):
        c.exigir_tela()


def test_ping_aponta_para_a_tela_do_robo(cfg):
    """"Logado" tem de significar "alcanca a tela" — nao "existe um cookie"."""
    c = cfg()
    assert c.URL_PING == c.URL_GERAR
    assert c.ping_provisorio() is False


def test_ping_explicito_ganha_de_tudo(cfg):
    c = cfg(URL_GERAR_PAG="https://x/smart/a.php",
            URL_PING_PAG="https://x/smart/b.php")
    assert c.URL_PING == "https://x/smart/b.php"


# --------------------------------------------------------------------------- #
# 2. os defaults seguros
# --------------------------------------------------------------------------- #
def test_dry_run_e_o_padrao(cfg):
    """Remessa de pagamento move dinheiro: o padrao tem de ser nao fazer."""
    assert cfg().DRY_RUN is True


@pytest.mark.parametrize("valor,esperado", [
    ("false", False), ("False", False), ("0", False), ("nao", False),
    ("true", True), ("True", True), ("1", True), ("sim", True), ("SIM", True),
    ("", False), ("talvez", False),
])
def test_dry_run_so_desliga_com_valor_explicito(cfg, valor, esperado):
    """Valor estranho no `.env` NAO pode virar 'gera de verdade'."""
    assert cfg(DRY_RUN_PAG=valor).DRY_RUN is esperado


def test_credencial_ausente_falha_com_mensagem_util(cfg):
    c = cfg()
    with pytest.raises(RuntimeError) as e:
        c.exigir_credenciais()
    assert "PAGAMENTO_EMAIL" in str(e.value) and "PAGAMENTO_SENHA" in str(e.value)
    assert "remessa_pagamento.env" in str(e.value)


def test_credencial_so_de_espaco_conta_como_ausente(cfg):
    c = cfg(PAGAMENTO_EMAIL="  ", PAGAMENTO_SENHA="x")
    with pytest.raises(RuntimeError, match="PAGAMENTO_EMAIL"):
        c.exigir_credenciais()


# --------------------------------------------------------------------------- #
# 3. o slot — display, CDP e perfil PROPRIOS
# --------------------------------------------------------------------------- #
def test_conta_e_a_unica_do_select_da_tela(cfg):
    """Medido: o <select> IdContaBancaria tem uma conta so alem do 'Selecione'.

        404 = "mp prospere | 274 | 0001 | 0986952"   (274 = BMP Money Plus)
    """
    c = cfg()
    assert c.CONTA == "404"
    assert c.STATUS == c.STATUS_PENDENTE == "P"


def test_slot_e_o_reservado_na_tabela(cfg):
    """:94/9226/data/robo_pagamento — ver docs/COMO_SUBIR_UM_ROBO.md §1."""
    c = cfg()
    assert c.DISPLAY == ":94"
    assert c.CDP_PORT == 9226
    assert c.USER_DATA_DIR == "/app/data/robo_pagamento/perfil_chrome"


def test_display_do_container_nao_contamina_o_robo(cfg, monkeypatch):
    """O compose define DISPLAY=:99 (boletos) para TODO processo do container.

    Se o config lesse `DISPLAY` puro, um `docker exec` sem `-e` subiria este
    Chrome em cima do dos boletos — e dois Chromes no mesmo display fazem o
    login quicar de volta para a landing.
    """
    monkeypatch.setenv("DISPLAY", ":99")
    assert cfg().DISPLAY == ":94"


def test_cdp_em_ipv4_explicito(cfg):
    """'localhost' resolve para ::1 e o Chrome so escuta em IPv4."""
    assert cfg().CDP_URL == "http://127.0.0.1:9226"
    assert "localhost" not in cfg().CDP_URL


def test_saida_fica_em_temp_que_e_gitignored(cfg):
    c = cfg()
    assert c.PASTA_SAIDA == "/app/temp/remessas de pagamento"
    # o controle NAO: `data/` sobrevive a recriacao do container
    assert c.ARQ_CONTROLE.startswith("/app/data/")


def test_a_pasta_de_saida_tem_espacos_e_isso_e_deliberado(cfg):
    """Caminho pedido pelo dono em 21/08/2026, com espacos mesmo.

    Este teste existe para quem for mexer em shell: `$PASTA` solto quebra, tem
    de ser `"$PASTA"`. Mesma situacao do destino do robo_remessa
    (`remessas a enviar`).
    """
    assert " " in cfg().PASTA_SAIDA
