# 📧 Sistema de Notificações por Email - PROSPER-ERP-AUTOMATION

Sistema inteligente de notificações que envia emails automáticos quando a automação precisa de intervenção humana (CAPTCHA, erros críticos, etc).

---

## 🎯 Objetivo

Permitir que **qualquer pessoa** (de qualquer dispositivo: celular, tablet, PC) possa:
1. **Receber alertas** quando a automação para
2. **Acessar o VNC** remotamente
3. **Resolver o problema** manualmente
4. **Retomar a automação** com um clique

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│  AUTOMAÇÃO DETECTA PROBLEMA (CAPTCHA, ERRO, ETC)               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. PAUSA AUTOMAÇÃO                                             │
│  2. ENVIA EMAIL VIA SMTP (MailerSend)                           │
│  3. INICIA API DE CONTROLE (Flask porta 6092)                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  USUÁRIO RECEBE EMAIL COM:                                      │
│  - Link VNC: http://3.148.126.73:6080/vnc.html                  │
│  - Link Continuar: http://3.148.126.73:6092/resume             │
└────────────────────────┬────────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
┌───────────────────┐         ┌────────────────────┐
│  OPÇÃO 1:         │         │  OPÇÃO 2:          │
│  Acessar VNC      │         │  Clicar "Continuar"│
│  Resolver problema│         │  (após resolver)   │
│  Pressionar [R]   │         │                    │
└─────────┬─────────┘         └─────────┬──────────┘
          │                             │
          └──────────────┬──────────────┘
                         ▼
          ┌──────────────────────────────┐
          │  AUTOMAÇÃO RETOMA EXECUÇÃO   │
          └──────────────────────────────┘
```

---

## 📁 Arquivos do Sistema

### **1. Módulo de Notificações**
```
src/common/notification_utils.py
```

**Funções principais:**
- `enviar_email_intervencao()` - Envia email genérico de intervenção
- `enviar_alerta_captcha()` - Email específico para CAPTCHA
- `enviar_alerta_erro_critico()` - Email para erros críticos
- `testar_envio_email()` - Testa configuração SMTP

### **2. API de Controle Remoto**
```
src/api/control_api.py
```

**Endpoints:**
- `GET /` - Info da API
- `GET /status` - Status da automação
- `GET /resume` - **Retoma execução**
- `GET /pause` - Pausa execução
- `GET /stop` - Para execução
- `GET /health` - Health check

### **3. Integração no Processador**
```
src/processors/web/titulos_abertos_e_marcados_recompras.py
```

**Modificações:**
- Importa `enviar_alerta_captcha` e `enviar_alerta_erro_critico`
- Importa `iniciar_api_controle`
- Adiciona `self.control_api` ao `__init__()`
- Inicia API no método `processar()`
- Envia email no timeout de CAPTCHA

---

## ⚙️ Configuração

### **Variáveis .env**

```env
# SMTP (já configurado)
SMTP_SERVER=smtp.mailersend.net
SMTP_PORT=2525
SMTP_USER=MS_D9Skx2@prosperfidc.online
SMTP_PASSWORD=__REMOVIDO_GUARDIAN__
EMAIL_FROM=prosperito@prosperfidc.online
EMAIL_RECIPIENT=guilherme@prosperinvest.com.br

# Servidor (configurado)
SERVER_IP=3.148.126.73
SERVER_PORT=6092
```

### **Porta AWS**

A porta **6092** já está aberta no Security Group AWS (range 6080-6095).

---

## 🚀 Como Funciona

### **Cenário 1: CAPTCHA Não Resolvido**

1. **Automação detecta timeout** (60 segundos)
2. **Pausa automaticamente**
3. **Envia email para:** `guilherme@prosperinvest.com.br`
4. **Email contém:**
   - Alerta de CAPTCHA não resolvido
   - Botão "🖥️ Acessar VNC"
   - Botão "▶️ Continuar Automação"
5. **Usuário clica em "Acessar VNC":**
   - Abre http://3.148.126.73:6080/vnc.html
   - Senha: `vetor2025`
   - Resolve CAPTCHA manualmente
6. **Usuário clica em "Continuar Automação":**
   - Abre http://3.148.126.73:6092/resume
   - Automação retoma execução
   - Mostra página de confirmação

### **Cenário 2: Erro Crítico**

1. **Automação encontra erro que não consegue recuperar**
2. **Pausa e envia email com detalhes do erro**
3. **Usuário:**
   - Acessa VNC
   - Analisa o problema
   - Clica em "Continuar" quando resolver

---

## 📧 Template do Email

O email é **responsivo** e funciona em:
- ✅ Desktop (Outlook, Gmail, etc)
- ✅ Mobile (celular)
- ✅ Tablet

**Elementos do email:**
- Header com gradiente roxo
- Badge de alerta vermelho
- Caixa amarela com mensagem do problema
- Informações (data/hora, servidor, processador)
- Detalhes técnicos (se houver)
- Instruções passo a passo
- Dois botões grandes:
  - "🖥️ Acessar VNC" (cinza)
  - "▶️ Continuar Automação" (roxo, destaque)

---

## 🌐 API de Controle

### **Base URL**
```
http://3.148.126.73:6092
```

### **Endpoints**

#### **1. Status**
```bash
GET /status

Resposta:
{
  "pausado": true,
  "parar": false,
  "captcha_errors": 1,
  "timestamp": "2025-10-20T22:30:15"
}
```

#### **2. Retomar (Principal)**
```bash
GET /resume

Retorna: Página HTML de confirmação
```

#### **3. Pausar**
```bash
GET /pause

Retorna: Página HTML de confirmação
```

#### **4. Parar**
```bash
GET /stop

Retorna: Página HTML de confirmação
```

#### **5. Health Check**
```bash
GET /health

Resposta:
{
  "status": "healthy",
  "api_version": "1.0",
  "timestamp": "2025-10-20T22:30:15"
}
```

---

## 🧪 Testando o Sistema

### **1. Testar Envio de Email**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION

# Testar módulo de notificação
python -c "from src.common.notification_utils import testar_envio_email; testar_envio_email()"
```

Você deve receber um email de teste em `guilherme@prosperinvest.com.br`.

### **2. Testar API Manualmente**

```bash
# Em uma janela terminal, executar a automação
./run_processor.sh

# A API inicia automaticamente na porta 6092
# Testar endpoints:
curl http://localhost:6092/status
curl http://localhost:6092/health
```

### **3. Testar Fluxo Completo**

1. Execute a automação
2. Aguarde um CAPTCHA aparecer
3. NÃO resolva (deixe dar timeout de 60s)
4. Verifique o email recebido
5. Clique em "Continuar Automação"
6. Verifique se a automação retomou

---

## 📱 Uso no Celular

### **iPhone/Android**

1. **Receba o email** no app de email
2. **Clique em "Acessar VNC"**
   - Abre o navegador
   - Digite senha: `vetor2025`
   - Veja o Chrome rodando
3. **Resolva o problema** (touch funciona!)
4. **Volte ao email**
5. **Clique em "Continuar Automação"**
6. **Pronto!** Automação retomada

---

## 🔒 Segurança

### **Recomendações**

1. ✅ **Email já protegido** - SMTP com autenticação
2. ✅ **VNC com senha** - `vetor2025`
3. ⚠️ **API sem autenticação** - Apenas IPs confiáveis devem acessar
4. ⚠️ **Porta 6092 pública** - Considerar adicionar token de segurança

### **Melhorias Futuras (Opcionais)**

```python
# Adicionar token de segurança simples
@app.route('/resume/<token>')
def resume(token):
    if token != os.getenv("API_SECRET_TOKEN"):
        return "Unauthorized", 401
    # ... resto do código
```

---

## 🛠️ Troubleshooting

### **❌ Email não enviado**

**Verificar:**
```bash
# 1. Variáveis .env
grep -E "SMTP_|EMAIL_" .env

# 2. Testar SMTP
python -c "from src.common.notification_utils import testar_envio_email; testar_envio_email()"
```

**Possíveis causas:**
- Credenciais SMTP incorretas
- MailerSend bloqueado
- EMAIL_RECIPIENT errado

---

### **❌ API não responde**

**Verificar:**
```bash
# 1. API está rodando?
ps aux | grep -i flask

# 2. Porta está escutando?
netstat -tlnp | grep 6092
# ou
ss -tlnp | grep 6092

# 3. Testar localmente
curl http://localhost:6092/health
```

**Possíveis causas:**
- Porta 6092 não aberta no Security Group AWS
- Firewall local bloqueando
- API não iniciou (erro no Flask)

---

### **❌ Link "Continuar" não funciona**

**Verificar:**
```bash
# 1. IP correto no .env?
grep SERVER_IP .env

# 2. Porta correta?
grep SERVER_PORT .env

# 3. Testar endpoint
curl http://3.148.126.73:6092/resume
```

---

## 📝 Logs

### **Logs de Email**

Procure por `[EMAIL]` nos logs:

```bash
tail -f logs/app.log | grep EMAIL
```

**Saída esperada:**
```
[EMAIL] Enviando notificação de CAPTCHA...
[EMAIL] ✅ Email enviado com sucesso!
[EMAIL] 📧 Verifique sua caixa de entrada: guilherme@prosperinvest.com.br
```

### **Logs da API**

Procure por `[API]` nos logs:

```bash
tail -f logs/app.log | grep API
```

**Saída esperada:**
```
[API] Iniciando API de controle remoto...
[API] ✅ API iniciada na porta 6092
[API] ▶️ Execução RETOMADA via API remota
[API] IP do solicitante: 192.168.1.100
```

---

## 🎯 Próximos Passos

### **1. Testar Sistema**
```bash
./run_processor.sh
# Aguardar CAPTCHA timeout e verificar email
```

### **2. Configurar Destinatários Adicionais**

No futuro, para enviar para múltiplos emails:

```python
# Em notification_utils.py
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "guilherme@prosperinvest.com.br,outro@email.com")
msg['To'] = EMAIL_RECIPIENT  # Aceita múltiplos separados por vírgula
```

### **3. Adicionar Mais Alertas**

Você pode adicionar notificações para outros eventos:

```python
# Exemplo: Notificar quando completar ciclo
from src.common.notification_utils import enviar_email_intervencao

enviar_email_intervencao(
    tipo_intervencao="✅ CICLO COMPLETO",
    mensagem="A automação completou um ciclo com sucesso!",
    detalhes_adicionais=f"CSVs gerados: {arquivos}"
)
```

---

## 📞 Suporte

Se tiver problemas:

1. Verifique os logs: `tail -f logs/app.log`
2. Teste envio de email: `python -c "from src.common.notification_utils import testar_envio_email; testar_envio_email()"`
3. Teste API: `curl http://localhost:6092/health`
4. Consulte esta documentação

---

**Última atualização:** 2025-10-20
**Versão:** 1.0
**Status:** ✅ Funcionando
