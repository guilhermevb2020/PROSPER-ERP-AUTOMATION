# 🖥️ Setup de 12 Displays Virtuais + VNC

**Versão:** 1.0
**Data:** Outubro 2025

---

## 🎯 Objetivo

Configurar **12 displays virtuais independentes** (Xvfb) com acesso VNC via web (noVNC), permitindo:

- ✅ Cada automação roda em seu próprio display isolado
- ✅ Acesso remoto individual via browser
- ✅ Configuração persistente (reinicia com a VM)
- ✅ Senhas individuais por display

---

## 📐 Arquitetura de Displays

```
┌──────────────────────────────────────────────────────┐
│               SERVIDOR UBUNTU                         │
├──────────────────────────────────────────────────────┤
│                                                       │
│  Display :1  →  x11vnc :5900  →  noVNC :6080        │
│  Display :2  →  x11vnc :5901  →  noVNC :6081        │
│  Display :3  →  x11vnc :5902  →  noVNC :6082        │
│  Display :4  →  x11vnc :5903  →  noVNC :6083        │
│  Display :5  →  x11vnc :5904  →  noVNC :6084        │
│  Display :6  →  x11vnc :5905  →  noVNC :6085        │
│  Display :7  →  x11vnc :5906  →  noVNC :6086        │
│  Display :8  →  x11vnc :5907  →  noVNC :6087        │
│  Display :9  →  x11vnc :5908  →  noVNC :6088        │
│  Display :10 →  x11vnc :5909  →  noVNC :6089        │
│  Display :11 →  x11vnc :5910  →  noVNC :6090        │
│  Display :12 →  x11vnc :5911  →  noVNC :6091        │
│                                                       │
└──────────────────────────────────────────────────────┘
         │                      │
         │                      │
         ▼                      ▼
   VNC Direto            Browser (noVNC)
   (porta 5900-5911)     (porta 6080-6091)
```

---

## 🚀 Script Automatizado de Setup

Vou criar um script que configura TUDO automaticamente!

### **Passo 1: Criar o Script Principal**

```bash
sudo nano /usr/local/bin/setup_displays_vnc.sh
```

Cole o conteúdo:

```bash
#!/bin/bash
# =============================================================================================
# Script de Setup: 12 Displays Virtuais + VNC + noVNC
# =============================================================================================
# Este script configura 12 displays virtuais Xvfb com acesso VNC via web
# Uso: sudo ./setup_displays_vnc.sh
# =============================================================================================

set -e  # Para na primeira falha

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup: 12 Displays Virtuais + VNC${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Verificar se é root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Execute como root: sudo $0${NC}"
    exit 1
fi

# Usuário que vai rodar (não root)
TARGET_USER="ubuntu"
TARGET_HOME="/home/$TARGET_USER"

echo -e "${YELLOW}[1/6] Instalando dependências...${NC}"
apt update
apt install -y xvfb x11vnc xfonts-base xfonts-75dpi xfonts-100dpi

echo -e "${YELLOW}[2/6] Criando diretório de senhas VNC...${NC}"
mkdir -p $TARGET_HOME/.vnc
chown $TARGET_USER:$TARGET_USER $TARGET_HOME/.vnc

echo -e "${YELLOW}[3/6] Gerando senhas VNC para 12 displays...${NC}"
for i in $(seq 1 12); do
    DISPLAY_NUM=$i
    PASSWD_FILE="$TARGET_HOME/.vnc/passwd_display_$(printf "%02d" $i)"

    # Gerar senha aleatória de 16 caracteres
    PASSWORD=$(openssl rand -base64 16 | tr -d "=+/" | cut -c1-16)

    # Criar arquivo de senha VNC
    echo "$PASSWORD" | sudo -u $TARGET_USER x11vnc -storepasswd "$PASSWD_FILE" -usepw

    # Salvar senha em arquivo de texto (para referência)
    echo "Display :$DISPLAY_NUM - Senha: $PASSWORD" >> $TARGET_HOME/.vnc/passwords.txt

    echo -e "${GREEN}  ✅ Display :$DISPLAY_NUM senha criada${NC}"
done

chown $TARGET_USER:$TARGET_USER $TARGET_HOME/.vnc/passwords.txt
chmod 600 $TARGET_HOME/.vnc/passwords.txt

echo -e "${GREEN}  📄 Senhas salvas em: $TARGET_HOME/.vnc/passwords.txt${NC}"

echo -e "${YELLOW}[4/6] Criando serviços systemd para Xvfb...${NC}"
for i in $(seq 1 12); do
    DISPLAY_NUM=$i
    SERVICE_NAME="xvfb-display-$i.service"

    cat > /etc/systemd/system/$SERVICE_NAME <<EOF
[Unit]
Description=Xvfb Display :$DISPLAY_NUM
After=network.target

[Service]
Type=simple
User=$TARGET_USER
Environment="DISPLAY=:$DISPLAY_NUM"
ExecStart=/usr/bin/Xvfb :$DISPLAY_NUM -screen 0 1920x1080x24
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME

    echo -e "${GREEN}  ✅ Xvfb Display :$DISPLAY_NUM iniciado${NC}"
done

echo -e "${YELLOW}[5/6] Criando serviços systemd para x11vnc...${NC}"
for i in $(seq 1 12); do
    DISPLAY_NUM=$i
    VNC_PORT=$((5899 + $i))  # 5900, 5901, ..., 5911
    PASSWD_FILE="$TARGET_HOME/.vnc/passwd_display_$(printf "%02d" $i)"
    SERVICE_NAME="x11vnc-display-$i.service"

    cat > /etc/systemd/system/$SERVICE_NAME <<EOF
[Unit]
Description=x11vnc for Display :$DISPLAY_NUM
After=xvfb-display-$i.service
Requires=xvfb-display-$i.service

[Service]
Type=simple
User=$TARGET_USER
Environment="DISPLAY=:$DISPLAY_NUM"
ExecStart=/usr/bin/x11vnc \\
    -display :$DISPLAY_NUM \\
    -forever \\
    -shared \\
    -rfbauth $PASSWD_FILE \\
    -rfbport $VNC_PORT \\
    -noxdamage \\
    -xkb \\
    -ncache 10 \\
    -ncache_cr
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME

    echo -e "${GREEN}  ✅ x11vnc Display :$DISPLAY_NUM porta $VNC_PORT iniciado${NC}"
done

echo -e "${YELLOW}[6/6] Criando serviços systemd para noVNC...${NC}"

# Verificar se noVNC existe
if [ ! -d "$TARGET_HOME/noVNC" ]; then
    echo -e "${YELLOW}  Clonando noVNC...${NC}"
    sudo -u $TARGET_USER git clone https://github.com/novnc/noVNC.git $TARGET_HOME/noVNC
    sudo -u $TARGET_USER git clone https://github.com/novnc/websockify $TARGET_HOME/noVNC/utils/websockify
fi

for i in $(seq 1 12); do
    DISPLAY_NUM=$i
    VNC_PORT=$((5899 + $i))
    WEB_PORT=$((6079 + $i))  # 6080, 6081, ..., 6091
    SERVICE_NAME="novnc-display-$i.service"

    cat > /etc/systemd/system/$SERVICE_NAME <<EOF
[Unit]
Description=noVNC for Display :$DISPLAY_NUM
After=x11vnc-display-$i.service
Requires=x11vnc-display-$i.service

[Service]
Type=simple
User=$TARGET_USER
WorkingDirectory=$TARGET_HOME/noVNC
ExecStart=$TARGET_HOME/noVNC/utils/novnc_proxy \\
    --vnc localhost:$VNC_PORT \\
    --listen $WEB_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME

    echo -e "${GREEN}  ✅ noVNC Display :$DISPLAY_NUM porta web $WEB_PORT iniciado${NC}"
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ SETUP COMPLETO!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}📋 Informações de Acesso:${NC}"
echo ""

for i in $(seq 1 12); do
    WEB_PORT=$((6079 + $i))
    echo -e "  Display :$i → http://$(hostname -I | awk '{print $1}'):$WEB_PORT/vnc.html"
done

echo ""
echo -e "${YELLOW}🔑 Senhas VNC:${NC}"
echo -e "  Arquivo: $TARGET_HOME/.vnc/passwords.txt"
echo ""
echo -e "${YELLOW}🔧 Gerenciar Serviços:${NC}"
echo -e "  Parar tudo:     sudo systemctl stop xvfb-display-*.service x11vnc-display-*.service novnc-display-*.service"
echo -e "  Iniciar tudo:   sudo systemctl start xvfb-display-*.service x11vnc-display-*.service novnc-display-*.service"
echo -e "  Status:         sudo systemctl status xvfb-display-1.service"
echo ""
echo -e "${GREEN}========================================${NC}"
```

### **Passo 2: Dar Permissão de Execução**

```bash
sudo chmod +x /usr/local/bin/setup_displays_vnc.sh
```

### **Passo 3: Executar o Script**

```bash
sudo /usr/local/bin/setup_displays_vnc.sh
```

**O que o script faz:**

1. ✅ Instala Xvfb, x11vnc, fonts
2. ✅ Gera 12 senhas VNC aleatórias (salvas em `~/.vnc/passwords.txt`)
3. ✅ Cria 12 serviços systemd para Xvfb (displays :1 a :12)
4. ✅ Cria 12 serviços systemd para x11vnc (portas 5900-5911)
5. ✅ Cria 12 serviços systemd para noVNC (portas 6080-6091)
6. ✅ Inicia tudo automaticamente
7. ✅ Configura para iniciar no boot

---

## 🧪 Testando os Displays

### **Teste 1: Verificar se Xvfb está rodando**

```bash
ps aux | grep Xvfb
```

**Saída esperada:**
```
ubuntu   1234  Xvfb :1 -screen 0 1920x1080x24
ubuntu   1235  Xvfb :2 -screen 0 1920x1080x24
...
ubuntu   1245  Xvfb :12 -screen 0 1920x1080x24
```

### **Teste 2: Verificar se x11vnc está rodando**

```bash
ss -tlnp | grep -E "590[0-9]|591[0-1]"
```

**Saída esperada:**
```
LISTEN 0  32  0.0.0.0:5900  0.0.0.0:*  users:(("x11vnc",pid=...))
LISTEN 0  32  0.0.0.0:5901  0.0.0.0:*  users:(("x11vnc",pid=...))
...
LISTEN 0  32  0.0.0.0:5911  0.0.0.0:*  users:(("x11vnc",pid=...))
```

### **Teste 3: Verificar se noVNC está rodando**

```bash
ss -tlnp | grep -E "608[0-9]|609[0-1]"
```

**Saída esperada:**
```
LISTEN 0  100  0.0.0.0:6080  0.0.0.0:*  users:(("python3",pid=...))
LISTEN 0  100  0.0.0.0:6081  0.0.0.0:*  users:(("python3",pid=...))
...
LISTEN 0  100  0.0.0.0:6091  0.0.0.0:*  users:(("python3",pid=...))
```

### **Teste 4: Abrir Chrome em Display Específico**

```bash
# Testar display :1
DISPLAY=:1 google-chrome --no-sandbox https://www.google.com &

# Acessar via VNC
# http://SEU_IP:6080/vnc.html
```

Você deve ver o Chrome aberto no display :1!

---

## 📝 Gerenciamento dos Serviços

### **Ver Status de Todos os Serviços**

```bash
# Status resumido
systemctl list-units --type=service | grep -E "(xvfb|x11vnc|novnc)"

# Status detalhado de um serviço
sudo systemctl status xvfb-display-1.service
sudo systemctl status x11vnc-display-1.service
sudo systemctl status novnc-display-1.service
```

### **Parar/Iniciar Serviços**

```bash
# Parar todos os displays
sudo systemctl stop xvfb-display-*.service x11vnc-display-*.service novnc-display-*.service

# Iniciar todos os displays
sudo systemctl start xvfb-display-*.service x11vnc-display-*.service novnc-display-*.service

# Reiniciar display específico
sudo systemctl restart xvfb-display-3.service x11vnc-display-3.service novnc-display-3.service
```

### **Ver Logs de um Serviço**

```bash
# Logs do Xvfb display 1
sudo journalctl -u xvfb-display-1.service -f

# Logs do x11vnc display 1
sudo journalctl -u x11vnc-display-1.service -f

# Logs do noVNC display 1
sudo journalctl -u novnc-display-1.service -f
```

---

## 🔑 Gerenciamento de Senhas VNC

### **Ver Todas as Senhas**

```bash
cat ~/.vnc/passwords.txt
```

**Saída:**
```
Display :1 - Senha: XyZ123AbC456DeF7
Display :2 - Senha: AbC789DeF012GhI3
...
Display :12 - Senha: MnO456PqR789StU0
```

### **Trocar Senha de um Display**

```bash
# Gerar nova senha para display :3
NOVA_SENHA=$(openssl rand -base64 16 | tr -d "=+/" | cut -c1-16)
echo "$NOVA_SENHA" | x11vnc -storepasswd ~/.vnc/passwd_display_03 -usepw

# Reiniciar x11vnc do display 3
sudo systemctl restart x11vnc-display-3.service

# Atualizar arquivo de senhas
sed -i "s/^Display :3 - Senha:.*$/Display :3 - Senha: $NOVA_SENHA/" ~/.vnc/passwords.txt

echo "Nova senha display :3: $NOVA_SENHA"
```

---

## 🌐 Acessando via Browser

### **URLs de Acesso**

Substitua `SEU_IP` pelo IP público do servidor:

```
Display :1  → http://SEU_IP:6080/vnc.html
Display :2  → http://SEU_IP:6081/vnc.html
Display :3  → http://SEU_IP:6082/vnc.html
Display :4  → http://SEU_IP:6083/vnc.html
Display :5  → http://SEU_IP:6084/vnc.html
Display :6  → http://SEU_IP:6085/vnc.html
Display :7  → http://SEU_IP:6086/vnc.html
Display :8  → http://SEU_IP:6087/vnc.html
Display :9  → http://SEU_IP:6088/vnc.html
Display :10 → http://SEU_IP:6089/vnc.html
Display :11 → http://SEU_IP:6090/vnc.html
Display :12 → http://SEU_IP:6091/vnc.html
```

### **Conectar com Senha**

1. Abra a URL no browser
2. Clique em "Connect"
3. Digite a senha (consulte `~/.vnc/passwords.txt`)
4. Pronto! Você verá o display virtual

---

## ⚙️ Configurações Avançadas

### **Ajustar Resolução dos Displays**

Edite o serviço:

```bash
sudo nano /etc/systemd/system/xvfb-display-1.service
```

Mude a linha `ExecStart`:

```ini
# Resolução 1920x1080 (Full HD)
ExecStart=/usr/bin/Xvfb :1 -screen 0 1920x1080x24

# Resolução 1280x720 (HD - usa menos recursos)
ExecStart=/usr/bin/Xvfb :1 -screen 0 1280x720x24

# Resolução 2560x1440 (2K - para telas grandes)
ExecStart=/usr/bin/Xvfb :1 -screen 0 2560x1440x24
```

Depois:

```bash
sudo systemctl daemon-reload
sudo systemctl restart xvfb-display-1.service
```

### **Limitar Conexões Simultâneas por Display**

Edite o serviço x11vnc:

```bash
sudo nano /etc/systemd/system/x11vnc-display-1.service
```

Adicione `-noshared` para permitir apenas 1 conexão:

```ini
ExecStart=/usr/bin/x11vnc \
    -display :1 \
    -forever \
    -noshared \    # ← Adicionar esta linha
    ...
```

---

## 🐛 Troubleshooting

### **Problema: Display não inicia**

```bash
# Ver logs
sudo journalctl -u xvfb-display-1.service -n 50

# Testar manualmente
Xvfb :99 -screen 0 1920x1080x24
# Se funcionar, o problema é no serviço systemd
```

### **Problema: x11vnc não conecta**

```bash
# Ver logs
sudo journalctl -u x11vnc-display-1.service -n 50

# Testar manualmente
DISPLAY=:1 x11vnc -display :1 -rfbport 5999
# Tentar conectar em localhost:5999
```

### **Problema: noVNC "Connection failed"**

```bash
# Ver logs
sudo journalctl -u novnc-display-1.service -n 50

# Verificar se x11vnc está respondendo
nc -zv localhost 5900  # Deve retornar "succeeded"

# Testar noVNC manualmente
cd ~/noVNC
./utils/novnc_proxy --vnc localhost:5900 --listen 7000
# Acessar http://localhost:7000/vnc.html
```

### **Problema: Porta já em uso**

```bash
# Descobrir que processo está usando a porta
sudo lsof -i :5900

# Matar processo
sudo kill -9 PID
```

---

## 📊 Monitoramento de Recursos

### **Ver Uso de RAM por Display**

```bash
ps aux --sort=-%mem | grep -E "(Xvfb|x11vnc|chrome)" | head -20
```

### **Ver Uso de CPU**

```bash
top -p $(pgrep -d',' -f 'Xvfb|x11vnc')
```

### **Limpar Displays Inativos**

Se um display travar:

```bash
# Parar serviços
sudo systemctl stop xvfb-display-5.service x11vnc-display-5.service novnc-display-5.service

# Limpar processos órfãos
pkill -9 -f "Xvfb :5"
pkill -9 -f "x11vnc.*:5"

# Reiniciar
sudo systemctl start xvfb-display-5.service x11vnc-display-5.service novnc-display-5.service
```

---

## 🚀 Próximo Passo

Displays configurados! Agora:

**→ [04-SEGURANCA-VNC.md](./04-SEGURANCA-VNC.md)**

Implementar sistema de tokens temporários e autenticação.

---

**Última atualização:** 2025-10-20
