# Debug de Popup SmartSecurities (Janela sem Botão Direito)

## Problema

O SmartSecurities abre uma janela popup após clicar em "Imprimir Boleto", mas desabilita o botão direito do mouse (context menu), impedindo a inspeção de elementos.

## Solução

Use os scripts JavaScript abaixo no console do navegador (F12) para investigar a popup.

---

## 📋 Passos de Uso

### 1. Executar o Processador

```bash
cd /home/ubuntu/PROSPER-ERP-AUTOMATION
DISPLAY=:1 PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION venv/bin/python3 src/processors/web/emissao_boleto_primeira_via.py
```

### 2. Acessar VNC no Browser

Durante a pausa de 3 minutos (após clicar "Imprimir Boleto"):

```
http://3.148.126.73:6080/vnc.html
```

### 3. Focar na Janela Popup

- Quando a janela pequena aparecer, clique nela para focar
- Pressione **F12** para abrir DevTools
- Vá na aba **Console**

### 4. Colar os Scripts Abaixo

Cole e execute cada script no console.

---

## 🛠️ Scripts JavaScript de Debug

### Script 1: Reabilitar Botão Direito e Eventos

```javascript
// ============================================================================
// SCRIPT 1: REABILITAR BOTÃO DIREITO E REMOVER BLOQUEIOS
// ============================================================================

(function() {
    console.log("🔓 Removendo bloqueios de inspeção...");

    // Remover todos os event listeners de contextmenu (botão direito)
    document.addEventListener('contextmenu', function(e) {
        e.stopPropagation();
        return true;
    }, true);

    // Remover proteções comuns
    document.oncontextmenu = null;
    document.onselectstart = null;
    document.ondragstart = null;

    // Reabilitar seleção de texto
    document.body.style.userSelect = 'auto';
    document.body.style.webkitUserSelect = 'auto';
    document.body.style.mozUserSelect = 'auto';

    // Remover event listeners inline
    const elements = document.querySelectorAll('*');
    elements.forEach(el => {
        el.oncontextmenu = null;
        el.onselectstart = null;
    });

    console.log("✅ Botão direito reabilitado!");
    console.log("✅ Agora você pode usar Inspect Element normalmente");
})();
```

### Script 2: Mapear Todos os Elementos Clicáveis

```javascript
// ============================================================================
// SCRIPT 2: MAPEAR TODOS OS BOTÕES E ELEMENTOS CLICÁVEIS
// ============================================================================

(function() {
    console.log("🔍 Mapeando todos os elementos clicáveis...\n");

    const elementos = {
        buttons: [],
        inputs: [],
        links: [],
        outros: []
    };

    // Procurar botões
    document.querySelectorAll('button').forEach((el, idx) => {
        elementos.buttons.push({
            index: idx,
            tag: 'BUTTON',
            text: el.textContent.trim(),
            id: el.id,
            name: el.name,
            type: el.type,
            value: el.value,
            classes: el.className,
            visible: el.offsetParent !== null,
            onclick: el.onclick ? el.onclick.toString() : null,
            elemento: el
        });
    });

    // Procurar inputs (submit, button)
    document.querySelectorAll('input[type="button"], input[type="submit"], input[type="reset"]').forEach((el, idx) => {
        elementos.inputs.push({
            index: idx,
            tag: 'INPUT',
            text: el.value,
            id: el.id,
            name: el.name,
            type: el.type,
            value: el.value,
            classes: el.className,
            visible: el.offsetParent !== null,
            onclick: el.onclick ? el.onclick.toString() : null,
            elemento: el
        });
    });

    // Procurar links
    document.querySelectorAll('a').forEach((el, idx) => {
        elementos.links.push({
            index: idx,
            tag: 'A',
            text: el.textContent.trim(),
            id: el.id,
            href: el.href,
            classes: el.className,
            visible: el.offsetParent !== null,
            onclick: el.onclick ? el.onclick.toString() : null,
            elemento: el
        });
    });

    // Procurar outros elementos com onclick
    document.querySelectorAll('[onclick]').forEach((el, idx) => {
        if (!['BUTTON', 'INPUT', 'A'].includes(el.tagName)) {
            elementos.outros.push({
                index: idx,
                tag: el.tagName,
                text: el.textContent.trim().substring(0, 50),
                id: el.id,
                classes: el.className,
                visible: el.offsetParent !== null,
                onclick: el.onclick.toString(),
                elemento: el
            });
        }
    });

    // Exibir resultados
    console.log("═══════════════════════════════════════════════════════════");
    console.log("📊 RESUMO DE ELEMENTOS CLICÁVEIS");
    console.log("═══════════════════════════════════════════════════════════");
    console.log(`Botões <button>: ${elementos.buttons.length}`);
    console.log(`Inputs (button/submit): ${elementos.inputs.length}`);
    console.log(`Links <a>: ${elementos.links.length}`);
    console.log(`Outros com onclick: ${elementos.outros.length}`);
    console.log("═══════════════════════════════════════════════════════════\n");

    // Detalhar botões
    if (elementos.buttons.length > 0) {
        console.log("🔘 BOTÕES <button>:");
        elementos.buttons.forEach(btn => {
            console.log(`  [${btn.index}] ${btn.visible ? '✅' : '❌'} "${btn.text}"`);
            console.log(`      ID: ${btn.id || 'N/A'} | Name: ${btn.name || 'N/A'} | Type: ${btn.type || 'N/A'}`);
            if (btn.onclick) console.log(`      onclick: ${btn.onclick.substring(0, 100)}...`);
        });
        console.log("");
    }

    // Detalhar inputs
    if (elementos.inputs.length > 0) {
        console.log("🔘 INPUTS (button/submit):");
        elementos.inputs.forEach(inp => {
            console.log(`  [${inp.index}] ${inp.visible ? '✅' : '❌'} "${inp.value}"`);
            console.log(`      ID: ${inp.id || 'N/A'} | Name: ${inp.name || 'N/A'} | Type: ${inp.type}`);
            if (inp.onclick) console.log(`      onclick: ${inp.onclick.substring(0, 100)}...`);
        });
        console.log("");
    }

    // Detalhar links
    if (elementos.links.length > 0) {
        console.log("🔗 LINKS <a>:");
        elementos.links.forEach(link => {
            console.log(`  [${link.index}] ${link.visible ? '✅' : '❌'} "${link.text}"`);
            console.log(`      ID: ${link.id || 'N/A'} | href: ${link.href || 'N/A'}`);
            if (link.onclick) console.log(`      onclick: ${link.onclick.substring(0, 100)}...`);
        });
        console.log("");
    }

    // Salvar para uso posterior
    window._debugElementos = elementos;

    console.log("💾 Elementos salvos em: window._debugElementos");
    console.log("📝 Use o Script 3 para inspecionar elementos específicos");
    console.log("═══════════════════════════════════════════════════════════\n");

    return elementos;
})();
```

### Script 3: Inspecionar e Clicar em Elemento Específico

```javascript
// ============================================================================
// SCRIPT 3: INSPECIONAR E CLICAR EM ELEMENTO ESPECÍFICO
// ============================================================================

// USAGE:
// inspecionarElemento('buttons', 0);  // Inspeciona primeiro botão
// clicarElemento('inputs', 1);        // Clica no segundo input

function inspecionarElemento(tipo, index) {
    const elementos = window._debugElementos;

    if (!elementos) {
        console.error("❌ Execute o Script 2 primeiro!");
        return;
    }

    if (!elementos[tipo]) {
        console.error(`❌ Tipo inválido. Use: buttons, inputs, links, outros`);
        return;
    }

    const el = elementos[tipo][index];

    if (!el) {
        console.error(`❌ Índice ${index} não encontrado em ${tipo}`);
        return;
    }

    console.log("═══════════════════════════════════════════════════════════");
    console.log(`🔍 INSPEÇÃO DETALHADA: ${tipo.toUpperCase()}[${index}]`);
    console.log("═══════════════════════════════════════════════════════════");
    console.log(`Tag: ${el.tag}`);
    console.log(`Texto: "${el.text}"`);
    console.log(`ID: ${el.id || 'N/A'}`);
    console.log(`Name: ${el.name || 'N/A'}`);
    console.log(`Type: ${el.type || 'N/A'}`);
    console.log(`Value: ${el.value || 'N/A'}`);
    console.log(`Classes: ${el.classes || 'N/A'}`);
    console.log(`Visível: ${el.visible ? 'SIM ✅' : 'NÃO ❌'}`);

    if (el.href) console.log(`Href: ${el.href}`);

    if (el.onclick) {
        console.log(`\n📜 Onclick Handler:`);
        console.log(el.onclick);
    }

    console.log(`\n🏷️  Seletores CSS possíveis:`);

    const seletores = [];

    if (el.id) {
        seletores.push(`#${el.id}`);
    }

    if (el.name) {
        seletores.push(`${el.tag.toLowerCase()}[name="${el.name}"]`);
    }

    if (el.value) {
        seletores.push(`${el.tag.toLowerCase()}[value="${el.value}"]`);
    }

    if (el.type) {
        seletores.push(`${el.tag.toLowerCase()}[type="${el.type}"]`);
    }

    seletores.forEach((sel, idx) => {
        console.log(`  ${idx + 1}. ${sel}`);
    });

    console.log(`\n🖱️  Para clicar: clicarElemento('${tipo}', ${index})`);
    console.log(`📍 Para destacar: destacarElemento('${tipo}', ${index})`);
    console.log("═══════════════════════════════════════════════════════════\n");

    // Destacar elemento na página
    el.elemento.style.outline = '5px solid red';
    el.elemento.style.backgroundColor = 'yellow';

    return el;
}

function clicarElemento(tipo, index) {
    const elementos = window._debugElementos;

    if (!elementos || !elementos[tipo] || !elementos[tipo][index]) {
        console.error("❌ Elemento não encontrado. Execute Script 2 e verifique índices.");
        return;
    }

    const el = elementos[tipo][index].elemento;

    console.log(`🖱️  Clicando em ${tipo}[${index}]...`);

    // Tentar múltiplas formas de clicar
    try {
        el.click();
        console.log("✅ Clique realizado com sucesso!");
    } catch (e) {
        console.warn("⚠️ Clique direto falhou, tentando dispatchEvent...");

        const event = new MouseEvent('click', {
            view: window,
            bubbles: true,
            cancelable: true
        });

        el.dispatchEvent(event);
        console.log("✅ Evento de clique disparado!");
    }
}

function destacarElemento(tipo, index) {
    const elementos = window._debugElementos;

    if (!elementos || !elementos[tipo] || !elementos[tipo][index]) {
        console.error("❌ Elemento não encontrado.");
        return;
    }

    const el = elementos[tipo][index].elemento;

    el.style.outline = '5px solid red';
    el.style.backgroundColor = 'yellow';
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    console.log(`✅ Elemento destacado em vermelho/amarelo`);
}

console.log("✅ Funções carregadas:");
console.log("   - inspecionarElemento(tipo, index)");
console.log("   - clicarElemento(tipo, index)");
console.log("   - destacarElemento(tipo, index)");
```

### Script 4: Procurar Botão "OK" Automaticamente

```javascript
// ============================================================================
// SCRIPT 4: PROCURAR BOTÃO "OK" AUTOMATICAMENTE
// ============================================================================

(function() {
    console.log("🔍 Procurando botão 'OK' na página...\n");

    const candidatos = [];

    // Estratégia 1: Procurar inputs com value="OK"
    document.querySelectorAll('input').forEach(el => {
        const value = (el.value || '').toUpperCase();
        const name = (el.name || '').toUpperCase();

        if (value.includes('OK') || name.includes('OK')) {
            candidatos.push({
                tipo: 'input',
                relevancia: value === 'OK' ? 10 : 5,
                elemento: el,
                info: `<input type="${el.type}" name="${el.name}" value="${el.value}">`
            });
        }
    });

    // Estratégia 2: Procurar botões com texto "OK"
    document.querySelectorAll('button').forEach(el => {
        const text = (el.textContent || '').toUpperCase().trim();

        if (text.includes('OK')) {
            candidatos.push({
                tipo: 'button',
                relevancia: text === 'OK' ? 10 : 5,
                elemento: el,
                info: `<button>${el.textContent}</button>`
            });
        }
    });

    // Estratégia 3: Procurar links com texto "OK"
    document.querySelectorAll('a').forEach(el => {
        const text = (el.textContent || '').toUpperCase().trim();

        if (text.includes('OK')) {
            candidatos.push({
                tipo: 'link',
                relevancia: text === 'OK' ? 8 : 4,
                elemento: el,
                info: `<a href="${el.href}">${el.textContent}</a>`
            });
        }
    });

    // Ordenar por relevância
    candidatos.sort((a, b) => b.relevancia - a.relevancia);

    console.log("═══════════════════════════════════════════════════════════");
    console.log(`📊 ENCONTRADOS ${candidatos.length} CANDIDATOS A BOTÃO OK`);
    console.log("═══════════════════════════════════════════════════════════\n");

    candidatos.forEach((cand, idx) => {
        console.log(`[${idx}] ${cand.info}`);
        console.log(`    Tipo: ${cand.tipo} | Relevância: ${cand.relevancia}/10`);
        console.log(`    Visível: ${cand.elemento.offsetParent !== null ? 'SIM ✅' : 'NÃO ❌'}`);

        // Gerar seletor CSS
        const el = cand.elemento;
        let seletor = '';

        if (el.id) {
            seletor = `#${el.id}`;
        } else if (el.name) {
            seletor = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        } else if (el.value) {
            seletor = `${el.tagName.toLowerCase()}[value="${el.value}"]`;
        } else {
            seletor = el.tagName.toLowerCase();
        }

        console.log(`    Seletor CSS: ${seletor}\n`);
    });

    // Salvar candidatos
    window._candidatosOK = candidatos;

    if (candidatos.length > 0) {
        console.log("💡 DICA: Para clicar no candidato mais provável:");
        console.log("   window._candidatosOK[0].elemento.click()");
        console.log("\n💡 Para destacar o candidato:");
        console.log("   window._candidatosOK[0].elemento.style.outline = '5px solid red'");
    } else {
        console.log("⚠️ Nenhum candidato encontrado!");
        console.log("   Use o Script 2 para mapear todos os elementos");
    }

    console.log("═══════════════════════════════════════════════════════════\n");

    return candidatos;
})();
```

### Script 5: Clicar Automaticamente no Botão OK Mais Provável

```javascript
// ============================================================================
// SCRIPT 5: CLICAR AUTOMATICAMENTE NO MELHOR CANDIDATO
// ============================================================================

(function() {
    if (!window._candidatosOK || window._candidatosOK.length === 0) {
        console.error("❌ Execute o Script 4 primeiro!");
        return;
    }

    const melhorCandidato = window._candidatosOK[0];

    console.log(`🖱️  Clicando no melhor candidato: ${melhorCandidato.info}`);

    try {
        melhorCandidato.elemento.click();
        console.log("✅ Clique realizado com sucesso!");
    } catch (e) {
        console.warn("⚠️ Tentando dispatchEvent...");

        const event = new MouseEvent('click', {
            view: window,
            bubbles: true,
            cancelable: true
        });

        melhorCandidato.elemento.dispatchEvent(event);
        console.log("✅ Evento disparado!");
    }
})();
```

---

## 📝 Exemplo de Uso Completo

```javascript
// 1. Reabilitar botão direito
// (Cole Script 1)

// 2. Mapear todos os elementos
// (Cole Script 2)

// 3. Procurar botão OK
// (Cole Script 4)

// 4. Clicar no botão OK
// (Cole Script 5)

// OU manualmente:
window._candidatosOK[0].elemento.click();
```

---

## 🎯 Identificar o Seletor Correto

Após executar os scripts, você terá:

1. **Lista de todos os elementos clicáveis**
2. **Candidatos ao botão OK ordenados por relevância**
3. **Seletores CSS para usar no Playwright**

### Exemplo de Output:

```
[0] <input type="submit" name="OK" value="OK">
    Tipo: input | Relevância: 10/10
    Visível: SIM ✅
    Seletor CSS: input[name="OK"]
```

### Usar no Playwright:

```python
# No processador, substituir linha ~652:
await popup.click('input[name="OK"]')
```

---

## 🚨 Dicas Importantes

1. **Executar os scripts na ordem** (1 → 2 → 4 → 5)
2. **Se a janela for iframe**, abra o console NO IFRAME (não na página pai)
3. **Se múltiplos candidatos**, teste cada um:
   ```javascript
   window._candidatosOK[0].elemento.click();
   window._candidatosOK[1].elemento.click();
   ```
4. **Copiar o seletor CSS** que funcionar para usar no código Python

---

## 📊 Próximos Passos

Após identificar o seletor correto:

1. Anotar o seletor CSS (ex: `input[name="OK"]`)
2. Atualizar o processador Python com o seletor
3. Remover a pausa de 180 segundos
4. Testar o fluxo completo automatizado
