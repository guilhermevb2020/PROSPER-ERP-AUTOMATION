# 🖥️ Requisitos de Infraestrutura

**Versão:** 1.0
**Data:** Outubro 2025

---

## 📊 Especificação da Máquina Virtual

### **Configuração Mínima (POC - 2 automações)**

```
CPU:      4 cores
RAM:      8 GB
Disco:    50 GB SSD
OS:       Ubuntu 22.04 LTS (64-bit)
Rede:     IP público fixo
Provider: AWS EC2, Azure, GCP, ou servidor local
```

### **Configuração Recomendada (Produção - 12 automações)**

```
CPU:      16 cores (ou 8 cores com hyperthreading)
RAM:      32 GB
Disco:    200 GB SSD NVMe
OS:       Ubuntu 22.04 LTS (64-bit)
Rede:    IP público fixo + domínio (opcional)
Provider: AWS EC2 (t3.2xlarge ou superior)
          Azure (Standard_D8s_v3 ou superior)
          GCP (n2-standard-8 ou superior)
```

**Justificativa:**

| Componente | Consumo por Automação | Total (12 automações) |
|------------|----------------------|----------------------|
| **Chrome + Nodriver** | ~500 MB RAM | 6 GB RAM |
| **Xvfb (Display virtual)** | ~50 MB RAM | 600 MB RAM |
| **x11vnc** | ~20 MB RAM | 240 MB RAM |
| **noVNC** | ~30 MB RAM | 360 MB RAM |
| **Python + Processador** | ~100 MB RAM | 1.2 GB RAM |
| **Sistema Operacional** | - | 2 GB RAM |
| **Orquestrador + Buffer** | - | 4 GB RAM |
| **TOTAL** | ~700 MB/automação | **~15 GB RAM** |

**CPU:**
- Chrome é CPU-intensive (especialmente com anti-detecção Nodriver)
- Mínimo 1 core por 2 automações
- Recomendado 1 core por automação para performance ideal

**Disco:**
- Logs: ~100 MB/dia/automação = 1.2 GB/dia (12 auto) = 36 GB/mês
- Downloads (CSVs): ~10 MB/dia/automação = 120 MB/dia = 3.6 GB/mês
- Screenshots de erro: ~50 MB/dia (total)
- Sistema + Dependências: ~20 GB

---

## 🌐 Requisitos de Rede

### **Portas Necessárias**

| Serviço | Porta | Protocolo | Expor Publicamente? |
|---------|-------|-----------|---------------------|
| SSH | 22 | TCP | ⚠️ Sim (apenas IPs autorizados) |
| VNC #1 | 5900 | TCP | ❌ Não (usar noVNC) |
| VNC #2-12 | 5901-5911 | TCP | ❌ Não (usar noVNC) |
| noVNC #1 | 6080 | HTTP | ✅ Sim (com autenticação) |
| noVNC #2-12 | 6081-6091 | HTTP | ✅ Sim (com autenticação) |
| SMTP | 587 | TCP | ✅ Sim (outbound) |
| Dashboard (opcional) | 8080 | HTTP | ✅ Sim (com autenticação) |

### **Regras de Firewall (AWS Security Group)**

```bash
# SSH - Apenas IPs autorizados
Type: SSH
Port: 22
Source: SEU_IP/32
Description: SSH Admin Access

# noVNC - Acesso web ao VNC (portas 6080-6091)
Type: Custom TCP
Port range: 6080-6091
Source: 0.0.0.0/0  # ou restringir a IPs específicos
Description: noVNC Web Access

# SMTP Outbound - Para envio de emails
Type: Custom TCP (Outbound)
Port: 587
Destination: 0.0.0.0/0
Description: Email Alerts (SMTP)
```

### **Largura de Banda**

- **Download:** Mínimo 50 Mbps (100 Mbps recomendado)
- **Upload:** Mínimo 10 Mbps (50 Mbps recomendado para VNC)

**Por que?**
- VNC streaming: ~1-2 Mbps por conexão ativa
- Downloads de CSVs: pequeno (~100 KB)
- Acesso simultâneo via noVNC: até 3 pessoas = 6 Mbps

---

## 💾 Software Necessário

### **Sistema Operacional Base**

```bash
OS: Ubuntu 22.04 LTS Server (64-bit)
Kernel: 5.15 ou superior
```

### **Pacotes do Sistema**

```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Ferramentas essenciais
sudo apt install -y \
    build-essential \
    git \
    wget \
    curl \
    vim \
    htop \
    net-tools \
    ufw

# Display virtual (Xvfb)
sudo apt install -y \
    xvfb \
    x11vnc \
    xfonts-base \
    xfonts-75dpi \
    xfonts-100dpi

# Python 3.12+
sudo apt install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    python3-dev

# Google Chrome (para Nodriver)
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f -y

# noVNC (interface web para VNC)
git clone https://github.com/novnc/noVNC.git /home/ubuntu/noVNC
git clone https://github.com/novnc/websockify /home/ubuntu/noVNC/utils/websockify
```

### **Dependências Python**

```bash
# Criar virtualenv
python3 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install --upgrade pip
pip install \
    nodriver \
    python-dotenv \
    requests \
    pandas \
    openpyxl \
    psutil \
    schedule
```

### **Configuração de Email (SMTP)**

Opções:

**1. Gmail** (Fácil, para testes)
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu-email@gmail.com
SMTP_PASSWORD=senha-de-app  # Não a senha normal!
```

**2. SendGrid** (Recomendado para produção)
```env
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.xxx...  # API Key do SendGrid
```

**3. AWS SES** (Melhor para alta escala)
```env
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=AKIAIOSFODNN7EXAMPLE
SMTP_PASSWORD=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

---

## 🗂️ Estrutura de Diretórios

```
/home/ubuntu/
├── automacoes/
│   └── PROSPER-ERP-AUTOMATION/
│       ├── src/
│       │   ├── common/              # Utilit
ários compartilhados
│       │   ├── core/                # Configurações core
│       │   └── processors/          # Processadores (automações)
│       │       └── web/
│       │           ├── titulos_abertos_e_marcados_recompras.py
│       │           ├── titulos_vencidos.py  (futuro)
│       │           └── ...
│       │
│       ├── data/
│       │   ├── raw_inputs/          # CSVs baixados (12 subpastas)
│       │   │   ├── auto_01/
│       │   │   ├── auto_02/
│       │   │   └── ...
│       │   └── processed/           # CSVs processados
│       │
│       ├── logs/
│       │   ├── orquestrador/        # Logs do orquestrador
│       │   ├── automacao_01/        # Logs de cada automação
│       │   ├── automacao_02/
│       │   └── ...
│       │
│       ├── scripts/
│       │   ├── setup_vm.sh          # Setup completo da VM
│       │   ├── setup_displays.sh    # Configura 12 displays
│       │   ├── start_all.sh         # Inicia todas automações
│       │   └── stop_all.sh          # Para todas automações
│       │
│       ├── docs/                    # Documentação (este arquivo)
│       ├── venv/                    # Virtualenv Python
│       ├── .env                     # Variáveis de ambiente
│       └── requirements.txt
│
├── noVNC/                           # Interface web VNC
│   └── utils/
│       └── websockify/
│
└── .vnc/                            # Senhas VNC
    ├── passwd_display_01
    ├── passwd_display_02
    └── ...
```

---

## 🔒 Requisitos de Segurança

### **1. SSH**

```bash
# Desabilitar login root
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

# Usar apenas chave SSH (desabilitar senha)
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# Reiniciar SSH
sudo systemctl restart sshd
```

### **2. Firewall (UFW)**

```bash
# Ativar firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from SEU_IP to any port 22   # SSH
sudo ufw allow 6080:6091/tcp               # noVNC
sudo ufw enable
```

### **3. Fail2Ban** (Proteção contra ataques)

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### **4. Senhas VNC**

- ✅ SEMPRE usar senhas únicas para cada display
- ✅ Senhas com mínimo 12 caracteres
- ✅ Armazenar em `~/.vnc/passwd_display_XX`
- ❌ NUNCA usar `-nopw` em produção

---

## 💰 Estimativa de Custos (Cloud)

### **AWS EC2 (us-east-1)**

| Configuração | Instância | vCPUs | RAM | Custo/mês | Custo/ano |
|--------------|-----------|-------|-----|-----------|-----------|
| **POC (2 auto)** | t3.large | 2 | 8 GB | ~$60 | ~$720 |
| **Produção (12 auto)** | t3.2xlarge | 8 | 32 GB | ~$240 | ~$2,880 |
| **Alta Performance** | c6i.4xlarge | 16 | 32 GB | ~$490 | ~$5,880 |

**Adicionais:**
- EBS 200GB SSD: ~$20/mês
- IP Elástico: ~$3.60/mês
- Transferência de dados: ~$10/mês

**Total Produção:** ~$275/mês ou ~$3,300/ano

### **Azure (East US)**

| Configuração | VM Size | vCPUs | RAM | Custo/mês |
|--------------|---------|-------|-----|-----------|
| **POC** | Standard_D2s_v3 | 2 | 8 GB | ~$70 |
| **Produção** | Standard_D8s_v3 | 8 | 32 GB | ~$280 |

### **Servidor Local (On-Premise)**

| Componente | Especificação | Custo (uma vez) |
|------------|---------------|-----------------|
| **Servidor** | Dell PowerEdge T340 | $1,500 |
| **RAM** | 32GB DDR4 ECC | $200 |
| **SSD** | 500GB NVMe | $100 |
| **UPS** | 1500VA | $200 |
| **TOTAL** | - | **~$2,000** |

**Custos mensais:**
- Energia elétrica: ~$30/mês
- Internet dedicada: ~$100/mês

**Break-even:** 8-10 meses vs Cloud

---

## ⚙️ Configuração de IP e DNS (Opcional)

### **IP Fixo**

- **AWS:** Elastic IP (gratuito se associado)
- **Azure:** Public IP reservado (~$3/mês)
- **GCP:** Static external IP (~$7/mês)

### **Domínio (Opcional mas Recomendado)**

```
automacoes.suaempresa.com.br

Vantagens:
- URLs amigáveis: http://automacoes.suaempresa.com.br:6080
- Certificado SSL via Let's Encrypt
- Subdomínios por automação:
  - auto1.automacoes.suaempresa.com.br
  - auto2.automacoes.suaempresa.com.br
```

**Custo:** ~$15/ano (.com.br)

### **SSL/HTTPS (Altamente Recomendado)**

```bash
# Instalar Certbot
sudo apt install -y certbot

# Gerar certificado (requer domínio)
sudo certbot certonly --standalone -d automacoes.suaempresa.com.br

# Configurar noVNC com HTTPS
cd /home/ubuntu/noVNC
./utils/novnc_proxy \
    --vnc localhost:5900 \
    --listen 6080 \
    --cert /etc/letsencrypt/live/automacoes.suaempresa.com.br/fullchain.pem \
    --key /etc/letsencrypt/live/automacoes.suaempresa.com.br/privkey.pem
```

---

## 📋 Checklist de Preparação da VM

### **Antes de Iniciar:**

- [ ] VM provisionada com specs mínimas
- [ ] IP público fixo configurado
- [ ] Acesso SSH funcionando
- [ ] Firewall configurado
- [ ] Domínio apontado (se aplicável)

### **Instalação Básica:**

- [ ] Sistema atualizado (`apt update && apt upgrade`)
- [ ] Xvfb instalado e testado
- [ ] x11vnc instalado
- [ ] noVNC clonado e funcionando
- [ ] Python 3.12+ instalado
- [ ] Chrome instalado
- [ ] Git configurado

### **Configuração de Segurança:**

- [ ] SSH com chave (senha desabilitada)
- [ ] Firewall UFW ativo
- [ ] Fail2Ban instalado
- [ ] Senhas VNC geradas
- [ ] SSL configurado (se usar domínio)

### **Testes Iniciais:**

- [ ] Display virtual :1 funcionando
- [ ] x11vnc conectando
- [ ] noVNC acessível via web
- [ ] Chrome abre no display virtual
- [ ] Nodriver funciona
- [ ] Envio de email testado

---

## 🚀 Próximo Passo

Após validar os requisitos, prosseguir para:

**→ [03-SETUP-DISPLAYS-VNC.md](./03-SETUP-DISPLAYS-VNC.md)**

Scripts automatizados de configuração de 12 displays + VNC.

---

**Última atualização:** 2025-10-20
