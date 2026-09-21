# Documentação: Processador de Relatório de Títulos em Aberto

## 📋 Sumário

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Arquitetura Técnica](#arquitetura-técnica)
- [Fluxo de Execução](#fluxo-de-execução)
- [Configuração](#configuração)
- [Como Executar](#como-executar)
- [Logs e Monitoramento](#logs-e-monitoramento)
- [Troubleshooting](#troubleshooting)

---

## 📊 Visão Geral

**Processador**: `relatorio_titulos_aberto.py`
**Localização**: `/home/ubuntu/PROSPER-ERP-AUTOMATION/src/processors/web/relatorio_titulos_aberto.py`
**Objetivo**: Automatizar a extração de relatório de títulos em aberto do SmartSecurities em formato CSV.

### Características Principais

- ✅ **Modo LOOP**: Executa continuamente em loop (intervalo configurável de 30s)
- ✅ **Nodriver**: Usa Nodriver ao invés de Playwright (mais leve)
- ✅ **CAPTCHA Automático**: Resolução via CapSolver
- ✅ **Navegação em Iframes**: Estrutura complexa de framesets
- ✅ **Download Automático**: Aguarda e renomeia arquivo CSV
- ✅ **API de Controle**: Permite pausar/retomar remotamente (porta 6091)
- ✅ **Notificações**: Email ao iniciar sessão
- ✅ **Logs Estruturados**: Logging com timestamps

---

## 🎯 Funcionalidades

### 1. Login Automatizado

**URL**: `https://www.smartsecurities.com.br/smartsecurities/`

#### Fluxo de Login:
1. Acessa página de login
2. Aguarda iframe de login carregar (`loginsec.php`)
3. Preenche credenciais (`.env`)
4. Clica botão OK
5. Resolve CAPTCHA automaticamente (CapSolver)
6. Aguarda redirecionamento para dashboard

**Credenciais**:
- Carregadas de variáveis de ambiente (`.env`)
- `USUARIO_SITE_SMART` e `SENHA_SITE_SMART`

### 2. Navegação para Relatório

**URL**: `https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php`

- Navegação via JavaScript (`document.getElementById('code').src`)
- Aguarda 5 segundos para carregamento completo

### 3. Preenchimento de Formulário

#### Dados do Formulário:
- **Data Inicial**: 1 ano atrás (captura histórico de 12 meses)
- **Data Final**: Data atual
- **Checkbox**: Recomendação de recompra (desmarcado)

#### Navegação em Iframes:
```
document
└── frame#code
    └── frame[name="text"] ou primeiro iframe
        ├── input#Emissao1 (Data Inicial)
        ├── input#Emissao23 ou #Emissao2 (Data Final)
        └── input#recomendacaoRecompraConfirmacao (Checkbox)
```

### 4. Geração de CSV

1. Clica no botão "Pesquisar"
2. Aguarda 8s para resultados carregarem
3. Verifica se há CAPTCHA após pesquisa
4. Marca checkbox "Selecionar Todos" (`cSelecionarTodos`)
5. Clica no botão "Gerar CSV" (`ImprimirCSV`)
6. Verifica novamente se há CAPTCHA

### 5. Download e Renomeação

#### Aguardar Download:
```python
# Monitora diretório: data/raw_inputs/
# Timeout: 90 segundos
# Detecta arquivo:
- Novo arquivo CSV
- Modificação recente (timestamp > início da espera)
```

#### Renomeação Automática:
```python
# De: arquivo_original.csv
# Para: titulos_abertos_YYYY_MM_DD_HHMMSS.csv

# Formato: titulos_abertos_{timestamp}.csv
```

### 6. Notificações por Email

**Quando envia**:
- ✅ Ao iniciar sessão (primeira execução)
- ✅ Em caso de erro crítico

**Destinatário**: Configurado em `.env` (`EMAIL_DESTINATARIO`)

---

## 🏗️ Arquitetura Técnica

### Dependências

```python
- nodriver (Browser automation - leve e rápido)
- asyncio (Async/await support)
- src.common.utils.nodriver_utils (Inicialização de browser)
- src.common.captcha.captcha_solver (CapSolver API)
- src.common.utils.notification_utils (Email notifications)
- src.api.control_api_titulos (API de controle remoto - porta 6091)
```

### Diferenças vs `relatorio_operacao_desagio.py`

| Característica | `relatorio_titulos_aberto.py` | `relatorio_operacao_desagio.py` |
|---------------|-------------------------------|----------------------------------|
| **Framework** | Nodriver | Playwright |
| **Modo** | Loop contínuo | One-shot |
| **Display** | :2 | :1 |
| **VNC Port** | 6081 | 6080 |
| **API Port** | 6091 | 6092 |
| **URL** | titulosemaberto.php | detalhamentodesagio.php |
| **Período** | 1 ano | 10 anos |
| **Intervalo** | 30 segundos | N/A (uma vez) |
| **Perfil** | Temporário (limpo a cada execução) | Persistente |

---

## 🔄 Fluxo de Execução

### Diagrama Completo

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. INICIALIZAÇÃO                                                │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Carrega credenciais do .env                                  │
│ ✓ Cria perfil temporário do Chrome                             │
│ ✓ Inicializa browser Nodriver (headless=false)                 │
│ ✓ Inicia API de controle (porta 6091)                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. LOGIN (ETAPA 1 - Apenas na primeira execução)               │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Acessa smartsecurities.com.br                                │
│ ✓ Aguarda iframe de login (loginsec.php)                       │
│ ✓ Preenche email + senha                                       │
│ ✓ Clica botão OK                                               │
│ ✓ Resolve CAPTCHA via CapSolver                                │
│ ✓ Clica botão OK final                                         │
│ ✓ Aguarda redirecionamento                                     │
│ ✓ Envia notificação de login por email                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. LOOP INFINITO (CICLOS DE EXTRAÇÃO)                          │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ CICLO DE EXTRAÇÃO                                           │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ ✓ ETAPA 3: Navegar para titulosemaberto.php                │ │
│ │ ✓ ETAPA 4: Verificar CAPTCHA (se aparecer)                 │ │
│ │ ✓ ETAPA 5: Verificar frames prontos                        │ │
│ │ ✓ ETAPA 6: Preencher datas (inicial: -1 ano, final: hoje)  │ │
│ │ ✓ ETAPA 7: Desmarcar checkbox recomendação                 │ │
│ │ ✓ ETAPA 8: Clicar "Pesquisar"                              │ │
│ │ ✓ ETAPA 4 (novamente): Verificar CAPTCHA após pesquisa     │ │
│ │ ✓ ETAPA 5 (novamente): Verificar frames prontos            │ │
│ │ ✓ ETAPA 9: Marcar "Selecionar Todos"                       │ │
│ │ ✓ ETAPA 10: Clicar "Gerar CSV"                             │ │
│ │ ✓ ETAPA 4 (novamente): Verificar CAPTCHA após gerar        │ │
│ │ ✓ ETAPA 11: Aguardar download (90s timeout)                │ │
│ │ ✓ ETAPA 12: Renomear arquivo                               │ │
│ │ ✓ Aguardar 30 segundos                                     │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                           ↓                                     │
│                      Loop continua                              │
└─────────────────────────────────────────────────────────────────┘
```

### Timing Médio

| Etapa | Tempo |
|-------|-------|
| Login (primeira vez) | ~30s |
| Navegação | 5s |
| Preencher formulário | 10s |
| Pesquisar + aguardar | 8s |
| Gerar CSV + CAPTCHA | 15-20s |
| Download | 10-40s |
| **Total por ciclo** | **~1-2 minutos** |
| **Intervalo entre ciclos** | **30 segundos** |

---

## ⚙️ Configuração

### 1. Variáveis de Ambiente (`.env`)

```bash
# Credenciais SmartSecurities
USUARIO_SITE_SMART=seu_email@exemplo.com
SENHA_SITE_SMART=SuaSenha123

# CapSolver API
CAPSOLVER_API_KEY=CAP-xxxxxxxxxxxxx

# Servidor
SERVER_IP=3.148.126.73

# Email (Notificações)
SMTP_SERVER=smtp.mailersend.net
SMTP_PORT=2525
SMTP_USER=MS_xxx
SMTP_PASSWORD=xxx
EMAIL_FROM=prosperito@prosperfidc.online
EMAIL_RECIPIENT=guilherme@prosperinvest.com.br

# Display VNC
DISPLAY=:2  # Display :2 (VNC porta 6081)
```

### 2. Configuração no Código

```python
# Diretórios
DOWNLOAD_DIR = "data/raw_inputs/"

# Timeouts
TIMEOUT_DOWNLOAD = 90  # segundos
INTERVALO_LOOP = 30  # 30 segundos entre extrações

# Display e Portas
DISPLAY = ":2"
VNC_PORT = 6081  # Calculado: 6080 + (display_num - 1)
API_PORT = 6091
```

---

## 🚀 Como Executar

### Execução Manual

```bash
# 1. Ativar ambiente virtual
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate

# 2. Verificar VNC (display :2)
./scripts/iniciar_vnc_displays.sh status

# 3. Executar processador (loop contínuo)
DISPLAY=:2 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/relatorio_titulos_aberto.py
```

### Execução via Systemd (Recomendado)

```bash
# Criar serviço systemd
sudo nano /etc/systemd/system/relatorio-titulos-aberto.service
```

```ini
[Unit]
Description=Processador - Relatório Títulos Aberto
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/PROSPER-ERP-AUTOMATION
Environment="DISPLAY=:2"
Environment="PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION"
ExecStart=/home/ubuntu/PROSPER-ERP-AUTOMATION/venv/bin/python3 src/processors/web/relatorio_titulos_aberto.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Habilitar e iniciar
sudo systemctl daemon-reload
sudo systemctl enable relatorio-titulos-aberto
sudo systemctl start relatorio-titulos-aberto

# Verificar status
sudo systemctl status relatorio-titulos-aberto

# Ver logs
sudo journalctl -u relatorio-titulos-aberto -f
```

---

## 📊 Logs e Monitoramento

### Estrutura de Logs

**Logs em console** (stdout):
```
================================================================================
PROCESSADOR: titulos_aberto
INÍCIO: 2025-11-18 10:00:00
================================================================================

[LOGIN] Abrindo página de login...
[LOGIN] Aguardando iframe de login carregar...
[LOGIN] ✅ Iframe encontrado
[LOGIN] ✅ Credenciais preenchidas
[CAPTCHA] Resolvendo CAPTCHA...
[LOGIN] ✅ Login realizado com sucesso!

[EMAIL] ✅ Notificação de login enviada

████████████████████████████████████████████████████████████████████████████████
█ CICLO #1 - 10:01:30
████████████████████████████████████████████████████████████████████████████████

[NAVEGAÇÃO] Carregando página via JavaScript...
[NAVEGAÇÃO] ✅ Página carregada

[FRAMES] ✅ Frames prontos!

[DATAS] Inicial: 18/11/2024
[DATAS] Final: 18/11/2025
[DATAS] ✅ Data inicial: 18/11/2024
[DATAS] ✅ Data final: 18/11/2025

[PESQUISAR] ✅ Clicado!
[PESQUISAR] ⏳ Aguardando 8s para resultados carregarem...

[SELECIONAR] ✅ Marcado!

[GERAR CSV] ✅ Clicado!

[DOWNLOAD] ✅ Arquivo baixado: arquivo_original.csv

[RENOMEAR] ✅ Arquivo renomeado
[RENOMEAR] Para: titulos_abertos_2025_11_18_100215.csv

================================================================================
✅ CICLO CONCLUÍDO!
✅ Arquivo: titulos_abertos_2025_11_18_100215.csv
================================================================================

⏱️  Aguardando 30s...
```

### Arquivos Gerados

```bash
# CSVs baixados
data/raw_inputs/titulos_abertos_2025_11_18_100215.csv
data/raw_inputs/titulos_abertos_2025_11_18_100330.csv
...
```

### Monitoramento em Tempo Real

#### VNC (Visual):
```
http://3.148.126.73:6081/vnc.html
```

#### API de Controle (porta 6091):
```bash
# Status
curl http://3.148.126.73:6091/status

# Parar processador
curl -X POST http://3.148.126.73:6091/stop

# Pausar (se suportado)
curl -X POST http://3.148.126.73:6091/pause
```

---

## 🐛 Troubleshooting

### Problema: CAPTCHA não é resolvido

**Sintomas**:
```
[CAPTCHA] ⚠️ Não foi resolvido
```

**Causas**:
- CapSolver API falhou ou sem créditos
- Timeout de resolução excedido

**Solução**:
```bash
# Verificar saldo CapSolver
curl "https://api.capsolver.com/getBalance" \
  -H "Content-Type: application/json" \
  -d '{"clientKey":"SUA_API_KEY"}'

# Verificar .env
grep CAPSOLVER_API_KEY .env
```

### Problema: Frames não ficam prontos

**Sintomas**:
```
[FRAMES] ❌ Frames não ficaram prontos
```

**Causas**:
- Página demorou mais que 10 tentativas (20s)
- Estrutura de iframes mudou

**Solução**:
1. Acesse VNC: http://3.148.126.73:6081/vnc.html
2. Inspecione a página manualmente
3. Verifique se estrutura de iframes mudou
4. Aumente o número de tentativas no código se necessário

### Problema: Download não inicia

**Sintomas**:
```
[DOWNLOAD] Timeout: arquivo CSV não baixado em 90s
```

**Diagnóstico**:
1. Verificar se botão "Gerar CSV" foi clicado
2. Verificar se há CAPTCHA bloqueando
3. Verificar diretório de download

**Solução**:
```bash
# Verificar se diretório existe
ls -la data/raw_inputs/

# Ver arquivos recentes
find data/raw_inputs/ -name "*.csv" -mmin -10

# Aumentar timeout se necessário
# No código: TIMEOUT_DOWNLOAD = 120
```

### Problema: Nodriver não instalado

**Sintomas**:
```
⚠️ Nodriver não instalado. Execute: pip install nodriver
```

**Solução**:
```bash
pip install nodriver
```

### Problema: Loop não para

**Causas**:
- Processador está em loop infinito (comportamento esperado)
- Para parar: Ctrl+C ou usar API de controle

**Solução**:
```bash
# Via API
curl -X POST http://3.148.126.73:6091/stop

# Ou: Ctrl+C no terminal
```

---

## 🔐 Segurança

### Credenciais

- ✅ Armazenadas em `.env` (gitignored)
- ✅ Perfil temporário de Chrome (limpo a cada execução)
- ⚠️ Screenshots podem conter dados sensíveis

### CAPTCHA

- ✅ API key da CapSolver em `.env`
- ⚠️ Custos: ~$0.0005 por CAPTCHA resolvido

---

## 📚 Referências

### Código Fonte

- **Processador principal**: `src/processors/web/relatorio_titulos_aberto.py`
- **Utils Nodriver**: `src/common/utils/nodriver_utils.py`
- **CAPTCHA Solver**: `src/common/captcha/captcha_solver.py`
- **API de Controle**: `src/api/control_api_titulos.py`

### Processadores Relacionados

- **Processador similar**: `relatorio_operacao_desagio.py` (mesma estrutura de login, mas usa Playwright)

### URLs do Sistema

- **Login**: https://www.smartsecurities.com.br/smartsecurities/
- **Títulos Abertos**: https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php
- **Documentação CapSolver**: https://docs.capsolver.com/

---

## 📝 Changelog

### 2025-11-18 - Versão 1.0 (Documentação Inicial)

- ✅ Documentação completa criada
- ✅ Processador usa Nodriver (não Playwright)
- ✅ Modo loop contínuo (30s de intervalo)
- ✅ API de controle na porta 6091
- ✅ Notificações por email
- ✅ Perfil temporário de Chrome (limpo a cada execução)

### 2024-10-21 - Versão 2.0 (Refatoração)

- ✅ Refatorado para padronização
- ✅ Migração para Nodriver
- ✅ Estrutura de iframes atualizada
- ✅ Sistema de notificações

---

**Documentação criada em**: 2025-11-18
**Última atualização**: 2025-11-18
**Versão do processador**: v2.0
**Autor**: PROSPER-ERP-AUTOMATION Team
