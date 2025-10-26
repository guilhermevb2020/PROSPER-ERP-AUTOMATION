# =============================================================================================
# ARQUIVO: notification_utils.py
# CAMINHO: src/common/notification_utils.py
# VERSÃO: v1.0
# DESCRIÇÃO:
#   Utilitários para envio de notificações por email quando automação precisa de intervenção
# =============================================================================================

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configurações SMTP do .env
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.mailersend.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "2525"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", "prosperito@prosperfidc.online")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "guilherme@prosperinvest.com.br")

# IP/URL do servidor (para links VNC e API)
SERVER_IP = os.getenv("SERVER_IP", "3.148.126.73")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))

# Senha VNC do .env
VNC_PASSWORD = os.getenv("VNC_PASSWORD", "vetor2025")


def enviar_email_intervencao(
    tipo_intervencao: str,
    mensagem: str,
    vnc_url: str = None,
    api_resume_url: str = None,
    detalhes_adicionais: str = None
) -> bool:
    """
    Envia email solicitando intervenção humana na automação

    Args:
        tipo_intervencao: Tipo de intervenção ("CAPTCHA", "ERRO", "VALIDACAO", etc)
        mensagem: Mensagem descritiva do problema
        vnc_url: URL do VNC (padrão: http://{SERVER_IP}:6080/vnc.html)
        api_resume_url: URL da API para continuar (padrão: http://{SERVER_IP}:{SERVER_PORT}/resume)
        detalhes_adicionais: Detalhes extras (opcional)

    Returns:
        bool: True se enviado com sucesso, False caso contrário
    """

    # URLs padrão se não fornecidas
    if not vnc_url:
        vnc_url = f"http://{SERVER_IP}:6080/vnc.html"
    if not api_resume_url:
        api_resume_url = f"http://{SERVER_IP}:{SERVER_PORT}/resume"

    # Timestamp
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Template HTML do email
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
            margin: -30px -30px 20px -30px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .alert-badge {{
            display: inline-block;
            background-color: #ff6b6b;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            margin-top: 8px;
        }}
        .message-box {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .message-box h2 {{
            margin-top: 0;
            color: #856404;
            font-size: 18px;
        }}
        .message-box p {{
            margin: 10px 0 0 0;
            color: #856404;
        }}
        .details {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }}
        .button-container {{
            text-align: center;
            margin: 30px 0;
        }}
        .button {{
            display: inline-block;
            padding: 14px 32px;
            margin: 10px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
            font-size: 16px;
            transition: all 0.3s ease;
        }}
        .button-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .button-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        }}
        .button-secondary {{
            background-color: #6c757d;
            color: white;
        }}
        .button-secondary:hover {{
            background-color: #5a6268;
        }}
        .instructions {{
            background-color: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .instructions h3 {{
            margin-top: 0;
            color: #1976D2;
            font-size: 16px;
        }}
        .instructions ol {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .instructions li {{
            margin: 8px 0;
            color: #1976D2;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            color: #666;
            font-size: 13px;
        }}
        .info-row {{
            margin: 10px 0;
            padding: 8px 12px;
            background-color: #f8f9fa;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
        }}
        .info-label {{
            font-weight: bold;
            color: #495057;
        }}
        .info-value {{
            color: #6c757d;
        }}
        @media only screen and (max-width: 600px) {{
            body {{
                padding: 10px;
            }}
            .container {{
                padding: 15px;
            }}
            .button {{
                display: block;
                margin: 10px 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Automação PROSPER ERP</h1>
            <span class="alert-badge">⚠️ INTERVENÇÃO NECESSÁRIA</span>
        </div>

        <div class="message-box">
            <h2>{tipo_intervencao}</h2>
            <p>{mensagem}</p>
        </div>

        <div class="info-row">
            <span class="info-label">Data/Hora:</span>
            <span class="info-value">{agora}</span>
        </div>

        <div class="info-row">
            <span class="info-label">Servidor:</span>
            <span class="info-value">{SERVER_IP}</span>
        </div>

        <div class="info-row">
            <span class="info-label">Processador:</span>
            <span class="info-value">titulos_abertos_e_marcados_recompras</span>
        </div>

        {f'<div class="details"><strong>Detalhes:</strong><br>{detalhes_adicionais}</div>' if detalhes_adicionais else ''}

        <div class="instructions">
            <h3>📋 Como Resolver:</h3>
            <ol>
                <li><strong>Acesse o VNC</strong> clicando no botão abaixo (senha: <code>{VNC_PASSWORD}</code>)</li>
                <li><strong>Resolva o problema</strong> manualmente no navegador Chrome</li>
                <li><strong>Clique em "Continuar Automação"</strong> para retomar a execução</li>
            </ol>
        </div>

        <div class="button-container">
            <a href="{vnc_url}" class="button button-secondary" target="_blank">
                🖥️ Acessar VNC
            </a>
            <a href="{api_resume_url}" class="button button-primary" target="_blank">
                ▶️ Continuar Automação
            </a>
        </div>

        <div class="footer">
            <p><strong>Dica:</strong> Você pode acessar de qualquer dispositivo (celular, tablet, PC)</p>
            <p>PROSPER-ERP-AUTOMATION • Versão 26.0</p>
            <p>Este é um email automático. Não responda.</p>
        </div>
    </div>
</body>
</html>
"""

    # Versão texto simples (fallback)
    text_content = f"""
AUTOMAÇÃO PROSPER ERP - INTERVENÇÃO NECESSÁRIA

{tipo_intervencao}

{mensagem}

Data/Hora: {agora}
Servidor: {SERVER_IP}

COMO RESOLVER:
1. Acesse o VNC: {vnc_url}
   Senha: {VNC_PASSWORD}

2. Resolva o problema manualmente no Chrome

3. Clique no link para continuar:
   {api_resume_url}

{f'Detalhes: {detalhes_adicionais}' if detalhes_adicionais else ''}

---
PROSPER-ERP-AUTOMATION
Este é um email automático. Não responda.
"""

    try:
        # Criar mensagem
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"⚠️ Automação PROSPER - {tipo_intervencao}"
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_RECIPIENT

        # Anexar versões texto e HTML
        part1 = MIMEText(text_content, 'plain', 'utf-8')
        part2 = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(part1)
        msg.attach(part2)

        # Conectar e enviar
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[EMAIL] ✅ Email enviado para {EMAIL_RECIPIENT}")
        return True

    except Exception as e:
        print(f"[EMAIL] ❌ Erro ao enviar email: {e}")
        return False


def enviar_alerta_captcha(captcha_errors: int = 0) -> bool:
    """
    Envia email específico para timeout de CAPTCHA

    Args:
        captcha_errors: Número de erros de CAPTCHA consecutivos

    Returns:
        bool: True se enviado com sucesso
    """
    detalhes = f"Tentativas de resolução automática: {captcha_errors}\n"
    detalhes += "A extensão CapSolver não conseguiu resolver o CAPTCHA em 60 segundos."

    return enviar_email_intervencao(
        tipo_intervencao="🔒 CAPTCHA NÃO RESOLVIDO",
        mensagem="O sistema detectou um CAPTCHA que precisa de resolução manual.",
        detalhes_adicionais=detalhes
    )


def enviar_alerta_erro_critico(erro_descricao: str) -> bool:
    """
    Envia email para erro crítico que requer intervenção

    Args:
        erro_descricao: Descrição do erro

    Returns:
        bool: True se enviado com sucesso
    """
    return enviar_email_intervencao(
        tipo_intervencao="❌ ERRO CRÍTICO",
        mensagem="A automação encontrou um erro que requer intervenção manual.",
        detalhes_adicionais=erro_descricao
    )


def enviar_alerta_instalacao_extensao(capsolver_api_key: str) -> bool:
    """
    Envia email solicitando instalação da extensão CapSolver

    Args:
        capsolver_api_key: API Key da CapSolver

    Returns:
        bool: True se enviado com sucesso
    """
    detalhes = f"""
PASSO A PASSO:

1. Acesse o VNC (clique no botão abaixo)
2. No Chrome que está aberto, clique em "Usar no Chrome"
3. Confirme a instalação da extensão
4. Configure a API Key da CapSolver:
   {capsolver_api_key}
5. Ative "Auto Solve" na extensão
6. Clique em "Continuar Automação" no email

A extensão CapSolver resolve CAPTCHAs automaticamente durante a automação.
"""

    return enviar_email_intervencao(
        tipo_intervencao="🔌 INSTALAÇÃO NECESSÁRIA - Extensão CapSolver",
        mensagem="A automação está aguardando a instalação da extensão CapSolver no Chrome.",
        detalhes_adicionais=detalhes
    )


def enviar_alerta_login_sucesso(
    nome_processador: str = "titulos_abertos_e_marcados_recompras",
    vnc_port: int = 6080,
    descricao_processador: str = "Títulos Abertos e Marcados para Recompra"
) -> bool:
    """
    Envia email informando que o login foi realizado com sucesso
    e a automação está rodando em loop infinito

    Args:
        nome_processador: Nome técnico do processador (ex: "titulos_abertos")
        vnc_port: Porta VNC do processador (ex: 6080 para display :1, 6081 para display :2)
        descricao_processador: Descrição amigável do processador

    Returns:
        bool: True se enviado com sucesso
    """
    vnc_url = f"http://{SERVER_IP}:{vnc_port}/vnc.html"
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Template HTML do email de sucesso
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
            margin: -30px -30px 20px -30px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .success-badge {{
            display: inline-block;
            background-color: #28a745;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            margin-top: 8px;
        }}
        .message-box {{
            background-color: #d4edda;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .message-box h2 {{
            margin-top: 0;
            color: #155724;
            font-size: 18px;
        }}
        .message-box p {{
            margin: 10px 0 0 0;
            color: #155724;
        }}
        .info-box {{
            background-color: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .info-box h3 {{
            margin-top: 0;
            color: #1976D2;
            font-size: 16px;
        }}
        .info-box ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .info-box li {{
            margin: 8px 0;
            color: #1976D2;
        }}
        .button-container {{
            text-align: center;
            margin: 30px 0;
        }}
        .button {{
            display: inline-block;
            padding: 14px 32px;
            margin: 10px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
            font-size: 16px;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%);
            color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        }}
        .info-row {{
            margin: 10px 0;
            padding: 8px 12px;
            background-color: #f8f9fa;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
        }}
        .info-label {{
            font-weight: bold;
            color: #495057;
        }}
        .info-value {{
            color: #6c757d;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            color: #666;
            font-size: 13px;
        }}
        @media only screen and (max-width: 600px) {{
            body {{
                padding: 10px;
            }}
            .container {{
                padding: 15px;
            }}
            .button {{
                display: block;
                margin: 10px 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Automação PROSPER ERP</h1>
            <span class="success-badge">✅ SISTEMA ATIVO</span>
        </div>

        <div class="message-box">
            <h2>✅ {descricao_processador} - Login Realizado!</h2>
            <p>A automação está funcionando 100% automaticamente em loop contínuo.</p>
        </div>

        <div class="info-row">
            <span class="info-label">Data/Hora:</span>
            <span class="info-value">{agora}</span>
        </div>

        <div class="info-row">
            <span class="info-label">Servidor:</span>
            <span class="info-value">{SERVER_IP}</span>
        </div>

        <div class="info-row">
            <span class="info-label">Processador:</span>
            <span class="info-value">{nome_processador}</span>
        </div>

        <div class="info-row">
            <span class="info-label">VNC:</span>
            <span class="info-value">Porta {vnc_port}</span>
        </div>

        <div class="info-row">
            <span class="info-label">Status:</span>
            <span class="info-value">🟢 Executando em loop infinito</span>
        </div>

        <div class="info-box">
            <h3>🔄 O que a automação está fazendo:</h3>
            <ul>
                <li>✅ Extração automática de CSVs a cada 60 segundos</li>
                <li>✅ Resolução automática de CAPTCHAs (via API CapSolver)</li>
                <li>✅ Títulos abertos marcados para recompra</li>
                <li>✅ Todos os títulos abertos</li>
            </ul>
        </div>

        <div class="info-box">
            <h3>📧 Próximos emails:</h3>
            <ul>
                <li>Você receberá emails <strong>SOMENTE</strong> em caso de erro ou problema</li>
                <li>Enquanto tudo funcionar, não haverá mais notificações</li>
                <li>Você pode monitorar via VNC clicando no botão abaixo</li>
            </ul>
        </div>

        <div class="button-container">
            <a href="{vnc_url}" class="button" target="_blank">
                🖥️ Abrir Automação Rodando
            </a>
        </div>

        <div class="footer">
            <p><strong>Dica:</strong> Clique no botão acima e veja a automação rodando ao vivo (abre direto, sem senha)</p>
            <p>PROSPER-ERP-AUTOMATION • Versão 27.0</p>
            <p>Este é um email automático. Não responda.</p>
        </div>
    </div>
</body>
</html>
"""

    # Versão texto simples (fallback)
    text_content = f"""
AUTOMAÇÃO PROSPER ERP - {descricao_processador.upper()}

✅ Login realizado! A automação está funcionando 100% automaticamente!

Data/Hora: {agora}
Servidor: {SERVER_IP}
Processador: {nome_processador}
VNC: Porta {vnc_port}
Status: Executando em loop infinito

O QUE ESTÁ RODANDO:
- Extração automática de CSVs a cada 60 segundos
- Resolução automática de CAPTCHAs
- Títulos abertos marcados para recompra
- Todos os títulos abertos

PRÓXIMOS EMAILS:
Você receberá emails SOMENTE em caso de erro ou problema.
Enquanto tudo funcionar, não haverá mais notificações.

MONITORAMENTO:
Acesse o VNC para visualizar: {vnc_url}
(Abre direto, sem senha)

---
PROSPER-ERP-AUTOMATION
Este é um email automático. Não responda.
"""

    try:
        # Criar mensagem
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"✅ PROSPER - {descricao_processador} - Sistema Ativo"
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_RECIPIENT

        # Anexar versões texto e HTML
        part1 = MIMEText(text_content, 'plain', 'utf-8')
        part2 = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(part1)
        msg.attach(part2)

        # Conectar e enviar
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[EMAIL] ✅ Email de login bem-sucedido enviado para {EMAIL_RECIPIENT}")
        return True

    except Exception as e:
        print(f"[EMAIL] ❌ Erro ao enviar email de sucesso: {e}")
        return False


def testar_envio_email():
    """Testa envio de email"""
    print("Testando envio de email...")
    resultado = enviar_email_intervencao(
        tipo_intervencao="🧪 TESTE",
        mensagem="Este é um email de teste do sistema de notificações.",
        detalhes_adicionais="Se você recebeu este email, o sistema está funcionando corretamente!"
    )

    if resultado:
        print("✅ Teste enviado com sucesso!")
    else:
        print("❌ Falha no teste")

    return resultado


if __name__ == "__main__":
    # Testar módulo
    testar_envio_email()
