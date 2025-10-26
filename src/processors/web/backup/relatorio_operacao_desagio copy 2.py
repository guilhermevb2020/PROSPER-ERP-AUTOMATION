#!/usr/bin/env python3
# =============================================================================================
# ARQUIVO: relatorio_operacao_desagio.py
# VERSÃO: v3.0 - REESCRITO DO ZERO
# DESCRIÇÃO: Extrai relatório de operações de deságio do SmartSecurities
# URL: https://www.smartsecurities.com.br/smart/relatorios/frmrelatorio.php?page=relatorios/detalhamentodesagio.php
# DISPLAY: :1 (VNC porta 6080)
# API: Porta 6090
# =============================================================================================

import os
import sys
import asyncio
import time
import tempfile
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Nodriver imports
try:
    import nodriver as uc
    from nodriver import Browser, Tab
    NODRIVER_AVAILABLE = True
except ImportError:
    NODRIVER_AVAILABLE = False
    print("⚠️ Nodriver não instalado. Execute: pip install nodriver")
    sys.exit(1)

from src.common.nodriver_utils import init_browser, wait_for_element, human_click, human_type
from src.core.logging_config import get_logger
from src.common.notification_utils import enviar_alerta_login_sucesso, enviar_alerta_erro_critico
from src.common.captcha_solver import CapSolverAPI

# =============================================================================================
# CONFIGURAÇÕES
# =============================================================================================

load_dotenv()

logger = get_logger(__name__)

# URLs
URL_LOGIN = "https://www.smartsecurities.com.br/smartsecurities/"
URL_RELATORIO = "https://www.smartsecurities.com.br/smart/relatorios/frmrelatorio.php?page=relatorios/detalhamentodesagio.php"

# Diretórios
DOWNLOAD_DIR = Path("data/raw_inputs/")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Credenciais
SMART_EMAIL = os.getenv("USUARIO_SITE_SMART")
SMART_PASSWORD = os.getenv("SENHA_SITE_SMART")
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY")
SERVER_IP = os.getenv("SERVER_IP", "3.148.126.73")

# Timeouts
TIMEOUT_DOWNLOAD = 90  # segundos (CSV grande demora mais)
TIMEOUT_CAPTCHA = 60  # segundos
INTERVALO_LOOP = 5  # 5 segundos entre extrações

# =============================================================================================
# PROCESSADOR
# =============================================================================================

class ProcessadorRelatorioDesagio:
    """Processador simples e enxuto para extração de relatório de deságio"""

    def __init__(self):
        self.nome = "relatorio_desagio"
        self.browser: Browser = None
        self.tab: Tab = None
        self.display = os.environ.get('DISPLAY', ':1')
        self.capsolver = CapSolverAPI(CAPSOLVER_API_KEY)
        self.download_dir = str(DOWNLOAD_DIR.absolute())

        # Perfil temporário único para cada execução (evita reutilização de sessão)
        self.temp_profile_dir = tempfile.mkdtemp(prefix="chrome_profile_")

        # Controle de execução
        self.parar = False
        self.primeira_execucao = True

        logger.info(f"[{self.nome}] Processador inicializado")
        logger.info(f"[{self.nome}] Perfil temporário: {self.temp_profile_dir}")

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

    # =========================================================================================
    # ETAPA 1: LOGIN
    # =========================================================================================

    async def fazer_login(self):
        """
        Faz login no SmartSecurities - COPIADO DO CÓDIGO ANTIGO QUE FUNCIONAVA
        """
        print(f"\n{'='*80}")
        print(f"🔐 ETAPA 1: LOGIN NO SMARTSECURITIES")
        print(f"{'='*80}\n")

        logger.info(f"[{self.nome}] Iniciando login...")

        try:
            # Abrir página de login
            print(f"[LOGIN] Abrindo página de login...")
            self.tab = await self.browser.get(URL_LOGIN)
            await asyncio.sleep(3)

            # Aguardar iframe carregar (com retry)
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

            # Preencher credenciais
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

            if not resultado or not resultado.get('success'):
                raise Exception("Falha ao preencher credenciais")

            print(f"[LOGIN] ✅ Credenciais preenchidas")
            await asyncio.sleep(1)

            # Clicar no botão OK (ANTES do CAPTCHA)
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

            # Aguardar CAPTCHA aparecer
            print(f"[LOGIN] Aguardando CAPTCHA aparecer...")
            await asyncio.sleep(3)

            # Resolver CAPTCHA usando método automático
            print(f"[LOGIN] Resolvendo CAPTCHA...")
            site_url = await self.tab.evaluate("window.location.href")
            captcha_resolvido = await self.capsolver.resolver_recaptcha_automatico(self.tab, site_url)

            if not captcha_resolvido:
                raise Exception("CAPTCHA não foi resolvido")

            print(f"[LOGIN] ✅ CAPTCHA resolvido!")

            # Clicar no botão OK novamente (para submeter com CAPTCHA)
            print(f"[LOGIN] Clicando no botão OK final...")
            await asyncio.sleep(2)

            resultado_raw = await self.tab.evaluate(script_clicar)
            resultado = self.converter_cdp_para_dict(resultado_raw)

            print(f"[LOGIN] Aguardando redirecionamento...")
            await asyncio.sleep(5)

            # Verificar se login foi bem-sucedido
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
    # ETAPA 2: NOTIFICAÇÃO DE SUCESSO (apenas na primeira vez)
    # =========================================================================================

    async def enviar_notificacao_login(self):
        """Envia email notificando que o processador foi logado com sucesso"""

        # DESABILITADO TEMPORARIAMENTE
        print(f"\n{'='*80}")
        print(f"📧 ETAPA 2: NOTIFICAÇÃO DE LOGIN (DESABILITADA)")
        print(f"{'='*80}\n")
        print(f"[EMAIL] ⏭️ Envio de email desabilitado")
        return

    # =========================================================================================
    # ETAPA 3: NAVEGAR PARA RELATÓRIO
    # =========================================================================================

    async def navegar_relatorio(self):
        """Navega para a página de relatório de deságio"""

        print(f"\n{'='*80}")
        print(f"🌐 ETAPA 3: NAVEGANDO PARA RELATÓRIO")
        print(f"{'='*80}\n")

        print(f"[NAVEGAÇÃO] Acessando: {URL_RELATORIO}")

        try:
            await self.tab.get(URL_RELATORIO)
            await asyncio.sleep(5)  # Aumentado para dar tempo do iframe carregar

            print(f"[NAVEGAÇÃO] ✅ Página carregada")
            logger.info(f"[{self.nome}] Navegou para relatório de deságio")

        except Exception as e:
            logger.error(f"[{self.nome}] Erro ao navegar: {e}", exc_info=True)
            raise

    # =========================================================================================
    # ETAPA 4: PREENCHER FORMULÁRIO
    # =========================================================================================

    async def preencher_formulario(self):
        """Preenche os campos do formulário (DtInicial, DtFinal, csvType)"""

        print(f"\n{'='*80}")
        print(f"📝 ETAPA 4: PREENCHENDO FORMULÁRIO")
        print(f"{'='*80}\n")

        try:
            # Calcular datas (EXATAMENTE 10 anos atrás)
            from dateutil.relativedelta import relativedelta
            data_hoje = datetime.now()
            data_inicial = data_hoje - relativedelta(years=10)  # EXATAMENTE 10 anos atrás
            data_inicial_str = data_inicial.strftime("%d/%m/%Y")
            data_final_str = data_hoje.strftime("%d/%m/%Y")

            print(f"[FORMULÁRIO] DtInicial: {data_inicial_str}")
            print(f"[FORMULÁRIO] DtFinal: {data_final_str}")

            # Aguardar frames carregarem (2 segundos é suficiente)
            await asyncio.sleep(2)

            # BUSCA RECURSIVA - PREENCHE FORMULÁRIO E JÁ CLICA NO BOTÃO
            print(f"[FORMULÁRIO] Procurando e preenchendo formulário...")

            resultado_raw = await self.tab.evaluate(f"""
                (() => {{
                    function buscarRecursivo(doc, profundidade = 0, caminho = 'main') {{
                        // Procurar no documento atual
                        const dtInicial = doc.getElementById('DtInicial');
                        const dtFinal = doc.getElementById('DtFinal');
                        const radioCSV = doc.querySelector('input[name="tipoImp"][value="csvType"]');

                        if (dtInicial && dtFinal && radioCSV) {{
                            // ENCONTROU! Preencher
                            dtInicial.value = '{data_inicial_str}';
                            dtFinal.value = '{data_final_str}';
                            radioCSV.checked = true;

                            // Procurar E CLICAR no botão Imprimir NO MESMO documento
                            const botao = doc.querySelector('input[name="Imprimir"]') ||
                                         doc.querySelector('input[value="Gerar relatório"]') ||
                                         doc.querySelector('button[name="Imprimir"]');

                            let botaoClicado = false;
                            if (botao) {{
                                botao.click();
                                botaoClicado = true;
                            }}

                            return {{
                                success: true,
                                caminho: caminho,
                                profundidade: profundidade,
                                dtInicial: dtInicial.value,
                                dtFinal: dtFinal.value,
                                csvChecked: radioCSV.checked,
                                botaoClicado: botaoClicado
                            }};
                        }}

                        // Buscar em frames filhos (recursivo)
                        if (profundidade < 10) {{ // Limitar profundidade para evitar loop infinito
                            const frames = doc.querySelectorAll('frame, iframe');
                            for (let i = 0; i < frames.length; i++) {{
                                try {{
                                    const frameDoc = frames[i].contentDocument || frames[i].contentWindow.document;
                                    const novoCaminho = `${{caminho}} > frame[${{i}}](${{frames[i].name || frames[i].id || 'sem-nome'}})`;
                                    const resultado = buscarRecursivo(frameDoc, profundidade + 1, novoCaminho);
                                    if (resultado) return resultado;
                                }} catch (e) {{
                                    // Ignorar cross-origin
                                }}
                            }}
                        }}

                        return null;
                    }}

                    const resultado = buscarRecursivo(document);
                    if (resultado) return resultado;

                    return {{ success: false, error: 'Campos não encontrados em nenhum frame (busca recursiva)' }};
                }})()
            """)

            resultado = self.converter_cdp_para_dict(resultado_raw)

            print(f"[FORMULÁRIO] Resultado: {resultado}")

            if not resultado or not resultado.get('success'):
                erro = resultado.get('error') if resultado else 'Script retornou None'
                raise Exception(f"Falha ao preencher formulário: {erro}")

            print(f"[FORMULÁRIO] ✅ Caminho: {resultado.get('caminho')}")
            print(f"[FORMULÁRIO] ✅ Profundidade: {resultado.get('profundidade')}")
            print(f"[FORMULÁRIO] ✅ DtInicial: {resultado.get('dtInicial')}")
            print(f"[FORMULÁRIO] ✅ DtFinal: {resultado.get('dtFinal')}")
            print(f"[FORMULÁRIO] ✅ CSV selecionado: {resultado.get('csvChecked')}")
            print(f"[FORMULÁRIO] ✅ Botão CLICADO: {resultado.get('botaoClicado')}")

            logger.info(f"[{self.nome}] Formulário preenchido e botão clicado")

        except Exception as e:
            logger.error(f"[{self.nome}] Erro ao preencher formulário: {e}", exc_info=True)
            raise

    # =========================================================================================
    # ETAPA 4.5: VERIFICAR E RESOLVER CAPTCHA (SE APARECER)
    # =========================================================================================

    async def verificar_e_resolver_recaptcha(self):
        """Verifica e resolve reCAPTCHA se necessário (aparece após clicar no botão)"""
        print(f"\n{'='*80}")
        print(f"🔍 VERIFICANDO reCAPTCHA APÓS CLIQUE")
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

                # Aguardar submissão do CAPTCHA
                print(f"[CAPTCHA] Aguardando 2s após clicar Confirmar...")
                await asyncio.sleep(2)

                # FECHAR a aba do CAPTCHA (isso é CRUCIAL!)
                print(f"[CAPTCHA] Fechando aba do CAPTCHA...")
                try:
                    await self.tab.close()
                    print(f"[CAPTCHA] ✅ Aba do CAPTCHA fechada")
                except Exception as e:
                    print(f"[CAPTCHA] ⚠️ Erro ao fechar aba: {e}")

                # Voltar para tab principal
                self.tab = tab_principal
                print(f"[CAPTCHA] ✅ Voltou para tab principal")
                await asyncio.sleep(1)

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
    # ETAPA 5: GERAR RELATÓRIO
    # =========================================================================================

    async def gerar_relatorio(self):
        """Clica no botão Imprimir para gerar o relatório"""

        print(f"\n{'='*80}")
        print(f"🖨️  ETAPA 5: GERANDO RELATÓRIO")
        print(f"{'='*80}\n")

        try:
            print(f"[RELATÓRIO] Clicando no botão Imprimir...")

            # BUSCA RECURSIVA para encontrar botão Imprimir
            resultado_raw = await self.tab.evaluate("""
                (() => {
                    function buscarRecursivo(doc, profundidade = 0, caminho = 'main') {
                        // Procurar botão no documento atual
                        const botao = doc.querySelector('input[name="Imprimir"]') ||
                                     doc.querySelector('input[value="Gerar relatório"]') ||
                                     doc.querySelector('button[name="Imprimir"]');

                        if (botao) {
                            botao.click();
                            return {
                                success: true,
                                caminho: caminho,
                                profundidade: profundidade
                            };
                        }

                        // Buscar em frames filhos (recursivo)
                        if (profundidade < 10) {
                            const frames = doc.querySelectorAll('frame, iframe');
                            for (let i = 0; i < frames.length; i++) {
                                try {
                                    const frameDoc = frames[i].contentDocument || frames[i].contentWindow.document;
                                    const novoCaminho = `${caminho} > frame[${i}](${frames[i].name || frames[i].id || 'sem-nome'})`;
                                    const resultado = buscarRecursivo(frameDoc, profundidade + 1, novoCaminho);
                                    if (resultado) return resultado;
                                } catch (e) {
                                    // Ignorar cross-origin
                                }
                            }
                        }

                        return null;
                    }

                    const resultado = buscarRecursivo(document);
                    if (resultado) return resultado;

                    return { success: false, error: 'Botão não encontrado (busca recursiva)' };
                })()
            """)

            resultado = self.converter_cdp_para_dict(resultado_raw)

            if not resultado or not resultado.get('success'):
                erro = resultado.get('error') if resultado else 'Script retornou None'
                raise Exception(f"Falha ao clicar Imprimir: {erro}")

            print(f"[RELATÓRIO] ✅ Botão Imprimir clicado")
            print(f"[RELATÓRIO] ✅ Caminho: {resultado.get('caminho')}")
            print(f"[RELATÓRIO] ✅ Profundidade: {resultado.get('profundidade')}")
            logger.info(f"[{self.nome}] Relatório gerado")

        except Exception as e:
            logger.error(f"[{self.nome}] Erro ao gerar relatório: {e}", exc_info=True)
            raise

    # =========================================================================================
    # ETAPA 6: AGUARDAR DOWNLOAD
    # =========================================================================================

    async def aguardar_download(self):
        """Aguarda o download do arquivo CSV"""

        print(f"\n{'='*80}")
        print(f"⏬ ETAPA 6: AGUARDANDO DOWNLOAD")
        print(f"{'='*80}\n")

        print(f"[DOWNLOAD] Aguardando arquivo CSV...")
        print(f"[DOWNLOAD] Timeout: {TIMEOUT_DOWNLOAD}s")

        # Listar arquivos antes
        arquivos_antes = set(DOWNLOAD_DIR.glob("*"))

        # Aguardar novo arquivo aparecer
        for i in range(TIMEOUT_DOWNLOAD):
            await asyncio.sleep(1)

            arquivos_agora = set(DOWNLOAD_DIR.glob("*"))
            novos_arquivos = arquivos_agora - arquivos_antes

            # Procurar por arquivo CSV completo (não .crdownload, .tmp, etc)
            for arquivo in novos_arquivos:
                if arquivo.suffix.lower() == '.csv':
                    print(f"[DOWNLOAD] ✅ Arquivo baixado: {arquivo.name}")
                    logger.info(f"[{self.nome}] Download concluído: {arquivo.name}")
                    return arquivo

            # Feedback a cada 5 segundos
            if (i + 1) % 5 == 0:
                print(f"[DOWNLOAD] Aguardando... ({i + 1}s)")

        raise Exception(f"Timeout: arquivo CSV não baixado em {TIMEOUT_DOWNLOAD}s")

    # =========================================================================================
    # ETAPA 7: RENOMEAR ARQUIVO
    # =========================================================================================

    async def renomear_arquivo(self, arquivo_original: Path):
        """Renomeia o arquivo baixado com timestamp"""

        print(f"\n{'='*80}")
        print(f"📝 ETAPA 7: RENOMEANDO ARQUIVO")
        print(f"{'='*80}\n")

        try:
            timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
            novo_nome = f"relatorio_desagio_{timestamp}.csv"
            novo_caminho = DOWNLOAD_DIR / novo_nome

            arquivo_original.rename(novo_caminho)

            print(f"[RENOMEAR] ✅ Arquivo renomeado")
            print(f"[RENOMEAR] De: {arquivo_original.name}")
            print(f"[RENOMEAR] Para: {novo_nome}")

            logger.info(f"[{self.nome}] Arquivo renomeado: {novo_nome}")

            return novo_caminho

        except Exception as e:
            logger.error(f"[{self.nome}] Erro ao renomear arquivo: {e}", exc_info=True)
            raise

    # =========================================================================================
    # CICLO DE EXTRAÇÃO COMPLETO
    # =========================================================================================

    async def executar_ciclo_extracao(self):
        """Executa um ciclo completo de extração (ETAPAS 3-7)"""

        print(f"\n{'#'*80}")
        print(f"# INICIANDO CICLO DE EXTRAÇÃO")
        print(f"# Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*80}\n")

        try:
            # ETAPA 3: Navegar
            await self.navegar_relatorio()

            # ETAPA 4: Preencher formulário e clicar em Imprimir
            await self.preencher_formulario()

            # ETAPA 5: Verificar e resolver CAPTCHA (SEMPRE aparece após clicar Imprimir!)
            await self.verificar_e_resolver_recaptcha()

            # ETAPA 6: Aguardar download
            arquivo = await self.aguardar_download()

            # ETAPA 7: Renomear
            arquivo_final = await self.renomear_arquivo(arquivo)

            print(f"\n{'='*80}")
            print(f"✅ CICLO CONCLUÍDO COM SUCESSO!")
            print(f"✅ Arquivo: {arquivo_final.name}")
            print(f"{'='*80}\n")

            logger.info(f"[{self.nome}] Ciclo de extração concluído: {arquivo_final.name}")

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ ERRO NO CICLO DE EXTRAÇÃO")
            print(f"❌ {str(e)}")
            print(f"{'='*80}\n")

            logger.error(f"[{self.nome}] Erro no ciclo de extração: {e}", exc_info=True)
            raise

    # =========================================================================================
    # LOOP PRINCIPAL
    # =========================================================================================

    async def iniciar(self):
        """Inicia o processador"""

        print(f"\n{'='*80}")
        print(f"🚀 INICIANDO PROCESSADOR: {self.nome}")
        print(f"{'='*80}\n")

        try:
            # Configurar display
            if self.display:
                os.environ['DISPLAY'] = self.display
                print(f"[INIT] Display: {self.display}")

            # Iniciar navegador com perfil temporário
            print(f"[INIT] Iniciando navegador Nodriver...")
            print(f"[INIT] Perfil temporário: {self.temp_profile_dir}")
            self.browser = await init_browser(
                download_dir=self.download_dir,
                headless=False,
                display=self.display,
                user_data_dir=self.temp_profile_dir
            )
            print(f"[INIT] ✅ Navegador iniciado")

            # ETAPA 1: Login (uma vez)
            await self.fazer_login()

            # ETAPA 2: Notificar (uma vez)
            await self.enviar_notificacao_login()
            self.primeira_execucao = False

            # LOOP: ETAPAS 3-7 (repetir)
            ciclo_numero = 1

            while not self.parar:
                print(f"\n{'█'*80}")
                print(f"█ CICLO #{ciclo_numero}")
                print(f"{'█'*80}\n")

                try:
                    await self.executar_ciclo_extracao()

                    # Aguardar intervalo antes do próximo ciclo
                    print(f"\n[LOOP] Próximo ciclo em {INTERVALO_LOOP // 60} minutos...")
                    print(f"[LOOP] Pressione Ctrl+C para parar\n")

                    await asyncio.sleep(INTERVALO_LOOP)
                    ciclo_numero += 1

                except Exception as e:
                    print(f"\n[LOOP] ⚠️ Erro no ciclo #{ciclo_numero}: {e}")
                    print(f"[LOOP] Tentando novamente em 60 segundos...\n")

                    # Enviar email de erro
                    try:
                        enviar_alerta_erro_critico(
                            erro_descricao=f"Erro no ciclo #{ciclo_numero}: {str(e)}"
                        )
                    except:
                        pass

                    await asyncio.sleep(60)
                    ciclo_numero += 1  # Incrementar mesmo com erro

        except KeyboardInterrupt:
            print(f"\n[INIT] ⏹️ Interrupção pelo usuário")
            logger.info(f"[{self.nome}] Interrompido pelo usuário")

        except Exception as e:
            print(f"\n[INIT] ❌ Erro crítico: {e}")
            logger.error(f"[{self.nome}] Erro crítico: {e}", exc_info=True)
            raise

        finally:
            # Fechar todas as tabs primeiro
            if self.browser:
                print(f"\n[CLEANUP] Fechando todas as tabs...")
                try:
                    tabs = await self.browser.tabs
                    for tab in tabs:
                        try:
                            await tab.close()
                        except:
                            pass
                    print(f"[CLEANUP] ✅ {len(tabs)} tab(s) fechada(s)")
                except Exception as e:
                    print(f"[CLEANUP] ⚠️ Erro ao fechar tabs: {e}")

            # Fechar navegador
            if self.browser:
                print(f"[CLEANUP] Fechando navegador...")
                try:
                    await self.browser.stop()
                    print(f"[CLEANUP] ✅ Navegador fechado")
                except Exception as e:
                    print(f"[CLEANUP] ⚠️ Erro ao fechar navegador: {e}")

            # Limpar perfil temporário
            if hasattr(self, 'temp_profile_dir') and os.path.exists(self.temp_profile_dir):
                print(f"[CLEANUP] Limpando perfil temporário...")
                try:
                    import shutil
                    shutil.rmtree(self.temp_profile_dir, ignore_errors=True)
                    print(f"[CLEANUP] ✅ Perfil temporário removido")
                except Exception as e:
                    print(f"[CLEANUP] ⚠️ Erro ao remover perfil: {e}")

            print(f"\n{'='*80}")
            print(f"👋 PROCESSADOR FINALIZADO")
            print(f"{'='*80}\n")

# =============================================================================================
# MAIN
# =============================================================================================

async def main():
    """Função principal"""

    processador = ProcessadorRelatorioDesagio()
    await processador.iniciar()

if __name__ == "__main__":
    asyncio.run(main())
