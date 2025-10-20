# 📋 Sistema de Automações Inteligentes - Visão Geral

**Versão:** 1.0
**Data:** Outubro 2025
**Autor:** Equipe de Automação PROSPER ERP

---

## 🎯 Objetivo do Sistema

Criar uma **infraestrutura de automações web 24/7** altamente resiliente, capaz de:

1. **Rodar múltiplas automações simultaneamente** (até 12 instâncias)
2. **Auto-recuperação inteligente** quando problemas ocorrerem
3. **Alertas automáticos** para intervenção humana quando necessário
4. **Zero downtime** - sistema nunca para completamente
5. **Acesso remoto seguro** via VNC para debugging/resolução de CAPTCHAs

---

## 🏗️ Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORQUESTRADOR CENTRAL                          │
│  - Monitora 12 processos em tempo real                          │
│  - Detecta travamentos e erros                                  │
│  - Envia emails de alerta com link VNC                          │
│  - Reinicia processos automaticamente                           │
│  - Dashboard web (opcional) para visualização                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┬──────────────┐
         ▼               ▼               ▼              ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐   ┌─────────┐
    │ Auto #1 │     │ Auto #2 │     │ Auto #3 │...│ Auto #12│
    │ VNC:5900│     │ VNC:5901│     │ VNC:5902│   │ VNC:5911│
    │ HTTP:6080│    │ HTTP:6081│    │ HTTP:6082│  │ HTTP:6091│
    │ Display:1│    │ Display:2│    │ Display:3│  │ Display:12│
    └─────────┘     └─────────┘     └─────────┘   └─────────┘
         │               │               │              │
         └───────────────┴───────────────┴──────────────┘
                         │
                    ┌────▼────┐
                    │  SMTP   │  → Alertas por Email
                    └─────────┘
```

---

## 🔄 Fluxo de Funcionamento

### **1. Operação Normal**

```
┌─────────────────────────────────────────────────────────┐
│ AUTOMAÇÃO #1 - Títulos Abertos (COM checkbox recompra) │
└─────────────────────────────────────────────────────────┘
         │
         ▼
    Login automático (credenciais .env)
         │
         ▼
    Resolver CAPTCHA (extensão CapSolver)
         │
         ▼
    Navegar → Preencher datas → Marcar checkbox
         │
         ▼
    Pesquisar → Selecionar todos → Gerar CSV
         │
         ▼
    Download completo → Renomear arquivo
         │
         ▼
    Aguardar 60 segundos
         │
         └──────► Repetir ciclo
```

### **2. Cenário de Erro - CAPTCHA não Resolvido**

```
AUTOMAÇÃO #3 rodando...
         │
         ▼
    CAPTCHA aparece após "Gerar CSV"
         │
         ▼
    Extensão tenta resolver (60s timeout)
         │
         ▼
    ❌ FALHA - CAPTCHA não resolvido
         │
         ▼
    Orquestrador DETECTA travamento (5 min sem atividade)
         │
         ▼
    Gera TOKEN temporário de acesso VNC
         │
         ▼
    Envia EMAIL de alerta:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🤖 Automação #3 precisa de ajuda!

    Problema: CAPTCHA não resolvido após 60s
    Display: :3
    Porta VNC: 5902
    Porta Web: 6082
    Tempo travado: 5 minutos

    🔗 Acesso VNC (expira em 1h):
    http://3.141.54.43:6082/vnc.html?token=xyz123abc

    📋 O que fazer:
    1. Acesse o link acima
    2. Resolva o CAPTCHA manualmente
    3. Clique no botão "✅ Resolvido" na interface
       OU pressione [R] no terminal

    ⏰ Token expira: 2025-10-20 21:30:00
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         │
         ▼
    Humano acessa VNC via link
         │
         ▼
    Humano resolve CAPTCHA manualmente
         │
         ▼
    Humano pressiona [R] (retomar)
         │
         ▼
    Automação retoma execução
         │
         ▼
    Token VNC é invalidado
         │
         ▼
    Log registra: "Automação #3 retomada por João Silva (IP: 177.115.243.213)"
         │
         ▼
    Ciclo continua normalmente
```

### **3. Cenário de Erro - Botão não Encontrado**

```
AUTOMAÇÃO #7 rodando...
         │
         ▼
    Tenta clicar em "Gerar CSV"
         │
         ▼
    ❌ ERRO: Botão não encontrado após 3 tentativas
         │
         ▼
    Sistema de retry tenta 3x com intervalo de 3s
         │
         ▼
    ❌ Todas as tentativas falharam
         │
         ▼
    Orquestrador DETECTA erro crítico
         │
         ▼
    EMAIL de alerta enviado (mesmo padrão CAPTCHA)
         │
         ▼
    Humano acessa VNC
         │
         ▼
    Humano identifica problema: página mudou de layout
         │
         ▼
    Humano pode:
    - Resolver manualmente e retomar [R]
    - OU pausar [P] e avisar dev para corrigir código
```

---

## 🎛️ Tipos de Processadores (Automações)

### **Processador Base:**
- `titulos_abertos_e_marcados_recompras.py` (atual)

### **Novos Processadores (futuros):**
- `titulos_vencidos.py`
- `relatorio_cobranca.py`
- `extrato_cliente.py`
- `posicao_custodia.py`
- etc.

**Cada processador:**
- Herda da classe base `ProcessadorBase`
- Implementa métodos específicos da extração
- Usa o mesmo sistema de alertas/retry
- Roda em seu próprio display/VNC isolado

---

## 🔐 Sistema de Segurança VNC

### **1. Tokens Temporários**

Cada email de alerta contém um **token único** que:

- ✅ Expira em 1 hora
- ✅ Permite acesso VNC apenas daquele processador específico
- ✅ Registra quem acessou (IP, timestamp, usuário)
- ✅ Invalida automaticamente após resolução

### **2. Autenticação Multi-camadas**

```
Camada 1: Firewall AWS
    ↓
Camada 2: Token URL válido
    ↓
Camada 3: Senha VNC (x11vnc)
    ↓
Camada 4: Log de acesso
```

### **3. Restrição de IPs (opcional)**

- Listar IPs autorizados no config
- Bloquear acessos de IPs não conhecidos
- Alertar se tentativa de acesso suspeito

---

## 📊 Monitoramento e Logs

### **Dashboard Central (opcional - Fase 3)**

```
┌─────────────────────────────────────────────────────────┐
│  Sistema de Automações - Status em Tempo Real          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Automação #1: ✅ Rodando (Ciclo 47, CSV gerado 09:15) │
│  Automação #2: ✅ Rodando (Ciclo 47, CSV gerado 09:14) │
│  Automação #3: ⚠️  PAUSADO - CAPTCHA (aguardando...)   │
│  Automação #4: ✅ Rodando (Ciclo 46, CSV gerado 09:13) │
│  Automação #5: ❌ ERRO - Reiniciando...                │
│  Automação #6-12: ✅ Rodando                           │
│                                                         │
│  📈 Estatísticas (24h):                                │
│    - CSVs gerados: 2,304                               │
│    - Taxa sucesso: 98.7%                               │
│    - Intervenções manuais: 12                          │
│    - Tempo médio por ciclo: 62s                        │
│                                                         │
│  🔔 Últimos Alertas:                                   │
│    09:15 - Auto #3 - CAPTCHA não resolvido             │
│    08:42 - Auto #5 - Erro ao conectar (resolvido)      │
│    07:30 - Auto #11 - CAPTCHA não resolvido            │
└─────────────────────────────────────────────────────────┘
```

### **Logs Detalhados**

```
logs/
├── orquestrador/
│   ├── 2025-10-20.log          # Log principal do orquestrador
│   ├── alerts_sent.log         # Histórico de alertas enviados
│   └── human_interventions.log # Log de intervenções manuais
│
├── automacao_01/
│   ├── 2025-10-20.log          # Log da automação #1
│   ├── errors/                 # Screenshots de erros
│   └── downloads/              # CSVs baixados
│
├── automacao_02/
│   └── ...
│
└── vnc_access/
    └── 2025-10-20.log          # Log de acessos VNC
```

---

## 📧 Sistema de Alertas por Email

### **Quando Enviar Alertas:**

1. **CAPTCHA não resolvido** após 60 segundos
2. **Botão/elemento não encontrado** após 3 tentativas
3. **Processo travou** (sem atividade por 5 minutos)
4. **Processo crashou** (erro fatal Python)
5. **Download não completou** após 60 segundos
6. **Espaço em disco < 10%**
7. **Memória RAM > 90%** de uso

### **Template de Email:**

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; }
        .alert-box {
            border: 3px solid #f44336;
            background: #ffebee;
            padding: 20px;
            border-radius: 8px;
        }
        .button {
            background: #4CAF50;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 4px;
            display: inline-block;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="alert-box">
        <h2>🤖 Automação #{automacao_id} precisa de ajuda!</h2>

        <p><strong>Tipo de problema:</strong> {tipo_erro}</p>
        <p><strong>Descrição:</strong> {descricao}</p>
        <p><strong>Display:</strong> :{display_num}</p>
        <p><strong>Porta VNC:</strong> {porta_vnc}</p>
        <p><strong>Tempo travado:</strong> {tempo_travado}</p>

        <h3>🔗 Acesso VNC</h3>
        <p>
            <a href="http://{servidor_ip}:{porta_web}/vnc.html?token={token}" class="button">
                🖥️ Acessar Automação via VNC
            </a>
        </p>

        <p><small>⏰ Token expira em: {expiracao}</small></p>

        <h3>📋 O que fazer</h3>
        <ol>
            <li>Clique no link acima para acessar o VNC</li>
            <li>Resolva o problema manualmente (CAPTCHA, login, etc)</li>
            <li>Pressione [R] no terminal para retomar a automação</li>
        </ol>

        <p><small>Este é um alerta automático. Não responda este email.</small></p>
    </div>
</body>
</html>
```

### **Destinatários:**

Configurável em `.env`:
```bash
ALERT_EMAIL_TO="suporte@empresa.com,dev@empresa.com,plantao@empresa.com"
ALERT_EMAIL_CC="gerente@empresa.com"
```

---

## 🚀 Fases de Implementação

### **Fase 1: Documentação (ATUAL)** ✍️
- [x] Criar docs/01-VISAO-GERAL.md
- [ ] Criar docs/02-REQUISITOS-INFRAESTRUTURA.md
- [ ] Criar docs/03-SETUP-DISPLAYS-VNC.md
- [ ] Criar docs/04-SEGURANCA-VNC.md
- [ ] Criar docs/05-SISTEMA-ALERTAS.md
- [ ] Criar docs/06-ORQUESTRADOR.md

### **Fase 2: Prova de Conceito (POC)** 🧪
- [ ] Rodar 2 processadores em paralelo
- [ ] Testar sistema de email
- [ ] Testar recuperação manual via VNC
- [ ] Validar tokens temporários

### **Fase 3: Orquestrador** 🎛️
- [ ] Desenvolver orquestrador central
- [ ] Sistema de monitoramento
- [ ] Dashboard web (opcional)
- [ ] Sistema de tokens VNC

### **Fase 4: Escalar para Produção** 📈
- [ ] Provisionar VM de produção
- [ ] Configurar 12 displays + VNC
- [ ] Deploy de 12 processadores
- [ ] Testes de carga 24/7
- [ ] Documentação de operação

---

## 📝 Próximos Passos

1. **Revisar esta documentação** com a equipe
2. **Criar documento de requisitos de infraestrutura**
3. **Provisionar VM de testes** (POC com 2 automações)
4. **Desenvolver orquestrador** básico
5. **Testar sistema completo** por 48h
6. **Escalar para produção** (12 automações)

---

## 🤝 Contribuidores

- **Desenvolvimento:** Claude Code + Equipe Dev
- **Infraestrutura:** Equipe DevOps
- **Processos:** Equipe PROSPER ERP

---

**Última atualização:** 2025-10-20
