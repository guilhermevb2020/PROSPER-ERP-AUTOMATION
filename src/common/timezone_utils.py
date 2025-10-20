# Versão: v1.0
# Gerado por: ChatGPT
# Data: 2025-05-12

# -----------------------------------------------------------------------------
# MÓDULO: timezone_utils.py
# CAMINHO: src/common/timezone_utils.py
# OBJETIVO: Utilitários de data/hora com fuso horário de Brasília
# -----------------------------------------------------------------------------

from datetime import datetime
import pytz

# 1.0 Define o fuso horário de Brasília
BR_TIMEZONE = pytz.timezone("America/Sao_Paulo")

# 2.0 Retorna datetime atual no fuso horário de Brasília
def now_br():
    """
    Retorna a data e hora atuais no fuso horário de Brasília.
    """
    return datetime.now(BR_TIMEZONE)

# 3.0 Retorna apenas a hora atual (int)
def hour_br():
    """
    Retorna apenas a hora atual no fuso horário de Brasília.
    """
    return now_br().hour

# 4.0 Retorna somente a data
def today_br():
    """
    Retorna a data atual no fuso horário de Brasília.
    """
    return now_br().date()

# 5.0 Retorna data/hora atual formatada
def formatted_now_br(fmt="%Y-%m-%d %H:%M:%S"):
    """
    Retorna a data/hora atual formatada no fuso horário de Brasília.
    Parâmetro fmt controla o formato de saída (ex: %d/%m/%Y).
    """
    return now_br().strftime(fmt)
