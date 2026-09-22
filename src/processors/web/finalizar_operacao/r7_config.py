# -*- coding: utf-8 -*-
"""
r7_config.py - configuracao do Robo 7 (FINALIZAR OPERACAO).

Estrategia (mesma dos R3/R4/R5):
  - REUSA as credenciais do R1 (mesmo .env raiz via credito/config.py).
  - PERFIL Chrome PROPRIO (.perfil_chrome_r7) + porta CDP propria (9225), p/ rodar
    EM PARALELO ao R1 (9222)/R3 (9223)/R4 (9224) sem disputar o profile lock.
    LEMBRETE: NUNCA rodar 2 scripts no mesmo CDP ao mesmo tempo - colidem.

O QUE O ROBO 7 FAZ (fila de entrada = etapa "Aguardando Ass."):
  1. checa no doc2you se TODOS os documentos da operacao estao ASSINADOS
     (status "Concluido" - nao basta existir);
  2. checa a FORMA DE PAGAMENTO (grade PIX da tela da operacao);
  3. tudo OK  -> abre "Resumir" e clica em FINALIZAR;
     algo NOK -> NAO finaliza e manda e-mail p/ o operador com o que falta.

Sobrescrever via env (override por run):
  $env:CDP_PORT_R7="9225"; $env:USER_DATA_DIR_R7=".perfil_chrome_r7"
  $env:R7_DRY_RUN="1"       # nunca clica em Finalizar (so confere e avisa)
"""
import os
import sys
from datetime import datetime, time as dt_time

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)

# REUSA o credito do repo em vez de carregar as copias que vieram no pacote
# de origem (regra 3 do CLAUDE.md: nao duplicar o que ja existe). Conferido em
# 02/09/2026: `smart_session.py` e byte a byte identico ao do pacote, e os
# simbolos que este robo consome de `config.py` -- URL_LOGIN, URL_CONSULTA,
# URL_EDITAR, VALOR_ETAPA_AGUARDANDO_ASS -- tem valores IGUAIS nas duas versoes.
# A do repo e mais nova e mais segura (nao carrega senha default no fonte).
#
# `analisar_credito_operacao`, `banco` e `subfluxos` tambem vem dali.
# `classe_risco_tool` e `verificar_docs` nao existiam no repo e por isso moram
# aqui -- candidatos a `src/common/` quando um segundo robo precisar deles.
_CREDITO = os.path.join(_RAIZ, "credito")
for _p in (_AQUI, _CREDITO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config as r1_config  # noqa: E402  -> EMAIL/SENHA/URLs/seletores do credito


def _s(chave: str, padrao: str) -> str:
    return os.environ.get(chave, padrao)


def _b(chave: str, padrao: str) -> bool:
    return _s(chave, padrao).strip().lower() in ("1", "true", "sim", "yes")


# --------------------------------------------------------------------------- #
# Credenciais / sessao
# --------------------------------------------------------------------------- #
# O R7 tem SESSAO PROPRIA (perfil + janela + porta CDP so dele) e faz o proprio
# login - nao depende do robo de credito estar no ar. As credenciais saem do
# MESMO .env da raiz; R7_CONTA escolhe qual:
#   principal -> SMART_EMAIL/SMART_SENHA  (a mesma do R1/R3/R4 - default)
#   op2       -> SMART_EMAIL_OP2/SMART_SENHA_OP2 (conta OPERACIONAL 2)
# ATENCAO: quem finaliza a operacao fica registrado na trilha do Smart com ESTA
# conta. Trocar p/ op2 muda o nome que aparece la.
CONTA = _s("R7_CONTA", "principal").strip().lower()
if CONTA == "op2":
    EMAIL = os.environ.get("SMART_EMAIL_OP2", "") or r1_config.EMAIL
    SENHA = os.environ.get("SMART_SENHA_OP2", "") or r1_config.SENHA
else:
    EMAIL = r1_config.EMAIL
    SENHA = r1_config.SENHA

USER_DATA_DIR = _s("USER_DATA_DIR_R7", ".perfil_chrome_r7")
HEADLESS = _b("HEADLESS_R7", "False")
CDP_PORT = int(_s("CDP_PORT_R7", "9225"))      # R1=9222 R3=9223 R4=9224 R7=9225
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"       # IPv4 explicito (NAO 'localhost')
# Display PROPRIO (Xvfb :92, que o run_agendado.sh sobe). O compose define
# DISPLAY=:99 (boletos) para o container inteiro; o smart_sessao publica este
# antes de abrir o Chrome, para nunca subir em cima do dos boletos.
DISPLAY = _s("DISPLAY_R7", ":92")

PING_INTERVALO_S = int(_s("PING_INTERVALO_S_R7", "120"))
URL_PING = r1_config.URL_CONSULTA
URL_LOGIN = r1_config.URL_LOGIN
URL_EDITAR = r1_config.URL_EDITAR              # novatelaoperacao.php?action=edit&op={op}

# --------------------------------------------------------------------------- #
# Fila de entrada
# --------------------------------------------------------------------------- #
# Etapa onde a verificacao acontece (o R1 V4 deposita as ops aqui).
VALOR_ETAPA_ENTRADA = _s("R7_ETAPA_ENTRADA", r1_config.VALOR_ETAPA_AGUARDANDO_ASS)  # "15"
ROTULO_ETAPA_ENTRADA = _s("R7_ROTULO_ETAPA_ENTRADA", "Aguardando Ass.")

# --------------------------------------------------------------------------- #
# REGRAS DA FORMA DE PAGAMENTO (grade PIX da tela da operacao)
# --------------------------------------------------------------------------- #
# Coluna "Tipo" da grade: tem de ser PIX (nada de TED/DOC/deposito).
TIPO_PAGAMENTO_ESPERADO = _s("R7_TIPO_PAGAMENTO", "PIX")

# Coluna "Cta. origem": a conta de onde o dinheiro SAI (conta da Prosper).
# Comparacao normalizada (sem acento, caixa baixa, espacos colapsados) e por
# "contem" - o Smart trunca o nome na tela.
CONTA_ORIGEM_ESPERADA = _s("R7_CONTA_ORIGEM", "mp prospere")

# Colunas que precisam estar PREENCHIDAS (dados do favorecido/cedente).
# Os nomes aqui sao os *canonicos* usados pelo checagem_pagamento.py; o
# de-para com os campos reais do HTML fica em checagem_pagamento.CAMPOS.
CAMPOS_OBRIGATORIOS = [c.strip() for c in _s(
    "R7_CAMPOS_OBRIGATORIOS",
    "cta_destino,bco,agencia,tipo_conta,cc,favorecido,cpf_cnpj").split(",") if c.strip()]

# Uma PIX sem chave nao paga -> por padrao a chave tambem e exigida.
EXIGIR_CHAVE_PIX = _b("R7_EXIGIR_CHAVE_PIX", "1")

# Coluna "Vencto" tem de ser a data de HOJE.
EXIGIR_VENCTO_HOJE = _b("R7_EXIGIR_VENCTO_HOJE", "1")

# Coluna "SP" (checkbox no fim da linha) tem de estar marcada.
EXIGIR_SP_MARCADO = _b("R7_EXIGIR_SP", "1")

# ORDEM DAS CHECAGENS (regra do usuario, 2026-08-28): a forma de pagamento so e
# conferida DEPOIS que as assinaturas estao ok. Enquanto ninguem assinou, o
# cadastro de pagamento ainda esta sendo montado - cobrar dele nessa fase e
# ruido (o 'SP' desmarcado aparecia em quase toda op recem-chegada). Com o
# portao ligado, op com documento pendente recebe SO as pendencias de
# documento, e o pagamento e conferido no ciclo seguinte, quando assinarem.
# Efeito colateral: um pagamento errado (ex.: Tipo=TED, conta em branco) so
# aparece depois das assinaturas - mais tarde, mas no momento em que importa.
PAGAMENTO_SO_APOS_ASSINATURAS = _b("R7_PAGAMENTO_SO_APOS_ASSINATURAS", "1")

# --------------------------------------------------------------------------- #
# REGRAS DOS DOCUMENTOS (doc2you)
# --------------------------------------------------------------------------- #
# "Devidamente assinado" = status Concluido no doc2you. Pendente = aguardando
# assinatura -> NAO pode finalizar.
STATUS_ASSINADO = ("concluido", "concluído")

# EXCECAO DO ADITIVO (regra do usuario, 2026-08-28): o Aditivo NUNCA fica
# "Concluido" no doc2you porque falta a assinatura da PROSPER, que e feita
# depois. Entao ele conta como OK quando **todos os assinantes que NAO sao a
# Prosper ja assinaram** - so a Prosper pendente nao impede a finalizacao.
# Documentos com essa excecao (nomes canonicos do checagem_docs):
ASSINATURA_PROSPER_OPCIONAL = [d.strip() for d in _s(
    "R7_ASSINATURA_PROSPER_OPCIONAL", "aditivo").split(",") if d.strip()]
# Como reconhecer a Prosper na lista de assinantes do doc2you. A ordem de
# confianca importa (ver checagem_docs._e_prosper):
#   1) PAPEL   - a tabela do doc2you tem a coluna "Papel": a Prosper e a
#      'Contratada'; cedente/representantes sao 'Contratante' e os garantidores
#      'Avalista'. E o criterio mais confiavel.
PAPEIS_PROSPER = [p.strip() for p in _s("R7_PAPEIS_PROSPER", "Contratada").split(",") if p.strip()]
#      Quem tem um destes papeis NUNCA e a Prosper (fecha a porta p/ erro de nome).
PAPEIS_TERCEIRO = [p.strip() for p in _s(
    "R7_PAPEIS_TERCEIRO", "Contratante,Avalista,Interveniente,Testemunha").split(",") if p.strip()]
#   2) CNPJ da Prosper na coluna documento.
CNPJ_PROSPER = [c.strip() for c in _s(
    "R7_CNPJ_PROSPER", "61.798.154/0001-65").split(",") if c.strip()]
#   3) NOME (ultimo recurso, criterio fragil - so usado se papel e CNPJ nao decidirem).
ASSINANTES_PROSPER = [a.strip() for a in _s(
    "R7_ASSINANTES_PROSPER", "prospere securitizadora,prosper vetor,prosperfidc").split(",") if a.strip()]
# Como avaliar a excecao acima:
#   signatarios -> abre o documento no doc2you e confere assinante a assinante
#                  (regra exata; exige o endpoint de detalhe mapeado)
#   so_existe   -> nao olha assinante: basta o Aditivo existir (regra frouxa,
#                  usada como PONTE ate o endpoint estar mapeado)
# Em "signatarios", se a leitura dos assinantes falhar, cai p/ "so_existe" e
# AVISA no log (nunca reprova a op por falha de leitura).
MODO_ADITIVO = _s("R7_MODO_ADITIVO", "signatarios").strip().lower()

# Tipos de titulo que EXIGEM Duplicata/Letra de cambio alem de Aditivo+NPP.
# (regra confirmada em 2026-05-29: LCB/CTR/CHQ nao geram Duplicata; DUR/DSR sim)
TIPOS_COM_DUPLICATA = [t.strip().upper() for t in _s(
    "R7_TIPOS_COM_DUPLICATA", "DUR,DSR,DMR").split(",") if t.strip()]
# Tipos que exigem LETRA DE CAMBIO (LCB) no doc2you.
TIPOS_COM_LETRA_CAMBIO = [t.strip().upper() for t in _s(
    "R7_TIPOS_LCB", "LCB").split(",") if t.strip()]

# --------------------------------------------------------------------------- #
# Notificacao (e-mail p/ o operador)
# --------------------------------------------------------------------------- #
EMAIL_DESTINO = [e.strip() for e in _s(
    "R7_EMAIL_DESTINO", "operacional@prospereinvest.com.br").split(",") if e.strip()]
# O SMTP vem do ambiente (broker do Access Guardian: SMTP_SERVER/SMTP_PORT/EMAIL_FROM,
# senha vazia) - ver notificar.py. Ate 22/09/2026 vinha de um email_config.json da maquina
# Windows de origem, que nao existe no servidor.
EMAIL_ATIVO = _b("R7_EMAIL_ATIVO", "1")
# Caixa do `notificar.py --teste` (a caixa de testes da casa, nunca o operacional).
EMAIL_TESTE = [e.strip() for e in _s(
    "R7_EMAIL_TESTE", "testes@prospereinvest.com.br").split(",") if e.strip()]
# Canais do aviso de PAGAMENTO pendente (documentos ok, grade PIX travando). Cada um
# ainda obedece a sua chave: whatsapp -> R7_WHATSAPP_ATIVO; email -> R7_EMAIL_ATIVO.
# Vazio desliga o aviso de pendencia sem mexer no WhatsApp das finalizacoes.
AVISO_PENDENCIA_CANAIS = [c.strip().lower() for c in _s(
    "R7_AVISO_PENDENCIA_CANAIS", "whatsapp,email").split(",") if c.strip()]

# Avisar TAMBEM quando a operacao FOR FINALIZADA (nao so quando e barrada),
# dizendo o motivo: o que foi conferido e por que passou.
AVISAR_FINALIZACAO = _b("R7_AVISAR_FINALIZACAO", "1")
EMAIL_DESTINO_FINALIZACAO = [e.strip() for e in _s(
    "R7_EMAIL_DESTINO_FINALIZACAO", ",".join(EMAIL_DESTINO)).split(",") if e.strip()]
# Canal do aviso de FINALIZACAO, ligavel separado (o de PENDENCIA continua no
# EMAIL_ATIVO). Hoje o usuario quer so o WhatsApp nas finalizacoes.
EMAIL_FINALIZACAO_ATIVO = _b("R7_EMAIL_FINALIZACAO", "1")

# --------------------------------------------------------------------------- #
# WhatsApp - canal PLUGAVEL
# --------------------------------------------------------------------------- #
# Adaptado ao servidor em 02/09/2026: o envio real e DELEGADO ao modulo comum
# `src/common/clients/whatsapp_evolution.py`, que le EVOLUTION_API_URL e
# EVOLUTION_API_KEY do AMBIENTE - dentro do container elas ja existem (o
# docker-compose injeta o .env da raiz via env_file), entao la nao ha nada a
# configurar. No sandbox (host) quem as publica e o harness, a partir de
# config/sandbox.env.
#
# O provider `baileys_local` do pacote de origem (bot Node na maquina Windows)
# foi APOSENTADO: nao existe nesse servidor. Ficaram:
#   evolution -> modulo comum (Prosperito) - o DEFAULT
#   arquivo   -> so grava a mensagem num .txt (nao envia; util p/ ensaio)
#   nenhum    -> desligado
WHATSAPP_PROVIDER = _s("R7_WHATSAPP_PROVIDER", "evolution").strip().lower()
WHATSAPP_ATIVO = _b("R7_WHATSAPP_ATIVO", "1")
WHATSAPP_DESTINO = [n.strip() for n in _s(
    "R7_WHATSAPP_DESTINO", "5511963226389").split(",") if n.strip()]
# Quem recebe o aviso de PAGAMENTO pendente no WhatsApp (padrao: o mesmo das finalizacoes).
WHATSAPP_DESTINO_PENDENCIA = [n.strip() for n in _s(
    "R7_WHATSAPP_DESTINO_PENDENCIA", ",".join(WHATSAPP_DESTINO)).split(",") if n.strip()]
# Instancia da Evolution. O nome real e resolvido pelo modulo comum via
# EVOLUTION_INST_<TAG>_NAME, a mesma convencao do healthcheck dos boletos.
WHATSAPP_INSTANCIA = _s("R7_WHATSAPP_INSTANCIA", "Prosperito")
WHATSAPP_ARQUIVO_SAIDA = _s("R7_WHATSAPP_ARQUIVO", os.path.join(_AQUI, "whatsapp_enviados.txt"))

# --------------------------------------------------------------------------- #
# Seguranca / operacao
# --------------------------------------------------------------------------- #
# DRY_RUN: confere e avisa, mas NUNCA clica em Finalizar. Deixe LIGADO ate
# validar num lote real.
DRY_RUN = _b("R7_DRY_RUN", "1")
# LIMITE DE HORA para clicar em Finalizar. A remessa de pagamento sai a cada 5 min
# ate 18:55 e exige vencimento = hoje: operacao finalizada depois disso so entra na
# remessa de amanha, com o vencimento de ontem. Pendencia do README desde 21/09/2026,
# fechada em 22/09/2026 ao tirar o robo do DRY. Formato HH:MM, hora local do
# container (TZ=America/Sao_Paulo). Vazio desliga o limite; valor invalido FECHA a
# porta: a acao e irreversivel, entao configuracao errada nunca pode abri-la.
HORA_LIMITE_FINALIZAR = _s("R7_HORA_LIMITE_FINALIZAR", "18:30").strip()


def _agora():
    """Separado para os testes fixarem o relogio."""
    return datetime.now()


def dentro_da_janela_de_finalizacao(agora=None):
    """-> (True/False, detalhe). Vale para QUALQUER caminho que clique em Finalizar:
    o processar() consulta antes de registrar a intencao de clique e o
    finalizar_da_grade() consulta de novo no ponto do clique."""
    if not HORA_LIMITE_FINALIZAR:
        return True, "sem limite de hora (R7_HORA_LIMITE_FINALIZAR vazio)"
    try:
        hh, mm = HORA_LIMITE_FINALIZAR.split(":")
        limite = dt_time(int(hh), int(mm))
    except (ValueError, TypeError):
        return False, (f"R7_HORA_LIMITE_FINALIZAR invalido ({HORA_LIMITE_FINALIZAR!r}, "
                       "esperado HH:MM): porta fechada por seguranca")
    agora = agora or _agora()
    if agora.time() > limite:
        return False, (f"{agora.strftime('%H:%M')} passa do limite {HORA_LIMITE_FINALIZAR}; "
                       "a remessa de pagamento exige vencimento = hoje e a ultima sai 18:55")
    return True, f"{agora.strftime('%H:%M')} dentro do limite {HORA_LIMITE_FINALIZAR}"


# Quanto esperar o botao Pagamento sair de "desabilitado" (operacao aberta por outro
# usuario no Smart) antes de desistir da op neste ciclo.
ESPERA_BTN_PAGAMENTO_S = float(_s("R7_ESPERA_BTN_PAGAMENTO_S", "90"))
# Intervalo entre ciclos (segundos) quando roda em modo --loop.
INTERVALO_CICLO_S = int(_s("R7_INTERVALO_CICLO_S", "600"))

# REENVIO DO AVISO com espacamento DOBRADO (regra do usuario, 2026-08-28): a op
# que continua pendente e cobrada de novo, mas cada vez mais espacado -
# 1o aviso na hora, depois 2h, 4h, 8h, 16h, ... ate o teto.
# Se as PENDENCIAS MUDAREM (o operador resolveu uma e sobrou outra), o contador
# ZERA e o aviso sai na hora.
AVISO_INTERVALO_BASE_MIN = int(_s("R7_AVISO_INTERVALO_BASE_MIN", "120"))  # 2h
AVISO_INTERVALO_TETO_H = int(_s("R7_AVISO_INTERVALO_TETO_H", "24"))       # 1x/dia no limite
ARQ_AVISOS = os.path.join(_AQUI, "avisos_enviados.csv")
# Ops finalizadas pelo robo (trilha de auditoria).
ARQ_FINALIZADAS = os.path.join(_AQUI, "finalizadas.csv")
DEBUG_DIR = _s("DEBUG_DIR_R7", "debug_r7")


def ensure_dirs() -> None:
    """Cria as pastas de trabalho (contrato do src.common.clients.smart_sessao). Idempotente."""
    for d in (USER_DATA_DIR, DEBUG_DIR):
        os.makedirs(d, exist_ok=True)
