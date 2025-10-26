#!/bin/bash
# ============================================================================
# SCRIPT: start_fresh.sh
# DESCRIÇÃO: Reinicia ambiente E executa automação (tudo de uma vez)
# USO: ./start_fresh.sh
# ============================================================================

echo "================================================================================"
echo "🚀 INICIANDO AMBIENTE COMPLETO + AUTOMAÇÃO"
echo "================================================================================"
echo

# Executar restart
echo "Executando restart_environment.sh..."
/home/ubuntu/PROSPER-ERP-AUTOMATION/restart_environment.sh

# Verificar se deu certo
if [ $? -ne 0 ]; then
    echo
    echo "❌ ERRO ao reiniciar ambiente!"
    exit 1
fi

echo
echo "================================================================================"
echo "⏳ Aguardando 3 segundos antes de iniciar automação..."
echo "================================================================================"
sleep 3

echo
echo "================================================================================"
echo "🤖 INICIANDO AUTOMAÇÃO..."
echo "================================================================================"
echo

cd /home/ubuntu/PROSPER-ERP-AUTOMATION

# Ativar venv
source venv/bin/activate

# Configurar variáveis
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
export DISPLAY=:1

# Executar processador
python3 src/processors/web/titulos_abertos_e_marcados_recompras.py
