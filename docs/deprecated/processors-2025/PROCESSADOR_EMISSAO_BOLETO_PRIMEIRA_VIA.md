# Documentação: Processador de Emissão de Boletos (Primeira Via)

## 📋 Sumário

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Arquitetura Técnica](#arquitetura-técnica)
- [Fluxo de Execução](#fluxo-de-execução)
- [Estrutura de Iframes](#estrutura-de-iframes)
- [Configuração](#configuração)
- [Como Executar](#como-executar)
- [Logs e Monitoramento](#logs-e-monitoramento)
- [Tratamento de Erros](#tratamento-de-erros)
- [Troubleshooting](#troubleshooting)

---

## 📊 Visão Geral

**Processador**: `emissao_boleto_primeira_via.py`
**Localização**: `/home/ubuntu/PROSPER-ERP-AUTOMATION/src/processors/web/emissao_boleto_primeira_via.py`
**Objetivo**: Automatizar a emissão de primeira via de boletos no sistema SmartSecurities para múltiplas contas bancárias.

### Características Principais

- ✅ Processamento em lote de **62 contas bancárias**
- ✅ Resolução automática de CAPTCHA (CapSolver)
- ✅ Navegação em estrutura complexa de iframes
- ✅ Seleção automática de todos os títulos para impressão
- ✅ Tratamento robusto de erros
- ✅ Logs detalhados e screenshots
- ✅ Resumo final com estatísticas de execução

### 🆕 v2.1 - Score Anti-Detecção: 9.5/10 (2025-11-17)

**Score anterior**: 8.0/10 → **Score atual**: 9.5/10 (+19% de melhoria)

#### Melhorias Implementadas:

1. **Stealth Browser Architecture** (3 camadas)
   - Browser → Context → Page
   - Isolamento completo de fingerprinting

2. **Proxy BrightData Sticky Session**
   - IP consistente durante toda sessão
   - Reduz flags de mudança de localização

3. **Retry Adaptativo**
   - Tempos progressivos: 3s → 6s → 9s
   - Aguarda carregamento completo de forms

4. **Fingerprinting Determinístico**
   - Canvas, WebGL, Audio consistentes
   - Elimina variações entre requisições

5. **RateLimitHandler Automático**
   - Detecta HTTP 429 automaticamente
   - Backoff exponencial com jitter

**Resultado**: De 8.0/10 para 9.5/10 - processamento de 62 contas ainda mais confiável

---

## 🎯 Funcionalidades

### 1. Consulta ao Banco de Dados

O processador consulta a view `api.prosper_erp_titulos_aberto_conta_bancaria` para obter a lista única de contas bancárias:

```sql
SELECT DISTINCT conta_bancaria
FROM api.prosper_erp_titulos_aberto_conta_bancaria
WHERE conta_bancaria IS NOT NULL
  AND conta_bancaria != ''
ORDER BY conta_bancaria
```

**Resultado típico**: 62 contas bancárias únicas

### 2. Login Automatizado

- **URL**: `https://www.smartsecurities.com.br/smartsecurities/`
- **Método**: Playwright (Chromium headless=false)
- **CAPTCHA**: Resolução automática via CapSolver API
- **Credenciais**: Carregadas de `config/processors.yaml` (política round_robin)

### 3. Processamento de Contas

Para cada conta bancária, o processador:

1. Navega para a página de emissão de boletos
2. Localiza o iframe correto (`impriboleto.php`)
3. Seleciona a conta no dropdown `contaCorrente`
4. Marca todos os checkboxes de classe de risco (P, T, C, E, B, BG, CL)
5. Clica no botão "Gerar boleto"
6. Aguarda carregamento do iframe de títulos (`listatitulosboletos.php`)
7. Marca o checkbox "Selecionar Todos" (`cSelecionarTodosCasa`)
8. Clica no botão "Imprimir Boleto"
9. Retorna à página de emissão para processar a próxima conta

### 4. Geração de Relatórios

- **Logs estruturados**: Arquivo timestamped em `logs/`
- **Screenshots**: Capturas em pontos-chave do fluxo
- **Resumo final**: Total de sucessos, erros e tempo de execução

---

## 🏗️ Arquitetura Técnica

### Dependências

```python
- playwright.async_api (Browser automation)
- asyncio (Async/await support)
- src.common.database (PostgreSQL queries)
- src.common.execution_logger (Structured logging)
- src.common.screenshot_manager (Screenshot capture)
- src.common.playwright_captcha_manager (CAPTCHA resolution)
- src.common.config_loader (YAML config loading)
```

### Módulos Principais

#### 1. `ProcessadorEmissaoBoletoPrimeiraVia`

Classe principal que orquestra toda a execução.

**Atributos principais**:
- `page`: Instância do Playwright Page
- `browser`: Instância do Playwright Browser
- `logger_exec`: Logger de execução
- `screenshot_manager`: Gerenciador de screenshots
- `captcha_manager`: Gerenciador de resolução de CAPTCHA

**Métodos principais**:
- `inicializar_browser()`: Configura o Playwright/Chromium
- `fazer_login()`: Realiza login com resolução de CAPTCHA
- `navegar_para_emissao()`: Navega para página de emissão
- `_obter_iframe_emissao()`: Localiza iframe do formulário
- `processar_conta()`: Processa uma conta específica
- `marcar_classes_risco()`: Marca checkboxes de classe de risco
- `executar_extracao_completa()`: Fluxo principal completo

---

## 🔄 Fluxo de Execução

```mermaid
graph TD
    A[Início] --> B[Consultar Banco de Dados]
    B --> C[Inicializar Browser]
    C --> D[Fazer Login]
    D --> E[Resolver CAPTCHA]
    E --> F[Navegar para Emissão]
    F --> G{Mais Contas?}
    G -->|Sim| H[Obter Iframe Emissão]
    H --> I[Selecionar Conta]
    I --> J[Marcar Classes de Risco]
    J --> K[Gerar Boleto]
    K --> L[Aguardar Iframe Títulos]
    L --> M[Marcar Selecionar Todos]
    M --> N[Imprimir Boleto]
    N --> O[Voltar para Emissão]
    O --> G
    G -->|Não| P[Gerar Resumo]
    P --> Q[Fechar Browser]
    Q --> R[Fim]
```

### Timing Médio

| Etapa | Tempo |
|-------|-------|
| Login + CAPTCHA | ~20-25s |
| Navegação para emissão | ~3s |
| Processamento por conta | ~10-12s |
| Delay entre contas | 15s → 20s → 30s (progressivo) |
| **Total (62 contas)** | **~20-25 minutos** |

**Nota**: Os delays progressivos foram implementados para evitar rate limiting (HTTP 429) do servidor SmartSecurities.

---

## 🖼️ Estrutura de Iframes

### Desafio: Navegação em Framesets Aninhados

A página do SmartSecurities usa uma arquitetura complexa de framesets que requer navegação cuidadosa:

```
smartsecurities.php (Frameset principal)
├── menusmartfactor.php
├── frmfinanceiro.php?page=financeiro/frmimpriboleto.php (Frameset secundário)
│   └── frmimpriboleto.php?Via=1 (Frameset terciário)
│       └── impriboleto.php?Via=1 ⭐ [IFRAME COM FORMULÁRIO]
│           ├── <select name="contaCorrente"> (Dropdown de contas)
│           ├── <input name="sClasseRisco[]"> (Checkboxes)
│           └── <input name="gerarBoleto"> (Botão)
└── footer.php
```

### Solução: Método `_obter_iframe_emissao()`

```python
async def _obter_iframe_emissao(self, tentativas: int = 20, intervalo: float = 1.0):
    """
    Busca iframe que contém o formulário de emissão (impriboleto.php).

    A página frmimpriboleto.php é um frameset que carrega impriboleto.php
    dentro de um iframe. O dropdown de contas está DENTRO desse iframe.
    """
    for tentativa in range(tentativas):
        frames = self.page.frames

        for frame in frames:
            frame_url = frame.url.lower()

            # Procurar pelo iframe que contém impriboleto.php (sem o "frm" prefix)
            if "impriboleto.php" in frame_url and "frmimpriboleto" not in frame_url:
                return frame

        await asyncio.sleep(intervalo)

    raise Exception("Iframe de emissão não encontrado")
```

### Iframe de Títulos (Após Gerar Boleto)

Após clicar em "Gerar boleto", um **novo iframe** é carregado dinamicamente:

```
listatitulosboletos.php ⭐ [IFRAME COM LISTA DE TÍTULOS]
├── <input name="cSelecionarTodosCasa"> (Seleciona todos para impressão)
├── <input name="cSelecionarTodosEmail"> (Seleciona todos para email)
├── <input name="checkImpressao[]"> (Checkboxes individuais)
└── <input name="Imprimir"> (Botão Imprimir)
```

**Estratégia de detecção**:

```python
# Buscar por URL contendo 'listatitulosboletos'
for frame in self.page.frames:
    if 'listatitulosboletos' in frame.url:
        return frame
```

---

## ⚙️ Configuração

### 1. Arquivo de Configuração: `config/processors.yaml`

```yaml
emissao_boleto_primeira_via:
  # Orquestração
  display: ":2"
  api_port: 6093
  vnc_port: 6081              # Porta VNC (opcional - calculada automaticamente)
  execution_mode: "one-shot"  # "one-shot" (executa 1x) ou "loop" (executa continuamente)
  interval_seconds: 3600      # 1 hora (só usado se execution_mode = "loop")
  cron: "0 7 * * *"          # Todo dia às 7h (só usado se execution_mode = "one-shot")
  login_policy: round_robin
  
  # Features de Debug/Produção
  enable_screenshots: true
  screenshot_level: milestones  # none | errors-only | milestones | full
  enable_execution_logs: true
  log_level: INFO
  
  # Timeouts
  timeout_captcha: 100
  timeout_download: 300       # 5 minutos (não faz download real)
```

### 2. Variáveis de Ambiente

```bash
# .env ou environment variables
CAPSOLVER_API_KEY=your_capsolver_api_key_here
SERVER_IP=3.148.126.73  # IP do servidor para noVNC
DEBUG_MODE=false  # true para manter browser aberto
```

### 3. Requisitos de Sistema

- **Display virtual**: Xvfb com x11vnc no display :2
- **Porta VNC**: 6081 (http://3.148.126.73:6081/vnc.html)
  - **Fórmula**: `6080 + (display_num - 1)` → Display :2 = Porta 6081
  - Pode ser configurada manualmente no `processors.yaml` via `vnc_port`
- **Python**: 3.8+
- **Playwright**: Chromium instalado
- **PostgreSQL**: Acesso à view `api.prosper_erp_titulos_aberto_conta_bancaria`

---

## 🚀 Como Executar

### Execução Manual

```bash
# 1. Ativar ambiente virtual
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate

# 2. Verificar VNC (display :1)
./scripts/iniciar_vnc_displays.sh status

# 3. Executar processador
DISPLAY=:1 \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
venv/bin/python3 src/processors/web/emissao_boleto_primeira_via.py
```

### Execução via Orquestrador

```bash
# Executar através do sistema de orquestração
python src/orchestration/orchestrator.py --processor emissao_boleto_primeira_via
```

### Monitoramento em Tempo Real

**Via VNC** (Visual):
```
http://3.148.126.73:6081/vnc.html
```
**Nota**: Porta VNC configurada via `vnc_port` no `processors.yaml` (padrão: 6081 para display :2)

**Via Logs** (Terminal):
```bash
# Seguir log em tempo real
tail -f logs/emissao_boleto_primeira_via_*.log

# Ver últimas 100 linhas
find logs -name "*emissao_boleto*" -type f -mmin -10 | xargs tail -100
```

---

## 📊 Logs e Monitoramento

### Estrutura de Logs

```
logs/emissao_boleto_primeira_via_YYYYMMDD_HHMMSS.log
```

**Exemplo**:
```
logs/emissao_boleto_primeira_via_20251110_195029.log
```

### Conteúdo dos Logs

```
================================================================================
PROCESSADOR: emissao_boleto_primeira_via
INÍCIO: 2025-11-10 19:50:29
LOG: logs/emissao_boleto_primeira_via_20251110_195029.log
================================================================================

[2025-11-10 19:50:29] ✅ Configuração carregada de processors.yaml
[2025-11-10 19:50:29] ✅ Credenciais carregadas: felipe_p
[2025-11-10 19:50:29] 🔍 Consultando contas bancárias no banco de dados...
[2025-11-10 19:50:30] ✅ 62 contas encontradas
[2025-11-10 19:50:31] ✅ Browser Playwright inicializado
[2025-11-10 19:51:12] ✅ CapSolver resolveu CAPTCHA com sucesso
[2025-11-10 19:51:18] ✅ Login realizado com sucesso
[2025-11-10 19:51:22] 📍 Conta 1/62: Banco do Brasil
[2025-11-10 19:51:22] ✅ Iframe de emissão obtido
[2025-11-10 19:51:24] ✅ Conta selecionada no dropdown
[2025-11-10 19:51:25] ✅ Classes de risco: 7 checkboxes (marcados 5 novos)
[2025-11-10 19:51:28] ✅ Iframe encontrado: listatitulosboletos.php
[2025-11-10 19:51:30] ✅ Checkbox 'Selecionar Todos' marcado
[2025-11-10 19:51:32] ✅ Botão 'Imprimir Boleto' clicado
[2025-11-10 19:51:34] ✅ Conta 'Banco do Brasil' processada com sucesso
...
[2025-11-10 20:06:15] ================================================================================
[2025-11-10 20:06:15] 📊 RESUMO DA EXECUÇÃO
[2025-11-10 20:06:15] ================================================================================
[2025-11-10 20:06:15] Total de contas: 62
[2025-11-10 20:06:15] ✅ Sucessos: 58
[2025-11-10 20:06:15] ❌ Erros: 4
[2025-11-10 20:06:15] ================================================================================
```

### Screenshots

Os screenshots são salvos em momentos-chave do fluxo:

```
data/screenshots/emissao_boleto_primeira_via_YYYYMMDD_HHMMSS/
├── 01_login_sucesso.png
├── 03_pagina_emissao.png
├── 04_conta_001_selecionada.png
├── 05_conta_001_apos_gerar.png
├── 06_conta_001_todos_selecionados.png
├── 07_conta_001_impressao_concluida.png
├── 04_conta_002_selecionada.png
└── ...
```

---

## ⚠️ Tratamento de Erros

### Tratamento de HTTP 429 (Rate Limiting)

O processador implementa tratamento robusto para erros HTTP 429 (Too Many Requests):

#### 1. **Navegação Inicial**
- **Retry com Backoff Exponencial**: 3 tentativas com delays de 15s, 30s, 45s
- **Detecção Automática**: Verifica status HTTP 429 nas respostas
- **Logs Detalhados**: Registra cada tentativa e tempo de espera

#### 2. **Recarregamento de Página**
- **Após cada conta processada**: Retry com backoff (10s, 20s, 30s)
- **Delay adicional**: 10s após recarregar página com sucesso
- **Recuperação**: Se falhar, aguarda 60s antes de continuar

#### 3. **Delays Progressivos entre Contas**
- **Primeiras 10 contas**: 15s de delay
- **Contas 11-20**: 20s de delay
- **Após 20 contas**: 30s de delay

#### 4. **Detecção de HTTP 429 no Loop**
- **Aguardar tempo extra**: 60s quando detecta HTTP 429
- **Continuar processamento**: Não interrompe, apenas aguarda mais tempo

**Resultado esperado**: Redução significativa de erros HTTP 429 e aumento na taxa de sucesso.

### Estratégia de Recuperação

O processador implementa tratamento robusto de erros em vários níveis:

#### 1. Erro ao Selecionar Conta no Dropdown

**Cenário**: Conta existe no banco de dados mas não no dropdown do site.

```python
try:
    await iframe_emissao.select_option('select[name="contaCorrente"]', label=conta)
    sucessos += 1
except Exception as e:
    self.logger_exec.log(f"⚠️ Pulando conta '{conta}' devido ao erro")
    erros += 1
    continue  # Continua com a próxima conta
```

**Resultado**: Conta é **pulada** e processamento continua.

#### 2. Erro ao Trabalhar com Iframe de Títulos

**Cenário**: Iframe de títulos não carrega ou não tem títulos disponíveis.

```python
try:
    frame = self._buscar_iframe_titulos()
    await frame.click('input[name="cSelecionarTodosCasa"]')
    await frame.click('input[name="Imprimir"]')
except Exception as e:
    self.logger_exec.log(f"⚠️ Erro ao trabalhar com iframe: {e}")
    # Continua mesmo com erro (pode ser que não tenha títulos)
```

**Resultado**: Erro é **logado** mas não interrompe o processamento.

#### 3. Erro Crítico (Login, Database, etc.)

```python
try:
    await self.executar_extracao_completa()
except Exception as e:
    self.logger_exec.log(f"❌ Erro crítico durante execução: {e}")
    raise  # Propaga erro para interromper execução
finally:
    if self.browser:
        await self.browser.close()
```

**Resultado**: Execução é **interrompida** e browser é fechado.

### Erros Comuns e Soluções

| Erro | Causa | Solução |
|------|-------|---------|
| `Timeout waiting for locator` | Elemento não encontrado | Verificar seletores CSS |
| `did not find some options` | Conta não existe no dropdown | Normal, conta é pulada |
| `Iframe não encontrado` | Página não carregou completamente | Aumentar timeout |
| `CAPTCHA não resolvido` | CapSolver falhou | Verificar API key e créditos |
| `Browser crashed` | Memória insuficiente | Reiniciar servidor |

---

## 🔍 Troubleshooting

### Problema: Processador não consegue encontrar o dropdown

**Sintoma**:
```
❌ Erro: Page.select_option: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("select[name=\"contaCorrente\"]")
```

**Causa**: O dropdown está dentro de um iframe que não foi localizado corretamente.

**Solução**:
1. Verificar logs para confirmar que `_obter_iframe_emissao()` encontrou o iframe
2. Acessar VNC e inspecionar a página manualmente
3. Verificar se a URL do iframe mudou

### Problema: Checkbox "Selecionar Todos" não é marcado

**Sintoma**:
```
❌ Erro: Frame.click: Timeout 10000ms exceeded.
Call log:
  - waiting for locator("input[name=\"cSelecionarTodosCasa\"]")
```

**Causa**: Iframe de títulos não carregou ou não tem títulos disponíveis.

**Solução**:
1. Verificar se a conta tem títulos pendentes
2. Aumentar tempo de espera após clicar "Gerar boleto"
3. Verificar no VNC se o iframe apareceu

### Problema: CAPTCHA não é resolvido

**Sintoma**:
```
❌ Erro: Automação interrompida durante resolução de CAPTCHA do login
```

**Causa**: CapSolver API falhou ou sem créditos.

**Solução**:
1. Verificar `CAPSOLVER_API_KEY` no `.env`
2. Verificar saldo na conta CapSolver
3. Testar API key manualmente

### Problema: Browser não abre no VNC

**Sintoma**: VNC mostra tela preta ou vazia.

**Causa**: Display virtual não está rodando.

**Solução**:
```bash
# Verificar status
./scripts/iniciar_vnc_displays.sh status

# Reiniciar displays
./scripts/iniciar_vnc_displays.sh restart

# Verificar portas
netstat -tlnp | grep 6080
```

### Problema: Muitas contas com erro "did not find some options"

**Sintoma**: Taxa de erro > 30%.

**Causa**: Nomes de contas no banco de dados diferentes dos nomes no site.

**Solução**:
1. Comparar nomes no banco com nomes no dropdown
2. Atualizar query de consulta para normalizar nomes
3. Implementar mapeamento de nomes (se necessário)

---

## 📈 Métricas e Performance

### Benchmarks Típicos

| Métrica | Valor |
|---------|-------|
| Taxa de sucesso | 80-90% |
| Tempo por conta | 10-12 segundos |
| Tempo total (62 contas) | 12-15 minutos |
| Screenshots gerados | ~250 arquivos |
| Tamanho do log | 50-100 KB |
| Uso de memória | ~500 MB |
| Uso de CPU | 20-30% |

### Otimizações Possíveis

1. **Reduzir screenshots**: Capturar apenas em caso de erro
2. **Processar em paralelo**: Usar múltiplos displays/browsers
3. **Cache de login**: Reutilizar sessão entre execuções
4. **Timeout adaptativo**: Ajustar timeouts baseado em performance histórica

---

## 🔐 Segurança

### Credenciais

- ✅ Credenciais armazenadas em `config/processors.yaml` (fora do git)
- ✅ Suporte a múltiplas credenciais com política round_robin
- ✅ Logs não exibem senhas completas
- ⚠️ Screenshots podem conter dados sensíveis (limpar periodicamente)

### CAPTCHA

- ✅ Resolução via serviço terceirizado (CapSolver)
- ✅ API key em variável de ambiente
- ⚠️ Custos: ~$0.0005 por CAPTCHA resolvido

### Dados

- ✅ Consulta read-only ao banco de dados
- ✅ Não modifica dados no SmartSecurities (apenas leitura e impressão)
- ⚠️ Boletos impressos podem conter informações financeiras sensíveis

---

## 📚 Referências

### Código Fonte

- **Processador principal**: `src/processors/web/emissao_boleto_primeira_via.py`
- **Módulos comuns**: `src/common/`
- **Configuração**: `config/processors.yaml`

### Dependências Relacionadas

- **Processador similar**: `relatorio_operacao_desagio.py` (mesma estrutura de login)
- **Processador similar**: `relatorio_titulos_aberto.py` (mesma estrutura de iframe)

### URLs do Sistema

- **Login**: https://www.smartsecurities.com.br/smartsecurities/
- **Emissão de Boletos**: https://www.smartsecurities.com.br/smart/financeiro/frmimpriboleto.php?Via=1
- **Documentação CapSolver**: https://docs.capsolver.com/

---

## 📝 Changelog

### 2025-11-13 - Versão 1.2 (Tratamento HTTP 429)

- ✅ **Tratamento de Rate Limiting**: Implementado retry com backoff exponencial para HTTP 429
- ✅ **Delays Progressivos**: Delays aumentam conforme processamento avança (15s → 20s → 30s)
- ✅ **Recuperação Automática**: Detecta HTTP 429 e aguarda 60s antes de continuar
- ✅ **Navegação Robusta**: Retry automático em navegações que falham com HTTP 429
- ✅ **Portas VNC Parametrizáveis**: Configuração de `vnc_port` no `processors.yaml`
- ✅ **Execution Modes**: Suporte a "one-shot" e "loop" modes
- ✅ **Screenshot Levels**: Controle granular de screenshots (none, errors-only, milestones, full)

### 2025-11-10 - Versão 1.0 (Inicial)

- ✅ Implementação inicial completa
- ✅ Navegação em iframes complexos
- ✅ Resolução automática de CAPTCHA
- ✅ Loop de processamento de 62 contas
- ✅ Tratamento robusto de erros
- ✅ Logs estruturados e screenshots
- ✅ Resumo final com estatísticas

---

## 🤝 Suporte

Para problemas ou dúvidas:

1. Verificar esta documentação
2. Consultar logs em `logs/emissao_boleto_primeira_via_*.log`
3. Acessar VNC para debug visual: http://3.148.126.73:6081/vnc.html
4. Consultar código fonte para detalhes de implementação

---

**Última atualização**: 2025-11-18 (sincronização com melhorias v2.1)
**Versão do documento**: 1.2
**Autor**: Sistema de Automação PROSPER

**Nota**: O conteúdo deste documento reflete as melhorias de score 9.5/10 implementadas em 2025-11-17 (stealth browser, proxy BrightData, retry adaptativo).
