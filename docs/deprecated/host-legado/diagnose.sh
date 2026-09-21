#!/bin/bash
# =============================================================================================
# Script de Diagnóstico - PROSPER-ERP-AUTOMATION
# =============================================================================================

echo "=========================================="
echo "DIAGNÓSTICO PROSPER-ERP-AUTOMATION"
echo "=========================================="
echo ""
echo "Data: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Servidor: $(hostname)"
echo "IP: $(hostname -I | awk '{print $1}')"
echo ""

echo "=========================================="
echo "1. PROCESSOS EM EXECUÇÃO"
echo "=========================================="
ps aux | grep -E "(Xvfb|x11vnc|novnc|python.*titulos)" | grep -v grep || echo "Nenhum processo encontrado"
echo ""

echo "=========================================="
echo "2. PORTAS ABERTAS"
echo "=========================================="
netstat -tlnp 2>/dev/null | grep -E "(5900|6080)" || ss -tlnp | grep -E "(5900|6080)" || echo "Nenhuma porta VNC aberta"
echo ""

echo "=========================================="
echo "3. VARIÁVEIS DE AMBIENTE"
echo "=========================================="
echo "DISPLAY=$DISPLAY"
echo "PYTHONPATH=$PYTHONPATH"
echo "PWD=$PWD"
echo ""

echo "=========================================="
echo "4. PYTHON E AMBIENTE VIRTUAL"
echo "=========================================="
which python python3
python3 --version 2>/dev/null || echo "Python3 não encontrado"
echo ""
if [ -d "venv" ]; then
    echo "✅ Ambiente virtual encontrado em: venv/"
    source venv/bin/activate 2>/dev/null
    echo "Python no venv: $(which python)"
    echo "Versão: $(python --version)"
else
    echo "❌ Ambiente virtual NÃO encontrado"
fi
echo ""

echo "=========================================="
echo "5. DEPENDÊNCIAS PYTHON"
echo "=========================================="
if [ -d "venv" ]; then
    source venv/bin/activate 2>/dev/null
    echo "Principais dependências:"
    pip list 2>/dev/null | grep -E "(nodriver|selenium|dotenv|pandas|capsolver)" || echo "Nenhuma dependência encontrada"
else
    echo "❌ Ambiente virtual não encontrado - não é possível verificar dependências"
fi
echo ""

echo "=========================================="
echo "6. ESPAÇO EM DISCO"
echo "=========================================="
df -h /home/ubuntu | head -2
echo ""
echo "Tamanho do projeto:"
du -sh /home/ubuntu/PROSPER-ERP-AUTOMATION 2>/dev/null || echo "Não foi possível calcular"
echo ""

echo "=========================================="
echo "7. MEMÓRIA RAM"
echo "=========================================="
free -h
echo ""

echo "=========================================="
echo "8. ARQUIVOS DE CONFIGURAÇÃO"
echo "=========================================="
if [ -f ".env" ]; then
    echo "✅ .env encontrado"
    echo "Variáveis configuradas:"
    grep -v "^#" .env | grep -v "^$" | sed 's/=.*/=***/' 2>/dev/null || echo "Erro ao ler .env"
else
    echo "❌ .env NÃO encontrado"
fi
echo ""

if [ -f "/home/ubuntu/.vnc/passwd" ]; then
    echo "✅ Senha VNC configurada"
else
    echo "❌ Senha VNC NÃO configurada"
fi
echo ""

echo "=========================================="
echo "9. LOGS RECENTES (últimas 15 linhas)"
echo "=========================================="
if [ -f "logs/app.log" ]; then
    tail -15 logs/app.log
else
    echo "❌ Arquivo de log não encontrado"
fi
echo ""

echo "=========================================="
echo "10. ARQUIVOS CSV GERADOS"
echo "=========================================="
if [ -d "data/raw_inputs" ]; then
    echo "Últimos 5 CSVs:"
    ls -lht data/raw_inputs/*.csv 2>/dev/null | head -5 || echo "Nenhum CSV encontrado"
else
    echo "❌ Diretório data/raw_inputs não encontrado"
fi
echo ""

echo "=========================================="
echo "11. CONECTIVIDADE"
echo "=========================================="
echo "Teste de DNS:"
nslookup smartsecurities.com.br 2>/dev/null | grep -A2 "Name:" || echo "Falha ao resolver DNS"
echo ""

echo "=========================================="
echo "12. CHROME INSTALADO"
echo "=========================================="
if command -v google-chrome &> /dev/null; then
    echo "✅ Chrome instalado"
    google-chrome --version
else
    echo "❌ Chrome NÃO instalado"
fi
echo ""

echo "=========================================="
echo "RESUMO DO DIAGNÓSTICO"
echo "=========================================="
echo "✅ = Funcionando | ❌ = Problema"
echo ""

# Resumo
[ -d "venv" ] && echo "✅ Ambiente virtual" || echo "❌ Ambiente virtual"
[ -f ".env" ] && echo "✅ Arquivo .env" || echo "❌ Arquivo .env"
pgrep Xvfb > /dev/null && echo "✅ Xvfb rodando" || echo "❌ Xvfb NÃO rodando"
pgrep x11vnc > /dev/null && echo "✅ x11vnc rodando" || echo "❌ x11vnc NÃO rodando"
pgrep -f novnc > /dev/null && echo "✅ noVNC rodando" || echo "❌ noVNC NÃO rodando"
[ -f "/home/ubuntu/.vnc/passwd" ] && echo "✅ Senha VNC configurada" || echo "❌ Senha VNC NÃO configurada"
command -v google-chrome &> /dev/null && echo "✅ Chrome instalado" || echo "❌ Chrome NÃO instalado"

echo ""
echo "=========================================="
echo "FIM DO DIAGNÓSTICO"
echo "=========================================="
