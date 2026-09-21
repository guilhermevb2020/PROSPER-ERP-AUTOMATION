# Documentação: Processador de Envio de Boletos (Operação Oculto)

## 📋 Sumário

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Arquitetura Técnica](#arquitetura-técnica)
- [Fluxo de Execução](#fluxo-de-execução)
- [Configuração](#configuração)
- [Como Executar](#como-executar)
- [Logs e Monitoramento](#logs-e-monitoramento)
- [Tratamento de Erros](#tratamento-de-erros)
- [Sistema de Retry](#sistema-de-retry)
- [Troubleshooting](#troubleshooting)

---

## 📊 Visão Geral

**Processador**: `envio_boleto_operacao_oculto.py`
**Localização**: `/home/ubuntu/PROSPER-ERP-AUTOMATION/src/processors/web/envio_boleto_operacao_oculto.py`
**Objetivo**: Automatizar o envio de boletos de operações ocultas por e-mail no sistema SmartSecurities.

### Características Principais

- ✅ Processamento em lote de operações ocultas
- ✅ Consulta ao banco de dados (`api.erp_operacoes_ocultas_dia_anterior`)
- ✅ **Login por operação** (cada operação usa credenciais específicas)
- ✅ **Agrupamento por credenciais** (otimização de logins)
- ✅ Resolução automática de CAPTCHA (CapSolver)
- ✅ Navegação em estrutura complexa de iframes
- ✅ Envio automático de boletos por e-mail
- ✅ **Mensagem personalizada** (carrega template de mensagem_boletos.txt)
- ✅ **Retry automático** (até 2 tentativas por operação)
- ✅ Tratamento robusto de erros HTTP 429 (rate limiting)
- ✅ **Checkpoint Manager** (salva operações falhadas para retry posterior)
- ✅ Logs detalhados e screenshots
- ✅ Resumo final com estatísticas de execução

---

## 🎯 Funcionalidades

### 1. Consulta ao Banco de Dados

O processador consulta a view `api.erp_operacoes_ocultas_dia_anterior` para obter a lista de operações ocultas:

```sql
SELECT id_operacao,
       conta_bancaria,
       login_smart,
       senha_smart
FROM api.erp_operacoes_ocultas_dia_anterior
WHERE data_operacao = CURRENT_DATE - INTERVAL '1 day'
ORDER BY login_smart, senha_smart, conta_bancaria
```

**Resultado**: Lista de operações com:
- `id_operacao`: ID único da operação
- `conta_bancaria`: Conta bancária para seleção no dropdown
- `login_smart`: Credencial de login específica da operação
- `senha_smart`: Senha específica da operação

### 2. Agrupamento por Credenciais

**Otimização**: O processador agrupa operações por credenciais (`login_smart` + `senha_smart`) para:
- **Reduzir logins**: Faz 1 login por grupo ao invés de 1 login por operação
- **Aumentar eficiência**: Processa múltiplas operações na mesma sessão
- **Reduzir detecção**: Menos logins = menos flags de bot

**Exemplo**:
```
Operações originais:
1. Op 123 (user1@email.com / senha1)
2. Op 124 (user1@email.com / senha1)
3. Op 125 (user2@email.com / senha2)
4. Op 126 (user1@email.com / senha1)

Após agrupamento:
Grupo 1 (user1@email.com): [Op 123, Op 124, Op 126]
Grupo 2 (user2@email.com): [Op 125]
```

### 3. Login Automatizado

**URL**: `https://www.smartsecurities.com.br/smartsecurities/`

#### Fluxo de Login (por grupo):
1. Acessa página de login
2. Localiza iframe de login (`loginsec.php`)
3. Preenche credenciais do grupo
4. Resolve CAPTCHA se presente (CapSolver)
5. Submete formulário
6. Aguarda redirecionamento para dashboard
7. **Mantém sessão aberta** para processar todas as operações do grupo

### 4. Processamento de Operação

Para cada operação no grupo:

1. **Navega para página de emissão**
   - URL: `frmimpriboleto.php?Via=2`

2. **Seleciona conta bancária**
   - Dropdown `#cconta_bancaria`
   - Valor: `conta_bancaria` da operação

3. **Preenche campos de busca**
   - `#nop1`: `id_operacao`
   - `#nop2`: `id_operacao`

4. **Gera boleto**
   - Clica botão "Gerar boleto"
   - Aguarda carregamento do iframe de títulos

5. **Trabalha com iframe de títulos**
   - Iframe: `listatitulosboletos.php`
   - Marca checkbox "Selecionar Todos Email"
   - Clica "Enviar por e-mail"

6. **Aceita confirmação**
   - Dialog de confirmação
   - Clica "OK"

7. **Preenche e envia e-mail**
   - Nova janela popup abre
   - Substitui conteúdo do `body#tinymce` com mensagem personalizada
   - Mensagem carregada de `data/assets/email/templates/mensagem_boletos.txt`
   - Clica "Enviar"
   - Aguarda popup fechar

8. **Aguarda intervalo**
   - Se não for a última operação do grupo: aguarda 5 segundos

### 5. Finalização de Grupo

Após processar todas as operações do grupo:
1. Fecha browser (logout implícito)
2. Aguarda intervalo antes do próximo grupo:
   - **10 segundos** (padrão)
   - **30 segundos** (se houve erro de proxy)

---

## 🏗️ Arquitetura Técnica

### Tecnologias

- **Playwright (Async)**: Automação web
- **PostgreSQL**: Banco de dados (via `src.common.core.database`)
- **CapSolver**: Resolução de CAPTCHA
- **CheckpointManager**: Sistema de checkpoint e retry
- **ExecutionLogger**: Logging estruturado
- **ScreenshotManager**: Gerenciamento de screenshots

### Módulos Utilizados

```python
from src.common.core.database import query
from src.common.core.checkpoint_manager import CheckpointManager, criar_operacao_falhada
from src.common.utils.wait_utils import (
    wait_for_page_ready,
    wait_for_element,
    smart_wait,
    wait_for_navigation_complete,
    wait_for_frame,
    wait_for_new_page,
    wait_for_popup_close,
    wait_for_iframe_content,
    HumanBehaviorProfile,
    smart_wait_after_load,
    cleanup_extra_pages
)
```

### Estrutura de Classes

```python
class EnvioBoletoOperacaoOculto:
    """
    Processador de envio de boletos (operação oculto).

    Attributes:
        logger_exec: Logger de execução
        screenshot_manager: Gerenciador de screenshots
        checkpoint_manager: Gerenciador de checkpoints
        browser: Instância do browser Playwright
        page: Página principal do Playwright
        mensagem_boletos: Template de mensagem carregado
    """
```

---

## 🔄 Fluxo de Execução

### 1. Inicialização

```
1. Carrega configurações
2. Inicializa ExecutionLogger
3. Inicializa ScreenshotManager
4. Inicializa CheckpointManager
5. Carrega template de mensagem (mensagem_boletos.txt)
6. Conecta ao banco de dados
7. Consulta operações do dia anterior
8. Agrupa operações por credenciais
```

### 2. Processamento por Grupo

```
Para cada grupo de credenciais:
├── Inicializa browser (Playwright)
├── Faz login com credenciais do grupo
├── Para cada operação do grupo:
│   ├── Navega para página de emissão
│   ├── Seleciona conta bancária
│   ├── Preenche nop1 e nop2
│   ├── Gera boleto
│   ├── Marca "Selecionar Todos Email"
│   ├── Envia por e-mail
│   ├── Preenche mensagem personalizada
│   ├── Envia
│   └── Aguarda 5s (se não for última)
├── Fecha browser
└── Aguarda 10s (ou 30s se erro de proxy)
```

### 3. Finalização

```
1. Salva operações falhadas (se houver)
   └── Arquivo: data/checkpoints/envio_boleto_operacao_oculto_failed_{timestamp}.json
2. Exibe resumo da execução
3. Fecha conexão com banco de dados
4. Finaliza logs
```

---

## ⚙️ Configuração

### Arquivo: `config/processors.yaml`

```yaml
envio_boleto_operacao_oculto:
  enabled: true
  mode: one-shot
  schedule: "0 8 * * *"  # Todo dia às 8h
  screenshot_level: milestones
  captcha:
    provider: capsolver
    api_key: ${CAPSOLVER_API_KEY}
  retry:
    max_attempts: 2
    delay: 10
  checkpoint:
    enabled: true
    dir: data/checkpoints
```

### Variáveis de Ambiente

```bash
# Banco de dados
DB_HOST=localhost
DB_PORT=5432
DB_NAME=prosper_erp
DB_USER=postgres
DB_PASSWORD=senha

# CAPTCHA
CAPSOLVER_API_KEY=CAP-xxxxxxxxxxxxx

# Display VNC
DISPLAY=:2

# Debug (mantém browser aberto)
DEBUG_MODE=false
```

### Template de Mensagem

**Arquivo**: `data/assets/email/templates/mensagem_boletos.txt`

```
Prezado(a) %NOME_SACADO%,

Segue em anexo o(s) boleto(s) bancário(s) referente(s) à(s) operação(ões) realizada(s) com %NOME_CEDENTE%.

%RELACAO_TITULOS%

Atenciosamente,
PROSPER Factoring
```

**Placeholders**:
- `%NOME_SACADO%`: Nome do sacado (preenchido automaticamente pelo sistema)
- `%NOME_CEDENTE%`: Nome do cedente (preenchido automaticamente)
- `%RELACAO_TITULOS%`: Relação de títulos (preenchida automaticamente)

---

## 🚀 Como Executar

### Modo Produção (One-Shot)

```bash
DISPLAY=:2 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto.py
```

### Modo Debug (Browser Permanece Aberto)

```bash
DISPLAY=:2 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto.py
```

### Via Cron (Agendamento)

```bash
# Editar crontab
crontab -e

# Adicionar linha (todo dia às 8h)
0 8 * * * cd /home/ubuntu/PROSPER-ERP-AUTOMATION && \
  DISPLAY=:2 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto.py >> logs/cron_envio_boleto_oculto.log 2>&1
```

---

## 📊 Logs e Monitoramento

### Arquivo de Log

**Local**: `logs/envio_boleto_operacao_oculto_YYYYMMDD_HHMMSS.log`

### Estrutura de Log

```
[2025-11-17 08:00:00] [INFO] [GENERAL] [0.00s] ================================================================================
[2025-11-17 08:00:00] [INFO] [GENERAL] [0.00s] 🚀 INICIANDO PROCESSADOR: Envio Boleto Operação Oculto
[2025-11-17 08:00:01] [INFO] [GENERAL] [1.23s] 📊 Total de operações encontradas: 15
[2025-11-17 08:00:01] [INFO] [GENERAL] [1.23s] 👥 Grupos de credenciais: 3
[2025-11-17 08:00:02] [INFO] [GENERAL] [2.34s] ✅ Browser inicializado
[2025-11-17 08:00:05] [INFO] [GENERAL] [5.67s] ✅ Login realizado com sucesso
[2025-11-17 08:00:10] [INFO] [GENERAL] [10.12s] 📧 Operação 12345 processada com sucesso
[2025-11-17 08:00:15] [INFO] [GENERAL] [15.45s] 📧 Operação 12346 processada com sucesso
...
[2025-11-17 08:05:00] [INFO] [GENERAL] [300.00s] ================================================================================
[2025-11-17 08:05:00] [INFO] [GENERAL] [300.00s] 📊 RESUMO DA EXECUÇÃO
[2025-11-17 08:05:00] [INFO] [GENERAL] [300.00s] ✅ Sucessos: 13
[2025-11-17 08:05:00] [INFO] [GENERAL] [300.00s] ❌ Erros: 2
[2025-11-17 08:05:00] [INFO] [GENERAL] [300.00s] 📝 Arquivo de retry: data/checkpoints/envio_boleto_operacao_oculto_failed_20251117_080500.json
```

### Screenshots

**Local**: `data/screenshots/envio_boleto_operacao_oculto_YYYYMMDD_HHMMSS/`

**Níveis** (configurável em `screenshot_level`):
- `none`: Sem screenshots
- `errors-only`: Apenas em erros
- `milestones`: Pontos-chave (padrão)
- `full`: Todos os screenshots

**Capturas de Milestones**:
```
01_login_page.png
02_after_login.png
03_emissao_page_op001.png
04_iframe_titulos_op001.png
05_email_sent_op001.png
...
ERROR_operacao_012.png  # Se houver erro
```

---

## 🛡️ Tratamento de Erros

### 1. Erro em Operação Individual

**Comportamento**:
- Tenta **até 2 vezes** (1 inicial + 1 retry)
- Aguarda **10 segundos** entre tentativas
- Se falhar após todas tentativas:
  - Captura screenshot de erro
  - Adiciona à lista de retry (`operacoes_falhadas`)
  - **Continua** processando próxima operação
  - **NÃO fecha** o browser
  - **NÃO interrompe** o grupo

**Log**:
```
[2025-11-17 08:00:15] [ERROR] [GENERAL] [15.45s] ❌ Erro ao processar operação 12347: Timeout ao aguardar iframe
[2025-11-17 08:00:15] [INFO] [GENERAL] [15.45s] 🔄 Tentando novamente (tentativa 2/2)...
[2025-11-17 08:00:25] [ERROR] [GENERAL] [25.67s] ❌ Erro após 2 tentativas. Pulando operação 12347.
[2025-11-17 08:00:25] [INFO] [GENERAL] [25.67s] 📸 Screenshot de erro capturado: ERROR_operacao_003.png
```

### 2. Erro em Grupo Inteiro

**Causas**:
- Erro de login
- Erro de proxy
- Erro de navegação

**Comportamento**:
- **Todas** as operações do grupo são marcadas como falhadas
- Fecha o browser
- Aguarda intervalo maior:
  - **30 segundos** (se erro de proxy)
  - **10 segundos** (outros erros)
- **Continua** com próximo grupo

**Log**:
```
[2025-11-17 08:00:30] [ERROR] [GENERAL] [30.12s] ❌ Erro ao processar grupo 'user@email.com': ERR_HTTP_RESPONSE_CODE_FAILURE
[2025-11-17 08:00:30] [WARNING] [GENERAL] [30.12s] ⚠️ Possível erro de proxy. Aguardando 30s antes de continuar...
[2025-11-17 08:00:30] [INFO] [GENERAL] [30.12s] 📝 5 operações do grupo adicionadas à lista de retry
```

### 3. Erro de HTTP 429 (Rate Limiting)

**Tratamento Automático** via `RateLimitHandler`:
- Detecta HTTP 429 automaticamente
- Aguarda tempo do header `Retry-After`
- Backoff exponencial com jitter
- Navega de volta para página de emissão
- **NÃO requer** retry manual

---

## 🔄 Sistema de Retry

### Arquivo de Checkpoint

**Local**: `data/checkpoints/envio_boleto_operacao_oculto_failed_{timestamp}.json`

**Estrutura**:
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

### Processador de Retry

**Arquivo**: `src/processors/web/envio_boleto_operacao_oculto_retry.py`

**Como usar**:
```bash
# Executar retry das operações falhadas
DISPLAY=:2 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto_retry.py
```

**Comportamento**:
- Lê arquivo de checkpoint mais recente
- Processa apenas operações falhadas
- Tenta novamente (max 2 tentativas)
- Gera novo checkpoint se houver falhas

---

## 🔧 Troubleshooting

### Problema: Operações não encontradas

**Verificar**:
```sql
SELECT COUNT(*)
FROM api.erp_operacoes_ocultas_dia_anterior
WHERE data_operacao = CURRENT_DATE - INTERVAL '1 day';
```

**Solução**: Verificar se há operações ocultas no dia anterior.

---

### Problema: Erro de login

**Sintomas**:
```
❌ Erro ao processar grupo 'user@email.com': Timeout ao aguardar dashboard
```

**Verificar**:
1. Credenciais corretas no banco de dados
2. CAPTCHA resolvido corretamente
3. CapSolver com saldo suficiente

**Solução**:
```bash
# Verificar saldo CapSolver
curl -X POST https://api.capsolver.com/getBalance \
  -H "Content-Type: application/json" \
  -d '{"clientKey":"CAP-xxxxxxxxxxxxx"}'
```

---

### Problema: Timeout ao aguardar iframe

**Sintomas**:
```
❌ Erro ao processar operação 12347: Timeout ao aguardar iframe de títulos
```

**Causas**:
- Conta bancária sem títulos
- Página não carregou completamente
- nop1/nop2 incorretos

**Solução**:
1. Executar em modo DEBUG para visualizar:
```bash
DISPLAY=:2 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/envio_boleto_operacao_oculto.py
```

2. Acessar VNC: `http://SEU_IP:6082/vnc.html`

3. Verificar manualmente no SmartSecurities

---

### Problema: Erro de proxy

**Sintomas**:
```
❌ Erro ao processar grupo: ERR_HTTP_RESPONSE_CODE_FAILURE
⚠️ Possível erro de proxy
```

**Verificar**:
1. Conectividade com proxy BrightData
2. Credenciais do proxy corretas
3. Saldo disponível

**Solução**:
```bash
# Verificar conectividade
curl -x "http://USERNAME:PASSWORD@brd.superproxy.io:33335" \
  https://lumtest.com/myip.json
```

---

### Problema: Template de mensagem não encontrado

**Sintomas**:
```
❌ Erro ao carregar mensagem_boletos.txt
```

**Verificar**:
```bash
ls -la data/assets/email/templates/mensagem_boletos.txt
```

**Solução**:
```bash
# Criar arquivo se não existir
mkdir -p data/assets/email/templates/
cat > data/assets/email/templates/mensagem_boletos.txt << 'EOF'
Prezado(a) %NOME_SACADO%,

Segue em anexo o(s) boleto(s) bancário(s) referente(s) à(s) operação(ões) realizada(s) com %NOME_CEDENTE%.

%RELACAO_TITULOS%

Atenciosamente,
PROSPER Factoring
EOF
```

---

### Problema: Alta taxa de erros

**Sintomas**:
```
📊 RESUMO: Sucessos: 5 | Erros: 10
```

**Causas**:
- Proxy instável
- CAPTCHA não resolvendo
- Timeout muito curto
- Rate limiting

**Diagnóstico**:
```bash
# Ver logs detalhados
tail -200 logs/envio_boleto_operacao_oculto_*.log | grep -E "ERROR|WARNING"

# Ver screenshots de erro
ls -lt data/screenshots/envio_boleto_operacao_oculto_*/ERROR_*.png | head -10
```

**Solução**:
1. Verificar proxy (reconectar se necessário)
2. Verificar saldo CapSolver
3. Aumentar timeouts em `wait_utils`
4. Reduzir número de operações por grupo

---

## 📈 Estatísticas e Performance

### Tempo Médio

- **Login**: ~10 segundos
- **Processamento por operação**: ~15 segundos
- **Total (15 operações, 3 grupos)**: ~5 minutos

### Taxa de Sucesso Esperada

- **Com proxy BrightData**: ≥ 90%
- **Sem proxy**: 70-80%

### Recursos

- **Memória**: ~200-300 MB por browser
- **CPU**: 10-20% (processamento sequencial)
- **Disco**: ~50 MB de screenshots por execução

---

## 🔗 Arquivos Relacionados

- **Processador**: `src/processors/web/envio_boleto_operacao_oculto.py`
- **Retry**: `src/processors/web/envio_boleto_operacao_oculto_retry.py`
- **Template**: `data/assets/email/templates/mensagem_boletos.txt`
- **Checkpoints**: `data/checkpoints/envio_boleto_operacao_oculto_failed_*.json`
- **Logs**: `logs/envio_boleto_operacao_oculto_*.log`
- **Screenshots**: `data/screenshots/envio_boleto_operacao_oculto_*/`

---

**Última atualização**: 2025-11-18 | **Versão**: 1.0
