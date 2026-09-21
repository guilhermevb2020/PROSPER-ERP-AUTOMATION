# ROADMAP ANTI-BOT PRAGMÁTICO - SIMPLIFICADO E ROBUSTO

**Data:** 2025-11-15  
**Objetivo:** Aumentar score de 7.5 → 8.5-9.0 (BOM SUFICIENTE)  
**Manutenção:** Uma pessoa pode manter  
**Filosofia:** Simplicidade > Perfeição

---

## 📊 ANÁLISE SMARTSECURITIES - REALIDADE

### Risk Score: 60/200 (30% - MÉDIO)

**5 Proteções REALMENTE CRÍTICAS:**

| # | Proteção | Status | Impacto | Solução |
|---|----------|--------|--------|---------|
| 1 | 🚨 **WebRTC vaza IP real** | CRÍTICO | Alto | Bloquear completamente |
| 2 | 🚨 **Cloudflare Turnstile** | CRÍTICO | Alto | CapSolver (já resolve 100%) |
| 3 | ⚠️ **Network Fetch interceptado** | IMPORTANTE | Médio | Restaurar fetch original |
| 4 | ⚠️ **Fingerprinting básico ativo** | IMPORTANTE | Médio | Perfil consistente |
| 5 | ⚠️ **Timezone/Locale detection** | IMPORTANTE | Baixo | Configurar correto |

**SEM proteções avançadas:** DataDome, PerimeterX, reCAPTCHA v3, hCaptcha - Tudo FÁCIL.

---

## ✅ O QUE JÁ FUNCIONA (NÃO MEXER)

```
✅ CapSolver resolve Turnstile 100% (já implementado)
✅ Comportamento humano com delays (já implementado)
✅ Rate limiting com backoff (já implementado)
✅ Rotação de credenciais (já implementado)
✅ Hardware profiles consistentes (já implementado)
✅ Screenshots automáticas (já implementado)
```

**Score fornecido por essas features: ~7.5/10**

---

## 🎯 ROADMAP ESSENCIAL (3-4 DIAS)

### PRIORIDADE 1: FIX CRÍTICOS (Dia 1 - 4 horas)

#### 1.1 Bloquear WebRTC (CRÍTICO - 1h)
**Por quê:** IP real está vazando via WebRTC  
**Esforço:** 1 hora  
**Impacto:** ALTO (reduz detecção 15-20%)

**Checklist:**
- [ ] Adicionar flag Chromium: `--disable-web-resources` ou `--disable-features=WebRtcAllowMediaStreamToPeerConnection`
- [ ] Criar init script que bloqueia `RTCPeerConnection`
- [ ] Testar: Nenhuma leak de IP detectada
- [ ] Score esperado: 7.5 → 7.9

**Arquivo:** `src/common/anti_detection_2025.py` (já existe, melhorar)

**Código essencial:**
```python
# Em create_browser_context()
args=['--disable-features=WebRtcAllowMediaStreamToPeerConnection'],

# Em page setup
await page.add_init_script("""
    window.RTCPeerConnection = function() {
        throw new Error('WebRTC disabled');
    };
""")
```

#### 1.2 Restaurar Fetch Original (IMPORTANTE - 2h)
**Por quê:** SmartSecurities intercepta `fetch` para monitorar requisições  
**Esforço:** 2 horas  
**Impacto:** MÉDIO (evita bloqueios por comportamento anormal)

**Checklist:**
- [ ] Salvar `fetch` original ANTES de navegação
- [ ] Restaurar antes de requisições críticas (download, login)
- [ ] Usar `XMLHttpRequest` como fallback
- [ ] Testar: Requisições passam por monitoramento
- [ ] Score esperado: 7.9 → 8.2

**Arquivo:** `src/common/anti_detection_2025.py`

**Código essencial:**
```python
# Antes de navegar
await page.add_init_script("""
    window.__originalFetch = window.fetch;
    window.__originalXHR = window.XMLHttpRequest;
""")

# Antes de requisição crítica
await page.evaluate("""
    window.fetch = window.__originalFetch;
""")
```

#### 1.3 Timezone & Locale Corretos (IMPORTANTE - 1h)
**Por quê:** SmartSecurities detecta timezone (deve ser America/Sao_Paulo)  
**Esforço:** 1 hora  
**Impacto:** MÉDIO (consistência simples)

**Checklist:**
- [ ] Setar em `playwright_context_config`: `locale: "pt-BR"`, `timezone_id: "America/Sao_Paulo"`
- [ ] Validar via JavaScript
- [ ] Testar consistência entre execuções
- [ ] Score esperado: 8.2 → 8.4

**Arquivo:** `src/common/browser/` ou `src/common/config_loader.py`

---

### PRIORIDADE 2: MELHORIAS DE ROBUSTEZ (Dia 2-3 - 6 horas)

#### 2.1 Fingerprints Consistentes (IMPORTANTE - 2h)
**Por quê:** Canvas, WebGL, Audio devem ser mesmos entre execuções  
**Esforço:** 2 horas  
**Impacto:** MÉDIO (evita "usuário diferente" a cada execução)

**Checklist:**
- [ ] Usar `hardware_profiles.py` para gerar seeds fixos por processador
- [ ] Canvas: injeta noise com seed determinístico (não aleatório)
- [ ] WebGL: usa valores fixos do perfil
- [ ] Audio: injeta padrão de frequência consistente
- [ ] Score esperado: 8.4 → 8.6

**Arquivo:** `src/common/hardware_profiles.py` (já existe, usar melhor)

**Decisão simples:**
```python
# NÃO fazer:
canvas_noise = random.randint(0, 255)  # ❌ Diferente cada execução

# FAZER:
processor_seed = hash("relatorio_operacao_desagio") % 10000
canvas_noise = (processor_seed + frame_num) % 256  # ✅ Determinístico
```

#### 2.2 Headers & User-Agent Consistentes (IMPORTANTE - 1h)
**Por quê:** Headers devem corresponder ao user-agent escolhido  
**Esforço:** 1 hora  
**Impacto:** BAIXO (mas evita red flags)

**Checklist:**
- [ ] User-Agent = Hardware Profile
- [ ] Headers: `Accept-Language: pt-BR,en-US,pt,en`
- [ ] Headers: `Sec-Ch-Ua` compatível com User-Agent
- [ ] Verificar logs: Headers consistentes
- [ ] Score esperado: 8.6 → 8.7

**Arquivo:** `src/common/hardware_profiles.py`

#### 2.3 Comportamento Humano Melhorado (IMPORTANTE - 3h)
**Por quê:** Remover padrões mecânicos (delays exatos, mesma sequência)  
**Esforço:** 3 horas  
**Impacto:** MÉDIO (detecção comportamental)

**Checklist:**
- [ ] Delays variáveis: 500-2000ms (não 1000ms fixo)
- [ ] Mouse movements com curva natural (Bezier)
- [ ] Scroll aleatório antes de clicar (humano sempre faz isso)
- [ ] Occasional "hesitation" (pausa antes de ação)
- [ ] Validar via script que detecta padrões
- [ ] Score esperado: 8.7 → 8.9

**Arquivo:** `src/common/human_behavior_utils.py` (já existe, melhorar aleatoriedade)

---

### PRIORIDADE 3: POLISH (Dia 4 - 2 horas)

#### 3.1 Logs Estruturados (NICE-TO-HAVE - 1h)
**Checklist:**
- [ ] Quando WebRTC é bloqueado: log específico
- [ ] Quando fetch é restaurado: log específico
- [ ] Dashboard simples: score estimado por categoria
- [ ] Facilita debugging se taxa de sucesso cair

#### 3.2 Testes Automatizados (NICE-TO-HAVE - 1h)
**Checklist:**
- [ ] Script que acessa page de anti-bot analysis (fake)
- [ ] Verifica: WebRTC bloqueado, Fetch ok, Timezone correto
- [ ] Valida hardware profile consistência
- [ ] Pode rodar 1x por semana

---

## 📋 CHECKLIST IMPLEMENTAÇÃO

### Fase 1: WebRTC + Fetch (Dia 1)
```markdown
- [ ] Criar `src/common/browser/webrtc_blocker.py`
      - Bloqueia WebRTC completamente
      - Testa: Nenhuma leak detectada
      
- [ ] Atualizar `src/common/browser/fetch_restorer.py`
      - Salva fetch original
      - Restaura antes de requisições críticas
      
- [ ] Atualizar `src/common/config_loader.py`
      - Setar timezone correto
      - Setar locale correto
      
- [ ] Testar em um processador
      - Executar 5x seguidas
      - Verificar logs: sem erros de detecção
```

### Fase 2: Fingerprints Consistentes (Dia 2)
```markdown
- [ ] Atualizar `src/common/hardware_profiles.py`
      - Canvas seed = determinístico por processador
      - WebGL valores fixos
      - Audio padrão fixo
      
- [ ] Testar consistência
      - Rodar mesmo processador 3x
      - Comparar fingerprints (devem ser iguais)
      
- [ ] Atualizar `src/common/anti_detection_2025.py`
      - Usar perfil como seed
```

### Fase 3: Comportamento Humano (Dia 2-3)
```markdown
- [ ] Atualizar `src/common/human_behavior_utils.py`
      - Variabilidade em delays
      - Scroll aleatório
      - Hesitations ocasionais
      
- [ ] Testar 10 execuções
      - Cada execução tem pattern diferente
      - Mas sucesso é consistente (>95%)
```

### Fase 4: Testing & Polish (Dia 4)
```markdown
- [ ] Criar script de teste anti-bot
      - Simula analysis do scanner
      - Valida cada proteção
      
- [ ] Update documentação
      - scores por categoria
      - Como debugar cada proteção
      
- [ ] Commit & changelog
```

---

## 🔧 ARQUIVOS A MODIFICAR

**Criar novo:**
```
src/common/browser/webrtc_blocker.py      (novo - 50 linhas)
src/common/browser/fetch_restorer.py      (novo - 50 linhas)
tests/integration/test_anti_bot.py        (novo - 100 linhas)
```

**Melhorar (não reescrever):**
```
src/common/anti_detection_2025.py         (+ WebRTC + Fetch)
src/common/hardware_profiles.py           (+ seeds determinísticos)
src/common/human_behavior_utils.py        (+ variabilidade)
src/common/config_loader.py               (+ timezone/locale)
```

**Não mexer:**
```
✅ src/processors/web/relatorio_*.py     (funcionam bem)
✅ src/common/playwright_captcha_manager.py
✅ src/common/rate_limit_handler.py
```

---

## 📊 SCORE PROGRESSION

| Fase | WebRTC | Fetch | TZ/Locale | FP Consistentes | Human Behavior | Score |
|------|--------|-------|-----------|-----------------|-----------------|-------|
| Atual | ❌ | ❌ | ❌ | ⚠️ | ✅ | **7.5** |
| Fase 1 | ✅ | ✅ | ✅ | ⚠️ | ✅ | **8.2** |
| Fase 2 | ✅ | ✅ | ✅ | ✅ | ✅ | **8.6** |
| Fase 3 | ✅ | ✅ | ✅ | ✅ | ✅✅ | **8.9** |

**Score realista:** 8.9/10 (não 10/10 porque SmartSecurities sempre terá detecção básica)

---

## ⚠️ O QUE NÃO FAZER (AVOID)

```markdown
❌ TLS Fingerprinting
   - Requer curl_cffi, fora do escopo Playwright
   - Impacto: 2-3% improvement
   - Esforço: 20+ horas
   - SKIP

❌ Residential Proxy
   - Já tentamos, bloqueia Google
   - Causa mais problemas que resolve
   - SKIP

❌ Puppeteer (em vez de Playwright)
   - Problema não está no framework
   - Movimento lateral desnecessário
   - SKIP

❌ TLS Versioning, HTTP/2
   - SmartSecurities não valida
   - Ruído técnico
   - SKIP

❌ Random Canvas fingerprints (a cada execução)
   - Parece "usuário diferente"
   - SmartSecurities detecta como bot
   - SKIP

❌ Plugins/Extensions Chrome falsas
   - Complexidade altíssima
   - Manutenção impossível para 1 pessoa
   - SKIP
```

---

## 🚀 TIMELINE REALISTA

```
Dia 1 (4h):
  - 14:00-15:00: WebRTC Blocker (1h)
  - 15:00-17:00: Fetch Restorer (2h)
  - 17:00-18:00: Timezone/Locale Config (1h)
  - Teste básico

Dia 2 (6h):
  - 09:00-11:00: Fingerprints Determinísticos (2h)
  - 11:00-12:00: Headers Consistency (1h)
  - 13:00-16:00: Comportamento Humano (3h)
  - Teste robusto: 10 execuções

Dia 3 (2h):
  - 09:00-10:00: Script de Testing
  - 10:00-11:00: Documentação + Commit

Dia 4 (Reserve):
  - Debugging se necessário
  - Ajustes finais
```

---

## 📈 COMO VALIDAR

### 1. Verificação Imediata (pós Dia 1)
```bash
# Cada execução loga isso:
[2025-11-15 14:30:45] ✅ WebRTC bloqueado
[2025-11-15 14:30:45] ✅ Fetch original restaurado
[2025-11-15 14:30:45] ✅ Timezone: America/Sao_Paulo
[2025-11-15 14:31:20] ✅ Turnstile resolvido
[2025-11-15 14:32:10] ✅ Relatório baixado
```

### 2. Teste de Consistência (pós Dia 2)
```bash
# Rodar 3x seguidas
./run_processor.sh 3
# Todos com sucesso? ✅
# Mesmos fingerprints (Canvas/WebGL/Audio)? ✅
```

### 3. Teste Anti-Bot Detector (pós Dia 3)
```bash
# Script simula análise Deep Protection
pytest tests/integration/test_anti_bot.py
# Resultado: todas proteções detectadas
```

---

## 🛡️ MANUTENÇÃO PÓS-IMPLEMENTAÇÃO

### Verificações Mensais (15 min):
```
□ Taxa de sucesso > 90%? Se não:
  - Verificar logs para padrões
  - SmartSecurities adicionou proteção nova?
  - Ajustar delays se necessário

□ WebRTC leak? Se sim:
  - Atualizar flags Chromium
  - Testar novo browser version

□ Fetch interceptado? Se sim:
  - Pode ser site update
  - Restaurar fetch em mais locais
```

### Quando adicionar mais proteção:
```
✅ SE taxa cai < 85% consistentemente
✅ SE SmartSecurities adiciona proteção NOVA
✅ SE análise detecta nova brecha

❌ Se taxa > 90%: NÃO mexer (não vai estragar!)
❌ Se é para "melhorar de 8.9 para 9.1": deixar
```

---

## 📝 PRINCÍPIOS DE DESIGN

### Simplicidade > Sofisticação
```
✅ if webrtc_detected: block_it()
❌ if webrtc_detected: use_tls_fingerprinting_and_randomize_user_agent_and_...
```

### Determinismo > Aleatoriedade
```
✅ Canvas noise = f(processador_id, frame_number) → DETERMINÍSTICO
❌ Canvas noise = random() → DIFERENTE cada execução
```

### Consistência > Perfeição
```
✅ Mesmo processador SEMPRE com mesmo fingerprint
❌ Cada execução com fingerprint aleatório (parece bot)
```

### Manutenível > Complexo
```
✅ Código que 1 pessoa entende em 5 minutos
❌ Código que requer PhD em anti-bot para mexer
```

---

## ✅ FINAL CHECKLIST

Antes de considerar PRONTO:

- [ ] WebRTC 100% bloqueado (valida com ferramentas online)
- [ ] Fetch original restaurado (logs confirmam)
- [ ] Timezone correto (valida via JavaScript)
- [ ] Fingerprints determinísticos (executa 3x, verifica igualdade)
- [ ] Comportamento humano variável (10 execuções com padrões diferentes)
- [ ] Taxa de sucesso ≥ 90% em 20 execuções
- [ ] Logs claros (fácil debugar se cair taxa)
- [ ] Documentação atualizada
- [ ] Ninguém quebrou os processadores existentes

**Quando terminar:** Score 8.9/10, manuível, robusto. PRONTO PARA 1 PESSOA.

---

**Criado:** 2025-11-15  
**Versão:** 1.0 - PRAGMÁTICO  
**Impacto Esperado:** +1.4 pontos (7.5 → 8.9)  
**Esforço:** 14 horas / 3-4 dias  
**Manutenção:** Fácil (1 pessoa consegue)
