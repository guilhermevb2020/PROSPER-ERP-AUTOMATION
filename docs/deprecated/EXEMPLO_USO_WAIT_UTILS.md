# Exemplos de Uso - wait_utils.py

Este documento demonstra como usar as funções do módulo `src/common/wait_utils.py`.

## Importação

```python
from src.common.wait_utils import (
    wait_for_element,
    wait_for_navigation,
    wait_for_frame,
    wait_for_new_page,
    wait_for_popup_close,
    wait_for_iframe_content,
    wait_for_condition,
    wait_for_selector_count,
    wait_for_download,
    wait_with_random_delay
)
from src.common.execution_logger import ExecutionLogger
```

---

## 1. Funções Básicas

### `wait_for_element()` - Aguardar elemento aparecer

```python
async def exemplo_wait_element(page, logger):
    # Aguardar botão de login ficar visível
    success = await wait_for_element(
        page=page,
        selector="button#login",
        state="visible",
        timeout=30000,
        logger=logger
    )

    if success:
        await page.click("button#login")
```

### `wait_for_navigation()` - Aguardar navegação

```python
async def exemplo_navigation(page, logger):
    # Navegar e aguardar página carregar
    success = await wait_for_navigation(
        page=page,
        trigger_action=lambda: page.goto("https://exemplo.com"),
        wait_until="load",
        logger=logger
    )

    # Ou aguardar navegação sem trigger
    await wait_for_navigation(
        page=page,
        wait_until="networkidle",
        logger=logger
    )
```

### `wait_with_random_delay()` - Delay aleatório (comportamento humano)

```python
async def exemplo_random_delay(logger):
    # Aguardar entre 1 e 3 segundos
    await wait_with_random_delay(
        min_seconds=1.0,
        max_seconds=3.0,
        logger=logger
    )
```

---

## 2. Funções Avançadas - Frames e Popups

### `wait_for_frame()` - Aguardar frame específico aparecer

```python
async def exemplo_wait_frame(page, logger):
    # Aguardar iframe de login aparecer
    frame = await wait_for_frame(
        page=page,
        frame_url_pattern="loginsec.php",
        timeout=30000,
        logger=logger
    )

    if frame:
        # Interagir com elementos dentro do frame
        await frame.fill("input#username", "usuario")
        await frame.fill("input#password", "senha")
        await frame.click("button#login")
```

### `wait_for_new_page()` - Aguardar nova aba abrir

```python
async def exemplo_new_page(context, page, logger):
    # Aguardar nova página abrir após clicar em link
    new_page = await wait_for_new_page(
        context=context,
        trigger_action=lambda: page.click("a[target='_blank']"),
        timeout=30000,
        logger=logger
    )

    if new_page:
        # Trabalhar na nova página
        await new_page.wait_for_load_state()
        title = await new_page.title()
        logger.log(f"Nova página: {title}")

        # Fechar nova página
        await new_page.close()
```

### `wait_for_popup_close()` - Aguardar popup fechar

```python
async def exemplo_popup_close(context, page, logger):
    # Abrir popup
    popup = await wait_for_new_page(
        context=context,
        trigger_action=lambda: page.click("button#open-popup"),
        logger=logger
    )

    if popup:
        # Fazer algo no popup
        await popup.fill("input#data", "valor")
        await popup.click("button#submit")

        # Aguardar popup fechar automaticamente
        closed = await wait_for_popup_close(
            popup=popup,
            timeout=30000,
            logger=logger
        )

        if closed:
            logger.log("Popup fechado com sucesso")
```

### `wait_for_iframe_content()` - Aguardar conteúdo dentro de iframe

```python
async def exemplo_iframe_content(page, logger):
    # Primeiro, aguardar iframe aparecer
    frame = await wait_for_frame(
        page=page,
        frame_url_pattern="captcha.php",
        logger=logger
    )

    if frame:
        # Aguardar elemento dentro do iframe
        success = await wait_for_iframe_content(
            frame=frame,
            selector="div#captcha-container",
            state="visible",
            timeout=30000,
            logger=logger
        )

        if success:
            # Interagir com elemento do iframe
            await frame.click("div#captcha-container")
```

---

## 3. Funções Utilitárias

### `wait_for_condition()` - Aguardar condição customizada

```python
async def exemplo_condition(page, logger):
    # Aguardar múltiplos frames aparecerem
    success = await wait_for_condition(
        condition_func=lambda: len(page.frames) > 2,
        timeout=30000,
        condition_name="múltiplos frames",
        logger=logger
    )

    # Aguardar URL conter padrão específico
    success = await wait_for_condition(
        condition_func=lambda: "dashboard" in page.url,
        timeout=30000,
        condition_name="navegação para dashboard",
        logger=logger
    )
```

### `wait_for_selector_count()` - Aguardar número de elementos

```python
async def exemplo_selector_count(page, logger):
    # Aguardar 10 linhas de tabela aparecerem
    success = await wait_for_selector_count(
        page=page,
        selector="table tbody tr",
        expected_count=10,
        timeout=30000,
        logger=logger
    )

    if success:
        # Processar linhas
        rows = await page.locator("table tbody tr").all()
        for row in rows:
            text = await row.inner_text()
            logger.log(f"Linha: {text}")
```

### `wait_for_download()` - Aguardar download iniciar

```python
async def exemplo_download(page, logger):
    # Aguardar download após clicar em botão
    download = await wait_for_download(
        page=page,
        trigger_action=lambda: page.click("button#download-csv"),
        timeout=60000,
        logger=logger
    )

    if download:
        # Salvar arquivo
        filename = download.suggested_filename
        save_path = f"/tmp/{filename}"
        await download.save_as(save_path)
        logger.log(f"Download salvo: {save_path}")
```

---

## 4. Exemplo Completo - Fluxo de Login com Iframe

```python
from playwright.async_api import async_playwright
from src.common.wait_utils import *
from src.common.execution_logger import ExecutionLogger

async def exemplo_completo_login():
    logger = ExecutionLogger(log_file="/tmp/exemplo.log")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # 1. Navegar para página de login
            logger.log("Navegando para página de login...")
            await wait_for_navigation(
                page=page,
                trigger_action=lambda: page.goto("https://exemplo.com/login"),
                logger=logger
            )

            # 2. Aguardar iframe de login aparecer
            logger.log("Aguardando iframe de login...")
            frame = await wait_for_frame(
                page=page,
                frame_url_pattern="loginsec.php",
                timeout=30000,
                logger=logger
            )

            if not frame:
                logger.log("❌ Iframe não encontrado")
                return

            # 3. Aguardar campo de usuário dentro do iframe
            logger.log("Aguardando campo de usuário...")
            await wait_for_iframe_content(
                frame=frame,
                selector="input#username",
                state="visible",
                logger=logger
            )

            # 4. Preencher credenciais (com delay humano)
            logger.log("Preenchendo credenciais...")
            await frame.fill("input#username", "usuario")
            await wait_with_random_delay(0.5, 1.5, logger)

            await frame.fill("input#password", "senha")
            await wait_with_random_delay(0.5, 1.5, logger)

            # 5. Clicar em login e aguardar navegação
            logger.log("Clicando em login...")
            await wait_for_navigation(
                page=page,
                trigger_action=lambda: frame.click("button#login"),
                wait_until="networkidle",
                logger=logger
            )

            # 6. Verificar se login funcionou
            success = await wait_for_condition(
                condition_func=lambda: "dashboard" in page.url,
                timeout=10000,
                condition_name="navegação para dashboard",
                logger=logger
            )

            if success:
                logger.log("✅ Login realizado com sucesso!")
            else:
                logger.log("❌ Falha no login")

        finally:
            await browser.close()

# Executar exemplo
if __name__ == "__main__":
    import asyncio
    asyncio.run(exemplo_completo_login())
```

---

## 5. Exemplo Real - Processador com Popup de CAPTCHA

```python
async def exemplo_processador_com_captcha(page, context, logger):
    """
    Exemplo de processador que lida com popup de CAPTCHA.
    """

    # 1. Navegar para página
    await page.goto("https://sistema.com/relatorios")

    # 2. Clicar em botão que abre popup de CAPTCHA
    logger.log("Abrindo popup de CAPTCHA...")
    popup = await wait_for_new_page(
        context=context,
        trigger_action=lambda: page.click("button#gerar-relatorio"),
        timeout=30000,
        logger=logger
    )

    if not popup:
        logger.log("❌ Popup não abriu")
        return False

    # 3. Aguardar frame do reCAPTCHA no popup
    logger.log("Aguardando frame do reCAPTCHA...")
    recaptcha_frame = await wait_for_frame(
        page=popup,
        frame_url_pattern="recaptcha",
        timeout=30000,
        logger=logger
    )

    if not recaptcha_frame:
        logger.log("❌ Frame do reCAPTCHA não encontrado")
        await popup.close()
        return False

    # 4. Resolver CAPTCHA (usando seu captcha solver)
    logger.log("Resolvendo CAPTCHA...")
    # ... código de resolução de CAPTCHA ...

    # 5. Aguardar popup fechar automaticamente
    logger.log("Aguardando popup fechar...")
    closed = await wait_for_popup_close(
        popup=popup,
        timeout=60000,
        check_interval=0.5,
        logger=logger
    )

    if not closed:
        logger.log("⚠️ Popup não fechou automaticamente, fechando manualmente...")
        await popup.close()

    # 6. Aguardar download iniciar na página principal
    logger.log("Aguardando download...")
    download = await wait_for_download(
        page=page,
        trigger_action=lambda: asyncio.sleep(0),  # Download já foi disparado
        timeout=60000,
        logger=logger
    )

    if download:
        logger.log(f"✅ Download iniciado: {download.suggested_filename}")
        return True
    else:
        logger.log("❌ Download não iniciou")
        return False
```

---

## Boas Práticas

1. **Sempre use logger** - facilita debug e monitoramento
2. **Timeouts generosos** - especialmente para operações de rede
3. **Check intervals adequados** - 0.3s a 0.5s é ideal na maioria dos casos
4. **Tratamento de erros** - sempre verificar retorno das funções
5. **Delays humanos** - use `wait_with_random_delay()` entre ações
6. **Frames e popups** - sempre verificar se foram encontrados antes de usar

---

**Data**: 2025-11-15
**Módulo**: `src/common/wait_utils.py`
