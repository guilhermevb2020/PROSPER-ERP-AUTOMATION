#!/bin/bash
# Script para executar teste de email

cd /home/ubuntu/PROSPER-ERP-AUTOMATION

# Ativar ambiente virtual
source venv/bin/activate

# Configurar PYTHONPATH
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION

# Executar teste
python3 tests/test_email_notification.py
