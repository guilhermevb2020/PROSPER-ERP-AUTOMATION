# REFERÊNCIAS - SISTEMA ANTI-BOT 2025

**Data:** 2025-11-15  
**Compilado para:** PROSPER-ERP-AUTOMATION

---

## PARTE 1: BIBLIOTECAS PYTHON HUMANIZAÇÃO (2025)

### 1.1 Playwright-Stealth (Python)

**PyPI:** `playwright-stealth`  
**GitHub:** Fork mantido pela comunidade  
**Status:** Ativo (última release June 2025)  
**Python:** >=3.9  

**Instalação:**
```bash
pip install playwright-stealth
```

**O que oferece:**
- Remove `navigator.webdriver` flag
- Patches para fingerprints básicos
- Override de propriedades do navegador
- Compatível com Playwright async

**Recomendação PROSPER:** Complementar (PROSPER já cobre isso)

---

### 1.2 Botright (Python)

**PyPI:** `botright`  
**GitHub:** https://github.com/Vinyzu/botright/  
**Status:** Ativo (v0.2.2+)  
**Python:** >=3.9  

**Instalação:**
```bash
pip install botright
```

**O que oferece:**
- Fingerprint rotation automática
- AI-powered CAPTCHA solver (sem API paga)
- Human behavior advanced
- Real Chromium from system
- Menos detectável TLS

**Diferenciais:**
- Muda fingerprints entre requisições (PROSPER é fixo)
- Usa Computer Vision para CAPTCHA (PROSPER usa CapSolver API)
- Real system Chromium (PROSPER usa bundled)

**Recomendação PROSPER:** Experimental para futuro

---

### 1.3 Humanization-Playwright (Python)

**PyPI:** `humanization-playwright`  
**GitHub:** https://github.com/nicoandmee/playwright-humanize  
**Status:** Ativo  
**Arquitetura:** Built on Patchright (undetected Playwright)  

**Instalação:**
```bash
pip install humanization-playwright
```

**O que oferece:**
- Cubic Bezier curves com jitter (melhor que PROSPER)
- Typing patterns com variabilidade
- Async full integration
- Seamless Playwright integration

**Diferenciais:**
- Mouse movements mais realistas (Bezier vs linear)
- Pauses e hesitações naturais
- Bem mantido 2025

**Recomendação PROSPER:** Integração recomendada para mouse movements

---

### 1.4 Undetected-Playwright (Python)

**PyPI:** `undetected-playwright`  
**GitHub:** https://github.com/kaliiiiiiiiii/undetected-playwright-python  
**Alternativa:** `Patchright-python` (mais recente)  
**Status:** Community maintained  

**O que oferece:**
- Patches profundas ao Playwright
- Alterações diretas no protocolo CDP
- Async API completa
- Browser signature spoofing

**Diferenciais:**
- Protocol-level spoofing (vs script injection)
- Menos detectável em TLS
- Experimental

**Recomendação PROSPER:** Futuro se Playwright vanilla não for suficiente

---

### 1.5 Playwright-Extra (Node.js - Referência)

**npm:** `playwright-extra` + `puppeteer-extra-plugin-stealth`  
**GitHub:** https://github.com/berstend/puppeteer-extra  
**Status:** Ativo (6.4k stars)  
**Tipos:** TypeScript nativo  

**Plugins Disponíveis 2025:**
1. Stealth Plugin - Remove sinais de automação
2. Proxy Router - Rotação de proxies
3. reCAPTCHA Solver - Resolve CAPTCHA
4. Custom plugins - Comunidade criando

**Recomendação PROSPER:** Node.js only (não aplicável)

---

## PARTE 2: DOCUMENTAÇÃO SMARTSECURITIES

### 2.1 Arquivos Locais PROSPER

**CRÍTICA:**
- `/docs/ANALISE_ANTI_BOT_SMARTSECURITIES.md` - Risk score 60/200 (30%)
- `/docs/SOLUCAO_DEFINITIVA_ANTI_DETECCAO_2025.md` - Estratégia completa
- `/docs/SOLUCAO_SUBMIT_LOGIN_SMARTSECURITIES.md` - Login specifics

**IMPORTANTE:**
- `src/common/anti_detection_2025.py` - DEPRECADO (usar novos módulos)
- `src/common/fingerprinting/` - Módulos individuais (7 existentes)

### 2.2 Score SmartSecurities

```
Score Atual: 60/200 (30% - MÉDIO)
Com PROSPER: ~150/200 (75% - BOM)
Com novos módulos: ~195/200 (97% - EXCELENTE)
```

### 2.3 Proteções Identificadas (9)

| # | Proteção | Vetor | Solução PROSPER |
|---|----------|--------|-----------------|
| 1 | Cloudflare Turnstile | CAPTCHA | CapSolver API |
| 2 | WebRTC Leak | IP leak | WebRTCBlocker |
| 3 | Network Monitoring | Fetch interceptado | XHR nativo |
| 4 | Canvas Fingerprint | JavaScript | CanvasFingerprint |
| 5 | WebGL Fingerprint | Graphics API | WebGLFingerprint |
| 6 | Audio Fingerprint | Audio context | AudioFingerprint |
| 7 | Font Detection | CSS metrics | FontFingerprinting (NOVO) |
| 8 | Hardware Info | Navigator API | NavigatorOverrides |
| 9 | Timezone/Locale | Browser config | Context config |

---

## PARTE 3: PESQUISA 2025 - TÉCNICAS AVANÇADAS

### 3.1 Font Fingerprinting

**Detecção:**
- BrowserLeaks FontFingerprint database
- Canvas.measureText() para dimensões
- CSS offset metrics
- Element height/width variações

**Bypass 2025:**
- Override canvas.measureText()
- Adicionar noise ao getComputedStyle()
- Randomizar offset dimensions
- Usar FontFingerprint.js contra si mesmo

**Referências:**
- https://browserleaks.com/fonts
- https://github.com/w3cping/font-anti-fingerprinting
- https://undetectable.io/blog/fonts-browser-fingerprints/

---

### 3.2 CSS Fingerprinting

**Detecção:**
- window.matchMedia() para media queries
- CSS 3D transforms availability
- CSS.supports() feature detection
- CSS prefixes (webkit, moz, etc)

**Bypass 2025:**
- Override window.matchMedia()
- Mock CSS.supports()
- Randomizar prefixes com seed
- Simular diferentes CSS engines

**Referências:**
- https://scrapfly.io/blog/posts/browser-fingerprinting-with-creepjs
- https://browsercat.com/post/browser-fingerprint-spoofing-explained

---

### 3.3 DeviceOrientation/Motion

**Detecção:**
- window.DeviceOrientationEvent disponível?
- window.DeviceMotionEvent?
- GPS/Accelerometer simulado?

**Bypass 2025:**
- Bloquear completamente (mais realista para desktop)
- Simular valores fake se necessário
- Negar permissões

**Referências:**
- MDN WebDocs DeviceOrientationEvent
- MDN WebDocs DeviceMotionEvent

---

### 3.4 WebAssembly Detection

**Detecção:**
- window.WebAssembly disponível?
- Suporte a WebAssembly.instantiate()?

**Bypass 2025:**
- Negar acesso (undefined)
- Simular com erro "not supported"
- Alguns usuários desktop não têm

**Referências:**
- https://litport.net/blog/creepjs-detection-prevention-guide-76978
- ArXiv: The WASM Cloak (2508.21219)

---

### 3.5 TLS Fingerprinting / JA3

**Detecção:**
- TLS handshake signature (JA3)
- HTTP header order
- Cipher suite ordering
- SSL version

**Bypass 2025:**
- Usar curl_cffi (Python) para JA3 customizado
- Residential proxy com real OS
- Alternativa: Nodriver (CDPless)

**Complexidade:** ALTA - requer C-level changes

**Referências:**
- https://roundproxies.com/blog/what-is-tls-fingerprint/
- https://www.capsolver.com/blog/Cloudflare/cloudflare-tls
- https://rebrowser.net/blog/tls-fingerprinting-advanced-guide-for-security-engineers

---

### 3.6 Nodriver vs Playwright

**Comparação 2025:**

| Aspecto | Playwright | Nodriver |
|---------|-----------|----------|
| Detecção CDPless | ✅ Detectável | ❌ Não (CDPless) |
| TLS Signature | ⚠️ Automação | ✅ Nativa |
| Performance | ✅ Rápido | ⚠️ Mais lento |
| Manutenção | ✅ Ativa | ✅ Ativa |
| Python 2025 | ✅ Sim | ✅ Sim |

**Referências:**
- https://blog.castle.io/from-puppeteer-stealth-to-nodriver/
- https://medium.com/@dimakynal/baseline-performance-comparison...
- https://github.com/ultrafunkamsterdam/nodriver

---

## PARTE 4: DETECTORES A VALIDAR

### 4.1 CreepJS

**URL:** https://creepjs.com/  
**O que detecta:**
- Canvas fingerprinting
- WebGL fingerprinting
- Audio fingerprinting
- Font detection
- WebAssembly support
- DeviceOrientation
- TLS fingerprinting (proxy info)

**Como testar:**
```python
# Abrir SmartSecurities + chamar CreepJS.js
# Verificar score final
```

---

### 4.2 Fingerprint.com (Fingerprint Pro)

**URL:** https://fingerprint.com/  
**O que detecta:**
- Canvas fingerprinting
- WebGL fingerprinting
- Font detection
- Screen resolution
- Timezone
- Hardware concurrency
- TLS signature

---

### 4.3 BrowserLeaks

**URL:** https://browserleaks.com/  
**O que detecta:**
- Font fingerprinting
- WebRTC leak
- DNS leak
- HTTP leak
- Canvas/WebGL
- Timezone
- Battery API

---

## PARTE 5: TÉCNICAS ANTI-DETECÇÃO POR CATEGORIA

### 5.1 JavaScript-Level Injection

**Técnicas:**
```javascript
// 1. Override prototypes
Object.defineProperty(navigator, 'webdriver', { get: () => undefined })

// 2. Proxy interception
const handler = {
    apply(target, thisArg, args) { ... }
};
WebGLRenderingContext.getParameter = new Proxy(..., handler)

// 3. Canvas manipulation
CanvasRenderingContext2D.prototype.toDataURL = function(...) { ... }

// 4. Event blocking
window.RTCPeerConnection = function() { throw Error(...) }
```

**Implementação:** page.add_init_script()

---

### 5.2 Browser Flags / Arguments

**Chromium args:**
```
--disable-webrtc              # WebRTC blocker
--disable-blink-features=AutomationControlled
--disable-features=IsolateOrigins,site-per-process
--disable-dev-shm-usage       # Linux
--no-sandbox                  # Docker
```

---

### 5.3 Context Configuration

**Playwright Context:**
```python
context = await browser.new_context(
    viewport={'width': 1920, 'height': 1080},
    locale='pt-BR',
    timezone_id='America/Sao_Paulo',
    user_agent='Mozilla/5.0...',
    extra_http_headers={'Accept-Language': 'pt-BR,...'},
)
```

---

### 5.4 Human Behavior Simulation

**Técnicas:**
- Mouse movement com Bezier curves
- Typing com velocidade variável
- Pauses aleatórias entre ações
- Scroll patterns naturais
- Click timing realista
- Hover delays

**Implementação:** `human_behavior_utils.py`

---

### 5.5 Rate Limiting Inteligente

**Técnicas:**
- Exponential backoff (2^n)
- Operations per hour limit
- Histórico de requisições
- Retry com delay crescente
- Respeitar Retry-After header

**Implementação:** `RateLimiter` em `anti_detection_2025.py`

---

## PARTE 6: FERRAMENTAS & RECURSOS

### 6.1 npm Packages (Referência)

```bash
# Stealth plugins (Node.js)
npm install playwright-extra puppeteer-extra-plugin-stealth

# Python equivalentes
pip install playwright-stealth
pip install botright
pip install humanization-playwright
```

---

### 6.2 GitHub Repositories

| Projeto | GitHub | Linguagem | Status 2025 |
|---------|--------|-----------|-----------|
| Botright | github.com/Vinyzu/botright | Python | Ativo |
| undetected-playwright | github.com/kaliiiiiiiiii/undetected-playwright-python | Python | Community |
| Patchright | github.com/Kaliiiiiiiiii-Vinyzu/patchright-python | Python | Novo |
| Nodriver | github.com/ultrafunkamsterdam/nodriver | Python | Ativo |
| playwright-extra | github.com/berstend/puppeteer-extra | TypeScript | Ativo |

---

### 6.3 Documentação Oficial

| Recurso | URL |
|---------|-----|
| Playwright Docs | https://playwright.dev/ |
| Cloudflare Turnstile | https://developers.cloudflare.com/turnstile/ |
| CapSolver Docs | https://docs.capsolver.com/ |
| MDN - Canvas | https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API |
| MDN - WebGL | https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API |
| MDN - WebRTC | https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API |

---

### 6.4 Blogs & Artigos 2025

| Título | Fonte | Relevância |
|--------|-------|-----------|
| "From Puppeteer stealth to Nodriver" | castle.io | 🔴 Crítica |
| "How to Make Playwright Undetectable" | ScrapeOps | 🟡 Alta |
| "Browser Fingerprinting Defense 2025" | mr-alias.com | 🟡 Alta |
| "TLS Fingerprinting Advanced Guide 2025" | Rebrowser | 🟡 Alta |
| "Best Undetected ChromeDriver Alternatives" | neurofiq.in | 🟡 Alta |
| "Top 7 Browser Automation Tools 2025" | brightdata.com | 🟢 Média |

---

## PARTE 7: INTEGRAÇÃO RECOMENDADA

### 7.1 Adicionar humanization-playwright

**Passo 1: Instalar**
```bash
pip install humanization-playwright
```

**Passo 2: Usar em human_behavior_utils.py**
```python
from humanization_playwright import HumanBehavior
# Ou integrar técnicas Bezier ao código existente
```

---

### 7.2 Adicionar Font Fingerprinting

**Passo 1: Criar novo módulo**
```python
# src/common/fingerprinting/font_fingerprinting.py
class FontFingerprinting:
    @staticmethod
    async def inject(page):
        await page.add_init_script("""
            // Override canvas.measureText()
            // Adicionar noise
            // Randomizar offsets
        """)
```

---

### 7.3 Adicionar CSS Fingerprinting

**Passo 1: Criar novo módulo**
```python
# src/common/fingerprinting/css_fingerprinting.py
class CSSFingerprinting:
    @staticmethod
    async def inject(page):
        await page.add_init_script("""
            // Override window.matchMedia()
            // Mock CSS.supports()
        """)
```

---

## PARTE 8: TIMELINE RECOMENDADA

### Imediato (Próximas 2 horas)
- Revisar documento roadmap completo
- Planejar Fase 1 (Fixes rápidos)

### Curto Prazo (Próxima semana)
- Implementar Fase 1-2 (novos módulos core)
- Testar em SmartSecurities
- Atingir 9.0/10

### Médio Prazo (Próximas 2 semanas)
- Implementar Fase 3-4 (fine-tuning)
- Validação completa
- Atingir 9.5/10

### Longo Prazo (Próximo mês)
- Implementar Fase 5 (avançada)
- Considerar Nodriver vs Playwright
- Atingir 9.8+/10

---

## PARTE 9: PERGUNTAS FREQUENTES

### P: Qual biblioteca usar?
**R:** Manter PROSPER. Opcional: integrar `humanization-playwright` para Bezier curves.

### P: Botright é melhor que PROSPER?
**R:** Botright tem fingerprint rotation e AI CAPTCHA, mas é mais complexo. PROSPER é mais simples e estável.

### P: TLS fingerprinting é necessário?
**R:** Para SmartSecurities: não. Para sites avançados (Cloudflare, Akamai): talvez.

### P: Nodriver vs Playwright?
**R:** Nodriver é melhor para TLS, mas mais lento. Playwright é suficiente para 95% dos casos.

### P: Font fingerprinting é crítico?
**R:** Sim para sites avançados, não para SmartSecurities. Mas implementar ajuda.

---

## CONCLUSÃO

PROSPER está em excelente estado (7.5/10). Próximos passos são bem definidos:

1. Implementar Fase 1-4 para 9.5/10 (5 dias, 15 horas)
2. Validação completa (1 dia)
3. Deploy em produção

Fase 5 (TLS, Nodriver) é opcional e futura.

---

**Data:** 2025-11-15  
**Versão:** 1.0  
**Próxima atualização:** Após implementação Fase 2

