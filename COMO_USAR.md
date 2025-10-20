# Como Usar - Automação PROSPER ERP com Nodriver

## 🚀 Início Rápido

### 1. Iniciar o Ambiente (Display Virtual + VNC)

```bash
cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION
./start_automation.sh
```

Isso vai:
- ✅ Iniciar Xvfb (display virtual :1)
- ✅ Iniciar x11vnc (VNC na porta 5900)
- ✅ Ativar ambiente virtual Python
- ✅ Configurar DISPLAY=:1

### 2. Conectar via VNC (para visualizar o Chrome)

Use um cliente VNC (TightVNC, RealVNC, TigerVNC, etc.):

```
Servidor: <IP_DO_SERVIDOR>:5900
Senha: (sem senha configurada)
```

**Exemplo:**
```
52.12.34.56:5900
```

### 3. Executar o Processador

Dentro do ambiente (após `./start_automation.sh`):

```bash
python src/processors/web/titulos_abertos_e_marcados_recompras.py
```

**Controles durante execução:**
- **P** - Pausar
- **R** - Retomar
- **Q** - Parar

---

## 📁 Estrutura do Projeto

```
PROSPER-ERP-AUTOMATION/
├── venv/                           # Ambiente virtual Python
├── src/
│   ├── processors/web/
│   │   └── titulos_abertos_e_marcados_recompras.py  # Processador principal
│   └── common/
│       └── nodriver_utils.py       # Utilitários Nodriver
├── data/
│   └── raw_inputs/                 # CSVs baixados salvos aqui
├── requirements.txt                # Dependências Python
├── start_automation.sh             # Script de inicialização
└── .env                            # Credenciais (criar este arquivo!)
```

---

## ⚙️ Configuração Inicial

### 1. Criar arquivo `.env`

```bash
nano .env
```

Adicione suas credenciais:

```env
# SmartSecurities Login
SMART_EMAIL=seu_email@example.com
SMART_PASSWORD=sua_senha

# CapSolver API (opcional - extensão resolve local)
CAPSOLVER_API_KEY=CAP-XXXXXXXXX

# Display Virtual (Xvfb)
DISPLAY=:1
```

### 2. Instalar extensão CapSolver no Chrome

**Via VNC:**
1. Conecte via VNC ao servidor
2. Abra o Chrome manualmente: `DISPLAY=:1 google-chrome`
3. Vá em: `chrome://extensions/`
4. Ative "Modo do desenvolvedor"
5. Instale extensão CapSolver da Chrome Web Store
6. Configure API key na extensão (opcional)
7. Ative "Auto Solve"

**IMPORTANTE:** A extensão precisa estar instalada ANTES de rodar o processador!

---

## 🔧 Comandos Úteis

### Ver processos rodando
```bash
ps aux | grep -E "Xvfb|x11vnc"
```

### Parar serviços
```bash
pkill Xvfb
pkill x11vnc
```

### Verificar porta VNC
```bash
netstat -tlnp | grep 5900
```

### Testar display virtual
```bash
export DISPLAY=:1
xdpyinfo
```

### Limpar downloads antigos
```bash
rm -f data/raw_inputs/*.csv
```

---

## 🐛 Troubleshooting

### Problema: "Cannot open display :1"
```bash
# Reiniciar Xvfb
pkill Xvfb
Xvfb :1 -screen 0 1920x1080x24 &
```

### Problema: "VNC não conecta"
```bash
# Verificar firewall (porta 5900)
sudo ufw allow 5900

# Ou reiniciar x11vnc
pkill x11vnc
x11vnc -display :1 -forever -nopw -quiet -bg
```

### Problema: "Chrome não abre"
```bash
# Instalar Chrome (se não tiver)
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f
```

### Problema: "Nodriver não encontrado"
```bash
# Ativar ambiente virtual
source venv/bin/activate

# Reinstalar Nodriver
pip install nodriver>=0.33
```

### Problema: "CAPTCHA não resolve automaticamente"
1. Verifique se extensão CapSolver está instalada no Chrome
2. Verifique se "Auto Solve" está ativado
3. Se persistir → código pausa e você resolve manualmente via VNC

---

## 📊 Fluxo de Execução

```
1. start_automation.sh
   ↓
2. Xvfb :1 (display virtual)
   ↓
3. x11vnc (VNC porta 5900)
   ↓
4. source venv/bin/activate
   ↓
5. python src/processors/web/titulos_abertos_e_marcados_recompras.py
   ↓
6. Nodriver abre Chrome no display :1
   ↓
7. Login automático + CAPTCHA (extensão resolve)
   ↓
8. Loop infinito:
   - Extração COM checkbox recompra
   - Extração SEM checkbox recompra
   - Aguardar 60s
   - Repetir
```

---

## 📝 Logs

Logs são salvos em:
```
logs/processors/titulos_abertos_e_marcados_recompras_{data}.log
```

Ver logs em tempo real:
```bash
tail -f logs/processors/*.log
```

---

## 🎯 Próximos Passos

1. **Testar processador:**
   ```bash
   ./start_automation.sh
   python src/processors/web/titulos_abertos_e_marcados_recompras.py
   ```

2. **Verificar CSVs baixados:**
   ```bash
   ls -lah data/raw_inputs/
   ```

3. **Monitorar via VNC** para ver o Chrome rodando

4. **Criar cronjob** (opcional) para rodar automaticamente:
   ```bash
   crontab -e
   # Adicionar:
   # 0 */6 * * * cd /home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION && ./start_automation.sh && python src/processors/web/titulos_abertos_e_marcados_recompras.py
   ```

---

## ✅ Checklist de Validação

Antes de rodar o processador pela primeira vez:

- [ ] Ambiente virtual criado (`venv/`)
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] Xvfb instalado (`which Xvfb`)
- [ ] x11vnc instalado (`which x11vnc`)
- [ ] Arquivo `.env` criado com credenciais
- [ ] Extensão CapSolver instalada no Chrome
- [ ] VNC conectando corretamente
- [ ] Display :1 funcionando (`DISPLAY=:1 xdpyinfo`)

---

**Tudo pronto! 🚀**
