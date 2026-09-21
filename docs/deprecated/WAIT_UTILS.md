# Wait Utils - Módulo de Espera Inteligente

## 📋 Visão Geral

Módulo centralizado em `src/common/wait_utils.py` para aguardar páginas e elementos de forma robusta.

**IMPORTANTE**: Com proxy (especialmente proxy rotativo), páginas demoram MUITO mais para carregar. Este módulo garante que a automação só continua quando a página/elemento está realmente pronto.

## 🎯 Problema Resolvido

### ❌ ANTES (sem wait inteligente):
```python
await page.goto(URL)
# ❌ Tenta clicar IMEDIATAMENTE (elemento pode não estar pronto!)
await page.click("button#submit")  # ERRO: elemento não encontrado
```

### ✅ DEPOIS (com wait inteligente):
```python
from src.common.wait_utils import wait_for_page_ready, wait_for_element

await page.goto(URL)
await wait_for_page_ready(page, timeout=60000)  # Aguarda página carregar
await wait_for_element(page, "button#submit")  # Aguarda botão estar visível
await page.click("button#submit")  # ✅ SUCESSO!
```

---

## 📚 Funções Disponíveis

### 1. `wait_for_page_ready()` - Aguardar Página Carregar

Aguarda a página carregar completamente antes de continuar.

```python
from src.common.wait_utils import wait_for_page_ready

# Aguardar com networkidle (RECOMENDADO para proxy)
await wait_for_page_ready(page, timeout=60000, wait_until="networkidle")

# Com logger
await wait_for_page_ready(page, timeout=60000, logger=self.logger_exec)
```

**Estratégias de espera**:
- `"networkidle"` → Aguarda rede idle (RECOMENDADO - mais confiável)
- `"load"` → Aguarda evento load (rápido, mas pode não estar 100% pronto)
- `"domcontentloaded"` → Aguarda DOM carregado (médio)

---

### 2. `wait_for_element()` - Aguardar Elemento Específico

Aguarda elemento estar visível/pronto antes de interagir.

```python
from src.common.wait_utils import wait_for_element

# Aguardar botão estar visível
if await wait_for_element(page, "button#submit", state="visible"):
    await page.click("button#submit")

# Aguardar input estar anexado ao DOM
await wait_for_element(page, "input#username", state="attached")
```

**Estados disponíveis**:
- `"visible"` → Elemento está visível (RECOMENDADO)
- `"attached"` → Elemento existe no DOM
- `"hidden"` → Elemento está escondido
- `"detached"` → Elemento não existe no DOM

---

### 3. `wait_for_element_with_retry()` - Aguardar com Retry

Tenta múltiplas vezes aguardar elemento (útil para páginas MUITO lentas com proxy).

```python
from src.common.wait_utils import wait_for_element_with_retry

# Tentar 3x com 5s entre tentativas
success = await wait_for_element_with_retry(
    page,
    "div#content",
    max_retries=3,
    retry_delay=5000,  # 5 segundos entre tentativas
    logger=self.logger_exec
)

if success:
    # Elemento encontrado!
    await page.click("div#content")
```

---

### 4. `wait_for_navigation_complete()` - Aguardar Navegação

Aguarda navegação completar e página carregar (útil após login, submit de form, etc).

```python
from src.common.wait_utils import wait_for_navigation_complete

# Aguardar redirecionamento para dashboard após login
await wait_for_navigation_complete(
    page,
    url_pattern="dashboard",
    timeout=60000,
    logger=self.logger_exec
)
```

---

### 5. `smart_wait()` - Wait Inteligente com Proxy

Wait que se adapta automaticamente ao uso de proxy.

```python
from src.common.wait_utils import smart_wait

# Wait simples (2s)
await smart_wait(page)

# Wait com proxy (3s - aumenta automaticamente 50%)
await smart_wait(page, with_proxy=True, logger=self.logger_exec)

# Wait customizado
await smart_wait(page, base_delay=5000, with_proxy=True)
```

---

### 6. `wait_for_frame_ready()` - Aguardar Iframe Carregar

Aguarda iframe (frame interno) carregar completamente.

```python
from src.common.wait_utils import wait_for_frame_ready

# Obter iframe
frame = page.frame(name="iframe_emissao")

# Aguardar iframe carregar
await wait_for_frame_ready(frame, timeout=30000, logger=self.logger_exec)

# Agora pode interagir com elementos do iframe
await frame.click("button#gerar_boleto")
```

---

## 🚀 Exemplos Práticos

### Exemplo 1: Login com Proxy Lento

```python
from src.common.wait_utils import (
    wait_for_page_ready,
    wait_for_element,
    smart_wait
)

# Navegar para login
await page.goto(URL_LOGIN)
await wait_for_page_ready(page, timeout=60000, logger=self.logger_exec)

# Aguardar formulário de login estar pronto
await wait_for_element(page, "input#username", logger=self.logger_exec)

# Preencher
await page.fill("input#username", username)
await page.fill("input#password", password)

# Wait antes de clicar (comportamento humano)
await smart_wait(page, with_proxy=True)

# Clicar em login
await page.click("button#login")

# Aguardar navegação pós-login
await wait_for_page_ready(page, timeout=60000, logger=self.logger_exec)
```

---

### Exemplo 2: Trabalhar com Iframe

```python
from src.common.wait_utils import wait_for_frame_ready, wait_for_element

# Aguardar página principal carregar
await wait_for_page_ready(page, timeout=60000)

# Aguardar iframe aparecer
await wait_for_element(page, "iframe[name='iframe_emissao']")

# Obter iframe
frame = page.frame(name="iframe_emissao")

# Aguardar iframe carregar
await wait_for_frame_ready(frame, timeout=30000, logger=self.logger_exec)

# Aguardar elemento dentro do iframe
await wait_for_element(frame, "button#gerar_boleto", logger=self.logger_exec)

# Clicar no botão
await frame.click("button#gerar_boleto")
```

---

### Exemplo 3: Retry para Páginas Muito Lentas

```python
from src.common.wait_utils import wait_for_element_with_retry

# Tentar 5x aguardar elemento (útil com proxy muito lento)
success = await wait_for_element_with_retry(
    page,
    "div#resultado",
    max_retries=5,
    retry_delay=10000,  # 10s entre tentativas
    timeout=30000,      # 30s por tentativa
    logger=self.logger_exec
)

if not success:
    raise Exception("Elemento 'div#resultado' não apareceu após 5 tentativas")

# Continuar processamento
await page.click("div#resultado")
```

---

## 🎯 Quando Usar Cada Função

| Situação | Função Recomendada |
|----------|-------------------|
| Após `page.goto()` | `wait_for_page_ready()` |
| Antes de clicar em elemento | `wait_for_element()` |
| Proxy MUITO lento | `wait_for_element_with_retry()` |
| Após submit de form | `wait_for_navigation_complete()` |
| Between actions (comportamento humano) | `smart_wait()` |
| Trabalhar com iframe | `wait_for_frame_ready()` |

---

## ⚙️ Configurações Recomendadas

### Com Proxy (Bright Data):
```python
# Timeouts maiores
await wait_for_page_ready(page, timeout=90000)  # 90s
await wait_for_element(page, selector, timeout=45000)  # 45s
await smart_wait(page, base_delay=3000, with_proxy=True)  # 4.5s
```

### Sem Proxy (Conexão Direta):
```python
# Timeouts normais
await wait_for_page_ready(page, timeout=30000)  # 30s
await wait_for_element(page, selector, timeout=15000)  # 15s
await smart_wait(page, base_delay=2000)  # 2s
```

---

## 🔧 Integração com Processadores Existentes

### ANTES:
```python
async def fazer_login(self):
    await self.page.goto(URL_LOGIN)
    await asyncio.sleep(5)  # ❌ Wait fixo (não confiável)
    await self.page.fill("input#username", username)
    await self.page.click("button#login")
    await asyncio.sleep(10)  # ❌ Wait fixo (não confiável)
```

### DEPOIS:
```python
from src.common.wait_utils import wait_for_page_ready, wait_for_element, smart_wait

async def fazer_login(self):
    await self.page.goto(URL_LOGIN)
    await wait_for_page_ready(self.page, timeout=60000, logger=self.logger_exec)

    await wait_for_element(self.page, "input#username", logger=self.logger_exec)
    await self.page.fill("input#username", username)

    await smart_wait(self.page, with_proxy=True)
    await self.page.click("button#login")

    await wait_for_page_ready(self.page, timeout=60000, logger=self.logger_exec)
```

---

## 📊 Benefícios

✅ **Confiabilidade**: Aguarda REALMENTE a página/elemento estar pronto
✅ **Adaptável**: Ajusta timeouts automaticamente para proxy
✅ **Reutilizável**: Um módulo para TODOS os processadores
✅ **Logging**: Integrado com ExecutionLogger
✅ **Retry Inteligente**: Tenta múltiplas vezes em caso de página lenta
✅ **Type Hints**: Suporte completo para IDE autocomplete

---

**Autor**: Sistema de Automação PROSPER
**Data**: 2025-11-15
**Módulo**: `src/common/wait_utils.py`
