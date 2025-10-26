# 🖥️ Como Acessar o VNC - PROSPER-ERP-AUTOMATION

Este documento explica como acessar remotamente a interface gráfica (Chrome) da automação PROSPER-ERP rodando no servidor AWS.

---

## 📋 Índice

1. [Informações de Acesso](#informações-de-acesso)
2. [Acesso via Navegador (Recomendado)](#acesso-via-navegador-recomendado)
3. [Acesso via Cliente VNC](#acesso-via-cliente-vnc)
4. [Solução de Problemas](#solução-de-problemas)
5. [Alterando a Senha](#alterando-a-senha)

---

## 🔐 Informações de Acesso

| Item | Valor |
|------|-------|
| **Endereço IP** | `3.148.126.73` |
| **Porta Web (noVNC)** | `6080` |
| **Porta VNC Direta** | `5900` |
| **Senha** | `vetor2025` |
| **URL Completa** | http://3.148.126.73:6080/vnc.html |

---

## 🌐 Acesso via Navegador (Recomendado)

Esta é a forma **mais fácil e rápida** de acessar o VNC, sem precisar instalar nada.

### Passo a Passo:

1. **Abra seu navegador** (Chrome, Firefox, Edge, Safari)

2. **Acesse a URL:**
   ```
   http://3.148.126.73:6080/vnc.html
   ```

3. **Tela de Conexão:**
   - Você verá a interface do noVNC
   - Clique no botão **"Connect"**

4. **Digite a Senha:**
   - Senha: `vetor2025`
   - Pressione **Enter** ou clique em **"Send Credentials"**

5. **Pronto!** 🎉
   - Você verá o desktop virtual
   - Quando a automação estiver rodando, verá o Chrome em ação

### Versão Lite (Mais Leve):

Se a conexão estiver lenta, use a versão lite:
```
http://3.148.126.73:6080/vnc_lite.html
```

---

## 🖥️ Acesso via Cliente VNC

Se preferir usar um cliente VNC tradicional (mais estável para conexões longas):

### Clientes Recomendados:

- **Windows/Mac/Linux:** [RealVNC Viewer](https://www.realvnc.com/pt/connect/download/viewer/)
- **Windows:** [TightVNC](https://www.tightvnc.com/)
- **Mac:** [VNC Viewer](https://apps.apple.com/br/app/vnc-viewer/id352019548)
- **Linux:** `vncviewer` (via apt/yum)

### Configuração:

1. **Instale um cliente VNC** (links acima)

2. **Configure a conexão:**
   - **Servidor:** `3.148.126.73:5900`
   - **OU apenas:** `3.148.126.73` (porta 5900 é padrão)

3. **Conecte:**
   - Clique em "Connect"
   - Digite a senha: `vetor2025`

4. **Pronto!** Você verá o desktop virtual

---

## 🔧 Solução de Problemas

### ❌ Problema: "Conexão recusada" ou "Cannot connect"

**Causas possíveis:**
1. Serviços VNC não estão rodando
2. Firewall AWS bloqueando a porta 6080

**Solução:**

1. **Verificar se serviços estão rodando** (no servidor via SSH):
   ```bash
   ps aux | grep -E "(Xvfb|x11vnc|novnc)"
   ```

2. **Reiniciar serviços:**
   ```bash
   cd /home/ubuntu/PROSPER-ERP-AUTOMATION
   ./start_automation.sh
   ```

3. **Verificar Security Group AWS:**
   - Acesse o console AWS EC2
   - Vá em "Security Groups"
   - Certifique-se que a porta **6080** está aberta para **0.0.0.0/0** (ou seu IP)

---

### ❌ Problema: "Senha incorreta" ou "Authentication failed"

**Solução:**

1. **Verificar senha atual:**
   - A senha padrão é: `vetor2025`
   - Certifique-se de estar digitando corretamente (case-sensitive)

2. **Recriar senha** (no servidor via SSH):
   ```bash
   x11vnc -storepasswd /home/ubuntu/.vnc/passwd
   # Digite a nova senha duas vezes
   ```

3. **Reiniciar x11vnc:**
   ```bash
   pkill x11vnc
   x11vnc -display :1 -forever -rfbauth /home/ubuntu/.vnc/passwd -quiet -bg -rfbport 5900
   ```

---

### ❌ Problema: "Tela preta" ou "Desktop vazio"

**Causas possíveis:**
1. Xvfb não está rodando
2. Display :1 não está configurado

**Solução:**

1. **Verificar Xvfb:**
   ```bash
   ps aux | grep Xvfb
   ```

2. **Reiniciar Xvfb:**
   ```bash
   pkill Xvfb
   Xvfb :1 -screen 0 1920x1080x24 &
   ```

3. **Reiniciar todos os serviços:**
   ```bash
   cd /home/ubuntu/PROSPER-ERP-AUTOMATION
   ./start_automation.sh
   ```

---

### ❌ Problema: Página mostra "lista de arquivos" em vez do noVNC

**Solução:**

Você precisa acessar o arquivo `.html` específico:

- ✅ **Correto:** `http://3.148.126.73:6080/vnc.html`
- ❌ **Errado:** `http://3.148.126.73:6080/`

---

## 🔐 Alterando a Senha

### Método 1: Via Script Automático

1. **Edite o arquivo `.env` ou crie variável de ambiente:**
   ```bash
   export VNC_PASSWORD="sua_nova_senha"
   ```

2. **Recrie o arquivo de senha:**
   ```bash
   x11vnc -storepasswd sua_nova_senha /home/ubuntu/.vnc/passwd
   chmod 600 /home/ubuntu/.vnc/passwd
   ```

3. **Reinicie x11vnc:**
   ```bash
   pkill x11vnc
   x11vnc -display :1 -forever -rfbauth /home/ubuntu/.vnc/passwd -quiet -bg -rfbport 5900
   ```

### Método 2: Via Comando Interativo

1. **Execute:**
   ```bash
   x11vnc -storepasswd /home/ubuntu/.vnc/passwd
   ```

2. **Digite a nova senha duas vezes**

3. **Reinicie x11vnc:**
   ```bash
   pkill x11vnc
   x11vnc -display :1 -forever -rfbauth /home/ubuntu/.vnc/passwd -quiet -bg -rfbport 5900
   ```

---

## 📊 Status dos Serviços

Para verificar se tudo está rodando corretamente:

```bash
# Verificar processos
ps aux | grep -E "(Xvfb|x11vnc|novnc)" | grep -v grep

# Verificar portas
netstat -tlnp | grep -E "(5900|6080)"

# Ou com ss (mais moderno)
ss -tlnp | grep -E "(5900|6080)"
```

**Saída esperada:**
```
tcp  0.0.0.0:5900  LISTEN  x11vnc
tcp  0.0.0.0:6080  LISTEN  python3 (websockify)
```

---

## 🚀 Iniciando a Automação

Depois de conectado ao VNC:

1. **No servidor (via SSH), execute:**
   ```bash
   cd /home/ubuntu/PROSPER-ERP-AUTOMATION
   ./run_processor.sh
   ```

2. **No VNC (via navegador):**
   - Você verá o Chrome abrindo automaticamente
   - A automação começará a executar
   - Controles:
     - **P** = Pausar
     - **R** = Retomar
     - **Q** = Parar

---

## 📞 Suporte

Se você encontrar problemas não listados aqui:

1. **Verifique os logs:**
   ```bash
   tail -f /home/ubuntu/PROSPER-ERP-AUTOMATION/logs/app.log
   ```

2. **Reinicie todos os serviços:**
   ```bash
   cd /home/ubuntu/PROSPER-ERP-AUTOMATION
   pkill Xvfb && pkill x11vnc && pkill -f novnc_proxy
   ./start_automation.sh
   ```

3. **Entre em contato com a equipe de desenvolvimento**

---

## 📝 Notas Importantes

- ⚠️ **Segurança:** A porta 6080 está aberta para a internet. Recomenda-se:
  - Usar uma senha forte
  - Restringir acesso a IPs específicos no Security Group AWS
  - Considerar usar um túnel SSH para acesso mais seguro

- 🔒 **Senha Padrão:** Altere a senha padrão `vetor2025` em produção

- 🌐 **IP Dinâmico:** Se o IP AWS mudar, atualize este documento

- 💾 **Backup:** O arquivo de senha está em `/home/ubuntu/.vnc/passwd`

---

**Última atualização:** 2025-10-20
**Versão:** 1.0
