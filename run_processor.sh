#!/bin/bash
# Script simples para rodar o processador com todas as configurações corretas

cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION

# Ativar ambiente virtual
source venv/bin/activate

# Configurar variáveis de ambiente
export PYTHONPATH=/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
export DISPLAY=:1

# Executar processador
python3 src/processors/web/titulos_abertos_e_marcados_recompras.py
