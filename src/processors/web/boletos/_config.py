# -*- coding: utf-8 -*-
"""
Config dos TESTES de migracao do robo de boletos para o servidor.

Versao adaptada do boleto_config.py local. Mudancas para o container:
- Paths absolutos dentro de /app/data/boletos (perfil, debug, log).
- Defaults conservadores: DRY_RUN=True, SCAN=True, HEADLESS=False
  (precisa de display Xvfb p/ renderizar; quando estabilizar, ligamos
   headless real depois).
- Credenciais vem de config/boletos.env (fora do git) ou do ambiente do
  `docker exec` — nunca do fonte. Ver `exigir_credenciais()`.
"""

import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Este repo tem remote publico; credencial nao mora no fonte. Mesmo padrao ja
# usado por config/nextcloud.env e config/robo_credito.env. `load_dotenv` NAO
# sobrescreve o que ja veio do `docker exec`, entao a env explicita continua
# tendo precedencia sobre o arquivo.
ENV_FILE = os.environ.get("BOLETO_ENV_FILE", "/app/config/boletos.env")
load_dotenv(ENV_FILE)


def _s(chave: str, padrao: str) -> str:
    return os.environ.get(chave, padrao)


def _b(chave: str, padrao: str) -> bool:
    return _s(chave, padrao).strip().lower() in ("1", "true", "sim", "yes")


# --------------------------------------------------------------------------- #
# Paths persistentes (volume Docker /app/data)
# --------------------------------------------------------------------------- #
BASE_DATA = Path("/app/data/boletos")
USER_DATA_DIR = str(BASE_DATA / "perfil_chrome")
DEBUG_DIR = str(BASE_DATA / "debug")
LOG_DIR = str(BASE_DATA / "logs")
TEMPLATES_DIR = Path(__file__).parent / "templates"
T_LISTA_PATH = str(TEMPLATES_DIR / "listatitulos.txt")
T_ENVIO_PATH = str(TEMPLATES_DIR / "envio.txt")

# --------------------------------------------------------------------------- #
# Credenciais
# --------------------------------------------------------------------------- #
EMAIL = _s("BOLETO_EMAIL", "")
SENHA = _s("BOLETO_SENHA", "")
EMPRESA = _s("BOLETO_EMPRESA", "PROSPER VETOR SECURITIZADORA S.A.")


def exigir_credenciais() -> None:
    """Falha alto se as credenciais nao carregaram.

    Chamado pelos fluxos de LOGIN, nao no import: o healthcheck precisa
    conseguir subir e reportar `chrome_down` mesmo sem credencial na mao.
    """
    faltando = [n for n, v in (("BOLETO_EMAIL", EMAIL), ("BOLETO_SENHA", SENHA)) if not v.strip()]
    if faltando:
        raise RuntimeError(
            f"Credencial ausente: {', '.join(faltando)}. "
            f"Defina em {ENV_FILE} (fora do git) ou no ambiente do container."
        )

# --------------------------------------------------------------------------- #
# Flags de seguranca (defaults SEGUROS)
# --------------------------------------------------------------------------- #
# DRY_RUN: True = preenche o form e PARA antes de Pesquisar/Gerar/Enviar.
DRY_RUN = _b("DRY_RUN", "true")
# SCAN:   gera lista de boletos do dia para CONTAR titulos, mas NAO envia.
#         Util como "preview" sem clicar Enviar. Tem prioridade sobre DRY_RUN.
SCAN = _b("SCAN", "true")
# DEBUG: ativa screenshots em DEBUG_DIR
DEBUG = _b("DEBUG", "true")
# HEADLESS: false enquanto estamos testando (precisa Xvfb p/ pintar)
HEADLESS = _b("HEADLESS", "false")

# --------------------------------------------------------------------------- #
# Filtros operacionais (uteis em teste)
# --------------------------------------------------------------------------- #
MAX_CONTAS = int(_s("MAX_CONTAS", "0"))
CONTAS_IGNORAR = [c.strip().lower() for c in _s("CONTAS_IGNORAR", "").split(";") if c.strip()]
SO_TIPO_CONTA = _s("SO_TIPO_CONTA", "").strip().lower()  # padrao | mp | ""
SO_CONTA = _s("SO_CONTA", "").strip().lower()             # rotulo exato

# --------------------------------------------------------------------------- #
# Data alvo
# --------------------------------------------------------------------------- #
FERIADOS = set(d.strip() for d in _s("FERIADOS", "").split(";") if d.strip())
FORMATO_DATA = _s("FORMATO_DATA", "%Y-%m-%d")
DATA_FIXA = _s("DATA_FIXA", "").strip()


def ultimo_dia_util(ref: date = None) -> date:
    d = (ref or date.today()) - timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in FERIADOS:
        d -= timedelta(days=1)
    return d


def data_alvo() -> date:
    if DATA_FIXA:
        return date.fromisoformat(DATA_FIXA)
    return ultimo_dia_util()


def data_alvo_str() -> str:
    return data_alvo().strftime(FORMATO_DATA)


# --------------------------------------------------------------------------- #
# URLs
# --------------------------------------------------------------------------- #
URL_LOGIN = _s("URL_LOGIN", "https://www.smartsecurities.com.br/smartsecurities/")
URL_BOLETO = _s(
    "URL_BOLETO",
    "https://wvw.smartsecurities.com.br/smart/financeiro/frmimpriboleto.php?Via=1",
)
URL_SESSAO = _s("URL_SESSAO", URL_BOLETO)
URL_PAINEL = _s("URL_PAINEL", "https://wvw.smartsecurities.com.br/smart/smartsecurities.php")
URL_FORM_HTTP = _s("URL_FORM_HTTP", "https://wvw.smartsecurities.com.br/smart/financeiro/impriboleto.php?Via=2")
URL_LISTA_HTTP = _s("URL_LISTA_HTTP", "https://wvw.smartsecurities.com.br/smart/financeiro/listatitulosboletos.php")
URL_ENVIO_HTTP = _s("URL_ENVIO_HTTP", "https://wvw.smartsecurities.com.br/smart/financeiro/cobranca/printcobrancapdf.php")

# --------------------------------------------------------------------------- #
# Seletores
# --------------------------------------------------------------------------- #
SEL_LOGIN_EMAIL = "#fEmail"
SEL_LOGIN_SENHA = "input[type='password']"
SEL_LOGIN_ENTRAR = "#OK"
SEL_RECAPTCHA_ANCHOR = "#recaptcha-anchor"
SEL_ACESSAR = "#OKExtra"
SEL_ACESSAR_EMPRESA = "a:has-text('Acessar'), button:has-text('Acessar'), input[value='Acessar']"

SEL_CONTA = "select[name='contaCorrente']"
SEL_CONTA_FALLBACK = "select:has(option:has-text('Selecione a conta'))"
SEL_MODALIDADE = "select[name='modalidadeS']"
MODALIDADE_VALOR = _s("MODALIDADE_VALOR", "C")

CONTAS_PLACEHOLDER = ["selecione a conta", "tÃ­tulos sem conta", "titulos sem conta"]
SEL_DATA_INICIAL = "#DtInicial, input[name='DtInicial']"
SEL_DATA_FINAL = "#DtFinal, input[name='DtFinal']"
SEL_BTN_PESQUISAR = "button:has-text('Pesquisar'), input[value='Pesquisar']"
SEL_BTN_GERAR_BOLETO = "button:has-text('Gerar boleto'), input[value='Gerar boleto']"

SEL_CLASSE_RISCO = "input[name='sClasseRisco[]']"
CLASSES_PADRAO = [c.strip() for c in _s("CLASSES_PADRAO", "P;T;CL").split(";") if c.strip()]
CLASSES_MP = [c.strip() for c in _s("CLASSES_MP", "P;T;E;B;I;BG;CL").split(";") if c.strip()]
PREFIXO_MP = "mp "

MENU_BOLETO_PAI = "Imprimir ou Enviar boletos"
MENU_BOLETO_ITEM = "2Âª Via de Boleto"
SEL_CHK_TODOS_EMAIL = "input[name='cSelecionarTodosEmail']"
SEL_BTN_ENVIAR_EMAIL = "button:has-text('Enviar por e-mail'), input[value='Enviar por e-mail']"
URL_POPUP_EMAIL_FRAG = "popupenviaremailboleto.php"
SEL_BTN_ENVIAR_POPUP = "button:has-text('Enviar'), input[value='Enviar']"

REMETENTE = _s("REMETENTE", "primario").strip().lower()
_MAP_REMETENTE = {
    "usuario": "#smtpUsuario", "primario": "#smtpPrimario",
    "secundario": "#smtpSecundario", "terciario": "#smtpTerciario",
}
SEL_REMETENTE = _MAP_REMETENTE.get(REMETENTE, "#smtpPrimario")

# --------------------------------------------------------------------------- #
# Tempos / portas
# --------------------------------------------------------------------------- #
WAIT_POS_LOGIN = int(_s("WAIT_POS_LOGIN", "8"))
WAIT_POS_ACAO = int(_s("WAIT_POS_ACAO", "4"))
WAIT_CONFIRMA_ENVIO = int(_s("WAIT_CONFIRMA_ENVIO", "30"))

PAUSA_ENTRE_CONTAS = int(_s("PAUSA_ENTRE_CONTAS", "8"))
TIMEOUT_ENVIO_MS = int(_s("TIMEOUT_ENVIO", "600")) * 1000
TETO = int(_s("TETO", "800"))

CDP_PORT = int(_s("CDP_PORT", "9222"))
CDP_URL = _s("CDP_URL", f"http://127.0.0.1:{CDP_PORT}")
DISPLAY = _s("DISPLAY", ":99")


def ensure_dirs():
    for d in (USER_DATA_DIR, DEBUG_DIR, LOG_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)
