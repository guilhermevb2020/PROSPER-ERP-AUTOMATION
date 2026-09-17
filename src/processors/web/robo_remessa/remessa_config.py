# -*- coding: utf-8 -*-
"""
remessa_config.py - configuracao do robo de REMESSA CNAB no container.

Portado do pacote `robo4_remessa` que rodava no Windows com login manual. As
mudancas para o servidor, todas por env (nada de caminho de Windows no fonte):

  - PASTA_REMESSAS  -> bind-mount do host (o Financeiro le direto de la)
  - USER_DATA_DIR   -> perfil proprio em /app/data/robo_remessa (NUNCA o dos
                       boletos/doc2you/credito: 2 Chromes no mesmo perfil brigam
                       pelo lock e um dos dois nao sobe)
  - CDP_PORT 9224   -> 9222=boletos, 9223=doc2you, 9224=remessa (o robo de
                       credito usa remote-debugging-pipe, sem porta)
  - DISPLAY :97     -> :99=boletos, :98=doc2you, :96=credito, :97=remessa

Credenciais: `config/robo_remessa.env` (montado, fora do git). NUNCA no fonte —
este repo tem remote publico. Ver `robo_remessa.example.env`.
"""
import os

_AQUI = os.path.dirname(os.path.abspath(__file__))

# Credenciais/flags do robo. `load_dotenv` NAO sobrescreve o que ja veio do
# ambiente, entao `docker exec -e` continua tendo precedencia sobre o arquivo.
try:
    from dotenv import load_dotenv

    load_dotenv(os.environ.get("REMESSA_ENV_FILE", "/app/config/robo_remessa.env"))
except ImportError:
    pass


def _s(chave: str, padrao: str) -> str:
    return os.environ.get(chave, padrao)


def _b(chave: str, padrao: str) -> bool:
    return _s(chave, padrao).strip().lower() in ("1", "true", "sim", "yes")


# --------------------------------------------------------------------------- #
# Credenciais do Smart
# --------------------------------------------------------------------------- #
# ATENCAO: o usuario precisa de acesso as telas Financeiro > CNAB (Gerar Remessa
# e Download de Remessa) E as contas que serao percorridas. Nao e o mesmo perfil
# dos boletos (`envioboletos`) nem necessariamente o do doc2you (`Raphaelas`).
EMAIL = _s("REMESSA_EMAIL", "")
SENHA = _s("REMESSA_SENHA", "")


def exigir_credenciais() -> None:
    """Falha alto e cedo se a credencial nao carregou.

    Chamado pelo fluxo de login, nao no import: os modos read-only (--contas,
    --listar sobre uma sessao ja viva) nao precisam de senha.
    """
    faltando = [n for n, v in (("REMESSA_EMAIL", EMAIL), ("REMESSA_SENHA", SENHA))
                if not v.strip()]
    if faltando:
        raise RuntimeError(
            f"Credencial ausente: {', '.join(faltando)}. Defina em "
            "/app/config/robo_remessa.env (fora do git) ou no ambiente do container.")


# --------------------------------------------------------------------------- #
# Chrome / display - ISOLADOS dos demais robos do container
# --------------------------------------------------------------------------- #
USER_DATA_DIR = _s("USER_DATA_DIR_REM", "/app/data/robo_remessa/perfil_chrome")
HEADLESS = _b("HEADLESS_REM", "False")   # False: pinta no Xvfb :97 (VNC de debug)
CDP_PORT = int(_s("CDP_PORT_REM", "9224"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"   # IPv4 explicito: 'localhost' resolve
                                           # p/ ::1 e o Chrome so escuta em IPv4
# Var PROPRIA, e nao a `DISPLAY` do container. O compose define DISPLAY=:99
# (boletos) para todo processo; se lessemos `DISPLAY`, um `docker exec` sem
# `-e` subiria o nosso Chrome EM CIMA do dos boletos — dois Chromes no mesmo
# display fazem o login "quicar" de volta para a landing (foi o que custou dias
# no doc2you, e a razao de cada robo daqui ter o seu). `_sessao.abrir_propria`
# publica este valor em os.environ["DISPLAY"] antes de subir o Chrome.
DISPLAY = _s("DISPLAY_REM", ":97")

# --------------------------------------------------------------------------- #
# Smart
# --------------------------------------------------------------------------- #
SMART_HOST = _s("SMART_HOST", "https://wvw.smartsecurities.com.br").rstrip("/")
SMART_BASE = SMART_HOST + "/smart"
URL_LOGIN = _s("URL_LOGIN", "https://www.smartsecurities.com.br/smartsecurities/")

# Tela de DOWNLOAD DE REMESSA: lista as remessas ja geradas por conta + periodo.
# (NAO confundir com downloadremessamulticedente.php, que e so de conta escrow e
#  volta vazia para as remessas normais.)
URL_DOWNLOAD_REMESSA = SMART_BASE + "/financeiro/downloadremessa.php"
URL_GERAR_REMESSA = SMART_BASE + "/financeiro/remessaocorrencia.php"

# Ping de sessao. Aponta para a PROPRIA tela de remessa de proposito: assim
# "logado" quer dizer "alcanca a tela que o robo precisa", e nao apenas "existe
# um cookie". Usuario sem permissao no CNAB falha aqui, cedo e com mensagem
# clara, em vez de virar "nenhuma conta com remessa" la na frente.
URL_PING = _s("URL_PING_REM", URL_DOWNLOAD_REMESSA)

# --------------------------------------------------------------------------- #
# Escopo da geracao
# --------------------------------------------------------------------------- #
# DRY_RUN=True: monta o POST, loga o que faria e NAO gera nada no Smart.
# Default TRUE de proposito - gerar consome sequencial e tira titulo da fila.
DRY_RUN = _b("DRY_RUN_REM", "True")
CONTA_PADRAO = _s("CONTA_REMESSA", "291")
CARTEIRA_PADRAO = _s("CARTEIRA_REMESSA", "9")
DIAS_PADRAO = int(_s("DIAS_REMESSA", "7"))
# Prefixo das contas percorridas por --todas-contas (as contas 'mp *' sao as de
# cobranca registrada; 'Banco do Brasil*' tem outro fluxo).
PREFIXO_CONTAS = _s("PREFIXO_CONTAS_REM", "mp ")

# --------------------------------------------------------------------------- #
# Pastas
# --------------------------------------------------------------------------- #
# Destino dos .REM. No compose isto e um bind-mount do host:
#   /home/prospere/docker/automation/process-automation/tmp/remessas a enviar
PASTA_REMESSAS = _s("PASTA_REMESSAS", "/app/data/remessas_a_enviar")
# Alem do disco, sobe cada .REM para o Nextcloud — e la que o Financeiro
# enxerga: a PASTA_REMESSAS acima nao esta em share nenhum (nem Nextcloud nem
# Samba), so quem tem acesso ao servidor a alcanca. Destino e convencao de
# caminho ficam em `_nextcloud.py`; aqui so o interruptor.
# `ENVIAR_NEXTCLOUD_REM=false` desliga sem tocar no codigo — licao do BUG-566,
# em que caminho fixo no fonte fez 67 arquivos sumirem em silencio quando a
# arvore do Nextcloud mudou.
ENVIAR_NEXTCLOUD = _b("ENVIAR_NEXTCLOUD_REM", "True")
# Controle de idempotencia (id/arquivo/md5). Fica no volume ./data, que
# sobrevive a recriacao do container.
ARQ_CONTROLE = _s("ARQ_CONTROLE", "/app/data/robo_remessa/controle_remessas.csv")
# Lista de EXCLUSAO da geracao, escrita pelo process-automation
# (`apontar_exclusoes_remessa_400`, dia util 17:30) no bind compartilhado
# `data/retornos_a_processar`: titulos abertos de sacado cujo endereco sai SEM
# numero do pagador no CNAB 400 — o MoneyPlus recusa o arquivo INTEIRO por um so
# (09/09/2026: 166 titulos; 17/09: 175). O robo desmarca esses e o resto passa.
# Lista mais velha que a validade declarada nela e ignorada, com aviso.
ARQ_EXCLUSOES = _s("ARQ_EXCLUSOES_REM",
                   "/app/data/retornos_a_processar/remessa_cnab_400/exclusoes.json")
DEBUG_DIR = _s("DEBUG_DIR_REM", "/app/data/robo_remessa/debug")

# Segundos entre pings de keep-alive quando o robo roda em modo sessao viva.
PING_INTERVALO_S = int(_s("PING_INTERVALO_S_REM", "120"))


def ensure_dirs() -> None:
    """Cria as pastas de trabalho. Idempotente."""
    for d in (USER_DATA_DIR, PASTA_REMESSAS, DEBUG_DIR,
              os.path.dirname(ARQ_CONTROLE) or "."):
        os.makedirs(d, exist_ok=True)
