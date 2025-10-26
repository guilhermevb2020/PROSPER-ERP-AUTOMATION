# 🚀 Guia Rápido - PROSPER-ERP-AUTOMATION

**Última atualização:** 2025-10-25

---

## ⚡ Início em 2 Minutos

### **1. Acessar o VNC**

Abra no navegador:
```
http://3.148.126.73:6080/vnc.html
```

**Senha:** `vetor2025`

---

### **2. Executar a Automação**

No terminal SSH:
```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate
export DISPLAY=:1
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION

python src/processors/web/relatorios_operacoes.py
```

**Pronto!** 🎉 Você verá o Chrome abrindo no VNC.

---

## ⌨️ Controles Durante Execução

| Tecla | Ação |
|-------|------|
| **P** | Pausar |
| **R** | Retomar |
| **Q** | Parar |

---

## 📂 Onde Ficam os Arquivos?

### **CSVs Baixados**
```bash
ls -lh data/raw_inputs/
```

Arquivos gerados:
```
relatorios_operacoes_2025_10_25_143052.csv
titulos_abertos_2025_10_25_143127.csv
```

### **Logs**
```bash
tail -f logs/app.log
```

---

## 🔧 Comandos Úteis

### **Reiniciar Ambiente Completo**
```bash
./restart_environment.sh
```

### **Parar Tudo**
```bash
pkill Xvfb && pkill x11vnc && pkill -f novnc_proxy && pkill -f "python.*processors"
```

### **Verificar Serviços Rodando**
```bash
ps aux | grep -E "(Xvfb|x11vnc|novnc|python.*processors)"
```

### **Verificar Portas**
```bash
ss -tlnp | grep -E "(5900|6080|6092)"
```

---

## 📧 Sistema de Notificações

### **O Que Acontece Quando CAPTCHA Trava?**

1. ⏸️ Automação **pausa** automaticamente
2. 📧 Email é enviado para você com 2 botões:
   - **🖥️ Acessar VNC** - Para resolver o problema
   - **▶️ Continuar Automação** - Para retomar após resolver

### **Como Retomar?**

**Opção 1:** Clique no botão "Continuar Automação" no email

**Opção 2:** Acesse diretamente:
```
http://3.148.126.73:6092/resume
```

**Opção 3:** Pressione `R` no terminal

---

## ❌ Problemas Comuns

### **VNC não conecta**
```bash
./restart_environment.sh
```

### **ModuleNotFoundError**
```bash
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
```

### **Cannot connect to browser**
```bash
pkill Xvfb
Xvfb :1 -screen 0 1920x1080x24 &
sleep 2
./restart_environment.sh
```

### **Tela preta no VNC**
```bash
# Verificar se Xvfb está rodando
ps aux | grep Xvfb

# Se não estiver, iniciar
Xvfb :1 -screen 0 1920x1080x24 &
```

---

## 🌐 Acessos Importantes

| Serviço | URL | Senha |
|---------|-----|-------|
| **VNC Web (Display :1)** | http://3.148.126.73:6080/vnc.html | `vetor2025` |
| **VNC Web (Display :2)** | http://3.148.126.73:6081/vnc.html | `vetor2025` |
| **API Controle** | http://3.148.126.73:6092 | - |
| **API Health Check** | http://3.148.126.73:6092/health | - |
| **API Status** | http://3.148.126.73:6092/status | - |

---

## 📊 Estrutura de Arquivos

```
PROSPER-ERP-AUTOMATION/
├── src/processors/web/
│   └── relatorios_operacoes.py    # Processador principal
│
├── data/
│   └── raw_inputs/                # CSVs baixados aqui
│
├── logs/
│   └── app.log                    # Logs de execução
│
├── venv/                          # Ambiente virtual Python
│
└── docs/                          # Documentação completa
```

---

## 📖 Documentação Completa

Para mais detalhes, consulte:

- **[README.md](README.md)** - Visão geral completa
- **[docs/ARQUITETURA.md](docs/ARQUITETURA.md)** - Arquitetura do sistema
- **[docs/CRIAR_PROCESSADOR.md](docs/CRIAR_PROCESSADOR.md)** - Como criar novos processadores
- **[docs/ACESSO_VNC.md](docs/ACESSO_VNC.md)** - Guia completo de acesso VNC
- **[docs/NOTIFICACOES.md](docs/NOTIFICACOES.md)** - Sistema de notificações
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Solução de problemas detalhada

---

## 🆘 Suporte

**Problemas não resolvidos?**

1. Consulte o [Troubleshooting](docs/TROUBLESHOOTING.md)
2. Verifique os logs: `tail -f logs/app.log`
3. Entre em contato com a equipe de TI

---

**Desenvolvido pela equipe de TI da Prosper Capital**
