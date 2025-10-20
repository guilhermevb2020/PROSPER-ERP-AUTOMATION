# ✅ SETUP COMPLETO - PROSPER-ERP-AUTOMATION

## 📦 O QUE FOI INSTALADO

### 1. Ambiente Virtual Python
```
✅ venv/ - Ambiente isolado
✅ Python 3.12.3
✅ pip 25.2
```

### 2. Dependências Python (instaladas no venv)
```
✅ nodriver 0.47.0        - Automação web anti-detecção (PRINCIPAL)
✅ selenium 4.27.1         - Fallback
✅ capsolver 1.0.0         - CAPTCHA solver
✅ pandas 2.2.3            - Processamento de dados
✅ python-dotenv 1.1.0     - Variáveis de ambiente
✅ + 20 outras dependências
```

### 3. Sistema Operacional (Ubuntu 24.04)
```
✅ Google Chrome 141.0.7390.107
✅ xvfb              - Display virtual
✅ x11vnc            - VNC server (porta 5900)
✅ fluxbox           - Window manager
```

### 4. Scripts e Documentação
```
✅ start_automation.sh    - Inicia ambiente completo
✅ COMO_USAR.md          - Guia de uso
✅ SETUP_COMPLETO.md     - Este arquivo
✅ NODRIVER_MIGRATION_COMPLETE.md - Detalhes da migração
```

---

## 🚀 COMO USAR

### Passo 1: Criar arquivo .env

```bash
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
nano .env
```

Adicione suas credenciais:

```env
# SmartSecurities Login
SMART_EMAIL=seu_email@example.com
SMART_PASSWORD=sua_senha_aqui

# CapSolver API (opcional - extensão resolve local)
CAPSOLVER_API_KEY=CAP-XXXXXXXXX

# Display Virtual
DISPLAY=:1
```

### Passo 2: Iniciar Ambiente

```bash
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
./start_automation.sh
```

Isso vai:
- ✅ Iniciar Xvfb (display virtual :1)
- ✅ Iniciar x11vnc (VNC porta 5900)
- ✅ Ativar ambiente virtual
- ✅ Configurar PYTHONPATH e DISPLAY

### Passo 3: Conectar via VNC (para ver o Chrome)

Use um cliente VNC (RealVNC, TightVNC, etc):

```
Servidor: <SEU_IP>:5900
Senha: (sem senha)
```

**Exemplo:**
```
ec2-54-123-45-67.compute-1.amazonaws.com:5900
```

### Passo 4: Executar o Processador

No terminal (após `./start_automation.sh`):

```bash
python src/processors/web/titulos_abertos_e_marcados_recompras.py
```

**Controles:**
- `P` - Pausar
- `R` - Retomar
- `Q` - Parar

---

## ⚙️ CONFIGURAÇÕES IMPORTANTES

### 1. Firewall (porta VNC)

Se não conseguir conectar via VNC:

```bash
sudo ufw allow 5900
sudo ufw status
```

### 2. Extensão CapSolver (IMPORTANTE!)

**Via VNC:**

1. Conecte via VNC
2. Abra Chrome: `DISPLAY=:1 google-chrome`
3. Acesse: `chrome://extensions/`
4. Ative "Modo desenvolvedor"
5. Instale CapSolver:
   - Chrome Web Store → "CapSolver"
   - OU baixe: https://www.capsolver.com/
6. Configure API key (opcional)
7. Ative "Auto Solve"

**Sem extensão = CAPTCHA manual!**

---

## 📂 ESTRUTURA DO PROJETO

```
/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION/
│
├── venv/                                # Ambiente virtual
│   └── lib/python3.12/site-packages/   # Pacotes instalados
│
├── src/
│   ├── processors/web/
│   │   └── titulos_abertos_e_marcados_recompras.py  # Processador principal
│   ├── common/
│   │   └── nodriver_utils.py           # Utilitários Nodriver
│   └── core/
│       ├── logging_config.py           # Configuração de logs
│       └── timezone_utils.py           # Utilitários de timezone
│
├── data/
│   └── raw_inputs/                     # CSVs baixados salvos aqui
│
├── logs/
│   └── processors/                     # Logs de execução
│
├── .env                                 # ⚠️ CRIAR! (credenciais)
├── requirements.txt                     # Dependências
├── start_automation.sh                  # Script de inicialização
│
└── Documentação:
    ├── COMO_USAR.md
    ├── SETUP_COMPLETO.md (este arquivo)
    └── NODRIVER_MIGRATION_COMPLETE.md
```

---

## 🧪 TESTE RÁPIDO

Verificar se tudo está funcionando:

```bash
# 1. Ativar venv
source venv/bin/activate

# 2. Configurar variáveis
export PYTHONPATH=/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
export DISPLAY=:1

# 3. Testar import
python3 -c "import src.processors.web.titulos_abertos_e_marcados_recompras; print('✅ OK')"

# 4. Verificar Chrome
google-chrome --version

# 5. Verificar Xvfb (se já rodou start_automation.sh)
ps aux | grep Xvfb
```

---

## 🔧 COMANDOS ÚTEIS

### Ver processos rodando
```bash
ps aux | grep -E "Xvfb|x11vnc"
```

### Parar tudo
```bash
pkill Xvfb
pkill x11vnc
```

### Verificar porta VNC
```bash
netstat -tlnp | grep 5900
```

### Ver logs do processador
```bash
tail -f logs/processors/*.log
```

### Limpar CSVs antigos
```bash
rm -f data/raw_inputs/*.csv
```

---

## 🐛 TROUBLESHOOTING

### Erro: "No module named 'src'"

**Solução:**
```bash
export PYTHONPATH=/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
```

Ou use o script:
```bash
./start_automation.sh
```

### Erro: "Chrome not found"

**Solução:**
```bash
# Reinstalar Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f -y
```

### Erro: "Cannot open display :1"

**Solução:**
```bash
# Reiniciar Xvfb
pkill Xvfb
Xvfb :1 -screen 0 1920x1080x24 &
export DISPLAY=:1
```

### VNC não conecta

**Solução:**
```bash
# 1. Verificar firewall
sudo ufw allow 5900

# 2. Reiniciar x11vnc
pkill x11vnc
x11vnc -display :1 -forever -nopw -quiet -bg

# 3. Verificar se está rodando
netstat -tlnp | grep 5900
```

### CAPTCHA não resolve automaticamente

**Causa:** Extensão CapSolver não instalada

**Solução:**
1. Conecte via VNC
2. Abra Chrome: `DISPLAY=:1 google-chrome`
3. Instale extensão CapSolver
4. Ative "Auto Solve"

---

## ✅ CHECKLIST ANTES DE RODAR

- [ ] Arquivo `.env` criado com credenciais
- [ ] Ambiente virtual ativo (`source venv/bin/activate`)
- [ ] Xvfb rodando (`ps aux | grep Xvfb`)
- [ ] x11vnc rodando (`ps aux | grep x11vnc`)
- [ ] VNC conectando
- [ ] Chrome instalado (`google-chrome --version`)
- [ ] Extensão CapSolver instalada (via VNC)
- [ ] `PYTHONPATH` configurado
- [ ] `DISPLAY=:1` configurado

---

## 🎯 EXECUTAR AGORA

```bash
# Tudo em um comando:
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION && \
./start_automation.sh

# Depois, no shell que abrir:
python src/processors/web/titulos_abertos_e_marcados_recompras.py
```

---

## 📊 FLUXO COMPLETO

```
1. ./start_automation.sh
   ↓
2. Xvfb :1 iniciado
   ↓
3. x11vnc porta 5900 iniciado
   ↓
4. venv ativado + PYTHONPATH configurado
   ↓
5. python src/processors/web/titulos_abertos_e_marcados_recompras.py
   ↓
6. Nodriver abre Chrome no display :1
   ↓
7. Login automático
   ↓
8. Extensão CapSolver resolve CAPTCHA
   ↓
9. Loop infinito:
   - Extração COM checkbox recompra → CSV
   - Extração SEM checkbox recompra → CSV
   - Aguardar 60s
   - Repetir
```

---

## 📝 LOGS

Logs salvos em:
```
logs/processors/titulos_abertos_e_marcados_recompras_YYYY_MM_DD.log
```

Ver em tempo real:
```bash
tail -f logs/processors/*.log
```

---

## 🚨 IMPORTANTE

1. **NUNCA compartilhe o arquivo `.env`** (contém senhas!)
2. **Extensão CapSolver é obrigatória** para CAPTCHA automático
3. **Firewall deve permitir porta 5900** para VNC
4. **Use `./start_automation.sh`** para configurar tudo automaticamente

---

**Tudo pronto! 🎉**

Consulte [COMO_USAR.md](COMO_USAR.md) para mais detalhes.
