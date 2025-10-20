# 🚀 COMO EXECUTAR - COMANDOS PRONTOS

## ✅ TESTADO E FUNCIONANDO

---

## 1️⃣ INICIAR XVFB E VNC (Display Virtual)

Execute **UMA VEZ** quando reiniciar o servidor:

```bash
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION

# Parar processos antigos (se houver)
pkill Xvfb 2>/dev/null || true
pkill x11vnc 2>/dev/null || true

# Iniciar Xvfb (display virtual)
Xvfb :1 -screen 0 1920x1080x24 &

# Aguardar 2 segundos
sleep 2

# Iniciar x11vnc (servidor VNC porta 5900)
x11vnc -display :1 -forever -nopw -quiet -bg

# Verificar se está rodando
ps aux | grep -E "Xvfb|x11vnc" | grep -v grep
```

**Você deve ver:**
```
ubuntu  12345  ... Xvfb :1 -screen 0 1920x1080x24
ubuntu  12346  ... x11vnc -display :1 -forever -nopw -quiet -bg
```

---

## 2️⃣ EXECUTAR O PROCESSADOR

### Opção A: Usar o script (RECOMENDADO)

```bash
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
./run_processor.sh
```

### Opção B: Comando manual

```bash
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
source venv/bin/activate
export PYTHONPATH=/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
export DISPLAY=:1
python3 src/processors/web/titulos_abertos_e_marcados_recompras.py
```

---

## 3️⃣ CONECTAR VIA VNC (Para Ver o Chrome)

### Passo 1: Ver o IP do servidor

```bash
curl ifconfig.me
```

**Anote o IP que aparecer** (exemplo: 54.123.45.67)

### Passo 2: Liberar porta 5900 no firewall

```bash
sudo ufw allow 5900
sudo ufw status
```

### Passo 3: Conectar do seu computador

**No Windows:**
1. Baixe **RealVNC Viewer**: https://www.realvnc.com/en/connect/download/viewer/
2. Instale e abra
3. Digite na barra de endereço:
   ```
   54.123.45.67:5900
   ```
   (use o IP que apareceu no `curl ifconfig.me`)
4. Clique "Connect"
5. Se pedir senha, deixe em branco

**No Linux:**
```bash
# Instalar
sudo apt install tigervnc-viewer

# Conectar (substitua pelo seu IP)
vncviewer 54.123.45.67:5900
```

**No Mac:**
```bash
# Abrir Screen Sharing (substitua pelo seu IP)
open vnc://54.123.45.67:5900
```

---

## 4️⃣ INSTALAR EXTENSÃO CAPSOLVER (OBRIGATÓRIO)

**Via VNC (após conectar):**

1. Na janela do VNC, você verá o Chrome aberto
2. Digite na barra de endereço: `chrome://extensions/`
3. Ative **"Modo do desenvolvedor"** (canto superior direito)
4. Clique em **"Chrome Web Store"** (ou abra uma nova aba)
5. Busque por: **"CapSolver"**
6. Clique em **"Adicionar ao Chrome"**
7. Após instalar, clique no ícone da extensão (canto superior direito)
8. Configure:
   - Cole a API key: `CAP-019482E44F3684B64453E091CBA221E39745E67C94B0EB000610DDE79C94BC96`
   - Ative **"Auto Solve"**
9. Pronto!

---

## 5️⃣ CONTROLES DURANTE EXECUÇÃO

Quando o processador estiver rodando:

- **P** - Pausar execução
- **R** - Retomar execução
- **Q** - Parar completamente

---

## 📋 CHECKLIST

Antes de executar, verifique:

- [ ] Xvfb rodando (`ps aux | grep Xvfb`)
- [ ] x11vnc rodando (`ps aux | grep x11vnc`)
- [ ] Porta 5900 liberada (`sudo ufw status`)
- [ ] VNC conectando (testar do seu PC)
- [ ] Extensão CapSolver instalada no Chrome (via VNC)

---

## 🔧 COMANDOS ÚTEIS

### Ver processos rodando
```bash
ps aux | grep -E "Xvfb|x11vnc|chrome" | grep -v grep
```

### Parar tudo
```bash
pkill Xvfb
pkill x11vnc
pkill chrome
```

### Reiniciar display virtual
```bash
pkill Xvfb && pkill x11vnc
Xvfb :1 -screen 0 1920x1080x24 &
sleep 2
x11vnc -display :1 -forever -nopw -quiet -bg
```

### Ver IP do servidor
```bash
curl ifconfig.me
```

### Ver porta VNC
```bash
netstat -tlnp | grep 5900
```

### Ver logs
```bash
tail -f logs/processors/*.log
```

---

## 🐛 TROUBLESHOOTING

### Erro: "No module named 'src'"

**Causa:** PYTHONPATH não configurado

**Solução:** Use o script `run_processor.sh` ou configure manualmente:
```bash
export PYTHONPATH=/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
```

### Erro: "Chrome not found"

**Causa:** Chrome não instalado

**Solução:**
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f -y
```

### VNC não conecta

**Causa:** Porta 5900 bloqueada

**Solução 1 - Firewall Ubuntu:**
```bash
sudo ufw allow 5900
```

**Solução 2 - AWS Security Group (se for EC2):**
1. AWS Console → EC2 → Security Groups
2. Selecione o security group da instância
3. Inbound Rules → Edit
4. Add Rule:
   - Type: Custom TCP
   - Port: 5900
   - Source: 0.0.0.0/0 (ou seu IP)
5. Save

### CAPTCHA não resolve automaticamente

**Causa:** Extensão CapSolver não instalada

**Solução:**
1. Conecte via VNC
2. Instale extensão CapSolver no Chrome (passo 4️⃣)
3. Ative "Auto Solve"

---

## 📊 FLUXO COMPLETO

```
1. Servidor Ubuntu (SSH)
   ↓
2. Xvfb :1 (display virtual) + x11vnc (VNC)
   ↓
3. ./run_processor.sh
   ↓
4. Nodriver abre Chrome no display :1
   ↓
5. Conectar via VNC do seu PC para ver
   ↓
6. Instalar extensão CapSolver (primeira vez)
   ↓
7. Chrome faz login automático
   ↓
8. Extensão resolve CAPTCHA
   ↓
9. Loop infinito:
   - Extração COM checkbox → CSV
   - Extração SEM checkbox → CSV
   - Aguardar 60s
   - Repetir
```

---

## ✅ TESTE RÁPIDO

Para verificar se está tudo funcionando:

```bash
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION

# 1. Verificar ambiente virtual
source venv/bin/activate
python3 -c "import nodriver; print('✅ Nodriver OK')"

# 2. Verificar Chrome
google-chrome --version

# 3. Verificar Xvfb
ps aux | grep Xvfb | grep -v grep

# 4. Verificar VNC
ps aux | grep x11vnc | grep -v grep

# 5. Verificar porta VNC
netstat -tlnp | grep 5900
```

Se todos retornarem resultado, está pronto! 🎉

---

## 🚀 COMANDOS RESUMIDOS

```bash
# No servidor (SSH):
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
pkill Xvfb 2>/dev/null || true && pkill x11vnc 2>/dev/null || true
Xvfb :1 -screen 0 1920x1080x24 &
sleep 2
x11vnc -display :1 -forever -nopw -quiet -bg
./run_processor.sh

# No seu PC:
# Conectar via VNC: <IP_DO_SERVIDOR>:5900
```

---

**Pronto para usar! 🎉**
