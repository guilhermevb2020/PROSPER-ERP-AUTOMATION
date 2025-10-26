# 🛠️ Troubleshooting - PROSPER-ERP-AUTOMATION

Guia completo de solução de problemas.

---

## 📋 Índice

1. [Problemas de Ambiente](#problemas-de-ambiente)
2. [Problemas de VNC](#problemas-de-vnc)
3. [Problemas de Execução Python](#problemas-de-execução-python)
4. [Problemas com Chrome/Nodriver](#problemas-com-chromenodriver)
5. [Problemas com CAPTCHA](#problemas-com-captcha)
6. [Problemas de Rede/Firewall](#problemas-de-redefirewall)
7. [Problemas de Logs](#problemas-de-logs)
8. [Comandos de Diagnóstico](#comandos-de-diagnóstico)

---

## 1. Problemas de Ambiente

### ❌ **"ModuleNotFoundError: No module named 'src'"**

**Causa:** PYTHONPATH não configurado

**Solução:**
```bash
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
python3 src/processors/web/titulos_abertos_e_marcados_recompras.py
```

**Solução permanente (usar script):**
```bash
./run_processor.sh  # Script já configura PYTHONPATH automaticamente
```

---

### ❌ **"ModuleNotFoundError: No module named 'dotenv'"**

**Causa:** Ambiente virtual não ativado ou dependências não instaladas

**Solução:**
```bash
# Ativar ambiente virtual
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

**Verificar instalação:**
```bash
pip list | grep -E "(dotenv|nodriver|selenium)"
```

---

### ❌ **"Permission denied: './run_processor.sh'"**

**Causa:** Script sem permissão de execução

**Solução:**
```bash
chmod +x run_processor.sh start_automation.sh
```

---

### ❌ **"required file not found" ao executar script .sh**

**Causa:** Arquivo tem line endings Windows (CRLF)

**Solução:**
```bash
# Converter CRLF para LF
sed -i 's/\r$//' run_processor.sh
sed -i 's/\r$//' start_automation.sh

# Tornar executável
chmod +x *.sh
```

---

## 2. Problemas de VNC

### ❌ **"Conexão recusada" ao tentar conectar VNC**

**Verificar se serviços estão rodando:**
```bash
ps aux | grep -E "(Xvfb|x11vnc|novnc)"
```

**Se não aparecer nada, iniciar serviços:**
```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
./start_automation.sh
```

**Verificar portas abertas:**
```bash
netstat -tlnp | grep -E "(5900|6080)"
# ou
ss -tlnp | grep -E "(5900|6080)"
```

---

### ❌ **"Authentication failed" ou "Senha incorreta"**

**Senha correta:**
```
vetor2025
```

**Recriar senha VNC:**
```bash
x11vnc -storepasswd vetor2025 /home/ubuntu/.vnc/passwd
chmod 600 /home/ubuntu/.vnc/passwd

# Reiniciar x11vnc
pkill x11vnc
x11vnc -display :1 -forever -rfbauth /home/ubuntu/.vnc/passwd -quiet -bg -rfbport 5900
```

---

### ❌ **Tela preta ou desktop vazio no VNC**

**Causa:** Xvfb não está rodando

**Verificar Xvfb:**
```bash
ps aux | grep Xvfb | grep -v grep
```

**Reiniciar Xvfb:**
```bash
pkill Xvfb
Xvfb :1 -screen 0 1920x1080x24 &
sleep 2

# Reiniciar x11vnc
pkill x11vnc
x11vnc -display :1 -forever -rfbauth /home/ubuntu/.vnc/passwd -quiet -bg -rfbport 5900
```

---

### ❌ **noVNC mostra "lista de arquivos" em vez da interface**

**Causa:** URL incompleta

**URL correta:**
```
http://3.148.126.73:6080/vnc.html
```

**NÃO use apenas:**
```
http://3.148.126.73:6080/  ❌
```

---

### ❌ **noVNC não carrega (erro 404 ou timeout)**

**Verificar se noVNC está instalado:**
```bash
ls -la /home/ubuntu/noVNC/
```

**Se não existir, instalar:**
```bash
cd /home/ubuntu
git clone https://github.com/novnc/noVNC.git
git clone https://github.com/novnc/websockify.git
```

**Reiniciar noVNC:**
```bash
pkill -f novnc_proxy
cd /home/ubuntu/noVNC
./utils/novnc_proxy --vnc localhost:5900 --listen 6080 &
```

---

## 3. Problemas de Execução Python

### ❌ **"No module named 'nodriver'"**

**Instalar nodriver:**
```bash
source venv/bin/activate
pip install nodriver>=0.33
```

---

### ❌ **"SyntaxError" ou "invalid syntax"**

**Causa:** Versão Python incorreta

**Verificar versão:**
```bash
python3 --version
# Deve ser 3.12+
```

**Se < 3.12, atualizar Python:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv
```

---

### ❌ **Script para abruptamente sem erro**

**Ver logs:**
```bash
tail -50 logs/app.log
```

**Executar com mais verbosidade:**
```bash
export APP_LOG_LEVEL=DEBUG
python3 src/processors/web/titulos_abertos_e_marcados_recompras.py
```

---

## 4. Problemas com Chrome/Nodriver

### ❌ **"Failed to connect to browser"**

**Causas possíveis:**
1. Xvfb não está rodando
2. DISPLAY não configurado
3. sandbox=False não configurado

**Solução:**
```bash
# 1. Verificar Xvfb
ps aux | grep Xvfb
# Se não estiver rodando:
Xvfb :1 -screen 0 1920x1080x24 &

# 2. Configurar DISPLAY
export DISPLAY=:1

# 3. Verificar se sandbox=False está em nodriver_utils.py
grep "sandbox=False" src/common/nodriver_utils.py
# Deve aparecer na linha ~94
```

**Reiniciar tudo:**
```bash
./start_automation.sh
./run_processor.sh
```

---

### ❌ **"Chrome crashed" ou "Browser closed unexpectedly"**

**Verificar recursos do sistema:**
```bash
free -h     # RAM disponível
df -h       # Disco disponível
```

**Se pouca RAM (<500MB livre):**
```bash
# Aumentar swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

### ❌ **Chrome não abre janelas**

**Testar Chrome manualmente:**
```bash
export DISPLAY=:1
google-chrome --no-sandbox --disable-dev-shm-usage
```

**Se não funcionar, reinstalar Chrome:**
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f
```

---

## 5. Problemas com CAPTCHA

### ❌ **CAPTCHA não resolve automaticamente**

**Verificações:**

1. **Extensão CapSolver instalada?**
   - Conecte ao VNC
   - Abra Chrome: `chrome://extensions/`
   - Verifique se CapSolver está instalada e ativada

2. **API Key configurada?**
   ```bash
   grep CAPSOLVER_API_KEY .env
   # Deve aparecer: CAPSOLVER_API_KEY=CAP-xxxxx
   ```

3. **Créditos suficientes?**
   - Acesse: https://dashboard.capsolver.com/
   - Verifique saldo

**Se não resolver automaticamente:**
- O código **pausa automaticamente** após 60 segundos
- Resolva manualmente via VNC
- Pressione **R** para retomar após resolver

---

## 6. Problemas de Rede/Firewall

### ❌ **Porta 6080 ou 5900 não acessível externamente**

**Verificar Security Group AWS:**
1. Acesse Console AWS → EC2 → Security Groups
2. Encontre o security group da instância
3. Verifique regras **Inbound**:
   ```
   Porta 5900 TCP - 0.0.0.0/0 (ou seu IP)
   Porta 6080 TCP - 0.0.0.0/0 (ou seu IP)
   ```

**Verificar firewall local (ufw):**
```bash
sudo ufw status

# Se bloqueado, liberar:
sudo ufw allow 5900
sudo ufw allow 6080
sudo ufw reload
```

---

### ❌ **"Connection timeout" ao acessar VNC**

**Verificar se servidor está acessível:**
```bash
# No seu computador
ping 3.148.126.73
telnet 3.148.126.73 6080
```

**Se timeout:**
- Verificar Security Group AWS
- Verificar se instância está rodando
- Verificar se IP público está correto

---

## 7. Problemas de Logs

### ❌ **Logs não aparecem**

**Verificar se diretório logs/ existe:**
```bash
ls -la logs/
```

**Se não existir:**
```bash
mkdir -p logs
```

**Testar logging:**
```bash
python3 -c "from src.core.logging_config import get_logger; logger = get_logger('test'); logger.info('Teste')"
```

---

### ❌ **Logs muito grandes**

**Ver tamanho:**
```bash
du -sh logs/
```

**Limpar logs antigos:**
```bash
find logs/ -name "*.log.*" -mtime +10 -delete
```

---

## 8. Comandos de Diagnóstico

### **Status Geral do Sistema**

```bash
#!/bin/bash
echo "=== DIAGNÓSTICO PROSPER-ERP-AUTOMATION ==="
echo ""
echo "1. PROCESSOS:"
ps aux | grep -E "(Xvfb|x11vnc|novnc|python)" | grep -v grep
echo ""
echo "2. PORTAS:"
netstat -tlnp | grep -E "(5900|6080)" || ss -tlnp | grep -E "(5900|6080)"
echo ""
echo "3. DISPLAY:"
echo "DISPLAY=$DISPLAY"
echo ""
echo "4. PYTHONPATH:"
echo "PYTHONPATH=$PYTHONPATH"
echo ""
echo "5. AMBIENTE VIRTUAL:"
which python
python --version
echo ""
echo "6. ESPAÇO EM DISCO:"
df -h /home/ubuntu
echo ""
echo "7. MEMÓRIA:"
free -h
echo ""
echo "8. LOGS RECENTES:"
tail -10 logs/app.log 2>/dev/null || echo "Sem logs"
```

**Salve como `diagnose.sh` e execute:**
```bash
chmod +x diagnose.sh
./diagnose.sh
```

---

### **Verificar Dependências Python**

```bash
source venv/bin/activate
pip list | grep -E "(nodriver|selenium|dotenv|pandas|capsolver)"
```

**Resultado esperado:**
```
capsolver      1.0.0
nodriver       0.47.0
pandas         2.2.3
python-dotenv  1.1.0
selenium       4.27.1
```

---

### **Testar Conexão com SmartSecurities**

```bash
curl -I https://smartsecurities.com.br
```

---

### **Verificar Extensão CapSolver (via VNC)**

1. Conecte ao VNC
2. Abra Chrome
3. Digite na barra: `chrome://extensions/`
4. Verifique se **CapSolver** aparece e está **Enabled**

---

## 🆘 Reiniciar Tudo (Reset Completo)

Se nada funcionar, **reset completo**:

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION

# 1. Parar todos os processos
pkill Xvfb
pkill x11vnc
pkill -f novnc_proxy
pkill -f titulos_abertos

# 2. Aguardar
sleep 3

# 3. Reiniciar ambiente
./start_automation.sh

# 4. Executar processador
./run_processor.sh
```

---

## 📞 Suporte

Se nenhuma solução acima resolver:

1. **Coletar informações:**
   ```bash
   ./diagnose.sh > diagnostico.txt
   tail -100 logs/app.log > ultimos_logs.txt
   ```

2. **Enviar para equipe de TI:**
   - Arquivo `diagnostico.txt`
   - Arquivo `ultimos_logs.txt`
   - Descrição do problema
   - Passos para reproduzir

---

**Última atualização:** 2025-10-20
