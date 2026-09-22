"""
Configuracoes e seletores do robo de analise de credito.

Todos os seletores aqui foram extraidos do "Control Repository" do fluxo
original do Power Automate Desktop (arquivo "robo analise de credito.txt").
Mantê-los centralizados facilita ajustar caso a tela do Smart Securities mude.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# Credenciais e ambiente (lidos do .env)
# --------------------------------------------------------------------------- #
def _bool(nome: str, padrao: str) -> bool:
    return os.getenv(nome, padrao).strip().lower() in ("1", "true", "yes", "sim")


EMAIL = os.getenv("SMART_EMAIL", "")
SENHA = os.getenv("SMART_SENHA", "")
USER_DATA_DIR = os.getenv("USER_DATA_DIR", ".perfil_chrome")
HEADLESS = _bool("HEADLESS", "False")

# DRY_RUN=True faz login/navegacao/extracao mas NAO clica em Salvar nem muda
# status (nao altera dados de producao). Ideal para validar seletores.
DRY_RUN = _bool("DRY_RUN", "False")

# DEBUG=True salva screenshot + HTML da tela de consulta apos a pesquisa,
# para diagnosticar layout/seletores. Saida em DEBUG_DIR.
DEBUG = _bool("DEBUG", "False")
DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")

# SKIP_DIGITAIS=True pula o sub-fluxo DIGITAIS VM (ainda em ajuste).
SKIP_DIGITAIS = _bool("SKIP_DIGITAIS", "False")
# SKIP_ANALISE_HOME=True pula o processamento "Análise Home -> Feedback ROB"
# (o select #etapaOperacao vem disabled em Análise Home; em investigacao).
SKIP_ANALISE_HOME = _bool("SKIP_ANALISE_HOME", "False")

# --------------------------------------------------------------------------- #
# URLs (linhas 8, 22, 53, 76/79 do fluxo original)
# Obs.: o fluxo usa tanto "wvw" quanto "www" no dominio (provavelmente espelho
# interno). Mantidos exatamente como no original.
# --------------------------------------------------------------------------- #
URL_BOLETO = "https://wvw.smartsecurities.com.br/smart/financeiro/frmimpriboleto.php?Via=1"
URL_LOGIN = "https://www.smartsecurities.com.br/smartsecurities/"
URL_CONSULTA = "https://wvw.smartsecurities.com.br/smart/operacao/frmconoperacao.php"
# %op% e substituido pelo numero da operacao extraido (DataFromWebPage2)
URL_EDITAR = "https://wvw.smartsecurities.com.br/smart/operacaoajax/web/novatelaoperacao.php?action=edit&op={op}"

# --------------------------------------------------------------------------- #
# Seletores (extraidos do Control Repository do PAD)
# --------------------------------------------------------------------------- #
# Tela de login -> conteudo dentro de um <iframe> (body#bodyindexsistema)
SEL_LOGIN_EMAIL = "#fEmail"                 # Input text 'fEmail'
SEL_LOGIN_SENHA = "input[type='password']"  # campo seguinte (alcancado via Tab no PAD)
SEL_LOGIN_ENTRAR = "#OK"                     # Button 'Entrar' (type=submit)
SEL_RECAPTCHA_ANCHOR = "#recaptcha-anchor"   # Check Box 'Não sou um robô' (iframe reCAPTCHA)
SEL_ACESSAR = "#OKExtra"                      # Button 'Acessar'

# Tela de consulta de operacao -> dentro de iframe[name=stage] + frameset#framesetOperacao
# IMPORTANTE: clicar no ICONE <i> dentro do botao (clicar no botao inteiro
# trocava para o layout errado).
SEL_TROCAR_LAYOUT = "#btn_modificar_layout_operacao > i"  # icone do 'Trocar layout'

# Tipo de consulta (radios no topo). Operacoes podem ser de QUALQUER um dos
# dois tipos -> a busca tenta os dois (igual o PAD alterna rTipo).
SEL_RADIO_TIPO_HOME = "#rTipoH"    # Home-Securities (value S)
SEL_RADIO_TIPO_SMART = "#rTipoO"   # SmartSecurities (value O)
SEL_RADIO_TIPO = "#rTipoH"                  # Input radio 'rTipo'
SEL_RADIO_PESQUISA = "#rPesquisaEtapa"      # Input radio 'rPesquisa'
SEL_PESQUISAR = "#Pesquisar"                # Button 'Pesquisar'

# Filtro de ETAPA da consulta (id real: fEtapaOperacao). O PAD seleciona
# "Análise Home" antes de pesquisar para so trazer operacoes nessa etapa.
SEL_FILTRO_ETAPA = "#fEtapaOperacao"
OPCAO_STATUS_CONSULTA = "Análise Home"      # rotulo da opcao
VALOR_ETAPA_ANALISE_HOME = "10"             # value="10" -> Análise Home
# Valores das demais etapas (do <select id=fEtapaOperacao>), para referencia:
#   0 Todas as etapas | 9 Home | 10 Análise Home | 1 Nova |
#   18 Feedback Analise ROB | 2 Análise de crédito | 3 Confirmação de títulos |
#   14 C/ Critica | 13 S/ Critica -Recompra | 16 Enviar Digitais |
#   15 Aguardando Ass. | 11 Programada | 8 Concluída
VALOR_ETAPA_FEEDBACK_ROB = "18"             # value="18" -> Feedback Analise ROB
VALOR_ETAPA_ANALISE_CREDITO = "2"           # value="2"  -> Análise de crédito
VALOR_ETAPA_ENVIAR_DIGITAIS = "16"          # value="16" -> Enviar Digitais
VALOR_ETAPA_AGUARDANDO_ASS = "15"           # value="15" -> Aguardando Ass.

# --------------------------------------------------------------------------- #
# Endpoints de PDF (descobertos por investigacao) - download direto via HTTP
# (substitui o "imprimir + dialogo Salvar como" com coordenadas de mouse do PAD)
# --------------------------------------------------------------------------- #
URL_NF_PDF = "https://wvw.smartsecurities.com.br/smart/operacaoajax/web/gerardanfes.php?NumOperacao={op}"
URL_RESUMO_POST = "https://wvw.smartsecurities.com.br/smart/popup/popuprelatoriopreanalise.php?numOp={op}"

# Pastas de saida LOCAIS (staging/fallback; no servidor aponte p/ um dir do
# container, ex.: /tmp/credito/nfe). So usadas se o upload p/ Nextcloud
# estiver desligado ou falhar (fail-safe: nunca perder o PDF).
PASTA_NFE = os.getenv("PASTA_NFE", r"C:\ProsperAI\inboxnfe")
PASTA_RESUMO = os.getenv("PASTA_RESUMO", r"C:\ProsperAI\inbox")

# Destino FINAL = Nextcloud via WebDAV (groupfolder CADASTRO), igual ao doc2you.
#   NF     -> DEST_BASE/nf operacao/NFE<op>.pdf
#   Resumo -> DEST_BASE/resumo da operacao/resumo<op>.pdf
# DEST_BASE/credenciais ficam em _nextcloud.py (reusa /app/config/nextcloud.env).
SALVAR_NEXTCLOUD = _bool("SALVAR_NEXTCLOUD", "True")
NC_SUBPASTA_NF = os.getenv("NC_SUBPASTA_NF", "nf operacao")
NC_SUBPASTA_RESUMO = os.getenv("NC_SUBPASTA_RESUMO", "resumo da operacao")
# Documentos complementares (aba "Outros documentos" da op): vao p/ uma SUBPASTA
# POR OPERACAO -> DEST_BASE/documentos complementares operacoes/<numero_op>/<doc>
NC_SUBPASTA_COMPLEMENTARES = os.getenv(
    "NC_SUBPASTA_COMPLEMENTARES", "documentos complementares operacoes")
# numFactoring fixo observado no form do resumo (PROSPER VETOR = 3912)
NUM_FACTORING = os.getenv("NUM_FACTORING", "3912")

# --------------------------------------------------------------------------- #
# Banco de dados (PostgreSQL) - societario p/ conferencia V3 (NAO p/ descoberta)
# --------------------------------------------------------------------------- #
# FONTE DOS OPS = SMART (raspagem da UI), nao o banco. Motivo (validado 2026-06-25):
# trs.operacao_desagio NAO sincroniza a SAIDA da etapa - quando uma op e
# rejeitada/avanca, ela CONTINUA aparecendo na etapa antiga no banco. Ex.: o
# banco listava 30 ops em "FEEDBACK ANALISE ROB" e 160 em "Análise de crédito",
# enquanto o Smart ao vivo tinha 0 e 1, respectivamente. Descobrir ops pelo banco
# pega esses "fantasmas" e tenta baixar resumo de ops antigas -> expira.php.
# Por isso USAR_BANCO_DOWNLOAD=False: o sub-fluxo BAIXAR NF/RESUMO raspa a tela de
# consulta (listar_operacoes_etapa), igual ao loop principal e ao PAD original -
# assim so processa os ops que o robo ACABOU de mover p/ "Feedback ROB" (recentes,
# com resumo disponivel). O banco abaixo so e usado p/ o quadro societario (V3).
USAR_BANCO_DOWNLOAD = _bool("USAR_BANCO_DOWNLOAD", "False")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.50.5"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "dev_user"),
    "password": os.getenv("DB_PASSWORD", ""),  # sem default: senha vem SO do env
    "dbname": os.getenv("DB_NAME", "prosperedb"),
}
# timeout curto: VPN fora -> falha rapido e cai no fallback (nao trava o ciclo)
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
TABELA_OPERACOES = os.getenv("TABELA_OPERACOES", "trs.operacao_desagio")
# Valor da coluna 'etapa' no banco (MAIUSCULO e SEM acento - diferente do
# rotulo do Smart "Feedback Analise ROB").
ETAPA_DB_FEEDBACK_ROB = os.getenv("ETAPA_DB_FEEDBACK_ROB", "FEEDBACK ANALISE ROB")
# --------------------------------------------------------------------------- #
# Estado LOCAL do robo — mora em data/, nao junto do codigo
#
# Ate 12/08/2026 estes arquivos ficavam dentro de src/processors/web/credito/,
# isto e: estado de execucao dentro da arvore de fonte. Os outros robos deste repo
# (remessa, retorno) sempre gravaram em /app/data/<robo>/.
#
# A resolucao abaixo e deliberadamente tolerante, para que a troca seja um simples
# `cp` sem NENHUMA janela em que o robo leia um controle vazio e re-baixe tudo:
#
#   ja esta em data/          -> usa data/
#   nao esta em lugar nenhum  -> usa data/  (instalacao nova ja nasce certa)
#   so existe no local antigo -> usa o antigo, ate a migracao rodar
#
# Sempre UM caminho so, para leitura e escrita — nunca os dois ao mesmo tempo.
#
# ⚠️ O diretorio e criado aqui de proposito: `_salvar_controle()` (banco.py)
# reescreve o arquivo INTEIRO a cada gravacao e engole erro de escrita num print.
# Se o diretorio faltasse, o robo perderia o controle do run em silencio.
# --------------------------------------------------------------------------- #
_DIR_ROBO = os.path.dirname(os.path.abspath(__file__))
_DIR_ESTADO = os.getenv("DIR_ESTADO_ROBO_CREDITO", "/app/data/robo_credito")


def _arquivo_estado(nome: str) -> str:
    novo = os.path.join(_DIR_ESTADO, nome)
    antigo = os.path.join(_DIR_ROBO, nome)
    if os.path.exists(novo) or not os.path.exists(antigo):
        try:
            os.makedirs(_DIR_ESTADO, exist_ok=True)
        except OSError:
            return antigo          # data/ nao gravavel -> nao muda nada
        return novo
    return antigo


# Controle dos downloads ja feitos (1 linha por operacao). Evita rebaixar e
# permite retentar so a troca de etapa sem rebaixar.
ARQ_CONTROLE_DOWNLOAD = (
    os.getenv("ARQ_CONTROLE_DOWNLOAD") or _arquivo_estado("controle_downloads.csv"))
# Move robusto: maximo de ciclos consecutivos tentando mover uma op que NAO sai
# da fila de Feedback ROB. Apos isso a op vai p/ ops_move_revisar_manual.txt e o
# robo PARA de tentar (evita loop quando o move "verifica OK" mas a op nao sai
# da fila de verdade). 0 = nunca desiste.
MAX_TENTATIVAS_MOVE = int(os.getenv("MAX_TENTATIVAS_MOVE", "5"))
ARQ_MOVE_REVISAR = _arquivo_estado("ops_move_revisar_manual.txt")

# XPath/CSS exato usado no PAD (linha 72) para extrair o numero da operacao
# da tabela de resultados.
XPATH_NUMERO_OPERACAO = (
    "html > body > div > div > main > iframe > html > frameset > frame:eq(1) > "
    "html > body > div:eq(0) > div > form > div:eq(5) > div > table > tbody > "
    "tr > td:eq(2)"
)
# Equivalente em CSS para Playwright (frame:eq(1) e tratado via troca de frame):
CSS_NUMERO_OPERACAO = (
    "div:nth-of-type(1) > div > form > div:nth-of-type(6) > div > table > tbody "
    "> tr > td:nth-of-type(3)"
)

# Tela de edicao da operacao
SEL_SALVAR = "#SalvarOperacaoButton"        # Button 'SalvarOperacaoButton'
# Select de STATUS/ETAPA na tela de EDICAO (id real: etapaOperacao).
# ATENCAO: e diferente do filtro da consulta (#fEtapaOperacao)! Aqui a selecao
# e feita pela LABEL (texto da opcao), nao pelo value.
SEL_STATUS_EDICAO = "#etapaOperacao"
OPCAO_STATUS_FEEDBACK = "Feedback Analise ROB"   # label
ROTULO_ANALISE_CREDITO = "Análise de crédito"    # label
ROTULO_AGUARDANDO_ASS = "Aguardando Ass."        # label

# --------------------------------------------------------------------------- #
# Limites dos loops (iguais ao fluxo original) e tempos de espera (segundos)
# --------------------------------------------------------------------------- #
# Valores originais do PAD; podem ser reduzidos via .env para testes controlados.
# MAX_REINICIOS=0 => LOOP INFINITO. A JANELA de operacao (abaixo) faz o robo
# encerrar sozinho no fim do expediente. >0 limita reinicios (util em teste).
MAX_REINICIOS = int(os.getenv("MAX_REINICIOS", "0"))         # 0 = infinito

# Janela de operacao em horario de BRASILIA (BRT = -3 fixo, sem horario de verao).
# O hub INICIA o robo via cron (7:45 dias uteis); o robo PARA SOZINHO as 18:50
# (opcao B) checando o horario no inicio de cada ciclo/reinicio. Formato HH:MM.
JANELA_INICIO = os.getenv("JANELA_INICIO", "07:45")
JANELA_FIM = os.getenv("JANELA_FIM", "18:50")

MAX_OPERACOES = int(os.getenv("MAX_OPERACOES", "1000"))      # LOOP LoopIndex2 1..1000
REPETICOES_INTERNAS = int(os.getenv("REPETICOES_INTERNAS", "2"))  # LOOP LoopIndex3 1..2

# Watchdog (anti-travamento): se um passo ficar > WATCHDOG_MAX_OCIOSO s sem bater o
# heartbeat, mata o Chrome e o main() relanca do ZERO. Deve ser MAIOR que o passo
# legitimo mais longo (conferencia Claude ~300s, DIGITAIS ~120s, login ~120s).
WATCHDOG_MAX_OCIOSO = int(os.getenv("WATCHDOG_MAX_OCIOSO", "360"))
WATCHDOG_CHECAR = int(os.getenv("WATCHDOG_CHECAR", "15"))
# Backoff entre reinicios (cresce com falhas consecutivas, ate o teto).
REINICIO_BACKOFF = int(os.getenv("REINICIO_BACKOFF", "10"))
REINICIO_BACKOFF_MAX = int(os.getenv("REINICIO_BACKOFF_MAX", "60"))

# Esperas (s). Reduzidas vs o PAD original p/ VELOCIDADE; todas tunaveis por env
# (se aparecer flakiness, e so subir a env correspondente sem mexer no codigo).
WAIT_POS_CLEANUP = int(os.getenv("WAIT_POS_CLEANUP", "20"))
WAIT_POS_LOGIN = int(os.getenv("WAIT_POS_LOGIN", "5"))
WAIT_POS_SALVAR = int(os.getenv("WAIT_POS_SALVAR", "3"))            # era 5
WAIT_ENTRE_OPERACOES = int(os.getenv("WAIT_ENTRE_OPERACOES", "12"))  # era 40
# Espera (s) apos clicar "Pesquisar" na consulta, antes de extrair os numeros.
WAIT_POS_PESQUISA = float(os.getenv("WAIT_POS_PESQUISA", "1.5"))     # era 2 fixo
# Espacamento entre a Promissoria e a Duplicata no DIGITAIS via HTTP (segundos):
# da tempo da NPP finalizar/assinar no servidor antes de pedir a Duplicata.
ESPACO_NPP_DUP = int(os.getenv("ESPACO_NPP_DUP", "10"))             # era 15

# IDs dos sub-fluxos externos chamados pelo PAD (External.RunFlow)
FLOW_DIGITAIS_VM = "872977a0-e5eb-f011-8407-6045bd3911ee"
FLOW_BAIXAR_NF = "63615c7c-95cd-41e5-a3cb-1cefcca31e31"
