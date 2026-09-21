# Documentação: Processador de Retry - Envio de Boletos (Operação Oculto)

## 📋 Sumário

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Arquitetura Técnica](#arquitetura-técnica)
- [Fluxo de Execução](#fluxo-de-execução)
- [Configuração](#configuração)
- [Como Executar](#como-executar)
- [Estrutura de Checkpoints](#estrutura-de-checkpoints)
- [Troubleshooting](#troubleshooting)

---

## 📊 Visão Geral

**Processador**: `envio_boleto_operacao_oculto_retry.py`
**Localização**: `/home/ubuntu/PROSPER-ERP-AUTOMATION/src/processors/web/envio_boleto_operacao_oculto_retry.py`
**Objetivo**: Reexecutar operações que falharam durante a execução do processador principal `envio_boleto_operacao_oculto.py`.

### Características Principais

- ✅ **Herda do processador principal**: Reutiliza toda a lógica de processamento
- ✅ **Lê arquivos de checkpoint**: Processa operações salvas em JSON
- ✅ **Agrupamento por credenciais**: Otimiza logins (igual ao principal)
- ✅ **Rastreamento de arquivos**: Move arquivos processados para `processed/` ou `failed/`
- ✅ **Retry incrementado**: Incrementa contador de tentativas
- ✅ **Geração de novos checkpoints**: Salva operações que falharam novamente
- ✅ **Modo one-shot ou loop**: Configurável via `processors.yaml`

---

## 🎯 Funcionalidades

### 1. Carregamento de Operações Falhadas

**Diretório de origem**: `data/checkpoints/`

**Arquivos processados**:
- **Padrão**: `envio_boleto_operacao_oculto_failed_YYYYMMDD_HHMMSS.json`
- **Gerados por**: Processador principal quando operações falham

**Estrutura esperada do JSON**:
```json
{
  "timestamp": "2025-11-17T08:05:00",
  "processador": "envio_boleto_operacao_oculto",
  "operacoes_falhadas": [
    {
      "id_operacao": 12347,
      "conta_bancaria": "Banco X",
      "login_smart": "user@email.com",
      "senha_smart": "senha123",
      "erro": "Timeout ao aguardar iframe",
      "tentativa": 1,
      "data_original": "2025-11-17"
    }
  ]
}
```

### 2. Agrupamento por Credenciais

**Otimização**: Igual ao processador principal
- Agrupa operações por `(login_smart, senha_smart)`
- Faz **1 login por grupo** ao invés de 1 login por operação
- Processa todas as operações do grupo na mesma sessão

### 3. Processamento de Retry

Para cada operação:
1. **Login** (uma vez por grupo)
2. **Navega** para página de emissão
3. **Seleciona** conta bancária
4. **Preenche** nop1 e nop2
5. **Gera** boleto
6. **Envia** por e-mail com mensagem personalizada
7. **Retorna** para página de emissão (próxima operação)

**Delays entre operações**:
- Operações 1-3: 40s
- Operações 4-6: 50s
- Operações 7+: 60s

### 4. Movimentação de Arquivos

Após processar um arquivo de checkpoint:

#### Sucesso (todas operações processadas):
```
data/checkpoints/envio_boleto_operacao_oculto_failed_20251117_080500.json
→ data/checkpoints/processed/envio_boleto_operacao_oculto_failed_20251117_080500.json
```

#### Falha parcial/total:
```
data/checkpoints/envio_boleto_operacao_oculto_failed_20251117_080500.json
→ data/checkpoints/failed/envio_boleto_operacao_oculto_failed_20251117_080500.json
```

### 5. Geração de Novos Checkpoints

Se operações falharem novamente, um novo arquivo é gerado:

```
data/checkpoints/envio_boleto_operacao_oculto_failed_retry_20251118_094530.json
```

**Diferenças no novo checkpoint**:
- Nome do arquivo inclui `_retry_`
- Campo `tentativa` é incrementado (1 → 2, 2 → 3, etc.)
- Campo `erro` é atualizado com novo erro

---

## 🏗️ Arquitetura Técnica

### Herança

```python
class ProcessadorEnvioBoletoOperacaoOcultaRetry(ProcessadorEnvioBoletoOperacaoOculto):
    """
    Herda do processador principal para reutilizar toda a lógica.
    Sobrescreve apenas o método de busca de operações.
    """
```

**Métodos sobrescritos**:
- `__init__()`: Recria logger, screenshot manager e CAPTCHA manager com nome correto
- `buscar_operacoes_ocultas()`: Carrega de arquivos JSON ao invés do banco de dados

**Métodos novos**:
- `carregar_operacoes_falhadas()`: Lê arquivos JSON de checkpoints
- `mover_arquivo_processado()`: Move arquivo para `processed/` ou `failed/`
- `executar_retry()`: Fluxo principal do retry

### Dependências

```python
from src.processors.web.envio_boleto_operacao_oculto import (
    ProcessadorEnvioBoletoOperacaoOculto,
    URL_LOGIN,
    URL_EMISSAO,
    converter_mensagem_para_html,
    carregar_mensagem_boletos
)
```

**Reutiliza do processador principal**:
- Login automatizado
- Navegação para emissão
- Processamento de operação
- Agrupamento por credenciais
- CAPTCHA resolution
- Screenshot management
- Execution logging

---

## 🔄 Fluxo de Execução

### Diagrama Completo

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. INICIALIZAÇÃO                                                │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Herda de ProcessadorEnvioBoletoOperacaoOculto                │
│ ✓ Recria logger com nome "envio_boleto_operacao_oculto_retry"  │
│ ✓ Recria screenshot manager e CAPTCHA manager                  │
│ ✓ Carrega configuração de processors.yaml (se existir)         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. CARREGAMENTO DE OPERAÇÕES FALHADAS                          │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Busca arquivos: data/checkpoints/envio_*_failed_*.json       │
│ ✓ Lê cada arquivo JSON                                         │
│ ✓ Valida estrutura (operacoes_falhadas)                        │
│ ✓ Adiciona campo interno _arquivo_origem                       │
│ ✓ Acumula todas operações em lista única                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. AGRUPAMENTO POR CREDENCIAIS                                 │
├─────────────────────────────────────────────────────────────────┤
│ ✓ Agrupa por (login_smart, senha_smart)                        │
│ ✓ Exemplo:                                                     │
│   Grupo 1 (user1@email.com): [Op 123, Op 124, Op 126]         │
│   Grupo 2 (user2@email.com): [Op 125]                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. PROCESSAMENTO POR GRUPO                                     │
├─────────────────────────────────────────────────────────────────┤
│ Para cada grupo:                                               │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ ✓ Inicializa browser (stealth)                             │ │
│ │ ✓ Faz login com credenciais do grupo                       │ │
│ │ ✓ Navega para página de emissão                            │ │
│ │                                                             │ │
│ │ Para cada operação do grupo:                               │ │
│ │ ┌───────────────────────────────────────────────────────┐   │ │
│ │ │ ✓ Processa operação (mesma lógica do principal)      │   │ │
│ │ │ ✓ Se sucesso: incrementa contador de sucessos        │   │ │
│ │ │ ✓ Se falha: adiciona a operacoes_falhadas_novamente  │   │ │
│ │ │ ✓ Se não for última: retorna para página de emissão  │   │ │
│ │ │ ✓ Aguarda delay (40s, 50s ou 60s)                    │   │ │
│ │ └───────────────────────────────────────────────────────┘   │ │
│ │                                                             │ │
│ │ ✓ Fecha browser                                             │ │
│ │ ✓ Aguarda 30s antes do próximo grupo                       │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. MOVIMENTAÇÃO DE ARQUIVOS PROCESSADOS                        │
├─────────────────────────────────────────────────────────────────┤
│ Para cada arquivo de checkpoint original:                     │
│                                                                │
│ ✓ Se TODAS operações foram bem-sucedidas:                     │
│   → Move para data/checkpoints/processed/                     │
│                                                                │
│ ✓ Se ALGUMA operação falhou:                                  │
│   → Move para data/checkpoints/failed/                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. SALVAMENTO DE NOVAS FALHAS                                  │
├─────────────────────────────────────────────────────────────────┤
│ Se operacoes_falhadas_novamente > 0:                          │
│                                                                │
│ ✓ Cria arquivo:                                                │
│   envio_boleto_operacao_oculto_failed_retry_YYYYMMDD_HHMMSS   │
│                                                                │
│ ✓ Incrementa campo tentativa (1 → 2)                          │
│ ✓ Atualiza campo erro com novo erro                           │
│ ✓ Mantém campos originais (id_operacao, conta_bancaria, etc.) │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. RESUMO FINAL                                                 │
├─────────────────────────────────────────────────────────────────┤
│ ✅ Total de operações: X                                       │
│ ✅ Sucessos: Y                                                 │
│ ❌ Erros: Z                                                    │
│ 📁 Arquivos processados com sucesso: A                         │
│ 📁 Arquivos com erros: B                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Configuração

### 1. Arquivo: `config/processors.yaml`

**Configuração específica do retry** (opcional):

```yaml
envio_boleto_operacao_oculto_retry:
  enabled: true
  mode: one-shot  # ou "loop"
  schedule: "0 9 * * *"  # Todo dia às 9h (1h após o principal)

  # Display e porta
  display: ":4"
  vnc_port: 6083  # Display :4 → Porta 6083

  # Screenshots
  screenshot_level: milestones  # none | errors-only | milestones | full
  enable_screenshots: true

  # Timeouts
  timeout_captcha: 100

  # Intervals (se mode = loop)
  interval_seconds: 3600  # 1 hora
```

**Se não configurado**: Usa valores padrão do código.

### 2. Variáveis de Ambiente

**Mesmas do processador principal**:

```bash
# CAPTCHA
CAPSOLVER_API_KEY=CAP-xxxxxxxxxxxxx

# Display
DISPLAY=:4  # Display :4 (VNC porta 6083)

# Servidor
SERVER_IP=3.148.126.73

# Debug
DEBUG_MODE=false
```

---

## 🚀 Como Executar

### Modo One-Shot (Padrão)

```bash
# 1. Verificar se há arquivos de retry
ls -la data/checkpoints/envio_boleto_operacao_oculto_failed_*.json

# 2. Se houver arquivos, executar retry
DISPLAY=:4 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto_retry.py
```

### Modo Debug (Browser Permanece Aberto)

```bash
DISPLAY=:4 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto_retry.py
```

### Via Cron (Agendamento Automático)

```bash
# Editar crontab
crontab -e

# Adicionar linha (todo dia às 9h - 1h após o principal)
0 9 * * * cd /home/ubuntu/PROSPER-ERP-AUTOMATION && \
  DISPLAY=:4 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto_retry.py \
  >> logs/cron_envio_boleto_oculto_retry.log 2>&1
```

### Modo Loop (Execução Contínua)

**Configurar em `processors.yaml`**:
```yaml
envio_boleto_operacao_oculto_retry:
  mode: loop
  interval_seconds: 3600  # 1 hora
```

**Executar**:
```bash
DISPLAY=:4 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto_retry.py
```

---

## 📁 Estrutura de Checkpoints

### Diretórios

```
data/checkpoints/
├── envio_boleto_operacao_oculto_failed_20251117_080500.json  # Aguardando retry
├── envio_boleto_operacao_oculto_failed_20251117_090230.json  # Aguardando retry
│
├── processed/  # Arquivos totalmente processados
│   └── envio_boleto_operacao_oculto_failed_20251116_080500.json
│
└── failed/  # Arquivos com operações que falharam novamente
    └── envio_boleto_operacao_oculto_failed_20251115_080500.json
```

### Exemplo de Arquivo de Checkpoint

**Arquivo original** (gerado pelo principal):
```json
{
  "timestamp": "2025-11-17T08:05:00",
  "processador": "envio_boleto_operacao_oculto",
  "operacoes_falhadas": [
    {
      "id_operacao": 12347,
      "conta_bancaria": "Banco do Brasil",
      "login_smart": "user@email.com",
      "senha_smart": "senha123",
      "erro": "Timeout ao aguardar iframe de títulos",
      "tentativa": 1,
      "data_original": "2025-11-16"
    },
    {
      "id_operacao": 12348,
      "conta_bancaria": "Itaú",
      "login_smart": "user@email.com",
      "senha_smart": "senha123",
      "erro": "HTTP 429 - Too Many Requests",
      "tentativa": 1,
      "data_original": "2025-11-16"
    }
  ]
}
```

**Novo arquivo de retry** (se operações falharem novamente):
```json
{
  "timestamp": "2025-11-18T09:15:30",
  "processador": "envio_boleto_operacao_oculto_retry",
  "operacoes_falhadas": [
    {
      "id_operacao": 12347,
      "conta_bancaria": "Banco do Brasil",
      "login_smart": "user@email.com",
      "senha_smart": "senha123",
      "erro": "Timeout ao aguardar iframe de títulos",
      "tentativa": 2,  // Incrementado!
      "data_original": "2025-11-16"
    }
  ]
}
```

---

## 📊 Logs e Monitoramento

### Estrutura de Logs

**Arquivo**: `logs/envio_boleto_operacao_oculto_retry_YYYYMMDD_HHMMSS.log`

**Exemplo**:
```
[2025-11-18 09:00:00] 🚀 Processador de RETRY 'envio_boleto_operacao_oculto_retry' inicializado
[2025-11-18 09:00:00] 📁 Diretório de checkpoints: /home/ubuntu/PROSPER-ERP-AUTOMATION/data/checkpoints
[2025-11-18 09:00:00] 🔍 Buscando arquivos de operações falhadas...
[2025-11-18 09:00:00] ✅ 2 arquivo(s) de retry encontrado(s)
[2025-11-18 09:00:00]    📄 Lendo arquivo: envio_boleto_operacao_oculto_failed_20251117_080500.json
[2025-11-18 09:00:00]    ✅ 3 operação(ões) encontrada(s) no arquivo
[2025-11-18 09:00:00]    📄 Lendo arquivo: envio_boleto_operacao_oculto_failed_20251117_090230.json
[2025-11-18 09:00:00]    ✅ 2 operação(ões) encontrada(s) no arquivo
[2025-11-18 09:00:00] ✅ Total de 5 operação(ões) falhada(s) carregada(s) de 2 arquivo(s)
[2025-11-18 09:00:00] 📊 Operações agrupadas em 2 arquivo(s)

================================================================================
🔄 RETRY - GRUPO 1/2 - Login: user@email.com
   Operações neste grupo: 3
================================================================================

[2025-11-18 09:00:05] ✅ Browser inicializado
[2025-11-18 09:00:30] ✅ Login realizado com sucesso

--------------------------------------------------------------------------------
🔄 RETRY - OPERAÇÃO 1/5 (Grupo 1, Op 1/3)
   ID: 12347, Conta: Banco do Brasil
   Tentativa anterior: 1
   Erro anterior: Timeout ao aguardar iframe de títulos
--------------------------------------------------------------------------------

[2025-11-18 09:01:00] 📧 Operação 12347 processada com sucesso
...

================================================================================
📁 Movendo arquivos processados...
================================================================================
   ✅ Arquivo envio_boleto_operacao_oculto_failed_20251117_080500.json: todas operações processadas com sucesso
   ⚠️ Arquivo envio_boleto_operacao_oculto_failed_20251117_090230.json: algumas operações falharam novamente

📝 1 operação(ões) falharam novamente - salvas em: data/checkpoints/envio_boleto_operacao_oculto_failed_retry_20251118_090430.json

================================================================================
📊 RESUMO DO RETRY
================================================================================
Total de operações: 5
✅ Sucessos: 4
❌ Erros: 1
📁 Arquivos processados com sucesso: 1
📁 Arquivos com erros: 1
================================================================================

✅ Retry concluído
```

### Monitoramento VNC

**URL**: `http://3.148.126.73:6083/vnc.html` (Display :4)

---

## 🔧 Troubleshooting

### Problema: Nenhum arquivo de retry encontrado

**Sintomas**:
```
⚠️ Nenhum arquivo de operações falhadas encontrado
```

**Causas**:
- Processador principal não gerou arquivos de checkpoint (todas operações com sucesso)
- Arquivos já foram processados e movidos para `processed/` ou `failed/`

**Solução**:
```bash
# Verificar arquivos existentes
ls -la data/checkpoints/

# Verificar arquivos processados
ls -la data/checkpoints/processed/
ls -la data/checkpoints/failed/
```

### Problema: Operação falha novamente com mesmo erro

**Sintomas**:
```
⚠️ Operação falhou novamente: Timeout ao aguardar iframe
```

**Causas**:
- Erro persistente no site (SmartSecurities)
- Conta bancária sem títulos
- Timeout muito curto
- Proxy instável

**Solução**:
```bash
# Executar em modo DEBUG para investigar
DISPLAY=:4 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto_retry.py

# Acessar VNC para visualizar
# http://3.148.126.73:6083/vnc.html
```

### Problema: Todas operações falharam (erro de grupo)

**Sintomas**:
```
⚠️ Erro ao processar grupo 'user@email.com': ...
```

**Causas**:
- Erro de login (credenciais inválidas)
- Erro de proxy
- CAPTCHA não resolvido

**Solução**:
1. Verificar credenciais no banco de dados
2. Verificar saldo CapSolver
3. Verificar proxy BrightData

### Problema: Arquivo movido para `failed/` mas deveria estar em `processed/`

**Causa**:
- Pelo menos uma operação do arquivo falhou novamente

**Solução**:
- Normal - arquivo ficará em `failed/` e um novo checkpoint de retry será gerado
- As operações que falharam novamente estarão no novo arquivo `_retry_`
- Executar retry novamente no dia seguinte

---

## 📈 Estatísticas e Performance

### Tempo Médio

- **Login**: ~10 segundos (por grupo)
- **Processamento por operação**: ~15 segundos
- **Delays entre operações**: 40-60 segundos (progressivo)
- **Total (5 operações, 2 grupos)**: ~6-8 minutos

### Taxa de Sucesso Esperada

- **1ª tentativa (processador principal)**: 85-95%
- **2ª tentativa (primeiro retry)**: 70-80%
- **3ª tentativa (segundo retry)**: 50-60%

**Nota**: Taxa diminui pois erros persistentes indicam problemas estruturais (conta inválida, sem títulos, etc.)

---

## 🔗 Arquivos Relacionados

- **Processador principal**: `src/processors/web/envio_boleto_operacao_oculto.py`
- **Documentação do principal**: `docs/processors/PROCESSADOR_ENVIO_BOLETO_OPERACAO_OCULTO.md`
- **Checkpoints**: `data/checkpoints/envio_boleto_operacao_oculto_failed_*.json`
- **Logs**: `logs/envio_boleto_operacao_oculto_retry_*.log`

---

## 📝 Changelog

### 2025-11-18 - Versão 1.0 (Documentação Inicial)

- ✅ Documentação completa criada
- ✅ Processador de retry implementado
- ✅ Herança do processador principal
- ✅ Sistema de movimentação de arquivos
- ✅ Geração de novos checkpoints de retry
- ✅ Incremento de contador de tentativas

### 2025-11-14 - Versão 1.0 (Implementação)

- ✅ Implementação inicial
- ✅ Herança de `ProcessadorEnvioBoletoOperacaoOculto`
- ✅ Leitura de arquivos JSON
- ✅ Movimentação para `processed/` e `failed/`
- ✅ Suporte a modo one-shot e loop

---

**Última atualização**: 2025-11-18
**Versão do documento**: 1.0
**Autor**: Sistema de Automação PROSPER
