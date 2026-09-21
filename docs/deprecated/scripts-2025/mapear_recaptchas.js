// ========================================================================
// MAPEADOR DE RECAPTCHAS - SmartSecurities
// Cole este código no console do navegador (F12) para mapear todos os CAPTCHAs
// ========================================================================

(function() {
    console.clear();

    const resultados = {
        url_atual: window.location.href,
        data_hora: new Date().toISOString(),
        recaptchas_encontrados: []
    };

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("🔍 MAPEADOR DE RECAPTCHAS - SmartSecurities");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");
    console.log("📍 URL:", window.location.href);
    console.log("📅 Data:", new Date().toLocaleString('pt-BR'));
    console.log("");

    // ====================================================================
    // FUNÇÃO: Buscar recursivamente em todos os documentos e iframes
    // ====================================================================

    function buscarRecursivo(doc, contexto, profundidade = 0) {
        if (profundidade > 10) return; // Limitar profundidade

        const indent = "  ".repeat(profundidade);

        // 1. Buscar iframes com reCAPTCHA na URL
        const iframes = doc.querySelectorAll('iframe');
        for (let i = 0; i < iframes.length; i++) {
            const iframe = iframes[i];
            const src = iframe.src || '';

            if (src.indexOf('recaptcha') !== -1 || src.indexOf('google.com') !== -1) {
                const matchK = src.match(/[?&]k=([^&]+)/);
                if (matchK && matchK[1]) {
                    const sitekey = matchK[1];

                    resultados.recaptchas_encontrados.push({
                        tipo: 'iframe_src',
                        contexto: contexto,
                        profundidade: profundidade,
                        sitekey: sitekey,
                        tamanho: sitekey.length,
                        iframe_src: src.substring(0, 100) + '...',
                        xpath: getXPath(iframe)
                    });

                    console.log(indent + "✅ reCAPTCHA no iframe #" + i);
                    console.log(indent + "   Site key:", sitekey);
                    console.log(indent + "   Tamanho:", sitekey.length, "chars");
                    console.log(indent + "   Contexto:", contexto);
                    console.log("");
                }
            }

            // Tentar acessar contentDocument (se same-origin)
            try {
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                if (iframeDoc) {
                    buscarRecursivo(iframeDoc, contexto + " > iframe[" + i + "]", profundidade + 1);
                }
            } catch (e) {
                // Ignorar cross-origin
            }
        }

        // 2. Buscar elementos com data-sitekey
        const elementosSitekey = doc.querySelectorAll('[data-sitekey]');
        for (let i = 0; i < elementosSitekey.length; i++) {
            const elemento = elementosSitekey[i];
            const sitekey = elemento.getAttribute('data-sitekey');

            if (sitekey) {
                resultados.recaptchas_encontrados.push({
                    tipo: 'data-sitekey',
                    contexto: contexto,
                    profundidade: profundidade,
                    sitekey: sitekey,
                    tamanho: sitekey.length,
                    elemento: elemento.tagName,
                    classes: elemento.className,
                    xpath: getXPath(elemento)
                });

                console.log(indent + "✅ data-sitekey no elemento", elemento.tagName);
                console.log(indent + "   Site key:", sitekey);
                console.log(indent + "   Tamanho:", sitekey.length, "chars");
                console.log(indent + "   Classes:", elemento.className || "(nenhuma)");
                console.log(indent + "   Contexto:", contexto);
                console.log("");
            }
        }

        // 3. Buscar .g-recaptcha
        const gRecaptchas = doc.querySelectorAll('.g-recaptcha');
        for (let i = 0; i < gRecaptchas.length; i++) {
            const elemento = gRecaptchas[i];
            const sitekey = elemento.getAttribute('data-sitekey');

            if (sitekey) {
                resultados.recaptchas_encontrados.push({
                    tipo: 'g-recaptcha',
                    contexto: contexto,
                    profundidade: profundidade,
                    sitekey: sitekey,
                    tamanho: sitekey.length,
                    id: elemento.id || "(sem id)",
                    xpath: getXPath(elemento)
                });

                console.log(indent + "✅ .g-recaptcha #" + i);
                console.log(indent + "   Site key:", sitekey);
                console.log(indent + "   Tamanho:", sitekey.length, "chars");
                console.log(indent + "   ID:", elemento.id || "(sem id)");
                console.log(indent + "   Contexto:", contexto);
                console.log("");
            }
        }
    }

    // ====================================================================
    // FUNÇÃO: Obter XPath de um elemento
    // ====================================================================

    function getXPath(elemento) {
        if (elemento.id !== '') {
            return '//*[@id="' + elemento.id + '"]';
        }
        if (elemento === document.body) {
            return '/html/body';
        }

        let ix = 0;
        const siblings = elemento.parentNode ? elemento.parentNode.childNodes : [];

        for (let i = 0; i < siblings.length; i++) {
            const sibling = siblings[i];
            if (sibling === elemento) {
                return getXPath(elemento.parentNode) + '/' + elemento.tagName.toLowerCase() + '[' + (ix + 1) + ']';
            }
            if (sibling.nodeType === 1 && sibling.tagName === elemento.tagName) {
                ix++;
            }
        }
    }

    // ====================================================================
    // EXECUTAR BUSCA
    // ====================================================================

    console.log("🔎 Iniciando busca...");
    console.log("");

    buscarRecursivo(document, "document", 0);

    // ====================================================================
    // RESUMO
    // ====================================================================

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("📊 RESUMO");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");
    console.log("Total de reCAPTCHAs encontrados:", resultados.recaptchas_encontrados.length);
    console.log("");

    if (resultados.recaptchas_encontrados.length === 0) {
        console.log("❌ NENHUM RECAPTCHA ENCONTRADO NESTA PÁGINA");
        console.log("");
        console.log("Possíveis motivos:");
        console.log("  1. A página ainda não carregou completamente");
        console.log("  2. O CAPTCHA aparece apenas após alguma ação (clicar em botão, etc)");
        console.log("  3. Esta página não possui CAPTCHAs");
        console.log("");
    } else {
        // Agrupar por site key único
        const sitekeysUnicos = {};

        for (let i = 0; i < resultados.recaptchas_encontrados.length; i++) {
            const captcha = resultados.recaptchas_encontrados[i];
            const key = captcha.sitekey;

            if (!sitekeysUnicos[key]) {
                sitekeysUnicos[key] = {
                    sitekey: key,
                    tamanho: captcha.tamanho,
                    ocorrencias: []
                };
            }

            sitekeysUnicos[key].ocorrencias.push({
                tipo: captcha.tipo,
                contexto: captcha.contexto
            });
        }

        console.log("📝 Site Keys únicos encontrados:", Object.keys(sitekeysUnicos).length);
        console.log("");

        let contador = 1;
        for (let key in sitekeysUnicos) {
            const info = sitekeysUnicos[key];

            console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            console.log("🔑 SITE KEY #" + contador);
            console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            console.log("");
            console.log("Site key:", key);
            console.log("Tamanho:", info.tamanho, "caracteres");
            console.log("");
            console.log("Status:", info.tamanho === 40 ? "✅ VÁLIDO (40 chars)" : "⚠️ ATENÇÃO (" + info.tamanho + " chars - esperado 40)");
            console.log("");
            console.log("Encontrado em " + info.ocorrencias.length + " local(is):");

            for (let i = 0; i < info.ocorrencias.length; i++) {
                const ocorrencia = info.ocorrencias[i];
                console.log("  " + (i + 1) + ". Tipo:", ocorrencia.tipo, "→", ocorrencia.contexto);
            }

            console.log("");

            contador++;
        }
    }

    // ====================================================================
    // GERAR MARKDOWN PARA COPIAR
    // ====================================================================

    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("📋 MARKDOWN PARA DOCUMENTAÇÃO");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");

    let markdown = "# reCAPTCHAs Encontrados\n\n";
    markdown += "## Página: " + window.location.href + "\n";
    markdown += "## Data: " + new Date().toLocaleString('pt-BR') + "\n\n";
    markdown += "---\n\n";

    if (resultados.recaptchas_encontrados.length === 0) {
        markdown += "❌ **Nenhum reCAPTCHA encontrado nesta página**\n\n";
    } else {
        const sitekeysUnicos = {};

        for (let i = 0; i < resultados.recaptchas_encontrados.length; i++) {
            const captcha = resultados.recaptchas_encontrados[i];
            const key = captcha.sitekey;

            if (!sitekeysUnicos[key]) {
                sitekeysUnicos[key] = {
                    sitekey: key,
                    tamanho: captcha.tamanho,
                    ocorrencias: []
                };
            }

            sitekeysUnicos[key].ocorrencias.push(captcha);
        }

        markdown += "## Total: " + Object.keys(sitekeysUnicos).length + " site key(s) único(s)\n\n";

        let contador = 1;
        for (let key in sitekeysUnicos) {
            const info = sitekeysUnicos[key];

            markdown += "### Site Key #" + contador + "\n\n";
            markdown += "```\n" + key + "\n```\n\n";
            markdown += "- **Tamanho:** " + info.tamanho + " caracteres\n";
            markdown += "- **Status:** " + (info.tamanho === 40 ? "✅ VÁLIDO" : "⚠️ Inválido (esperado 40)") + "\n";
            markdown += "- **Ocorrências:** " + info.ocorrencias.length + "\n\n";

            markdown += "**Locais:**\n\n";
            for (let i = 0; i < info.ocorrencias.length; i++) {
                const ocorrencia = info.ocorrencias[i];
                markdown += "- **Tipo:** `" + ocorrencia.tipo + "`\n";
                markdown += "  - **Contexto:** `" + ocorrencia.contexto + "`\n";
                if (ocorrencia.xpath) {
                    markdown += "  - **XPath:** `" + ocorrencia.xpath + "`\n";
                }
                markdown += "\n";
            }

            markdown += "---\n\n";
            contador++;
        }
    }

    console.log(markdown);
    console.log("");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("✅ ANÁLISE CONCLUÍDA");
    console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("");
    console.log("💾 O markdown acima foi copiado para o console.");
    console.log("   Você pode copiar e colar em um arquivo .md");
    console.log("");
    console.log("📊 Dados completos disponíveis em:");
    console.log("   window.recaptchaResults");
    console.log("");

    // Salvar resultados globalmente para acesso posterior
    window.recaptchaResults = resultados;

    return resultados;
})();
