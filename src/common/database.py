# -*- coding: utf-8 -*-
# =============================================================================================
# ARQUIVO: database.py
# CAMINHO: src/common/database.py
# VERSÃO: v1.4 (Proteção contra conexões mortas - pool_pre_ping + pool_recycle)
# AUTOR: ChatGPT
# DATA: 2025-10-01 (MODIFICADO: pool_pre_ping e pool_recycle para evitar conexões mortas)
# DESCRIÇÃO:
#   Fornece uma conexão centralizada com o banco de dados via SQLAlchemy,
#   usando string de conexão gerada dinamicamente em settings.py.
#   Utiliza singleton para garantir que a engine seja criada apenas uma vez.
# =============================================================================================

# =============================================================================================
# 1.0 IMPORTAÇÕES
# =============================================================================================
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

# Importa a configuração global do logger, garantindo que o logger deste módulo a siga.
from src.core.logging_config import get_logger
from src.config import settings

# =============================================================================================
# 2.0 RECUPERAÇÃO DA STRING DE CONEXÃO
# =============================================================================================
DATABASE_URL = settings.variaveis.get("DATABASE_URL")

# =============================================================================================
# 3.0 CONFIGURAÇÃO DO LOGGER LOCAL
# (REMOVIDA: Esta seção foi removida para usar a configuração global de logging_config.py)
# =============================================================================================
logger = get_logger(__name__) # Usa o logger globalmente configurado.

# =============================================================================================
# 4.0 VARIÁVEL INTERNA PARA CACHING (Singleton)
# =============================================================================================
_engine_instance: Engine = None

# =============================================================================================
# 5.0 FUNÇÃO PRINCIPAL DE CONEXÃO (Singleton)
# =============================================================================================
def connect_db() -> Engine:
    """
    Cria e retorna uma engine SQLAlchemy pronta para uso com pyodbc.
    A engine é criada apenas uma vez e reaproveitada em chamadas futuras.
    As mensagens de conexão são agora gerenciadas pelo sistema de logging global (para arquivo).
    """
    global _engine_instance
    if _engine_instance is not None:
        # Se a instância já existe, podemos logar em DEBUG (irá para o arquivo, não para o console)
        logger.debug("Reutilizando engine SQLAlchemy existente.")
        return _engine_instance

    try:
        # REMOVIDO: logger.info("Teste de conexão inicial com a engine SQLAlchemy realizado com sucesso.")
        _engine_instance = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,      # Testa conexão antes de usar (evita conexões mortas do pool)
            pool_recycle=3600        # Recicla conexões a cada 1 hora (evita timeout do Azure)
        )
        # Teste de conexão: Apenas para garantir que a engine funciona antes de retorná-la
        with _engine_instance.connect() as connection:
            connection.execute(text("SELECT 1"))
        # REMOVIDO: logger.info("Engine SQLAlchemy criada com sucesso.")
        logger.info("Engine SQLAlchemy criada e testada com sucesso (pool_pre_ping=True, pool_recycle=3600s).") # Mensagem mais concisa, ainda em INFO para o arquivo.
        return _engine_instance
    except SQLAlchemyError as e:
        logger.critical(f"Falha CRÍTICA ao criar ou testar engine SQLAlchemy: {e}", exc_info=True)
        raise # Re-lança a exceção para que o script principal saiba que falhou