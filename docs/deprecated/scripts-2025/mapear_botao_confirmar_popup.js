// ========================================================================
// MAPEADOR DE BOTÃO "CONFIRMAR" NA POPUP DO CAPTCHA
// Cole este código no console quando a POPUP do CAPTCHA estiver aberta!
// ========================================================================

(function() {
    console.clear();

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("🔍 MAPEADOR DE BOTÃO 'CONFIRMAR' - Popup CAPTCHA");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");
    console.log("📍 URL:", window.location.href);
    console.log("📅 Data:", new Date().toLocaleString('pt-BR'));
    console.log("");

    const resultados = {
        url_atual: window.location.href,
        data_hora: new Date().toISOString(),
        botoes_encontrados: []
    };

    function buscarBotoesRecursivo(doc, contexto, profundidade = 0) {
        if (profundidade > 10) return;

        const indent = "  ".repeat(profundidade);

        // Buscar TODOS os inputs e buttons
        const inputs = doc.querySelectorAll('input, button');

        console.log(indent + `📦 Documento: ${contexto} - ${inputs.length} elementos encontrados`);

        for (let i = 0; i < inputs.length; i++) {
            const elemento = inputs[i];

            const info = {
                tipo: elemento.tagName.toLowerCase(),
                contexto: contexto,
                profundidade: profundidade,
                tagName: elemento.tagName,
                type: elemento.type || null,
                name: elemento.name || null,
                value: elemento.value || null,
                id: elemento.id || null,
                className: elemento.className || null,
                innerHTML: elemento.innerHTML ? elemento.innerHTML.substring(0, 100) : null,
                visivel: elemento.offsetParent !== null,
                onclick: elemento.onclick ? elemento.onclick.toString().substring(0, 200) : null,
                onclickAttr: elemento.getAttribute('onclick') || null
            };

            resultados.botoes_encontrados.push(info);

            console.log(indent + `  ✅ Elemento #${i}:`);
            console.log(indent + `     Tag: ${info.tagName}`);
            console.log(indent + `     Type: ${info.type}`);
            console.log(indent + `     Name: ${info.name}`);
            console.log(indent + `     Value: ${info.value}`);
            console.log(indent + `     ID: ${info.id}`);
            console.log(indent + `     Class: ${info.className}`);
            console.log(indent + `     onclick: ${info.onclickAttr}`);
            console.log(indent + `     Visível: ${info.visivel ? '✅ SIM' : '❌ NÃO'}`);
            console.log("");
        }

        // Buscar em iframes
        const iframes = doc.querySelectorAll('iframe, frame');
        for (let i = 0; i < iframes.length; i++) {
            try {
                const iframeDoc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                if (iframeDoc) {
                    buscarBotoesRecursivo(iframeDoc, contexto + ` > iframe[${i}]`, profundidade + 1);
                }
            } catch (e) {
                console.log(indent + `  ⚠️ Iframe[${i}] cross-origin - não acessível`);
            }
        }
    }

    console.log("🔎 Iniciando busca...");
    console.log("");

    buscarBotoesRecursivo(document, "document", 0);

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("📊 RESUMO");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");
    console.log("Total de elementos encontrados:", resultados.botoes_encontrados.length);
    console.log("");

    // Filtrar botões que podem ser "Confirmar" ou "Prosseguir"
    const candidatos = resultados.botoes_encontrados.filter(b => {
        const texto = (b.value || b.innerHTML || b.name || b.id || '').toLowerCase();
        return texto.includes('confirmar') ||
               texto.includes('prosseguir') ||
               texto.includes('submit') ||
               texto.includes('finalizar') ||
               b.id === 'prosseguir' ||
               b.name === 'prosseguir' ||
               (b.onclickAttr && b.onclickAttr.includes('finalizar'));
    });

    if (candidatos.length > 0) {
        console.log("🎯 CANDIDATOS para 'Confirmar/Prosseguir':");
        console.log("");

        candidatos.forEach((c, i) => {
            console.log(`━━━ Candidato #${i + 1} ━━━`);
            console.log(`  Tag: ${c.tagName}`);
            console.log(`  Type: ${c.type}`);
            console.log(`  Name: ${c.name}`);
            console.log(`  Value: ${c.value}`);
            console.log(`  ID: ${c.id}`);
            console.log(`  Class: ${c.className}`);
            console.log(`  onclick: ${c.onclickAttr}`);
            console.log(`  Contexto: ${c.contexto}`);
            console.log(`  Profundidade: ${c.profundidade}`);
            console.log(`  Visível: ${c.visivel ? '✅ SIM' : '❌ NÃO'}`);
            console.log("");
        });

        console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        console.log("💡 SELETOR SUGERIDO PARA O CÓDIGO:");
        console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        console.log("");

        candidatos.forEach((c, i) => {
            let seletores = [];
            if (c.id) seletores.push(`#${c.id}`);
            if (c.name) seletores.push(`[name="${c.name}"]`);
            if (c.value) seletores.push(`[value="${c.value}"]`);

            if (seletores.length > 0) {
                console.log(`Candidato #${i + 1}:`);
                seletores.forEach(s => console.log(`  ${s}`));
                console.log("");
            }
        });

    } else {
        console.log("❌ NENHUM botão candidato encontrado!");
        console.log("");
        console.log("Listando TODOS os elementos visíveis:");
        console.log("");

        const visiveis = resultados.botoes_encontrados.filter(b => b.visivel);
        visiveis.forEach((b, i) => {
            console.log(`Elemento #${i + 1}:`);
            console.log(`  Tag: ${b.tagName}`);
            console.log(`  Type: ${b.type}`);
            console.log(`  Name: ${b.name}`);
            console.log(`  Value: ${b.value}`);
            console.log(`  ID: ${b.id}`);
            console.log(`  onclick: ${b.onclickAttr}`);
            console.log(`  Contexto: ${b.contexto}`);
            console.log("");
        });
    }

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("✅ ANÁLISE CONCLUÍDA");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");
    console.log("💾 Dados completos disponíveis em:");
    console.log("   window.confirmarResults");
    console.log("");

    // Salvar resultados globalmente
    window.confirmarResults = resultados;

    return resultados;
})();
