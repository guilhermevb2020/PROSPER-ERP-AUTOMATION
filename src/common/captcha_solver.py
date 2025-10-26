"""
Módulo para resolver CAPTCHAs usando API HTTP direta do CapSolver
100% automatizado, sem biblioteca Python (que estava quebrada)
Baseado na documentação oficial: https://docs.capsolver.com/
"""

import asyncio
import time
from typing import Optional, Dict
import aiohttp
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class CapSolverAPI:
    """Cliente HTTP direto para resolver CAPTCHAs usando API do CapSolver"""

    # Endpoints oficiais da API
    CREATE_TASK_URL = "https://api.capsolver.com/createTask"
    GET_TASK_RESULT_URL = "https://api.capsolver.com/getTaskResult"

    def __init__(self, api_key: str):
        """
        Inicializa o cliente CapSolver com HTTP direto

        Args:
            api_key: API key do CapSolver (do .env)
        """
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("CAPSOLVER_API_KEY não encontrada no .env")

    async def resolver_recaptcha_v2(
        self,
        site_url: str,
        site_key: str,
        timeout: int = 180,
        poll_interval: int = 1
    ) -> Optional[str]:
        """
        Resolve reCAPTCHA v2 usando API HTTP direta do CapSolver

        Args:
            site_url: URL da página com CAPTCHA (ex: https://www.smartsecurities.com.br/...)
            site_key: Site key do reCAPTCHA (extraído do HTML)
            timeout: Timeout em segundos (padrão: 180s = 3min)
            poll_interval: Intervalo entre verificações em segundos (padrão: 1s)

        Returns:
            Token do CAPTCHA resolvido ou None se falhar
        """
        print(f"\n[CAPSOLVER HTTP] Iniciando resolução de reCAPTCHA v2...")
        print(f"[CAPSOLVER HTTP] URL: {site_url}")
        print(f"[CAPSOLVER HTTP] Site Key: {site_key}")
        print(f"[CAPSOLVER HTTP] API Key: {self.api_key[:10]}...{self.api_key[-4:]}")

        try:
            # PASSO 1: Criar task
            task_id = await self._create_task(site_url, site_key)
            if not task_id:
                print(f"[CAPSOLVER HTTP] ❌ Falha ao criar task")
                return None

            print(f"[CAPSOLVER HTTP] ✅ Task criada: {task_id}")
            print(f"[CAPSOLVER HTTP] ⏳ Aguardando resolução (máx {timeout}s)...")

            # PASSO 2: Poll para resultado
            start_time = time.time()
            attempt = 0

            while time.time() - start_time < timeout:
                attempt += 1
                await asyncio.sleep(poll_interval)

                result = await self._get_task_result(task_id)

                if result:
                    status = result.get("status")

                    if status == "ready":
                        token = result.get("solution", {}).get("gRecaptchaResponse")
                        if token:
                            elapsed = time.time() - start_time
                            print(f"[CAPSOLVER HTTP] ✅ CAPTCHA RESOLVIDO em {elapsed:.1f}s!")
                            print(f"[CAPSOLVER HTTP] Token: {token[:50]}...")
                            logger.info(f"reCAPTCHA resolvido via HTTP em {elapsed:.1f}s")
                            return token
                        else:
                            print(f"[CAPSOLVER HTTP] ❌ Status ready mas sem token")
                            logger.error("CapSolver retornou ready mas sem token")
                            return None

                    elif status == "failed":
                        error_msg = result.get("errorDescription", "Unknown error")
                        print(f"[CAPSOLVER HTTP] ❌ Task falhou: {error_msg}")
                        logger.error(f"CapSolver task failed: {error_msg}")
                        return None

                    elif status == "processing":
                        # Feedback visual a cada 10 tentativas
                        if attempt % 10 == 0:
                            elapsed = time.time() - start_time
                            print(f"[CAPSOLVER HTTP] ⏳ Ainda processando... ({elapsed:.0f}s)")

                    else:
                        print(f"[CAPSOLVER HTTP] ⚠️ Status desconhecido: {status}")

            # Timeout
            print(f"[CAPSOLVER HTTP] ❌ Timeout após {timeout}s")
            logger.error(f"CapSolver timeout após {timeout}s")
            return None

        except Exception as e:
            import traceback
            print(f"[CAPSOLVER HTTP] ❌ Erro: {e}")
            print(f"[CAPSOLVER HTTP] Traceback: {traceback.format_exc()}")
            logger.error(f"Erro ao resolver CAPTCHA via HTTP: {e}")
            return None

    async def _create_task(self, site_url: str, site_key: str) -> Optional[str]:
        """
        Cria uma task de resolução de CAPTCHA via HTTP POST

        Args:
            site_url: URL da página
            site_key: Site key do reCAPTCHA

        Returns:
            task_id se sucesso, None se falhar
        """
        payload = {
            "clientKey": self.api_key,  # ⚠️ É "clientKey", não "apiKey"!
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": site_url,
                "websiteKey": site_key
            }
        }

        print(f"[CAPSOLVER HTTP] Enviando createTask...")
        print(f"[CAPSOLVER HTTP] Payload: {payload}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.CREATE_TASK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_text = await response.text()
                    print(f"[CAPSOLVER HTTP] Response status: {response.status}")
                    print(f"[CAPSOLVER HTTP] Response: {response_text}")

                    if response.status != 200:
                        logger.error(f"CapSolver HTTP error {response.status}: {response_text}")
                        return None

                    data = await response.json()

                    error_id = data.get("errorId")
                    if error_id and error_id != 0:
                        error_code = data.get("errorCode", "UNKNOWN")
                        error_desc = data.get("errorDescription", "No description")
                        print(f"[CAPSOLVER HTTP] ❌ API Error {error_id}: {error_code} - {error_desc}")
                        logger.error(f"CapSolver API error: {error_code} - {error_desc}")
                        return None

                    task_id = data.get("taskId")
                    return task_id

        except asyncio.TimeoutError:
            print(f"[CAPSOLVER HTTP] ❌ Timeout ao criar task")
            logger.error("Timeout ao criar task no CapSolver")
            return None
        except Exception as e:
            print(f"[CAPSOLVER HTTP] ❌ Erro ao criar task: {e}")
            logger.error(f"Erro ao criar task: {e}")
            return None

    async def _get_task_result(self, task_id: str) -> Optional[Dict]:
        """
        Verifica o resultado de uma task via HTTP POST

        Args:
            task_id: ID da task criada

        Returns:
            Dict com resultado ou None se erro
        """
        payload = {
            "clientKey": self.api_key,
            "taskId": task_id
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.GET_TASK_RESULT_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()

                    error_id = data.get("errorId")
                    if error_id and error_id != 0:
                        error_code = data.get("errorCode", "UNKNOWN")
                        error_desc = data.get("errorDescription", "No description")
                        logger.error(f"CapSolver getTaskResult error: {error_code} - {error_desc}")
                        return None

                    return data

        except Exception:
            return None

    async def extrair_site_key_recaptcha(self, tab) -> Optional[str]:
        """
        Extrai o site_key do reCAPTCHA da página (incluindo dentro de iframes)

        Args:
            tab: Tab do Nodriver (equivalente ao driver do Selenium)

        Returns:
            Site key do reCAPTCHA ou None se não encontrar
        """
        print(f"\n[CAPSOLVER HTTP] Extraindo site_key do reCAPTCHA...")

        try:
            # Múltiplas formas de extrair site_key (incluindo dentro de iframes)
            site_key_script = """
            (() => {
                // Função helper para buscar em um documento
                function buscarSiteKey(doc) {
                    // Método 1: Via iframe do reCAPTCHA
                    const recaptchaIframe = doc.querySelector('iframe[src*="recaptcha"]');
                    if (recaptchaIframe) {
                        const src = recaptchaIframe.getAttribute('src');
                        const match = src.match(/[?&]k=([^&]+)/);
                        if (match) {
                            return match[1];
                        }
                    }

                    // Método 2: Via div com data-sitekey
                    const recaptchaDiv = doc.querySelector('[data-sitekey]');
                    if (recaptchaDiv) {
                        return recaptchaDiv.getAttribute('data-sitekey');
                    }

                    // Método 3: Via classe g-recaptcha
                    const gRecaptcha = doc.querySelector('.g-recaptcha');
                    if (gRecaptcha) {
                        return gRecaptcha.getAttribute('data-sitekey');
                    }

                    // Método 4: Buscar em todos os iframes
                    const allIframes = doc.querySelectorAll('iframe');
                    for (const iframe of allIframes) {
                        const src = iframe.src || '';
                        if (src.includes('recaptcha') || src.includes('google.com/recaptcha')) {
                            const match = src.match(/[?&]k=([^&]+)/);
                            if (match) {
                                return match[1];
                            }
                        }
                    }

                    return null;
                }

                // PASSO 1: Buscar na página principal
                let siteKey = buscarSiteKey(document);
                if (siteKey) {
                    return siteKey;
                }

                // PASSO 2: Buscar dentro de TODOS os iframes (incluindo iframe de login)
                const todosIframes = document.querySelectorAll('iframe');
                for (const iframe of todosIframes) {
                    try {
                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        if (!iframeDoc) continue;

                        siteKey = buscarSiteKey(iframeDoc);
                        if (siteKey) {
                            return siteKey;
                        }

                        // Buscar em iframes aninhados (iframe dentro de iframe)
                        const nestedIframes = iframeDoc.querySelectorAll('iframe');
                        for (const nestedIframe of nestedIframes) {
                            try {
                                const nestedDoc = nestedIframe.contentDocument || nestedIframe.contentWindow.document;
                                if (!nestedDoc) continue;

                                siteKey = buscarSiteKey(nestedDoc);
                                if (siteKey) {
                                    return siteKey;
                                }
                            } catch (e) {
                                // CORS bloqueado, continuar
                                continue;
                            }
                        }
                    } catch (e) {
                        // CORS bloqueado, continuar
                        continue;
                    }
                }

                return null;
            })();
            """

            site_key = await tab.evaluate(site_key_script)

            if site_key:
                print(f"[CAPSOLVER HTTP] ✅ Site key encontrada: {site_key}")
                logger.info(f"Site key extraída: {site_key}")
                return site_key
            else:
                print(f"[CAPSOLVER HTTP] ⚠️ Site key não encontrada!")
                logger.warning("Site key do reCAPTCHA não encontrada na página")
                return None

        except Exception as e:
            print(f"[CAPSOLVER HTTP] ❌ Erro ao extrair site_key: {e}")
            logger.error(f"Erro ao extrair site_key: {e}")
            return None

    async def injetar_token_recaptcha(self, tab, token: str) -> bool:
        """
        Injeta o token resolvido no reCAPTCHA da página (incluindo dentro de iframes)

        Args:
            tab: Tab do Nodriver
            token: Token do CAPTCHA resolvido

        Returns:
            True se injetado com sucesso, False caso contrário
        """
        print(f"\n[CAPSOLVER HTTP] Injetando token no reCAPTCHA...")

        try:
            injetar_script = f"""
            (() => {{
                // Função helper para injetar token em um documento
                function injetarToken(doc) {{
                    let injetado = false;

                    // Método 1: Preencher textarea oculto por ID
                    const textarea = doc.getElementById('g-recaptcha-response');
                    if (textarea) {{
                        textarea.value = '{token}';
                        textarea.innerHTML = '{token}';
                        injetado = true;
                    }}

                    // Método 2: Preencher todas as textareas de reCAPTCHA
                    const textareas = doc.querySelectorAll('textarea[name="g-recaptcha-response"]');
                    textareas.forEach(ta => {{
                        ta.value = '{token}';
                        ta.innerHTML = '{token}';
                        injetado = true;
                    }});

                    // Método 3: Chamar callback do reCAPTCHA se existir
                    const win = doc.defaultView || doc.parentWindow;
                    if (win && typeof win.grecaptcha !== 'undefined') {{
                        try {{
                            const recaptchaElement = doc.querySelector('.g-recaptcha');
                            if (recaptchaElement) {{
                                const callback = recaptchaElement.getAttribute('data-callback');
                                if (callback && typeof win[callback] === 'function') {{
                                    win[callback]('{token}');
                                    injetado = true;
                                }}
                            }}
                        }} catch (e) {{
                            console.log('Erro ao chamar callback:', e);
                        }}
                    }}

                    return injetado;
                }}

                // PASSO 1: Injetar na página principal
                let sucesso = injetarToken(document);

                // PASSO 2: Injetar em TODOS os iframes (incluindo iframe de login)
                const todosIframes = document.querySelectorAll('iframe');
                for (const iframe of todosIframes) {{
                    try {{
                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        if (!iframeDoc) continue;

                        if (injetarToken(iframeDoc)) {{
                            sucesso = true;
                        }}

                        // Injetar em iframes aninhados (iframe dentro de iframe)
                        const nestedIframes = iframeDoc.querySelectorAll('iframe');
                        for (const nestedIframe of nestedIframes) {{
                            try {{
                                const nestedDoc = nestedIframe.contentDocument || nestedIframe.contentWindow.document;
                                if (!nestedDoc) continue;

                                if (injetarToken(nestedDoc)) {{
                                    sucesso = true;
                                }}
                            }} catch (e) {{
                                // CORS bloqueado, continuar
                                continue;
                            }}
                        }}
                    }} catch (e) {{
                        // CORS bloqueado, continuar
                        continue;
                    }}
                }}

                return sucesso;
            }})();
            """

            resultado = await tab.evaluate(injetar_script)

            if resultado:
                print(f"[CAPSOLVER HTTP] ✅ Token injetado com sucesso!")
                logger.info("Token do CAPTCHA injetado na página")

                # Aguardar um pouco para o token ser processado (reduzido de 2s para 0.5s)
                await asyncio.sleep(0.5)
                return True
            else:
                print(f"[CAPSOLVER HTTP] ⚠️ Falha ao injetar token")
                logger.warning("Falha ao injetar token do CAPTCHA")
                return False

        except Exception as e:
            print(f"[CAPSOLVER HTTP] ❌ Erro ao injetar token: {e}")
            logger.error(f"Erro ao injetar token: {e}")
            return False

    async def resolver_recaptcha_automatico(self, tab, site_url: str) -> bool:
        """
        Pipeline completo: extrai site_key, resolve CAPTCHA e injeta token

        Args:
            tab: Tab do Nodriver
            site_url: URL da página atual

        Returns:
            True se resolvido com sucesso, False caso contrário
        """
        print(f"\n{'='*80}")
        print(f"🤖 RESOLVENDO reCAPTCHA AUTOMATICAMENTE VIA HTTP")
        print(f"{'='*80}\n")

        # Passo 1: Extrair site_key
        site_key = await self.extrair_site_key_recaptcha(tab)
        if not site_key:
            print(f"[CAPSOLVER HTTP] ❌ Não foi possível extrair site_key")
            return False

        # Passo 2: Resolver CAPTCHA via HTTP
        token = await self.resolver_recaptcha_v2(site_url, site_key)
        if not token:
            print(f"[CAPSOLVER HTTP] ❌ Não foi possível resolver CAPTCHA")
            return False

        # Passo 3: Injetar token na página
        sucesso = await self.injetar_token_recaptcha(tab, token)
        if not sucesso:
            print(f"[CAPSOLVER HTTP] ❌ Não foi possível injetar token")
            return False

        print(f"\n{'='*80}")
        print(f"✅ reCAPTCHA RESOLVIDO AUTOMATICAMENTE VIA HTTP!")
        print(f"{'='*80}\n")

        return True
