# 🏗️ Arquitetura do PROSPER-ERP-AUTOMATION

**Versão:** 2.0
**Data:** 2025-10-25

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Por Que Separado do PROSPER_DATA_HUB?](#por-que-separado-do-prosper_data_hub)
3. [Stack Tecnológico](#stack-tecnológico)
4. [Arquitetura de Isolamento](#arquitetura-de-isolamento)
5. [Sistema de Displays Virtuais](#sistema-de-displays-virtuais)
6. [Convenção de Portas](#convenção-de-portas)
7. [Anatomia de um Processador](#anatomia-de-um-processador)
8. [Fluxo de Execução](#fluxo-de-execução)
9. [Sistema de Notificações](#sistema-de-notificações)
10. [API de Controle Remoto](#api-de-controle-remoto)
11. [Recursos de Infraestrutura](#recursos-de-infraestrutura)

---

## 🎯 Visão Geral

O **PROSPER-ERP-AUTOMATION** é um sistema especializado para **automações web headless** que:

- ✅ Extrai dados do ERP SmartSecurities automaticamente
- ✅ Usa **Nodriver** com anti-detecção nativa (indetectável)
- ✅ Roda em **displays virtuais isolados** (Xvfb + VNC)
- ✅ Resolve **CAPTCHAs automaticamente** via CapSolver
- ✅ Permite **acesso remoto** via navegador (noVNC)
- ✅ Envia **notificações por email** quando precisa intervenção
- ✅ Suporta **controle remoto via API REST**

---

## 🤔 Por Que Separado do PROSPER_DATA_HUB?

### **ANTES: Tudo numa VM**

```
┌────────────────────────────────────────────────────┐
│         VM Única (t3.xlarge - 16GB RAM)            │
├────────────────────────────────────────────────────┤
│  Superset (BI)              → 5.5GB RAM (34%)      │
│  PROSPER_DATA_HUB (API)     → 141MB RAM (1%)       │
│  Processadores Web          → 500MB+ RAM           │
├────────────────────────────────────────────────────┤
│  Problema: Competição por recursos                │
│  Se Chrome travar → afeta processadores API        │
│  Difícil escalar uma parte sem afetar outra        │
└────────────────────────────────────────────────────┘
```

### **DEPOIS: Separado**

```
┌──────────────────────────────┐  ┌──────────────────────────────┐
│  VM 1: API (t3.small)        │  │  VM 2: WEB (t3.large)        │
│  PROSPER_DATA_HUB            │  │  PROSPER-ERP-AUTOMATION      │
├──────────────────────────────┤  ├──────────────────────────────┤
│  - 17+ processadores API     │  │  - Chrome + Nodriver         │
│  - Headless (sem interface)  │  │  - VNC (acesso remoto)       │
│  - Roda 24/7 automático      │  │  - Múltiplas automações      │
│  - Baixo consumo (~200MB)    │  │  - Interação humana          │
│  - Systemd gerenciado        │  │  - Sob demanda ou agendado   │
└──────────────────────────────┘  └──────────────────────────────┘
     Custo: ~$16/mês                   Custo: ~$61/mês
```

**Benefícios:**
- ✅ **Isolamento total:** falha em WEB não afeta API
- ✅ **Escalabilidade:** aumenta recursos só da VM necessária
- ✅ **Segurança:** VMs com regras de firewall diferentes
- ✅ **Manutenção:** atualiza/reinicia uma sem afetar outra

---

## ⚙️ Stack Tecnológico

| Camada | Tecnologia | Versão | Função |
|--------|------------|--------|--------|
| **Automação Web** | Nodriver | 0.47+ | Anti-detecção nativa (CORE) |
| **Automação Fallback** | Selenium | 4.27.1 | Fallback/legacy |
| **CAPTCHA Solver** | CapSolver API | - | Resolução automática via HTTP |
| **Display Virtual** | Xvfb | - | Monitor virtual headless |
| **VNC Server** | x11vnc | - | Servidor VNC (porta 5900) |
| **VNC Web** | noVNC | - | Acesso VNC via navegador (porta 6080) |
| **API REST** | Flask | 3.0.0 | Controle remoto (porta 6092) |
| **Banco de Dados** | PostgreSQL | - | Azure Database |
| **Email** | SMTP (MailerSend) | - | Notificações |
| **Processamento** | Pandas | 2.2.3 | Manipulação de dados |
| **Timezone** | pytz | 2025.2 | Fuso horário Brasil (UTC-3) |
| **Async** | asyncio | stdlib | 100% async/await |

---

## 🔒 Arquitetura de Isolamento

### **Conceito: 1 Processador = 1 Display Isolado**

Cada processador roda em seu próprio display virtual completamente isolado:

```
┌────────────────────────────────────────────────────┐
│              SERVIDOR AWS (Ubuntu)                 │
├────────────────────────────────────────────────────┤
│                                                    │
│  Display :1 (VNC 5900, Web 6080)                  │
│  └─ Processador: relatorios_operacoes.py          │
│                                                    │
│  Display :2 (VNC 5901, Web 6081)                  │
│  └─ Processador: titulos_abertos.py               │
│                                                    │
│  Display :3 (VNC 5902, Web 6082)                  │
│  └─ Processador: outro_processador.py             │
│                                                    │
│  ... (suporta até 12 displays simultâneos)        │
│                                                    │
└────────────────────────────────────────────────────┘
```

### **Por que isolar?**

| Aspecto | Sem Isolamento | Com Isolamento |
|---------|----------------|----------------|
| **Crash** | Crash em um afeta todos | Cada um independente |
| **Debug** | Difícil identificar qual travou | Debug individual |
| **VNC** | Vê todas janelas misturadas | 1 conexão = 1 processador |
| **Restart** | Reinicia tudo | Reinicia só o necessário |
| **RAM** | ~2.7GB (5 procs) | ~4.2GB (5 procs) |
| **Custo** | +700MB RAM | Maior segurança |

✅ **Diferença:** +700MB RAM pela segurança do isolamento total

---

## 📺 Sistema de Displays Virtuais

### **Mapeamento de Portas**

```
Display :1  →  x11vnc :5900  →  noVNC :6080
Display :2  →  x11vnc :5901  →  noVNC :6081
Display :3  →  x11vnc :5902  →  noVNC :6082
...
Display :12 →  x11vnc :5911  →  noVNC :6091
```

### **Acesso**

```bash
# Via navegador (mais fácil)
http://3.148.126.73:6080/vnc.html  # Display :1
http://3.148.126.73:6081/vnc.html  # Display :2
http://3.148.126.73:6082/vnc.html  # Display :3

# Via cliente VNC
3.148.126.73:5900  # Display :1
3.148.126.73:5901  # Display :2
3.148.126.73:5902  # Display :3
```

### **Configuração de Display**

```bash
# Iniciar processador no display :1
DISPLAY=:1 python src/processors/web/relatorios_operacoes.py

# Iniciar processador no display :2
DISPLAY=:2 python src/processors/web/outro_processador.py
```

---

## 🔢 Convenção de Portas

### **Regra: API sempre +10 da porta VNC**

Cada processador utiliza **duas portas**:
- **Porta VNC**: Para acesso remoto ao display virtual (noVNC)
- **Porta API**: Para controle remoto (pause/resume/stop) via HTTP

**Fórmula**: `API_PORT = VNC_PORT + 10`

### **Exemplo Atual**

```
Processador: relatorio_operacao_desagio
├─ Display: :1
├─ VNC Port: 6080
│  └─ URL: http://3.148.126.73:6080/vnc.html
└─ API Port: 6090 (VNC + 10)
   └─ URL: http://3.148.126.73:6090
```

### **Tabela de Processadores**

| Processador                  | Display | VNC    | API    | Status  |
|------------------------------|---------|--------|--------|---------|
| relatorio_operacao_desagio   | :1      | 6080   | 6090   | ✅ Ativo |
| (reservado)                  | :2      | 6070   | 6080   | ⏸️ Futuro|
| (reservado)                  | :3      | 6060   | 6070   | ⏸️ Futuro|

### **Por Que Esta Convenção?**

1. **Fácil Memorização**: Sempre somar 10 à porta VNC
2. **Padronização**: Todos os processadores seguem a mesma lógica
3. **Escalabilidade**: Simples adicionar novos processadores
4. **Documentação**: Regra clara e objetiva

📖 **Documentação Completa**: [docs/CONVENCOES_PORTAS.md](CONVENCOES_PORTAS.md)

---

## 🤖 Anatomia de um Processador

### **Estrutura Obrigatória**

Todo processador segue este padrão:

```python
import asyncio
import nodriver as uc
from src.common.nodriver_utils import init_browser, human_click, human_type
from src.common.captcha_solver import CapSolverAPI
from src.common.notification_utils import enviar_alerta_captcha
from src.core.logging_config import get_logger

class ProcessadorNome:
    """Processador - 100% Nodriver Async"""

    def __init__(self):
        self.nome = "nome_processador"
        self.browser = None
        self.tab = None
        self.display = os.environ.get('DISPLAY', ':1')
        self.pausado = False
        self.parar = False
        self.capsolver = CapSolverAPI(os.getenv("CAPSOLVER_API_KEY"))

    async def iniciar_navegador(self):
        """Inicializa Nodriver no display virtual"""
        self.browser = await init_browser(
            download_dir="data/raw_inputs/",
            headless=False,
            display=self.display
        )

    async def fazer_login_automatico(self):
        """Login no sistema"""
        pass  # Implementação específica

    async def executar_extracao_completa(self):
        """Pipeline completo de extração"""
        pass  # Implementação específica

    async def processar(self, modo_simulacao=False):
        """Loop principal"""
        await self.iniciar_navegador()

        ciclo = 1
        while not self.parar:
            await self.verificar_pausa()
            logger.info(f"Ciclo {ciclo}")
            await self.executar_extracao_completa()
            ciclo += 1
            await asyncio.sleep(60)  # Aguarda 1 min

# Wrapper sync
def processar_nome(modo_simulacao: bool = False) -> dict:
    processador = ProcessadorNome()
    return asyncio.run(processador.processar(modo_simulacao))
```

### **Características Obrigatórias**

1. ✅ **100% Async/Await** - Sem bloqueios síncronos
2. ✅ **Nodriver puro** - Sem Selenium
3. ✅ **Controle P/R/Q** - Pausar/retomar/parar via teclado
4. ✅ **Logging estruturado** - Via `get_logger(__name__)`
5. ✅ **CAPTCHA handling** - Via `CapSolverAPI`
6. ✅ **Notificações** - Via `enviar_alerta_captcha()`
7. ✅ **Display configurável** - Via `os.environ['DISPLAY']`
8. ✅ **Retry/Timeout** - Com backoff exponencial
9. ✅ **Máquina de estados** - Estados claros e rastreáveis
10. ✅ **Wrapper sync** - Função entry point que chama `asyncio.run()`

---

## 🔄 Fluxo de Execução

### **Cenário 1: Execução Perfeita** ✅

```
08:00 - Script Python inicia
08:01 - Nodriver abre Chrome no display :1
08:02 - Login automático no SmartSecurities
08:03 - Preenche formulário
08:04 - CapSolver resolve CAPTCHA automaticamente
08:05 - Clica "Pesquisar"
08:06 - Seleciona todos resultados
08:07 - Clica "Gerar CSV"
08:08 - CSV baixado em data/raw_inputs/
08:09 - Aguarda 60 segundos
08:10 - Reinicia ciclo
```

✅ **Você:** Não precisa fazer nada!

### **Cenário 2: CAPTCHA Complexo** ⚠️

```
08:00 - Script inicia
08:01 - Chrome abre
08:02 - Login automático
08:03 - CAPTCHA COMPLEXO aparece
08:04 - CapSolver tenta... FALHA (60s timeout)
08:05 - Script PAUSA automaticamente
08:05 - Email enviado para você com:
        - Link VNC: http://3.148.126.73:6080/vnc.html
        - Link API: http://3.148.126.73:6092/resume
08:06 - Você acessa VNC via email
08:07 - Você resolve CAPTCHA manualmente
08:08 - Você clica no link "Retomar" do email
08:09 - Script RETOMA automaticamente
08:10 - CSV baixado
08:11 - Ciclo continua normalmente
```

✅ **Você:** Interveio 3 minutos, resolveu, continua sozinho!

---

## 📧 Sistema de Notificações

### **Quando Enviar Email?**

- ⚠️ CAPTCHA não resolvido após 60s
- ❌ Erro crítico (site fora do ar, elemento não encontrado)
- 🔄 Processo travou (timeout)
- ⚠️ Extensão CapSolver não instalada

### **Estrutura do Email**

```html
┌─────────────────────────────────────────────┐
│  [Logo Prosper]                             │
│                                             │
│  🚨 Automação Precisa de Ajuda              │
│                                             │
│  Processador: relatorios_operacoes          │
│  Problema: CAPTCHA não resolvido            │
│  Display: :1                                │
│  Horário: 08:05:23 (Brasília)               │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  🖥️ Acessar VNC                     │   │
│  │  http://3.148.126.73:6080/vnc.html  │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  ▶️ Continuar Automação              │   │
│  │  http://3.148.126.73:6092/resume    │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  [Mascote Prosperito]                       │
└─────────────────────────────────────────────┘
```

### **Configuração SMTP**

Via `.env`:
```bash
SMTP_SERVER=smtp.mailersend.net
SMTP_PORT=2525
SMTP_USER=MS_XXXXXX
SMTP_PASSWORD=XXXXXX
EMAIL_FROM=prosperito@prosperfidc.online
EMAIL_RECIPIENT=guilherme@prosperinvest.com.br
```

---

## 🌐 API de Controle Remoto

### **Endpoints Disponíveis**

```bash
# Base URL
http://3.148.126.73:6092

# Endpoints
GET  /                  # Info da API
GET  /status            # Status atual (pausado, parar, captcha_errors)
GET  /resume            # Retomar execução (renderiza HTML)
GET  /pause             # Pausar execução
GET  /stop              # Parar execução
GET  /health            # Health check
```

### **Uso via Email**

Quando você recebe email de alerta, basta clicar no botão "Continuar Automação" que chama automaticamente:

```
http://3.148.126.73:6092/resume
```

A página confirma:
```html
✅ Automação Retomada com Sucesso!
Você pode fechar esta janela.
```

### **Uso via cURL**

```bash
# Ver status
curl http://3.148.126.73:6092/status

# Retomar
curl http://3.148.126.73:6092/resume

# Pausar
curl http://3.148.126.73:6092/pause
```

---

## 💰 Recursos de Infraestrutura

### **Setup Atual (Produção)**

```
Tipo: t3.large (AWS)
- vCPUs: 2
- RAM: 8 GB
- Custo: ~$61/mês

Componentes           RAM      CPU
─────────────────────────────────────
Sistema operacional   500MB    5%
Xvfb (2 displays)     400MB    2%
VNC Server (2x)       150MB    2%
Chrome (2x)          2500MB   15-25%
Python scripts        200MB    3-5%
─────────────────────────────────────
TOTAL               ~3750MB   27-39%
Livre                ~4250MB   61-73%
```

### **Crescimento**

- **+1 processador** = +650MB RAM + 5% CPU
- **Limite recomendado:** 8 processadores por t3.large
- **Limite teórico:** 12 processadores (requer t3.xlarge - 16GB RAM)

### **Setup Inicial (1-2 processadores)**

```
Tipo: t3.medium (AWS)
- vCPUs: 2
- RAM: 4 GB
- Custo: ~$30/mês

Suficiente para começar!
```

---

## 🎯 Resumo Executivo

### **Este Sistema É:**
- ✅ Automações web com Chrome visível
- ✅ Anti-detecção nativa (Nodriver)
- ✅ Isolamento total por processador
- ✅ Acesso remoto via VNC web
- ✅ Notificações automáticas
- ✅ Controle remoto via API REST
- ✅ 100% async/await

### **Diferencial Técnico:**
- 🤖 Indetectável (sem CDP)
- ⚡ Alta performance (async)
- 🧠 Simula comportamento humano
- 🔄 Auto-recuperação inteligente
- 📊 Estados claros e rastreáveis
- 🌐 Controle total remoto

### **Veja Também:**
- [Como Criar um Processador](CRIAR_PROCESSADOR.md)
- [Fluxos de Processadores](fluxos_processadores/) - **Exemplos práticos**
- [Como Acessar VNC](ACESSO_VNC.md)
- [Sistema de Notificações](NOTIFICACOES.md)
- [Troubleshooting](TROUBLESHOOTING.md)

---

**Última atualização:** 2025-10-25
**Versão:** 2.0
