// ========================================================================
// MAPEADOR DE BOTÃO "GERAR RELATÓRIO" - SmartSecurities
// Cole este código no console do navegador (F12) para encontrar o botão
// ========================================================================

(function() {
    console.clear();

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("🔍 MAPEADOR DE BOTÃO 'GERAR RELATÓRIO' - SmartSecurities");
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

        // Buscar TODOS os inputs do tipo button/submit
        const inputs = doc.querySelectorAll('input[type="button"], input[type="submit"], button');

        console.log(indent + `📦 Documento: ${contexto} - ${inputs.length} botões encontrados`);

        for (let i = 0; i < inputs.length; i++) {
            const botao = inputs[i];

            const info = {
                tipo: 'botao',
                contexto: contexto,
                profundidade: profundidade,
                tagName: botao.tagName,
                type: botao.type || null,
                name: botao.name || null,
                value: botao.value || null,
                id: botao.id || null,
                className: botao.className || null,
                innerHTML: botao.innerHTML ? botao.innerHTML.substring(0, 100) : null,
                visivel: botao.offsetParent !== null,
                onclick: botao.onclick ? botao.onclick.toString().substring(0, 200) : null
            };

            resultados.botoes_encontrados.push(info);

            console.log(indent + `  ✅ Botão #${i}:`);
            console.log(indent + `     Tag: ${info.tagName}`);
            console.log(indent + `     Type: ${info.type}`);
            console.log(indent + `     Name: ${info.name}`);
            console.log(indent + `     Value: ${info.value}`);
            console.log(indent + `     ID: ${info.id}`);
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
    console.log("Total de botões encontrados:", resultados.botoes_encontrados.length);
    console.log("");

    // Filtrar botões que podem ser "Gerar relatório"
    const candidatos = resultados.botoes_encontrados.filter(b => {
        const texto = (b.value || b.innerHTML || '').toLowerCase();
        return texto.includes('gerar') ||
               texto.includes('imprimir') ||
               texto.includes('relatório') ||
               texto.includes('relatorio') ||
               b.name === 'Imprimir';
    });

    if (candidatos.length > 0) {
        console.log("🎯 CANDIDATOS para 'Gerar relatório':");
        console.log("");

        candidatos.forEach((c, i) => {
            console.log(`Candidato #${i + 1}:`);
            console.log(`  Tag: ${c.tagName}`);
            console.log(`  Type: ${c.type}`);
            console.log(`  Name: ${c.name}`);
            console.log(`  Value: ${c.value}`);
            console.log(`  ID: ${c.id}`);
            console.log(`  Contexto: ${c.contexto}`);
            console.log(`  Visível: ${c.visivel ? '✅' : '❌'}`);
            console.log("");
        });
    } else {
        console.log("❌ NENHUM botão candidato encontrado!");
        console.log("");
        console.log("Listando TODOS os botões visíveis:");
        console.log("");

        const visiveis = resultados.botoes_encontrados.filter(b => b.visivel);
        visiveis.forEach((b, i) => {
            console.log(`Botão #${i + 1}:`);
            console.log(`  Value: ${b.value}`);
            console.log(`  Name: ${b.name}`);
            console.log(`  ID: ${b.id}`);
            console.log(`  Contexto: ${b.contexto}`);
            console.log("");
        });
    }

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("✅ ANÁLISE CONCLUÍDA");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");
    console.log("💾 Dados completos disponíveis em:");
    console.log("   window.botoesResults");
    console.log("");

    // Salvar resultados globalmente
    window.botoesResults = resultados;

    return resultados;
})();
