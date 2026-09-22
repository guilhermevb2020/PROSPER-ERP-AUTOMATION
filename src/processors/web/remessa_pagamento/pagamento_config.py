# -*- coding: utf-8 -*-
"""
pagamento_config.py - configuracao do robo de REMESSA DE PAGAMENTO no container.

Tela do Smart: Financeiro > Sistemas de pagamento > Pagamento BMP Money Plus >
Gerar Remessa. NAO confundir com a remessa de COBRANCA, que e do `remessa_cobranca`
e vive em outra arvore (`financeiro/remessaocorrencia.php`).

Slot deste robo (ver docs/COMO_SUBIR_UM_JOB.md §1):
    display :94 | VNC 5905 | noVNC 6085 | CDP 9226 | perfil data/robo_pagamento

Credenciais: `config/remessa_pagamento.env` (montado, fora do git). NUNCA no fonte —
este repo tem remote publico. Ver `remessa_pagamento.example.env`.

Os endpoints abaixo foram MEDIDOS em 21/08/2026, pelo sandbox do host
(`scripts/sandbox/pagamento.py`), contra o Smart real. Nao sao chute: cada um
saiu do HTML que esta guardado em `data/sandbox/robo_pagamento/debug/`.
"""
import os

# Credenciais/flags do robo. `load_dotenv` NAO sobrescreve o que ja veio do
# ambiente, entao `docker exec -e` continua tendo precedencia sobre o arquivo.
try:
    from dotenv import load_dotenv

    load_dotenv(os.environ.get("PAGAMENTO_ENV_FILE", "/app/config/remessa_pagamento.env"))
except ImportError:
    pass


def _s(chave: str, padrao: str) -> str:
    return os.environ.get(chave, padrao)


def _b(chave: str, padrao: str) -> bool:
    return _s(chave, padrao).strip().lower() in ("1", "true", "sim", "yes")


# --------------------------------------------------------------------------- #
# Credenciais do Smart
# --------------------------------------------------------------------------- #
# O usuario precisa de acesso a Financeiro > Sistemas de pagamento > Pagamento
# BMP Money Plus E a conta percorrida. Hoje e a MESMA conta de todos os robos do
# container (prosperito@prospereinvest.com.br) — mexer nela atinge os cinco.
EMAIL = _s("PAGAMENTO_EMAIL", "")
SENHA = _s("PAGAMENTO_SENHA", "")

# --------------------------------------------------------------------------- #
# Chrome / display - ISOLADOS dos demais robos
# --------------------------------------------------------------------------- #
USER_DATA_DIR = _s("USER_DATA_DIR_PAG", "/app/data/robo_pagamento/perfil_chrome")
HEADLESS = _b("HEADLESS_PAG", "False")     # False: pinta no Xvfb :94 (VNC de debug)
CDP_PORT = int(_s("CDP_PORT_PAG", "9226"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"   # IPv4 explicito: 'localhost' vira ::1
                                           # e o Chrome so escuta em IPv4
# Var PROPRIA, nunca `DISPLAY`: o compose define DISPLAY=:99 (boletos) para todo
# processo do container, e ler a var pura poe este Chrome em cima do deles —
# dois Chromes no mesmo display fazem o login quicar de volta para a landing.
DISPLAY = _s("DISPLAY_PAG", ":94")

# --------------------------------------------------------------------------- #
# Smart
# --------------------------------------------------------------------------- #
SMART_HOST = _s("SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
SMART_BASE = SMART_HOST + "/smart"
URL_LOGIN = _s("URL_LOGIN", "https://www.smartsecurities.com.br/smartsecurities/")

# A arvore NAO se chama "pagamento": e `financeiro/pagtobmp/`. Medido em
# 21/08/2026 — procurar por "pagamento" no menu devolve ZERO (foi o que a
# primeira rodada da Fase 0 fez, e por isso isto esta escrito aqui).
_PAGTOBMP = SMART_BASE + "/financeiro/pagtobmp"

# Tela de PESQUISA: so o filtro. A grade nao vem no GET dela nem do grid.
URL_PESQUISA = _s("URL_PESQUISA_PAG", _PAGTOBMP + "/pagtobmppesquisa.php")

# GRADE: e o mesmo endpoint para as DUAS coisas, e essa e a pegadinha da tela.
#   POST com `pesquisar=1`              -> LISTA os pagamentos (inofensivo)
#   POST com `processar=1` e `acao=1`   -> GERA A REMESSA (irreversivel)
# Um caractere de diferenca entre consultar e mover dinheiro.
URL_GERAR = _s("URL_GERAR_PAG", _PAGTOBMP + "/pagtobmpgrid.php").strip()
URL_LISTAR = _s("URL_LISTAR_PAG", URL_GERAR).strip()

# Download do arquivo gerado: GET com o id que a grade mostra no link.
# Medido: `mandarsispag.php?file=22` -> `CP2108000001.REM`. O nome segue o mesmo
# padrao da cobranca (`CB`+DDMM+seq), trocando o prefixo: CP de pagamento.
URL_DOWNLOAD = _s("URL_DOWNLOAD_PAG", SMART_BASE + "/financeiro/mandarsispag.php")

# Valores de `acao` no POST de processamento, lidos do JS `GerarMultipag(bt, acao)`
# da propria grade.
ACAO_GERAR = 1
ACAO_REENVIAR = 2      # devolve os titulos para pendente (a tela pede confirm)
ACAO_CANCELAR = 3      # idem

# ⛔⛔ O STATUS DO FILTRO DITA A ACAO DA TELA. Medido em 21/08/2026, comparando o
#     HTML das duas grades (estao em DEBUG_DIR):
#
#       filtro P (Pendente) -> a tela tem UM botao:  GerarMultipag(this, 1)
#                              "Gerar Pagamento BMP Money Plus"
#       filtro G (Gerado)   -> a tela tem UM botao:  GerarMultipag(this, 3)
#                              "Cancelar Pagamento BMP Money Plus"
#
#     Mesmo form (`multipagForm`), mesmo endpoint, MESMOS campos, mesmos titulos
#     na grade. So muda o numero em `acao`. Um robo que filtrasse por "Gerado"
#     para achar o arquivo e submetesse o form da tela CANCELARIA os pagamentos —
#     e o POST e identico ao de gerar, exceto por um digito.
#
#     Por isso o robo NUNCA le a acao da tela: ela e chumbada em ACAO_GERAR, e a
#     geracao so pode rodar sobre uma grade que veio do filtro PENDENTE. Ler a
#     acao do HTML seria deixar a tela decidir o que fazer com o dinheiro.
EXIGIR_STATUS_PENDENTE_PARA_GERAR = True

# Tela usada so pela Fase 0 para colher os links do menu. E uma tela que JA
# sabemos que responde (a de remessa de cobranca), e serve unicamente de ponto de
# partida do reconhecimento — nao tem nada a ver com o trabalho deste robo.
URL_SEMENTE = _s("URL_SEMENTE_PAG", SMART_BASE + "/financeiro/remessaocorrencia.php")

# Ping de sessao. Deve apontar para A TELA QUE ESTE ROBO PRECISA: assim "logado"
# quer dizer "alcanca a tela", e um usuario sem permissao no Pagamento BMP falha
# no comeco, com mensagem clara, em vez de virar "nada a fazer" la na frente.
# Enquanto a Fase 0 nao rodou, cai na semente — o que valida a SESSAO mas NAO a
# permissao; `ping_provisorio()` existe para o robo dizer isso em voz alta.
URL_PING = _s("URL_PING_PAG", URL_GERAR or URL_SEMENTE)


def ping_provisorio() -> bool:
    """True enquanto o ping ainda for a semente, e nao a tela do robo."""
    return URL_PING == URL_SEMENTE


def exigir_credenciais() -> None:
    """Falha alto e cedo se a credencial nao carregou.

    Chamado pelo fluxo de login, nao no import: os modos read-only sobre uma
    sessao ja viva (`--cdp`) nao precisam de senha.
    """
    faltando = [n for n, v in (("PAGAMENTO_EMAIL", EMAIL), ("PAGAMENTO_SENHA", SENHA))
                if not v.strip()]
    if faltando:
        raise RuntimeError(
            f"Credencial ausente: {', '.join(faltando)}. Defina em "
            "/app/config/remessa_pagamento.env (fora do git) ou no ambiente do container.")


def exigir_tela() -> None:
    """Impede a geracao enquanto o endpoint real nao foi descoberto.

    Sem isso o robo postaria numa URL vazia, receberia erro e — pior — poderia
    tratar o erro como 'nao ha pagamento a gerar'. Falha explicita e melhor.
    """
    if not URL_GERAR:
        raise RuntimeError(
            "URL_GERAR_PAG esta vazia. O default e o endpoint medido na Fase 0 "
            f"({_PAGTOBMP}/pagtobmpgrid.php); alguem o apagou no .env. Sem ele o "
            "robo postaria numa URL vazia e leria o erro como 'nada a gerar'.")


# --------------------------------------------------------------------------- #
# Escopo
# --------------------------------------------------------------------------- #
# DRY_RUN=True: monta o POST, loga o que faria e NAO gera nada no Smart.
# Default TRUE de proposito — gerar remessa de pagamento move dinheiro.
DRY_RUN = _b("DRY_RUN_PAG", "True")
# UMA conta fixa (decisao do dono): a rodada e curta e previsivel, o que e o que
# a cadencia de 30 em 30 minutos pede. Medido na Fase 0: o <select>
# `IdContaBancaria` da tela tem UMA conta so alem do "Selecione" —
#   404 = "mp prospere | 274 | 0001 | 0986952"  (274 = BMP Money Plus)
CONTA = _s("CONTA_PAG", "404").strip()

# Status no <select> `pagtobmp` da pesquisa. O robo busca PENDENTE: e o que
# ainda nao virou remessa.
STATUS_PENDENTE = "P"
STATUS_GERADO = "G"
STATUS_REJEITADO = "R"
STATUS = _s("STATUS_PAG", STATUS_PENDENTE).strip()

# --------------------------------------------------------------------------- #
# Pastas
# --------------------------------------------------------------------------- #
# Destino do arquivo gerado (decisao do dono, 21/08/2026). `/app/temp` e
# bind-mount de `erp-automation/temp/` no host (`./temp:/app/temp` no compose) e
# esta no .gitignore (`temp/*`), entao remessa de pagamento nao entra no repo
# por acidente.
#
# ⚠️ O NOME TEM ESPACOS, e isso e de proposito (foi o caminho pedido). Toda
# referencia em shell precisa de aspas: `"$PASTA"`, nunca $PASTA solto. Ha
# precedente no projeto — o destino do remessa_cobranca e
# `process-automation/tmp/remessas a enviar`, tambem com espacos.
#
# ⚠️ Pasta LOCAL, "por enquanto": nao esta em share Samba nem no Nextcloud — de
# um Windows ninguem a enxerga, so quem tem acesso ao servidor. Foi exatamente
# essa a limitacao que fez o remessa_cobranca passar a publicar no Nextcloud, e o
# uploader (`src/common/clients/nextcloud_webdav.py`) ja e compartilhado quando
# isso virar requisito.
PASTA_SAIDA = _s("PASTA_SAIDA_PAG", "/app/temp/remessas de pagamento")
# Controle de idempotencia. Fica em data/, que sobrevive a recriacao do
# container (temp/ tambem sobrevive, mas e pasta de trabalho: some sem aviso).
ARQ_CONTROLE = _s("ARQ_CONTROLE_PAG", "/app/data/robo_pagamento/controle_pagamentos.csv")
# Fase 2 de docs/PLANO_CONTROLE_NO_BANCO.md: de onde vem o "ja gerei este arquivo".
# `csv` (padrao) le o controle acima; `banco` le erp_automation.vw_controle_pagamento e,
# sem banco, volta ao CSV avisando. O CSV e escrito nos dois modos ate o corte (Fase 4).
CONTROLE_FONTE = _s("CONTROLE_FONTE_PAG", _s("CONTROLE_FONTE", "csv")).strip().lower()
DEBUG_DIR = _s("DEBUG_DIR_PAG", "/app/data/robo_pagamento/debug")


def ensure_dirs() -> None:
    """Cria as pastas de trabalho. Idempotente."""
    for d in (USER_DATA_DIR, PASTA_SAIDA, DEBUG_DIR,
              os.path.dirname(ARQ_CONTROLE) or "."):
        os.makedirs(d, exist_ok=True)
