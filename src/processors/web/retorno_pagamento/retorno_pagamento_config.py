# -*- coding: utf-8 -*-
"""
retorno_pagamento_config.py - configuracao do robo que INSERE o retorno de
PAGAMENTO no Smart.

Tela: Financeiro > Sistemas de pagamento > Pagamento BMP Money Plus > Processar
Retorno. MESMA area do `remessa_pagamento` (que so GERA a remessa) — por isso usa a
MESMA credencial (`PAGAMENTO_EMAIL`/`PAGAMENTO_SENHA`, carregada pelo
`run_agendado.sh` de `config/remessa_pagamento.env`), mas com display, perfil e
sessao PROPRIOS: dois robos no mesmo perfil de Chrome travam o login um do
outro (mesmo motivo do `retorno_cobranca` ter sessao propria, so que aqui a conta
Smart e a MESMA e so o navegador e isolado).

Slot deste robo (ver docs/COMO_SUBIR_UM_ROBO.md §1):
    display :93 | VNC 5906 | noVNC 6086 | CDP 9227 | perfil data/robo_retorno_pagamento

O contrato do form foi MEDIDO em 26/08/2026 via `descobrir.py` (GET simples,
sem submeter nada): `retornopagtobmp.php` tem 1 form (`retornoSispag`,
multipart/form-data, POST pra si mesma) com 4 campos — `MAX_FILE_SIZE` (hidden,
15728640), `form_submit` (hidden, "1"), `origem` (hidden, SEMPRE vazio — nao
existe JS na tela que o preencha) e `avatar_file` (o `.RET`). O HTML cru esta
em `DEBUG_DIR`.

O robo INSERE — nao julga a resposta. Uma vez que o POST chegou ao servidor e
teve resposta, o arquivo sai da entrada e nao e reenviado (decisao do dono,
26/08/2026: ninguem revisa fila de resultado incerto, entao o robo nao cria
uma).
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv(os.environ.get("RETPAG_ENV_FILE", "/app/config/retorno_pagamento.env"))
except ImportError:
    pass


def _s(chave: str, padrao: str) -> str:
    return os.environ.get(chave, padrao)


def _b(chave: str, padrao: str) -> bool:
    return _s(chave, padrao).strip().lower() in ("1", "true", "sim", "yes")


# --------------------------------------------------------------------------- #
# Credenciais do Smart — MESMA conta do remessa_pagamento (mesma tela, mesmo modulo)
# --------------------------------------------------------------------------- #
# O `run_agendado.sh` deste robo carrega `config/remessa_pagamento.env` ANTES
# (mesma variavel, sem duplicar o segredo em dois arquivos). Um `RETPAG_EMAIL`/
# `RETPAG_SENHA` explicito sobrescreve, se um dia a conta precisar ser outra.
EMAIL = _s("RETPAG_EMAIL", _s("PAGAMENTO_EMAIL", ""))
SENHA = _s("RETPAG_SENHA", _s("PAGAMENTO_SENHA", ""))

# --------------------------------------------------------------------------- #
# Chrome / display - ISOLADOS dos demais robos
# --------------------------------------------------------------------------- #
USER_DATA_DIR = _s("USER_DATA_DIR_RETPAG", "/app/data/robo_retorno_pagamento/perfil_chrome")
HEADLESS = _b("HEADLESS_RETPAG", "False")
CDP_PORT = int(_s("CDP_PORT_RETPAG", "9227"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
# Var PROPRIA, nunca `DISPLAY`: ver a mesma nota em pagamento_config.py.
DISPLAY = _s("DISPLAY_RETPAG", ":93")

# --------------------------------------------------------------------------- #
# Smart
# --------------------------------------------------------------------------- #
SMART_HOST = _s("SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
SMART_BASE = SMART_HOST + "/smart"
URL_LOGIN = _s("URL_LOGIN", "https://www.smartsecurities.com.br/smartsecurities/")

# A tela de Processar Retorno do pagamento BMP — medida em 26/08/2026 (ver
# docstring do modulo).
URL_RETORNO = _s("URL_RETORNO_RETPAG", SMART_BASE + "/financeiro/pagtobmp/retornopagtobmp.php")

# Ping = a PROPRIA tela do robo: "logado" quer dizer "alcanca a tela", nao so
# "a sessao existe" — usuario sem permissao no Processar Retorno falha cedo.
URL_PING = _s("URL_PING_RETPAG", URL_RETORNO)


def exigir_credenciais() -> None:
    """Falha alto e cedo se a credencial nao carregou."""
    faltando = [n for n, v in (("PAGAMENTO_EMAIL/RETPAG_EMAIL", EMAIL),
                                ("PAGAMENTO_SENHA/RETPAG_SENHA", SENHA))
                if not v.strip()]
    if faltando:
        raise RuntimeError(
            f"Credencial ausente: {', '.join(faltando)}. O run_agendado.sh deste "
            "robo carrega config/remessa_pagamento.env antes de rodar — confira se "
            "esse arquivo existe e tem PAGAMENTO_EMAIL/PAGAMENTO_SENHA.")


# --------------------------------------------------------------------------- #
# Seguranca
# --------------------------------------------------------------------------- #
# DRY_RUN=True: baixa o .RET do Nextcloud, monta o multipart e LOGA o que
# mandaria — NAO faz o POST. Default TRUE de proposito: o POST desta tela DA
# BAIXA em titulo de pagamento real, e a resposta nunca foi medida antes
# (ver aviso no topo do arquivo).
DRY_RUN = _b("DRY_RUN_RETPAG", "True")

# --------------------------------------------------------------------------- #
# Nextcloud — onde o .RET chega e para onde vai depois
# --------------------------------------------------------------------------- #
# `baixar_retorno_pagamento.py` (process-automation) publica o `.RET` cru aqui
# assim que grava com sucesso em `financeiro.cnab240_pagamento`. Mesma arvore
# do `enviar_pagamento.py` (`FINANCEIRO/Pagamentos-MoneyPlus/`), pasta irma de
# `_A_ENVIAR`/`_ENVIADAS`/`_ERRO`.
NC_DEST_BASE = _s("RETPAG_NC_DEST", "FINANCEIRO/Pagamentos-MoneyPlus/_RETORNOS")
NC_ENV = _s("RETPAG_NC_ENV", "/app/config/nextcloud.env")

# Subpasta DENTRO de NC_DEST_BASE — mesmo desenho do retorno_cobranca
# (PASTA_PROCESSADOS = subpasta de PASTA_ENTRADA). Só duas situações existem:
#   ""            entrada — .RET ainda não submetido
#   PROCESSADOS   o POST chegou ao servidor e teve resposta — não se reenvia
#                 mais, seja qual for o conteúdo da resposta (o robô insere,
#                 não julga; ver retorno_pagamento.py)
# Falha de rede ou sessão morta NÃO move nada — o arquivo fica na entrada e a
# próxima rodada tenta de novo, porque nesses casos o POST pode nem ter saído.
SUB_PROCESSADOS = "_PROCESSADOS"

# --------------------------------------------------------------------------- #
# Controle e debug (local, sobrevive a recriacao do container)
# --------------------------------------------------------------------------- #
ARQ_CONTROLE = _s("ARQ_CONTROLE_RETPAG", "/app/data/robo_retorno_pagamento/controle.csv")
DEBUG_DIR = _s("DEBUG_DIR_RETPAG", "/app/data/robo_retorno_pagamento/debug")
PAUSA_ENTRE_ARQUIVOS = float(_s("PAUSA_ENTRE_ARQUIVOS_RETPAG", "1.0"))


def ensure_dirs() -> None:
    """Cria as pastas de trabalho. Idempotente."""
    for d in (USER_DATA_DIR, DEBUG_DIR, os.path.dirname(ARQ_CONTROLE) or "."):
        os.makedirs(d, exist_ok=True)
