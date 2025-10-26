# =============================================================================================
# ARQUIVO: control_api.py
# CAMINHO: src/api/control_api.py
# VERSÃO: v1.0
# DESCRIÇÃO:
#   API Flask simples para controle remoto da automação via HTTP
#   Permite retomar/pausar/parar a automação remotamente (email, celular, etc)
# =============================================================================================

import os
import threading
from flask import Flask, jsonify, request, render_template_string
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configurações
API_PORT = int(os.getenv("SERVER_PORT", "6092"))  # Porta 6092 está aberta no AWS
API_HOST = os.getenv("API_HOST", "0.0.0.0")  # 0.0.0.0 = acessível externamente

# Template HTML para página de sucesso
SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Automação Retomada</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 500px;
        }
        .success-icon {
            font-size: 64px;
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
        }
        p {
            color: #666;
            line-height: 1.6;
        }
        .status {
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
        }
        .info {
            font-size: 14px;
            color: #888;
            margin-top: 20px;
        }
        .button {
            display: inline-block;
            margin-top: 20px;
            padding: 12px 24px;
            background-color: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <h1>{{ titulo }}</h1>
        <div class="status">
            <strong>{{ mensagem }}</strong>
        </div>
        <p>{{ descricao }}</p>
        <div class="info">
            <p><strong>Horário:</strong> {{ horario }}</p>
            <p><strong>Status:</strong> {{ status }}</p>
        </div>
        <a href="http://{{ server_ip }}:6080/vnc.html" class="button" target="_blank">
            🖥️ Acessar VNC
        </a>
    </div>
</body>
</html>
"""


class AutomacaoControlAPI:
    """API Flask para controle remoto da automação"""

    def __init__(self, processador_instance):
        """
        Inicializa API de controle

        Args:
            processador_instance: Instância do ProcessadorTitulosAbertosEMarcadosRecompras
        """
        self.processador = processador_instance
        self.app = Flask(__name__)
        self.server_thread = None
        self.running = False

        # Desabilitar logs do Flask (apenas erros)
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        self._configurar_rotas()

    def _configurar_rotas(self):
        """Configura endpoints da API"""

        @self.app.route('/')
        def index():
            """Página inicial da API"""
            return jsonify({
                "api": "PROSPER-ERP-AUTOMATION Control API",
                "version": "1.0",
                "status": "running",
                "endpoints": {
                    "/status": "Status da automação",
                    "/resume": "Retomar execução",
                    "/pause": "Pausar execução",
                    "/stop": "Parar execução",
                    "/health": "Health check"
                }
            })

        @self.app.route('/status')
        def status():
            """Retorna status atual da automação"""
            return jsonify({
                "pausado": self.processador.pausado,
                "parar": self.processador.parar,
                "captcha_errors": self.processador.captcha_errors,
                "estado_atual": self.processador.estado_atual,
                "mensagem_estado": self.processador.mensagem_estado,
                "timestamp": datetime.now().isoformat()
            })

        @self.app.route('/resume')
        def resume():
            """Retoma execução da automação"""
            if self.processador.pausado:
                # Guardar estado antes de retomar
                estado_anterior = self.processador.estado_atual
                mensagem_anterior = self.processador.mensagem_estado

                self.processador.pausado = False
                print(f"\n{'='*80}")
                print(f"[API] ▶️ Execução RETOMADA via API remota")
                print(f"[API] Estado anterior: {estado_anterior}")
                print(f"[API] Mensagem: {mensagem_anterior}")
                print(f"[API] IP do solicitante: {request.remote_addr}")
                print(f"{'='*80}\n")

                return render_template_string(
                    SUCCESS_TEMPLATE,
                    titulo="Automação Retomada!",
                    mensagem=f"A execução foi retomada com sucesso.",
                    descricao=f"A automação continuará de onde parou: {mensagem_anterior if mensagem_anterior else 'processamento normal'}. Você pode acompanhar o progresso pelo VNC.",
                    horario=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status="EXECUTANDO",
                    server_ip=os.getenv("SERVER_IP", "3.148.126.73")
                )
            else:
                return render_template_string(
                    SUCCESS_TEMPLATE,
                    titulo="Automação Já Está Rodando",
                    mensagem="A automação não estava pausada.",
                    descricao="Não foi necessário retomar a execução.",
                    horario=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status="EXECUTANDO",
                    server_ip=os.getenv("SERVER_IP", "3.148.126.73")
                )

        @self.app.route('/pause')
        def pause():
            """Pausa execução da automação"""
            if not self.processador.pausado:
                self.processador.pausado = True
                print(f"\n[API] ⏸️ Execução PAUSADA via API remota")
                print(f"[API] IP do solicitante: {request.remote_addr}")

                return render_template_string(
                    SUCCESS_TEMPLATE,
                    titulo="Automação Pausada",
                    mensagem="A execução foi pausada com sucesso.",
                    descricao="Use o endpoint /resume ou pressione R no terminal para retomar.",
                    horario=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status="PAUSADO",
                    server_ip=os.getenv("SERVER_IP", "3.148.126.73")
                )
            else:
                return render_template_string(
                    SUCCESS_TEMPLATE,
                    titulo="Automação Já Está Pausada",
                    mensagem="A automação já estava pausada.",
                    descricao="Use o botão 'Continuar Automação' para retomar.",
                    horario=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status="PAUSADO",
                    server_ip=os.getenv("SERVER_IP", "3.148.126.73")
                )

        @self.app.route('/stop')
        def stop():
            """Para execução da automação"""
            self.processador.parar = True
            print(f"\n[API] ⏹️ PARADA solicitada via API remota")
            print(f"[API] IP do solicitante: {request.remote_addr}")

            return render_template_string(
                SUCCESS_TEMPLATE,
                titulo="Automação Parada",
                mensagem="A execução será interrompida em breve.",
                descricao="A automação finalizará o processamento atual e encerrará.",
                horario=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status="PARANDO",
                server_ip=os.getenv("SERVER_IP", "3.148.126.73")
            )

        @self.app.route('/health')
        def health():
            """Health check"""
            return jsonify({
                "status": "healthy",
                "api_version": "1.0",
                "timestamp": datetime.now().isoformat()
            })

    def iniciar(self):
        """Inicia servidor API em thread separada"""
        if self.running:
            print("[API] ⚠️ API já está rodando")
            return

        self.running = True

        def run_server():
            self.app.run(
                host=API_HOST,
                port=API_PORT,
                debug=False,
                use_reloader=False,
                threaded=True
            )

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        print(f"\n{'='*80}")
        print(f"[API] ✅ API de Controle Remoto INICIADA")
        print(f"[API] 🌐 Endpoints disponíveis:")
        print(f"[API]    - http://{os.getenv('SERVER_IP', '0.0.0.0')}:{API_PORT}/")
        print(f"[API]    - http://{os.getenv('SERVER_IP', '0.0.0.0')}:{API_PORT}/status")
        print(f"[API]    - http://{os.getenv('SERVER_IP', '0.0.0.0')}:{API_PORT}/resume")
        print(f"[API]    - http://{os.getenv('SERVER_IP', '0.0.0.0')}:{API_PORT}/pause")
        print(f"[API]    - http://{os.getenv('SERVER_IP', '0.0.0.0')}:{API_PORT}/stop")
        print(f"{'='*80}\n")

    def parar(self):
        """Para servidor API"""
        self.running = False
        print("[API] API de controle encerrada")


# Função auxiliar para criar e iniciar API
def iniciar_api_controle(processador_instance):
    """
    Cria e inicia API de controle para o processador

    Args:
        processador_instance: Instância do processador

    Returns:
        AutomacaoControlAPI: Instância da API
    """
    api = AutomacaoControlAPI(processador_instance)
    api.iniciar()
    return api
