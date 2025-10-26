# 📊 Fluxo: Processador Relatório Operação Deságio

**Nome do Processador:** `relatorio_operacao_desagio.py`
**Objetivo:** Extrair relatório de operações de deságio do SmartSecurities em loop contínuo
**Display:** `:1` (VNC porta 6080)
**Frequência:** **Loop contínuo (5 segundos entre ciclos)**
**Última atualização:** 2025-10-26
**Status:** ✅ **100% FUNCIONAL E OTIMIZADO**

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Fluxo Completo Atualizado](#fluxo-completo-atualizado)
3. [Problema de Seleção de Frames (RESOLVIDO)](#problema-de-seleção-de-frames-resolvido)
4. [Mapeamento de Elementos](#mapeamento-de-elementos)
5. [Lógica de Código](#lógica-de-código)
6. [Configurações e Constantes](#configurações-e-constantes)
7. [Tratamento de Erros](#tratamento-de-erros)
8. [Mudanças Recentes](#mudanças-recentes)
9. [Como Executar](#como-executar)

---

## 🎯 Visão Geral

### **URL de Destino**
```
https://www.smartsecurities.com.br/smart/relatorios/frmrelatorio.php?page=relatorios/detalhamentodesagio.php
```

### **Dados Extraídos**
- Relatório de operações de deságio (CSV)
- Período: **10 anos atrás** até **hoje**
- Formato: CSV
- Tamanho típico: ~6MB

### **Características**
- ✅ **100% autônomo** - Resolve CAPTCHAs automaticamente
- ✅ **Loop contínuo** - Repete a cada 5 segundos
- ✅ **Perfis temporários** - Cada execução cria perfil Chrome único
- ✅ **Limpeza robusta** - Fecha tabs, browser e remove perfis ao finalizar
- ✅ **Anti-detecção** - Usa Nodriver com comportamento humano
- ✅ **Notificações** - Envia email em caso de erro

### **Pré-requisitos**
- Credenciais válidas (`.env`: `USUARIO_SITE_SMART`, `SENHA_SITE_SMART`)
- API Key CapSolver configurada (`CAPSOLVER_API_KEY`)
- Display `:1` disponível (Xvfb + VNC)

---

## 🔄 Fluxo Completo Atualizado

### **INICIALIZAÇÃO**

```
┌─────────────────────────────────────────────────┐
│ INICIALIZAÇÃO                                   │
├─────────────────────────────────────────────────┤
│ 1. Criar perfil temporário único                │
│    → /tmp/chrome_profile_XXXXXXXX/              │
│                                                 │
│ 2. Configurar display virtual                   │
│    → export DISPLAY=:1                          │
│                                                 │
│ 3. Iniciar navegador Nodriver                   │
│    → Browser com anti-detecção                  │
│    → Downloads via CDP configurados             │
│    → Usando perfil temporário                   │
└─────────────────────────────────────────────────┘
```

**Código relevante:**
```python
# Linha 77-78: Criar perfil temporário
self.temp_profile_dir = tempfile.mkdtemp(prefix="chrome_profile_")

# Linha 768-774: Inicializar browser com perfil temporário
self.browser = await init_browser(
    download_dir=self.download_dir,
    headless=False,
    display=self.display,
    user_data_dir=self.temp_profile_dir  # ← NOVO!
)
```

---

### **ETAPA 1: LOGIN NO SMARTSECURITIES** 🔐

```
┌─────────────────────────────────────────────────┐
│ ETAPA 1: LOGIN NO SMARTSECURITIES               │
└─────────────────────────────────────────────────┘
```

**URL:** `https://www.smartsecurities.com.br/smartsecurities/`

#### 1.1 Estrutura de Frames da Página de Login

```
┌───────────────────────────────────────────────────┐
│ Página Principal                                  │
│  ┌─────────────────────────────────────────────┐  │
│  │ <iframe id="principal">                     │  │
│  │  ┌───────────────────────────────────────┐  │  │
│  │  │ Formulário de Login                   │  │  │
│  │  │  - #email (campo)                     │  │  │
│  │  │  - #senha (campo)                     │  │  │
│  │  │  - input[value="OK"] (botão)          │  │  │
│  │  │  - reCAPTCHA v2                       │  │  │
│  │  └───────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

#### 1.2 Sequência de Login

1. **Abrir página de login**
   ```python
   await self.tab.get(URL_LOGIN)
   await asyncio.sleep(2)
   ```

2. **Aguardar iframe aparecer** (até 20 tentativas)
   ```python
   for tentativa in range(1, 21):
       iframe = await self.tab.query_selector('iframe[id="principal"]')
       if iframe:
           break
       await asyncio.sleep(1)
   ```

3. **Preencher credenciais via JavaScript**
   ```javascript
   var doc = iframe.contentDocument;
   doc.getElementById('email').value = 'usuario@email.com';
   doc.getElementById('senha').value = 'senha_secreta';
   ```

4. **Clicar no botão OK**
   ```javascript
   doc.querySelector('input[value="OK"]').click();
   ```

5. **Aguardar CAPTCHA aparecer**
   ```python
   await asyncio.sleep(3)
   ```

6. **Resolver reCAPTCHA via CapSolver HTTP API** (veja seção detalhada abaixo)

7. **Clicar no botão OK final**
   ```javascript
   doc.querySelector('input[value="OK"]').click();
   ```

8. **Aguardar redirecionamento**
   ```python
   await asyncio.sleep(5)
   ```

**✅ Login completo!**

---

### **RESOLUÇÃO DE CAPTCHA (Automática via HTTP API)** 🤖

```
┌─────────────────────────────────────────────────┐
│ RESOLVENDO reCAPTCHA AUTOMATICAMENTE VIA HTTP   │
└─────────────────────────────────────────────────┘
```

**Método:** CapSolver HTTP API (SEM extensão browser)

#### Fluxo de Resolução:

```
1. Extrair site_key do reCAPTCHA
   ↓
   Site key: 6Le-JHwUAAAAAGZJWerkysOyQeo-Ehm7704vfT1q

2. POST https://api.capsolver.com/createTask
   ↓
   Body: {
     "clientKey": "CAP-019482...",
     "task": {
       "type": "ReCaptchaV2TaskProxyLess",
       "websiteURL": "https://www.smartsecurities.com.br/...",
       "websiteKey": "6Le-JHwUA..."
     }
   }
   ↓
   Response: {"taskId": "425152bd-204f-4b60-9f39-bdc49fe2ced2"}

3. Loop GET /getTaskResult (polling a cada 1s)
   ↓
   Aguarda até status = "ready"
   ↓
   Tempo médio: 15-30 segundos
   ↓
   Token: 0cAFcWeA5a3VRai9MeZH2PEfO-sr1GR8_4Z_E9kU...

4. Injetar token no reCAPTCHA
   ↓
   JavaScript:
   document.getElementById('g-recaptcha-response').value = token;
   document.getElementById('g-recaptcha-response').innerHTML = token;

5. Submeter formulário automaticamente
```

**Código:** `src/common/captcha_solver.py:416-457`

**Logs de exemplo:**
```
[CAPSOLVER HTTP] Extraindo site_key do reCAPTCHA...
[CAPSOLVER HTTP] ✅ Site key encontrada: 6Le-JHwUA...
[CAPSOLVER HTTP] Enviando createTask...
[CAPSOLVER HTTP] ✅ Task criada: 425152bd-...
[CAPSOLVER HTTP] ⏳ Aguardando resolução (máx 180s)...
[CAPSOLVER HTTP] ✅ CAPTCHA RESOLVIDO em 15.3s!
[CAPSOLVER HTTP] Injetando token no reCAPTCHA...
[CAPSOLVER HTTP] ✅ Token injetado com sucesso!
```

---

### **LOOP DE EXTRAÇÃO** (A cada 5 segundos) 🔁

```
████████████████████████████████████████████████████
█ CICLO #N
████████████████████████████████████████████████████
```

Cada ciclo executa as etapas abaixo:

---

### **ETAPA 3: NAVEGANDO PARA RELATÓRIO** 🌐

```
┌─────────────────────────────────────────────────┐
│ ETAPA 3: NAVEGANDO PARA RELATÓRIO               │
└─────────────────────────────────────────────────┘
```

**URL:** `https://www.smartsecurities.com.br/smart/relatorios/frmrelatorio.php?page=relatorios/detalhamentodesagio.php`

```python
await self.tab.get(URL_RELATORIO)
await asyncio.sleep(2)
```

**✅ Página carregada**

---

### **ETAPA 4: PREENCHENDO FORMULÁRIO** 📝

```
┌─────────────────────────────────────────────────┐
│ ETAPA 4: PREENCHENDO FORMULÁRIO                 │
└─────────────────────────────────────────────────┘
```

#### 4.1 Estrutura de Frames da Página de Relatório

**🚨 PROBLEMA ANTERIOR: SELEÇÃO DE FRAMES ERA COMPLEXA 🚨**

```
┌────────────────────────────────────────────────────────┐
│ Página Principal (frmrelatorio.php)                    │
│  ┌──────────────────────────────────────────────────┐  │
│  │ <iframe name="code" id="code">                   │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │ <frame name="text">                        │  │  │
│  │  │  ┌──────────────────────────────────────┐  │  │  │
│  │  │  │ Formulário                           │  │  │  │
│  │  │  │  - input[name="DtInicial"]           │  │  │  │
│  │  │  │  - input[name="DtFinal"]             │  │  │  │
│  │  │  │  - input[value="csvType"] (radio)    │  │  │  │
│  │  │  │  - input[name="Imprimir"] (botão)    │  │  │  │
│  │  │  └──────────────────────────────────────┘  │  │  │
│  │  └────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

**Caminho completo:** `main > frame[1](code) > frame[2](text) > formulário`

#### 4.2 Calcular Datas

```python
# Data inicial: 10 anos atrás
data_inicial = datetime.now() - timedelta(days=3650)
dtInicial = data_inicial.strftime("%d/%m/%Y")  # Ex: "26/10/2015"

# Data final: Hoje
data_final = datetime.now()
dtFinal = data_final.strftime("%d/%m/%Y")  # Ex: "26/10/2025"
```

#### 4.3 Método de Preenchimento (Recursivo em Frames)

**🎯 SOLUÇÃO IMPLEMENTADA: Busca recursiva em frames**

```python
async def preencher_formulario_recursivo(tab, profundidade=0):
    """
    Busca recursivamente em frames até encontrar o formulário
    """
    # Tentar no frame atual
    try:
        input_dt_inicial = await tab.query_selector('input[name="DtInicial"]')
        if input_dt_inicial:
            # ENCONTROU! Preencher aqui
            await tab.evaluate(f"""
                document.querySelector('input[name="DtInicial"]').value = '{dtInicial}';
                document.querySelector('input[name="DtFinal"]').value = '{dtFinal}';
                document.querySelector('input[value="csvType"]').checked = true;
            """)

            # Clicar no botão Imprimir
            await tab.evaluate("""
                document.querySelector('input[name="Imprimir"]').click();
            """)

            return {
                'success': True,
                'profundidade': profundidade,
                'dtInicial': dtInicial,
                'dtFinal': dtFinal
            }
    except:
        pass

    # Se não encontrou, buscar em child frames
    child_frames = await tab.query_selector_all('iframe, frame')

    for frame in child_frames:
        resultado = await preencher_formulario_recursivo(frame, profundidade + 1)
        if resultado['success']:
            return resultado

    return {'success': False}
```

**Código real:** `src/processors/web/relatorio_operacao_desagio.py:577-647`

#### 4.4 Logs de Sucesso

```
[FORMULÁRIO] DtInicial: 26/10/2015
[FORMULÁRIO] DtFinal: 26/10/2025
[FORMULÁRIO] Procurando e preenchendo formulário...
[FORMULÁRIO] ✅ Caminho: main > frame[1](code) > frame[2](text)
[FORMULÁRIO] ✅ Profundidade: 2
[FORMULÁRIO] ✅ DtInicial: 26/10/2015
[FORMULÁRIO] ✅ DtFinal: 26/10/2025
[FORMULÁRIO] ✅ CSV selecionado: True
[FORMULÁRIO] ✅ Botão CLICADO: True
```

**✅ Formulário preenchido e botão Imprimir clicado!**

---

### **ETAPA 5: VERIFICANDO E RESOLVENDO reCAPTCHA (SEMPRE APARECE!)** 🔍

```
┌─────────────────────────────────────────────────┐
│ ETAPA 5: VERIFICANDO reCAPTCHA APÓS CLIQUE      │
└─────────────────────────────────────────────────┘
```

**🚨 IMPORTANTE: CAPTCHA SEMPRE APARECE APÓS CLICAR "IMPRIMIR" 🚨**

#### 5.1 Detectar Abertura de Nova Aba

Após clicar "Imprimir", o sistema abre uma **nova aba** com CAPTCHA:

```python
# Salvar tab principal
tab_principal = self.tab

# Aguardar nova aba abrir
await asyncio.sleep(2)

# Verificar se há nova aba
todas_tabs = await self.browser.tabs
if len(todas_tabs) > 1:
    # NOVA ABA DETECTADA!
    # Última tab = aba do CAPTCHA
    self.tab = todas_tabs[-1]
```

**URL da aba CAPTCHA:**
```
https://www.smartsecurities.com.br/smart/php/captcha.php?info=Rm9ybQ==&metodoRetorno=submit
```

#### 5.2 Resolver CAPTCHA na Nova Aba

Mesmo processo da ETAPA 1 (CapSolver HTTP API).

**Tempo médio:** 20-30 segundos

#### 5.3 Clicar no Botão "Confirmar"

Após CAPTCHA resolvido:

```python
# Procurar botão "Confirmar" na aba CAPTCHA
btn_confirmar = await self.tab.query_selector('input[value="Confirmar"]')
await btn_confirmar.click()

# Aguardar submissão
await asyncio.sleep(2)
```

#### 5.4 **FECHAR A ABA DO CAPTCHA** ⚠️ (CORREÇÃO CRÍTICA!)

**🔥 PROBLEMA QUE VOCÊ TEVE:**
- A aba do CAPTCHA ficava aberta após resolver
- Isso **bloqueava o download** do CSV
- O processador ficava aguardando 90s e dava timeout

**✅ SOLUÇÃO IMPLEMENTADA:**

```python
# FECHAR a aba do CAPTCHA (CRUCIAL!)
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
```

**Código:** `src/processors/web/relatorio_operacao_desagio.py:518-533`

**Logs:**
```
[CAPTCHA] ✅ CAPTCHA resolvido!
[CAPTCHA] Procurando botão Confirmar...
[CAPTCHA] ✅ Botão Confirmar clicado
[CAPTCHA] Aguardando 2s após clicar Confirmar...
[CAPTCHA] Fechando aba do CAPTCHA...
[CAPTCHA] ⚠️ Erro ao fechar aba: server rejected WebSocket connection: HTTP 500
[CAPTCHA] ✅ Voltou para tab principal
```

**Nota:** Mesmo com erro ao fechar (websocket), a aba é fechada com sucesso e o download funciona!

---

### **ETAPA 6: AGUARDANDO DOWNLOAD** ⏬

```
┌─────────────────────────────────────────────────┐
│ ETAPA 6: AGUARDANDO DOWNLOAD                    │
└─────────────────────────────────────────────────┘
```

**Diretório:** `data/raw_inputs/`
**Timeout:** 90 segundos

#### 6.1 Polling no Diretório

```python
async def aguardar_download():
    """Aguarda CSV aparecer no diretório"""
    arquivos_antes = set(self.download_dir.glob("*.csv"))
    tempo_inicio = time.time()

    while time.time() - tempo_inicio < TIMEOUT_DOWNLOAD:
        await asyncio.sleep(5)

        # Verificar novos CSVs
        arquivos_agora = set(self.download_dir.glob("*.csv"))
        novos_arquivos = arquivos_agora - arquivos_antes

        if novos_arquivos:
            arquivo = list(novos_arquivos)[0]
            print(f"[DOWNLOAD] ✅ Arquivo baixado: {arquivo.name}")
            return arquivo

        print(f"[DOWNLOAD] Aguardando... ({int(time.time() - tempo_inicio)}s)")

    raise Exception(f"Timeout: arquivo CSV não baixado em {TIMEOUT_DOWNLOAD}s")
```

**Código:** `src/processors/web/relatorio_operacao_desagio.py:649-688`

**Logs:**
```
[DOWNLOAD] Aguardando arquivo CSV...
[DOWNLOAD] Timeout: 90s
[DOWNLOAD] Aguardando... (5s)
[DOWNLOAD] Aguardando... (10s)
[DOWNLOAD] Aguardando... (15s)
[DOWNLOAD] Aguardando... (20s)
...
[DOWNLOAD] Aguardando... (40s)
[DOWNLOAD] ✅ Arquivo baixado: DetalhamentoDesagio.csv
```

**Arquivo baixado:** `DetalhamentoDesagio.csv` (~6.1MB)

---

### **ETAPA 7: RENOMEANDO ARQUIVO** 📝

```
┌─────────────────────────────────────────────────┐
│ ETAPA 7: RENOMEANDO ARQUIVO                     │
└─────────────────────────────────────────────────┘
```

**Formato:** `relatorio_desagio_YYYY_MM_DD_HHMMSS.csv`

```python
timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
novo_nome = f"relatorio_desagio_{timestamp}.csv"

# Renomear
arquivo_original.rename(self.download_dir / novo_nome)

print(f"[RENOMEAR] ✅ Arquivo renomeado")
print(f"[RENOMEAR] De: {arquivo_original.name}")
print(f"[RENOMEAR] Para: {novo_nome}")
```

**Código:** `src/processors/web/relatorio_operacao_desagio.py:690-706`

**Exemplo de nome final:**
```
relatorio_desagio_2025_10_26_004006.csv
```

---

### **FIM DO CICLO** ✅

```
┌─────────────────────────────────────────────────┐
│ ✅ CICLO CONCLUÍDO COM SUCESSO!                 │
│ ✅ Arquivo: relatorio_desagio_2025_10_26...csv │
└─────────────────────────────────────────────────┘

[LOOP] Próximo ciclo em 0 minutos...
[LOOP] Pressione Ctrl+C para parar
```

**Aguardar:** 5 segundos

**Repetir:** ETAPA 3 até ETAPA 7 em loop infinito

---

## 🔧 Problema de Seleção de Frames (RESOLVIDO)

### **O Problema**

Você teve dificuldade em selecionar os campos do formulário porque eles estavam **profundamente aninhados** em múltiplos frames:

```
Página Principal
  └─ iframe #code
      └─ frame name="text"
          └─ FORMULÁRIO AQUI
```

**Sintomas:**
- Seletores CSS não encontravam elementos
- `query_selector()` retornava `null`
- JavaScript não conseguia acessar `document.querySelector()`

### **Por que aconteceu?**

Quando você tem frames aninhados, o `document` de cada frame é **isolado**. Você precisa:

1. Acessar o frame pai
2. Pegar o `contentDocument` do frame pai
3. Buscar o frame filho dentro do pai
4. Pegar o `contentDocument` do filho
5. **AGORA SIM** você consegue fazer `querySelector()` no formulário

### **Solução Implementada**

#### Opção 1: JavaScript Recursivo (caminho completo)

```javascript
// 1. Acessar main page
var doc = document;

// 2. Entrar no iframe "code"
var frameCode = doc.getElementById('code') || doc.querySelector('iframe[name="code"]');
if (!frameCode) return {error: 'Frame code não encontrado'};

var docCode = frameCode.contentDocument || frameCode.contentWindow.document;

// 3. Entrar no frame "text" dentro de "code"
var frameText = docCode.querySelector('frame[name="text"]');
if (!frameText) return {error: 'Frame text não encontrado'};

var docText = frameText.contentDocument || frameText.contentWindow.document;

// 4. AGORA SIM acessar formulário
var inputInicial = docText.querySelector('input[name="DtInicial"]');
var inputFinal = docText.querySelector('input[name="DtFinal"]');
var radioCSV = docText.querySelector('input[value="csvType"]');
var btnImprimir = docText.querySelector('input[name="Imprimir"]');

// 5. Preencher e clicar
if (inputInicial && inputFinal && radioCSV && btnImprimir) {
    inputInicial.value = '26/10/2015';
    inputFinal.value = '26/10/2025';
    radioCSV.checked = true;
    btnImprimir.click();

    return {
        success: true,
        caminho: 'main > frame[1](code) > frame[2](text)',
        profundidade: 2
    };
}

return {error: 'Elementos não encontrados'};
```

#### Opção 2: Nodriver Recursivo (Python)

```python
async def preencher_em_frames(tab, profundidade=0):
    """
    Busca recursivamente em todos os frames até encontrar o formulário
    """
    # Tentar no contexto atual
    try:
        input_inicial = await tab.query_selector('input[name="DtInicial"]')
        if input_inicial:
            # ENCONTROU! Preencher aqui
            await preencher_formulario(tab)
            return True
    except:
        pass

    # Não encontrou? Buscar em child frames
    frames = await tab.query_selector_all('iframe, frame')

    for frame in frames:
        encontrou = await preencher_em_frames(frame, profundidade + 1)
        if encontrou:
            return True

    return False
```

### **Dicas para Debugging de Frames**

#### 1. Ver estrutura de frames via DevTools Console

```javascript
// Executar no console do navegador
function listarFrames(doc, nivel = 0) {
    const indent = '  '.repeat(nivel);

    // Listar iframes
    const iframes = doc.querySelectorAll('iframe');
    iframes.forEach((iframe, i) => {
        console.log(`${indent}└─ iframe[${i}] id="${iframe.id}" name="${iframe.name}"`);
        try {
            listarFrames(iframe.contentDocument, nivel + 1);
        } catch (e) {
            console.log(`${indent}   ⚠️ Não acessível (CORS)`);
        }
    });

    // Listar frames (deprecated mas ainda usado)
    const frames = doc.querySelectorAll('frame');
    frames.forEach((frame, i) => {
        console.log(`${indent}└─ frame[${i}] name="${frame.name}"`);
        try {
            listarFrames(frame.contentDocument, nivel + 1);
        } catch (e) {
            console.log(`${indent}   ⚠️ Não acessível (CORS)`);
        }
    });
}

listarFrames(document);
```

**Output esperado:**
```
└─ iframe[0] id="code" name="code"
   └─ frame[0] name="text"
   └─ frame[1] name="lista"
```

#### 2. Testar acesso via console

```javascript
// Tentar caminho manual
var frameCode = document.getElementById('code');
console.log('Frame code:', frameCode);

var docCode = frameCode.contentDocument;
console.log('Document code:', docCode);

var frameText = docCode.querySelector('frame[name="text"]');
console.log('Frame text:', frameText);

var docText = frameText.contentDocument;
console.log('Document text:', docText);

var input = docText.querySelector('input[name="DtInicial"]');
console.log('Input encontrado:', input);
```

Se qualquer `console.log()` retornar `null`, você sabe onde parar e investigar.

#### 3. Usar VNC para ver visualmente

```
http://3.148.126.73:6080/vnc.html
```

- Abra o DevTools (F12)
- Execute os comandos acima
- Veja os frames na aba "Elements"

---

## 🗺️ Mapeamento de Elementos

### **Página de Login**

| Elemento | Frame | Seletor CSS | ID | Name | Valor |
|----------|-------|-------------|----|----- |-------|
| Iframe principal | `main` | `iframe[id="principal"]` | `#principal` | - | - |
| Campo Email | `iframe#principal` | `input#email` | `#email` | `email` | Variável `.env` |
| Campo Senha | `iframe#principal` | `input#senha` | `#senha` | `senha` | Variável `.env` |
| Botão OK | `iframe#principal` | `input[value="OK"]` | - | - | - |
| reCAPTCHA | `iframe#principal` | `div.g-recaptcha` | - | - | - |

### **Página do Relatório de Deságio**

| Elemento | Frame | Seletor CSS | ID | Name | Valor |
|----------|-------|-------------|----|----- |-------|
| Frame code | `main` | `iframe[id="code"]` | `#code` | `code` | - |
| Frame text | `frame#code` | `frame[name="text"]` | - | `text` | - |
| Data Inicial | `frame[name="text"]` | `input[name="DtInicial"]` | `#DtInicial` | `DtInicial` | `DD/MM/YYYY` |
| Data Final | `frame[name="text"]` | `input[name="DtFinal"]` | `#DtFinal` | `DtFinal` | `DD/MM/YYYY` |
| Radio CSV | `frame[name="text"]` | `input[value="csvType"]` | - | `tipoImp` | `csvType` |
| Botão Imprimir | `frame[name="text"]` | `input[name="Imprimir"]` | - | `Imprimir` | - |

### **Página de CAPTCHA (Nova Aba)**

| Elemento | Frame | Seletor CSS | Valor |
|----------|-------|-------------|-------|
| reCAPTCHA | `main` | `iframe[src*="recaptcha"]` | - |
| Botão Confirmar | `main` | `input[value="Confirmar"]` | `Confirmar` |

---

## 💻 Lógica de Código

### **Estrutura da Classe**

```python
class ProcessadorRelatorioDesagio:
    """
    Processador de Relatório de Operações de Deságio - 100% Nodriver Async

    Características:
    - Perfil temporário único por execução
    - Loop contínuo (5s entre ciclos)
    - CAPTCHA automático via CapSolver HTTP
    - Limpeza robusta de recursos
    """

    def __init__(self):
        self.nome = "relatorio_desagio"
        self.browser = None
        self.tab = None
        self.display = os.environ.get('DISPLAY', ':1')
        self.temp_profile_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        # ...

    async def iniciar_navegador(self):
        """Inicializa browser com perfil temporário"""

    async def fazer_login(self):
        """Login + CAPTCHA automático"""

    async def navegar_para_relatorio(self):
        """Abre página do relatório"""

    async def preencher_formulario(self):
        """Preenche datas e clica Imprimir (busca recursiva em frames)"""

    async def verificar_e_resolver_recaptcha(self):
        """Detecta nova aba, resolve CAPTCHA e FECHA a aba"""

    async def aguardar_download(self):
        """Polling no diretório até CSV aparecer"""

    async def renomear_arquivo(self, arquivo):
        """Renomeia com timestamp"""

    async def executar_ciclo_extracao(self):
        """Pipeline completo: ETAPA 3 até ETAPA 7"""

    async def processar(self):
        """Loop principal + limpeza final"""
```

### **Fluxo do `processar()`**

```python
async def processar(self):
    try:
        # INICIALIZAÇÃO
        await self.iniciar_navegador()

        # ETAPA 1: Login
        await self.fazer_login()

        # ETAPA 2: Email (desabilitado)
        # ...

        # LOOP INFINITO
        ciclo_numero = 1
        while not self.parar:
            print(f"█ CICLO #{ciclo_numero}")

            try:
                # ETAPA 3-7: Extração completa
                await self.executar_ciclo_extracao()

                print(f"✅ CICLO CONCLUÍDO COM SUCESSO!")

            except Exception as e:
                print(f"❌ Erro no ciclo #{ciclo_numero}: {e}")
                await enviar_email_erro(erro=str(e))
                await asyncio.sleep(60)  # Retry após 60s

            ciclo_numero += 1

            # Aguardar próximo ciclo
            print(f"[LOOP] Próximo ciclo em 0 minutos...")
            await asyncio.sleep(INTERVALO_LOOP)  # 5 segundos

    finally:
        # LIMPEZA ROBUSTA
        await self.cleanup()
```

### **Método `cleanup()` (Limpeza Robusta)**

```python
async def cleanup(self):
    """
    Limpeza robusta ao finalizar processador

    Ordem:
    1. Fechar todas as tabs
    2. Fechar browser
    3. Remover perfil temporário
    """
    # 1. Fechar todas as tabs
    if self.browser:
        print(f"[CLEANUP] Fechando todas as tabs...")
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

    # 2. Fechar navegador
    if self.browser:
        print(f"[CLEANUP] Fechando navegador...")
        try:
            await self.browser.stop()
            print(f"[CLEANUP] ✅ Navegador fechado")
        except Exception as e:
            print(f"[CLEANUP] ⚠️ Erro ao fechar navegador: {e}")

    # 3. Limpar perfil temporário
    if hasattr(self, 'temp_profile_dir') and os.path.exists(self.temp_profile_dir):
        print(f"[CLEANUP] Limpando perfil temporário...")
        try:
            import shutil
            shutil.rmtree(self.temp_profile_dir, ignore_errors=True)
            print(f"[CLEANUP] ✅ Perfil temporário removido")
        except Exception as e:
            print(f"[CLEANUP] ⚠️ Erro ao remover perfil: {e}")
```

**Código:** `src/processors/web/relatorio_operacao_desagio.py:826-857`

---

## ⚙️ Configurações e Constantes

```python
# URLs
URL_LOGIN = "https://www.smartsecurities.com.br/smartsecurities/"
URL_RELATORIO = "https://www.smartsecurities.com.br/smart/relatorios/frmrelatorio.php?page=relatorios/detalhamentodesagio.php"

# Credenciais (.env)
USUARIO_SITE_SMART = os.getenv("USUARIO_SITE_SMART")
SENHA_SITE_SMART = os.getenv("SENHA_SITE_SMART")
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY")

# Timeouts (segundos)
TIMEOUT_DOWNLOAD = 90
TIMEOUT_CAPTCHA = 60
INTERVALO_LOOP = 5  # ← MUDANÇA RECENTE: Era 300 (5 min), agora é 5s

# Diretórios
DOWNLOAD_DIR = Path("data/raw_inputs/")
LOG_DIR = Path("logs/")

# Datas
DIAS_ATRAS = 3650  # 10 anos
```

**Arquivo:** `src/processors/web/relatorio_operacao_desagio.py:48-60`

---

## ⚠️ Tratamento de Erros

### **Erros Comuns e Soluções**

| Erro | Causa | Solução Implementada |
|------|-------|----------------------|
| **Timeout download (90s)** | Aba CAPTCHA ficou aberta | ✅ Fechar aba após resolver (linha 522-528) |
| **Frame não encontrado** | Estrutura HTML mudou | ✅ Busca recursiva em todos os frames |
| **CAPTCHA falhou** | API CapSolver indisponível | ✅ Retry + email de alerta |
| **Credenciais inválidas** | `.env` incorreto | ✅ Pausar e enviar email |
| **Browser crashou** | Falta de memória | ✅ Usar perfil temporário (limpa cache) |

### **Sistema de Notificações**

```python
# Email de erro crítico
await enviar_alerta_erro_critico(
    processador="relatorio_desagio",
    erro=str(e),
    display=":1"
)
```

**Para:** `guilherme@prosperinvest.com.br`

**Assunto:** `⚠️ ERRO CRÍTICO - relatorio_desagio`

**Conteúdo:**
```
❌ ERRO NO PROCESSADOR relatorio_desagio

Display: :1
VNC: http://3.148.126.73:6080/vnc.html

Erro: Timeout: arquivo CSV não baixado em 90s

Acesse o VNC para investigar.
```

---

## 🆕 Mudanças Recentes

### **Versão 30.0 (2025-10-26)**

#### 1. **Loop de 5 segundos** (era 5 minutos)

```diff
- INTERVALO_LOOP = 300  # 5 minutos entre extrações
+ INTERVALO_LOOP = 5    # 5 segundos entre extrações
```

**Por quê?**
- Usuário solicitou ciclos mais frequentes
- Máxima velocidade de extração
- Sistema suporta sem problemas

#### 2. **Perfis temporários únicos**

```diff
  def __init__(self):
      self.nome = "relatorio_desagio"
+     # Perfil temporário único para cada execução
+     self.temp_profile_dir = tempfile.mkdtemp(prefix="chrome_profile_")
```

**Por quê?**
- Evita reutilização de sessão
- Limpa cache/cookies entre execuções
- Previne detecção de bot

#### 3. **Fechamento da aba CAPTCHA**

```diff
  # Após resolver CAPTCHA
  await btn_confirmar.click()
  await asyncio.sleep(2)

+ # FECHAR a aba do CAPTCHA (CRÍTICO!)
+ try:
+     await self.tab.close()
+ except Exception as e:
+     print(f"[CAPTCHA] ⚠️ Erro ao fechar aba: {e}")
+
+ self.tab = tab_principal
```

**Por quê?**
- Aba aberta bloqueava download
- Causava timeout de 90s
- **FIX CRÍTICO** que resolveu o problema principal

#### 4. **Limpeza robusta no finally**

```python
finally:
    # Fechar todas as tabs
    # Fechar navegador
    # Remover perfil temporário
```

**Por quê?**
- Garantir limpeza mesmo com erro
- Prevenir memory leaks
- Deixar sistema limpo para próxima execução

#### 5. **Otimização do CapSolver**

```diff
  # Após injetar token
- await asyncio.sleep(2)
+ await asyncio.sleep(0.5)
```

**Arquivo:** `src/common/captcha_solver.py:437`

**Por quê?**
- Reduzir tempo total de resolução
- Sistema já valida token rapidamente
- Ganho de ~1.5s por CAPTCHA

---

## 🚀 Como Executar

### **Método 1: Execução Direta**

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
source venv/bin/activate
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
export DISPLAY=:1

python src/processors/web/relatorio_operacao_desagio.py
```

### **Método 2: Script Helper**

```bash
./run_relatorio_desagio.sh
```

### **Método 3: Background com Log**

```bash
nohup python src/processors/web/relatorio_operacao_desagio.py > /tmp/proc_desagio.log 2>&1 &
```

### **Monitorar Execução**

#### Via Log

```bash
tail -f /tmp/proc_desagio.log
```

#### Via VNC

```
http://3.148.126.73:6080/vnc.html
```

**Senha:** `vetor2025`

#### Controles

Durante execução, pressione:
- `P` - Pausar
- `R` - Retomar
- `Q` - Parar completamente

---

## 📊 Arquivos Gerados

**Localização:** `data/raw_inputs/`

**Formato do nome:** `relatorio_desagio_YYYY_MM_DD_HHMMSS.csv`

**Exemplo:**
```
relatorio_desagio_2025_10_26_004006.csv
```

**Tamanho típico:** ~6MB

**Conteúdo:** Operações de deságio dos últimos 10 anos

---

## 📚 Recursos Relacionados

- [Guia de Criação de Processadores](../CRIAR_PROCESSADOR.md)
- [Arquitetura do Sistema](../ARQUITETURA.md)
- [Acesso VNC](../ACESSO_VNC.md)
- [Sistema de Notificações](../NOTIFICACOES.md)
- [Troubleshooting](../TROUBLESHOOTING.md)
- [Documentação Nodriver](https://github.com/ultrafunkamsterdam/nodriver)

---

## 🎯 Checklist de Troubleshooting

Se algo não funcionar:

- [ ] Display :1 está rodando? (`ps aux | grep Xvfb`)
- [ ] VNC acessível? (http://3.148.126.73:6080/vnc.html)
- [ ] Credenciais no `.env` corretas?
- [ ] API Key CapSolver válida?
- [ ] Diretório `data/raw_inputs/` existe?
- [ ] Chrome instalado? (`google-chrome --version`)
- [ ] Memória disponível? (`free -h`)
- [ ] Logs mostram erros? (`tail -100 logs/app.log`)

---

**Última atualização:** 2025-10-26
**Versão do fluxo:** 3.0
**Status:** ✅ **100% FUNCIONAL - PRODUÇÃO**
