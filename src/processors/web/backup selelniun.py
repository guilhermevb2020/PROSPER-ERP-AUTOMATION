# =============================================================================================
# ARQUIVO: titulos_abertos_e_marcados_recompras.py
# VERSÃO: v24.0 - LOGIN AUTO + CAPSOLVER CLASSIFICATION (IA CLICA NAS IMAGENS REAIS!)
# SOLUÇÃO DEFINITIVA: CapSolver IA identifica imagens + código CLICA nas células corretas
# =============================================================================================

import os
import sys
import time
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchFrameException, NoSuchElementException
from src.common.selenium_utils import init_driver, wait_for_element, close_driver
from src.core.logging_config import get_logger
from src.common.timezone_utils import now_br

# CapSolver API (substitui AntiCaptcha)
try:
    import capsolver
    CAPSOLVER_AVAILABLE = True
except ImportError:
    CAPSOLVER_AVAILABLE = False
    print("⚠️ Biblioteca capsolver não instalada. Execute: pip install capsolver")

# Carregar variáveis de ambiente
load_dotenv()

logger = get_logger(__name__)

URL_LOGIN = "https://www.smartsecurities.com.br/smartsecurities/"
DOWNLOAD_DIR = "data/raw_inputs/"
TIMEOUT_CARREGAMENTO = 30

# Credenciais do .env
SMART_EMAIL = os.getenv("SMART_EMAIL")
SMART_PASSWORD = os.getenv("SMART_PASSWORD")
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY")

class ProcessadorTitulosAbertosEMarcadosRecompras:
    def __init__(self):
        self.nome = "titulos_abertos_e_marcados_recompras"
        self.driver = None
        self.download_dir = os.path.abspath(DOWNLOAD_DIR)

        # Controles de execução
        self.pausado = False
        self.parar = False
        self.listener_thread = None
        self.ultima_tecla_tempo = 0  # Debounce para evitar múltiplas leituras

        # Contador de erros de CAPTCHA (para abordagem híbrida)
        self.captcha_errors = 0

    def escutar_teclado(self):
        """Thread que escuta comandos do teclado"""
        print(f"\n{'='*80}")
        print("CONTROLES DE EXECUÇÃO:")
        print("  [P] - PAUSAR execução")
        print("  [R] - RETOMAR execução")
        print("  [Q] - PARAR completamente")
        print(f"{'='*80}\n")

        while not self.parar:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    if msvcrt.kbhit():
                        tecla = msvcrt.getch().decode('utf-8').upper()
                        self.processar_comando(tecla)
                else:
                    # Linux/Mac - modo não-blocking
                    import select
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        tecla = sys.stdin.read(1).upper()
                        self.processar_comando(tecla)
                time.sleep(0.1)
            except Exception as e:
                # Silenciar erros de leitura de teclado
                pass

    def processar_comando(self, tecla):
        """Processa comandos do teclado"""
        # Debounce: ignorar se a última tecla foi há menos de 0.5s
        tempo_atual = time.time()
        if tempo_atual - self.ultima_tecla_tempo < 0.5:
            return
        self.ultima_tecla_tempo = tempo_atual

        if tecla == 'P':
            if not self.pausado:
                self.pausado = True
                print(f"\n{'='*80}")
                print("⏸️  EXECUÇÃO PAUSADA!")
                print("Pressione [R] para retomar ou [Q] para parar")
                print(f"{'='*80}\n")
                logger.info(f"[{self.nome}] ⏸️ Execução pausada pelo usuário")

        elif tecla == 'R':
            if self.pausado:
                self.pausado = False
                print(f"\n{'='*80}")
                print("▶️  EXECUÇÃO RETOMADA!")
                print(f"{'='*80}\n")
                logger.info(f"[{self.nome}] ▶️ Execução retomada pelo usuário")

        elif tecla == 'Q':
            self.parar = True
            print(f"\n{'='*80}")
            print("⏹️  PARANDO EXECUÇÃO...")
            print(f"{'='*80}\n")
            logger.info(f"[{self.nome}] ⏹️ Parada solicitada pelo usuário")

    def verificar_pausa(self):
        """Verifica se está pausado e aguarda"""
        while self.pausado and not self.parar:
            time.sleep(0.2)  # Verificar a cada 200ms se foi retomado

    def iniciar_navegador(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        print(f"\n[DEBUG] Iniciando navegador...")
        logger.info(f"[{self.nome}] Iniciando navegador...")
        os.makedirs(self.download_dir, exist_ok=True)

        print(f"[CHROME] Abrindo Chrome...")

        chrome_options = Options()

        # Configurações anti-detecção
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Configurar downloads
        download_prefs = {
            "download.default_directory": os.path.abspath(self.download_dir),
            "download.prompt_for_download": False,
        }
        chrome_options.add_experimental_option("prefs", download_prefs)

        print(f"[CHROME] Downloads vão para: {self.download_dir}")

        self.driver = webdriver.Chrome(options=chrome_options)

        print(f"[CHROME] ✅ Chrome aberto!")

        # Abrir página da extensão CapSolver na Chrome Web Store
        capsolver_url = "https://chromewebstore.google.com/detail/captcha-solver-auto-captc/pgojnojmmhpofjgdmaebadhbocahppod?hl=pt-BR"
        print(f"\n[EXTENSÃO] Abrindo página da extensão CapSolver...")
        self.driver.get(capsolver_url)

        print(f"\n{'='*80}")
        print(f"[EXTENSÃO] ⚠️  AÇÃO NECESSÁRIA: INSTALE A EXTENSÃO CAPSOLVER")
        print(f"{'='*80}")
        print(f"")
        print(f"1. Clique no botão 'Usar no Chrome' na página que abriu")
        print(f"2. Confirme a instalação da extensão")
        print(f"3. Configure a API Key da CapSolver (se necessário)")
        print(f"4. Após instalar, pressione 'R' e ENTER para continuar...")
        print(f"")
        print(f"{'='*80}")

        # Aguardar usuário pressionar 'R'
        while True:
            resposta = input("\nPressione 'R' e ENTER após instalar a extensão: ").strip().upper()
            if resposta == 'R':
                break
            else:
                print("⚠️ Pressione 'R' para continuar...")

        print(f"\n[CHROME] ✅ Continuando...")
        print(f"[NAVEGADOR] Navegando para SmartSecurities: {URL_LOGIN}")

        self.driver.get(URL_LOGIN)

        print(f"[NAVEGADOR] ✅ Navegador aberto em: {URL_LOGIN}")
        print(f"[NAVEGADOR] Aguardando página carregar...")
        time.sleep(3)
        print(f"[NAVEGADOR] ✅ Página carregada!")

        logger.info(f"[{self.nome}] ✅ Navegador aberto e extensão instalada manualmente")

    def aguardar_extensao_resolver_captcha_login(self):
        """
        Aguarda extensão CapSolver resolver reCAPTCHA no login (ABORDAGEM HÍBRIDA)

        IMPORTANTE: reCAPTCHA JÁ ESTÁ VISÍVEL após clicar "Entrar"

        Fluxo CORRETO:
        1. reCAPTCHA checkbox já está visível
        2. **CÓDIGO CLICA** no checkbox "Não sou um robô"
        3. Google abre desafio de imagens
        4. **EXTENSÃO RESOLVE** as imagens automaticamente
        5. Verificar se botão "Acessar" ficou visível
        6. Se falhar → PAUSA e pede resolução manual

        Returns:
            bool: True se resolvido, False se falhou
        """

        print(f"\n[CAPTCHA] reCAPTCHA detectado após clicar 'Entrar'")

        # ============================================================
        # PASSO 1: CLICAR no checkbox "Não sou um robô"
        # ============================================================
        print(f"[CAPTCHA] Procurando checkbox 'Não sou um robô'...")

        try:
            # Aguardar checkbox aparecer (max 5s)
            time.sleep(2)

            # Procurar iframe do reCAPTCHA
            iframe_recaptcha = self.driver.find_element(By.XPATH, "//iframe[contains(@src, 'recaptcha')]")
            print(f"[CAPTCHA] ✅ Iframe reCAPTCHA encontrado!")

            # Entrar no iframe do reCAPTCHA
            self.driver.switch_to.frame(iframe_recaptcha)
            print(f"[CAPTCHA] Contexto mudado para iframe reCAPTCHA")

            # Procurar o checkbox
            checkbox = self.driver.find_element(By.CLASS_NAME, "recaptcha-checkbox-border")
            print(f"[CAPTCHA] ✅ Checkbox encontrado!")

            # CLICAR no checkbox
            print(f"[CAPTCHA] Clicando em 'Não sou um robô'...")
            checkbox.click()
            print(f"[CAPTCHA] ✅ Checkbox clicado!")

            # Voltar para o contexto do iframe de login
            self.driver.switch_to.parent_frame()

            # Aguardar desafio de imagens aparecer (se necessário)
            print(f"[CAPTCHA] Aguardando desafio de imagens aparecer...")
            time.sleep(3)

        except Exception as e:
            print(f"[CAPTCHA] ⚠️ Erro ao clicar no checkbox: {e}")
            print(f"[CAPTCHA] Continuando para aguardar extensão...")

        # ============================================================
        # PASSO 2: AGUARDAR extensão CapSolver resolver imagens
        # ============================================================
        print(f"[CAPTCHA] ⏳ Aguardando extensão CapSolver resolver desafio...")
        print(f"[CAPTCHA] (Máximo 30 segundos)")

        # PASSO 1: Aguardar extensão resolver (max 30s)
        # Verificar se botão "Acessar" ficou visível
        resolvido = False

        for tentativa in range(30):
            time.sleep(1)

            # Verificar se botão "Acessar" ficou visível
            try:
                botao_acessar = self.driver.find_element(By.ID, "OKExtra")
                estilo = botao_acessar.get_attribute("style")

                # Se botão está com display: inline → CAPTCHA resolvido!
                if "display: inline" in estilo or "display:inline" in estilo:
                    print(f"[CAPTCHA] ✅ RESOLVIDO pela extensão em {tentativa + 1}s!")
                    resolvido = True
                    break

            except NoSuchElementException:
                pass  # Botão ainda não apareceu

            # Feedback visual a cada 5s
            if (tentativa + 1) % 5 == 0:
                print(f"[CAPTCHA] ⏳ Aguardando... ({tentativa + 1}s)")

            # Verificar se usuário pausou
            self.verificar_pausa()

            # Verificar se usuário pediu para parar
            if self.parar:
                return False

        # PASSO 2: Se extensão NÃO resolveu → Fallback manual
        if not resolvido:
            print(f"\n{'='*80}")
            print(f"⚠️  CAPTCHA NÃO RESOLVIDO AUTOMATICAMENTE")
            print(f"⚠️  Extensão CapSolver não resolveu em 30 segundos")
            print(f"")
            print(f"📋 AÇÕES NECESSÁRIAS:")
            print(f"   1. Resolva o CAPTCHA MANUALMENTE no navegador")
            print(f"   2. Aguarde o botão 'Acessar' aparecer")
            print(f"   3. Pressione [R] aqui para RETOMAR a execução")
            print(f"")
            print(f"💡 DICA: Verifique se a extensão CapSolver está:")
            print(f"   - Instalada e ativa (chrome://extensions)")
            print(f"   - Configurada com a API key correta")
            print(f"   - Com 'Auto Solve' ATIVADO")
            print(f"   - Com 'reCAPTCHA v2 Classification' ATIVADO")
            print(f"{'='*80}\n")

            # Incrementar contador de falhas
            self.captcha_errors += 1

            # Se falhou 3+ vezes → avisar problema de configuração
            if self.captcha_errors >= 3:
                print(f"")
                print(f"🔧 ATENÇÃO: Extensão falhou {self.captcha_errors}x seguidas!")
                print(f"   Possível problema de configuração.")
                print(f"   Teste em: https://www.google.com/recaptcha/api2/demo")
                print(f"")

            # PAUSAR execução (NÃO fechar navegador!)
            self.pausado = True
            logger.warning(f"[{self.nome}] CAPTCHA não resolvido, pausando para intervenção manual")

            # Aguardar usuário resolver e pressionar R
            print(f"[CONTROLE] Aguardando você pressionar [R] para retomar...")
            while self.pausado and not self.parar:
                time.sleep(0.5)

            # Se usuário pediu para parar
            if self.parar:
                return False

            # Verificar se usuário resolveu
            try:
                botao_acessar = self.driver.find_element(By.ID, "OKExtra")
                estilo = botao_acessar.get_attribute("style")

                if "display: inline" in estilo or "display:inline" in estilo:
                    print(f"[CAPTCHA] ✅ RESOLVIDO manualmente!")
                    resolvido = True
                else:
                    print(f"[CAPTCHA] ⚠️  Botão 'Acessar' ainda não está visível")
                    print(f"[CAPTCHA] Verifique se CAPTCHA foi realmente resolvido")
                    return False
            except NoSuchElementException:
                print(f"[CAPTCHA] ⚠️  Botão 'Acessar' não encontrado")
                return False

        return resolvido

    def clicar_botao_acessar_login(self):
        """
        Clica no botão "Acessar" (id='OKExtra') após CAPTCHA resolvido

        IMPORTANTE: Este botão está DENTRO do iframe de login!
        Só fica visível (display: inline) após CAPTCHA ser resolvido
        """

        print(f"\n[LOGIN] Clicando no botão 'Acessar'...")

        try:
            # Procurar botão por múltiplas estratégias
            botao_acessar = None

            # Tentativa 1: Por ID
            try:
                botao_acessar = self.driver.find_element(By.ID, "OKExtra")
                print(f"[LOGIN] ✅ Botão 'Acessar' encontrado por ID!")
            except NoSuchElementException:
                # Tentativa 2: Por NAME
                try:
                    botao_acessar = self.driver.find_element(By.NAME, "OKExtra")
                    print(f"[LOGIN] ✅ Botão 'Acessar' encontrado por NAME!")
                except NoSuchElementException:
                    # Tentativa 3: Por texto
                    botao_acessar = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Acessar')]")
                    print(f"[LOGIN] ✅ Botão 'Acessar' encontrado por XPATH!")

            if botao_acessar:
                # Verificar se está realmente visível
                estilo = botao_acessar.get_attribute("style")
                print(f"[LOGIN] Estilo do botão: {estilo}")

                if "display: none" in estilo:
                    raise Exception("Botão 'Acessar' ainda está oculto! CAPTCHA pode não ter sido resolvido.")

                # Clicar no botão
                print(f"[LOGIN] Clicando no botão 'Acessar'...")
                botao_acessar.click()
                print(f"[LOGIN] ✅ Botão clicado!")

                # Aguardar login processar
                print(f"[LOGIN] Aguardando login completar...")
                time.sleep(5)

                return True

        except Exception as e:
            print(f"[LOGIN] ❌ Erro ao clicar no botão 'Acessar': {e}")
            raise

    def fazer_login_automatico(self):
        """Faz login automático usando credenciais do .env"""
        self.verificar_pausa()

        print(f"\n{'='*80}")
        print("🔐 REALIZANDO LOGIN AUTOMÁTICO")
        print(f"{'='*80}\n")
        logger.info(f"[{self.nome}] Iniciando login automático...")

        try:
            # Verificar se as credenciais estão disponíveis
            if not SMART_EMAIL or not SMART_PASSWORD:
                raise Exception("Credenciais não encontradas no .env (SMART_EMAIL ou SMART_PASSWORD)")

            print(f"[DEBUG] Email: {SMART_EMAIL}")
            print(f"[DEBUG] Senha: {'*' * len(SMART_PASSWORD)}")

            # IMPORTANTE: Os campos de login estão dentro de um iframe!
            print(f"\n[DEBUG] Procurando iframe de login...")
            time.sleep(3)  # Aguardar página carregar completamente

            # Tentar encontrar o iframe de login
            iframe_login = None
            try:
                # Tentativa 1: Por src contendo 'loginsec.php'
                iframe_login = self.driver.find_element(By.XPATH, "//iframe[contains(@src, 'loginsec.php')]")
                print(f"[DEBUG] ✅ Iframe encontrado por src='loginsec.php'")
            except NoSuchElementException:
                try:
                    # Tentativa 2: Primeiro iframe da página
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    if len(iframes) > 0:
                        iframe_login = iframes[0]
                        print(f"[DEBUG] ✅ Usando primeiro iframe da página")
                except:
                    pass

            if iframe_login:
                print(f"[DEBUG] Mudando contexto para iframe de login...")
                self.driver.switch_to.frame(iframe_login)
                time.sleep(2)
                print(f"[DEBUG] ✅ Contexto mudado para iframe")
            else:
                print(f"[DEBUG] ⚠️ Iframe não encontrado, tentando no contexto principal...")

            # PASSO 1: Preencher campo de email
            print(f"\n[DEBUG] Procurando campo de email (id='fEmail')...")
            try:
                campo_email = self.driver.find_element(By.ID, "fEmail")
                print(f"[DEBUG] ✅ Campo de email encontrado!")
            except NoSuchElementException:
                campo_email = self.driver.find_element(By.NAME, "fEmail")
                print(f"[DEBUG] ✅ Campo de email encontrado por NAME!")

            campo_email.clear()
            campo_email.send_keys(SMART_EMAIL)
            print(f"[DEBUG] ✅ Email preenchido")
            time.sleep(1)
            self.verificar_pausa()

            # PASSO 2: Preencher campo de senha
            print(f"\n[DEBUG] Procurando campo de senha (id='fPassword')...")
            try:
                campo_senha = self.driver.find_element(By.ID, "fPassword")
                print(f"[DEBUG] ✅ Campo de senha encontrado!")
            except NoSuchElementException:
                campo_senha = self.driver.find_element(By.NAME, "fPassword")
                print(f"[DEBUG] ✅ Campo de senha encontrado por NAME!")

            campo_senha.clear()
            campo_senha.send_keys(SMART_PASSWORD)
            print(f"[DEBUG] ✅ Senha preenchida")
            time.sleep(1)
            self.verificar_pausa()

            # PASSO 3: Clicar no botão "Entrar"
            print(f"\n[DEBUG] Procurando botão 'Entrar' (id='OK')...")
            botao_entrar = None

            try:
                botao_entrar = self.driver.find_element(By.ID, "OK")
                print(f"[DEBUG] ✅ Botão encontrado por ID!")
            except NoSuchElementException:
                try:
                    botao_entrar = self.driver.find_element(By.NAME, "OK")
                    print(f"[DEBUG] ✅ Botão encontrado por NAME!")
                except NoSuchElementException:
                    botao_entrar = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Entrar')]")
                    print(f"[DEBUG] ✅ Botão encontrado por XPath!")

            if botao_entrar:
                print(f"[DEBUG] Clicando no botão 'Entrar'...")
                botao_entrar.click()
                print(f"[DEBUG] ✅ Botão clicado!")

                # Aguardar 1s para reCAPTCHA carregar (já está visível!)
                print(f"\n[DEBUG] Aguardando reCAPTCHA carregar...")
                time.sleep(1)
                self.verificar_pausa()

                # ============================================================
                # NOVO: Aguardar extensão CapSolver resolver CAPTCHA (HÍBRIDO)
                # ============================================================
                captcha_resolvido = self.aguardar_extensao_resolver_captcha_login()

                if not captcha_resolvido:
                    raise Exception("CAPTCHA não foi resolvido")

                # ============================================================
                # NOVO: Clicar botão "Acessar" (após CAPTCHA)
                # ============================================================
                self.clicar_botao_acessar_login()

                # Voltar para contexto principal após login
                print(f"\n[DEBUG] Voltando para contexto principal...")
                self.driver.switch_to.default_content()
                time.sleep(2)

                print(f"\n{'='*80}")
                print("✅ LOGIN REALIZADO COM SUCESSO!")
                print(f"{'='*80}\n")
                logger.info(f"[{self.nome}] ✅ Login automático realizado")

                return True

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ ERRO NO LOGIN AUTOMÁTICO: {e}")
            print("Você pode fazer login manualmente no navegador")
            print(f"{'='*80}\n")
            logger.error(f"[{self.nome}] ❌ Erro no login automático: {e}")

            # Voltar para contexto principal em caso de erro
            try:
                self.driver.switch_to.default_content()
            except:
                pass

            # Fallback para login manual
            print("\n" + "="*80)
            print("⏸️  FAÇA LOGIN MANUALMENTE NO NAVEGADOR")
            print("⏸️  Depois pressione ENTER aqui para continuar...")
            print("="*80 + "\n")
            input(">>> Pressione ENTER quando terminar o login >>> ")
            print(f"\n[DEBUG] ENTER pressionado! Continuando automação...\n")
            time.sleep(3)

            return True

    def navegar_para_titulos_abertos(self):
        """Usa JavaScript para carregar a página no frame 'code'"""
        self.verificar_pausa()  # Verificar pausa antes de iniciar

        print(f"\n[DEBUG] ========== CARREGANDO TÍTULOS EM ABERTO ==========")
        logger.info(f"[{self.nome}] Carregando títulos em aberto...")

        url_titulos = "https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php"

        try:
            print(f"[DEBUG] Carregando página via JavaScript no frame 'code'...")
            script = f"document.getElementById('code').src = '{url_titulos}';"
            self.driver.execute_script(script)

            print(f"[DEBUG] Aguardando página carregar...")
            time.sleep(5)
            self.verificar_pausa()  # Verificar pausa após carregar

            print(f"[DEBUG] ✅ Página carregada no frame")

        except Exception as e:
            print(f"[DEBUG] ⚠️ Erro ao carregar via JavaScript: {e}")

    def mudar_para_frame_code(self):
        """Muda o contexto para o frame 'code' e depois para o frame interno 'text'"""
        self.verificar_pausa()  # Verificar pausa antes de iniciar

        print(f"\n[DEBUG] ========== MUDANDO PARA FRAMES ==========")
        logger.info(f"[{self.nome}] Mudando para frames...")

        try:
            # PASSO 1: Voltar para o contexto principal
            self.driver.switch_to.default_content()
            print(f"[DEBUG] ✅ Voltou para contexto principal")

            # PASSO 2: Mudar para o frame 'code'
            print(f"[DEBUG] Mudando para frame 'code'...")
            self.driver.switch_to.frame("code")
            print(f"[DEBUG] ✅ Contexto mudado para frame 'code'")
            time.sleep(3)
            self.verificar_pausa()  # Verificar pausa após mudança
            
            # PASSO 3: Verificar se há frameset/frame dentro
            print(f"[DEBUG] Verificando frames internos...")
            
            # Tentar encontrar o frame "text" dentro do frame "code"
            try:
                print(f"[DEBUG] Tentando mudar para frame 'text'...")
                self.driver.switch_to.frame("text")
                print(f"[DEBUG] ✅ Contexto mudado para frame 'text'")
                time.sleep(2)
            except NoSuchFrameException:
                print(f"[DEBUG] Frame 'text' não encontrado por name, tentando outras formas...")
                
                # Se não encontrou por name, tenta iframes e frames
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                frames = self.driver.find_elements(By.TAG_NAME, "frame")
                
                print(f"[DEBUG] Iframes encontrados: {len(iframes)}")
                print(f"[DEBUG] Frames encontrados: {len(frames)}")
                
                # Tentar frames primeiro (mais provável em framesets antigos)
                if len(frames) > 0:
                    for i, frame in enumerate(frames):
                        src = frame.get_attribute("src") or ""
                        name = frame.get_attribute("name") or ""
                        print(f"[DEBUG]   Frame {i}: name='{name}' src='{src[:60]}'")
                        
                        if "titulosemaberto" in src or name == "text":
                            print(f"[DEBUG] Mudando para frame {i} (name='{name}')...")
                            self.driver.switch_to.frame(frame)
                            print(f"[DEBUG] ✅ Contexto mudado!")
                            time.sleep(2)
                            return
                    
                    # Se não encontrou específico, tenta o primeiro
                    print(f"[DEBUG] Frame específico não encontrado, usando primeiro frame...")
                    self.driver.switch_to.frame(frames[0])
                    print(f"[DEBUG] ✅ Usando frame[0]")
                    time.sleep(2)
                
                # Se não há frames, tenta iframes
                elif len(iframes) > 0:
                    print(f"[DEBUG] Mudando para primeiro iframe...")
                    self.driver.switch_to.frame(iframes[0])
                    time.sleep(2)
            
            # VERIFICAÇÃO FINAL: Listar inputs disponíveis
            print(f"\n[DEBUG] VERIFICAÇÃO: Listando inputs no contexto atual...")
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            print(f"[DEBUG] Total de inputs encontrados: {len(inputs)}")
            
            if len(inputs) == 0:
                print(f"[DEBUG] ⚠️ NENHUM INPUT ENCONTRADO! Pode estar no contexto errado.")
                
                # Salvar HTML do contexto atual
                try:
                    html_contexto = f"logs/erros/web/contexto_frame_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                    os.makedirs("logs/erros/web", exist_ok=True)
                    with open(html_contexto, 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    print(f"[DEBUG] HTML do contexto salvo em: {html_contexto}")
                except:
                    pass
            
        except Exception as e:
            print(f"[DEBUG] ❌ Erro ao mudar para frames: {e}")
            raise

    def preencher_datas(self):
        self.verificar_pausa()  # Verificar pausa antes de iniciar

        data_atual = datetime.now()
        data_inicial = data_atual - timedelta(days=365)
        data_inicial_str = data_inicial.strftime("%d/%m/%Y")
        data_final_str = data_atual.strftime("%d/%m/%Y")

        print(f"\n[DEBUG] ========== PREENCHENDO DATAS ==========")
        print(f"[DEBUG] Data inicial (1 ano atrás): {data_inicial_str}")
        print(f"[DEBUG] Data final (hoje): {data_final_str}")
        logger.info(f"[{self.nome}] Preenchendo datas...")
        
        try:
            # CAMPO DATA INICIAL - Emissao1
            print(f"\n[DEBUG] Procurando campo 'Emissao1'...")
            
            # Tentar por ID primeiro
            try:
                campo_inicial = self.driver.find_element(By.ID, "Emissao1")
                print(f"[DEBUG] ✅ Campo 'Emissao1' encontrado por ID!")
            except NoSuchElementException:
                # Tentar por NAME
                try:
                    campo_inicial = self.driver.find_element(By.NAME, "Emissao1")
                    print(f"[DEBUG] ✅ Campo 'Emissao1' encontrado por NAME!")
                except NoSuchElementException:
                    # Tentar XPATH mais amplo
                    campo_inicial = self.driver.find_element(By.XPATH, "//input[contains(@name, 'Emissao1') or contains(@id, 'Emissao1')]")
                    print(f"[DEBUG] ✅ Campo 'Emissao1' encontrado por XPATH!")
            
            # SOLUÇÃO: Usar JavaScript para preencher (funciona mesmo se readonly)
            self.driver.execute_script(
                "arguments[0].removeAttribute('readonly'); arguments[0].value = arguments[1];",
                campo_inicial,
                data_inicial_str
            )
            print(f"[DEBUG] ✅ Data inicial preenchida via JS: {data_inicial_str}")
            time.sleep(1)
            
        except NoSuchElementException:
            print(f"[DEBUG] ❌ Campo 'Emissao1' não encontrado!")
            raise Exception("Campo de data inicial (Emissao1) não encontrado!")
        
        try:
            # CAMPO DATA FINAL - Emissao2/Emissao23
            print(f"\n[DEBUG] Procurando campo 'Emissao2' ou 'Emissao23'...")
            
            # Tentar por ID Emissao23 primeiro
            try:
                campo_final = self.driver.find_element(By.ID, "Emissao23")
                print(f"[DEBUG] ✅ Campo encontrado por ID 'Emissao23'!")
            except NoSuchElementException:
                # Tentar por NAME Emissao2
                try:
                    campo_final = self.driver.find_element(By.NAME, "Emissao2")
                    print(f"[DEBUG] ✅ Campo encontrado por NAME 'Emissao2'!")
                except NoSuchElementException:
                    # Tentar XPATH mais amplo
                    campo_final = self.driver.find_element(By.XPATH, "//input[contains(@name, 'Emissao2') or contains(@id, 'Emissao2')]")
                    print(f"[DEBUG] ✅ Campo encontrado por XPATH!")
            
            # SOLUÇÃO: Usar JavaScript para preencher (funciona mesmo se readonly)
            self.driver.execute_script(
                "arguments[0].removeAttribute('readonly'); arguments[0].value = arguments[1];",
                campo_final,
                data_final_str
            )
            print(f"[DEBUG] ✅ Data final preenchida via JS: {data_final_str}")
            time.sleep(1)
            
        except NoSuchElementException as e:
            print(f"[DEBUG] ⚠️ Campo de data final não encontrado: {e}")
            print(f"[DEBUG] (Pode ser opcional, continuando...)")

    def marcar_checkbox_recomendacao(self, marcar: bool = True):
        """Marca ou desmarca o checkbox de recomendação de recompra"""
        acao = "MARCANDO" if marcar else "DESMARCANDO"
        print(f"\n[DEBUG] ========== {acao} CHECKBOX RECOMENDAÇÃO ==========")
        logger.info(f"[{self.nome}] {acao} checkbox...")

        try:
            print(f"[DEBUG] Procurando checkbox 'recomendacaoRecompraConfirmacao'...")

            # Tentar por ID
            try:
                checkbox = self.driver.find_element(By.ID, "recomendacaoRecompraConfirmacao")
                print(f"[DEBUG] ✅ Checkbox encontrado por ID!")
            except NoSuchElementException:
                # Tentar por NAME
                checkbox = self.driver.find_element(By.NAME, "recomendacaoRecompraConfirmacao")
                print(f"[DEBUG] ✅ Checkbox encontrado por NAME!")

            # Verificar estado atual e ajustar
            esta_marcado = checkbox.is_selected()

            if marcar and not esta_marcado:
                print(f"[DEBUG] Checkbox desmarcado, marcando...")
                checkbox.click()
                print(f"[DEBUG] ✅ Checkbox marcado!")
            elif not marcar and esta_marcado:
                print(f"[DEBUG] Checkbox marcado, desmarcando...")
                checkbox.click()
                print(f"[DEBUG] ✅ Checkbox desmarcado!")
            else:
                estado = "marcado" if esta_marcado else "desmarcado"
                print(f"[DEBUG] ℹ️ Checkbox já estava {estado} como esperado")

            time.sleep(1)

        except NoSuchElementException:
            print(f"[DEBUG] ❌ Checkbox 'recomendacaoRecompraConfirmacao' não encontrado!")
            raise Exception("Checkbox de recomendação não encontrado!")

    def clicar_pesquisar(self):
        self.verificar_pausa()  # Verificar pausa antes de iniciar

        print(f"\n[DEBUG] ========== CLICANDO EM PESQUISAR ==========")
        logger.info(f"[{self.nome}] Clicando em Pesquisar...")
        
        try:
            print(f"\n[DEBUG] Procurando botão 'BtnSubmit' ou 'Pesquisar'...")
            
            # Tentar várias formas
            botao = None
            
            # Tentativa 1: Por ID
            try:
                botao = self.driver.find_element(By.ID, "BtnSubmit")
                print(f"[DEBUG] ✅ Botão encontrado por ID 'BtnSubmit'!")
            except NoSuchElementException:
                pass
            
            # Tentativa 2: Por value
            if not botao:
                try:
                    botao = self.driver.find_element(By.XPATH, "//input[@value='Pesquisar']")
                    print(f"[DEBUG] ✅ Botão encontrado por value 'Pesquisar'!")
                except NoSuchElementException:
                    pass
            
            # Tentativa 3: Por name
            if not botao:
                try:
                    botao = self.driver.find_element(By.NAME, "Consultar")
                    print(f"[DEBUG] ✅ Botão encontrado por name 'Consultar'!")
                except NoSuchElementException:
                    pass
            
            # Tentativa 4: XPATH amplo
            if not botao:
                botao = self.driver.find_element(By.XPATH, "//input[@type='button' and contains(@value, 'Pesq')]")
                print(f"[DEBUG] ✅ Botão encontrado por XPATH!")
            
            if botao:
                print(f"[DEBUG] Clicando no botão...")
                botao.click()
                print(f"[DEBUG] ✅ Botão clicado!")
                print(f"[DEBUG] Aguardando resultados carregarem...")
                time.sleep(5)
            else:
                raise Exception("Botão Pesquisar não encontrado!")
            
        except Exception as e:
            print(f"[DEBUG] ❌ Erro ao clicar em pesquisar: {e}")
            raise

    def selecionar_todos_resultados(self):
        """Marca o checkbox 'Selecionar Todos' na NOVA página de resultados"""
        self.verificar_pausa()  # Verificar pausa antes de iniciar

        print(f"\n[DEBUG] ========== SELECIONANDO TODOS OS RESULTADOS ==========")
        logger.info(f"[{self.nome}] Selecionando todos no formulário de resultados...")

        try:
            # IMPORTANTE: Checkbox está no formulário 'Financeiro' após pesquisar
            print(f"[DEBUG] Procurando checkbox name='cSelecionarTodos' no formulário Financeiro...")

            # Seletor EXATO conforme HTML fornecido
            checkbox_todos = None

            # Tentar contexto atual primeiro
            try:
                checkbox_todos = self.driver.find_element(By.NAME, "cSelecionarTodos")
                print(f"[DEBUG] ✅ Checkbox encontrado no contexto atual!")
            except NoSuchElementException:
                # Se não achou, pode estar em outro iframe ou contexto principal
                print(f"[DEBUG] Checkbox não encontrado no contexto atual, tentando contexto principal...")
                self.driver.switch_to.default_content()
                time.sleep(1)

                # Tentar novamente no contexto principal
                try:
                    checkbox_todos = self.driver.find_element(By.NAME, "cSelecionarTodos")
                    print(f"[DEBUG] ✅ Checkbox encontrado no contexto principal!")
                except NoSuchElementException:
                    # Tentar dentro de iframe code novamente
                    print(f"[DEBUG] Tentando dentro do iframe code...")
                    self.mudar_para_frame_code()
                    checkbox_todos = self.driver.find_element(By.NAME, "cSelecionarTodos")
                    print(f"[DEBUG] ✅ Checkbox encontrado no iframe code!")

            if checkbox_todos:
                print(f"[DEBUG] Verificando estado do checkbox...")
                if not checkbox_todos.is_selected():
                    print(f"[DEBUG] Clicando no checkbox 'cSelecionarTodos'...")
                    checkbox_todos.click()
                    print(f"[DEBUG] ✅ Todos os itens selecionados!")
                else:
                    print(f"[DEBUG] ℹ️  Checkbox já estava marcado")
                time.sleep(2)
            else:
                print(f"[DEBUG] ⚠️  Checkbox não encontrado, CONTINUANDO...")

        except Exception as e:
            print(f"[DEBUG] ⚠️  Erro ao selecionar todos: {e}")
            print(f"[DEBUG] Tentando continuar mesmo assim...")

    def verificar_e_resolver_recaptcha(self):
        """
        Verifica se há reCAPTCHA e resolve com extensão CapSolver (ABORDAGEM HÍBRIDA)

        Fluxo SIMPLES:
        1. Detectar se reCAPTCHA apareceu (janela atual OU nova aba)
        2. **CÓDIGO CLICA** no checkbox "Não sou um robô"
        3. **EXTENSÃO RESOLVE** automaticamente (simples ou com imagens)
        4. Clicar botão "Confirmar" (se houver)
        5. Fechar aba de CAPTCHA e voltar para principal

        NOTA: A extensão CapSolver resolve TUDO automaticamente após clicar checkbox.
              Não precisa de chamadas API, cliques em imagens, etc.
        """
        print(f"\n[DEBUG] ========== VERIFICANDO reCAPTCHA ==========")

        try:
            # Salvar janela principal
            janela_principal = self.driver.current_window_handle
            print(f"[DEBUG] Janela principal: {janela_principal[:20]}...")

            # IMPORTANTE: Aguardar para ver se abre NOVA ABA com CAPTCHA
            time.sleep(2)

            # Verificar se abriu nova janela/aba
            todas_janelas = self.driver.window_handles
            print(f"[DEBUG] Total de janelas abertas: {len(todas_janelas)}")

            janela_captcha = None
            captcha_em_nova_aba = False

            # CENÁRIO 1: CAPTCHA em NOVA ABA (comum ao gerar CSV)
            if len(todas_janelas) > 1:
                print(f"[DEBUG] ⚠️ NOVA ABA DETECTADA! Verificando se é CAPTCHA...")

                # Mudar para a nova aba
                for janela in todas_janelas:
                    if janela != janela_principal:
                        self.driver.switch_to.window(janela)
                        janela_captcha = janela
                        time.sleep(1)

                        url_atual = self.driver.current_url
                        titulo_atual = self.driver.title
                        print(f"[DEBUG] URL da nova aba: {url_atual}")
                        print(f"[DEBUG] Título: {titulo_atual}")

                        # Verificar se é página de CAPTCHA
                        if "captcha" in url_atual.lower() or "captcha" in titulo_atual.lower():
                            captcha_em_nova_aba = True
                            print(f"[DEBUG] ✅ CAPTCHA em NOVA ABA confirmado!")
                            break

            # CENÁRIO 2: CAPTCHA na janela atual (comum no login)
            if not captcha_em_nova_aba:
                print(f"[DEBUG] Verificando CAPTCHA na janela atual...")
                self.driver.switch_to.window(janela_principal)
                self.driver.switch_to.default_content()
                time.sleep(1)

            # PASSO 1: DETECTAR iframe do reCAPTCHA
            print(f"[DEBUG] Procurando iframe reCAPTCHA...")

            recaptcha_iframes = self.driver.find_elements(By.XPATH,
                "//iframe[@title='reCAPTCHA' or contains(@src, 'recaptcha')]")

            if len(recaptcha_iframes) == 0:
                print(f"[DEBUG] ✅ Nenhum reCAPTCHA detectado")

                # Se estava em nova aba, voltar para principal
                if captcha_em_nova_aba and janela_captcha:
                    print(f"[DEBUG] Fechando aba e voltando para principal...")
                    self.driver.close()
                    self.driver.switch_to.window(janela_principal)

                return False

            print(f"[DEBUG] ⚠️ reCAPTCHA DETECTADO! ({len(recaptcha_iframes)} iframe(s))")

            # PASSO 2: CLICAR no checkbox "Não sou um robô"
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC

                print(f"[DEBUG] Mudando para iframe do reCAPTCHA...")
                self.driver.switch_to.frame(recaptcha_iframes[0])

                # Procurar checkbox
                print(f"[DEBUG] Aguardando checkbox 'Não sou um robô' ficar clicável...")
                checkbox = None

                # Esperar ATÉ 10 SEGUNDOS para o checkbox ficar clicável
                try:
                    wait = WebDriverWait(self.driver, 10)
                    checkbox = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "recaptcha-checkbox-border")))
                    print(f"[DEBUG] ✅ Checkbox encontrado por CLASS_NAME!")
                except:
                    try:
                        checkbox = wait.until(EC.element_to_be_clickable((By.ID, "recaptcha-anchor")))
                        print(f"[DEBUG] ✅ Checkbox encontrado por ID!")
                    except:
                        checkbox = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='recaptcha-checkbox-border']")))
                        print(f"[DEBUG] ✅ Checkbox encontrado por XPATH!")

                if checkbox:
                    print(f"[DEBUG] ✅ Checkbox está clicável! Clicando...")
                    time.sleep(0.5)  # Pequena pausa antes de clicar
                    checkbox.click()
                    print(f"[DEBUG] ✅ Checkbox clicado!")

                    # PASSO 3: AGUARDAR extensão resolver automaticamente
                    # IMPORTANTE: Extensão pode demorar para resolver imagens complexas
                    print(f"[DEBUG] Aguardando extensão CapSolver resolver automaticamente...")
                    print(f"[DEBUG] (Pode demorar até 60s para imagens complexas...)")

                    # Voltar para contexto principal da aba de CAPTCHA
                    self.driver.switch_to.default_content()

                    # VERIFICAR se CAPTCHA foi resolvido (aguardar ATÉ 60 segundos)
                    captcha_resolvido = False
                    tempo_maximo = 60  # segundos
                    tempo_decorrido = 0
                    intervalo_verificacao = 2  # verificar a cada 2 segundos

                    print(f"[DEBUG] Verificando se extensão resolveu o CAPTCHA...")

                    while tempo_decorrido < tempo_maximo and not captcha_resolvido:
                        try:
                            # Verificar se o token do reCAPTCHA foi preenchido
                            # Quando o CAPTCHA é resolvido, o Google preenche o textarea com id="g-recaptcha-response"
                            recaptcha_response = self.driver.execute_script(
                                "return document.getElementById('g-recaptcha-response')?.value || '';"
                            )

                            if recaptcha_response and len(recaptcha_response) > 0:
                                print(f"[DEBUG] ✅ CAPTCHA RESOLVIDO! Token encontrado (comprimento: {len(recaptcha_response)})")
                                captcha_resolvido = True
                                break
                            else:
                                print(f"[DEBUG] ⏳ Aguardando... ({tempo_decorrido}s / {tempo_maximo}s)")
                                time.sleep(intervalo_verificacao)
                                tempo_decorrido += intervalo_verificacao

                        except Exception as e:
                            print(f"[DEBUG] ⚠️ Erro ao verificar token: {e}")
                            time.sleep(intervalo_verificacao)
                            tempo_decorrido += intervalo_verificacao

                    if not captcha_resolvido:
                        print(f"[DEBUG] ⚠️ TIMEOUT: Extensão não resolveu CAPTCHA em {tempo_maximo}s")
                        print(f"[DEBUG] Tentando continuar mesmo assim...")

                    # PASSO 4: CLICAR botão "Confirmar" (só se CAPTCHA foi resolvido OU timeout)
                    # A extensão resolve automaticamente mas não clica no botão!
                    if captcha_em_nova_aba:
                        print(f"[DEBUG] Procurando botão 'Confirmar'...")
                        botao_confirmar = None

                        try:
                            # Tentar ID primeiro (mais confiável)
                            botao_confirmar = self.driver.find_element(By.ID, "prosseguir")
                            print(f"[DEBUG] ✅ Botão 'Confirmar' encontrado por ID='prosseguir'!")
                        except:
                            try:
                                botao_confirmar = self.driver.find_element(By.NAME, "prosseguir")
                                print(f"[DEBUG] ✅ Botão 'Confirmar' encontrado por NAME='prosseguir'!")
                            except:
                                try:
                                    botao_confirmar = self.driver.find_element(By.XPATH, "//input[@value='Confirmar']")
                                    print(f"[DEBUG] ✅ Botão 'Confirmar' encontrado por value='Confirmar'!")
                                except:
                                    try:
                                        botao_confirmar = self.driver.find_element(By.XPATH, "//input[@type='button' and contains(@onclick, 'finalizar')]")
                                        print(f"[DEBUG] ✅ Botão 'Confirmar' encontrado por onclick='finalizar()'!")
                                    except:
                                        print(f"[DEBUG] ⚠️ Botão 'Confirmar' não encontrado!")

                        if botao_confirmar:
                            print(f"[DEBUG] Clicando no botão 'Confirmar'...")
                            try:
                                botao_confirmar.click()
                                print(f"[DEBUG] ✅ Botão 'Confirmar' clicado!")
                            except:
                                # Se click() falhar, tentar via JavaScript
                                print(f"[DEBUG] Click normal falhou, tentando via JavaScript...")
                                self.driver.execute_script("arguments[0].click();", botao_confirmar)
                                print(f"[DEBUG] ✅ Botão clicado via JavaScript!")

                            time.sleep(2)
                        else:
                            print(f"[DEBUG] ⚠️ Botão 'Confirmar' não encontrado! Tentando continuar...")

                        # PASSO 5: Fechar aba de CAPTCHA e voltar para principal
                        print(f"[DEBUG] Fechando aba de CAPTCHA e voltando para principal...")
                        self.driver.close()
                        self.driver.switch_to.window(janela_principal)
                        print(f"[DEBUG] ✅ Voltou para janela principal")

                    time.sleep(2)
                    return True

            except Exception as e:
                print(f"[DEBUG] ⚠️ Erro ao clicar checkbox: {e}")

                # Voltar para janela principal se estava em nova aba
                if captcha_em_nova_aba and janela_captcha:
                    try:
                        self.driver.close()
                    except:
                        pass
                    self.driver.switch_to.window(janela_principal)
                else:
                    self.driver.switch_to.default_content()

                return False

        except Exception as e:
            print(f"[DEBUG] Erro ao verificar reCAPTCHA: {e}")

            # Tentar voltar para janela principal
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.switch_to.window(self.driver.window_handles[0])
                else:
                    self.driver.switch_to.default_content()
            except:
                pass

            return False

    def resolver_recaptcha_com_capsolver(self):
        """
        Wrapper para manter compatibilidade - agora usa CapSolver Classification
        que clica nas imagens ao invés de só retornar token
        """
        print(f"\n[DEBUG] ⚠️ Função antiga chamada - usando novo método de classificação de imagens")

        # Esta função não é mais necessária porque vamos clicar diretamente nas imagens
        # Retornar None para que o código continue e use a lógica de cliques nas imagens
        return None

    def resolver_captcha_imagens_com_capsolver(self, bframe_element):
        """
        Resolve CAPTCHA de imagens usando CapSolver ReCaptchaV2Classification
        Retorna lista de índices das imagens para clicar
        """
        print(f"\n[DEBUG] ========== RESOLVENDO IMAGENS COM CAPSOLVER CLASSIFICATION ==========")

        if not CAPSOLVER_AVAILABLE:
            print(f"[DEBUG] ❌ Biblioteca CapSolver não disponível")
            return None

        if not CAPSOLVER_API_KEY:
            print(f"[DEBUG] ❌ CAPSOLVER_API_KEY não configurada no .env")
            return None

        try:
            import base64
            import requests
            from io import BytesIO
            from PIL import Image

            # PASSO 1: Mudar contexto para o bframe ANTES de tirar screenshot
            print(f"[DEBUG] Mudando contexto para bframe...")

            # Voltar ao contexto principal e navegar até o bframe
            self.driver.switch_to.default_content()
            iframe_login = self.driver.find_element(By.XPATH, "//iframe[contains(@src, 'loginsec.php')]")
            self.driver.switch_to.frame(iframe_login)

            # Encontrar o bframe novamente no contexto correto
            bframes = self.driver.find_elements(By.XPATH, "//iframe[contains(@src, 'bframe')]")
            if len(bframes) == 0:
                print(f"[DEBUG] ❌ bframe não encontrado")
                return None

            bframe = bframes[0]

            # PASSO 2: Mudar PARA DENTRO do bframe e tirar screenshot do grid
            print(f"[DEBUG] Entrando no bframe para capturar grid de imagens...")

            # Mudar para DENTRO do bframe
            self.driver.switch_to.frame(bframe)
            time.sleep(1)  # Aguardar carregar

            # Procurar a TABELA com o grid de imagens (não o iframe)
            try:
                grid_table = self.driver.find_element(By.XPATH,
                    "//table[@class='rc-imageselect-table-33' or @class='rc-imageselect-table-44']")
                print(f"[DEBUG] ✅ Grid de imagens encontrado, tirando screenshot...")

                # Tirar screenshot do GRID (não do iframe)
                screenshot_png = grid_table.screenshot_as_png

            except Exception as e:
                print(f"[DEBUG] ⚠️ Grid não encontrado, usando screenshot da página inteira do bframe")
                # Fallback: screenshot da página inteira dentro do bframe
                screenshot_png = self.driver.get_screenshot_as_png()

            # Converter para base64
            screenshot_base64 = base64.b64encode(screenshot_png).decode('utf-8')
            print(f"[DEBUG] ✅ Screenshot capturado ({len(screenshot_base64)} caracteres base64)")

            # Salvar screenshot para debug
            try:
                with open("temp/captcha_grid_debug.png", "wb") as f:
                    f.write(screenshot_png)
                print(f"[DEBUG] Screenshot salvo em: temp/captcha_grid_debug.png")
            except:
                pass

            # PASSO 3: Extrair a pergunta do CAPTCHA
            # JÁ ESTAMOS DENTRO DO BFRAME!
            print(f"[DEBUG] Procurando pergunta do CAPTCHA (já dentro do bframe)...")

            pergunta_texto = ""
            try:
                # Tentar pegar o texto da instrução
                pergunta_elementos = self.driver.find_elements(By.XPATH,
                    "//*[contains(@class, 'rc-imageselect-desc') or contains(@class, 'rc-imageselect-desc-wrapper')]")
                if len(pergunta_elementos) > 0:
                    pergunta_texto = pergunta_elementos[0].text
                    print(f"[DEBUG] ✅ Pergunta encontrada: '{pergunta_texto}'")
                else:
                    # Fallback: procurar por strong tag (onde geralmente está o texto)
                    strong_elements = self.driver.find_elements(By.TAG_NAME, "strong")
                    if len(strong_elements) > 0:
                        pergunta_texto = strong_elements[0].text
                        print(f"[DEBUG] ✅ Pergunta em <strong>: '{pergunta_texto}'")
                    else:
                        # Padrão comum
                        pergunta_texto = "traffic lights"
                        print(f"[DEBUG] ⚠️ Pergunta não encontrada, usando padrão: '{pergunta_texto}'")
            except Exception as e:
                pergunta_texto = "traffic lights"
                print(f"[DEBUG] ⚠️ Erro ao extrair pergunta: {e}")

            # Voltar para contexto do iframe de login
            self.driver.switch_to.default_content()
            iframe_login = self.driver.find_element(By.XPATH, "//iframe[contains(@src, 'loginsec.php')]")
            self.driver.switch_to.frame(iframe_login)

            # PASSO 4: Mapear pergunta para object code do CapSolver
            # CapSolver usa códigos específicos para cada tipo de objeto
            object_codes = {
                "traffic light": "/m/015qff",
                "semáforo": "/m/015qff",
                "car": "/m/0k4j",
                "carro": "/m/0k4j",
                "bus": "/m/01bjv",
                "ônibus": "/m/01bjv",
                "bicycle": "/m/0199g",
                "bicicleta": "/m/0199g",
                "motorcycle": "/m/04_sv",
                "motocicleta": "/m/04_sv",
                "crosswalk": "/m/014xcs",
                "faixa de pedestres": "/m/014xcs",
                "stairs": "/m/01lynh",
                "escada": "/m/01lynh",
                "chimney": "/m/01jk_4",
                "chaminé": "/m/01jk_4",
                "bridge": "/m/015kr",
                "ponte": "/m/015kr",
                "boat": "/m/019jd",
                "barco": "/m/019jd"
            }

            # Detectar object code baseado na pergunta
            question_code = "/m/015qff"  # Padrão: traffic lights
            pergunta_lower = pergunta_texto.lower()

            for keyword, code in object_codes.items():
                if keyword in pergunta_lower:
                    question_code = code
                    print(f"[DEBUG] ✅ Object code detectado: {code} para '{keyword}'")
                    break

            # PASSO 5: Enviar para CapSolver ReCaptchaV2Classification
            print(f"\n[DEBUG] Enviando para CapSolver ReCaptchaV2Classification...")
            print(f"[DEBUG] Question code: {question_code}")

            url_capsolver = "https://api.capsolver.com/createTask"
            payload = {
                "clientKey": CAPSOLVER_API_KEY,
                "task": {
                    "type": "ReCaptchaV2Classification",
                    "websiteURL": "https://www.smartsecurities.com.br/smartsecurities/",
                    "image": screenshot_base64,
                    "question": question_code
                }
            }

            response = requests.post(url_capsolver, json=payload, timeout=30)
            result = response.json()

            print(f"[DEBUG] Resposta CapSolver: {result}")

            if result.get('errorId') == 0 and 'taskId' in result:
                task_id = result['taskId']
                print(f"[DEBUG] Task criada: {task_id}")

                # Aguardar resolução
                print(f"[DEBUG] Aguardando CapSolver IA processar imagens...")

                for tentativa in range(30):  # Tentar por até 30 segundos
                    time.sleep(2)

                    # Consultar resultado
                    get_result_url = "https://api.capsolver.com/getTaskResult"
                    get_payload = {
                        "clientKey": CAPSOLVER_API_KEY,
                        "taskId": task_id
                    }

                    get_response = requests.post(get_result_url, json=get_payload, timeout=10)
                    task_result = get_response.json()

                    if task_result.get('status') == 'ready':
                        solution = task_result.get('solution', {})
                        print(f"[DEBUG] ✅ CapSolver resolveu!")
                        print(f"[DEBUG] Solution: {solution}")

                        # Extrair índices das imagens para clicar
                        if solution.get('type') == 'multi':
                            indices = solution.get('objects', [])
                            print(f"[DEBUG] ✅ Imagens para clicar: {indices}")
                            return indices
                        elif solution.get('type') == 'single':
                            if solution.get('hasObject'):
                                print(f"[DEBUG] ✅ Tem objeto na imagem")
                                return [0]  # Clicar na primeira (única) imagem
                            else:
                                print(f"[DEBUG] ⚠️ Sem objeto, pular CAPTCHA")
                                return []
                        else:
                            print(f"[DEBUG] ⚠️ Tipo de solução desconhecido: {solution}")
                            return None

                    elif task_result.get('status') == 'processing':
                        print(f"[DEBUG] Processando... ({tentativa + 1}/30)")
                        continue
                    else:
                        print(f"[DEBUG] ❌ Erro: {task_result}")
                        return None

                print(f"[DEBUG] ❌ Timeout aguardando resposta")
                return None
            else:
                print(f"[DEBUG] ❌ Erro ao criar task: {result}")
                return None

        except Exception as e:
            print(f"[DEBUG] ❌ Erro ao resolver imagens com CapSolver: {e}")
            import traceback
            print(f"[DEBUG] Traceback:")
            print(traceback.format_exc())
            return None

    def renomear_csv_baixado(self, com_checkbox_recompra: bool):
        """Renomeia o CSV baixado para o padrão correto COM VERIFICAÇÃO RIGOROSA"""
        import glob
        import subprocess
        import shutil

        print(f"\n[DEBUG] ========== RENOMEANDO CSV ==========")

        try:
            # ============================================================
            # ESTRATÉGIA: Procurar CSV em MÚLTIPLOS locais possíveis
            # ============================================================
            # 1. Pasta configurada (raw_inputs)
            # 2. Downloads padrão do Chrome no Windows
            # 3. Downloads do usuário no WSL

            possiveis_dirs = []

            # Adicionar pasta configurada
            possiveis_dirs.append(self.download_dir)

            # Se estamos no WSL, adicionar Downloads do Chrome no Windows
            if os.name == 'posix' and os.path.exists('/mnt/c'):
                print(f"[WSL] Detectado ambiente WSL")

                # Tentar pegar usuário do Windows
                try:
                    user_home = os.path.expanduser("~")
                    username = os.path.basename(user_home)

                    # Downloads padrão do Chrome no Windows
                    chrome_downloads = f"/mnt/c/Users/{username}/Downloads"
                    if os.path.exists(chrome_downloads):
                        possiveis_dirs.append(chrome_downloads)
                        print(f"[WSL] Adicionado: {chrome_downloads}")
                except:
                    pass

                # Converter caminho configurado para Windows também
                try:
                    resultado = subprocess.run(['wslpath', '-w', self.download_dir],
                                              capture_output=True, text=True, check=True)
                    download_dir_windows = resultado.stdout.strip()
                    possiveis_dirs.append(download_dir_windows)
                    print(f"[WSL] Adicionado: {download_dir_windows}")
                except:
                    pass

            print(f"[DEBUG] Procurando CSV em {len(possiveis_dirs)} locais...")

            # ============================================================
            # PASSO 1: Procurar .crdownload em TODOS os diretórios
            # ============================================================
            print(f"[DEBUG] Aguardando download finalizar...")
            max_tentativas = 30

            for tentativa in range(max_tentativas):
                tem_crdownload = False
                for dir_busca in possiveis_dirs:
                    if os.path.exists(dir_busca):
                        crdownload = glob.glob(os.path.join(dir_busca, "*.crdownload"))
                        if crdownload:
                            tem_crdownload = True
                            break

                if not tem_crdownload:
                    print(f"[DEBUG] ✅ Download finalizado em {tentativa + 1}s")
                    break

                time.sleep(1)
                if tentativa % 5 == 0 and tentativa > 0:
                    print(f"[DEBUG] Ainda baixando... ({tentativa}s)")

            time.sleep(2)

            # ============================================================
            # PASSO 2: Procurar CSV NOS ÚLTIMOS 20s em TODOS os diretórios
            # ============================================================
            print(f"[DEBUG] Procurando CSV recém-baixado...")

            todos_arquivos_csv = []
            for dir_busca in possiveis_dirs:
                if os.path.exists(dir_busca):
                    csvs = glob.glob(os.path.join(dir_busca, "*.csv"))
                    for csv in csvs:
                        todos_arquivos_csv.append((csv, dir_busca))
                    if csvs:
                        print(f"[DEBUG] Encontrou {len(csvs)} CSVs em: {dir_busca}")

            if not todos_arquivos_csv:
                print(f"[DEBUG] ⚠️ Nenhum CSV encontrado em NENHUM local!")
                for dir_busca in possiveis_dirs:
                    print(f"[DEBUG]   - {dir_busca}: {'existe' if os.path.exists(dir_busca) else 'NÃO EXISTE'}")
                return None

            # Filtrar APENAS arquivos modificados nos últimos 20 segundos
            agora = time.time()
            arquivos_novos = []

            for arquivo_path, dir_origem in todos_arquivos_csv:
                idade = agora - os.path.getmtime(arquivo_path)
                if idade <= 20:  # Modificado nos últimos 20 segundos
                    arquivos_novos.append((arquivo_path, dir_origem, idade))
                    print(f"[DEBUG] CSV novo: {os.path.basename(arquivo_path)} ({idade:.1f}s) em {dir_origem}")

            if not arquivos_novos:
                print(f"[DEBUG] ⚠️ NENHUM CSV novo (últimos 20s)!")
                print(f"[DEBUG] CSVs disponíveis:")
                for arquivo_path, dir_origem in todos_arquivos_csv:
                    idade = agora - os.path.getmtime(arquivo_path)
                    print(f"[DEBUG]   - {os.path.basename(arquivo_path)}: {idade:.0f}s em {dir_origem}")

                # Usar o mais recente mesmo que seja antigo
                arquivo_mais_recente = max(todos_arquivos_csv, key=lambda x: os.path.getmtime(x[0]))
                arquivo_path, dir_origem = arquivo_mais_recente
                idade_arquivo = agora - os.path.getmtime(arquivo_path)
                print(f"[DEBUG] ⚠️ Usando mais recente: {os.path.basename(arquivo_path)} ({idade_arquivo:.0f}s)")
            else:
                # Pegar o MAIS NOVO
                arquivo_mais_recente = min(arquivos_novos, key=lambda x: x[2])
                arquivo_path, dir_origem, idade_arquivo = arquivo_mais_recente
                print(f"[DEBUG] ✅ CSV recém-baixado: {os.path.basename(arquivo_path)} ({idade_arquivo:.1f}s)")

            print(f"[DEBUG] Arquivo origem: {arquivo_path}")
            print(f"[DEBUG] Diretório origem: {dir_origem}")

            # ============================================================
            # PASSO 3: COPIAR/MOVER para pasta raw_inputs com nome correto
            # ============================================================
            data_atual = datetime.now().strftime("%Y_%m_%d")

            if com_checkbox_recompra:
                nome_novo = f"titulos_abertos_marcados_recompras_{data_atual}.csv"
            else:
                nome_novo = f"titulos_abertos_{data_atual}.csv"

            # SEMPRE salvar em raw_inputs (WSL)
            caminho_destino = os.path.join(self.download_dir, nome_novo)

            # Se já existe, adicionar timestamp
            if os.path.exists(caminho_destino):
                timestamp = datetime.now().strftime("%H%M%S")
                if com_checkbox_recompra:
                    nome_novo = f"titulos_abertos_marcados_recompras_{data_atual}_{timestamp}.csv"
                else:
                    nome_novo = f"titulos_abertos_{data_atual}_{timestamp}.csv"
                caminho_destino = os.path.join(self.download_dir, nome_novo)

            print(f"[DEBUG] Copiando arquivo:")
            print(f"[DEBUG]   De:   {arquivo_path}")
            print(f"[DEBUG]   Para: {caminho_destino}")

            # COPIAR arquivo (shutil funciona entre WSL e Windows)
            shutil.copy2(arquivo_path, caminho_destino)
            print(f"[DEBUG] ✅ Arquivo copiado!")

            # DELETAR arquivo original (se não estiver já em raw_inputs)
            if dir_origem != self.download_dir:
                try:
                    os.remove(arquivo_path)
                    print(f"[DEBUG] ✅ Arquivo original deletado de: {dir_origem}")
                except Exception as e:
                    print(f"[DEBUG] ⚠️ Não foi possível deletar original: {e}")

            print(f"[DEBUG] ✅ CSV salvo como: {nome_novo}")
            logger.info(f"[{self.nome}] CSV salvo: {nome_novo}")

            return caminho_destino

        except Exception as e:
            print(f"[DEBUG] ⚠️ Erro ao renomear CSV: {e}")
            logger.warning(f"[{self.nome}] Erro ao renomear CSV: {e}")
            return None

    def clicar_gerar_csv(self):
        """Clica no botão 'Gerar CSV' para exportar os dados"""
        self.verificar_pausa()  # Verificar pausa antes de iniciar

        print(f"\n[DEBUG] ========== GERANDO CSV ==========")
        logger.info(f"[{self.nome}] Gerando CSV...")

        try:
            # SELETOR EXATO: <input name="Imprimir" id="ImprimirCSV" type="button" class="campo" onclick="TipoImpressaoRelatorio(3, this)" value="Gerar CSV">
            print(f"[DEBUG] Procurando botão ID='ImprimirCSV' name='Imprimir'...")

            botao_csv = None

            # Tentar ID primeiro (mais confiável)
            try:
                botao_csv = self.driver.find_element(By.ID, "ImprimirCSV")
                print(f"[DEBUG] ✅ Botão encontrado por ID 'ImprimirCSV'!")
            except NoSuchElementException:
                # Fallback: tentar por NAME
                try:
                    botao_csv = self.driver.find_element(By.NAME, "Imprimir")
                    print(f"[DEBUG] ✅ Botão encontrado por NAME 'Imprimir'!")
                except NoSuchElementException:
                    # Último recurso: XPATH com value
                    botao_csv = self.driver.find_element(By.XPATH, "//input[@value='Gerar CSV']")
                    print(f"[DEBUG] ✅ Botão encontrado por XPATH value='Gerar CSV'!")

            if botao_csv:
                print(f"[DEBUG] Clicando no botão 'Gerar CSV'...")
                botao_csv.click()
                print(f"[DEBUG] ✅ Botão clicado!")

                # IMPORTANTE: Verificar se apareceu reCAPTCHA
                time.sleep(3)  # Aguardar página reagir
                self.verificar_e_resolver_recaptcha()

                print(f"[DEBUG] Aguardando download do CSV...")
                time.sleep(10)  # Aguardar o download
            else:
                raise Exception("Botão 'Gerar CSV' não encontrado!")

        except NoSuchElementException as e:
            print(f"[DEBUG] ❌ Botão 'Gerar CSV' não encontrado: {e}")
            raise Exception("Botão 'Gerar CSV' não encontrado!")

    def executar_extracao_completa(self, com_checkbox_recompra: bool):
        """Executa uma extração completa (com ou sem checkbox marcado)"""
        tipo = "COM CHECKBOX RECOMPRA" if com_checkbox_recompra else "SEM CHECKBOX RECOMPRA"
        print(f"\n{'#'*80}")
        print(f"# EXECUTANDO EXTRAÇÃO: {tipo}")
        print(f"{'#'*80}\n")
        logger.info(f"[{self.nome}] Executando extração: {tipo}")

        try:
            self.navegar_para_titulos_abertos()

            # Verificar CAPTCHA antes de continuar (pode aparecer na navegação)
            captcha_resolvido = self.verificar_e_resolver_recaptcha()
            if captcha_resolvido:
                # Após resolver CAPTCHA, navegar novamente
                self.navegar_para_titulos_abertos()

            self.mudar_para_frame_code()
            self.preencher_datas()
            self.marcar_checkbox_recomendacao(marcar=com_checkbox_recompra)
            self.clicar_pesquisar()

            # Verificar reCAPTCHA após pesquisar (pode aparecer aqui também)
            captcha_resolvido = self.verificar_e_resolver_recaptcha()
            if captcha_resolvido:
                # Voltar para iframe após resolver CAPTCHA
                self.mudar_para_frame_code()

            self.selecionar_todos_resultados()
            self.clicar_gerar_csv()

            # IMPORTANTE: Renomear o CSV baixado para o padrão correto
            arquivo_salvo = self.renomear_csv_baixado(com_checkbox_recompra)

            if arquivo_salvo:
                print(f"\n[DEBUG] ✅ Extração {tipo} concluída!")
                print(f"[DEBUG] 📄 Arquivo: {os.path.basename(arquivo_salvo)}")
                logger.info(f"[{self.nome}] ✅ Extração {tipo} concluída - {os.path.basename(arquivo_salvo)}")
            else:
                print(f"\n[DEBUG] ⚠️ Extração {tipo} concluída, mas CSV não foi renomeado")
                logger.warning(f"[{self.nome}] ⚠️ Extração {tipo} concluída, mas CSV não foi renomeado")

            return True

        except Exception as e:
            print(f"\n[DEBUG] ❌ Erro na extração {tipo}: {e}")
            logger.error(f"[{self.nome}] ❌ Erro na extração {tipo}: {e}", exc_info=True)

            # Se der erro, tirar screenshot para debug
            try:
                screenshot_path = f"logs/erros/web/erro_extracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                os.makedirs("logs/erros/web", exist_ok=True)
                self.driver.save_screenshot(screenshot_path)
                print(f"[DEBUG] Screenshot do erro: {screenshot_path}")
            except:
                pass

            raise

    def processar(self, modo_simulacao=False):
        inicio = now_br()
        print(f"\n{'='*80}")
        print(f"PROCESSADOR - TÍTULOS ABERTOS E MARCADOS RECOMPRAS (v24.0)")
        print(f"CICLO CONTÍNUO: LOGIN AUTO + CAPSOLVER IA CLASSIFICATION")
        print(f"IA IDENTIFICA + CLICA NAS IMAGENS REAIS!")
        print(f"{'='*80}\n")
        logger.info(f"[{self.nome}] ========== INICIANDO CICLO CONTÍNUO ==========")

        if modo_simulacao:
            return {"success": True, "mensagem": "Simulação"}

        try:
            # PASSO 1: Iniciar listener de teclado em thread separada
            self.listener_thread = threading.Thread(target=self.escutar_teclado, daemon=True)
            self.listener_thread.start()
            logger.info(f"[{self.nome}] Thread de controle de teclado iniciada")

            # PASSO 2: Iniciar navegador e fazer login automático
            self.iniciar_navegador()
            self.fazer_login_automatico()

            # PASSO 3: Loop infinito de extrações
            ciclo = 1
            while not self.parar:
                # Verificar se está pausado
                self.verificar_pausa()

                # Se foi solicitado parar, sair do loop
                if self.parar:
                    break

                print(f"\n{'='*80}")
                print(f"CICLO #{ciclo} - {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*80}\n")
                logger.info(f"[{self.nome}] ========== CICLO #{ciclo} ==========")

                # EXTRAÇÃO 1: COM checkbox marcado
                print(f"\n[CICLO {ciclo}] ETAPA 1/2: Extraindo COM checkbox recompra...")
                self.verificar_pausa()  # Verificar pausa antes de cada etapa
                if not self.parar:
                    self.executar_extracao_completa(com_checkbox_recompra=True)

                # EXTRAÇÃO 2: SEM checkbox marcado
                print(f"\n[CICLO {ciclo}] ETAPA 2/2: Extraindo SEM checkbox recompra...")
                self.verificar_pausa()  # Verificar pausa antes de cada etapa
                if not self.parar:
                    self.executar_extracao_completa(com_checkbox_recompra=False)

                # ESPERA 1 MINUTO (com verificação de pausa durante a espera)
                if not self.parar:
                    print(f"\n{'='*80}")
                    print(f"✅ CICLO #{ciclo} CONCLUÍDO!")
                    print(f"⏳ Aguardando 60 segundos para próximo ciclo...")
                    print(f"{'='*80}\n")
                    logger.info(f"[{self.nome}] ✅ Ciclo #{ciclo} concluído, aguardando 60s...")

                    # Esperar 60s com verificação de pausa a cada 1s
                    for _ in range(60):
                        if self.parar:
                            break
                        self.verificar_pausa()
                        time.sleep(1)

                    ciclo += 1

            # Se chegou aqui, foi por causa do comando Q
            if self.parar:
                print(f"\n{'='*80}")
                print("⏹️  EXECUÇÃO PARADA PELO USUÁRIO")
                print(f"{'='*80}\n")
                logger.info(f"[{self.nome}] ⏹️ Execução parada pelo comando Q")
                return {"success": True, "mensagem": "Parado pelo usuário (Q)"}

        except KeyboardInterrupt:
            print(f"\n\n{'='*80}")
            print("⏹️  PROCESSAMENTO INTERROMPIDO PELO USUÁRIO")
            print(f"{'='*80}\n")
            logger.info(f"[{self.nome}] ⏹️ Interrompido pelo usuário")
            return {"success": True, "mensagem": "Interrompido pelo usuário"}

        except Exception as e:
            print(f"\n[DEBUG] ❌❌❌ ERRO CRÍTICO ❌❌❌")
            print(f"[DEBUG] {str(e)}")
            logger.error(f"[{self.nome}] ❌ Erro: {e}", exc_info=True)

            try:
                # IMPORTANTE: Usar mesmo timestamp para screenshot e HTML
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                screenshot_path = f"logs/erros/web/erro_debug_{timestamp}.png"
                os.makedirs("logs/erros/web", exist_ok=True)
                self.driver.save_screenshot(screenshot_path)
                print(f"[DEBUG] Screenshot salvo em: {screenshot_path}")

                html_path = f"logs/erros/web/erro_html_{timestamp}.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                print(f"[DEBUG] HTML salvo em: {html_path}")
            except Exception as save_error:
                print(f"[DEBUG] ⚠️ Erro ao salvar debug: {save_error}")

            return {"success": False, "mensagem": str(e)}

        finally:
            if self.driver:
                close_driver(self.driver)

def processar_titulos_abertos_e_marcados_recompras(modo_simulacao: bool = False) -> dict:
    return ProcessadorTitulosAbertosEMarcadosRecompras().processar(modo_simulacao=modo_simulacao)

if __name__ == "__main__":
    resultado = processar_titulos_abertos_e_marcados_recompras()
    print(f"\n{'='*80}")
    print("RESULTADO FINAL:", "✅ SUCESSO" if resultado["success"] else "❌ FALHA")
    print("Mensagem:", resultado.get("mensagem"))
    print("="*80 + "\n")