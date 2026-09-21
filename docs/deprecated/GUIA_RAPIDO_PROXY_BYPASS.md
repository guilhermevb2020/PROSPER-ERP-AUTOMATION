# GUIA RÁPIDO: Proxy Bypass para reCAPTCHA

**Problema:** Bright Data Residential Proxy bloqueia Google reCAPTCHA (erro 502 bad_endpoint)

**Solução:** Usar proxy APENAS para SmartSecurities, bypass para Google

---

## USO BÁSICO

### Código Atual (JÁ IMPLEMENTADO)

```python
from src.common.brightdata_proxy import get_proxy_config, get_stealth_context

# Launch com proxy Bright Data
proxy_config = get_proxy_config()
browser = await playwright.chromium.launch(proxy=proxy_config)

# Context com bypass automático para Google (PADRÃO)
context = await browser.new_context(**get_stealth_context())
```

**Resultado:**
- ✅ SmartSecurities: Usa proxy (anti-detecção)
- ✅ Google reCAPTCHA: Usa conexão direta (funciona)
- ✅ Downloads: Usa proxy (anti-detecção)

---

## O QUE MUDOU?

### ANTES (com erro)
```python
context = await browser.new_context(**get_stealth_context())
# PROBLEMA: Todos os domínios (incluindo Google) usavam proxy
# RESULTADO: reCAPTCHA bloqueado (erro 502 bad_endpoint)
```

### AGORA (solução)
```python
context = await browser.new_context(**get_stealth_context())
# SOLUÇÃO: Google usa conexão direta, resto usa proxy
# RESULTADO: reCAPTCHA funciona normalmente
```

**Mudança invisível:** O bypass está ATIVADO por padrão, nada precisa ser alterado no seu código.

---

## DOMÍNIOS COM BYPASS (conexão direta)

```
*.google.com              → reCAPTCHA API, Search, etc
*.gstatic.com             → Google Static (fonts, scripts)
*.googleusercontent.com   → User-generated content
*.googleapis.com          → Google APIs
*.doubleclick.net         → Google Ads
*.google-analytics.com    → Analytics
*.googletagmanager.com    → Tag Manager
*.googlesyndication.com   → AdSense
*.googleadservices.com    → Ad services
```

**Todos os outros domínios:** Usam proxy Bright Data normalmente.

---

## OPÇÕES AVANÇADAS

### Desativar Bypass (não recomendado)

```python
# APENAS se você quiser que Google use proxy (vai falhar)
context = await browser.new_context(
    **get_stealth_context(enable_proxy_bypass=False)
)
```

**Quando usar:** Nunca, exceto para testes de debugging.

### Adicionar Domínios ao Bypass

**Arquivo:** `src/common/brightdata_proxy.py`

```python
bypass_domains = [
    '*.google.com',
    '*.gstatic.com',
    # ... outros domínios Google ...
    '*.seudominio.com',  # Adicionar aqui
]
```

**Quando usar:** Se outro serviço externo estiver bloqueando o proxy.

---

## TESTES

### Executar Teste Automatizado

```bash
python tests/test_brightdata_proxy_bypass.py
```

**Testes incluídos:**
1. ❌ Proxy SEM bypass → Google deve falhar (teste de controle)
2. ✅ Proxy COM bypass → Google deve funcionar (teste real)
3. ✅ Verificação de IP → Deve ser do proxy para sites normais

### Teste Manual Rápido

```python
# No seu script de automação
context = await browser.new_context(**get_stealth_context())
page = await context.new_page()

# Verificar se reCAPTCHA carrega
await page.goto("https://www.google.com/recaptcha/api2/demo")
# Se carregar = ✅ bypass funcionou
# Se erro 502 = ❌ bypass falhou
```

---

## FAQ

### 1. Preciso alterar meu código?

**NÃO.** Se você já usa `get_stealth_context()`, o bypass está ativado automaticamente.

### 2. Google vai ver meu IP real?

**SIM, mas não é problema:**
- Google não é o alvo (SmartSecurities é)
- Resolver CAPTCHA legitimamente não viola ToS
- SmartSecurities continua vendo IP do proxy

### 3. Isso reduz segurança?

**NÃO:**
- SmartSecurities: 100% protegido (proxy + fingerprinting + sticky IP)
- Google: Conexão direta normal (igual a um browser comum)
- Nenhum dado sensível exposto

### 4. Isso aumenta custos Bright Data?

**NÃO, reduz:**
- Google resources não consomem dados do proxy
- Economia de ~20-30% em dados
- Evita desperdício com requests que falham (bad_endpoint)

---

## TROUBLESHOOTING

### reCAPTCHA ainda não carrega

1. **Verificar logs:**
   ```
   INFO - Bright Data: Proxy BYPASS ativado para 9 domínios Google
   ```
   Se não aparecer = bypass não ativou.

2. **Verificar .env:**
   ```bash
   BRIGHTDATA_PROXY_USERNAME=brd-customer-xxx-zone-residential_proxy1
   BRIGHTDATA_PROXY_PASSWORD=xxx
   ```

3. **Teste sem proxy:**
   ```python
   # Comentar temporariamente
   # proxy_config = get_proxy_config()
   browser = await playwright.chromium.launch()  # Sem proxy
   ```
   Se funcionar = problema é proxy (bypass não funcionou).

### Erro "bad_endpoint" ainda aparece

1. **Verificar se bypass está ativado:**
   - Olhar logs: "Proxy BYPASS ativado..."
   - Se não aparecer, bypass não ativou

2. **Verificar domínio bloqueado:**
   - Se erro em outro domínio (não Google), adicionar ao bypass

3. **Teste com bypass desativado:**
   ```python
   context = await browser.new_context(
       **get_stealth_context(enable_proxy_bypass=False)
   )
   ```
   Se erro continua = não é problema de bypass (é outro domínio).

---

## REFERÊNCIAS

- **Documentação Completa:** `/docs/SOLUCAO_BRIGHTDATA_RECAPTCHA.md`
- **Código Fonte:** `/src/common/brightdata_proxy.py`
- **Testes:** `/tests/test_brightdata_proxy_bypass.py`
