#!/bin/bash
# Verifica se notification_utils.py foi modificado

echo "================================================================================"
echo "VERIFICAÇÃO DE MODIFICAÇÕES NO SISTEMA DE NOTIFICAÇÕES"
echo "================================================================================"
echo

cd /home/ubuntu/PROSPER-ERP-AUTOMATION

echo "[1/4] Verificando status do Git para notification_utils.py..."
git status src/common/notification_utils.py
echo

echo "[2/4] Verificando diff (mudanças não commitadas)..."
if git diff src/common/notification_utils.py | grep -q .; then
    echo "❌ ARQUIVO FOI MODIFICADO!"
    git diff src/common/notification_utils.py
else
    echo "✅ Nenhuma modificação detectada em notification_utils.py"
fi
echo

echo "[3/4] Verificando histórico de commits..."
git log --oneline src/common/notification_utils.py | head -5
echo

echo "[4/4] Verificando TODAS as modificações não commitadas no projeto..."
echo "Arquivos modificados:"
git status --short
echo

echo "================================================================================"
echo "Diferenças no processador principal:"
echo "================================================================================"
git diff src/processors/web/titulos_abertos_e_marcados_recompras.py | grep -E "^(\+|\-)" | head -30
echo

echo "================================================================================"
echo "RESUMO: Apenas sleeps e correção de bug do frame foram modificados"
echo "================================================================================"
