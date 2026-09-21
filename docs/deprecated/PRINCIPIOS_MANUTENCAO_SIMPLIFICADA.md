# PRINCÍPIOS DE MANUTENÇÃO SIMPLIFICADA

**Para:** Uma pessoa mantendo o projeto por ANOS  
**Filosofia:** Simplicidade radical, zero dívida técnica

---

## 1. PRINCÍPIOS FUNDAMENTAIS

### P1: Simplicidade > Sofisticação

**A Regra de Ouro:**
```
Se você não consegue explicar a solução em 1 frase:
  ❌ Não faça
  
Se a solução tem mais de 100 linhas de código:
  ❌ Provavelmente está errada

Se você não consegue debugar em 15 minutos:
  ❌ Desfaça e faça de novo
```

**Exemplo:**

ERRADO:
```python
# anti_detection_advanced_ml_based_behavior_simulator.py
class AdvancedBehaviorSimulator:
    """Simula comportamento humano com ML"""
    def __init__(self, model_path, config):
        # 500 linhas de código
        # 3 dependências
        # 10 hiperparâmetros
        pass
```

CORRETO:
```python
# human_behavior.py
def get_random_delay():
    """Delay aleatório entre 500-2000ms"""
    return random.randint(500, 2000) / 1000
```

---

### P2: Determinismo > Aleatoriedade

**A Regra:**
```
Se o MESMO processador tem fingerprint DIFERENTE cada execução:
  ❌ Parece bot novo toda vez
  
Se o MESMO processador tem fingerprint IGUAL toda execução:
  ✅ Parece humano no mesmo PC
```

**Exemplo:**

ERRADO:
```python
canvas_noise = random.randint(0, 255)  # Diferente cada vez!
# Execução 1: Canvas = ...abc123...
# Execução 2: Canvas = ...xyz789...
# Interpretação: "Bot novo a cada execução"
```

CORRETO:
```python
# Hash DETERMINÍSTICO baseado no processador
seed = int(hashlib.md5(b"relatorio_operacao_desagio").hexdigest(), 16) % 10000
canvas_noise = (seed + frame_number) % 256  # Sempre reproduzível
# Execução 1: Canvas = ...abc123...
# Execução 2: Canvas = ...abc123...
# Interpretação: "Mesmo humano, mesmo PC"
```

---

### P3: Consistência > Perfeição

**A Regra:**
```
Score 8.9/10 com 1 pessoa mantendo:
  ✅ EXCELENTE
  
Score 10/10 com ninguém conseguindo manter:
  ❌ INÚTIL
```

**Exemplo:**

ERRADO:
```
Implementar:
- TLS fingerprinting avançado
- IP rotation com proxy
- Canvas randomization sofisticado
- Webgl simulation perfeita
- Anti-cloudflare v2
- Machine learning behavior detection
→ Score 9.5/10
→ Ninguém consegue mexer
→ Quebra, ninguém sabe consertar
→ Projeto morre
```

CORRETO:
```
Implementar:
- WebRTC blocker (10 linhas)
- Fetch restorer (10 linhas)
- Fingerprint seed (5 linhas)
- Behavior variability (20 linhas)
→ Score 8.9/10
→ Uma pessoa em 2 horas entende tudo
→ Se quebra, conserta em 10 minutos
→ Projeto vive
```

---

### P4: Manuível > Complexo

**A Regra:**
```
Código deve ser LEGÍVEL, não IMPRESSIONANTE
```

**Exemplo:**

ERRADO:
```python
# Gênio da computação, ninguém consegue ler depois
WebRTCLeakPreventionProxy = type('WebRTCLeakPreventionProxy', (object,), {
    'RTCPeerConnection': lambda self, *args: (lambda: (
        exec('raise Exception("WebRTC disabled")') or None
    ))()
})()
window.RTCPeerConnection = WebRTCLeakPreventionProxy.RTCPeerConnection
```

CORRETO:
```python
# Código que qualquer dev lê e entende em 5 segundos
window.RTCPeerConnection = function() {
    throw new Error('WebRTC is disabled');
}
```

---

## 2. PADRÃO DE DESIGN: 5 PROTEÇÕES SIMPLES

```
CADA PROTEÇÃO = 1 FILE = 1 FUNÇÃO = 1 PROPÓSITO

┌─────────────────────────────────────────────────────────────┐
│ webrtc_blocker.py                                           │
│ def block_webrtc(page):                                     │
│     """Bloqueia WebRTC em 3 passos"""                       │
│     # 1. Flag Chromium                                      │
│     # 2. Init script                                        │
│     # 3. Validate                                           │
│     return is_blocked                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ fetch_restorer.py                                           │
│ def restore_fetch(page):                                    │
│     """Restaura fetch original"""                           │
│     # 1. Save original                                      │
│     # 2. Before critical operation                          │
│     # 3. Validate                                           │
│     return is_restored                                      │
└─────────────────────────────────────────────────────────────┘

... (3 mais)
```

**Vantagem:**
- Cada proteção é independente
- Fácil remover/atualizar uma sem quebrar outras
- Fácil testar isoladamente
- Uma pessoa consegue debugar

---

## 3. LOGGING ESTRUTURADO PARA DEBUGGING FÁCIL

**Quando algo quebra, os logs devem responder:**

```markdown
1. ❌ Qual proteção falhou?
2. ❌ Por que falhou?
3. ❌ Como consertar?
```

**Exemplo:**

```
[2025-11-15 14:30:45] ✅ WebRTC blocker: OK
  └─ Flag: --disable-features=WebRtcAllowMediaStreamToPeerConnection
  └─ Script: window.RTCPeerConnection = throw
  └─ Validation: ✅ No RTCPeerConnection in window

[2025-11-15 14:30:46] ✅ Fetch restorer: OK
  └─ Saved original: window.__originalFetch
  └─ Restored before: login()
  └─ Validation: ✅ fetch === __originalFetch

[2025-11-15 14:31:20] ⚠️ Turnstile resolver: RETRY 1/3
  └─ Erro: CAPTCHA não apareceu em 5s
  └─ Ação: Aguardando mais 3s
  └─ Próxima tentativa em 2s

[2025-11-15 14:31:25] ✅ Turnstile resolver: OK
  └─ Token: ...abc123...
  └─ Tempo: 7s
  └─ Reusable: false
```

**Se falhar:**
```
[2025-11-15 15:00:00] ❌ Login: FALHOU
  └─ Erro: HTTP 429 Too Many Requests
  └─ Timestamp: 2025-11-15T15:00:00
  └─ Tentativas: 3/3
  └─ Arquivo: relatorio_desagio.py:145
  └─ Stack trace: ...
  └─ AÇÃO: Aumentar delay entre requisições
           Verificar se SmartSecurities bloqueou IP
           Testar com delay 30s
```

---

## 4. QUANDO ATUALIZAR? (Decisão Matrix)

### Cenário 1: Taxa de sucesso cai de 95% para 85%

```
□ Taxa < 90%?
└─ SIM:
   □ Verificar logs para padrão
   □ SmartSecurities adicionou proteção NOVA?
   └─ SIM: Analyze + Add new fix
   └─ NÃO: Aumentar delays ou revisar comportamento
   
□ Taxa > 90%?
└─ NÃO MEXER (não estraga o que funciona!)
```

### Cenário 2: SmartSecurities adiciona NOVA proteção

```
□ Análise detecta proteção NOVA?
└─ SIM:
   □ Qual é? (fingerprinting? behavior? network?)
   □ Risco score sobe de 60 para 80?
   └─ SIM: Adicione 1 new fix (max 8h)
   └─ NÃO: Ignore (score 8.9 é ok mesmo com 90/200)
```

### Cenário 3: Browser (Chromium) recebe UPDATE

```
□ Novo browser com novo bug?
└─ SIM:
   □ WebRTC leak voltou? Aplicar flag de novo
   □ Fetch monitoramento mudou? Restaurar antes
   □ Outros issues? Check changelog
   
□ Score continua > 8.5?
└─ SIM: NÃO MEXER
└─ NÃO: Investigar (provavelmente browser issue, não PROSPER)
```

---

## 5. TROUBLESHOOTING RÁPIDO (Decision Tree)

```
PROBLEMA: "Automação foi bloqueada"
│
├─ Verificar log da execução
│  │
│  ├─ "❌ WebRTC blocker: FAILED"?
│  │  └─ Ação: 10 min
│  │     1. Verificar flag Chromium
│  │     2. Rerunner test
│  │     3. Se ainda falhar: atualizar script
│  │
│  ├─ "❌ Fetch restorer: FAILED"?
│  │  └─ Ação: 10 min
│  │     1. Verificar timing (antes de requisição?)
│  │     2. Check if site mudou (new endpoints?)
│  │     3. Adicionar mais pontos de restauração
│  │
│  ├─ "❌ Turnstile resolver: TIMEOUT"?
│  │  └─ Ação: 5 min
│  │     1. Verificar saldo CapSolver
│  │     2. Verificar site key correto
│  │     3. Se ok: pode ser rate limiting
│  │
│  ├─ "HTTP 429 Too Many Requests"?
│  │  └─ Ação: 5 min
│  │     1. Aumentar delay entre requisições (+5s)
│  │     2. Verificar se múltiplos processors rodando
│  │     3. Aguardar antes de próxima tentativa
│  │
│  └─ Nenhum erro de proteção, outro erro?
│     └─ Ação: Debugar isoladamente
│        (site mudou, credencial expirou, etc)
│
└─ Se não consegue resolver em 20 min:
   1. Executar em DEBUG_MODE
   2. Verificar screenshots
   3. Accessar VNC para inspecionar browser
   4. Considerar revert de mudanças recentes
```

---

## 6. TEMPLATE: ADICIONAR NOVA PROTEÇÃO

**SE** necessário adicionar nova proteção além das 5:

```python
# src/common/my_new_protection.py
# ================================
# Descrição 1-liner:
"""Bloqueia XXX proteção detectada por SmartSecurities"""

async def apply_protection(page):
    """
    Aplica proteção contra XXX
    
    Args:
        page: Playwright Page
        
    Returns:
        bool: True se ok, False se falhou
    """
    try:
        # PASSO 1: O que queremos bloquear?
        await page.add_init_script("""
            // JavaScript que bloqueia
        """)
        
        # PASSO 2: Validar que funcionou
        result = await page.evaluate("""
            // JavaScript que valida
        """)
        
        # PASSO 3: Log resultado
        logger.info(f"✅ My protection: OK")
        return True
        
    except Exception as e:
        logger.error(f"❌ My protection failed: {e}")
        return False


# Adicionar ao processor:
async def run_processor():
    # ... setup browser ...
    
    # Aplicar proteção ANTES de navegar
    success = await my_new_protection.apply_protection(page)
    if not success:
        logger.error("Não conseguiu aplicar proteção")
        return False
    
    # Navegar
    await page.goto(URL)
```

**Checklist:**
- [ ] Proteção = máximo 50 linhas
- [ ] Só faz 1 coisa
- [ ] Tem validação clara
- [ ] Tem logging estruturado
- [ ] Testes antes de commit
- [ ] Documentação clara

---

## 7. DADOS MENSURÁVEIS

**Metricas para verificar SAÚDE do projeto:**

```markdown
## Verificação Semanal (5 min)

□ Taxa de sucesso últimas 100 execuções: >= 90%?
  └─ SIM: ✅ Tudo ok
  └─ NÃO: ❌ Investigar

□ Logs contêm erros de proteção?
  └─ NÃO: ✅ Tudo ok
  └─ SIM: ❌ Qual proteção? Consertar

□ Algum processador travou?
  └─ NÃO: ✅ Tudo ok
  └─ SIM: ❌ Verificar logs, matar processo


## Verificação Mensal (30 min)

□ Score SmartSecurities: >= 8.5/10?
  └─ SIM: ✅ Tudo ok
  └─ NÃO: ❌ Adicionar novo fix?

□ Cobertura de proteção:
  ├─ ✅ WebRTC blocker
  ├─ ✅ Fetch restorer
  ├─ ✅ Timezone/Locale
  ├─ ✅ Fingerprints determinísticos
  ├─ ✅ Comportamento variável
  └─ Todas presentes?
  
□ Taxa de sucesso por processador?
  ├─ relatorio_operacao_desagio: 95%?
  ├─ relatorio_titulos_aberto: 93%?
  ├─ envio_boleto_operacao_oculto: 92%?
  └─ Todas >= 85%?

□ Tempo médio de execução mudou?
  ├─ Estava: 4 min
  ├─ Agora: 4:30 min
  └─ Aumentou muito? (pode ser rate limiting novo)

□ Código mudou desde último mês?
  └─ NÃO mudanças desnecessárias?
  └─ Só mudou se taxa caiu ou site atualizou?


## Verificação Semestral (2h)

□ Revisar código de todas as 5 proteções
  ├─ Ainda relevante?
  ├─ Ainda simples?
  ├─ Alguém consegue ler/entender?
  └─ Se não: refatorar

□ Análise SmartSecurities
  ├─ Comparar com última análise
  ├─ Adicionaram novas proteções?
  ├─ Mudaram estratégia?
  └─ Se sim: considerar novo roadmap

□ Logs de erro últimos 6 meses
  ├─ Padrões repetidos?
  ├─ Bugs específicos?
  ├─ Se sim: consertar

□ Update dependências
  ├─ Playwright nova versão?
  ├─ CapSolver API mudou?
  ├─ Se sim: testar compatibilidade
```

---

## 8. QUANDO PARAR DE MEXER

**REGRA DE OURO:**

```
Taxa de sucesso >= 90%?
Nenhum erro crítico nos logs?
Score SmartSecurities >= 8.5/10?

→ PARAR TUDO
→ NÃO MEXER MAIS NADA
→ DEIXAR FUNCIONANDO

O projeto está bom!
Não tentar melhorar de 8.9 para 9.1.
Isso só quebra as coisas.
```

---

## 9. CÓDIGO REVIEW CHECKLIST

Antes de commitar QUALQUER mudança:

```markdown
□ Código é simples (< 100 linhas)?
□ Entende o propósito em 1 frase?
□ Tem logging clara (não é "mágico")?
□ Testes passam?
□ Taxa de sucesso não caiu?
□ Nenhum processador quebrou?
□ Não adiciona nova dependência?
□ Documentação clara?
□ Um novo dev em 2h entende?

Se algum é NÃO:
  → NÃO COMMITE
  → Refatore/Revise
  → Pergunte: "isso é mesmo necessário?"
```

---

## 10. ROTINA DIÁRIA (se mantendo o projeto)

```
SEGUNDA A SEXTA:
┌────────────────────────────────────────┐
│ 08:00 - 08:05: CHECK LOGS              │
│ □ Taxa sucesso OK?                     │
│ □ Erros críticos?                      │
│ □ Anomalias?                           │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ 12:00 - 12:05: MID-DAY CHECK           │
│ □ Quantos processos rodando?           │
│ □ Alguém travou?                       │
│ □ Uso de CPU/Memória ok?               │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ 17:00 - 17:05: END-OF-DAY CHECK        │
│ □ Taxa final do dia >= 90%?            │
│ □ Alertas de erro?                     │
│ □ Mensagens de CapSolver?              │
│ □ Agendar para amanhã tudo ok?         │
└────────────────────────────────────────┘

SE ENCONTRAR PROBLEMA:
  → DEBUG por máximo 15 min
  → Se não resolve:
     1. Verificar logs históricos
     2. Rodar em DEBUG_MODE
     3. Checkar VNC
  → Se ainda não sabe:
     1. Revert última mudança
     2. Sistema volte a funcionar
     3. Investigar depois com calma (não em emergência)
```

---

## 11. ESCALABILIDADE FUTURA

**Se precisar adicionar novo processador:**

```
NÃO:
- Copiar/colar código de outro processador
- Duplicar lógica

SIM:
- Usar templates em docs/COMO_CRIAR_PROCESSADORES.md
- Usar módulos comuns de src/common/
- Herdar proteções automáticamente
- Apenas customizar lógica específica do site
```

---

## 12. FINAL WISDOM

```
┌─────────────────────────────────────────────────────┐
│ MANUTENÇÃO DE 1 PESSOA POR ANOS                    │
│                                                     │
│ NÃO É SOBRE:                                       │
│ ❌ Código sofisticado                              │
│ ❌ Score 10/10                                     │
│ ❌ Features desnecessárias                         │
│ ❌ Trends de tecnologia                            │
│                                                     │
│ É SOBRE:                                           │
│ ✅ Código simples                                  │
│ ✅ Score 8.9/10 (suficiente)                       │
│ ✅ Logging excelente (debug fácil)                 │
│ ✅ Manutenibilidade acima de tudo                  │
│                                                     │
│ REGRA DE OURO:                                      │
│ "If it ain't broke, don't fix it"                  │
│                                                     │
│ SEGUNDA REGRA:                                      │
│ "When it's broken, debug systematically"           │
│                                                     │
│ TERCEIRA REGRA:                                     │
│ "Keep it simple, stupid"                           │
└─────────────────────────────────────────────────────┘
```

---

**Criado:** 2025-11-15  
**Versão:** 1.0  
**Propósito:** Manutenção simplificada e sustentável
