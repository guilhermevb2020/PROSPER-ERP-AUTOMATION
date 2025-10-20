# 🤖 PROSPER-ERP-AUTOMATION

Sistema de automação web para extração de dados do ERP SmartSecurities via Selenium.

---

## 📋 Visão Geral

Este projeto contém **automações web** que requerem navegador Chrome e interação humana ocasional (resolução de CAPTCHAs). É separado do projeto principal (`PROSPER_DATA_HUB`) que contém processadores API headless.

### Por que separado?

- ✅ **Isolamento**: Automações web não afetam processadores API
- ✅ **Recursos**: Chrome consome muita RAM/CPU
- ✅ **Escalabilidade**: Pode rodar em VM dedicada
- ✅ **Manutenção**: Atualiza independentemente

---

## 🏗️ Arquitetura

```
PROSPER-ERP-AUTOMATION/
├── src/
│   ├── processors/
│   │   └── web/
│   │       └── titulos_abertos_e_marcados_recompras.py
│   ├── common/
│   │   ├── selenium_utils.py      # Stealth mode, anti-detection
│   │   └── timezone_utils.py      # Timezone Brasília
│   ├── core/
│   │   └── logging_config.py      # Logger configurado
│   └── config/
├── data/
│   ├── raw_inputs/                # CSVs baixados
│   ├── processed_outputs/         # Dados processados
│   └── checkpoints/               # Controle de progresso
├── logs/                          # Logs rotativos
├── scripts/
│   ├── setup/                     # Instalação VNC, Chrome
│   ├── vnc/                       # Gerenciamento VNC
│   └── maintenance/               # Limpeza, backup
├── config/                        # Configurações VNC, systemd
├── docs/                          # Documentação
└── temp/                          # Arquivos temporários
```

---

## 🚀 Instalação

### Pré-requisitos

- Ubuntu 20.04+ (ou similar)
- Python 3.12+
- Google Chrome
- Xvfb + VNC (para ambiente headless)

### Passo 1: Clonar e Configurar

```bash
cd /home/ubuntu/automacoes
# (ou copiar pasta PROSPER-ERP-AUTOMATION para nova VM)

cd PROSPER-ERP-AUTOMATION
```

### Passo 2: Criar Virtualenv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Passo 3: Configurar Variáveis de Ambiente

```bash
cp .env.example .env
nano .env
```

Preencher:
```env
# Credenciais SmartSecurities
SMART_EMAIL=seu_email@prosper.com.br
SMART_PASSWORD=sua_senha

# CapSolver API
CAPSOLVER_API_KEY=CAP-xxxxxxxxxx

# Logs
APP_LOG_LEVEL=INFO
```

### Passo 4: Instalar Chrome

```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get -f install
```

### Passo 5: Instalar VNC (opcional - para servidor headless)

```bash
sudo apt install -y xvfb tigervnc-standalone-server xfce4

# Criar senha VNC
vncpasswd

# Configurar xstartup
mkdir -p ~/.vnc
echo '#!/bin/bash
xrdb $HOME/.Xresources
startxfce4 &' > ~/.vnc/xstartup
chmod +x ~/.vnc/xstartup

# Iniciar VNC
vncserver :1 -geometry 1920x1080 -depth 24
```

---

## 🎮 Como Usar

### Execução Manual (com display)

```bash
# Se tem interface gráfica (desktop Linux)
python -m src.processors.web.titulos_abertos_e_marcados_recompras
```

### Execução com VNC (servidor headless)

```bash
# Iniciar VNC se não estiver rodando
vncserver :1 -geometry 1920x1080 -depth 24

# Rodar automação no display virtual
DISPLAY=:1 python -m src.processors.web.titulos_abertos_e_marcados_recompras

# Do seu computador, conecte VNC:
# vncviewer SERVIDOR_IP:5901
```

### Controles Interativos

Durante a execução:
- **P** - Pausar
- **R** - Retomar
- **S** ou **Q** - Parar

---

## 🔧 Automações Disponíveis

### 1. Títulos Abertos e Marcados para Recompra

**Arquivo:** `src/processors/web/titulos_abertos_e_marcados_recompras.py`

**O que faz:**
- Extrai 2 CSVs: COM e SEM marcação de recompra
- Resolve CAPTCHAs automaticamente (CapSolver)
- Executa em loop a cada 60 segundos

**Como rodar:**
```bash
python -m src.processors.web.titulos_abertos_e_marcados_recompras
```

---

## 📁 Arquivos Gerados

```
data/raw_inputs/
├── titulos_abertos_marcados_recompras_YYYY_MM_DD_HHMMSS.csv  (25KB)
└── titulos_abertos_YYYY_MM_DD_HHMMSS.csv                     (2.8MB)
```

---

## 🛠️ Troubleshooting

### Chrome não abre

```bash
# Verificar se Chrome está instalado
google-chrome --version

# Testar manualmente
google-chrome --no-sandbox
```

### VNC não conecta

```bash
# Verificar se VNC está rodando
vncserver -list

# Reiniciar VNC
vncserver -kill :1
vncserver :1 -geometry 1920x1080 -depth 24
```

### CAPTCHA não resolve

1. Verificar se extensão CapSolver está instalada
2. Verificar API Key no `.env`
3. Verificar créditos no dashboard: https://dashboard.capsolver.com/

---

## 📊 Monitoramento

### Logs

```bash
# Ver logs em tempo real
tail -f logs/app.log.$(date +%Y-%m-%d)

# Filtrar erros
grep "ERROR" logs/app.log.$(date +%Y-%m-%d)
```

### Recursos

```bash
# Ver uso de RAM/CPU
htop

# Ver processo Python
ps aux | grep titulos_abertos_e_marcados_recompras
```

---

## 🔒 Segurança

- ✅ Credenciais em `.env` (nunca commitar)
- ✅ VNC com senha
- ✅ SSH tunnel para VNC (recomendado)
- ✅ Stealth mode para evitar detecção de bots

---

## 📞 Suporte

- **Equipe TI**: ti@prosper.com.br
- **Documentação completa**: `docs/`

---

## 🎯 Roadmap

- [ ] Adicionar noVNC (VNC no navegador)
- [ ] Sistema de notificação (email quando CAPTCHA travar)
- [ ] Dashboard de monitoramento
- [ ] Múltiplas automações em paralelo
- [ ] Filas de execução

---

<div align="center">
  <sub>Desenvolvido pela equipe de TI da Prosper Capital</sub><br>
  <sub>Última atualização: 2025-10-17</sub>
</div>
