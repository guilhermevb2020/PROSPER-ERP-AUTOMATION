# 🚀 Início Rápido - PROSPER-ERP-AUTOMATION

Guia super resumido para começar em **2 minutos**.

---

## ✅ Pré-requisitos

- ✅ Servidor AWS já configurado
- ✅ Porta 6080 aberta no Security Group
- ✅ Projeto em `/home/ubuntu/PROSPER-ERP-AUTOMATION`
- ✅ Dependências instaladas (`venv/`)

---

## 🎯 Passo 1: Acessar o VNC

**Abra no navegador:**
```
http://3.148.126.73:6080/vnc.html
```

**Senha:**
```
vetor2025
```

**Clique em "Connect"**

---

## 🎯 Passo 2: Executar a Automação

**No terminal SSH:**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
./run_processor.sh
```

**Pronto!** 🎉

Você verá o Chrome abrindo no VNC e a automação executando.

---

## ⌨️ Controles Durante Execução

| Tecla | Ação |
|-------|------|
| **P** | Pausar |
| **R** | Retomar |
| **Q** | Parar |

---

## 📂 Onde Ficam os CSVs?

```bash
ls -lh data/raw_inputs/
```

Você verá arquivos como:
```
titulos_abertos_marcados_recompras_2025_10_20_143052.csv
titulos_abertos_2025_10_20_143127.csv
```

---

## 🔧 Comandos Úteis

### Ver Logs
```bash
tail -f logs/app.log
```

### Reiniciar Ambiente
```bash
./start_automation.sh
```

### Parar Tudo
```bash
pkill Xvfb && pkill x11vnc && pkill -f novnc_proxy
```

### Verificar Serviços Rodando
```bash
ps aux | grep -E "(Xvfb|x11vnc|novnc)"
```

---

## ❌ Problemas Comuns

### "VNC não conecta"
```bash
./start_automation.sh
```

### "ModuleNotFoundError"
```bash
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
```

### "Cannot connect to browser"
```bash
pkill Xvfb
Xvfb :1 -screen 0 1920x1080x24 &
```

---

## 📖 Documentação Completa

- **[README.md](README.md)** - Visão geral completa
- **[ACESSO_VNC.txt](ACESSO_VNC.txt)** - Info rápida de acesso
- **[docs/COMO_ACESSAR_VNC.md](docs/COMO_ACESSAR_VNC.md)** - Guia completo VNC
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Solução de problemas

---

## 🎊 Pronto!

Agora você sabe executar a automação. Para mais detalhes, consulte o [README.md](README.md).
