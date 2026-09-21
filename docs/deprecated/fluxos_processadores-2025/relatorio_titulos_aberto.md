# 📋 Fluxo do Processador: Relatório Títulos Abertos

**Arquivo:** [src/processors/web/relatorio_titulos_aberto.py](../../src/processors/web/relatorio_titulos_aberto.py)
**Versão:** 1.0
**Display:** :2 (VNC porta 6081)
**API:** Porta 6091
**URL Alvo:** https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php

---

## 🎯 Objetivo

Extrair **TODOS os títulos abertos** do SmartSecurities e salvar em CSV, **SEM** marcar o checkbox de recompra (diferente do processador deságio que só extrai marcados).

---

## 🔄 Roteiro Completo de Execução

### **INICIALIZAÇÃO**

```
┌─────────────────────────────────────────────────────────┐
│ 1. INICIALIZAÇÃO DO PROCESSADOR                        │
└─────────────────────────────────────────────────────────┘
```

1. **Carregar Configurações**
   - Display: `:2` (dedicado)
   - VNC: `http://3.148.126.73:6081/vnc.html`
   - API: `http://3.148.126.73:6091` (placeholder)
   - Download Dir: `data/raw_inputs/`
   - Credenciais: `.env` (USUARIO_SITE_SMART, SENHA_SITE_SMART)
   - CapSolver API Key: `.env` (CAPSOLVER_API_KEY)

2. **Iniciar Browser (Nodriver)**
   - Modo: headless=False (visível)
   - Anti-detecção: Ativo (Nodriver)
   - Downloads: Configurados via CDP
   - Display: `:2`

---

### **ETAPA 1: LOGIN** 🔐

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 1: LOGIN NO SMARTSECURITIES                       │
└─────────────────────────────────────────────────────────┘
```

**URL:** https://www.smartsecurities.com.br/smartsecurities/

#### 1.1 Abrir Página de Login
```python
await tab.get(URL_LOGIN)
await asyncio.sleep(3)
```

#### 1.2 Aguardar Iframe de Login (até 20 tentativas)
```python
# Procurar iframe com id="principal"
iframe_principal = await tab.query_selector('iframe[id="principal"]')
```

**Estrutura de Iframes:**
```
┌─────────────────────────────────────────┐
│ Página Principal                        │
│  ┌───────────────────────────────────┐  │
│  │ <iframe id="principal">           │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │ Formulário de Login         │  │  │
│  │  │  - Campo Email              │  │  │
│  │  │  - Campo Senha              │  │  │
│  │  │  - Botão OK                 │  │  │
│  │  │  - reCAPTCHA                │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

#### 1.3 Preencher Credenciais
```javascript
// Executar JavaScript no iframe:
var campo = doc.getElementById('email');
campo.value = 'usuario@email.com';

var campoSenha = doc.getElementById('senha');
campoSenha.value = 'senha';
```

#### 1.4 Clicar no Botão OK (primeiro)
```javascript
var btnOk = doc.querySelector('input[value="OK"]');
btnOk.click();
```

#### 1.5 Aguardar reCAPTCHA Aparecer
```python
await asyncio.sleep(3)
```

#### 1.6 Resolver reCAPTCHA via CapSolver HTTP API
```
┌─────────────────────────────────────────┐
│ CapSolver HTTP API                      │
│                                         │
│ 1. Extrair site_key do HTML            │
│    → 6Le-JHwUAAAAAGZJWerkysOyQeo-...  │
│                                         │
│ 2. POST /createTask                     │
│    → taskId: 1a9f25d7-...              │
│                                         │
│ 3. Loop GET /getTaskResult              │
│    → Aguarda resolução (até 180s)      │
│                                         │
│ 4. Recebe token:                        │
│    → 0cAFcWeA50BPsMIN0HQc40Cin...      │
│                                         │
│ 5. Injeta token no reCAPTCHA:           │
│    document.getElementById(             │
│      'g-recaptcha-response'             │
│    ).value = token;                     │
└─────────────────────────────────────────┘
```

**Tempo médio:** 20-30 segundos

#### 1.7 Clicar no Botão OK Final
```javascript
btnOk.click();
```

#### 1.8 Aguardar Redirecionamento
```python
await asyncio.sleep(5)
```

**✅ Login Completo!**

---

### **LOOP DE EXTRAÇÃO** (Ciclos de 5 minutos)

```
┌─────────────────────────────────────────────────────────┐
│ CICLO #N - EXTRAÇÃO DE TÍTULOS ABERTOS                 │
└─────────────────────────────────────────────────────────┘
```

Cada ciclo executa as seguintes etapas:

---

### **ETAPA 2: NAVEGAÇÃO** 🌐

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 2: NAVEGANDO PARA TÍTULOS ABERTOS                │
└─────────────────────────────────────────────────────────┘
```

#### 2.1 Carregar Página via JavaScript
```javascript
// Executar no contexto da página:
window.location.href = 'https://www.smartsecurities.com.br/smart/financeiro/frmfinanceiro.php?page=financeiro/titulosemaberto.php';
```

**Por que JavaScript e não `tab.get()`?**
- Mantém sessão ativa
- Evita recarregar todo o contexto
- Simula navegação real do usuário

#### 2.2 Aguardar Página Carregar
```python
await asyncio.sleep(5)
```

**✅ Página carregada**

---

### **ETAPA 3: VERIFICAR reCAPTCHA** 🔍

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 3: VERIFICANDO reCAPTCHA                          │
└─────────────────────────────────────────────────────────┘
```

**Verificação:** A página pode ter reCAPTCHA ao navegar. Se tiver, resolve automaticamente usando o mesmo fluxo da ETAPA 1.6.

**Se reCAPTCHA encontrado:**
1. Resolver via CapSolver
2. Recarregar página (ETAPA 2 novamente)

**Se sem reCAPTCHA:**
- Continua para próxima etapa

---

### **ETAPA 4: AGUARDAR FRAMES PRONTOS** ⏳

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 4: AGUARDANDO FRAMES PRONTOS                      │
└─────────────────────────────────────────────────────────┘
```

**Estrutura de Frames da Página de Títulos:**

```
┌─────────────────────────────────────────────────────────┐
│ Página Principal (frmfinanceiro.php)                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │ <iframe name="code" id="code">                    │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │ <frame name="text">                         │  │  │
│  │  │  ┌───────────────────────────────────────┐  │  │  │
│  │  │  │ Formulário de Busca                   │  │  │  │
│  │  │  │  - Campo Data Inicial (Emissao1)      │  │  │  │
│  │  │  │  - Campo Data Final (Emissao23/2)     │  │  │  │
│  │  │  │  - Botão Pesquisar                    │  │  │  │
│  │  │  └───────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ <iframe name="lista">                             │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │ Tabela de Resultados                        │  │  │
│  │  │  - Checkbox "Selecionar Todos"              │  │  │
│  │  │  - Linhas de títulos                        │  │  │
│  │  │  - Botão "Gerar CSV"                        │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

#### 4.1 Verificar Iframe "code"
```javascript
var frameCode = document.getElementById('code');
// Deve existir e estar acessível
```

#### 4.2 Verificar Iframe "lista"
```javascript
var frameLista = document.getElementsByName('lista')[0];
// Deve existir e estar acessível
```

**Tentativas:** Até 30 vezes (1s cada = 30s total)

**✅ Frames prontos!**

---

### **ETAPA 5: PREENCHER DATAS** 📅

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 5: PREENCHENDO DATAS                              │
└─────────────────────────────────────────────────────────┘
```

**❌ ETAPA COM FALHA ATUAL**

#### 5.1 Calcular Datas
```python
# Data inicial: 90 dias atrás
data_inicial = datetime.now() - timedelta(days=90)
data_inicial_str = data_inicial.strftime("%d/%m/%Y")  # Ex: "26/07/2025"

# Data final: Hoje
data_final = datetime.now()
data_final_str = data_final.strftime("%d/%m/%Y")  # Ex: "25/10/2025"
```

#### 5.2 Navegar para Frame Interno
```javascript
// 1. Acessar frame "code"
var frameCode = document.getElementById('code');
var frameCodeDoc = frameCode.contentDocument;

// 2. Procurar frame "text" dentro de "code"
var frameText = frameCodeDoc.querySelector('frame[name="text"]');
var doc = frameText.contentDocument;
```

#### 5.3 Preencher Campo Inicial (OBRIGATÓRIO)
```javascript
var campoInicial = doc.getElementById('Emissao1');

// CRÍTICO: Remover readonly antes!
campoInicial.removeAttribute('readonly');

// Preencher valor
campoInicial.value = '26/07/2025';

// Validar
console.log('Data inicial:', campoInicial.value);
```

#### 5.4 Preencher Campo Final (OPCIONAL)
```javascript
// Tenta primeiro ID Emissao23
var campoFinal = doc.getElementById('Emissao23');

// Se não encontrar, tenta Emissao2
if (!campoFinal) {
    campoFinal = doc.getElementById('Emissao2');
}

if (campoFinal) {
    campoFinal.removeAttribute('readonly');
    campoFinal.value = '25/10/2025';
    console.log('Data final:', campoFinal.value);
} else {
    console.log('Campo final não encontrado (opcional)');
}
```

**⚠️ PROBLEMA ATUAL:**
- JavaScript executa sem erro
- Mas campos não aceitam o valor
- Possível causa: evento JavaScript bloqueando, shadow DOM, ou validação no frontend

**❌ FALHA: Campos retornam vazios após preenchimento**

---

### **ETAPA 6: CLICAR PESQUISAR** 🔎

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 6: CLICANDO PESQUISAR                             │
└─────────────────────────────────────────────────────────┘
```

**NÃO EXECUTADA (pois ETAPA 5 falha)**

#### Roteiro Previsto:
```javascript
// Localizar botão Pesquisar
var btnPesquisar = doc.querySelector('input[value="Pesquisar"]');

// Clicar
btnPesquisar.click();
```

**Aguardar:** 5 segundos para resultados carregarem

---

### **ETAPA 7: SELECIONAR TODOS RESULTADOS** ☑️

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 7: SELECIONANDO TODOS OS RESULTADOS              │
└─────────────────────────────────────────────────────────┘
```

**NÃO EXECUTADA (pois ETAPA 5 falha)**

#### Roteiro Previsto:
```javascript
// Acessar frame "lista"
var frameLista = document.getElementsByName('lista')[0];
var listaDoc = frameLista.contentDocument;

// Localizar checkbox "Selecionar Todos"
var checkboxTodos = listaDoc.querySelector('input[type="checkbox"][onclick*="marcartodos"]');

// Clicar
checkboxTodos.click();
```

**Resultado:** Todos os títulos da tabela ficam marcados

---

### **ETAPA 8: GERAR CSV** 📊

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 8: GERANDO CSV                                    │
└─────────────────────────────────────────────────────────┘
```

**NÃO EXECUTADA (pois ETAPA 5 falha)**

#### Roteiro Previsto:
```javascript
// Localizar botão "Gerar CSV" no frame lista
var btnGerarCsv = listaDoc.querySelector('input[value="Gerar CSV"]');

// Clicar
btnGerarCsv.click();
```

**Download:**
- Browser inicia download automático
- Arquivo salvo em: `data/raw_inputs/`
- Formato: `RelatorioTitulosAbertos.csv` (nome genérico)

**Aguardar:** Até 30 segundos para download completar

---

### **ETAPA 9: RENOMEAR CSV** 📝

```
┌─────────────────────────────────────────────────────────┐
│ ETAPA 9: RENOMEANDO CSV                                 │
└─────────────────────────────────────────────────────────┘
```

**NÃO EXECUTADA (pois ETAPA 5 falha)**

#### Roteiro Previsto:

1. **Aguardar Download Completar**
   ```python
   # Verificar se há arquivos .crdownload (download em andamento)
   while glob.glob("*.crdownload"):
       await asyncio.sleep(1)
   ```

2. **Localizar CSV Mais Recente**
   ```python
   csvs = glob.glob(f"{download_dir}/*.csv")
   arquivo_path = max(csvs, key=os.path.getmtime)
   ```

3. **Renomear com Timestamp**
   ```python
   timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
   nome_novo = f"titulos_abertos_{timestamp}.csv"
   # Ex: titulos_abertos_2025_10_25_223045.csv

   os.rename(arquivo_path, caminho_destino)
   ```

**✅ CSV salvo com nome único**

---

### **FIM DO CICLO** ✅

```
┌─────────────────────────────────────────────────────────┐
│ ✅ CICLO CONCLUÍDO!                                     │
│ ✅ Arquivo: titulos_abertos_2025_10_25_223045.csv      │
└─────────────────────────────────────────────────────────┘
```

**Aguardar:** 5 minutos (300 segundos)

**Repetir:** ETAPA 2 até ETAPA 9 em loop infinito

---

## 📊 Estrutura do CSV Gerado

**Nome:** `titulos_abertos_YYYY_MM_DD_HHMMSS.csv`

**Localização:** `data/raw_inputs/`

**Conteúdo (exemplo):**
```csv
Título,Emissão,Vencimento,Valor,Status,Cliente,...
12345,01/08/2025,01/11/2025,R$ 10.000,00,Aberto,Cliente ABC,...
12346,05/08/2025,05/12/2025,R$ 25.000,00,Aberto,Cliente XYZ,...
...
```

**Diferença para processador deságio:**
- **deságio:** Extrai apenas títulos **marcados para recompra**
- **titulos_aberto:** Extrai **TODOS** os títulos abertos (sem filtro)

---

## 🔄 Diferenças vs Processador Deságio

| Aspecto | relatorio_operacao_desagio | relatorio_titulos_aberto |
|---------|----------------------------|--------------------------|
| **Display** | :1 (VNC 6080) | :2 (VNC 6081) |
| **URL** | `.../relatoriooperacaodesagio.php` | `.../titulosemaberto.php` |
| **Filtro** | Apenas marcados para recompra | **TODOS** os títulos |
| **Checkbox** | Marca "Títulos Recompra" | **NÃO marca checkbox** |
| **Intervalo** | 60 segundos | 300 segundos (5 min) |
| **CSV Output** | `desagio_YYYY_MM_DD_HHMMSS.csv` | `titulos_abertos_YYYY_MM_DD_HHMMSS.csv` |
| **Status** | ✅ Funcionando | ❌ Falha na ETAPA 5 |

---

## ❌ Status Atual: FALHA NA ETAPA 5

### Problema:
**Campo de data não aceita valores via JavaScript**

### Evidências:
```
[DATAS] Preenchendo datas...
[DATAS] ❌ Erro ao preencher datas
Exception: Erro ao preencher datas
```

### Próximos Passos:
1. **Depurar via VNC** (http://3.148.126.73:6081/vnc.html)
2. **Inspecionar campo no DevTools**
3. **Testar preenchimento manual no Console**
4. **Implementar solução alternativa:**
   - Usar Nodriver direto (sem JavaScript)
   - Ou simular digitação humana (caractere por caractere)

---

## 🎯 Resumo do Fluxo

```
INICIALIZAÇÃO
    ↓
ETAPA 1: Login + CAPTCHA                        ✅ OK
    ↓
┌─ LOOP INFINITO (5 min entre ciclos) ──────────────┐
│                                                    │
│  ETAPA 2: Navegar para títulos abertos       ✅ OK │
│      ↓                                             │
│  ETAPA 3: Verificar reCAPTCHA                ✅ OK │
│      ↓                                             │
│  ETAPA 4: Aguardar frames prontos            ✅ OK │
│      ↓                                             │
│  ETAPA 5: Preencher datas                    ❌ FALHA │
│      ↓                                             │
│  ETAPA 6: Clicar Pesquisar               ⏭️ Não exec│
│      ↓                                             │
│  ETAPA 7: Selecionar todos resultados    ⏭️ Não exec│
│      ↓                                             │
│  ETAPA 8: Gerar CSV                      ⏭️ Não exec│
│      ↓                                             │
│  ETAPA 9: Renomear CSV                   ⏭️ Não exec│
│      ↓                                             │
│  Aguardar 5 minutos                                │
│      ↓                                             │
└────┘                                               │
```

---

**Documentação criada em:** 2025-10-25
**Status:** Processador em desenvolvimento, aguardando correção da ETAPA 5
