#!/usr/bin/env python3
# =============================================================================================
# ARQUIVO: relatorio_titulos_aberto.py
# VERSÃO: v1.0 - NOVO PROCESSADOR
# DESCRIÇÃO: Extrai relatório de títulos abertos do SmartSecurities
# URL: https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php
# DISPLAY: :2 (VNC porta 6081)
# API: Porta 6091
# =============================================================================================

import os
import sys
import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import glob

# Nodriver imports
try:
    import nodriver as uc
    from nodriver import Browser, Tab
    NODRIVER_AVAILABLE = True
except ImportError:
    NODRIVER_AVAILABLE = False
    print("⚠️ Nodriver não instalado. Execute: pip install nodriver")
    sys.exit(1)

from src.common.nodriver_utils import init_browser
from src.core.logging_config import get_logger
from src.common.notification_utils import enviar_alerta_erro_critico
from src.common.captcha_solver import CapSolverAPI

# =============================================================================================
# CONFIGURAÇÕES
# =============================================================================================

load_dotenv()

logger = get_logger(__name__)

# URLs
URL_LOGIN = "https://www.smartsecurities.com.br/smartsecurities/"
URL_TITULOS = "https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php"

# Diretórios
DOWNLOAD_DIR = Path("data/raw_inputs/")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Credenciais
SMART_EMAIL = os.getenv("USUARIO_SITE_SMART")
SMART_PASSWORD = os.getenv("SENHA_SITE_SMART")
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY")
SERVER_IP = os.getenv("SERVER_IP", "3.148.126.73")

# Timeouts
TIMEOUT_DOWNLOAD = 30  # segundos
INTERVALO_LOOP = 300  # 5 minutos entre extrações

# =============================================================================================
# PROCESSADOR
# =============================================================================================

class ProcessadorTitulosAberto:
    """Processador para extração de títulos abertos - 100% Nodriver Async"""

    def __init__(self):
        self.nome = "titulos_aberto"
        self.browser: Browser = None
        self.tab: Tab = None
        self.display = os.environ.get('DISPLAY', ':2')  # Display :2 (diferente do deságio)
        self.capsolver = CapSolverAPI(CAPSOLVER_API_KEY)
        self.download_dir = str(DOWNLOAD_DIR.absolute())

        # Controle de execução
        self.parar = False

        logger.info(f"[{self.nome}] Processador inicializado - Display {self.display}")

    def converter_cdp_para_dict(self, resultado_cdp):
        """
        Converte resultado CDP (Chrome DevTools Protocol) para dict Python
        CDP retorna: [['key1', {'type': 'type', 'value': val}], ['key2', ...]]
        Precisa virar: {'key1': val, 'key2': val, ...}
        """
        if isinstance(resultado_cdp, dict):
            return resultado_cdp

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

    # =========================================================================================
    # ETAPA 1: LOGIN (COPIADO DO relatorio_operacao_desagio.py)
    # =========================================================================================

    async def fazer_login(self):
        """Faz login no SmartSecurities - COPIADO DO CÓDIGO DESAGIO"""
        print(f"\n{'='*80}")
        print(f"🔐 ETAPA 1: LOGIN NO SMARTSECURITIES")
        print(f"{'='*80}\n")

        logger.info(f"[{self.nome}] Iniciando login...")

        try:
            print(f"[LOGIN] Abrindo página de login...")
            self.tab = await self.browser.get(URL_LOGIN)
            await asyncio.sleep(3)

            print(f"[LOGIN] Aguardando iframe de login carregar...")
            iframe_carregado = False
            max_tentativas = 20
            tentativa = 0

            while not iframe_carregado and tentativa < max_tentativas:
                tentativa += 1
                print(f"[LOGIN] Tentativa {tentativa}/{max_tentativas}")

                check_iframe = """
                (() => {
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        if (iframe.src && iframe.src.includes('loginsec.php')) {
                            return { found: true };
                        }
                    }
                    return { found: false };
                })();
                """

                resultado_raw = await self.tab.evaluate(check_iframe)
                resultado = self.converter_cdp_para_dict(resultado_raw)

                if resultado and resultado.get('found'):
                    print(f"[LOGIN] ✅ Iframe encontrado")
                    iframe_carregado = True
                    break

                await asyncio.sleep(2)

            if not iframe_carregado:
                raise Exception("Iframe de login não carregou")

            await asyncio.sleep(3)

            print(f"[LOGIN] Preenchendo credenciais...")

            script_preencher = f"""
            (() => {{
                const iframes = document.querySelectorAll('iframe');
                let iframeLogin = null;

                for (const iframe of iframes) {{
                    if (iframe.src && iframe.src.includes('loginsec.php')) {{
                        iframeLogin = iframe;
                        break;
                    }}
                }}

                if (!iframeLogin && iframes.length > 0) {{
                    iframeLogin = iframes[0];
                }}

                if (!iframeLogin) return {{ success: false, error: 'Iframe não encontrado' }};

                const iframeDoc = iframeLogin.contentDocument || iframeLogin.contentWindow.document;
                if (!iframeDoc) return {{ success: false, error: 'contentDocument não acessível' }};

                const campoEmail = iframeDoc.getElementById('fEmail') || iframeDoc.querySelector('[name="fEmail"]');
                const campoSenha = iframeDoc.getElementById('fPassword') || iframeDoc.querySelector('[name="fPassword"]');

                if (!campoEmail || !campoSenha) return {{ success: false, error: 'Campos não encontrados' }};

                campoEmail.value = '';
                campoEmail.value = '{SMART_EMAIL}';
                campoSenha.value = '';
                campoSenha.value = '{SMART_PASSWORD}';

                return {{ success: true }};
            }})();
            """

            resultado_raw = await self.tab.evaluate(script_preencher)
            resultado = self.converter_cdp_para_dict(resultado_raw)

            # Tratar ExceptionDetails (quando JavaScript falha)
            if hasattr(resultado, '__class__') and resultado.__class__.__name__ == 'ExceptionDetails':
                raise Exception(f"JavaScript falhou ao preencher credenciais: {resultado}")

            if not resultado or not resultado.get('success'):
                raise Exception("Falha ao preencher credenciais")

            print(f"[LOGIN] ✅ Credenciais preenchidas")
            await asyncio.sleep(1)

            print(f"[LOGIN] Clicando no botão OK...")

            script_clicar = """
            (() => {
                const iframes = document.querySelectorAll('iframe');
                for (const iframe of iframes) {
                    if (iframe.src && iframe.src.includes('loginsec.php')) {
                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        const botaoOK = iframeDoc.getElementById('OK') || iframeDoc.querySelector('[name="OK"]');
                        if (botaoOK) {
                            botaoOK.click();
                            return { success: true };
                        }
                    }
                }
                return { success: false, error: 'Botão OK não encontrado' };
            })();
            """

            resultado_raw = await self.tab.evaluate(script_clicar)
            resultado = self.converter_cdp_para_dict(resultado_raw)

            if not resultado or not resultado.get('success'):
                raise Exception("Falha ao clicar no botão OK")

            print(f"[LOGIN] ✅ Botão OK clicado")

            print(f"[LOGIN] Aguardando CAPTCHA aparecer...")
            await asyncio.sleep(3)

            print(f"[LOGIN] Resolvendo CAPTCHA...")
            site_url = await self.tab.evaluate("window.location.href")
            captcha_resolvido = await self.capsolver.resolver_recaptcha_automatico(self.tab, site_url)

            if not captcha_resolvido:
                raise Exception("CAPTCHA não foi resolvido")

            print(f"[LOGIN] ✅ CAPTCHA resolvido!")

            print(f"[LOGIN] Clicando no botão OK final...")
            await asyncio.sleep(2)

            resultado_raw = await self.tab.evaluate(script_clicar)
            resultado = self.converter_cdp_para_dict(resultado_raw)

            print(f"[LOGIN] Aguardando redirecionamento...")
            await asyncio.sleep(5)

            url_atual = self.tab.url
            if 'login' not in url_atual.lower():
                print(f"[LOGIN] ✅ Login realizado com sucesso!")
                logger.info(f"[{self.nome}] Login bem-sucedido")
                return True
            else:
                raise Exception("Login falhou - ainda na página de login")

        except Exception as e:
            logger.error(f"[{self.nome}] Erro no login: {e}", exc_info=True)
            raise

    # =========================================================================================
    # ETAPA 2: NAVEGAR PARA TÍTULOS ABERTOS
    # =========================================================================================

    async def navegar_para_titulos_abertos(self):
        """Navega para página de títulos em aberto"""
        print(f"\n{'='*80}")
        print(f"🌐 ETAPA 2: NAVEGANDO PARA TÍTULOS ABERTOS")
        print(f"{'='*80}\n")

        logger.info(f"[{self.nome}] Carregando títulos em aberto...")

        try:
            print(f"[NAVEGAÇÃO] Carregando página via JavaScript...")
            script = f"document.getElementById('code').src = '{URL_TITULOS}';"
            await self.tab.evaluate(script)

            print(f"[NAVEGAÇÃO] Aguardando página carregar...")
            await asyncio.sleep(5)

            print(f"[NAVEGAÇÃO] ✅ Página carregada")
            logger.info(f"[{self.nome}] Navegou para títulos abertos")

        except Exception as e:
            logger.error(f"[{self.nome}] Erro ao navegar: {e}", exc_info=True)
            raise

    # =========================================================================================
    # ETAPA 3: VERIFICAR CAPTCHA
    # =========================================================================================

    async def verificar_e_resolver_recaptcha(self):
        """Verifica e resolve reCAPTCHA se necessário"""
        print(f"\n{'='*80}")
        print(f"🔍 ETAPA 3: VERIFICANDO reCAPTCHA")
        print(f"{'='*80}\n")

        try:
            tab_principal = self.tab
            print(f"[CAPTCHA] Tab principal salva")

            print(f"[CAPTCHA] Aguardando 2s para ver se abre nova aba...")
            await asyncio.sleep(2)

            total_tabs = len(self.browser.tabs)
            print(f"[CAPTCHA] Total de tabs abertas: {total_tabs}")

            tab_captcha = None
            captcha_em_nova_aba = False

            if total_tabs > 1:
                print(f"[CAPTCHA] ⚠️ NOVA ABA DETECTADA!")

                for tab in self.browser.tabs:
                    if tab != tab_principal:
                        tab_captcha = tab
                        await asyncio.sleep(1)

                        try:
                            url_atual = await tab.evaluate("window.location.href")
                            titulo_atual = await tab.evaluate("document.title")
                        except:
                            url_atual = "desconhecido"
                            titulo_atual = "desconhecido"

                        print(f"[CAPTCHA] URL: {url_atual}")

                        if "captcha" in url_atual.lower() or "captcha" in titulo_atual.lower():
                            captcha_em_nova_aba = True
                            print(f"[CAPTCHA] ✅ CAPTCHA em nova aba confirmado!")
                            self.tab = tab_captcha
                            break
                        else:
                            try:
                                tem_botao = await tab.evaluate("(() => { return document.getElementById('prosseguir') !== null; })()")
                                if tem_botao:
                                    captcha_em_nova_aba = True
                                    print(f"[CAPTCHA] ✅ CAPTCHA em nova aba (botão prosseguir)!")
                                    self.tab = tab_captcha
                                    break
                            except:
                                pass

            if not captcha_em_nova_aba:
                print(f"[CAPTCHA] Verificando na tab principal...")
                self.tab = tab_principal
                await asyncio.sleep(1)

            print(f"[CAPTCHA] Procurando iframe reCAPTCHA...")
            tem_recaptcha = await self.tab.evaluate("(() => { const iframes = document.querySelectorAll('iframe[src*=\"recaptcha\"]'); return iframes.length > 0; })()")

            if not tem_recaptcha:
                print(f"[CAPTCHA] ✅ Nenhum reCAPTCHA detectado")

                if tab_captcha and not captcha_em_nova_aba:
                    await tab_captcha.close()
                    self.tab = tab_principal

                return False

            print(f"[CAPTCHA] ⚠️ reCAPTCHA DETECTADO!")
            print(f"[CAPTCHA] Resolvendo via CapSolver...")

            site_url = await self.tab.evaluate("window.location.href")
            captcha_resolvido = await self.capsolver.resolver_recaptcha_automatico(self.tab, site_url)

            if not captcha_resolvido:
                print(f"[CAPTCHA] ⚠️ Não foi resolvido")
                if captcha_em_nova_aba:
                    self.tab = tab_principal
                return False

            print(f"[CAPTCHA] ✅ CAPTCHA resolvido!")

            if captcha_em_nova_aba:
                print(f"[CAPTCHA] Procurando botão Confirmar...")
                await self.clicar_botao_confirmar()

                await tab_captcha.close()
                self.tab = tab_principal
                print(f"[CAPTCHA] ✅ Voltou para tab principal")
                await asyncio.sleep(2)

            return True

        except Exception as e:
            print(f"[CAPTCHA] Erro: {e}")
            try:
                self.tab = tab_principal
            except:
                pass
            return False

    async def clicar_botao_confirmar(self):
        """Clica no botão 'Confirmar' após CAPTCHA"""
        try:
            script = """
            (function() {
                function procurar(doc) {
                    return doc.getElementById('prosseguir') ||
                           doc.querySelector('[name="prosseguir"]') ||
                           doc.querySelector('input[value="Confirmar"]');
                }
                var botao = procurar(document);
                if (botao) { botao.click(); return { found: true }; }
                return { found: false };
            })();
            """

            resultado_raw = await self.tab.evaluate(script)
            resultado = self.converter_cdp_para_dict(resultado_raw)

            if resultado.get('found'):
                print(f"[CAPTCHA] ✅ Botão Confirmar clicado")
                await asyncio.sleep(2)

        except Exception as e:
            print(f"[CAPTCHA] Erro ao clicar confirmar: {e}")

    # =========================================================================================
    # ETAPA 4: VERIFICAR FRAMES PRONTOS
    # =========================================================================================

    async def verificar_e_aguardar_frames_prontos(self):
        """Verifica se frames estão acessíveis"""
        print(f"\n{'='*80}")
        print(f"📋 ETAPA 4: VERIFICANDO FRAMES")
        print(f"{'='*80}\n")

        max_tentativas = 10

        for tentativa in range(1, max_tentativas + 1):
            try:
                resultado = await self.tab.evaluate("""
                    (function() {
                        var frameCode = document.getElementById('code');
                        if (!frameCode) return { success: false, retry: true };

                        var frameCodeDoc = frameCode.contentDocument;
                        if (!frameCodeDoc) return { success: false, retry: true };

                        var frameText = frameCodeDoc.querySelector('frame[name="text"]');
                        var frameInterno = null;

                        if (frameText) {
                            frameInterno = frameText.contentDocument;
                        }

                        if (!frameInterno) return { success: false, retry: true };

                        var campoEmissao1 = frameInterno.getElementById('Emissao1');

                        return {
                            success: true,
                            temCampoEmissao1: campoEmissao1 !== null
                        };
                    })();
                """)

                resultado = self.converter_cdp_para_dict(resultado)

                if resultado.get('success'):
                    print(f"[FRAMES] ✅ Frames prontos!")
                    await asyncio.sleep(2)
                    return True

                if tentativa < max_tentativas:
                    print(f"[FRAMES] ⏳ Tentativa {tentativa}/{max_tentativas}")
                    await asyncio.sleep(1)

            except Exception as e:
                if tentativa < max_tentativas:
                    await asyncio.sleep(1)
                else:
                    raise

        raise Exception("Frames não ficaram prontos")

    # =========================================================================================
    # ETAPA 5: PREENCHER DATAS
    # =========================================================================================

    async def preencher_datas(self):
        """Preenche campos de data usando APPROACH 3: Simular digitação humana via clicks + backspace + type"""
        print(f"\n{'='*80}")
        print(f"📝 ETAPA 5: PREENCHENDO DATAS (Simulação Humana)")
        print(f"{'='*80}\n")

        import random

        data_atual = datetime.now()
        data_inicial = data_atual - timedelta(days=365)
        data_inicial_str = data_inicial.strftime("%d/%m/%Y")
        data_final_str = data_atual.strftime("%d/%m/%Y")

        print(f"[DATAS] Inicial: {data_inicial_str}")
        print(f"[DATAS] Final: {data_final_str}")

        try:
            # Passo 1: Focar no campo Emissao1 via JavaScript (para obter posição)
            print(f"[DATAS] Localizando campo Emissao1...")

            script_focar = """
            (function() {
                try {
                    var frameCode = document.getElementById('code');
                    if (!frameCode) return { success: false, error: 'Frame code não encontrado' };

                    var frameCodeDoc = frameCode.contentDocument || frameCode.contentWindow.document;
                    if (!frameCodeDoc) return { success: false, error: 'Frame code inacessível' };

                    var frameText = frameCodeDoc.querySelector('frame[name="text"], iframe[name="text"]');
                    var doc = frameCodeDoc;

                    if (frameText) {
                        doc = frameText.contentDocument || frameText.contentWindow.document;
                    } else {
                        var frames = frameCodeDoc.querySelectorAll('frame, iframe');
                        if (frames.length > 0) {
                            doc = frames[0].contentDocument || frames[0].contentWindow.document;
                        }
                    }

                    if (!doc) return { success: false, error: 'Documento interno inacessível' };

                    var campoInicial = doc.getElementById('Emissao1');
                    if (!campoInicial) return { success: false, error: 'Campo Emissao1 não encontrado' };

                    // Remover readonly e disabled
                    campoInicial.removeAttribute('readonly');
                    campoInicial.removeAttribute('disabled');

                    // Focar no campo
                    campoInicial.focus();
                    campoInicial.click();

                    // Selecionar todo texto existente
                    campoInicial.select();

                    return { success: true, valorAtual: campoInicial.value };

                } catch(e) {
                    return { success: false, error: 'Exceção: ' + e.message };
                }
            })();
            """

            resultado = self.converter_cdp_para_dict(await self.tab.evaluate(script_focar))

            if not resultado.get('success'):
                erro = resultado.get('error', 'Erro desconhecido')
                print(f"[DATAS] ❌ Erro ao focar campo: {erro}")
                raise Exception(f"Erro ao focar campo: {erro}")

            print(f"[DATAS] ✅ Campo focado (valor atual: '{resultado.get('valorAtual', '')}')")
            await asyncio.sleep(0.5)

            # Passo 2: Limpar campo (Ctrl+A + Delete)
            print(f"[DATAS] Limpando campo...")
            await self.tab.send('\x01')  # Ctrl+A (selecionar tudo)
            await asyncio.sleep(0.1)
            await self.tab.send('\x08')  # Backspace
            await asyncio.sleep(0.2)

            # Passo 3: Digitar data inicial caractere por caractere (simulando humano)
            print(f"[DATAS] Digitando data inicial: {data_inicial_str}")
            for char in data_inicial_str:
                await self.tab.send(char)
                await asyncio.sleep(random.uniform(0.05, 0.15))  # Delay humano entre teclas

            await asyncio.sleep(0.3)

            # Passo 4: Validar se data foi preenchida
            script_validar_inicial = """
            (function() {
                try {
                    var frameCode = document.getElementById('code');
                    var frameCodeDoc = frameCode.contentDocument || frameCode.contentWindow.document;
                    var frameText = frameCodeDoc.querySelector('frame[name="text"], iframe[name="text"]');
                    var doc = frameCodeDoc;
                    if (frameText) {
                        doc = frameText.contentDocument || frameText.contentWindow.document;
                    } else {
                        var frames = frameCodeDoc.querySelectorAll('frame, iframe');
                        if (frames.length > 0) {
                            doc = frames[0].contentDocument || frames[0].contentWindow.document;
                        }
                    }
                    var campoInicial = doc.getElementById('Emissao1');
                    return { success: true, valor: campoInicial ? campoInicial.value : 'campo não encontrado' };
                } catch(e) {
                    return { success: false, error: e.message };
                }
            })();
            """

            resultado_validacao = self.converter_cdp_para_dict(await self.tab.evaluate(script_validar_inicial))
            valor_preenchido = resultado_validacao.get('valor', '')

            print(f"[DATAS] ✅ Data inicial preenchida: '{valor_preenchido}'")

            if not valor_preenchido or valor_preenchido == '':
                raise Exception("Campo inicial ficou vazio após digitação!")

            # Passo 5: TAB para próximo campo (data final)
            print(f"[DATAS] Navegando para campo final (TAB)...")
            await self.tab.send('\t')  # Tab
            await asyncio.sleep(0.5)

            # Passo 6: Limpar e preencher campo final
            print(f"[DATAS] Limpando campo final...")
            await self.tab.send('\x01')  # Ctrl+A
            await asyncio.sleep(0.1)
            await self.tab.send('\x08')  # Backspace
            await asyncio.sleep(0.2)

            print(f"[DATAS] Digitando data final: {data_final_str}")
            for char in data_final_str:
                await self.tab.send(char)
                await asyncio.sleep(random.uniform(0.05, 0.15))

            await asyncio.sleep(0.5)

            # Passo 7: Validar data final
            script_validar_final = """
            (function() {
                try {
                    var frameCode = document.getElementById('code');
                    var frameCodeDoc = frameCode.contentDocument || frameCode.contentWindow.document;
                    var frameText = frameCodeDoc.querySelector('frame[name="text"], iframe[name="text"]');
                    var doc = frameCodeDoc;
                    if (frameText) {
                        doc = frameText.contentDocument || frameText.contentWindow.document;
                    } else {
                        var frames = frameCodeDoc.querySelectorAll('frame, iframe');
                        if (frames.length > 0) {
                            doc = frames[0].contentDocument || frames[0].contentWindow.document;
                        }
                    }
                    var campoFinal = doc.getElementById('Emissao23') || doc.getElementById('Emissao2');
                    return { success: true, valor: campoFinal ? campoFinal.value : 'campo não encontrado' };
                } catch(e) {
                    return { success: false, error: e.message };
                }
            })();
            """

            resultado_final = self.converter_cdp_para_dict(await self.tab.evaluate(script_validar_final))
            valor_final = resultado_final.get('valor', '')

            print(f"[DATAS] ✅ Data final preenchida: '{valor_final}'")

            print(f"\n[DATAS] ✅ DATAS PREENCHIDAS COM SUCESSO!")
            print(f"[DATAS]   Inicial: {valor_preenchido}")
            print(f"[DATAS]   Final: {valor_final}")

            await asyncio.sleep(1)

        except Exception as e:
            print(f"[DATAS] ❌ Erro ao preencher datas: {e}")
            logger.error(f"[{self.nome}] Erro ao preencher datas: {e}", exc_info=True)
            raise Exception(f"Erro ao preencher datas: {e}")

    # =========================================================================================
    # ETAPA 6: CLICAR PESQUISAR
    # =========================================================================================

    async def clicar_pesquisar(self):
        """Clica no botão Pesquisar"""
        print(f"\n{'='*80}")
        print(f"🔍 ETAPA 6: CLICANDO EM PESQUISAR")
        print(f"{'='*80}\n")

        script = """
        (function() {
            var frameCode = document.getElementById('code');
            if (!frameCode) return { found: false };

            var frameDoc = frameCode.contentDocument;
            if (!frameDoc) return { found: false };

            var frameText = frameDoc.querySelector('frame[name="text"]');
            if (frameText) {
                var doc = frameText.contentDocument;
                var botao = doc.getElementById('BtnSubmit') || doc.querySelector('input[value="Pesquisar"]');
                if (botao) {
                    botao.click();
                    return { found: true };
                }
            }

            return { found: false };
        })();
        """

        resultado = self.converter_cdp_para_dict(await self.tab.evaluate(script))

        if resultado.get('found'):
            print(f"[PESQUISAR] ✅ Clicado!")
            await asyncio.sleep(5)
        else:
            raise Exception("Botão Pesquisar não encontrado")

    # =========================================================================================
    # ETAPA 7: SELECIONAR TODOS
    # =========================================================================================

    async def selecionar_todos_resultados(self):
        """Marca checkbox Selecionar Todos"""
        print(f"\n{'='*80}")
        print(f"☑️  ETAPA 7: SELECIONANDO TODOS")
        print(f"{'='*80}\n")

        script = """
        (function() {
            var frameCode = document.getElementById('code');
            if (!frameCode) return { found: false };

            var frameDoc = frameCode.contentDocument;
            if (!frameDoc) return { found: false };

            var frameText = frameDoc.querySelector('frame[name="text"]');
            if (frameText) {
                var doc = frameText.contentDocument;
                var checkbox = doc.getElementById('checkallPesquisa') || doc.querySelector('input[type="checkbox"][onclick*="checkAll"]');
                if (checkbox && !checkbox.checked) {
                    checkbox.click();
                    return { found: true };
                }
                if (checkbox) return { found: true, jaEstava: true };
            }

            return { found: false };
        })();
        """

        resultado = self.converter_cdp_para_dict(await self.tab.evaluate(script))

        if resultado.get('found'):
            if resultado.get('jaEstava'):
                print(f"[SELECIONAR] ℹ️  Já estava marcado")
            else:
                print(f"[SELECIONAR] ✅ Marcado!")
            await asyncio.sleep(2)
        else:
            raise Exception("Checkbox não encontrado")

    # =========================================================================================
    # ETAPA 8: GERAR CSV
    # =========================================================================================

    async def clicar_gerar_csv(self):
        """Clica no botão Gerar CSV"""
        print(f"\n{'='*80}")
        print(f"📄 ETAPA 8: GERANDO CSV")
        print(f"{'='*80}\n")

        script = """
        (function() {
            var frameCode = document.getElementById('code');
            if (!frameCode) return { found: false };

            var frameDoc = frameCode.contentDocument;
            if (!frameDoc) return { found: false };

            var frameText = frameDoc.querySelector('frame[name="text"]');
            if (frameText) {
                var doc = frameText.contentDocument;
                var botao = doc.getElementById('ImprimirCSV') || doc.querySelector('input[value="Gerar CSV"]');
                if (botao) {
                    botao.click();
                    return { found: true };
                }
            }

            return { found: false };
        })();
        """

        resultado = self.converter_cdp_para_dict(await self.tab.evaluate(script))

        if resultado.get('found'):
            print(f"[GERAR CSV] ✅ Clicado!")
            await asyncio.sleep(3)
            await self.verificar_e_resolver_recaptcha()
            await asyncio.sleep(10)
        else:
            raise Exception("Botão Gerar CSV não encontrado")

    # =========================================================================================
    # ETAPA 9: RENOMEAR CSV
    # =========================================================================================

    async def renomear_csv_baixado(self):
        """Renomeia o CSV baixado"""
        print(f"\n{'='*80}")
        print(f"📝 ETAPA 9: RENOMEANDO CSV")
        print(f"{'='*80}\n")

        try:
            print(f"[RENOMEAR] Aguardando download...")
            for _ in range(30):
                crdownload = glob.glob(os.path.join(self.download_dir, "*.crdownload"))
                if not crdownload:
                    break
                await asyncio.sleep(1)

            await asyncio.sleep(2)

            csvs = glob.glob(os.path.join(self.download_dir, "*.csv"))
            if not csvs:
                print(f"[RENOMEAR] ⚠️ Nenhum CSV encontrado")
                return None

            arquivo_path = max(csvs, key=os.path.getmtime)

            timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
            nome_novo = f"titulos_abertos_{timestamp}.csv"
            caminho_destino = os.path.join(self.download_dir, nome_novo)

            os.rename(arquivo_path, caminho_destino)
            print(f"[RENOMEAR] ✅ Salvo: {nome_novo}")

            return caminho_destino

        except Exception as e:
            print(f"[RENOMEAR] ⚠️ Erro: {e}")
            return None

    # =========================================================================================
    # CICLO DE EXTRAÇÃO
    # =========================================================================================

    async def executar_ciclo_extracao(self):
        """Executa um ciclo completo"""
        print(f"\n{'#'*80}")
        print(f"# CICLO DE EXTRAÇÃO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*80}\n")

        try:
            await self.navegar_para_titulos_abertos()

            captcha_resolvido = await self.verificar_e_resolver_recaptcha()
            if captcha_resolvido:
                await self.navegar_para_titulos_abertos()

            await self.verificar_e_aguardar_frames_prontos()
            await self.preencher_datas()
            await self.clicar_pesquisar()
            await self.verificar_e_resolver_recaptcha()
            await self.verificar_e_aguardar_frames_prontos()
            await self.selecionar_todos_resultados()
            await self.clicar_gerar_csv()

            arquivo_final = await self.renomear_csv_baixado()

            print(f"\n{'='*80}")
            print(f"✅ CICLO CONCLUÍDO!")
            if arquivo_final:
                print(f"✅ Arquivo: {os.path.basename(arquivo_final)}")
            print(f"{'='*80}\n")

        except Exception as e:
            print(f"\n❌ ERRO NO CICLO: {e}")
            logger.error(f"[{self.nome}] Erro: {e}", exc_info=True)
            raise

    # =========================================================================================
    # LOOP PRINCIPAL
    # =========================================================================================

    async def iniciar(self):
        """Inicia o processador"""
        print(f"\n{'='*80}")
        print(f"🚀 PROCESSADOR: {self.nome}")
        print(f"🖥️  Display: {self.display}")
        print(f"🌐 VNC: http://{SERVER_IP}:6081/vnc.html")
        print(f"🔌 API: http://{SERVER_IP}:6091")
        print(f"{'='*80}\n")

        try:
            if self.display:
                os.environ['DISPLAY'] = self.display

            print(f"[INIT] Iniciando navegador...")
            self.browser = await init_browser(
                download_dir=self.download_dir,
                headless=False,
                display=self.display
            )
            print(f"[INIT] ✅ Navegador iniciado")

            await self.fazer_login()

            ciclo = 1
            while not self.parar:
                print(f"\n{'█'*80}")
                print(f"█ CICLO #{ciclo} - {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'█'*80}\n")

                try:
                    await self.executar_ciclo_extracao()
                except Exception as e:
                    print(f"\n❌ Erro no ciclo: {e}")
                    await enviar_alerta_erro_critico(self.nome, str(e), self.display)

                ciclo += 1

                if not self.parar:
                    print(f"\n⏱️  Aguardando {INTERVALO_LOOP}s...")
                    await asyncio.sleep(INTERVALO_LOOP)

            if self.browser:
                await self.browser.stop()

        except Exception as e:
            print(f"\n❌ ERRO FATAL: {e}")
            if self.browser:
                try:
                    await self.browser.stop()
                except:
                    pass
            raise


# =============================================================================================
# ENTRY POINT
# =============================================================================================

def processar_titulos_aberto():
    """Wrapper síncrono"""
    processador = ProcessadorTitulosAberto()
    return asyncio.run(processador.iniciar())


if __name__ == "__main__":
    print(f"\n{'='*80}")
    print(f"PROSPER-ERP-AUTOMATION")
    print(f"Processador: Títulos Abertos")
    print(f"Versão: 1.0")
    print(f"{'='*80}\n")

    processar_titulos_aberto()
