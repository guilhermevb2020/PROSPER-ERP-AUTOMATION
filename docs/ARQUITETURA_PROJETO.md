# 🏗️ Arquitetura do PROSPER-ERP-AUTOMATION

## 📋 Índice
1. [Visão Geral](#visão-geral)
2. [Por que Separar do PROSPER_DATA_HUB?](#por-que-separar)
3. [Como Funciona](#como-funciona)
4. [Arquitetura de VMs](#arquitetura-de-vms)
5. [Sistema de Displays Virtuais](#sistema-de-displays-virtuais)
6. [Isolamento de Automações](#isolamento-de-automações)
7. [Fluxo de Execução](#fluxo-de-execução)
8. [Sistema de Notificações](#sistema-de-notificações)
9. [Recursos Necessários](#recursos-necessários)

---

## 🎯 Visão Geral

O **PROSPER-ERP-AUTOMATION** é um sistema especializado para **automações web** que requerem:
- ✅ Navegador Chrome visível
- ✅ Interação humana ocasional (resolução de CAPTCHAs)
- ✅ Stealth mode (anti-detecção de bots)
- ✅ Monitoramento remoto via VNC

Foi separado do `PROSPER_DATA_HUB` (processadores API) para:
- Isolamento de recursos (Chrome consome muita RAM/CPU)
- Execução em VM dedicada
- Escalabilidade independente

---

## 🤔 Por que Separar do PROSPER_DATA_HUB?

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
│  - 17+ processadores API     │  │  - Chrome + Selenium         │
│  - Headless (sem interface)  │  │  - VNC (acesso remoto)       │
│  - Roda 24/7 automático      │  │  - Múltiplas automações      │
│  - Baixo consumo (~200MB)    │  │  - Interação humana          │
│  - Systemd gerenciado        │  │  - Sob demanda ou agendado   │
└──────────────────────────────┘  └──────────────────────────────┘
     Custo: ~$16/mês                   Custo: ~$61/mês
```

**Benefícios:**
- ✅ Isolamento total: falha em WEB não afeta API
- ✅ Escalabilidade: aumenta recursos só da VM necessária
- ✅ Segurança: VMs com regras de firewall diferentes
- ✅ Manutenção: atualiza/reinicia uma sem afetar outra

---

## ⚙️ Como Funciona

### **Componentes Principais**

```
┌─────────────────────────────────────────────────────────────┐
│              VM Linux (Ubuntu 20.04+)                       │
│              Sem monitor físico                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1️⃣ Xvfb (X Virtual Frame Buffer)                          │
│     "Monitor Virtual" - Cria tela fake                      │
│     Display: :1, :2, :3...                                  │
│     Resolução: 1920x1080                                    │
│                                                             │
│  2️⃣ VNC Server (TigerVNC)                                   │
│     Transmite tela virtual pela rede                        │
│     Portas: 5901, 5902, 5903...                            │
│                                                             │
│  3️⃣ Chrome + Selenium                                       │
│     Roda no display virtual                                 │
│     Pensa que tem monitor real                              │
│     Stealth mode (undetected-chromedriver)                  │
│                                                             │
│  4️⃣ Python Script                                           │
│     Controla Chrome via Selenium                            │
│     Detecta quando CAPTCHA trava                            │
│     Envia notificação email                                 │
└─────────────────────────────────────────────────────────────┘
                        ↓ (conexão remota)
┌─────────────────────────────────────────────────────────────┐
│              Seu Computador / Celular                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  VNC Viewer (RealVNC, TightVNC, Remmina)                    │
│  ou noVNC (VNC no navegador)                                │
│                                                             │
│  Conecta em: VM_IP:5901                                     │
│  Vê Chrome rodando remotamente                              │
│  Pode clicar, digitar, resolver CAPTCHA                     │
│  Fecha VNC = desconecta, Chrome continua rodando            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🖥️ Arquitetura de VMs

### **Opção 1: Setup Inicial (1 automação)**

```
┌────────────────────────────────────────────────────────────┐
│  VM: ETL_WEB (t3.medium - 2 vCPU, 4GB RAM)                │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Display :1 (VNC porta 5901)                               │
│  └─ Chrome → Automação: titulos_abertos_marcados          │
│                                                            │
│  Consumo: ~1GB RAM                                         │
│  Custo: ~$30/mês                                           │
└────────────────────────────────────────────────────────────┘
```

### **Opção 2: Produção com Múltiplas Automações**

```
┌────────────────────────────────────────────────────────────┐
│  VM: ETL_WEB (t3.large - 2 vCPU, 8GB RAM)                 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Display :1 (VNC 5901) → titulos_abertos_marcados         │
│  Display :2 (VNC 5902) → operacao_desagio_web             │
│  Display :3 (VNC 5903) → relatorios_customizados          │
│  Display :4 (VNC 5904) → exportacao_lotes                 │
│  Display :5 (VNC 5905) → consulta_cedentes                │
│                                                            │
│  Consumo: ~3-4GB RAM                                       │
│  Custo: ~$61/mês                                           │
└────────────────────────────────────────────────────────────┘
```

---

## 📺 Sistema de Displays Virtuais

### **Abordagem A: 1 Display + Múltiplos Chrome Profiles**

**Configuração:**
```bash
# 1 VNC Server (display :1)
vncserver :1 -geometry 1920x1080 -depth 24

# Múltiplos Chrome rodando em paralelo
DISPLAY=:1 google-chrome --user-data-dir=~/.chrome_titulos &
DISPLAY=:1 google-chrome --user-data-dir=~/.chrome_desagio &
DISPLAY=:1 google-chrome --user-data-dir=~/.chrome_relatorios &
```

**Visualização:**
```
┌─────────────────────────────────────────────────────┐
│  VNC Viewer (você vê tudo numa tela)                │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [Chrome 1]  [Chrome 2]  [Chrome 3]                │
│   Títulos    Deságio     Relatórios                │
│                                                     │
│  Você vê todas as janelas simultaneamente          │
└─────────────────────────────────────────────────────┘
```

✅ **Vantagens:** Simples, vê tudo numa tela
❌ **Desvantagens:** Confusão visual, se VNC cair perde tudo

---

### **Abordagem B: Múltiplos Displays (1 por automação)** ⭐ RECOMENDADO

**Configuração:**
```bash
# Display :1 para automação 1
Xvfb :1 -screen 0 1920x1080x24 &
vncserver :1

# Display :2 para automação 2
Xvfb :2 -screen 0 1920x1080x24 &
vncserver :2

# Display :3 para automação 3
Xvfb :3 -screen 0 1920x1080x24 &
vncserver :3

# Cada Chrome no seu display
DISPLAY=:1 google-chrome &  # Automação 1
DISPLAY=:2 google-chrome &  # Automação 2
DISPLAY=:3 google-chrome &  # Automação 3
```

**Visualização:**
```
Você conecta em portas diferentes:

VNC VM_IP:5901  →  Vê só automação 1 (títulos)
VNC VM_IP:5902  →  Vê só automação 2 (deságio)
VNC VM_IP:5903  →  Vê só automação 3 (relatórios)
```

✅ **Vantagens:** Isolamento total, organização, se um cair outros continuam
❌ **Desvantagens:** Mais complexo, +150MB RAM por display

---

## 🔒 Isolamento de Automações

### **Por que isolar?**

Se 5 automações rodarem no mesmo display:
- ❌ Crash em uma pode afetar outras
- ❌ Difícil debugar qual travou
- ❌ CAPTCHAs aparecem misturados

Com displays separados:
- ✅ Cada automação totalmente isolada
- ✅ Debugging individual
- ✅ Restart independente
- ✅ Monitoramento por porta VNC

### **Consumo de Recursos (5 automações)**

| Abordagem | RAM Total | CPU | Vantagem |
|-----------|-----------|-----|----------|
| **1 Display + 5 Chrome** | ~2.7GB | 15-25% | Mais leve |
| **5 Displays separados** | ~3.4GB | 20-30% | Mais robusto |

**Diferença:** +700MB RAM pela segurança do isolamento

---

## 🔄 Fluxo de Execução

### **Cenário 1: Automação Roda Perfeitamente**

```
08:00 - Automação inicia (script Python)
08:01 - Chrome abre no display virtual :1
08:02 - Login automático no SmartSecurities
08:03 - Preenche formulário
08:04 - CAPTCHA simples → CapSolver resolve sozinho
08:05 - Clica "Pesquisar"
08:06 - Seleciona todos resultados
08:07 - Clica "Gerar CSV"
08:08 - CSV baixado em data/raw_inputs/
08:09 - Automação finaliza
08:10 - Chrome continua aberto aguardando próximo ciclo
```

**Você:** Não precisa fazer nada! 🎉

---

### **Cenário 2: CAPTCHA Complexo Trava**

```
08:00 - Automação inicia
08:01 - Chrome abre no display virtual :1
08:02 - Login automático
08:03 - Preenche formulário
08:04 - CAPTCHA COMPLEXO aparece (imagens difíceis)
08:04 - CapSolver tenta resolver... falha
08:05 - Script detecta que CAPTCHA não resolveu
08:05 - Script PAUSA automação
08:05 - Script ENVIA EMAIL para você
        ┌────────────────────────────────────────┐
        │ 📧 EMAIL                               │
        ├────────────────────────────────────────┤
        │ Assunto: ⚠️ CAPTCHA Travado            │
        │                                        │
        │ Automação: titulos_abertos_marcados    │
        │ Status: PAUSADA aguardando resolução   │
        │                                        │
        │ 🔗 Clique para resolver:               │
        │ http://VM_IP:5901                      │
        │                                        │
        │ Ou use VNC Viewer: VM_IP:5901          │
        │ Senha: [sua_senha_vnc]                 │
        │                                        │
        │ Timeout: 10 minutos                    │
        └────────────────────────────────────────┘

08:06 - Você recebe email no celular/PC
08:07 - Clica no link
08:07 - Navegador abre VNC (via noVNC)
08:08 - Você VÊ o Chrome com CAPTCHA travado
08:08 - Você resolve CAPTCHA manualmente
08:09 - Fecha navegador (VNC desconecta)
08:09 - Script detecta CAPTCHA resolvido
08:09 - Automação RETOMA automaticamente
08:10 - CSV baixado
08:11 - Automação finaliza
```

**Você:** Interveio 2 minutos, resolveu, continua sozinho! ✅

---

## 📧 Sistema de Notificações

### **Quando Notificar?**

- ⚠️ CAPTCHA não resolvido após 60s
- ❌ Erro crítico (site fora do ar)
- 🔄 Automação travou (timeout)
- ⏱️ Execução excedeu tempo esperado

### **Email HTML Bonito**

```
┌─────────────────────────────────────────────────────┐
│  [Logo Prosper]                                     │
│                                                     │
│  🚨 Alerta de Falha - Processo Automático           │
│                                                     │
│  Olá, humano amigo. ⚠️                              │
│                                                     │
│  A automação "titulos_abertos_marcados" travou     │
│  em CAPTCHA e precisa da sua ajuda!                 │
│                                                     │
│  🔗 RESOLVER AGORA (clique aqui)                    │
│                                                     │
│  Detalhes técnicos:                                 │
│  - Horário: 08:05:23 (Brasília)                     │
│  - Tentativas: 3/3 (todas falharam)                 │
│  - Timeout em: 10 minutos                           │
│                                                     │
│  [Mascote Prosperito]                               │
│                                                     │
│  Atenciosamente,                                    │
│  Seu robô PROSPER-ERP-AUTOMATION 🤖                 │
└─────────────────────────────────────────────────────┘
```

### **Tecnologia**

- ✅ HTML com imagens inline (logo + mascote)
- ✅ Link clicável para VNC direto
- ✅ Estilo bonito e profissional
- ✅ SMTP configurado no .env

---

## 💰 Recursos Necessários

### **VM Recomendada (Produção - 5 automações simultâneas)**

```
Tipo: t3.large (AWS)
- vCPUs: 2
- RAM: 8 GB
- Custo: ~$61/mês

Componentes           RAM      CPU
─────────────────────────────────────
Sistema operacional   500MB    5%
Xvfb (5 displays)     400MB    2%
VNC Server (5x)       150MB    2%
XFCE (window mgr)     500MB    3%
Chrome (5x)          2500MB   15-25%
Python scripts        200MB    3-5%
─────────────────────────────────────
TOTAL               ~4200MB   30-40%
Livre                ~3800MB   60-70%
```

**Crescimento:**
- +1 automação = +650MB RAM + 5% CPU
- Limite recomendado: 8 automações por t3.large

### **Setup Inicial (1-2 automações)**

```
Tipo: t3.medium (AWS)
- vCPUs: 2
- RAM: 4 GB
- Custo: ~$30/mês

Suficiente para começar!
```

---

## 🎯 Resumo Executivo

### **Este Projeto É:**
- ✅ Sistema dedicado para automações web com Chrome
- ✅ Separado do PROSPER_DATA_HUB (processadores API)
- ✅ Roda em VM Linux com display virtual (Xvfb + VNC)
- ✅ Acesso remoto via VNC quando precisar intervir
- ✅ Notificações automáticas quando CAPTCHA travar
- ✅ Múltiplas automações isoladas (1 display por automação)

### **Por que Assim?**
- 🎯 **Isolamento**: Web não afeta API
- 🎯 **Escalabilidade**: Cresce conforme necessidade
- 🎯 **Confiabilidade**: Falha isolada
- 🎯 **Praticidade**: Você só intervém quando necessário
- 🎯 **Custo**: Paga só pelo que usa

### **Próximos Passos:**
1. Testar localmente (se possível)
2. Preparar VM dedicada
3. Instalar Xvfb + VNC
4. Configurar primeira automação
5. Adicionar mais automações conforme demanda

---

<div align="center">
  <sub>Arquitetura projetada pela equipe de TI da Prosper Capital</sub><br>
  <sub>Baseado em discussões estratégicas de arquitetura de sistemas</sub><br>
  <sub>Data: 2025-10-17</sub>
</div>
