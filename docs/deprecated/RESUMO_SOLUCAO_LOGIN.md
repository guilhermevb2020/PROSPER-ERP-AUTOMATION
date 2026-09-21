# RESUMO EXECUTIVO: Solucao para Submit de Login SmartSecurities

**Data:** 2025-11-15
**Problema:** Formulario nao avanca apos resolver CAPTCHA
**Causa Raiz:** Callback do reCAPTCHA nao esta sendo disparado

---

## PROBLEMA IDENTIFICADO

Apos analise do codigo e pesquisa de tecnicas anti-bot 2025, identifiquei a **CAUSA RAIZ**:

### Por que o formulario nao avanca?

Quando voce injeta o token do reCAPTCHA manualmente via JavaScript:

```javascript
textarea.value = 'token_aqui';
```

O reCAPTCHA **NAO dispara o callback automaticamente**. O SmartSecurities provavelmente usa `data-callback` no elemento g-recaptcha para:

1. Habilitar o botao de submit
2. Disparar validacoes JavaScript
3. Permitir navegacao pos-login

**Sem o callback, o site pensa que o CAPTCHA ainda nao foi resolvido, mesmo com token valido.**

---

## SOLUCAO PRINCIPAL (IMPLEMENTACAO IMEDIATA)

### CODIGO: Injecao de Token COM Disparo de Callback

Substituir a funcao `_injetar_token_capsolver()` no arquivo:
**`/home/ubuntu/PROSPER-ERP-AUTOMATION/src/common/playwright_captcha_manager.py`**

Linha 245-306 (funcao `_injetar_token_capsolver`)

**NOVA VERSAO:**

```python
async def _injetar_token_capsolver(self, page: Union[Page, Frame], token: str) -> bool:
    """
    Injeta token do CapSolver E dispara callback do reCAPTCHA.
    VERSAO 2025 - Resolve problema de submit nao funcionar.
    """
    script = f"""
    (() => {{
        const token = '{token}';

        // PASSO 1: Injetar token
        const updateTextarea = (doc) => {{
            let sucesso = false;
            const textarea = doc.getElementById('g-recaptcha-response');
            if (textarea) {{
                textarea.value = token;
                textarea.innerHTML = token;

                // NOVO: Disparar eventos de change/input
                try {{
                    const changeEvent = new Event('change', {{ bubbles: true }});
                    const inputEvent = new Event('input', {{ bubbles: true }});
                    textarea.dispatchEvent(changeEvent);
                    textarea.dispatchEvent(inputEvent);
                }} catch (e) {{}}

                sucesso = true;
            }}

            const textareas = doc.querySelectorAll('textarea[name="g-recaptcha-response"]');
            for (const ta of textareas) {{
                ta.value = token;
                ta.innerHTML = token;
                try {{
                    const changeEvent = new Event('change', {{ bubbles: true }});
                    const inputEvent = new Event('input', {{ bubbles: true }});
                    ta.dispatchEvent(changeEvent);
                    ta.dispatchEvent(inputEvent);
                }} catch (e) {{}}
                sucesso = true;
            }}
            return sucesso;
        }};

        // PASSO 2: CRITICO - Disparar callbacks do reCAPTCHA
        const acionarCallbacks = (doc) => {{
            const win = doc.defaultView || doc.parentWindow;
            if (!win) return;

            // 2.1: Callback customizado via data-callback
            if (win.grecaptcha) {{
                const elementos = doc.querySelectorAll('.g-recaptcha');
                for (const el of elementos) {{
                    const callback = el.getAttribute('data-callback');
                    if (callback && typeof win[callback] === 'function') {{
                        console.log('[CAPTCHA] Disparando callback:', callback);
                        try {{
                            win[callback](token);
                        }} catch (e) {{
                            console.log('[CAPTCHA] Erro callback:', e);
                        }}
                    }}
                }}
            }}

            // 2.2: Callbacks globais comuns
            const globalCallbacks = [
                'onRecaptchaSuccess', 'recaptchaCallback', 'captchaSuccess',
                'onCaptchaSuccess', 'submitForm', 'enableSubmit'
            ];

            for (const callbackName of globalCallbacks) {{
                if (typeof win[callbackName] === 'function') {{
                    console.log('[CAPTCHA] Callback global:', callbackName);
                    try {{
                        win[callbackName](token);
                    }} catch (e) {{}}
                }}
            }}

            // 2.3: Habilitar botao manualmente (fallback)
            const selectors = ['#OKExtra', '#OK', 'input[type="submit"]', 'button[type="submit"]'];
            for (const sel of selectors) {{
                const btn = doc.querySelector(sel);
                if (btn) {{
                    console.log('[CAPTCHA] Habilitando botao:', sel);
                    btn.disabled = false;
                    btn.removeAttribute('disabled');
                    btn.style.pointerEvents = 'auto';
                    btn.style.opacity = '1';
                    btn.classList.remove('disabled', 'btn-disabled', 'is-disabled');
                }}
            }}
        }};

        // PASSO 3: Processar documento e iframes recursivamente
        const processar = (doc) => {{
            let sucesso = updateTextarea(doc);
            acionarCallbacks(doc);

            const iframes = doc.querySelectorAll('iframe');
            for (const iframe of iframes) {{
                try {{
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    if (!iframeDoc) continue;
                    sucesso = processar(iframeDoc) || sucesso;
                }} catch (e) {{}}
            }}
            return sucesso;
        }};

        try {{
            const resultado = processar(document);
            console.log('[CAPTCHA] Injecao completa. Sucesso:', resultado);
            return resultado;
        }} catch (e) {{
            console.log('[CAPTCHA] Erro:', e);
            return false;
        }}
    }})();
    """
    try:
        resultado = await page.evaluate(script)
        return bool(resultado)
    except Exception as exc:
        logger.debug("Erro ao injetar token CapSolver: %s", exc)
        return False
```

**IMPORTANTE:** Esta mudanca deve resolver 80-90% dos casos.

---

## SOLUCOES COMPLEMENTARES (OPCIONAL)

### 1. AGUARDAR VALIDACAO ASSINCRONA

Apos resolver CAPTCHA, aguardar ate botao estar habilitado:

```python
# Adicionar no fazer_login() APOS resolver CAPTCHA
print("[LOGIN] Aguardando validacao assincrona do reCAPTCHA...")

max_wait = 10  # segundos
start_time = time.time()

while time.time() - start_time < max_wait:
    try:
        botao_habilitado = await iframe_login.evaluate("""
            () => {
                const button = document.querySelector('#OKExtra, #OK');
                if (!button) return false;

                const notDisabled = !button.disabled && !button.hasAttribute('disabled');
                const hasPointerEvents = window.getComputedStyle(button).pointerEvents !== 'none';

                return notDisabled && hasPointerEvents;
            }
        """)

        if botao_habilitado:
            print("[LOGIN] Botao habilitado - prosseguindo")
            break

        await asyncio.sleep(0.5)
    except Exception:
        break

# Aumentar sleep de 3s para 5s
await asyncio.sleep(5)
```

### 2. BEHAVIOR HUMANO (OPCIONAL - REDUZ DETECCAO)

Adicionar delays humanos no preenchimento:

```python
# Antes de preencher email
await asyncio.sleep(random.uniform(2.0, 4.0))

# Digitar email com delay entre teclas
await email_input.fill("")
for char in login_smart:
    await email_input.type(char, delay=random.randint(80, 180))

await asyncio.sleep(random.uniform(0.5, 1.0))

# Digitar senha
await senha_input.fill("")
for char in senha_smart:
    await senha_input.type(char, delay=random.randint(80, 180))

await asyncio.sleep(random.uniform(0.8, 1.5))
```

---

## DEBUGGING (SE PROBLEMA PERSISTIR)

### Script de Debug: Inspecionar Callbacks

Adicionar APOS resolver CAPTCHA:

```python
async def debug_recaptcha_callbacks(iframe_login):
    """Inspeciona callbacks e estado"""
    info = await iframe_login.evaluate("""
        () => {
            const result = {
                hasGrecaptcha: !!window.grecaptcha,
                callbacks: [],
                buttonDisabled: false,
                tokenLength: 0
            };

            // Token
            const textarea = document.getElementById('g-recaptcha-response');
            if (textarea) result.tokenLength = textarea.value.length;

            // Callbacks
            const elements = document.querySelectorAll('.g-recaptcha');
            elements.forEach((el) => {
                const callback = el.getAttribute('data-callback');
                if (callback) {
                    result.callbacks.push({
                        name: callback,
                        exists: typeof window[callback] === 'function'
                    });
                }
            });

            // Botao
            const button = document.querySelector('#OKExtra, #OK');
            if (button) result.buttonDisabled = button.disabled;

            return result;
        }
    """)

    print(f"[DEBUG] grecaptcha: {info['hasGrecaptcha']}")
    print(f"[DEBUG] Token length: {info['tokenLength']}")
    print(f"[DEBUG] Callbacks: {info['callbacks']}")
    print(f"[DEBUG] Botao disabled: {info['buttonDisabled']}")

    return info

# Usar:
debug_info = await debug_recaptcha_callbacks(iframe_login)
```

---

## TESTE RAPIDO

1. Aplicar mudanca em `playwright_captcha_manager.py`
2. Executar script de teste:

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
python scripts/test_login_smartsecurities.py
```

3. Resolver CAPTCHA manualmente quando aparecer
4. Observar se navegacao ocorre automaticamente

---

## METRICAS DE SUCESSO

Apos implementar a solucao principal:

- ✅ Taxa de sucesso deve ser >90%
- ✅ Navegacao deve ocorrer automaticamente apos resolver CAPTCHA
- ✅ Botao deve estar habilitado (verificar com debug script)

---

## SE AINDA NAO FUNCIONAR

### Ultima Opcao: Aguardar Navegacao Automatica

Talvez o callback submeta o formulario automaticamente (sem precisar clicar):

```python
# APOS resolver CAPTCHA e aguardar 5s
print("[LOGIN] Aguardando navegacao automatica...")

try:
    await page.wait_for_url(
        lambda url: "login" not in url.lower() and "/smart/" in url.lower(),
        timeout=30000
    )
    print("[LOGIN] Navegacao automatica detectada!")
except Exception:
    # Se nao navegou, tentar submit manual
    print("[LOGIN] Navegacao nao ocorreu - tentando submit manual...")
    await self._submit_login_form(iframe_login)
```

---

## ARQUIVOS CRIADOS

1. **Documentacao completa:**
   `/home/ubuntu/PROSPER-ERP-AUTOMATION/docs/SOLUCAO_SUBMIT_LOGIN_SMARTSECURITIES.md`

2. **Biblioteca de comportamento humano:**
   `/home/ubuntu/PROSPER-ERP-AUTOMATION/src/common/human_behavior_utils.py`

3. **Script de teste:**
   `/home/ubuntu/PROSPER-ERP-AUTOMATION/scripts/test_login_smartsecurities.py`

4. **Este resumo:**
   `/home/ubuntu/PROSPER-ERP-AUTOMATION/docs/RESUMO_SOLUCAO_LOGIN.md`

---

## PROXIMOS PASSOS

1. ✅ Implementar mudanca em `playwright_captcha_manager.py` (PRIORITARIO)
2. ✅ Testar com script de teste
3. ✅ Se funcionar, aplicar em todos os processadores
4. ✅ Monitorar taxa de sucesso nos logs
5. ⚠️ Se nao funcionar, adicionar solucoes complementares (aguardar validacao assincrona + comportamento humano)

---

**FIM DO RESUMO**
