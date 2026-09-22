# -*- coding: utf-8 -*-
"""
retorno_config.py - configuracao do robo de PROCESSAR RETORNO (CNAB) no container.

Portado do pacote `robo5_processar_retorno`, que rodava no Windows com login
manual e reusava a sessao do robo de remessa. No servidor cada robo tem sessao
PROPRIA: compartilhar amarraria os horarios dos dois e um perfil compartilhado
trava no lock do Chrome.

Slot deste robo (ver docs/COMO_SUBIR_UM_JOB.md):
    display :95 | VNC 5904 | noVNC 6084 | CDP 9225 | perfil data/robo_retorno

Credenciais: `config/retorno_cobranca.env` (montado, fora do git). NUNCA no fonte —
este repo tem remote publico.
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv(os.environ.get("RETORNO_ENV_FILE", "/app/config/retorno_cobranca.env"))
except ImportError:
    pass


def _s(chave: str, padrao: str) -> str:
    return os.environ.get(chave, padrao)


def _b(chave: str, padrao: str) -> bool:
    return _s(chave, padrao).strip().lower() in ("1", "true", "sim", "yes")


# --------------------------------------------------------------------------- #
# Credenciais do Smart
# --------------------------------------------------------------------------- #
# O usuario precisa de acesso a Financeiro > CNAB > Processar Retorno.
EMAIL = _s("RETORNO_EMAIL", "")
SENHA = _s("RETORNO_SENHA", "")

# --------------------------------------------------------------------------- #
# Chrome / display - ISOLADOS dos demais robos
# --------------------------------------------------------------------------- #
USER_DATA_DIR = _s("USER_DATA_DIR_RET", "/app/data/robo_retorno/perfil_chrome")
HEADLESS = _b("HEADLESS_RET", "False")
CDP_PORT = int(_s("CDP_PORT_RET", "9225"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"   # IPv4 explicito: 'localhost' vira ::1
# Var PROPRIA, nunca `DISPLAY`: o compose define DISPLAY=:99 (boletos) para todo
# processo do container, e ler a var pura poe este Chrome em cima do deles.
DISPLAY = _s("DISPLAY_RET", ":95")

# --------------------------------------------------------------------------- #
# Smart
# --------------------------------------------------------------------------- #
SMART_HOST = _s("SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
SMART_BASE = SMART_HOST + "/smart"
URL_LOGIN = _s("URL_LOGIN", "https://www.smartsecurities.com.br/smartsecurities/")
URL_PROCESSAR_RETORNO = SMART_BASE + "/financeiro/retornoocorrencia.php"
# Ping = a PROPRIA tela do robo. Assim "logado" quer dizer "alcanca a tela";
# usuario sem permissao no CNAB falha cedo, com mensagem clara.
URL_PING = _s("URL_PING_RET", URL_PROCESSAR_RETORNO)

# --------------------------------------------------------------------------- #
# Seguranca
# --------------------------------------------------------------------------- #
# DRY_RUN=True vai ate o UPLOAD (valida banco/conta, monta a grade, conta os
# titulos) e PARA antes do PROCESSAR_ARQUIVO, que e quem da a baixa.
DRY_RUN = _b("DRY_RUN_RET", "True")
# A tela PERGUNTA quando o retorno nao casa com conta cadastrada. Sem gente para
# decidir, o padrao e pular e reportar.
ACEITAR_CONTA_DESCONHECIDA = _b("ACEITAR_CONTA_DESCONHECIDA_RET", "False")

# PORTAO: confere a grade do upload ANTES do PROCESSAR_ARQUIVO e recusa o
# arquivo quando o titulo que o Smart resolveu discorda do que o arquivo mandou
# — o modo de falha do BUG-548 (baixa no titulo de outro sacado).
#
# ⛔ PADRAO DESLIGADO, e de proposito. `src/` deste projeto e BIND-MOUNT: salvar
# publica na hora, e o `processar_retornos_cnab` roda de hora em hora com
# DRY_RUN_RET=false, dando baixa de verdade. Ligar o portao MUDA o
# comportamento desse job — e ato do dono, nao efeito colateral de um commit.
#
# Medido antes de propor (`portao.py` guarda os numeros): sobre 1.238 titulos
# reais de banco, o criterio padrao recusaria ZERO. Ligar `PORTAO_STATUS_OK_RET`
# alem dele recusaria 5 arquivos por `Data de vencimento diferente`, que e
# liquidacao legitima — por isso sao duas chaves, e nao uma.
PORTAO = _b("PORTAO_RET", "False")
PORTAO_STATUS_OK = _b("PORTAO_STATUS_OK_RET", "False")

# --------------------------------------------------------------------------- #
# Pastas
# --------------------------------------------------------------------------- #
# Onde chegam os .RET a processar. O Financeiro larga os arquivos AQUI, soltos
# (o robo nao desce um nivel — subpasta e ignorada, e e por isso que a pasta de
# arquivo processado pode morar dentro dela sem atrapalhar).
PASTA_ENTRADA = _s("PASTA_ENTRADA_RET", "/app/data/retornos_a_processar")

# Depois de PROCESSAR DE VERDADE, o arquivo sai da entrada e vai para
# `_PROCESSADOS/<AAAA-MM>/`. Sem isso a pasta so cresce e cada rodada rele tudo
# de novo — em duas semanas sao centenas de arquivos e a rodada leva 20 min
# relendo coisa velha. Mesmo desenho do `organizar_remessas`, que move em vez de
# reler. Falha NAO move: fica na entrada, visivel, e a proxima rodada tenta de
# novo.
PASTA_PROCESSADOS = _s("PASTA_PROCESSADOS_RET",
                       os.path.join(PASTA_ENTRADA, "_PROCESSADOS"))
MOVER_PROCESSADOS = _b("MOVER_PROCESSADOS_RET", "True")
# Controle de idempotencia. A identidade do arquivo e o MD5 do CONTEUDO, nunca o
# nome: chega arquivo com o mesmo nome no mesmo dia e conteudo diferente, e ele
# TEM que ser processado como novo (o Smart so compara nome e diria "ja
# processado"). Fica em data/, que sobrevive a recriacao do container.
ARQ_CONTROLE = _s("ARQ_CONTROLE_RET", "/app/data/robo_retorno/controle_processados.csv")
# Fase 2 de docs/PLANO_CONTROLE_NO_BANCO.md: de onde vem o "ja processei". `csv`
# (padrao) le o controle acima; `banco` le erp_automation.vw_controle_retorno (e o wrapper
# le a lista de md5 do banco na descoberta) e, sem banco, volta ao CSV avisando. O CSV e
# escrito nos dois modos ate o corte (Fase 4).
CONTROLE_FONTE = _s("CONTROLE_FONTE_RET", _s("CONTROLE_FONTE", "csv")).strip().lower()
DEBUG_DIR = _s("DEBUG_DIR_RET", "/app/data/robo_retorno/debug")
PAUSA_ENTRE_ARQUIVOS = float(_s("PAUSA_ENTRE_ARQUIVOS_RET", "1.0"))


def ensure_dirs() -> None:
    """Cria as pastas de trabalho. Idempotente."""
    for d in (USER_DATA_DIR, PASTA_ENTRADA, DEBUG_DIR,
              os.path.dirname(ARQ_CONTROLE) or "."):
        os.makedirs(d, exist_ok=True)
