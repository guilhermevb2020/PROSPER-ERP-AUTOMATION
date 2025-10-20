# -*- coding: utf-8 -*-
# =============================================================================================
# ARQUIVO: logging_config.py
# CAMINHO: src/core/logging_config.py
# VERSÃO: v2.6 (Console EXTREMAMENTE limpo, apenas CRITICAL para root logger)
# AUTOR: ChatGPT
# DATA: 2025-05-22 (MODIFICADO: 2025-05-22 para definir root_logger como CRITICAL para console limpo)
# DESCRIÇÃO:
#   - Configura o sistema de logging da aplicação.
#   - Envia logs simultaneamente para terminal (apenas CRITICOS) e para arquivo rotativo em logs/app.log (tudo).
#   - NUNCA duplica handlers, mesmo em execuções sucessivas.
# =============================================================================================

# =============================================================================================
# 1.0 IMPORTAÇÕES
# =============================================================================================
import logging
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import TimedRotatingFileHandler

# =============================================================================================
# 2.0 DEFINIÇÃO DE FORMATOS E CAMINHOS DE LOG
# =============================================================================================

# 2.1 Formato da mensagem de log
LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] [%(name)s] (%(filename)s:%(lineno)d %(funcName)s) - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 2.2 Diretório e caminho para o arquivo de log rotativo
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# Variável global para controlar se o logging já foi configurado
_logging_configured = False

# =============================================================================================
# 3.0 FUNÇÃO: SETUP GLOBAL DO LOGGING
# =============================================================================================
def setup_logging(level: Optional[str] = "INFO") -> None:
    """
    Inicializa a configuração de logging global do sistema.
    Os logs são direcionados ao terminal (apenas erros CRÍTICOS) e ao arquivo com rotação diária (tudo).
    Esta função garante que o logging seja configurado apenas uma vez.

    Parâmetros:
    ----------
    level : str
        Nível de log desejado para o arquivo de log. O console será mais restritivo.
        Exemplos: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    """
    global _logging_configured
    if _logging_configured:
        return

    root_logger = logging.getLogger()

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Nível do logger raiz é configurado para capturar tudo para o arquivo.
    # No entanto, para o console, seremos mais restritivos.
    nivel_para_arquivo = getattr(logging, level.upper(), logging.INFO)
    # AQUI ESTÁ A MUDANÇA: O nível do logger raiz agora será CRITICAL.
    # Isso impede que mensagens INFO e WARNING apareçam no console por padrão.
    # As mensagens para o arquivo ainda serão gravadas no nível 'nivel_para_arquivo'.
    root_logger.setLevel(logging.CRITICAL) # <--- ÚNICA MUDANÇA DE NÍVEL AQUI PARA O CONSOLE

    # 3.2 Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    # Garante que o console_handler só mostra CRITICALs.
    console_handler.setLevel(logging.CRITICAL)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    # 3.3 Handler para arquivo rotativo (diário)
    file_handler = TimedRotatingFileHandler(
        filename=LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=10,
        encoding="utf-8"
    )
    # O nível do file_handler é o que determina o que vai para o arquivo.
    file_handler.setLevel(nivel_para_arquivo) # <--- Este continua recebendo INFO/DEBUG/etc.
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    # 3.4 Adiciona ambos os handlers ao logger raiz
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _logging_configured = True
    # O logger para este módulo (logging_config) ainda pode registrar INFO no arquivo.
    logging.getLogger(__name__).info(f"Logging configurado com sucesso (nível ROOT: CRITICAL, nível FILE: {level.upper()})")


# =============================================================================================
# 4.0 FUNÇÃO: GET LOGGER POR MÓDULO
# =============================================================================================
def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger específico para o módulo chamador.
    """
    # Importante: Quando você chama get_logger(name), ele pega um logger já configurado.
    # Sua mensagem "Teste de conexão inicial com a engine SQLAlchemy" vem de src.common.database
    # que provavelmente chama get_logger(__name__). Esse logger, por sua vez,
    # está conectado ao root_logger. Se o root_logger estiver em CRITICAL,
    # ele filtrará essas mensagens INFO antes que cheguem aos handlers.
    return logging.getLogger(name)

# =============================================================================================
# FIM DO ARQUIVO: logging_config.py
# =============================================================================================