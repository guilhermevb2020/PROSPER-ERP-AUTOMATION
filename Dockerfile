FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema + Chrome para Selenium/Nodriver
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    gnupg \
    wget \
    unzip \
    # Dependências do Chrome
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    fonts-liberation \
    xdg-utils \
    # Para Playwright
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libcups2 \
    libxfixes3 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Instalar Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Stack de display virtual + acesso remoto para login manual (reCAPTCHA, etc.)
#   Xvfb     -> display virtual
#   fluxbox  -> window manager leve (Chrome precisa de WM pra abrir corretamente)
#   x11vnc   -> servidor VNC (porta 5900)
#   novnc    -> bridge HTTP/WebSocket -> VNC (porta 6080, acessivel pelo navegador)
#   websockify -> usado pelo novnc
RUN apt-get update \
    && apt-get install -y \
        xvfb \
        x11vnc \
        fluxbox \
        novnc \
        websockify \
        net-tools \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Instalar Claude Code CLI (conferência IA do robô de análise de crédito - V3).
# Instalador nativo (binário self-contained, não precisa de npm); symlink p/ o PATH.
# A AUTENTICAÇÃO (credenciais) NÃO é baixada aqui (segredo não vai pra imagem):
# rodar `claude setup-token` no container e montar /root/.claude como volume p/
# persistir entre rebuilds (igual config/nextcloud.env).
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && ln -sf /root/.local/bin/claude /usr/local/bin/claude

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# certutil: o Chrome usa a base NSS, nao o SSL_CERT_FILE do OpenSSL. Sem isto nao ha como
# ensina-lo a confiar na CA do access-guardian, e o tunel HTTPS do guardian quebraria toda
# navegacao. Quem instala a CA e o scripts/boot_vnc.sh, na partida do container.
# Fica ANTES do `COPY . .` de proposito: assim o cache da imagem sobrevive a cada mudanca
# de codigo, e este apt-get nao roda de novo.
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends libnss3-tools \
    && rm -rf /var/lib/apt/lists/*

# Copiar código da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/data/downloads_api /app/data/processed /app/temp /app/data/screenshots

# Variáveis de ambiente
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV PYTHONPATH=/app

# Comando padrão (API de controle)
CMD ["python", "-m", "src.api.control_api_titulos"]
