# =============================================================================================
# ARQUIVO: selenium_utils.py
# CAMINHO: src/common/selenium_utils.py
# VERSÃO: v2.0 - STEALTH MODE (Anti-Detection 2025)
# AUTOR: ChatGPT & Guilherme Veloso
# DATA: 2025-05-20
# DESCRIÇÃO:
#   Utilitários STEALTH para automação com Selenium WebDriver (Chrome).
#   Usa undetected-chromedriver para evitar detecção de bots.
#   Técnicas: WebDriver masking, User-Agent rotation, delays randômicos.
#   Para uso em qualquer processador ETL web do projeto.
# =============================================================================================

# =============================================================================================
# 1.0 IMPORTAÇÕES E CONFIGS INICIAIS
# =============================================================================================
import os
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# STEALTH: Importar bibliotecas anti-detecção
try:
    import undetected_chromedriver as uc
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    uc = None
    print("[WARNING] undetected-chromedriver não instalado. Usando Selenium padrão.")

# SELENIUM-STEALTH: Plugin adicional de evasões
try:
    from selenium_stealth import stealth
    SELENIUM_STEALTH_AVAILABLE = True
except ImportError:
    SELENIUM_STEALTH_AVAILABLE = False
    stealth = None
    print("[WARNING] selenium-stealth não instalado. Algumas evasões não estarão disponíveis.")

# =============================================================================================
# CLASSE CUSTOMIZADA: Previne fechamento prematuro do navegador
# Solução baseada em: https://github.com/ultrafunkamsterdam/undetected-chromedriver/issues/924
# =============================================================================================
if STEALTH_AVAILABLE:
    class UndetectedChrome(uc.Chrome):
        """
        Extensão de undetected_chromedriver.Chrome que previne fechamento automático.
        Override do método __del__ para manter navegador aberto durante execução.
        """
        def __del__(self):
            """
            Destructor customizado que NÃO fecha o navegador automaticamente.
            Permite controle manual do ciclo de vida do driver.
            """
            try:
                # Limpar processos mas NÃO chamar quit()
                if hasattr(self, 'service') and self.service and hasattr(self.service, 'process'):
                    # Process cleanup será feito manualmente via close_driver()
                    pass
            except Exception:
                pass
            # NÃO chamar self.quit() aqui - causa fechamento prematuro
else:
    UndetectedChrome = None

# =============================================================================================
# 2.0 INICIALIZAÇÃO DO WEBDRIVER (CHROME) - MODO STEALTH
# =============================================================================================
def init_driver(download_dir: str, headless: bool = False, driver_path: str = None, stealth: bool = True, use_profile: bool = False, capsolver_extension: bool = False) -> webdriver.Chrome:
    """
    Inicializa o WebDriver do Chrome com MODO STEALTH para evitar detecção de bots.

    Args:
        download_dir (str): Caminho para salvar os downloads (ex: 'data/raw_inputs/')
        headless (bool): Se True, roda sem abrir a janela (NÃO RECOMENDADO com stealth)
        driver_path (str): Caminho para o ChromeDriver (ignorado se stealth=True)
        stealth (bool): Se True, usa undetected-chromedriver (RECOMENDADO)
        use_profile (bool): Se True, usa perfil real do Chrome (MÁXIMA PROTEÇÃO)
        capsolver_extension (bool): Se True, carrega extensão CapSolver para resolver CAPTCHAs automaticamente

    Returns:
        webdriver.Chrome: Instância pronta para uso (stealth ou padrão)
    """
    download_dir_abs = os.path.abspath(download_dir)

    # IMPORTANTE: Converter caminho WSL para Windows se necessário
    # Chrome no Windows NÃO entende caminhos WSL (/home/...)
    if os.name == 'posix' and os.path.exists('/mnt/c'):
        # Estamos no WSL - converter para caminho Windows
        import subprocess
        try:
            # Usar wslpath para converter
            resultado = subprocess.run(['wslpath', '-w', download_dir_abs],
                                      capture_output=True, text=True, check=True)
            download_dir_windows = resultado.stdout.strip()
            print(f"[WSL] Convertendo caminho:")
            print(f"[WSL]   WSL:     {download_dir_abs}")
            print(f"[WSL]   Windows: {download_dir_windows}")
            download_dir_abs = download_dir_windows
        except Exception as e:
            print(f"[WSL] ⚠️ Erro ao converter caminho: {e}")
            print(f"[WSL] Usando caminho original: {download_dir_abs}")

    # Configurar opções de download
    chrome_prefs = {
        "download.default_directory": download_dir_abs,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }

    # =============================================================================================
    # MODO STEALTH: Usar undetected-chromedriver (RECOMENDADO)
    # =============================================================================================
    if stealth and STEALTH_AVAILABLE:
        print("[STEALTH] Usando undetected-chromedriver para evitar detecção...")

        # Opções stealth - SIMPLIFICADAS para compatibilidade
        options = uc.ChromeOptions()

        # =============================================================================================
        # SOLUÇÃO: Carregar extensão CapSolver .CRX (NÃO usar perfil real - causa crashes)
        # =============================================================================================
        # Variáveis para guardar configurações de perfil (usadas no fallback)
        chrome_user_data_para_chrome = None
        profile_com_capsolver = None
        capsolver_extension_path = None

        if use_profile:
            print("[STEALTH] 🔥 Usando perfil REAL do Chrome (com extensões instaladas)")
            print("[STEALTH] ⚠️  IMPORTANTE: FECHE o Chrome completamente antes de rodar!")

            user_home = os.path.expanduser("~")

            # Detectar ambiente
            print(f"[STEALTH] 🔍 Sistema: {os.name}")

            if os.name == 'posix' and os.path.exists('/mnt/c'):
                # WSL
                username = os.path.basename(user_home)
                chrome_user_data = f"/mnt/c/Users/{username}/AppData/Local/Google/Chrome/User Data"
                print(f"[STEALTH] 🐧 WSL detectado - usando Chrome do Windows")
            elif os.name == 'nt':
                # Windows nativo
                chrome_user_data = os.path.join(user_home, "AppData", "Local", "Google", "Chrome", "User Data")
                print(f"[STEALTH] 🪟 Windows detectado")
            else:
                # Linux
                chrome_user_data = os.path.join(user_home, ".config", "google-chrome")
                print(f"[STEALTH] 🐧 Linux detectado")

            print(f"[STEALTH] 📁 Perfil do Chrome: {chrome_user_data}")

            # Verificar qual perfil tem a extensão CapSolver
            capsolver_id = "pgojnojmmhpofjgdmaebadhbocahppod"
            profile_com_capsolver = None

            for profile_name in ["Default", "Profile 1", "Profile 2", "Profile 3"]:
                extensions_dir = os.path.join(chrome_user_data, profile_name, "Extensions")
                capsolver_path = os.path.join(extensions_dir, capsolver_id)

                if os.path.exists(capsolver_path):
                    profile_com_capsolver = profile_name
                    print(f"[STEALTH] ✅ Extensão CapSolver encontrada no perfil: {profile_name}")
                    break

            if not profile_com_capsolver:
                print(f"[STEALTH] ⚠️  Extensão CapSolver NÃO encontrada!")
                print(f"[STEALTH] ℹ️  Instale CapSolver no Chrome e tente novamente")
                profile_com_capsolver = "Default"  # Usar Default como fallback

            # Converter caminho para Windows se necessário
            chrome_user_data_para_chrome = chrome_user_data

            if os.name == 'posix' and os.path.exists('/mnt/c'):
                import subprocess
                try:
                    resultado = subprocess.run(['wslpath', '-w', chrome_user_data],
                                              capture_output=True, text=True, check=True)
                    chrome_user_data_para_chrome = resultado.stdout.strip()
                    print(f"[STEALTH] 📁 Caminho convertido: {chrome_user_data_para_chrome}")
                except:
                    pass

            # Configurar Chrome para usar perfil REAL
            options.add_argument(f"--user-data-dir={chrome_user_data_para_chrome}")
            options.add_argument(f"--profile-directory={profile_com_capsolver}")
            print(f"[STEALTH] ✅ Usando perfil REAL: {profile_com_capsolver}")

        # IMPORTANTE: headless NÃO é recomendado com stealth (facilita detecção)
        if headless:
            print("[WARNING] Headless mode reduz eficácia do stealth!")
            options.add_argument("--headless=new")

        # Configurações básicas MÍNIMAS (menos é mais!)
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")

        # Preferências de download
        options.add_experimental_option("prefs", chrome_prefs)

        # IMPORTANTE: NÃO usar remote-debugging-port quando usa perfil real!
        # Causa conflito e Chrome fecha
        if not use_profile:
            options.add_argument("--remote-debugging-port=9222")

        # =============================================================================================
        # CAPSOLVER EXTENSION: Carregar extensão para resolver CAPTCHAs automaticamente
        # =============================================================================================
        if capsolver_extension:
            print("[CAPSOLVER] 🔧 Carregando extensão CapSolver...")

            # Caminho para a extensão (drivers/capsolver_extension/)
            extension_dir = os.path.join(os.getcwd(), "drivers", "capsolver_extension")

            # Se não existir, baixar da Chrome Web Store
            if not os.path.exists(extension_dir):
                print("[CAPSOLVER] Extensão não encontrada. Baixando...")
                try:
                    import requests
                    import zipfile
                    from io import BytesIO

                    # URL da extensão CapSolver (ID: pgojnojmmhpofjgdmaebadhbocahppod)
                    # Baixar do repositório oficial
                    extension_url = "https://github.com/capsolver/capsolver-extension/releases/latest/download/capsolver.zip"

                    response = requests.get(extension_url, timeout=30)

                    if response.status_code == 200:
                        # Extrair ZIP
                        os.makedirs(extension_dir, exist_ok=True)
                        with zipfile.ZipFile(BytesIO(response.content)) as zip_ref:
                            zip_ref.extractall(extension_dir)
                        print(f"[CAPSOLVER] ✅ Extensão baixada e extraída em: {extension_dir}")
                    else:
                        print(f"[CAPSOLVER] ⚠️ Erro ao baixar extensão (status {response.status_code})")
                        print(f"[CAPSOLVER] Por favor, instale manualmente da Chrome Web Store")
                        capsolver_extension = False

                except Exception as e:
                    print(f"[CAPSOLVER] ⚠️ Erro ao baixar extensão: {e}")
                    print(f"[CAPSOLVER] Alternativa: Use perfil real do Chrome (use_profile=True)")
                    capsolver_extension = False

            # Carregar extensão se existir
            if capsolver_extension and os.path.exists(extension_dir):
                try:
                    options.add_argument(f"--load-extension={extension_dir}")
                    print(f"[CAPSOLVER] ✅ Extensão carregada!")
                    print(f"[CAPSOLVER] ℹ️ Configure a API key após o navegador abrir")
                except Exception as e:
                    print(f"[CAPSOLVER] ⚠️ Erro ao carregar extensão: {e}")

        # Criar driver stealth com configuração corrigida
        try:
            # SOLUÇÃO GITHUB: Usar classe customizada que previne fechamento prematuro
            # version_main=140 para Chrome 140.x
            driver = UndetectedChrome(
                options=options,
                version_main=140,  # FIXO: Chrome 140
                # NÃO usar use_subprocess - causa fechamento prematuro
            )
            print("[STEALTH] ✅ Driver stealth inicializado com sucesso!")
            print("[STEALTH] ℹ️  Usando classe customizada para evitar fechamento automático")
        except Exception as e:
            print(f"[STEALTH] ⚠️  Erro ao criar driver stealth: {e}")
            print("[STEALTH] Tentando modo simplificado...")

            # IMPORTANTE: ChromeOptions não pode ser reutilizado!
            # Precisamos criar um NOVO objeto com as mesmas configurações
            options_fallback = uc.ChromeOptions()

            # Replicar configurações do options original
            if use_profile:
                # Replicar configuração de perfil
                options_fallback.add_argument(f"--user-data-dir={chrome_user_data_para_chrome}")
                options_fallback.add_argument(f"--profile-directory={profile_com_capsolver}")
                print(f"[STEALTH] Perfil recriado no fallback: {profile_com_capsolver}")

            # Replicar outras configurações
            options_fallback.add_argument("--window-size=1920,1080")
            options_fallback.add_argument("--start-maximized")
            options_fallback.add_argument("--disable-dev-shm-usage")
            options_fallback.add_argument("--no-sandbox")
            # NÃO usar remote-debugging-port com perfil real!
            if not use_profile:
                options_fallback.add_argument("--remote-debugging-port=9222")
            options_fallback.add_experimental_option("prefs", chrome_prefs)

            driver = UndetectedChrome(options=options_fallback, version_main=140)
            print("[STEALTH] ✅ Driver stealth (modo simplificado) inicializado!")
            print("[STEALTH] ℹ️  Perfil real MANTIDO no fallback")

        # =============================================================================================
        # EVASÕES CDP MÍNIMAS (só o essencial para não triggerar detecção)
        # =============================================================================================
        print("[STEALTH] Injetando evasões CDP mínimas...")
        try:
            # EVASÃO ÚNICA: Remover navigator.webdriver (undetected-chromedriver já faz o resto)
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            })

            print("[STEALTH] ✅ Evasão CDP injetada!")
        except Exception as e:
            print(f"[STEALTH] ⚠️  Erro ao injetar evasões CDP: {e}")

        return driver

    # =============================================================================================
    # MODO PADRÃO: Selenium tradicional (FALLBACK)
    # =============================================================================================
    else:
        if stealth and not STEALTH_AVAILABLE:
            print("[WARNING] Modo stealth solicitado mas undetected-chromedriver não disponível!")

        print("[PADRÃO] Usando Selenium WebDriver padrão...")

        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_experimental_option("prefs", chrome_prefs)

        if driver_path:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)

        return driver

# =============================================================================================
# 3.0 ESPERA DE ELEMENTOS NA PÁGINA (COM DELAYS RANDÔMICOS)
# =============================================================================================
def wait_for_element(driver, by_type, value, timeout=30, random_delay: bool = True):
    """
    Espera até que o elemento esteja presente no DOM.
    STEALTH: Adiciona delay randômico para simular comportamento humano.

    Args:
        driver: Instância do WebDriver
        by_type: selenium.webdriver.common.by.By (ex: By.XPATH)
        value: string do seletor (ex: '//button[@id="btn"]')
        timeout: tempo máximo (segundos)
        random_delay: Se True, adiciona delay randômico de 0.5-2s (anti-bot)

    Returns:
        WebElement: Elemento encontrado

    Raises:
        TimeoutException: se não achar o elemento em timeout
    """
    # Delay randômico antes de buscar (simula humano)
    if random_delay:
        delay = random.uniform(0.5, 2.0)
        time.sleep(delay)

    element = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by_type, value))
    )

    # Delay randômico após encontrar (simula leitura)
    if random_delay:
        delay = random.uniform(0.3, 1.0)
        time.sleep(delay)

    return element

# =============================================================================================
# 4.0 INJEÇÃO DO TOKEN reCAPTCHA NA PÁGINA
# =============================================================================================
def inject_recaptcha_token(driver, token: str, element_id: str = "g-recaptcha-response"):
    """
    Injeta o token do g-recaptcha-response no elemento escondido do formulário.
    Args:
        driver: Instância do WebDriver
        token: Token resolvido pela Anti-Captcha
        element_id: ID do textarea do reCAPTCHA
    """
    script = f"document.getElementById('{element_id}').style.display = '';"
    script += f"document.getElementById('{element_id}').value = '{token}';"
    script += f"document.getElementById('{element_id}').style.display = 'none';"
    driver.execute_script(script)

# =============================================================================================
# 5.0 ESPERAR O DOWNLOAD DO CSV
# =============================================================================================
def wait_for_download(download_dir: str, filename_contains: str = ".csv", timeout: int = 60):
    """
    Espera até que o arquivo .csv apareça na pasta de downloads.
    Args:
        download_dir (str): Caminho de downloads
        filename_contains (str): Substring para identificar o arquivo
        timeout (int): Segundos máximos
    Returns:
        str: Caminho completo do arquivo baixado
    Raises:
        TimeoutError: se não encontrar arquivo no tempo
    """
    start = time.time()
    while time.time() - start < timeout:
        for fname in os.listdir(download_dir):
            if filename_contains in fname and not fname.endswith(".crdownload"):
                return os.path.join(download_dir, fname)
        time.sleep(1)
    raise TimeoutError("Download do CSV não concluído no tempo esperado.")

# =============================================================================================
# 6.0 LOGIN AUTOMATIZADO (EXEMPLO PADRÃO)
# =============================================================================================
def perform_login(driver, login_url, username, password, username_field_id, password_field_id, submit_button_xpath):
    """
    Realiza login automatizado em páginas padrão.
    Args:
        driver: Instância do WebDriver
        login_url: URL da página de login
        username: Usuário
        password: Senha
        username_field_id: ID do campo usuário
        password_field_id: ID do campo senha
        submit_button_xpath: XPATH do botão submit
    """
    driver.get(login_url)
    wait_for_element(driver, By.ID, username_field_id).send_keys(username)
    wait_for_element(driver, By.ID, password_field_id).send_keys(password)
    wait_for_element(driver, By.XPATH, submit_button_xpath).click()

# =============================================================================================
# 7.0 MOVIMENTO DE MOUSE ALEATÓRIO (STEALTH - ANTI-BOT 2025)
# =============================================================================================
def random_mouse_movement(driver):
    """
    Simula movimento aleatório do mouse pela página.
    STEALTH: ERP pode detectar ausência de movimento de mouse.
    """
    try:
        from selenium.webdriver.common.action_chains import ActionChains

        # Movimento aleatório por 3-5 pontos da tela
        num_movements = random.randint(3, 5)
        actions = ActionChains(driver)

        for _ in range(num_movements):
            x_offset = random.randint(-100, 100)
            y_offset = random.randint(-50, 50)
            actions.move_by_offset(x_offset, y_offset)
            actions.pause(random.uniform(0.1, 0.3))

        actions.perform()
    except Exception as e:
        pass  # Silencioso - não é crítico

def scroll_like_human(driver):
    """
    Simula scroll humano pela página.
    STEALTH: Sites detectam falta de scroll natural.
    """
    try:
        # Scroll suave para baixo
        scroll_amount = random.randint(200, 500)
        driver.execute_script(f"window.scrollBy({{top: {scroll_amount}, behavior: 'smooth'}});")
        time.sleep(random.uniform(0.5, 1.5))

        # Às vezes scroll para cima (humanos fazem isso)
        if random.random() < 0.3:  # 30% de chance
            scroll_up = random.randint(50, 150)
            driver.execute_script(f"window.scrollBy({{top: -{scroll_up}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass

# =============================================================================================
# 8.0 CLIQUE HUMANO (STEALTH)
# =============================================================================================
def human_click(element, delay_before: float = None, delay_after: float = None):
    """
    Simula clique humano com delays randômicos.
    STEALTH: Adiciona pausas antes/depois para parecer mais natural.

    Args:
        element: WebElement do Selenium
        delay_before: Delay antes do clique (se None, usa randômico 0.3-1.5s)
        delay_after: Delay depois do clique (se None, usa randômico 0.5-2.0s)
    """
    # Delay antes do clique (simula movimento do mouse até o elemento)
    if delay_before is None:
        delay_before = random.uniform(0.3, 1.5)
    time.sleep(delay_before)

    # Scroll suave até o elemento (comportamento humano)
    try:
        element.parent.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(random.uniform(0.2, 0.5))
    except:
        pass

    # Clique
    element.click()

    # Delay depois do clique (simula espera para página reagir)
    if delay_after is None:
        delay_after = random.uniform(0.5, 2.0)
    time.sleep(delay_after)

# =============================================================================================
# 8.0 DIGITAÇÃO HUMANA (STEALTH)
# =============================================================================================
def human_type(element, text: str, wpm: int = 60):
    """
    Simula digitação humana com velocidade variável.
    STEALTH: Digita caractere por caractere com pausas randômicas.

    Args:
        element: WebElement do Selenium (input/textarea)
        text: Texto para digitar
        wpm: Palavras por minuto (60 = velocidade média humana)
    """
    # Calcular delay médio entre teclas (em segundos)
    # WPM 60 = 5 caracteres/segundo = 0.2s/caractere
    chars_per_second = (wpm * 5) / 60  # Assumindo 5 caracteres por palavra
    avg_delay = 1.0 / chars_per_second

    element.clear()
    time.sleep(random.uniform(0.1, 0.3))

    for char in text:
        element.send_keys(char)
        # Adiciona variação de ±40% no delay
        delay = avg_delay * random.uniform(0.6, 1.4)
        time.sleep(delay)

    # Pausa após terminar de digitar
    time.sleep(random.uniform(0.3, 0.8))

# =============================================================================================
# 10.0 SIMULAÇÃO DE ATIVIDADE HUMANA NA PÁGINA
# =============================================================================================
def simulate_human_activity(driver, duration: int = 3):
    """
    Simula atividade humana na página por alguns segundos.
    STEALTH: Combina scroll, movimento de mouse e pausas.

    Args:
        driver: WebDriver instance
        duration: Duração da simulação em segundos (padrão: 3s)
    """
    print(f"[STEALTH] Simulando atividade humana por {duration}s...")

    end_time = time.time() + duration
    actions_done = 0

    while time.time() < end_time:
        # Escolher ação aleatória
        action = random.choice(['scroll', 'mouse_move', 'pause'])

        if action == 'scroll':
            scroll_like_human(driver)
            actions_done += 1
        elif action == 'mouse_move':
            random_mouse_movement(driver)
            actions_done += 1
        else:  # pause
            time.sleep(random.uniform(0.5, 1.5))

        # Pequena pausa entre ações
        time.sleep(random.uniform(0.2, 0.5))

    print(f"[STEALTH] Atividade humana simulada: {actions_done} ações")

# =============================================================================================
# 11.0 FINALIZAÇÃO SEGURA DO DRIVER
# =============================================================================================
def close_driver(driver):
    """
    Finaliza o WebDriver com segurança.
    """
    try:
        driver.quit()
    except Exception:
        pass

# =============================================================================================
# 8.0 EXEMPLO DE USO
# =============================================================================================
if __name__ == "__main__":
    # Exemplo de uso (ajuste para seu cenário)
    DOWNLOAD_DIR = "data/raw_inputs/"
    DRIVER_PATH = None  # Ou caminho absoluto do chromedriver
    driver = init_driver(download_dir=DOWNLOAD_DIR, headless=False, driver_path=DRIVER_PATH)
    try:
        driver.get("https://www.google.com")
        print("Driver iniciado e página carregada!")
    finally:
        close_driver(driver)
