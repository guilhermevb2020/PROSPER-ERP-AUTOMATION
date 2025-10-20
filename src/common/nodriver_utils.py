# =============================================================================================
# ARQUIVO: nodriver_utils.py
# CAMINHO: src/common/nodriver_utils.py
# VERSÃO: v1.0 - ANTI-DETECTION COM NODRIVER (2025)
# AUTOR: Claude Code (migrado de selenium_utils.py)
# DATA: 2025-10-18
# DESCRIÇÃO:
#   Utilitários para automação com Nodriver (successor de undetected-chromedriver).
#   Nodriver elimina CDP (Chrome DevTools Protocol) detectável pelo site.
#   Técnicas: Async nativo, delays randômicos, comportamento humano simulado.
#   Para uso em qualquer processador ETL web do projeto.
# =============================================================================================

# =============================================================================================
# 1.0 IMPORTAÇÕES E CONFIGS INICIAIS
# =============================================================================================
from __future__ import annotations  # IMPORTANTE: Permite type hints sem imports

import os
import asyncio
import random
from pathlib import Path
from typing import Optional, Union

try:
    import nodriver as uc
    from nodriver import cdp, Browser, Tab
    from nodriver.core.element import Element
    NODRIVER_AVAILABLE = True
except ImportError:
    NODRIVER_AVAILABLE = False
    print("[ERROR] Nodriver não instalado. Execute: pip install nodriver")

# =============================================================================================
# 2.0 INICIALIZAÇÃO DO BROWSER (NODRIVER)
# =============================================================================================
async def init_browser(
    download_dir: str,
    headless: bool = False,
    display: str = None,
    user_data_dir: str = None,
    lang: str = "pt-BR"
) -> Browser:
    """
    Inicializa o Browser com Nodriver (anti-detecção nativa).

    Args:
        download_dir (str): Caminho para salvar os downloads (ex: 'data/raw_inputs/')
        headless (bool): Se True, roda sem interface (não recomendado para VNC)
        display (str): Display virtual (ex: ':1' para Xvfb). Se None, usa padrão
        user_data_dir (str): Diretório de perfil do Chrome (None = perfil temporário)
        lang (str): Idioma do navegador (padrão: pt-BR)

    Returns:
        Browser: Instância do navegador Nodriver
    """
    if not NODRIVER_AVAILABLE:
        raise ImportError("Nodriver não está instalado!")

    download_dir_abs = os.path.abspath(download_dir)
    os.makedirs(download_dir_abs, exist_ok=True)

    # Configurar display virtual (Xvfb/VNC)
    if display:
        os.environ['DISPLAY'] = display
        print(f"[NODRIVER] Display configurado: {display}")

    # Verificar se estamos no WSL
    if os.name == 'posix' and os.path.exists('/mnt/c'):
        print(f"[NODRIVER] WSL detectado")
        # Nodriver funciona melhor com caminhos Linux no WSL

    # Configurações do navegador
    browser_args = [
        '--start-maximized',
        '--disable-dev-shm-usage',
        '--no-sandbox',
        '--disable-blink-features=AutomationControlled',
        f'--lang={lang}',
    ]

    # Configurar downloads (via CDP após inicialização)
    print(f"[NODRIVER] Iniciando Chrome com Nodriver...")
    print(f"[NODRIVER] Downloads: {download_dir_abs}")

    if headless:
        print(f"[NODRIVER] ⚠️  Modo headless ativado (pode reduzir eficácia stealth)")

    # Criar configuração
    config = uc.Config(
        headless=headless,
        user_data_dir=user_data_dir,
        browser_args=browser_args,
    )

    # Iniciar browser
    browser = await uc.start(config=config)

    # Configurar downloads via CDP (funciona em todas as tabs)
    try:
        await browser.connection.send(cdp.browser.set_download_behavior(
            behavior="allow",
            download_path=download_dir_abs
        ))
        print(f"[NODRIVER] ✅ Downloads configurados via CDP")
    except Exception as e:
        print(f"[NODRIVER] ⚠️  Erro ao configurar downloads: {e}")

    print(f"[NODRIVER] ✅ Browser inicializado!")

    return browser


# =============================================================================================
# 3.0 ESPERA DE ELEMENTOS NA PÁGINA (COM DELAYS RANDÔMICOS)
# =============================================================================================
async def wait_for_element(
    tab: Tab,
    selector: str,
    timeout: int = 30,
    random_delay: bool = True
) -> Optional[Element]:
    """
    Espera até que o elemento esteja presente no DOM.
    STEALTH: Adiciona delay randômico para simular comportamento humano.

    Args:
        tab: Instância da Tab do Nodriver
        selector: Seletor CSS ou texto do elemento (ex: '#email', 'button.submit')
        timeout: tempo máximo (segundos)
        random_delay: Se True, adiciona delay randômico de 0.5-2s (anti-bot)

    Returns:
        Element: Elemento encontrado ou None se timeout
    """
    # Delay randômico antes de buscar (simula humano)
    if random_delay:
        delay = random.uniform(0.5, 2.0)
        await asyncio.sleep(delay)

    try:
        # Nodriver tem método find() que aguarda automaticamente
        element = await tab.find(selector, timeout=timeout)

        # Delay randômico após encontrar (simula leitura)
        if random_delay:
            delay = random.uniform(0.3, 1.0)
            await asyncio.sleep(delay)

        return element

    except asyncio.TimeoutError:
        print(f"[NODRIVER] ⏱️  Timeout aguardando elemento: {selector}")
        return None
    except Exception as e:
        print(f"[NODRIVER] ❌ Erro ao buscar elemento: {e}")
        return None


# =============================================================================================
# 4.0 AGUARDAR DOWNLOAD DE ARQUIVO
# =============================================================================================
async def wait_for_download(
    download_dir: str,
    filename_contains: str = ".csv",
    timeout: int = 60
) -> Optional[str]:
    """
    Espera até que o arquivo apareça na pasta de downloads.

    Args:
        download_dir (str): Caminho de downloads
        filename_contains (str): Substring para identificar o arquivo
        timeout (int): Segundos máximos

    Returns:
        str: Caminho completo do arquivo baixado ou None se timeout
    """
    start = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start) < timeout:
        for fname in os.listdir(download_dir):
            if filename_contains in fname and not fname.endswith(".crdownload"):
                return os.path.join(download_dir, fname)
        await asyncio.sleep(1)

    print(f"[NODRIVER] ⏱️  Timeout aguardando download: {filename_contains}")
    return None


# =============================================================================================
# 5.0 MOVIMENTO DE MOUSE ALEATÓRIO (STEALTH)
# =============================================================================================
async def random_mouse_movement(tab: Tab):
    """
    Simula movimento aleatório do mouse pela página.
    STEALTH: ERP pode detectar ausência de movimento de mouse.

    NOTA: Nodriver não suporta ActionChains diretamente.
    Alternativa: usar CDP Input.dispatchMouseEvent
    """
    try:
        # Movimento aleatório por 3-5 pontos da tela
        num_movements = random.randint(3, 5)

        # Posição inicial aleatória
        x, y = random.randint(100, 1800), random.randint(100, 900)

        for _ in range(num_movements):
            # Movimento incremental
            x += random.randint(-100, 100)
            y += random.randint(-50, 50)

            # Limitar dentro da tela
            x = max(0, min(1920, x))
            y = max(0, min(1080, y))

            # Enviar evento de movimento via CDP
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mouseMoved",
                x=x,
                y=y
            ))

            await asyncio.sleep(random.uniform(0.1, 0.3))

    except Exception as e:
        pass  # Silencioso - não é crítico


async def scroll_like_human(tab: Tab):
    """
    Simula scroll humano pela página.
    STEALTH: Sites detectam falta de scroll natural.
    """
    try:
        # Scroll suave para baixo
        scroll_amount = random.randint(200, 500)
        await tab.evaluate(f"window.scrollBy({{top: {scroll_amount}, behavior: 'smooth'}});")
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # Às vezes scroll para cima (humanos fazem isso)
        if random.random() < 0.3:  # 30% de chance
            scroll_up = random.randint(50, 150)
            await tab.evaluate(f"window.scrollBy({{top: -{scroll_up}, behavior: 'smooth'}});")
            await asyncio.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass


# =============================================================================================
# 6.0 CLIQUE HUMANO (STEALTH)
# =============================================================================================
async def human_click(
    element: Element,
    delay_before: float = None,
    delay_after: float = None
):
    """
    Simula clique humano com delays randômicos.
    STEALTH: Adiciona pausas antes/depois para parecer mais natural.

    Args:
        element: Element do Nodriver
        delay_before: Delay antes do clique (se None, usa randômico 0.3-1.5s)
        delay_after: Delay depois do clique (se None, usa randômico 0.5-2.0s)
    """
    # Delay antes do clique (simula movimento do mouse até o elemento)
    if delay_before is None:
        delay_before = random.uniform(0.3, 1.5)
    await asyncio.sleep(delay_before)

    # Scroll suave até o elemento (comportamento humano)
    try:
        await element.scroll_into_view()
        await asyncio.sleep(random.uniform(0.2, 0.5))
    except:
        pass

    # Clique
    await element.click()

    # Delay depois do clique (simula espera para página reagir)
    if delay_after is None:
        delay_after = random.uniform(0.5, 2.0)
    await asyncio.sleep(delay_after)


# =============================================================================================
# 7.0 DIGITAÇÃO HUMANA (STEALTH)
# =============================================================================================
async def human_type(element: Element, text: str, wpm: int = 60):
    """
    Simula digitação humana com velocidade variável.
    STEALTH: Digita caractere por caractere com pausas randômicas.

    Args:
        element: Element do Nodriver (input/textarea)
        text: Texto para digitar
        wpm: Palavras por minuto (60 = velocidade média humana)
    """
    # Calcular delay médio entre teclas (em segundos)
    # WPM 60 = 5 caracteres/segundo = 0.2s/caractere
    chars_per_second = (wpm * 5) / 60  # Assumindo 5 caracteres por palavra
    avg_delay = 1.0 / chars_per_second

    # Limpar campo primeiro
    await element.clear_input()
    await asyncio.sleep(random.uniform(0.1, 0.3))

    # Digitar caractere por caractere
    for char in text:
        await element.send_keys(char)
        # Adiciona variação de ±40% no delay
        delay = avg_delay * random.uniform(0.6, 1.4)
        await asyncio.sleep(delay)

    # Pausa após terminar de digitar
    await asyncio.sleep(random.uniform(0.3, 0.8))


# =============================================================================================
# 8.0 SIMULAÇÃO DE ATIVIDADE HUMANA NA PÁGINA
# =============================================================================================
async def simulate_human_activity(tab: Tab, duration: int = 3):
    """
    Simula atividade humana na página por alguns segundos.
    STEALTH: Combina scroll, movimento de mouse e pausas.

    Args:
        tab: Tab instance do Nodriver
        duration: Duração da simulação em segundos (padrão: 3s)
    """
    print(f"[STEALTH] Simulando atividade humana por {duration}s...")

    end_time = asyncio.get_event_loop().time() + duration
    actions_done = 0

    while asyncio.get_event_loop().time() < end_time:
        # Escolher ação aleatória
        action = random.choice(['scroll', 'mouse_move', 'pause'])

        if action == 'scroll':
            await scroll_like_human(tab)
            actions_done += 1
        elif action == 'mouse_move':
            await random_mouse_movement(tab)
            actions_done += 1
        else:  # pause
            await asyncio.sleep(random.uniform(0.5, 1.5))

        # Pequena pausa entre ações
        await asyncio.sleep(random.uniform(0.2, 0.5))

    print(f"[STEALTH] Atividade humana simulada: {actions_done} ações")


# =============================================================================================
# 9.0 FINALIZAÇÃO SEGURA DO BROWSER
# =============================================================================================
async def close_browser(browser: Browser):
    """
    Finaliza o Browser com segurança.
    """
    try:
        await browser.stop()
        print(f"[NODRIVER] ✅ Browser fechado")
    except Exception as e:
        print(f"[NODRIVER] ⚠️  Erro ao fechar browser: {e}")


# =============================================================================================
# 10.0 EXEMPLO DE USO
# =============================================================================================
async def example_usage():
    """
    Exemplo de uso básico do nodriver_utils
    """
    DOWNLOAD_DIR = "data/raw_inputs/"

    # Iniciar browser
    browser = await init_browser(
        download_dir=DOWNLOAD_DIR,
        headless=False,
        display=':1'  # Para Xvfb/VNC
    )

    try:
        # Pegar primeira tab
        tab = await browser.get("https://www.google.com")

        # Aguardar e buscar elemento
        search_box = await wait_for_element(tab, 'textarea[name="q"]', timeout=10)

        if search_box:
            # Digitar como humano
            await human_type(search_box, "Nodriver automation", wpm=80)

            # Simular atividade
            await simulate_human_activity(tab, duration=3)

            print("[EXEMPLO] ✅ Teste concluído!")

    finally:
        await close_browser(browser)


if __name__ == "__main__":
    # Executar exemplo
    asyncio.run(example_usage())
