# =============================================================================================
# ARQUIVO: titulos_abertos_e_marcados_recompras.py
# VERSÃO: v26.0 - REESCRITA COMPLETA COM NODRIVER
# MUDANÇA: Reescrita 100% Nodriver (async), sem código Selenium
# =============================================================================================

import os
import sys
import asyncio
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Nodriver imports (substitui Selenium completamente)
try:
    import nodriver as uc
    from nodriver import Browser, Tab
    from nodriver.core.element import Element
    NODRIVER_AVAILABLE = True
except ImportError:
    NODRIVER_AVAILABLE = False
    print("⚠️ Nodriver não instalado. Execute: pip install nodriver")

from src.common.nodriver_utils import (
    init_browser,
    wait_for_element,
    close_browser,
    human_click,
    human_type,
    simulate_human_activity
)
from src.core.logging_config import get_logger
from src.common.timezone_utils import now_br

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


# Exceção customizada para controle de fluxo do sistema de recuperação de erros
class VoltarEtapaAnteriorException(Exception):
    """Exceção lançada quando usuário solicita voltar à etapa anterior"""
    pass


class ProcessadorTitulosAbertosEMarcadosRecompras:
    """Processador de títulos abertos e marcados para recompras - 100% Nodriver Async"""

    def __init__(self):
        self.nome = "titulos_abertos_e_marcados_recompras"

        # Nodriver: browser e tab (substitui self.driver)
        self.browser: Browser = None
        self.tab: Tab = None  # Tab ativa (equivalente a self.driver no Selenium)

        self.download_dir = os.path.abspath(DOWNLOAD_DIR)

        # Display virtual (Xvfb/VNC)
        self.display = os.environ.get('DISPLAY', ':1')  # Padrão :1 se não configurado

        # Controles de execução
        self.pausado = False
        self.parar = False
        self.listener_thread = None
        self.ultima_tecla_tempo = 0  # Debounce para evitar múltiplas leituras

        # Contador de erros de CAPTCHA
        self.captcha_errors = 0

    def converter_cdp_para_dict(self, resultado_cdp):
        """
        Converte resultado CDP (Chrome DevTools Protocol) para dict Python

        CDP retorna: [['key1', {'type': 'type', 'value': val}], ['key2', ...]]
        Precisa virar: {'key1': val, 'key2': val, ...}
        """
        if isinstance(resultado_cdp, dict):
            return resultado_cdp  # Já é dict

        if isinstance(resultado_cdp, list):
            resultado_dict = {}
            for item in resultado_cdp:
                if isinstance(item, list) and len(item) == 2:
                    chave = item[0]
                    valor_obj = item[1]
                    if isinstance(valor_obj, dict) and 'value' in valor_obj:
                        resultado_dict[chave] = valor_obj['value']
                    else:
                        resultado_dict[chave] = valor_obj
            return resultado_dict

        return resultado_cdp

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
            except Exception:
                pass

    def processar_comando(self, tecla):
        """Processa comandos do teclado"""
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
            time.sleep(0.2)

    async def iniciar_navegador(self):
        """Inicializa navegador com Nodriver (anti-detecção nativa)"""
        print(f"\n[DEBUG] Iniciando navegador com Nodriver...")
        logger.info(f"[{self.nome}] Iniciando navegador...")
        os.makedirs(self.download_dir, exist_ok=True)

        if not NODRIVER_AVAILABLE:
            raise ImportError("Nodriver não está instalado! Execute: pip install nodriver")

        # Configurar display virtual (Xvfb/VNC)
        if self.display:
            os.environ['DISPLAY'] = self.display
            print(f"[NODRIVER] Display configurado: {self.display}")

        print(f"[NODRIVER] Abrindo Chrome com anti-detecção nativa...")
        print(f"[NODRIVER] Downloads: {self.download_dir}")

        # Iniciar browser
        self.browser = await init_browser(
            download_dir=self.download_dir,
            headless=False,
            display=self.display
        )

        print(f"[NODRIVER] ✅ Chrome aberto!")

        # IMPORTANTE: Abrir página da extensão CapSolver PRIMEIRO
        capsolver_url = "https://chromewebstore.google.com/detail/captcha-solver-auto-captc/pgojnojmmhpofjgdmaebadhbocahppod?hl=pt-BR"
        print(f"\n[EXTENSÃO] Abrindo página da extensão CapSolver...")
        self.tab = await self.browser.get(capsolver_url)

        print(f"\n{'='*80}")
        print(f"[EXTENSÃO] ⚠️  AÇÃO NECESSÁRIA: INSTALE A EXTENSÃO CAPSOLVER")
        print(f"{'='*80}")
        print(f"")
        print(f"1. Clique no botão 'Usar no Chrome' na página que abriu")
        print(f"2. Confirme a instalação da extensão")
        print(f"3. Configure a API Key da CapSolver:")
        print(f"   {CAPSOLVER_API_KEY}")
        print(f"4. Ative 'Auto Solve' na extensão")
        print(f"5. Pressione 'R' e ENTER aqui para continuar...")
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

        # Agora sim, navegar para SmartSecurities
        self.tab = await self.browser.get(URL_LOGIN)

        print(f"[NAVEGADOR] ✅ Navegador aberto em: {URL_LOGIN}")
        print(f"[NAVEGADOR] Aguardando página carregar...")
        await asyncio.sleep(3)
        print(f"[NAVEGADOR] ✅ Página carregada!")

        logger.info(f"[{self.nome}] ✅ Navegador Nodriver inicializado e extensão instalada")

    async def aguardar_extensao_resolver_captcha(self):
        """
        Aguarda extensão CapSolver resolver reCAPTCHA automaticamente

        Returns:
            bool: True se resolvido, False se cancelado
        """
        print(f"\n[CAPTCHA] Aguardando extensão CapSolver resolver reCAPTCHA...")
        print(f"[CAPTCHA] (Máximo 60 segundos)")

        for tentativa in range(60):
            try:
                # Verificar se token foi preenchido
                token = await self.tab.evaluate(
                    "document.getElementById('g-recaptcha-response')?.value || ''"
                )

                if token and len(token) > 0:
                    print(f"[CAPTCHA] ✅ RESOLVIDO pela extensão em {tentativa + 1}s!")
                    return True

                # Feedback visual a cada 5s
                if (tentativa + 1) % 5 == 0:
                    print(f"[CAPTCHA] ⏳ Aguardando... ({tentativa + 1}s)")

                # Verificar se usuário pausou/parou
                self.verificar_pausa()
                if self.parar:
                    return False

                await asyncio.sleep(1)

            except Exception as e:
                print(f"[CAPTCHA] ⚠️ Erro ao verificar token: {e}")
                await asyncio.sleep(1)

        # Timeout → Fallback manual
        print(f"\n{'='*80}")
        print(f"⚠️  CAPTCHA NÃO RESOLVIDO AUTOMATICAMENTE")
        print(f"⚠️  Extensão CapSolver não resolveu em 60 segundos")
        print(f"")
        print(f"📋 AÇÕES NECESSÁRIAS:")
        print(f"   1. Resolva o CAPTCHA MANUALMENTE no navegador (VNC)")
        print(f"   2. Pressione [R] aqui para RETOMAR a execução")
        print(f"{'='*80}\n")

        self.captcha_errors += 1
        self.pausado = True
        logger.warning(f"[{self.nome}] CAPTCHA timeout, pausando para intervenção manual")

        print(f"[CONTROLE] Aguardando você pressionar [R] para retomar...")
        while self.pausado and not self.parar:
            await asyncio.sleep(0.5)

        return not self.parar

    async def clicar_botao_acessar_login(self):
        """Clica no botão 'Acessar' após CAPTCHA resolvido"""
        print(f"\n[LOGIN] Clicando no botão 'Acessar'...")

        try:
            botao_acessar = await wait_for_element(self.tab, "#OKExtra", timeout=10)

            if not botao_acessar:
                botao_acessar = await wait_for_element(self.tab, "button:has-text('Acessar')", timeout=5)

            if botao_acessar:
                print(f"[LOGIN] ✅ Botão 'Acessar' encontrado!")
                await human_click(botao_acessar)
                print(f"[LOGIN] ✅ Botão clicado!")
                await asyncio.sleep(5)
                return True
            else:
                raise Exception("Botão 'Acessar' não encontrado!")

        except Exception as e:
            print(f"[LOGIN] ❌ Erro ao clicar no botão 'Acessar': {e}")
            raise

    async def fazer_login_automatico(self):
        """Faz login automático usando credenciais do .env - REPLICANDO LÓGICA SELENIUM"""
        self.verificar_pausa()

        print(f"\n{'='*80}")
        print("🔐 REALIZANDO LOGIN AUTOMÁTICO")
        print(f"{'='*80}\n")
        logger.info(f"[{self.nome}] Iniciando login automático...")

        try:
            if not SMART_EMAIL or not SMART_PASSWORD:
                raise Exception("Credenciais não encontradas no .env")

            print(f"[DEBUG] Email: {SMART_EMAIL}")
            print(f"[DEBUG] Aguardando campos de login carregar...")
            await asyncio.sleep(3)

            # ============================================================
            # SOLUÇÃO: Usar JavaScript para acessar iframe (igual Selenium)
            # No Selenium: driver.switch_to.frame(iframe)
            # No Nodriver: JavaScript com iframe.contentDocument
            # ============================================================

            print(f"\n[DEBUG] Preenchendo credenciais via JavaScript (dentro do iframe)...")

            # JavaScript que REPLICA o comportamento do Selenium switch_to.frame()
            login_script = f"""
            (async () => {{
                // 1. Encontrar iframe de login (igual Selenium)
                const iframes = document.querySelectorAll('iframe');
                let iframeLogin = null;

                for (const iframe of iframes) {{
                    if (iframe.src && iframe.src.includes('loginsec.php')) {{
                        iframeLogin = iframe;
                        break;
                    }}
                }}

                if (!iframeLogin && iframes.length > 0) {{
                    iframeLogin = iframes[0]; // Fallback: primeiro iframe
                }}

                if (!iframeLogin) {{
                    return {{ success: false, error: 'Iframe não encontrado' }};
                }}

                // 2. Acessar documento DENTRO do iframe (equivalente ao switch_to.frame)
                const iframeDoc = iframeLogin.contentDocument || iframeLogin.contentWindow.document;

                if (!iframeDoc) {{
                    return {{ success: false, error: 'contentDocument não acessível' }};
                }}

                // 3. Buscar campos NO CONTEXTO DO IFRAME (igual Selenium após switch_to)
                const campoEmail = iframeDoc.getElementById('fEmail') || iframeDoc.querySelector('[name="fEmail"]');
                const campoSenha = iframeDoc.getElementById('fPassword') || iframeDoc.querySelector('[name="fPassword"]');
                const botaoEntrar = iframeDoc.getElementById('OK') || iframeDoc.querySelector('[name="OK"]');

                if (!campoEmail) {{
                    return {{ success: false, error: 'Campo email não encontrado' }};
                }}
                if (!campoSenha) {{
                    return {{ success: false, error: 'Campo senha não encontrado' }};
                }}
                if (!botaoEntrar) {{
                    return {{ success: false, error: 'Botão Entrar não encontrado' }};
                }}

                // 4. Preencher campos (igual Selenium clear + send_keys)
                campoEmail.value = '';
                campoEmail.value = '{SMART_EMAIL}';

                campoSenha.value = '';
                campoSenha.value = '{SMART_PASSWORD}';

                return {{
                    success: true,
                    email_preenchido: campoEmail.value,
                    senha_preenchida: '***',
                    botao_encontrado: true
                }};
            }})();
            """

            # Executar JavaScript
            resultado = await self.tab.evaluate(login_script)

            if not resultado or not resultado.get('success'):
                erro = resultado.get('error', 'Erro desconhecido') if resultado else 'Script retornou None'
                raise Exception(f"Erro ao preencher campos via JavaScript: {erro}")

            print(f"[DEBUG] ✅ Email preenchido via JavaScript!")
            print(f"[DEBUG] ✅ Senha preenchida via JavaScript!")
            await asyncio.sleep(1)
            self.verificar_pausa()

            # ============================================================
            # Clicar botão "Entrar" via JavaScript (igual Selenium .click())
            # ============================================================
            print(f"\n[DEBUG] Clicando no botão 'Entrar' via JavaScript...")

            click_script = """
            (() => {
                const iframes = document.querySelectorAll('iframe');
                let iframeLogin = null;

                for (const iframe of iframes) {
                    if (iframe.src && iframe.src.includes('loginsec.php')) {
                        iframeLogin = iframe;
                        break;
                    }
                }

                if (!iframeLogin && iframes.length > 0) {
                    iframeLogin = iframes[0];
                }

                if (!iframeLogin) return { success: false, error: 'Iframe não encontrado' };

                const iframeDoc = iframeLogin.contentDocument || iframeLogin.contentWindow.document;
                const botaoEntrar = iframeDoc.getElementById('OK') || iframeDoc.querySelector('[name="OK"]');

                if (!botaoEntrar) return { success: false, error: 'Botão não encontrado' };

                botaoEntrar.click();
                return { success: true };
            })();
            """

            resultado_click = await self.tab.evaluate(click_script)

            if not resultado_click or not resultado_click.get('success'):
                erro = resultado_click.get('error', 'Erro ao clicar') if resultado_click else 'Script retornou None'
                raise Exception(f"Erro ao clicar no botão Entrar: {erro}")

            print(f"[DEBUG] ✅ Botão 'Entrar' clicado via JavaScript!")

            # Aguardar CAPTCHA carregar
            print(f"\n[DEBUG] Aguardando reCAPTCHA carregar...")
            await asyncio.sleep(2)
            self.verificar_pausa()

            # Aguardar extensão resolver CAPTCHA
            captcha_resolvido = await self.aguardar_extensao_resolver_captcha()

            if not captcha_resolvido:
                raise Exception("CAPTCHA não foi resolvido")

            # Clicar botão "Acessar" (após CAPTCHA)
            await self.clicar_botao_acessar_login()

            print(f"\n{'='*80}")
            print("✅ LOGIN REALIZADO COM SUCESSO!")
            print(f"{'='*80}\n")
            logger.info(f"[{self.nome}] ✅ Login automático realizado")

            return True

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ ERRO NO LOGIN AUTOMÁTICO: {e}")
            print("Você pode fazer login manualmente no navegador (VNC)")
            print(f"{'='*80}\n")
            logger.error(f"[{self.nome}] ❌ Erro no login automático: {e}")

            # Fallback para login manual
            print("\n" + "="*80)
            print("⏸️  FAÇA LOGIN MANUALMENTE NO NAVEGADOR (VNC)")
            print("⏸️  Depois pressione ENTER aqui para continuar...")
            print("="*80 + "\n")
            input(">>> Pressione ENTER quando terminar o login >>> ")
            print(f"\n[DEBUG] ENTER pressionado! Continuando automação...\n")
            await asyncio.sleep(3)

            return True

    async def navegar_para_titulos_abertos(self):
        """Navega para página de títulos em aberto"""
        self.verificar_pausa()

        print(f"\n[DEBUG] ========== CARREGANDO TÍTULOS EM ABERTO ==========")
        logger.info(f"[{self.nome}] Carregando títulos em aberto...")

        url_titulos = "https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php"

        try:
            print(f"[DEBUG] Carregando página via JavaScript...")
            script = f"document.getElementById('code').src = '{url_titulos}';"
            await self.tab.evaluate(script)

            print(f"[DEBUG] Aguardando página carregar...")
            await asyncio.sleep(5)
            self.verificar_pausa()

            print(f"[DEBUG] ✅ Página carregada")

        except Exception as e:
            print(f"[DEBUG] ⚠️ Erro ao carregar: {e}")

    async def verificar_e_aguardar_frames_prontos(self):
        """
        CRÍTICO: Equivalente ao mudar_para_frame_code() do Selenium

        No Selenium (linhas 568-653 do backup):
        - switch_to.default_content()
        - switch_to.frame("code") + aguarda 3s
        - switch_to.frame("text") ou primeiro frame + aguarda 2s

        No Nodriver:
        - Verifica se frames estão acessíveis via JavaScript
        - Aguarda e retenta se necessário
        - Retorna informações sobre os frames encontrados
        """
        self.verificar_pausa()

        print(f"\n[DEBUG] ========== VERIFICANDO FRAMES ==========")
        logger.info(f"[{self.nome}] Verificando frames prontos...")

        # Tentar até 10 vezes (10 segundos no total)
        max_tentativas = 10

        for tentativa in range(1, max_tentativas + 1):
            try:
                resultado = await self.tab.evaluate("""
                    (function() {
                        // Passo 1: Verificar frame 'code'
                        var frameCode = document.getElementById('code');
                        if (!frameCode) {
                            return { success: false, error: 'Frame code não encontrado', retry: true };
                        }

                        var frameCodeDoc = frameCode.contentDocument || frameCode.contentWindow.document;
                        if (!frameCodeDoc) {
                            return { success: false, error: 'Frame code contentDocument inacessível', retry: true };
                        }

                        // Passo 2: Verificar frame interno (POR NAME, não ID!)
                        var frameText = frameCodeDoc.querySelector('frame[name="text"], iframe[name="text"]');
                        var frameInterno = null;
                        var nomeFrameInterno = 'nenhum';

                        if (frameText) {
                            var docInterno = frameText.contentDocument || frameText.contentWindow.document;
                            if (docInterno) {
                                frameInterno = docInterno;
                                nomeFrameInterno = 'text';
                            }
                        } else {
                            // Procurar primeiro frame/iframe
                            var frames = frameCodeDoc.querySelectorAll('frame, iframe');
                            if (frames.length > 0) {
                                var docInterno = frames[0].contentDocument || frames[0].contentWindow.document;
                                if (docInterno) {
                                    frameInterno = docInterno;
                                    nomeFrameInterno = frames[0].name || 'frame[0]';
                                }
                            }
                        }

                        if (!frameInterno) {
                            return {
                                success: false,
                                error: 'Frame interno inacessível',
                                retry: true,
                                framesEncontrados: frameCodeDoc.querySelectorAll('frame, iframe').length
                            };
                        }

                        // Passo 3: Verificar se há inputs no frame interno (sinal que carregou)
                        var inputs = frameInterno.querySelectorAll('input');
                        var totalInputs = inputs.length;

                        // Verificar especificamente o campo Emissao1
                        var campoEmissao1 = frameInterno.getElementById('Emissao1');

                        return {
                            success: true,
                            frameCode: 'OK',
                            frameInterno: nomeFrameInterno,
                            totalInputs: totalInputs,
                            temCampoEmissao1: campoEmissao1 !== null
                        };

                    })();
                """)

                # Converter CDP para dict
                resultado = self.converter_cdp_para_dict(resultado)

                # DEBUG: Verificar tipo do resultado
                print(f"[DEBUG] Tipo após conversão: {type(resultado)}")
                print(f"[DEBUG] Valor: {resultado}")

                if not isinstance(resultado, dict):
                    print(f"[DEBUG] ⚠️ Não conseguiu converter para dict!")
                    print(f"[DEBUG] Tentando continuar sem verificação...")
                    # FALLBACK: assumir que frames estão prontos e continuar
                    await asyncio.sleep(2)
                    return True

                if resultado.get('success'):
                    print(f"[DEBUG] ✅ Frames prontos em {tentativa} tentativa(s)!")
                    print(f"[DEBUG]   Frame code: {resultado.get('frameCode')}")
                    print(f"[DEBUG]   Frame interno: {resultado.get('frameInterno')}")
                    print(f"[DEBUG]   Total de inputs: {resultado.get('totalInputs')}")
                    print(f"[DEBUG]   Campo Emissao1: {'encontrado' if resultado.get('temCampoEmissao1') else 'NÃO encontrado'}")

                    # Aguardar mais um pouco (equivalente ao time.sleep(2) do Selenium)
                    await asyncio.sleep(2)
                    return True

                elif resultado.get('retry'):
                    if tentativa < max_tentativas:
                        print(f"[DEBUG] ⏳ Frames não prontos, tentativa {tentativa}/{max_tentativas}: {resultado.get('error')}")
                        if 'framesEncontrados' in resultado:
                            print(f"[DEBUG]   Frames encontrados no 'code': {resultado.get('framesEncontrados')}")
                        await asyncio.sleep(1)
                        continue
                    else:
                        print(f"[DEBUG] ❌ Timeout aguardando frames: {resultado.get('error')}")
                        raise Exception(f"Frames não ficaram prontos após {max_tentativas} tentativas")
                else:
                    print(f"[DEBUG] ❌ Erro ao verificar frames: {resultado.get('error')}")
                    raise Exception(f"Erro ao verificar frames: {resultado.get('error')}")

            except Exception as e:
                if tentativa < max_tentativas:
                    print(f"[DEBUG] ⚠️ Exceção ao verificar frames (tentativa {tentativa}/{max_tentativas}): {e}")
                    await asyncio.sleep(1)
                    continue
                else:
                    raise

        raise Exception(f"Não foi possível verificar frames após {max_tentativas} tentativas")

    async def preencher_datas(self):
        """
        Preenche campos de data inicial e final - REPLICANDO LÓGICA SELENIUM

        No Selenium: já está no contexto do frame após mudar_para_frame_code()
        No Nodriver: precisa acessar frame via JavaScript toda vez
        """
        self.verificar_pausa()

        data_atual = datetime.now()
        data_inicial = data_atual - timedelta(days=365)
        data_inicial_str = data_inicial.strftime("%d/%m/%Y")
        data_final_str = data_atual.strftime("%d/%m/%Y")

        print(f"\n[DEBUG] ========== PREENCHENDO DATAS ==========")
        print(f"[DEBUG] Data inicial (1 ano atrás): {data_inicial_str}")
        print(f"[DEBUG] Data final (hoje): {data_final_str}")
        logger.info(f"[{self.nome}] Preenchendo datas...")

        print(f"\n[DEBUG] Preenchendo via JavaScript (frame 'code' → frame 'text')...")

        # IMPORTANTE: Usar template string seguro
        script = f"""
        (function() {{
            try {{
                // Passo 1: Encontrar frame 'code'
                var frameCode = document.getElementById('code');
                if (!frameCode) {{
                    return {{ success: false, error: 'Frame code não encontrado' }};
                }}

                var frameCodeDoc = frameCode.contentDocument || frameCode.contentWindow.document;
                if (!frameCodeDoc) {{
                    return {{ success: false, error: 'Frame code contentDocument inacessível' }};
                }}

                // Passo 2: Procurar frame 'text' dentro de 'code' (POR NAME, não ID!)
                var frameText = frameCodeDoc.querySelector('frame[name="text"], iframe[name="text"]');
                var doc = frameCodeDoc;

                if (frameText) {{
                    doc = frameText.contentDocument || frameText.contentWindow.document;
                }} else {{
                    // Se não tem frame 'text', procurar primeiro frame/iframe
                    var frames = frameCodeDoc.querySelectorAll('frame, iframe');
                    if (frames.length > 0) {{
                        doc = frames[0].contentDocument || frames[0].contentWindow.document;
                    }}
                }}

                if (!doc) {{
                    return {{ success: false, error: 'Documento do frame interno inacessível' }};
                }}

                // Passo 3: Preencher datas (SIMPLES como Selenium)
                var campoInicial = doc.getElementById('Emissao1');
                if (!campoInicial) {{
                    return {{ success: false, error: 'Campo Emissao1 não encontrado' }};
                }}

                campoInicial.removeAttribute('readonly');
                campoInicial.value = '{data_inicial_str}';

                // Campo final (opcional)
                var campoFinal = doc.getElementById('Emissao23') || doc.getElementById('Emissao2');
                if (campoFinal) {{
                    campoFinal.removeAttribute('readonly');
                    campoFinal.value = '{data_final_str}';
                }}

                return {{
                    success: true,
                    data_inicial: campoInicial.value,
                    data_final: campoFinal ? campoFinal.value : 'não encontrado'
                }};

            }} catch(e) {{
                return {{ success: false, error: 'Exceção: ' + e.message }};
            }}
        }})();
        """

        resultado_raw = await self.tab.evaluate(script)

        # DEBUG: Verificar tipo
        print(f"[DEBUG] Tipo retornado (RAW): {type(resultado_raw)}")
        print(f"[DEBUG] Valor (RAW): {resultado_raw}")

        # Converter CDP para dict se necessário
        resultado = self.converter_cdp_para_dict(resultado_raw)
        print(f"[DEBUG] Após conversão CDP: {resultado}")

        if not isinstance(resultado, dict):
            print(f"[DEBUG] ⚠️ Ainda não é dict após conversão!")
            raise Exception(f"Não foi possível converter resultado para dict")

        if not resultado.get('success'):
            erro = resultado.get('error', 'Erro desconhecido')
            print(f"[DEBUG] ❌ Erro retornado pelo JavaScript: {erro}")

            # DEBUG ADICIONAL: Verificar o que há no frame
            print(f"[DEBUG] Verificando estrutura do frame...")
            debug_script = """
            (function() {
                var frameCode = document.getElementById('code');
                if (!frameCode) return { erro: 'sem frame code' };

                var frameCodeDoc = frameCode.contentDocument;
                if (!frameCodeDoc) return { erro: 'sem contentDocument' };

                var frameText = frameCodeDoc.getElementById('text');
                var frames = frameCodeDoc.querySelectorAll('frame, iframe');

                return {
                    temFrameText: frameText !== null,
                    totalFrames: frames.length,
                    nomesFrames: Array.from(frames).map(f => f.name || f.id || 'sem nome')
                };
            })();
            """
            debug_info = await self.tab.evaluate(debug_script)
            debug_info = self.converter_cdp_para_dict(debug_info)
            print(f"[DEBUG] Estrutura do frame: {debug_info}")

            raise Exception(f"Erro ao preencher datas: {erro}")

        print(f"[DEBUG] ✅ Data inicial preenchida: {data_inicial_str}")
        print(f"[DEBUG] ✅ Data final preenchida: {data_final_str}")
        await asyncio.sleep(1)

    async def marcar_checkbox_recomendacao(self, marcar: bool = True):
        """
        Marca ou desmarca o checkbox de recomendação de recompra - REPLICANDO LÓGICA SELENIUM

        No Selenium (linhas 729-766 do backup):
        - Já está no contexto do frame após mudar_para_frame_code()
        - Usa simples find_element() e click()
        - Verifica estado com is_selected()

        No Nodriver:
        - Precisa acessar frame via JavaScript
        - Mas mantém a MESMA lógica simples
        """
        acao = "MARCANDO" if marcar else "DESMARCANDO"
        print(f"\n[DEBUG] ========== {acao} CHECKBOX RECOMENDAÇÃO ==========")
        logger.info(f"[{self.nome}] {acao} checkbox...")

        try:
            print(f"[DEBUG] Procurando checkbox 'recomendacaoRecompraConfirmacao'...")

            # JavaScript SIMPLES seguindo padrão Selenium
            script = f"""
            (function() {{
                try {{
                    // Passo 1: Encontrar frame 'code'
                    var frameCode = document.getElementById('code');
                    if (!frameCode) {{
                        return {{ success: false, error: 'Frame code não encontrado' }};
                    }}

                    var frameCodeDoc = frameCode.contentDocument || frameCode.contentWindow.document;
                    if (!frameCodeDoc) {{
                        return {{ success: false, error: 'Frame code contentDocument inacessível' }};
                    }}

                    // Passo 2: Procurar frame 'text' dentro de 'code' (POR NAME, não ID!)
                    var frameText = frameCodeDoc.querySelector('frame[name="text"], iframe[name="text"]');
                    var doc = frameCodeDoc;

                    if (frameText) {{
                        doc = frameText.contentDocument || frameText.contentWindow.document;
                    }} else {{
                        // Se não tem frame 'text', procurar primeiro frame/iframe
                        var frames = frameCodeDoc.querySelectorAll('frame, iframe');
                        if (frames.length > 0) {{
                            doc = frames[0].contentDocument || frames[0].contentWindow.document;
                        }}
                    }}

                    if (!doc) {{
                        return {{ success: false, error: 'Documento do frame interno inacessível' }};
                    }}

                    // Passo 3: Encontrar checkbox (SIMPLES como Selenium)
                    var checkbox = doc.getElementById('recomendacaoRecompraConfirmacao');
                    if (!checkbox) {{
                        // Tentar por name (fallback)
                        checkbox = doc.querySelector('[name="recomendacaoRecompraConfirmacao"]');
                    }}

                    if (!checkbox) {{
                        return {{ success: false, error: 'Checkbox não encontrado' }};
                    }}

                    // Passo 4: Verificar estado e clicar se necessário
                    var estaMarcado = checkbox.checked;
                    var precisaClicar = {str(marcar).lower()} ? !estaMarcado : estaMarcado;

                    if (precisaClicar) {{
                        checkbox.click();
                        return {{
                            success: true,
                            acao: 'clicado',
                            estadoAnterior: estaMarcado,
                            estadoNovo: !estaMarcado
                        }};
                    }} else {{
                        return {{
                            success: true,
                            acao: 'ja_no_estado_correto',
                            estadoAtual: estaMarcado
                        }};
                    }}

                }} catch(e) {{
                    return {{ success: false, error: 'Exceção: ' + e.message }};
                }}
            }})();
            """

            resultado_raw = await self.tab.evaluate(script)

            # Converter CDP para dict
            resultado = self.converter_cdp_para_dict(resultado_raw)

            if not isinstance(resultado, dict):
                print(f"[DEBUG] ⚠️ JavaScript retornou tipo inesperado: {type(resultado_raw)}")
                print(f"[DEBUG] Valor: {resultado_raw}")
                raise Exception(f"JavaScript retornou tipo inválido")

            if not resultado.get('success'):
                erro = resultado.get('error', 'Erro desconhecido')
                print(f"[DEBUG] ❌ Erro: {erro}")
                raise Exception(f"Checkbox de recomendação: {erro}")

            # Resultado bem-sucedido
            acao_realizada = resultado.get('acao')

            if acao_realizada == 'clicado':
                estado_anterior = 'marcado' if resultado.get('estadoAnterior') else 'desmarcado'
                estado_novo = 'marcado' if resultado.get('estadoNovo') else 'desmarcado'
                print(f"[DEBUG] ✅ Checkbox clicado!")
                print(f"[DEBUG]   Estado: {estado_anterior} → {estado_novo}")
            else:
                estado_atual = 'marcado' if resultado.get('estadoAtual') else 'desmarcado'
                print(f"[DEBUG] ℹ️  Checkbox já estava {estado_atual} como esperado")

            await asyncio.sleep(1)

        except Exception as e:
            print(f"[DEBUG] ❌ Erro: {e}")
            raise

    async def clicar_pesquisar(self):
        """Clica no botão 'Pesquisar' - DENTRO DO FRAME 'code' - BUSCA INTELIGENTE"""
        self.verificar_pausa()

        print(f"\n[DEBUG] ========== CLICANDO EM PESQUISAR ==========")
        logger.info(f"[{self.nome}] Clicando em Pesquisar...")

        try:
            # SOLUÇÃO INTELIGENTE: Procurar botão em TODOS os frames até achar
            print(f"[DEBUG] Procurando botão Pesquisar em TODOS os frames disponíveis...")

            resultado_raw = await self.tab.evaluate("""
                (function() {
                    var frameCode = document.getElementById('code');
                    if (!frameCode) return { found: false, error: 'Frame code não existe' };

                    var frameDoc = frameCode.contentDocument;
                    if (!frameDoc) return { found: false, error: 'ContentDocument não acessível' };

                    // Primeiro: tentar frame 'text' por NAME (não ID!)
                    var frameText = frameDoc.querySelector('frame[name="text"], iframe[name="text"]');
                    if (frameText) {
                        var doc = frameText.contentDocument || frameText.contentWindow.document;
                        var botao = doc.getElementById('BtnSubmit') ||
                                   doc.querySelector('input[value="Pesquisar"]') ||
                                   doc.querySelector('[name="Consultar"]') ||
                                   doc.querySelector('input[type="button"][value*="Pesq"]');
                        if (botao) {
                            botao.click();
                            return { found: true, frameIndex: -1, frameName: 'text' };
                        }
                    }

                    // Segundo: procurar em TODOS os frames/iframes
                    var frames = frameDoc.querySelectorAll('frame, iframe');
                    for (var i = 0; i < frames.length; i++) {
                        try {
                            var frame = frames[i];
                            var doc = frame.contentDocument || frame.contentWindow.document;
                            if (!doc) continue;

                            var botao = doc.getElementById('BtnSubmit') ||
                                       doc.querySelector('input[value="Pesquisar"]') ||
                                       doc.querySelector('[name="Consultar"]') ||
                                       doc.querySelector('input[type="button"][value*="Pesq"]');
                            if (botao) {
                                botao.click();
                                return {
                                    found: true,
                                    frameIndex: i,
                                    frameName: frame.name || 'sem nome',
                                    frameSrc: (frame.src || '').substring(0, 60)
                                };
                            }
                        } catch(e) {
                            // Frame bloqueado por CORS, pular
                            continue;
                        }
                    }

                    return { found: false, error: 'Botão Pesquisar não encontrado em nenhum frame', totalFrames: frames.length };
                })();
            """)

            # Converter CDP para dict
            resultado = self.converter_cdp_para_dict(resultado_raw)

            if not resultado.get('found'):
                print(f"[DEBUG] ❌ Botão Pesquisar NÃO encontrado!")
                print(f"[DEBUG]   Erro: {resultado.get('error')}")
                print(f"[DEBUG]   Total de frames verificados: {resultado.get('totalFrames', 0)}")
                raise Exception("Botão Pesquisar não encontrado!")

            # Botão encontrado e clicado!
            frame_usado = resultado.get('frameName')
            frame_index = resultado.get('frameIndex')

            print(f"[DEBUG] ✅ Botão 'Pesquisar' ENCONTRADO e CLICADO!")
            print(f"[DEBUG]   Frame: {frame_usado} (índice: {frame_index})")
            if frame_index >= 0:
                print(f"[DEBUG]   SRC: {resultado.get('frameSrc')}")

            print(f"[DEBUG] Aguardando resultados carregarem...")
            await asyncio.sleep(5)

        except Exception as e:
            print(f"[DEBUG] ❌ Erro: {e}")
            raise

    async def selecionar_todos_resultados(self):
        """Marca o checkbox 'Selecionar Todos' - DENTRO DO FRAME 'code' - BUSCA INTELIGENTE"""
        self.verificar_pausa()

        print(f"\n[DEBUG] ========== SELECIONANDO TODOS OS RESULTADOS ==========")
        logger.info(f"[{self.nome}] Selecionando todos no formulário de resultados...")

        try:
            # SOLUÇÃO INTELIGENTE: Procurar checkbox em TODOS os frames até achar
            print(f"[DEBUG] Procurando checkbox 'Selecionar Todos' em TODOS os frames disponíveis...")

            resultado_raw = await self.tab.evaluate("""
                (function() {
                    var frameCode = document.getElementById('code');
                    if (!frameCode) return { found: false, error: 'Frame code não existe' };

                    var frameDoc = frameCode.contentDocument;
                    if (!frameDoc) return { found: false, error: 'ContentDocument não acessível' };

                    // Primeiro: tentar frame 'text' por NAME (não ID!)
                    var frameText = frameDoc.querySelector('frame[name="text"], iframe[name="text"]');
                    if (frameText) {
                        var doc = frameText.contentDocument || frameText.contentWindow.document;
                        var checkbox = doc.querySelector('[name="cSelecionarTodos"]') ||
                                      doc.getElementById('cSelecionarTodos');
                        if (checkbox) {
                            var estaMarcado = checkbox.checked;
                            if (!estaMarcado) {
                                checkbox.click();
                                return { found: true, frameIndex: -1, frameName: 'text', acao: 'clicado' };
                            } else {
                                return { found: true, frameIndex: -1, frameName: 'text', acao: 'ja_marcado' };
                            }
                        }
                    }

                    // Segundo: procurar em TODOS os frames/iframes
                    var frames = frameDoc.querySelectorAll('frame, iframe');
                    for (var i = 0; i < frames.length; i++) {
                        try {
                            var frame = frames[i];
                            var doc = frame.contentDocument || frame.contentWindow.document;
                            if (!doc) continue;

                            var checkbox = doc.querySelector('[name="cSelecionarTodos"]') ||
                                          doc.getElementById('cSelecionarTodos');
                            if (checkbox) {
                                var estaMarcado = checkbox.checked;
                                if (!estaMarcado) {
                                    checkbox.click();
                                    return {
                                        found: true,
                                        frameIndex: i,
                                        frameName: frame.name || 'sem nome',
                                        frameSrc: (frame.src || '').substring(0, 60),
                                        acao: 'clicado'
                                    };
                                } else {
                                    return {
                                        found: true,
                                        frameIndex: i,
                                        frameName: frame.name || 'sem nome',
                                        frameSrc: (frame.src || '').substring(0, 60),
                                        acao: 'ja_marcado'
                                    };
                                }
                            }
                        } catch(e) {
                            // Frame bloqueado por CORS, pular
                            continue;
                        }
                    }

                    return { found: false, error: 'Checkbox não encontrado em nenhum frame', totalFrames: frames.length };
                })();
            """)

            # Converter CDP para dict
            resultado = self.converter_cdp_para_dict(resultado_raw)

            if not resultado.get('found'):
                # Checkbox não encontrado - continuar sem erro (warning only)
                print(f"[DEBUG] ⚠️  Checkbox 'Selecionar Todos' NÃO encontrado!")
                print(f"[DEBUG]   Erro: {resultado.get('error')}")
                print(f"[DEBUG]   Total de frames verificados: {resultado.get('totalFrames', 0)}")
                print(f"[DEBUG] ⚠️  Continuando mesmo assim...")
            else:
                # Checkbox encontrado e processado
                frame_usado = resultado.get('frameName')
                frame_index = resultado.get('frameIndex')
                acao = resultado.get('acao')

                print(f"[DEBUG] ✅ Checkbox 'Selecionar Todos' ENCONTRADO!")
                print(f"[DEBUG]   Frame: {frame_usado} (índice: {frame_index})")
                if frame_index >= 0:
                    print(f"[DEBUG]   SRC: {resultado.get('frameSrc')}")

                if acao == 'clicado':
                    print(f"[DEBUG] ✅ Todos os itens selecionados!")
                else:
                    print(f"[DEBUG] ℹ️  Checkbox já estava marcado")

            await asyncio.sleep(2)

        except Exception as e:
            print(f"[DEBUG] ⚠️  Erro ao selecionar todos: {e}")
            print(f"[DEBUG] Tentando continuar mesmo assim...")
            await asyncio.sleep(2)

    async def verificar_e_resolver_recaptcha(self):
        """
        Verifica se há reCAPTCHA e aguarda extensão resolver
        REPLICANDO LÓGICA SELENIUM - COM DETECÇÃO DE NOVA JANELA!

        ORDEM CORRETA (Selenium linhas 889-940):
        1. Salva janela principal (linha 890)
        2. Aguarda 2s para ver se abre nova aba (linha 894)
        3. Verifica se len(window_handles) > 1 (linha 897)
        4. Se sim, INVESTIGA nova aba (linha 904-924) SEM MUDAR self.tab!
        5. Se NÃO é CAPTCHA em nova aba, VOLTA para principal (linha 926-930)
        6. DEPOIS verifica reCAPTCHA (linha 933-940)
        7. Clica botão "Confirmar" SE captcha_em_nova_aba (linha 1026)
        8. Fecha nova aba e volta para principal (linha 1064-1068)
        """
        print(f"\n[DEBUG] ========== VERIFICANDO reCAPTCHA ==========")

        try:
            # PASSO 1: PRIMEIRO salvar tab principal (Selenium linha 890)
            tab_principal = self.tab
            print(f"[DEBUG] Tab principal salva")

            # PASSO 2: AGUARDAR para ver se abre NOVA ABA (Selenium linha 894)
            print(f"[DEBUG] Aguardando 2s para ver se abre nova aba com CAPTCHA...")
            await asyncio.sleep(2)

            # PASSO 3: Verificar se abriu nova janela/aba (Selenium linha 897-900)
            total_tabs = len(self.browser.tabs)
            print(f"[DEBUG] Total de tabs abertas: {total_tabs}")

            tab_captcha = None
            captcha_em_nova_aba = False

            # CENÁRIO 1: CAPTCHA em NOVA ABA (Selenium linha 903-924)
            if total_tabs > 1:
                print(f"[DEBUG] ⚠️ NOVA ABA DETECTADA! Verificando se é CAPTCHA...")

                # IMPORTANTE: Investigar a nova aba SEM mudar self.tab ainda!
                for tab in self.browser.tabs:
                    if tab != tab_principal:
                        tab_captcha = tab
                        await asyncio.sleep(1)

                        # Pegar URL/título da nova aba (Selenium linha 914-917)
                        try:
                            url_atual = await tab.evaluate("window.location.href")
                            titulo_atual = await tab.evaluate("document.title")
                        except:
                            url_atual = "desconhecido"
                            titulo_atual = "desconhecido"

                        print(f"[DEBUG] URL da nova aba: {url_atual}")
                        print(f"[DEBUG] Título da nova aba: {titulo_atual}")

                        # Verificar se é página de CAPTCHA (Selenium linha 920-923)
                        if "captcha" in url_atual.lower() or "captcha" in titulo_atual.lower():
                            captcha_em_nova_aba = True
                            print(f"[DEBUG] ✅ CAPTCHA em NOVA ABA confirmado!")
                            # Agora SIM mudar self.tab para a aba de CAPTCHA
                            self.tab = tab_captcha
                            break
                        else:
                            # Verificar se tem botão "Confirmar" (indica CAPTCHA)
                            try:
                                tem_botao = await tab.evaluate("""
                                    (() => {
                                        return document.getElementById('prosseguir') !== null;
                                    })()
                                """)
                                if tem_botao:
                                    captcha_em_nova_aba = True
                                    print(f"[DEBUG] ✅ CAPTCHA em NOVA ABA confirmado (botão prosseguir encontrado)!")
                                    # Agora SIM mudar self.tab para a aba de CAPTCHA
                                    self.tab = tab_captcha
                                    break
                            except:
                                pass

            # CENÁRIO 2: NÃO é CAPTCHA em nova aba → VOLTAR para principal (Selenium linha 926-930)
            if not captcha_em_nova_aba:
                print(f"[DEBUG] Verificando CAPTCHA na tab principal...")
                # GARANTIR que self.tab está na principal
                self.tab = tab_principal
                await asyncio.sleep(1)

            # PASSO 4: AGORA verificar se TEM reCAPTCHA (Selenium linha 933-940)
            print(f"\n[DEBUG] Procurando iframe reCAPTCHA...")
            tem_recaptcha = await self.tab.evaluate("""
                (() => {
                    const iframes = document.querySelectorAll('iframe[src*="recaptcha"]');
                    return iframes.length > 0;
                })()
            """)

            if not tem_recaptcha:
                print(f"[DEBUG] ✅ Nenhum reCAPTCHA detectado")

                # Se tinha nova aba (mas não era CAPTCHA), fechar e voltar (Selenium linha 942-946)
                if tab_captcha and not captcha_em_nova_aba:
                    print(f"[DEBUG] Fechando aba extra e voltando para principal...")
                    await tab_captcha.close()
                    self.tab = tab_principal
                    print(f"[DEBUG] ✅ Voltou para tab principal")

                return False

            print(f"[DEBUG] ⚠️ reCAPTCHA DETECTADO!")
            print(f"[DEBUG] Aguardando extensão CapSolver resolver...")

            # PASSO 5: Aguardar extensão resolver CAPTCHA
            captcha_resolvido = await self.aguardar_extensao_resolver_captcha()

            if not captcha_resolvido:
                print(f"[DEBUG] ⚠️ CAPTCHA não foi resolvido")
                # Voltar para principal se estava em nova aba
                if captcha_em_nova_aba:
                    self.tab = tab_principal
                return False

            print(f"[DEBUG] ✅ CAPTCHA resolvido!")

            # PASSO 6: Clicar botão "Confirmar" SOMENTE se em nova aba (Selenium linha 1026-1063)
            if captcha_em_nova_aba:
                print(f"[DEBUG] CAPTCHA em nova aba - procurando botão 'Confirmar'...")
                await self.clicar_botao_confirmar()

                # PASSO 7: Fechar aba de CAPTCHA e voltar para principal (Selenium linha 1064-1068)
                print(f"[DEBUG] Fechando aba de CAPTCHA e voltando para principal...")
                await tab_captcha.close()
                self.tab = tab_principal
                print(f"[DEBUG] ✅ Voltou para tab principal")
                await asyncio.sleep(2)
            else:
                # CENÁRIO 2: CAPTCHA na mesma janela (comum no login)
                print(f"[DEBUG] CAPTCHA resolvido na mesma janela")
                print(f"[DEBUG] Não é necessário clicar em 'Confirmar'")

            return True

        except Exception as e:
            print(f"[DEBUG] Erro ao verificar reCAPTCHA: {e}")
            # SEMPRE garantir que voltou para tab principal
            try:
                self.tab = tab_principal
            except:
                pass
            return False

    async def clicar_botao_confirmar(self):
        """
        Clica no botão 'Confirmar' após CAPTCHA resolvido - REPLICANDO SELENIUM

        Selenium (linhas 1024-1063):
        - Procura por ID='prosseguir', NAME='prosseguir', value='Confirmar'
        - Clica via click() ou JavaScript se falhar
        """
        try:
            print(f"[DEBUG] Procurando botão 'Confirmar' em TODOS os frames...")

            # JavaScript para procurar e clicar no botão "Confirmar"
            script = """
            (function() {
                // Função helper para procurar em um documento
                function procurarBotao(doc) {
                    // Tentar múltiplos seletores (igual Selenium)
                    var botao = doc.getElementById('prosseguir') ||
                               doc.querySelector('[name="prosseguir"]') ||
                               doc.querySelector('input[value="Confirmar"]') ||
                               doc.querySelector('input[type="button"][onclick*="finalizar"]');
                    return botao;
                }

                // 1. Procurar na página principal
                var botao = procurarBotao(document);
                if (botao) {
                    botao.click();
                    return { found: true, location: 'main_page' };
                }

                // 2. Procurar em TODOS os iframes
                var iframes = document.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    try {
                        var iframe = iframes[i];
                        var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        if (!iframeDoc) continue;

                        botao = procurarBotao(iframeDoc);
                        if (botao) {
                            botao.click();
                            return { found: true, location: 'iframe_' + i };
                        }
                    } catch(e) {
                        // CORS bloqueado, pular
                        continue;
                    }
                }

                // 3. Procurar no frame 'code' (se existir)
                var frameCode = document.getElementById('code');
                if (frameCode) {
                    try {
                        var frameCodeDoc = frameCode.contentDocument || frameCode.contentWindow.document;
                        if (frameCodeDoc) {
                            botao = procurarBotao(frameCodeDoc);
                            if (botao) {
                                botao.click();
                                return { found: true, location: 'frame_code' };
                            }

                            // Procurar em frames internos do 'code'
                            var innerFrames = frameCodeDoc.querySelectorAll('frame, iframe');
                            for (var j = 0; j < innerFrames.length; j++) {
                                try {
                                    var innerDoc = innerFrames[j].contentDocument || innerFrames[j].contentWindow.document;
                                    if (!innerDoc) continue;

                                    botao = procurarBotao(innerDoc);
                                    if (botao) {
                                        botao.click();
                                        return { found: true, location: 'frame_code_inner_' + j };
                                    }
                                } catch(e) {
                                    continue;
                                }
                            }
                        }
                    } catch(e) {
                        // Ignorar
                    }
                }

                return { found: false, error: 'Botão Confirmar não encontrado' };
            })();
            """

            resultado_raw = await self.tab.evaluate(script)
            resultado = self.converter_cdp_para_dict(resultado_raw)

            if resultado.get('found'):
                location = resultado.get('location', 'desconhecido')
                print(f"[DEBUG] ✅ Botão 'Confirmar' ENCONTRADO e CLICADO!")
                print(f"[DEBUG]   Localização: {location}")
                await asyncio.sleep(2)
            else:
                print(f"[DEBUG] ⚠️ Botão 'Confirmar' não encontrado (pode não ser necessário)")
                print(f"[DEBUG]   Continuando mesmo assim...")

        except Exception as e:
            print(f"[DEBUG] ⚠️ Erro ao clicar botão Confirmar: {e}")
            print(f"[DEBUG] Continuando mesmo assim...")

    async def clicar_gerar_csv(self):
        """Clica no botão 'Gerar CSV' - DENTRO DO FRAME 'code' - BUSCA INTELIGENTE"""
        self.verificar_pausa()

        print(f"\n[DEBUG] ========== GERANDO CSV ==========")
        logger.info(f"[{self.nome}] Gerando CSV...")

        try:
            # SOLUÇÃO INTELIGENTE: Procurar botão em TODOS os frames até achar
            print(f"[DEBUG] Procurando botão 'Gerar CSV' em TODOS os frames disponíveis...")

            resultado_raw = await self.tab.evaluate("""
                (function() {
                    var frameCode = document.getElementById('code');
                    if (!frameCode) return { found: false, error: 'Frame code não existe' };

                    var frameDoc = frameCode.contentDocument;
                    if (!frameDoc) return { found: false, error: 'ContentDocument não acessível' };

                    // Primeiro: tentar frame 'text' por NAME (não ID!)
                    var frameText = frameDoc.querySelector('frame[name="text"], iframe[name="text"]');
                    if (frameText) {
                        var doc = frameText.contentDocument || frameText.contentWindow.document;
                        var botao = doc.getElementById('ImprimirCSV') ||
                                   doc.querySelector('[name="Imprimir"]') ||
                                   doc.querySelector('input[value="Gerar CSV"]');
                        if (botao) {
                            botao.click();
                            return { found: true, frameIndex: -1, frameName: 'text' };
                        }
                    }

                    // Segundo: procurar em TODOS os frames/iframes
                    var frames = frameDoc.querySelectorAll('frame, iframe');
                    for (var i = 0; i < frames.length; i++) {
                        try {
                            var frame = frames[i];
                            var doc = frame.contentDocument || frame.contentWindow.document;
                            if (!doc) continue;

                            var botao = doc.getElementById('ImprimirCSV') ||
                                       doc.querySelector('[name="Imprimir"]') ||
                                       doc.querySelector('input[value="Gerar CSV"]');
                            if (botao) {
                                botao.click();
                                return {
                                    found: true,
                                    frameIndex: i,
                                    frameName: frame.name || 'sem nome',
                                    frameSrc: (frame.src || '').substring(0, 60)
                                };
                            }
                        } catch(e) {
                            // Frame bloqueado por CORS, pular
                            continue;
                        }
                    }

                    return { found: false, error: 'Botão Gerar CSV não encontrado em nenhum frame', totalFrames: frames.length };
                })();
            """)

            # Converter CDP para dict
            resultado = self.converter_cdp_para_dict(resultado_raw)

            if not resultado.get('found'):
                print(f"[DEBUG] ❌ Botão 'Gerar CSV' NÃO encontrado!")
                print(f"[DEBUG]   Erro: {resultado.get('error')}")
                print(f"[DEBUG]   Total de frames verificados: {resultado.get('totalFrames', 0)}")
                raise Exception("Botão 'Gerar CSV' não encontrado!")

            # Botão encontrado e clicado!
            frame_usado = resultado.get('frameName')
            frame_index = resultado.get('frameIndex')

            print(f"[DEBUG] ✅ Botão 'Gerar CSV' ENCONTRADO e CLICADO!")
            print(f"[DEBUG]   Frame: {frame_usado} (índice: {frame_index})")
            if frame_index >= 0:
                print(f"[DEBUG]   SRC: {resultado.get('frameSrc')}")

            # Aguardar possível CAPTCHA
            await asyncio.sleep(3)
            await self.verificar_e_resolver_recaptcha()

            print(f"[DEBUG] Aguardando download do CSV...")
            await asyncio.sleep(10)

        except Exception as e:
            print(f"[DEBUG] ❌ Erro: {e}")
            raise

    def renomear_csv_baixado(self, com_checkbox_recompra: bool):
        """Renomeia o CSV baixado para o padrão correto"""
        import glob

        print(f"\n[DEBUG] ========== RENOMEANDO CSV ==========")

        try:
            # Aguardar download finalizar
            print(f"[DEBUG] Aguardando download finalizar...")
            max_tentativas = 30

            for tentativa in range(max_tentativas):
                crdownload = glob.glob(os.path.join(self.download_dir, "*.crdownload"))
                if not crdownload:
                    print(f"[DEBUG] ✅ Download finalizado em {tentativa + 1}s")
                    break
                time.sleep(1)

            time.sleep(2)

            # Procurar CSV recém-baixado
            print(f"[DEBUG] Procurando CSV recém-baixado...")
            csvs = glob.glob(os.path.join(self.download_dir, "*.csv"))

            if not csvs:
                print(f"[DEBUG] ⚠️ Nenhum CSV encontrado!")
                return None

            # Pegar o mais recente
            arquivo_path = max(csvs, key=os.path.getmtime)
            idade = time.time() - os.path.getmtime(arquivo_path)

            print(f"[DEBUG] CSV encontrado: {os.path.basename(arquivo_path)} ({idade:.1f}s)")

            # Renomear
            data_atual = datetime.now().strftime("%Y_%m_%d")

            if com_checkbox_recompra:
                nome_novo = f"titulos_abertos_marcados_recompras_{data_atual}.csv"
            else:
                nome_novo = f"titulos_abertos_{data_atual}.csv"

            caminho_destino = os.path.join(self.download_dir, nome_novo)

            # Se já existe, adicionar timestamp
            if os.path.exists(caminho_destino):
                timestamp = datetime.now().strftime("%H%M%S")
                if com_checkbox_recompra:
                    nome_novo = f"titulos_abertos_marcados_recompras_{data_atual}_{timestamp}.csv"
                else:
                    nome_novo = f"titulos_abertos_{data_atual}_{timestamp}.csv"
                caminho_destino = os.path.join(self.download_dir, nome_novo)

            os.rename(arquivo_path, caminho_destino)
            print(f"[DEBUG] ✅ CSV salvo como: {nome_novo}")
            logger.info(f"[{self.nome}] CSV salvo: {nome_novo}")

            return caminho_destino

        except Exception as e:
            print(f"[DEBUG] ⚠️ Erro ao renomear CSV: {e}")
            logger.warning(f"[{self.nome}] Erro ao renomear CSV: {e}")
            return None

    async def executar_etapa_com_retry(self, nome_etapa: str, funcao_etapa, *args, **kwargs):
        """
        Executa uma etapa com retry automático em caso de erro

        Args:
            nome_etapa: Nome descritivo da etapa (ex: "Preencher datas")
            funcao_etapa: Função assíncrona a executar
            *args, **kwargs: Argumentos para a função

        Returns:
            Resultado da função ou None se pulada pelo usuário
        """
        max_tentativas = 3

        for tentativa in range(1, max_tentativas + 1):
            try:
                print(f"\n[ETAPA] {nome_etapa} (tentativa {tentativa}/{max_tentativas})")
                resultado = await funcao_etapa(*args, **kwargs)
                print(f"[ETAPA] ✅ {nome_etapa} concluída!")
                return resultado

            except Exception as e:
                print(f"[ETAPA] ❌ Erro em '{nome_etapa}': {e}")
                logger.error(f"[{self.nome}] Erro na etapa '{nome_etapa}' (tentativa {tentativa}): {e}", exc_info=True)

                if tentativa < max_tentativas:
                    # Ainda há tentativas restantes
                    print(f"[ETAPA] ⏳ Aguardando 3 segundos antes de tentar novamente...")
                    await asyncio.sleep(3)
                    continue
                else:
                    # Esgotou todas as tentativas
                    print(f"\n{'='*80}")
                    print(f"⚠️  FALHA NA ETAPA: {nome_etapa}")
                    print(f"⚠️  Tentativas esgotadas ({max_tentativas})")
                    print(f"")
                    print(f"📋 OPÇÕES:")
                    print(f"   [R] - TENTAR NOVAMENTE (mais 3 tentativas)")
                    print(f"   [P] - PULAR esta etapa e continuar")
                    print(f"   [V] - VOLTAR para etapa anterior")
                    print(f"   [Q] - PARAR execução completamente")
                    print(f"{'='*80}\n")

                    # Aguardar resposta do usuário
                    while True:
                        resposta = input(">>> Escolha uma opção [R/P/V/Q]: ").strip().upper()

                        if resposta == 'R':
                            # Tentar novamente - recursivo com reset de contador
                            print(f"\n[ETAPA] 🔄 Tentando novamente '{nome_etapa}'...")
                            return await self.executar_etapa_com_retry(nome_etapa, funcao_etapa, *args, **kwargs)

                        elif resposta == 'P':
                            # Pular etapa
                            print(f"\n[ETAPA] ⏭️  Pulando etapa '{nome_etapa}'...")
                            logger.warning(f"[{self.nome}] Etapa '{nome_etapa}' pulada pelo usuário")
                            return None

                        elif resposta == 'V':
                            # Voltar - lançar exceção especial
                            print(f"\n[ETAPA] ⏮️  Voltando para etapa anterior...")
                            raise VoltarEtapaAnteriorException(f"Usuário solicitou voltar da etapa: {nome_etapa}")

                        elif resposta == 'Q':
                            # Parar tudo
                            print(f"\n[ETAPA] ⏹️  Parando execução...")
                            self.parar = True
                            raise Exception("Execução parada pelo usuário após erro")

                        else:
                            print("⚠️ Opção inválida! Use R, P, V ou Q")

    async def aguardar_5_segundos(self):
        """Helper para aguardar 5 segundos - seguindo padrão Selenium"""
        print(f"[DEBUG] Aguardando 5 segundos para página carregar...")
        await asyncio.sleep(5)
        print(f"[DEBUG] ✅ Aguardo concluído")

    async def executar_extracao_completa(self, com_checkbox_recompra: bool):
        """
        Executa uma extração completa (com ou sem checkbox marcado)
        COM SISTEMA DE RECUPERAÇÃO DE ERROS INTELIGENTE
        """
        tipo = "COM CHECKBOX RECOMPRA" if com_checkbox_recompra else "SEM CHECKBOX RECOMPRA"
        print(f"\n{'#'*80}")
        print(f"# EXECUTANDO EXTRAÇÃO: {tipo}")
        print(f"{'#'*80}\n")
        logger.info(f"[{self.nome}] Executando extração: {tipo}")

        # IMPORTANTE: SEGUIR EXATAMENTE A LÓGICA DO SELENIUM (linhas 1558-1578 do backup)
        try:
            # ETAPA 1: Carregar página (linha 1558)
            await self.executar_etapa_com_retry(
                "Carregar página de títulos",
                self.navegar_para_titulos_abertos
            )

            # ETAPA 2: Verificar CAPTCHA ANTES de mudar para frames (linha 1561-1564)
            captcha_resolvido = await self.executar_etapa_com_retry(
                "Verificar reCAPTCHA (página inicial)",
                self.verificar_e_resolver_recaptcha
            )

            # SE resolveu CAPTCHA, recarregar página (linha 1564 do Selenium)
            if captcha_resolvido:
                await self.executar_etapa_com_retry(
                    "Recarregar página após CAPTCHA",
                    self.navegar_para_titulos_abertos
                )

            # ETAPA 3: Mudar para frames (linha 1566 do Selenium)
            await self.executar_etapa_com_retry(
                "Verificar e aguardar frames prontos",
                self.verificar_e_aguardar_frames_prontos
            )

            # ETAPA 4: Preencher datas (linha 1567)
            await self.executar_etapa_com_retry(
                "Preencher datas",
                self.preencher_datas
            )

            # ETAPA 5: Marcar checkbox (linha 1568)
            await self.executar_etapa_com_retry(
                "Marcar/desmarcar checkbox recomendação",
                self.marcar_checkbox_recomendacao,
                com_checkbox_recompra
            )

            # ETAPA 6: Clicar pesquisar (linha 1569)
            await self.executar_etapa_com_retry(
                "Clicar em Pesquisar",
                self.clicar_pesquisar
            )

            # ETAPA 7: Verificar CAPTCHA APÓS pesquisar (linha 1572-1575)
            captcha_resolvido = await self.executar_etapa_com_retry(
                "Verificar reCAPTCHA (após pesquisa)",
                self.verificar_e_resolver_recaptcha
            )

            # SE resolveu CAPTCHA, voltar para frames (linha 1575 do Selenium)
            if captcha_resolvido:
                await self.executar_etapa_com_retry(
                    "Voltar para frames após CAPTCHA",
                    self.verificar_e_aguardar_frames_prontos
                )

            # ETAPA 8: Selecionar todos (linha 1577)
            await self.executar_etapa_com_retry(
                "Selecionar todos os resultados",
                self.selecionar_todos_resultados
            )

            # ETAPA 9: Gerar CSV (linha 1578)
            await self.executar_etapa_com_retry(
                "Clicar em Gerar CSV",
                self.clicar_gerar_csv
            )

        except VoltarEtapaAnteriorException as e:
            # Usuário solicitou voltar - mas como agora é sequencial, não tem como voltar
            print(f"\n[CONTROLE] ⚠️  Voltar não é suportado no modo sequencial")
            logger.warning(f"[{self.nome}] Tentativa de voltar (não suportado)")
            raise

        except Exception as e:
            # Erro não tratado - propagar
            print(f"\n[ERRO] ❌ Erro crítico não tratado: {e}")
            logger.error(f"[{self.nome}] Erro crítico na extração {tipo}: {e}", exc_info=True)
            raise

        # Todas as etapas concluídas - renomear CSV
        print(f"\n[EXTRAÇÃO] 📥 Renomeando arquivo CSV baixado...")
        arquivo_salvo = self.renomear_csv_baixado(com_checkbox_recompra)

        if arquivo_salvo:
            print(f"\n[DEBUG] ✅ Extração {tipo} concluída!")
            print(f"[DEBUG] 📄 Arquivo: {os.path.basename(arquivo_salvo)}")
            logger.info(f"[{self.nome}] ✅ Extração {tipo} concluída - {os.path.basename(arquivo_salvo)}")
        else:
            print(f"\n[DEBUG] ⚠️ Extração {tipo} concluída, mas CSV não foi renomeado")
            logger.warning(f"[{self.nome}] ⚠️ Extração {tipo} concluída, mas CSV não foi renomeado")

        return True

    async def processar(self, modo_simulacao=False):
        """Método principal de processamento"""
        inicio = now_br()
        print(f"\n{'='*80}")
        print(f"PROCESSADOR - TÍTULOS ABERTOS E MARCADOS RECOMPRAS (v26.0)")
        print(f"100% NODRIVER ASYNC - ANTI-DETECÇÃO NATIVA")
        print(f"{'='*80}\n")
        logger.info(f"[{self.nome}] ========== INICIANDO CICLO CONTÍNUO ==========")

        if modo_simulacao:
            return {"success": True, "mensagem": "Simulação"}

        try:
            # Iniciar listener de teclado
            self.listener_thread = threading.Thread(target=self.escutar_teclado, daemon=True)
            self.listener_thread.start()
            logger.info(f"[{self.nome}] Thread de controle de teclado iniciada")

            # Iniciar navegador e fazer login
            await self.iniciar_navegador()
            await self.fazer_login_automatico()

            # Loop infinito de extrações
            ciclo = 1
            while not self.parar:
                self.verificar_pausa()

                if self.parar:
                    break

                print(f"\n{'='*80}")
                print(f"CICLO #{ciclo} - {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*80}\n")
                logger.info(f"[{self.nome}] ========== CICLO #{ciclo} ==========")

                # EXTRAÇÃO 1: COM checkbox marcado
                print(f"\n[CICLO {ciclo}] ETAPA 1/2: Extraindo COM checkbox recompra...")
                self.verificar_pausa()
                if not self.parar:
                    await self.executar_extracao_completa(com_checkbox_recompra=True)

                # EXTRAÇÃO 2: SEM checkbox marcado
                print(f"\n[CICLO {ciclo}] ETAPA 2/2: Extraindo SEM checkbox recompra...")
                self.verificar_pausa()
                if not self.parar:
                    await self.executar_extracao_completa(com_checkbox_recompra=False)

                # Aguardar 60 segundos
                if not self.parar:
                    print(f"\n{'='*80}")
                    print(f"✅ CICLO #{ciclo} CONCLUÍDO!")
                    print(f"⏳ Aguardando 60 segundos para próximo ciclo...")
                    print(f"{'='*80}\n")
                    logger.info(f"[{self.nome}] ✅ Ciclo #{ciclo} concluído, aguardando 60s...")

                    for _ in range(60):
                        if self.parar:
                            break
                        self.verificar_pausa()
                        time.sleep(1)

                    ciclo += 1

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
            return {"success": False, "mensagem": str(e)}

        finally:
            if self.browser:
                await close_browser(self.browser)


def processar_titulos_abertos_e_marcados_recompras(modo_simulacao: bool = False) -> dict:
    """Função wrapper para executar o processador"""
    processador = ProcessadorTitulosAbertosEMarcadosRecompras()
    return asyncio.run(processador.processar(modo_simulacao=modo_simulacao))


if __name__ == "__main__":
    resultado = processar_titulos_abertos_e_marcados_recompras()
    print(f"\n{'='*80}")
    print("RESULTADO FINAL:", "✅ SUCESSO" if resultado["success"] else "❌ FALHA")
    print("Mensagem:", resultado.get("mensagem"))
    print("="*80 + "\n")
