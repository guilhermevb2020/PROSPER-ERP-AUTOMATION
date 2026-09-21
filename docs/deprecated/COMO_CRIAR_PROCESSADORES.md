# 🏗️ GUIA COMPLETO: COMO CRIAR NOVOS PROCESSADORES

**Última atualização:** 2025-11-15
**Versão:** 3.0 (Atualizado com novos módulos anti-detecção)

---

## 📋 **ÍNDICE**

1. [Visão Geral](#visão-geral)
2. [Módulos Disponíveis](#módulos-disponíveis)
3. [Anatomia de um Processador](#anatomia-de-um-processador)
4. [Passo a Passo para Criar](#passo-a-passo)
5. [Sistema de Configuração](#sistema-de-configuração)
6. [Boas Práticas](#boas-práticas)
7. [Troubleshooting](#troubleshooting)
8. [Checklist de Validação](#checklist)

---

## 🎯 **VISÃO GERAL**

### **O que é um Processador?**

Um processador é um script Python assíncrono (asyncio + Playwright) que:
- Faz login em um site (ex: SmartSecurities)
- Navega até uma página específica
- Extrai dados (relatórios, arquivos CSV, etc)
- Salva os dados em `data/raw_inputs/`
- Registra logs detalhados de execução

### **Arquitetura Atualizada (2025)**

```
processador.py
├── Configuração (config/processors.yaml + credentials.csv)
├── Inicialização do Browser (Playwright + Anti-Detecção Score 9.0)
│   ├── Stealth Browser (args anti-bot)
│   ├── Stealth Context (fingerprinting determinístico)
│   ├── Stealth Page (todos os fingerprints injetados)
│   └── Bright Data Proxy (opcional, com bypass Google)
├── Login Automatizado (com CAPTCHA resolver + RateLimitHandler)
├── Navegação Inteligente (wait_utils para páginas lentas)
├── Extração de Dados
├── Download e Renomeação de Arquivos
└── Finalização e Logs
```

### **Score Anti-Detecção**

Nossos processadores atuais atingem **score 9.0/10** em anti-detecção:

- ✅ **Navigator overrides** (webdriver, plugins, languages)
- ✅ **Canvas fingerprint** determinístico
- ✅ **WebGL fingerprint** determinístico
- ✅ **Audio fingerprint** determinístico
- ✅ **WebRTC blocker** (sem vazamento de IP real)
- ✅ **Chrome Runtime** (masks CDP)
- ✅ **Playwright-Stealth** (masks automation signals)
- ✅ **Hardware profiles** consistentes
- ✅ **Bright Data proxy** (IP rotativo ou sticky)
- ✅ **Rate limit handling** automático (HTTP 429)

---

## 🧩 **MÓDULOS DISPONÍVEIS**

### **📦 Módulos Essenciais (Sempre Usar)**

#### 1. **Browser (Anti-Detecção)**
```python
from src.common.browser import (
    create_stealth_browser,      # Cria browser com args anti-bot
    create_stealth_context,       # Cria context com fingerprinting
    create_stealth_page           # Cria page com TODOS os fingerprints
)
```

**Score:** 9.0/10
**O que faz:** Cria browser, context e page com anti-detecção completa

#### 2. **Perfis de Hardware**
```python
from src.common.profiles.profile_manager import get_profile_for_processor
```

**O que faz:** Retorna perfil consistente (viewport, CPU, memory, seeds) para cada processador

#### 3. **ExecutionLogger**
```python
from src.common.execution_logger import setup_execution_logger
```

**O que faz:** Registra logs estruturados com timestamp em arquivo

#### 4. **ScreenshotManager**
```python
from src.common.screenshot_manager import setup_screenshot_manager
```

**O que faz:** Captura screenshots organizados por processador + timestamp

#### 5. **PlaywrightCaptchaManager**
```python
from src.common.playwright_captcha_manager import PlaywrightCaptchaManager
```

**O que faz:** Resolve CAPTCHAs com CapSolver + fallback humano (email)

#### 6. **ConfigLoader**
```python
from src.common.config_loader import get_config_loader
```

**O que faz:** Carrega configurações (processors.yaml) e credenciais (credentials.csv) com rotação

#### 7. **RateLimitHandler**
```python
from src.common.rate_limit_handler import RateLimitHandler
```

**O que faz:** Detecta e trata HTTP 429 (Too Many Requests) automaticamente com retry

---

### **📦 Módulos Opcionais (Usar Quando Necessário)**

#### 8. **Wait Utils (Para Páginas Lentas com Proxy)**
```python
from src.common.wait_utils import (
    wait_for_page_ready,           # Aguarda página carregar completamente
    wait_for_element,              # Aguarda elemento estar visível
    wait_for_element_with_retry,   # Aguarda com retry (proxy lento)
    wait_for_navigation_complete,  # Aguarda navegação + redirecionamento
    smart_wait,                    # Wait inteligente (adapta ao proxy)
    wait_for_frame_ready           # Aguarda iframe carregar
)
```

**Quando usar:** Se usar proxy Bright Data, páginas demoram MUITO mais para carregar

Documentação completa: `docs/WAIT_UTILS.md`

#### 9. **File Rename Utilities**
```python
from src.common.file_rename import aguardar_download_csv, renomear_arquivo_processador
```

**Quando usar:** Processadores que fazem download de arquivos CSV

#### 10. **Bright Data Proxy (Opcional)**
```python
from src.common.anti_detection.brightdata_proxy import get_proxy_config, get_stealth_context
```

**Quando usar:** Se quiser usar proxy rotativo (IP diferente) ou sticky (mesmo IP durante execução)

⚠️ **ATENÇÃO:** Proxy deixa páginas mais lentas. Use `wait_utils` para aguardar carregamento.

---

## 🔬 **ANATOMIA DE UM PROCESSADOR**

### **Estrutura Básica Atualizada (2025)**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROCESSADOR: nome_do_processador
DESCRIÇÃO: O que ele faz
URL: URL do site
SCORE ANTI-DETECÇÃO: 9.0/10
"""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Playwright
from playwright.async_api import async_playwright

# Módulos NOVOS (Anti-Detecção Score 9.0)
from src.common.browser import create_stealth_browser, create_stealth_context, create_stealth_page
from src.common.profiles.profile_manager import get_profile_for_processor
from src.common.wait_utils import wait_for_page_ready, wait_for_element, smart_wait
from src.common.rate_limit_handler import RateLimitHandler

# Módulos Comuns
from src.common.execution_logger import setup_execution_logger
from src.common.screenshot_manager import setup_screenshot_manager
from src.common.playwright_captcha_manager import PlaywrightCaptchaManager
from src.common.config_loader import get_config_loader
from src.common.file_rename import aguardar_download_csv, renomear_arquivo_processador
from src.common.notification_utils import enviar_notificacao_email

load_dotenv()

# Configurações
DEBUG = os.getenv("DEBUG_MODE", "false").lower() == "true"
URL_LOGIN = "https://site.com/login"
URL_TARGET = "https://site.com/target-page"
DOWNLOAD_DIR = Path("data/raw_inputs/")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Config loader
config_loader = get_config_loader()
PROCESSOR_NAME = "nome_do_processador"
processor_config = config_loader.get_processor_config(PROCESSOR_NAME)


class ProcessadorNomeDoProcessador:
    """Descrição do processador - Score 9.0/10"""

    def __init__(self):
        self.nome = PROCESSOR_NAME
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.rate_limiter = None

        # Loggers
        self.logger_exec = setup_execution_logger(self.nome, log_dir="logs")
        self.screenshot_manager = setup_screenshot_manager(
            self.nome,
            screenshot_dir="data/screenshots",
            config=processor_config
        )

        # Credenciais (com rotação automática)
        credential = config_loader.get_credentials(self.nome)
        self.email = credential.usuario
        self.senha = credential.senha

        # Flags de controle
        self.pausado_ref = {"value": False}
        self.parar_ref = {"value": False}

        # CAPTCHA Manager
        self.captcha_manager = PlaywrightCaptchaManager(
            capsolver_api_key=os.getenv("CAPSOLVER_API_KEY"),
            execution_logger=self.logger_exec,
            screenshot_callback=self._take_screenshot,
            pausado_flag_ref=self.pausado_ref,
            parar_flag_ref=self.parar_ref,
            nome_processador=self.nome
        )

        self.logger_exec.log(f"🚀 Processador '{self.nome}' inicializado (Score 9.0)")

    async def _take_screenshot(self, nome: str, full_page: bool = True):
        """Captura screenshot"""
        try:
            await self.screenshot_manager.capture(self.page, nome, full_page=full_page)
        except Exception as exc:
            self.logger_exec.log(f"⚠️ Falha ao capturar screenshot '{nome}': {exc}")

    def _retry_callback_429(self, retry_count: int, wait_time: float):
        """Callback chamado quando HTTP 429 é detectado"""
        self.logger_exec.log(f"🔄 HTTP 429 detectado - Tentativa {retry_count}, aguardando {wait_time}s...")

    async def inicializar_browser(self):
        """Inicializa Playwright e browser com NOVOS módulos anti-detecção (score 9.0)"""
        self.logger_exec.log("🔧 Inicializando browser com anti-detecção (score 9.0)...")

        self.playwright = await async_playwright().start()

        # Buscar perfil de hardware para este processador
        profile = get_profile_for_processor(self.nome)
        self.logger_exec.log(f"✅ Perfil de hardware carregado: {profile.name}")

        # 1. Criar browser (com proxy se configurado no .env)
        self.browser = await create_stealth_browser(
            playwright=self.playwright,
            headless=False,
            use_proxy=True  # Tenta usar proxy do .env (opcional)
        )

        # 2. Criar context (com perfil de hardware)
        self.context = await create_stealth_context(
            browser=self.browser,
            processor_name=self.nome,
            profile=profile
        )

        # 3. Criar page (com TODOS os fingerprints auto-injetados)
        self.page = await create_stealth_page(
            context=self.context,
            processor_name=self.nome,
            profile=profile
        )

        # 4. Inicializar RateLimitHandler (detecta HTTP 429 automaticamente)
        rate_limit_config = processor_config.rate_limit if processor_config and hasattr(processor_config, 'rate_limit') else {}

        self.rate_limiter = RateLimitHandler(
            page=self.page,
            context=self.context,
            execution_logger=self.logger_exec,
            config=rate_limit_config,
            on_retry_start=self._retry_callback_429
        )

        await self.rate_limiter.start_monitoring()
        self.logger_exec.log("✅ RateLimitHandler ativado - monitoramento automático de HTTP 429")

        self.logger_exec.log("✅ Browser Playwright inicializado (score 9.0/10)")

    async def fechar_browser(self):
        """Fecha browser"""
        try:
            if self.rate_limiter:
                await self.rate_limiter.stop_monitoring()
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.logger_exec.log("🔒 Browser fechado")
        except Exception as exc:
            self.logger_exec.log(f"⚠️ Erro ao fechar browser: {exc}")

    async def fazer_login(self):
        """Realiza login no site"""
        self.logger_exec.log("="*80)
        self.logger_exec.log("🔐 ETAPA 1: LOGIN")
        self.logger_exec.log("="*80)

        # Navegar para login
        await self.page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)

        # Aguardar página carregar completamente (especialmente importante com proxy)
        await wait_for_page_ready(self.page, timeout=60000, logger=self.logger_exec)

        await self._take_screenshot("01_pagina_login")

        # Aguardar campo de email estar visível
        await wait_for_element(self.page, "#email", logger=self.logger_exec)

        # Preencher credenciais
        await self.page.fill("#email", self.email)
        await self.page.fill("#password", self.senha)
        self.logger_exec.log(f"✅ Credenciais preenchidas ({self.email})")

        # Wait humano antes de clicar
        await smart_wait(self.page, with_proxy=True, logger=self.logger_exec)

        # Clicar em login
        await self.page.click("#login-button")

        # Resolver CAPTCHA (se aparecer)
        captcha_resolvido = await self.captcha_manager.resolver_com_fallback(
            self.page, "login", None
        )

        if not captcha_resolvido:
            raise Exception("CAPTCHA não resolvido durante login")

        # Aguardar redirecionamento
        await wait_for_page_ready(self.page, timeout=60000, logger=self.logger_exec)

        self.logger_exec.log("✅ Login realizado com sucesso")
        await self._take_screenshot("02_login_sucesso")

    async def extrair_dados(self):
        """Extrai dados da página alvo"""
        self.logger_exec.log("="*80)
        self.logger_exec.log("📊 ETAPA 2: EXTRAÇÃO DE DADOS")
        self.logger_exec.log("="*80)

        await self.page.goto(URL_TARGET, wait_until="networkidle", timeout=60000)
        await wait_for_page_ready(self.page, timeout=60000, logger=self.logger_exec)

        self.logger_exec.log("🌐 Página alvo acessada")
        await self._take_screenshot("03_pagina_carregada")

        # Aguardar botão de exportar estar visível
        await wait_for_element(self.page, "#export-button", logger=self.logger_exec)

        # Clicar no botão de exportar
        await self.page.click("#export-button")
        self.logger_exec.log("✅ Exportação iniciada")

        # Aguardar download
        arquivo = await aguardar_download_csv(
            DOWNLOAD_DIR,
            timeout=processor_config.timeout_download,
            processador_nome=self.nome
        )

        # Renomear arquivo
        await renomear_arquivo_processador(
            arquivo,
            self.nome,
            self.logger_exec
        )

        await self._take_screenshot("04_extracao_concluida")
        self.logger_exec.log("✅ Extração concluída com sucesso")

    async def executar_extracao_completa(self):
        """Executa extração completa"""
        await self.fazer_login()
        await self.extrair_dados()

    async def iniciar(self):
        """Loop principal"""
        try:
            await self.inicializar_browser()
            await self.executar_extracao_completa()

            if DEBUG:
                self.logger_exec.log("🔧 MODO DEBUG ATIVO - Browser permanecerá aberto")
                while True:
                    await asyncio.sleep(10)
            else:
                self.logger_exec.log("✅ EXTRAÇÃO CONCLUÍDA - Encerrando...")

        except Exception as exc:
            self.logger_exec.log(f"❌ Erro: {exc}")
            await self._take_screenshot("erro")

            # Enviar notificação de erro
            await enviar_notificacao_email(
                assunto=f"❌ Erro no Processador {self.nome}",
                corpo=f"Erro: {exc}",
                processador_nome=self.nome
            )
            raise

        finally:
            await self.fechar_browser()
            self.logger_exec.log("🏁 Processador finalizado")
            self.logger_exec.close()


async def main():
    processador = ProcessadorNomeDoProcessador()
    await processador.iniciar()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📝 **PASSO A PASSO PARA CRIAR**

### **1. Copiar Template**

```bash
# Copiar de um processador existente
cp src/processors/web/envio_boleto_operacao_oculto.py \
   src/processors/web/novo_processador.py
```

**Processadores de referência:**
- `envio_boleto_operacao_oculto.py` - Score 9.0, com todos os módulos novos
- `relatorio_operacao_desagio.py` - Score 9.0, template básico

### **2. Configurar Credenciais**

Editar `config/credentials.csv`:

```csv
processador,cliente,usuario,senha,ativo
novo_processador,prosper,user1@exemplo.com,senha1,true
novo_processador,prosper,user2@exemplo.com,senha2,true
```

### **3. Configurar Processador**

Editar `config/processors.yaml`:

```yaml
novo_processador:
  # Orquestração
  display: ":3"                      # Display VNC (1, 2, 3, 4...)
  api_port: 6094                     # Porta da API de controle
  vnc_port: 6082                     # Porta VNC (calculada automaticamente: 6080 + display - 1)
  execution_mode: "one-shot"         # "one-shot" ou "loop"
  interval_seconds: 300              # Intervalo (se loop)
  cron: "0 */2 * * *"               # Cron (se one-shot)
  login_policy: round_robin          # Rotação: round_robin, sequential, random, first

  # Features
  enable_screenshots: true
  screenshot_level: milestones       # none | errors-only | milestones | full
  enable_execution_logs: true
  log_level: INFO

  # Timeouts
  timeout_captcha: 100               # Segundos
  timeout_download: 90               # Segundos

  # Rate Limiting (HTTP 429)
  rate_limit:
    enabled: true                    # Ativar detecção automática
    max_retries: 3                   # Tentativas máximas
    initial_wait: 60                 # Espera inicial (segundos)
    backoff_multiplier: 2            # Multiplicador exponencial
    max_wait: 300                    # Espera máxima (segundos)
    extra_wait_after_success: 10     # Tempo extra após retry bem-sucedido
```

### **4. Customizar Código**

Modificar APENAS:

- ✅ `URL_LOGIN` e `URL_TARGET`
- ✅ Seletores CSS (#id, .class)
- ✅ Lógica de navegação específica
- ✅ Nome do processador (`PROCESSOR_NAME`)

**NÃO modificar:**
- ❌ Inicialização do browser (usar `create_stealth_*`)
- ❌ Sistema de logs
- ❌ Gerenciamento de CAPTCHA
- ❌ RateLimitHandler
- ❌ Sistema de credenciais

### **5. Testar**

```bash
# Modo debug (browser fica aberto)
DISPLAY=:3 DEBUG_MODE=true PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/novo_processador.py

# Modo produção (fecha automaticamente)
DISPLAY=:3 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION \
  venv/bin/python3 src/processors/web/novo_processador.py
```

Acessar VNC: `http://SEU_IP:6082/vnc.html` (porta 6082 = display :3)

---

## ⚙️ **SISTEMA DE CONFIGURAÇÃO**

### **Arquivo: config/processors.yaml**

**Campos importantes:**

- `display` - Display VNC único para cada processador
- `api_port` - Porta da API de controle (única por processador)
- `execution_mode` - `one-shot` (executa 1x) ou `loop` (infinito)
- `screenshot_level` - **milestones** (recomendado) captura pontos-chave
- `rate_limit.enabled` - **true** (recomendado) para ativar tratamento HTTP 429

### **Arquivo: config/credentials.csv**

**Rotação automática:**

```csv
processador,cliente,usuario,senha,ativo
meu_proc,prosper,user1@ex.com,senha1,true
meu_proc,prosper,user2@ex.com,senha2,false  ← Desabilitado (não será usado)
meu_proc,prosper,user3@ex.com,senha3,true
```

Com `login_policy: round_robin`:
- Exec 1: user1
- Exec 2: user3 (user2 pulado - ativo=false)
- Exec 3: user1

---

## 🎯 **BOAS PRÁTICAS**

### **1. SEMPRE usar novos módulos anti-detecção**

```python
# ✅ BOM (Score 9.0)
from src.common.browser import create_stealth_browser, create_stealth_context, create_stealth_page

self.browser = await create_stealth_browser(playwright, headless=False, use_proxy=True)
self.context = await create_stealth_context(browser, processor_name, profile)
self.page = await create_stealth_page(context, processor_name, profile)

# ❌ RUIM (Score 6.0 - módulos antigos)
self.browser = await playwright.chromium.launch(headless=False)
self.context = await self.browser.new_context()
self.page = await self.context.new_page()
```

### **2. SEMPRE usar wait_utils com proxy**

```python
# ✅ BOM (aguarda página carregar completamente)
await self.page.goto(URL, wait_until="networkidle", timeout=60000)
await wait_for_page_ready(self.page, timeout=60000, logger=self.logger_exec)
await wait_for_element(self.page, "#botao", logger=self.logger_exec)

# ❌ RUIM (pode clicar antes do elemento estar pronto)
await self.page.goto(URL)
await asyncio.sleep(5)  # Wait fixo não confiável
await self.page.click("#botao")
```

### **3. SEMPRE ativar RateLimitHandler**

```python
# ✅ BOM (trata HTTP 429 automaticamente)
self.rate_limiter = RateLimitHandler(
    page=self.page,
    context=self.context,
    execution_logger=self.logger_exec,
    config=rate_limit_config,
    on_retry_start=self._retry_callback_429
)
await self.rate_limiter.start_monitoring()

# ❌ RUIM (código manual HTTP 429 - duplicado, difícil de manter)
# ... 100+ linhas verificando HTTP 429 manualmente ...
```

### **4. Logs informativos**

```python
# ✅ BOM
self.logger_exec.log("✅ Login realizado com sucesso")
self.logger_exec.log(f"📝 Credenciais: {self.email}")

# ❌ RUIM
self.logger_exec.log("ok")
```

### **5. Screenshots estratégicos**

```python
# ✅ BOM (pontos-chave)
await self._take_screenshot("01_pagina_login")
await self._take_screenshot("02_login_sucesso")
await self._take_screenshot("erro_login")

# ❌ RUIM (screenshot a cada linha - poluição)
await self._take_screenshot("linha1")
await self._take_screenshot("linha2")
```

---

## 🐛 **TROUBLESHOOTING**

### **Problema: Página demora para carregar (timeout)**

**Causa:** Proxy Bright Data deixa páginas mais lentas

**Solução:**
```python
# Usar timeouts maiores + wait_utils
await self.page.goto(URL, wait_until="networkidle", timeout=90000)  # 90s
await wait_for_page_ready(self.page, timeout=90000, logger=self.logger_exec)
```

### **Problema: HTTP 429 Too Many Requests**

**Causa:** Servidor bloqueou muitas requisições

**Solução:** RateLimitHandler já trata automaticamente. Verifique se está ativado:
```yaml
# config/processors.yaml
rate_limit:
  enabled: true
```

### **Problema: CAPTCHA não resolve**

**Solução 1:** Verificar site_key correto:
```python
site_key = await self.page.evaluate("""
    () => {
        const iframe = document.querySelector('iframe[src*="recaptcha"]');
        if (iframe) {
            const match = iframe.src.match(/[?&]k=([^&]+)/);
            return match ? match[1] : null;
        }
        return null;
    }
""")
print(f"Site key: {site_key}")
```

**Solução 2:** Passar site_key manualmente:
```python
captcha_resolvido = await self.captcha_manager.resolver_com_fallback(
    self.page,
    "login",
    site_key_fallback="6Le-xxxxxxxxxxxxx"
)
```

### **Problema: Elemento não encontrado**

**Solução:** Aguardar elemento estar visível:
```python
# ✅ CORRETO
await wait_for_element(self.page, "#botao", state="visible", timeout=30000)
await self.page.click("#botao")

# ❌ ERRADO
await self.page.click("#botao")  # Pode falhar se não estiver visível
```

---

## ✅ **CHECKLIST DE VALIDAÇÃO**

Antes de considerar o processador pronto:

### **Funcionalidade**
- [ ] Login funciona
- [ ] CAPTCHA resolve automaticamente
- [ ] Navegação chega à página correta
- [ ] Extração/download funciona
- [ ] Arquivo renomeado corretamente

### **Anti-Detecção (Score 9.0)**
- [ ] Usa `create_stealth_browser/context/page`
- [ ] Perfil de hardware carregado
- [ ] RateLimitHandler ativado
- [ ] Wait utils usado (se proxy ativo)

### **Configuração**
- [ ] Credenciais no `credentials.csv`
- [ ] Configurações no `processors.yaml`
- [ ] Rate limit configurado
- [ ] Display VNC único

### **Logs e Debug**
- [ ] Logs detalhados
- [ ] Screenshots em pontos-chave
- [ ] Modo DEBUG funciona
- [ ] Modo PRODUÇÃO funciona

### **Robustez**
- [ ] Tratamento de erros adequado
- [ ] Timeouts configurados (90s+ com proxy)
- [ ] Aguarda elementos antes de interagir
- [ ] Fecha browser ao finalizar

### **Testes**
- [ ] Testado em DEBUG
- [ ] Testado em PRODUÇÃO
- [ ] Testado com 2+ credenciais (rotação)
- [ ] Testado com CAPTCHA manual
- [ ] Testado end-to-end completo

---

## 📚 **REFERÊNCIAS**

### **Documentação Interna**
- `docs/README_MODULOS.md` - Documentação completa de todos os módulos
- `docs/WAIT_UTILS.md` - Guia completo de wait_utils
- `docs/GUIA_BRIGHT_DATA.md` - Configuração Bright Data proxy
- `docs/ESTRUTURA_DE_PASTAS.md` - Organização do projeto

### **Código de Referência**
- `src/processors/web/envio_boleto_operacao_oculto.py` - Processador completo (Score 9.0)
- `src/processors/web/relatorio_operacao_desagio.py` - Template básico (Score 9.0)
- `src/common/browser/` - Módulos de browser anti-detecção
- `src/common/wait_utils.py` - Módulo de espera inteligente
- `src/common/rate_limit_handler.py` - Handler de HTTP 429

### **Ferramentas Externas**
- [Playwright Python Docs](https://playwright.dev/python/docs/intro)
- [CapSolver API Docs](https://docs.capsolver.com/)
- [Bright Data Docs](https://docs.brightdata.com/)

---

## 🚀 **INÍCIO RÁPIDO**

```bash
# 1. Criar novo processador
cp src/processors/web/envio_boleto_operacao_oculto.py \
   src/processors/web/meu_processador.py

# 2. Configurar
vim config/credentials.csv      # Adicionar credenciais
vim config/processors.yaml      # Adicionar configurações

# 3. Customizar código
vim src/processors/web/meu_processador.py
# → Alterar PROCESSOR_NAME, URL_LOGIN, URL_TARGET, seletores

# 4. Testar em DEBUG
DISPLAY=:3 DEBUG_MODE=true PYTHONPATH=$PWD \
  venv/bin/python3 src/processors/web/meu_processador.py

# 5. Acessar VNC para ver execução
# http://SEU_IP:6082/vnc.html (porta 6082 = display :3)

# 6. Testar em PRODUÇÃO
DISPLAY=:3 PYTHONPATH=$PWD \
  venv/bin/python3 src/processors/web/meu_processador.py
```

---

**Última atualização:** 2025-11-15
**Versão:** 3.0
**Score anti-detecção:** 9.0/10
**Processadores de referência:** `envio_boleto_operacao_oculto.py` (Score 9.0), `relatorio_operacao_desagio.py` (Score 9.0)
