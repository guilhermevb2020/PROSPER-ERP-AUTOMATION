# 🤖 PROSPER-ERP-AUTOMATION

**Sistema de automação web para extração de dados do ERP SmartSecurities usando Nodriver**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Nodriver](https://img.shields.io/badge/nodriver-0.47+-green.svg)](https://github.com/ultrafunkamsterdam/nodriver)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)]()

---

## 📋 Visão Geral

Sistema de automação web que extrai dados de títulos abertos do ERP **SmartSecurities** usando **Nodriver** (sucessor do undetected-chromedriver) para anti-detecção de bots.

### 🎯 O que faz:

- ✅ Extrai **2 CSVs** do SmartSecurities automaticamente:
  - Títulos abertos **marcados para recompra**
  - **Todos** os títulos abertos
- ✅ Resolve **CAPTCHAs** automaticamente via CapSolver
- ✅ Roda em **loop contínuo** (60 segundos entre ciclos)
- ✅ **Anti-detecção nativa** (Nodriver)
- ✅ **Simula comportamento humano** (movimentos de mouse, delays aleatórios)
- ✅ Acesso **remoto via navegador** (noVNC porta 6080)
- ✅ **Notificações por email** quando precisa intervenção (CAPTCHA, erros)
- ✅ **Controle remoto via API** (retomar automação de qualquer dispositivo)

### 🏗️ Por que separado do PROSPER_DATA_HUB?

- **Isolamento**: Automações web não afetam processadores API headless
- **Recursos**: Chrome consome muita RAM/CPU
- **Escalabilidade**: Pode rodar em VM dedicada AWS
- **Manutenção**: Atualiza independentemente

---

## 🚀 Início Rápido

### **1. Iniciar Displays VNC (EXECUTAR UMA VEZ)**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
./iniciar_vnc_displays.sh start
```

Isso inicia **10 displays virtuais** (:1 até :10) que ficam rodando permanentemente.

### **2. Acesse o VNC (ver automação rodando)**

```
🌐 Display :1 → http://3.148.126.73:6080/vnc.html
🌐 Display :2 → http://3.148.126.73:6081/vnc.html
...
🌐 Display :10 → http://3.148.126.73:6089/vnc.html
```

### **3. Execute um processador**

```bash
# Processador de relatório de deságio (Display :1)
DISPLAY=:1 python src/processors/web/relatorio_operacao_desagio.py
```

**Pronto!** Você verá o Chrome abrindo no VNC e a automação executando.

📖 **[Ver guia completo de acesso VNC](docs/ACESSO_VNC.md)**
📖 **[Ver convenções de portas](docs/CONVENCOES_PORTAS.md)**

---

## 📁 Estrutura do Projeto

```
PROSPER-ERP-AUTOMATION/
├── src/
│   ├── processors/web/
│   │   └── titulos_abertos_e_marcados_recompras.py  # Processador principal (822 linhas)
│   ├── common/
│   │   ├── nodriver_utils.py       # Utilitários Nodriver async
│   │   ├── timezone_utils.py       # Timezone Brasil (UTC-3)
│   │   └── reporting_utils.py      # Processamento de dados
│   └── core/
│       └── logging_config.py       # Logging com rotação diária
│
├── data/
│   ├── raw_inputs/                 # CSVs baixados salvos aqui
│   ├── processed_outputs/          # Dados processados
│   └── checkpoints/                # Controle de progresso
│
├── logs/                           # Logs rotativos (10 dias)
├── venv/                           # Ambiente virtual Python
├── docs/                           # Documentação detalhada
│
├── start_automation.sh             # 🚀 Inicia Xvfb + VNC + noVNC + ambiente Python
├── run_processor.sh                # 🚀 Executa o processador
├── requirements.txt                # Dependências Python
└── .env                            # Credenciais (NÃO commitado)
```

---

## ⚙️ Tecnologias

| Tecnologia | Versão | Função |
|------------|--------|--------|
| **Python** | 3.12+ | Linguagem principal |
| **Nodriver** | 0.47+ | Automação web anti-detecção (CORE) |
| **Selenium** | 4.27.1 | Fallback/legacy |
| **CapSolver** | 1.0.0 | Resolução automática de CAPTCHA |
| **Pandas** | 2.2.3 | Processamento de dados |
| **Xvfb** | - | Display virtual (headless) |
| **x11vnc** | - | Servidor VNC (porta 5900) |
| **noVNC** | - | VNC via browser (porta 6080) |

---

## 📦 Instalação e Setup

### **Pré-requisitos**

```bash
# Sistema
Ubuntu 20.04+ (ou similar)
Python 3.12+
Google Chrome
Xvfb + x11vnc

# Portas AWS abertas
5900 (VNC direto)
6080 (noVNC - acesso web)
```

### **Setup Completo**

```bash
# 1. Clonar/copiar projeto
cd /home/ubuntu
# Projeto já deve estar em /home/ubuntu/PROSPER-ERP-AUTOMATION

# 2. Criar ambiente virtual
cd PROSPER-ERP-AUTOMATION
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependências
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configurar credenciais
cp .env.example .env
nano .env
# Preencher SMART_EMAIL, SMART_PASSWORD, CAPSOLVER_API_KEY

# 5. Instalar noVNC (se não tiver)
cd /home/ubuntu
git clone https://github.com/novnc/noVNC.git
git clone https://github.com/novnc/websockify.git

# 6. Iniciar ambiente
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
./start_automation.sh
```

### **Arquivo .env**

```env
# SmartSecurities Login
SMART_EMAIL=seu_email@prosper.com.br
SMART_PASSWORD=sua_senha

# CapSolver API Key
CAPSOLVER_API_KEY=CAP-XXXXXXXXXX

# Display Virtual
DISPLAY=:1

# Logs
APP_LOG_LEVEL=INFO
```

---

## 🎮 Como Usar

### **Método 1: Script Automático (Recomendado)**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
./run_processor.sh
```

### **Método 2: Manual**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION

# Ativar ambiente
source venv/bin/activate
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
export DISPLAY=:1

# Executar
python3 src/processors/web/titulos_abertos_e_marcados_recompras.py
```

### **Controles Durante Execução**

- **P** - Pausar execução
- **R** - Retomar execução
- **Q** - Parar completamente

---

## 🌐 Acesso VNC

### **Via Navegador (Mais Fácil)**

```
URL: http://3.148.126.73:6080/vnc.html
Senha: vetor2025
```

### **Via Cliente VNC**

```
Servidor: 3.148.126.73:5900
Senha: vetor2025
```

📖 **[Guia completo de acesso VNC](docs/ACESSO_VNC.md)**

---

## 📊 Arquivos Gerados

```
data/raw_inputs/
├── titulos_abertos_marcados_recompras_2025_10_20_143052.csv  (~25KB)
└── titulos_abertos_2025_10_20_143127.csv                     (~2.8MB)
```

**Formato do nome:**
```
{nome}_{YYYY}_{MM}_{DD}_{HHMMSS}.csv
```

---

## 🔧 Scripts Utilitários

### **start_automation.sh**

Inicializa o ambiente completo:

```bash
./start_automation.sh
```

**O que faz:**
1. Verifica e mata processos Xvfb/x11vnc antigos
2. Inicia Xvfb no display :1
3. Cria senha VNC automática (se não existir)
4. Inicia x11vnc na porta 5900
5. Inicia noVNC na porta 6080
6. Ativa ambiente virtual Python
7. Configura PYTHONPATH e DISPLAY

### **run_processor.sh**

Executa o processador com ambiente configurado:

```bash
./run_processor.sh
```

---

## 📝 Logs

### **Localização**

```bash
logs/app.log               # Log atual
logs/app.log.2025-10-20    # Log rotativo diário
```

### **Ver logs em tempo real**

```bash
tail -f logs/app.log
```

### **Filtrar erros**

```bash
grep "ERROR" logs/app.log
```

### **Configuração de Logging**

- **Console**: Apenas CRITICAL
- **Arquivo**: INFO, DEBUG, WARNING, ERROR
- **Rotação**: Diária
- **Retenção**: 10 backups

---

## 🛠️ Troubleshooting

### **❌ "Cannot connect to browser"**

```bash
# Verificar se Xvfb está rodando
ps aux | grep Xvfb

# Reiniciar
pkill Xvfb
Xvfb :1 -screen 0 1920x1080x24 &
```

### **❌ "ModuleNotFoundError: No module named 'src'"**

```bash
# Configurar PYTHONPATH
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
```

### **❌ "VNC não conecta"**

```bash
# Verificar portas
netstat -tlnp | grep -E "(5900|6080)"

# Reiniciar serviços
pkill x11vnc && pkill -f novnc_proxy
./start_automation.sh
```

### **❌ "CAPTCHA não resolve"**

1. Verificar extensão CapSolver instalada no Chrome
2. Verificar API Key no `.env`
3. Código pausa automaticamente para resolução manual

📖 **[Guia completo de troubleshooting](docs/TROUBLESHOOTING.md)**

---

## 🔒 Segurança

### **Recomendações**

- ✅ Credenciais no `.env` (nunca commitar)
- ✅ VNC protegido com senha
- ✅ Restringir acesso à porta 6080 no AWS Security Group
- ⚠️ **Alterar senha padrão** `prosper2025` em produção
- ⚠️ Considerar túnel SSH para VNC em produção

### **Túnel SSH (Produção)**

```bash
# No seu computador
ssh -L 6080:localhost:6080 ubuntu@3.148.126.73

# Depois acesse
http://localhost:6080/vnc.html
```

---

## 📖 Documentação

### **Guias Rápidos**
- **[GUIA_RAPIDO.md](GUIA_RAPIDO.md)** - ⚡ Início em 2 minutos
- **[CHANGELOG.md](CHANGELOG.md)** - 📝 Histórico de versões

### **Documentação Técnica**
- **[docs/ARQUITETURA.md](docs/ARQUITETURA.md)** - 🏗️ Arquitetura completa do sistema
- **[docs/CRIAR_PROCESSADOR.md](docs/CRIAR_PROCESSADOR.md)** - 📘 Como criar novos processadores
- **[docs/ACESSO_VNC.md](docs/ACESSO_VNC.md)** - 🖥️ Guia completo de acesso VNC
- **[docs/NOTIFICACOES.md](docs/NOTIFICACOES.md)** - 📧 Sistema de notificações por email
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - 🔧 Solução de problemas

---

## 🎯 Status do Projeto

### **Versão Atual: 30.0** (2025-10-26)

- ✅ **Loop contínuo de 5 segundos** - Máxima velocidade de extração (60x mais rápido!)
- ✅ **Perfis temporários únicos** - Previne detecção de bot
- ✅ **Fechamento automático de tabs** - Fix crítico para download
- ✅ **Limpeza robusta** - Zero memory leaks
- ✅ **Documentação completa** - 1169 linhas detalhando cada etapa
- ✅ **Migração Nodriver completa** - 100% async/await (v26.0)
- ✅ **API CAPTCHA direta** - CapSolver sem extensão (v27.0)
- ✅ **Anti-detecção nativa** - Sem CDP detectável
- ✅ **VNC Web configurado** - Acesso porta 6080
- ✅ **Sistema de notificações** - Alertas por email
- ✅ **API de controle remoto** - Retomar de qualquer dispositivo
- ✅ **Isolamento por display** - 1 processador = 1 display VNC

### **Processadores Disponíveis:**
1. ✅ **relatorio_operacao_desagio.py** - Relatório de operação deságio (Display :1)
   - **Status:** ✅ 100% FUNCIONAL, PRODUÇÃO
   - **Loop:** 5 segundos entre ciclos
   - **CAPTCHA:** Automático via CapSolver HTTP
   - **Documentação:** [`docs/fluxos_processadores/relatorio_operacao_desagio.md`](docs/fluxos_processadores/relatorio_operacao_desagio.md)
2. ⏳ Mais processadores em desenvolvimento...

---

## 📞 Suporte

**Problemas ou dúvidas?**

1. Consulte a [documentação](docs/)
2. Verifique os [logs](logs/)
3. Entre em contato com a equipe de TI

---

## 📜 Licença

Propriedade da **Prosper Capital**. Todos os direitos reservados.

---

<div align="center">
  <sub>Desenvolvido pela equipe de TI da Prosper Capital</sub><br>
  <sub>Última atualização: 2025-10-25</sub>
</div>
