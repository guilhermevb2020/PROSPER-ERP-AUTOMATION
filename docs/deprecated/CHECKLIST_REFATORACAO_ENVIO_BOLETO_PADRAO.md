# Checklist de Refatoração: envio_boleto_operacao_padrao.py

**Data**: 2025-11-17
**Objetivo**: Modernizar `envio_boleto_operacao_padrao.py` para usar mesma arquitetura de `envio_boleto_operacao_oculto.py`
**Score Alvo**: 8.5/10 (atualmente ~5.0/10)

---

## 📊 ANÁLISE COMPARATIVA

### Estatísticas dos Arquivos

| Arquivo | Linhas | Score Estimado | Arquitetura |
|---------|--------|----------------|-------------|
| `envio_boleto_operacao_oculto.py` | 1,785 | 8.5/10 ✅ | Moderna (stealth) |
| `envio_boleto_operacao_padrao.py` | 1,138 | ~5.0/10 ❌ | Antiga (vanilla) |

---

## 🔍 DIFERENÇAS IDENTIFICADAS

### 1. ❌ Sistema Anti-Detecção (CRÍTICO)

#### Atual (Padrão - Linha ~328):
```python
self.browser = await self.playwright.chromium.launch(
    headless=False,
    args=[
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
    ]
)

context = await self.browser.new_context(
    viewport={'width': 1920, 'height': 1080},
    user_agent='Mozilla/5.0 ...',
    accept_downloads=True
)

self.page = await context.new_page()
```

**Problemas**:
- ❌ Sem fingerprinting (Canvas, WebGL, Audio, Navigator)
- ❌ Sem Sec-Fetch headers
- ❌ Sem hardware profiles
- ❌ Sem stealth integration
- ❌ User-agent hardcoded
- ❌ Args básicos (falta ~10 args modernos)

---

#### Desejado (Oculto - Linha ~334-389):
```python
from src.common.browser import create_stealth_browser, create_stealth_context, create_stealth_page
from src.common.profiles.profile_manager import get_profile_for_processor

# Carregar profile
profile = get_profile_for_processor(self.nome)

# Browser stealth
self.browser = await create_stealth_browser(
    playwright=self.playwright,
    headless=False,
    use_proxy=proxy_configurado
)

# Context com perfil
self.context = await create_stealth_context(
    browser=self.browser,
    processor_name=self.nome,
    profile=profile
)

# Page com fingerprints auto-injetados
self.page = await create_stealth_page(
    context=self.context,
    processor_name=self.nome,
    profile=profile
)
```

**Benefícios**:
- ✅ Score 8.5/10 automaticamente
- ✅ 7 fingerprints injetados
- ✅ Sec-Fetch headers
- ✅ Hardware profile consistente
- ✅ Launch args otimizados

---

### 2. ❌ Imports Faltantes

#### Atual (Padrão - Linha 27-40):
```python
import asyncio
import os
import time
import json
from datetime import datetime

from playwright.async_api import async_playwright, Page, Browser

from src.common.core.database import query
from src.common.core.execution_logger import ExecutionLogger
from src.common.core.screenshot_manager import ScreenshotManager
from src.common.captcha.playwright_captcha_manager import PlaywrightCaptchaManager
from src.common.core.config_loader import get_config_loader
```

**Faltando**:
- ❌ `from pathlib import Path` (oculto usa)
- ❌ `from src.common.utils.wait_utils import ...` (oculto usa)
- ❌ Imports stealth (browser, profiles)

---

#### Desejado (Oculto - tem):
```python
# ... imports existentes ...
from pathlib import Path

from src.common.utils.wait_utils import (
    wait_for_page_load,
    wait_for_element_stable,
    # ... outros
)

# Stealth (importados dentro de _inicializar_browser)
from src.common.browser import create_stealth_browser, create_stealth_context, create_stealth_page
from src.common.profiles.profile_manager import get_profile_for_processor
```

---

### 3. ❌ Funções Auxiliares de Template

#### Atual (Padrão):
- ❌ Não tem funções para carregar templates HTML
- ❌ Não tem conversão de mensagem texto → HTML

#### Desejado (Oculto - Linha 78-158):
```python
def converter_mensagem_para_html(mensagem_texto: str) -> str:
    """Converte mensagem de texto para HTML formatado."""
    # ...

def carregar_mensagem_boletos() -> str:
    """Carrega template de mensagem de boletos."""
    # ...
```

**Impacto**: Mensagens de email mais profissionais e ricas

---

### 4. ⚠️ Wait Utils (IMPORTANTE)

#### Atual (Padrão):
- Provavelmente usa apenas `await page.wait_for_selector()`
- Waits básicos sem estratégia

#### Desejado (Oculto):
```python
from src.common.utils.wait_utils import (
    wait_for_page_load,
    wait_for_element_stable,
    wait_for_element_clickable,
    wait_for_navigation_complete,
    # ...
)

# Uso:
await wait_for_page_load(self.page, timeout=30000)
await wait_for_element_stable(self.page, selector, timeout=10000)
```

**Benefícios**:
- ✅ Mais robusto com proxies
- ✅ Menos falhas por timing
- ✅ Retry automático

---

### 5. ⚠️ Configuração e Profiles

#### Atual (Padrão - Linha 99-119):
```python
try:
    config_loader = get_config_loader()
    processor_config = config_loader.get_processor_config(self.nome)
    # Usa apenas API_PORT e VNC_PORT
except:
    # Fallback para .env
```

**Faltando**:
- ❌ Não carrega hardware profile
- ❌ Não usa profile_override
- ❌ Não usa proxy config

---

#### Desejado (Oculto - Linha 338-361):
```python
config_loader = get_config_loader()
processor_config = config_loader.get_processor_config(self.nome)

# Carregar profile de hardware
profile = get_profile_for_processor(
    self.nome,
    profile_override=processor_config.hardware_profile_index
)

# Verificar proxy
proxy_configurado = (
    processor_config.proxy_enabled if processor_config
    else False
)
```

---

### 6. ⚠️ Estrutura de Métodos

#### Comparação de Métodos:

| Método | Padrão | Oculto | Observação |
|--------|--------|--------|------------|
| `__init__()` | ✅ Tem | ✅ Tem | Padrão mais simples |
| `_inicializar_browser()` | ✅ Tem | ✅ Tem | **Padrão usa vanilla, Oculto usa stealth** |
| `_fazer_login()` | ✅ Tem | ✅ Tem | Lógica similar |
| `_navegar_para_emissao()` | ✅ Tem | ✅ Tem | Lógica similar |
| `_processar_operacao()` | ✅ Tem | ✅ Tem | Núcleo do processamento |
| `_finalizar()` | ✅ Tem | ✅ Tem | Cleanup |
| `executar()` | ✅ Tem | ✅ Tem | Orquestrador principal |

**Conclusão**: Estrutura similar, mas implementações internas diferentes

---

## ✅ CHECKLIST DE REFATORAÇÃO

### Fase 1: Setup e Imports (Estimativa: 30min)

```
□ 1.1. Adicionar import de Path
□ 1.2. Adicionar imports de wait_utils
□ 1.3. Preparar imports stealth (dentro de _inicializar_browser)
□ 1.4. Adicionar docstring atualizado no topo do arquivo
```

---

### Fase 2: Funções Auxiliares (Estimativa: 1h)

```
□ 2.1. Copiar função converter_mensagem_para_html() do oculto
□ 2.2. Copiar função carregar_mensagem_boletos() do oculto
□ 2.3. Criar diretório data/assets/email/templates/ (se não existir)
□ 2.4. Testar funções isoladamente
```

---

### Fase 3: Inicialização Stealth (Estimativa: 2h) **CRÍTICO**

```
□ 3.1. Backup do método _inicializar_browser() atual
□ 3.2. Substituir conteúdo do método por versão stealth do oculto:
       □ 3.2.1. Importar módulos stealth
       □ 3.2.2. Carregar config e profile
       □ 3.2.3. Verificar proxy config
       □ 3.2.4. Usar create_stealth_browser()
       □ 3.2.5. Usar create_stealth_context()
       □ 3.2.6. Usar create_stealth_page()
□ 3.3. Adicionar logging de cada etapa
□ 3.4. Remover código antigo (browser.new_context, etc)
```

**Código de Referência**:
```python
async def _inicializar_browser(self):
    """Inicializa browser com anti-detecção (score 8.5)."""
    self.logger_exec.log("🔄 Inicializando browser com anti-detecção...")

    # Importar módulos stealth
    from playwright.async_api import async_playwright
    from src.common.browser import create_stealth_browser, create_stealth_context, create_stealth_page
    from src.common.profiles.profile_manager import get_profile_for_processor

    # Carregar configurações
    config_loader = get_config_loader()
    processor_config = config_loader.get_processor_config(self.nome)

    # Carregar profile de hardware
    profile = get_profile_for_processor(
        self.nome,
        profile_override=processor_config.hardware_profile_index if processor_config else None
    )
    self.logger_exec.log(f"   ✅ Profile carregado: {profile.description}")

    # Verificar proxy
    proxy_configurado = (
        processor_config.proxy_enabled if processor_config
        else False
    )

    # Inicializar Playwright
    self.playwright = await async_playwright().start()

    # 1. Criar browser stealth
    self.browser = await create_stealth_browser(
        playwright=self.playwright,
        headless=False,
        use_proxy=proxy_configurado
    )
    self.logger_exec.log("   ✅ Browser stealth criado")

    # 2. Criar context com perfil
    self.context = await create_stealth_context(
        browser=self.browser,
        processor_name=self.nome,
        profile=profile
    )
    self.logger_exec.log("   ✅ Context criado com perfil de hardware")

    # 3. Criar page com fingerprints
    self.page = await create_stealth_page(
        context=self.context,
        processor_name=self.nome,
        profile=profile
    )
    self.logger_exec.log("   ✅ Page criada com fingerprints (score 8.5)")
    self.logger_exec.log("      - Canvas, WebGL, Audio, Navigator, Font, WebRTC, ChromeRuntime")

    self.logger_exec.log("✅ Browser inicializado com sucesso (anti-detecção ativo)")
```

---

### Fase 4: Wait Utils Integration (Estimativa: 1-2h)

```
□ 4.1. Identificar todos os await page.wait_for_selector()
□ 4.2. Substituir por wait_utils quando apropriado:
       □ 4.2.1. Navegação → wait_for_navigation_complete()
       □ 4.2.2. Carregamento → wait_for_page_load()
       □ 4.2.3. Elemento estável → wait_for_element_stable()
       □ 4.2.4. Elemento clicável → wait_for_element_clickable()
□ 4.3. Testar cada substituição
```

---

### Fase 5: Configuração de Profiles (Estimativa: 30min)

```
□ 5.1. Adicionar carregamento de hardware profile em __init__
□ 5.2. Adicionar verificação de proxy config
□ 5.3. Passar profile para screenshot_manager (se necessário)
□ 5.4. Adicionar logging de configuração carregada
```

---

### Fase 6: Testes e Validação (Estimativa: 2-3h)

```
□ 6.1. Teste sintático (python3 -m py_compile)
□ 6.2. Teste de import (python3 -c "from src.processors...")
□ 6.3. Teste de execução seca (sem operações reais)
□ 6.4. Teste com 1 operação real
□ 6.5. Teste com 5 operações reais
□ 6.6. Comparar taxa de sucesso antes/depois
□ 6.7. Verificar logs (fingerprints presentes?)
□ 6.8. Verificar tempo de execução (similar?)
```

---

### Fase 7: Documentação (Estimativa: 1h)

```
□ 7.1. Atualizar docstring do arquivo
□ 7.2. Adicionar comentários sobre score 8.5
□ 7.3. Documentar em docs/processors/envio_boleto_operacao_padrao.md
□ 7.4. Atualizar CHANGELOG.md
□ 7.5. Adicionar nota no README.md
```

---

### Fase 8: Cleanup (Estimativa: 30min)

```
□ 8.1. Remover código comentado (se houver)
□ 8.2. Remover imports não utilizados
□ 8.3. Formatar código (PEP 8)
□ 8.4. Criar backup final
□ 8.5. Commit com mensagem descritiva
```

---

## 📊 ESTIMATIVA TOTAL

| Fase | Tempo Estimado | Prioridade |
|------|----------------|------------|
| Fase 1: Setup | 30 min | Baixa |
| Fase 2: Funções Auxiliares | 1h | Média |
| **Fase 3: Stealth** | **2h** | **CRÍTICA** |
| Fase 4: Wait Utils | 1-2h | Alta |
| Fase 5: Profiles | 30 min | Média |
| Fase 6: Testes | 2-3h | CRÍTICA |
| Fase 7: Docs | 1h | Baixa |
| Fase 8: Cleanup | 30 min | Baixa |
| **TOTAL** | **8.5 - 10.5h** | **1-2 dias** |

---

## ⚠️ RISCOS E MITIGAÇÕES

### Risco 1: Quebrar funcionalidade existente
**Probabilidade**: Média
**Impacto**: Alto
**Mitigação**:
```
✅ Criar backup antes de começar
✅ Testar cada fase isoladamente
✅ Manter versão antiga em backup/
✅ Rollback preparado
```

---

### Risco 2: Diferenças sutis entre fluxos padrão e oculto
**Probabilidade**: Média
**Impacto**: Médio
**Mitigação**:
```
✅ Ler ambos os arquivos completamente antes
✅ Identificar lógica específica de cada um
✅ Não copiar cegamente - adaptar quando necessário
```

---

### Risco 3: Tempo de execução aumentar
**Probabilidade**: Baixa
**Impacto**: Baixo
**Mitigação**:
```
✅ Stealth adiciona < 1% overhead
✅ Wait utils podem até reduzir tempo (menos retries)
✅ Medir tempo antes e depois
```

---

## 🎯 RESULTADO ESPERADO

### Antes da Refatoração:
```
Score: ~5.0/10
Fingerprinting: ❌ Nenhum
Headers modernos: ❌ Não
Hardware profiles: ❌ Não
Wait utils: ⚠️ Básicos
Taxa de sucesso: ~85% (estimado)
```

### Depois da Refatoração:
```
Score: 8.5/10 ✅
Fingerprinting: ✅ 7 tipos (Canvas, WebGL, Audio, Navigator, Font, WebRTC, Chrome)
Headers modernos: ✅ Sec-Fetch-*
Hardware profiles: ✅ Consistentes
Wait utils: ✅ Avançados
Taxa de sucesso: 90-95% (esperado)
```

---

## 📝 CHECKLIST DE PRÉ-REQUISITOS

Antes de começar, verificar:

```
✓ Backup de envio_boleto_operacao_padrao.py criado?
✓ envio_boleto_operacao_oculto.py está funcionando?
✓ Melhorias antibot 2025 implementadas?
✓ Testes do oculto passaram?
✓ Tempo disponível para fazer (1-2 dias)?
✓ Ambiente de teste preparado?
```

---

## 🚀 PRÓXIMOS PASSOS

1. ✅ **Revisar este checklist** com usuário
2. ⏳ **Criar backup** de `envio_boleto_operacao_padrao.py`
3. ⏳ **Começar Fase 1** (Setup e Imports)
4. ⏳ Seguir checklist fase por fase
5. ⏳ Testar após cada fase
6. ⏳ Commit quando estável

---

## 📞 PERGUNTAS PARA O USUÁRIO

Antes de começar, esclarecer:

1. ❓ O processador `envio_boleto_operacao_padrao` está em uso ativo?
2. ❓ Qual a taxa de sucesso atual dele?
3. ❓ Há diferenças de fluxo entre "padrão" e "oculto" que preciso saber?
4. ❓ Posso fazer a refatoração agora ou há operações agendadas?
5. ❓ Quer que eu implemente tudo de uma vez ou fase por fase com aprovação?

---

**Criado por**: Claude Code
**Data**: 2025-11-17
**Status**: ⏳ Aguardando aprovação do usuário
