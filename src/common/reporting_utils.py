# -*- coding: utf-8 -*-
# =============================================================================================
# ARQUIVO: reporting_utils.py
# CAMINHO: src/common/reporting_utils.py
# VERSÃO: v2.2 (correção bug cast, robustez email)
# AUTOR: ChatGPT
# DATA: 2025-05-20
# DESCRIÇÃO:
#   - Registra status finais (sucesso ou falha) em arquivos CSV
#   - Envia e-mail em caso de falha crítica, com corpo HTML, imagens e anexo de log
#   - Cast seguro e tratamento robusto de campos None ou inválidos
# =============================================================================================

# =============================================================================================
# 1.0 IMPORTAÇÕES
# =============================================================================================


import os
import smtplib
import pandas as pd
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage
from email.utils import make_msgid
from email.mime.image import MIMEImage
from src.common.timezone_utils import formatted_now_br
from src.core.logging_config import get_logger # Importa para usar o logger aqui também

# Inicializa o logger para este módulo
logger = get_logger(__name__)

# =============================================================================================
# 2.0 DEFINIÇÃO DE CAMINHOS
# =============================================================================================
PROJECT_ROOT = Path(__file__).resolve()
while PROJECT_ROOT.name not in ["PROSPER-ERP-AUTOMATION", "PROSPER_DATA_HUB"]:
    if PROJECT_ROOT.parent == PROJECT_ROOT:
        raise RuntimeError("Não encontrou a pasta raiz do projeto ('PROSPER-ERP-AUTOMATION').")
    PROJECT_ROOT = PROJECT_ROOT.parent

ASSETS_EMAIL = PROJECT_ROOT / "assets" / "email"
LOGO_PATH = ASSETS_EMAIL / "logo_prosper.png"
MASCOTE_PATH = ASSETS_EMAIL / "prosperito.png"

# =============================================================================================
# 2.1 FUNÇÃO AUXILIAR: CAST INT ROBUSTO
# =============================================================================================
def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

# =============================================================================================
# 3.0 FUNÇÃO: ENVIA E-MAIL DE FALHA COM ANEXO E IMAGENS
# =============================================================================================
def enviar_email_falha(assunto: str, corpo: str, caminho_csv: str) -> None:
    try:
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = os.getenv("EMAIL_FROM")
        msg["To"] = os.getenv("EMAIL_RECIPIENT")
        msg.set_content("Falha técnica detectada. Consulte o anexo.")

        # IDs embutidos para imagens inline
        cid_logo = make_msgid(domain="prosper.com.br")
        cid_mascote = make_msgid(domain="prosper.com.br")

        # Corpo HTML
        corpo_seguro = str(corpo or "Erro não especificado.").strip()
        html = f"""
        <html>
          <body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
            <div style="background:#ffffff;padding:25px;border-radius:10px;border:1px solid #ccc;">
              <img src="cid:logo_prosper" alt="Prosper" style="height:40px;margin-bottom:15px;" />
              <h2 style="color:#1c8cc7;">🚨 Alerta de Falha - Processo Automático</h2>
              <p style="font-size:16px;">Olá, humano amigo. ⚠️</p>
              <p style="font-size:15px;">O processo <b>{assunto.replace('[ERRO] ', '')}</b> apresentou uma falha crítica durante sua execução.</p>
              <p style="font-size:14px;color:#444;margin-top:15px;"><b>Detalhes técnicos:</b><br>
              <code style="color:#c7254e;background:#f9f2f4;padding:4px;border-radius:4px;font-size:13px;">{corpo_seguro}</code></p>
              <p style="font-size:13px;margin-top:25px;">📎 Em anexo está o log técnico da falha com data, status, descrição e duração.</p>
              <p style="font-size:13px;color:#888;margin-top:10px;">
                Prosperito está analisando os circuitos... 🤖🔧<br><br>
                <img src="cid:prosperito" alt="Prosperito" style="height:60px;margin-top:10px;" />
              </p>
            </div>
          </body>
        </html>
        """
        msg.add_alternative(html, subtype="html")

        # Anexo do CSV
        if os.path.exists(caminho_csv):
            with open(caminho_csv, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype="text",
                    subtype="csv",
                    filename=os.path.basename(caminho_csv)
                )

        # Embed das imagens no HTML
        if LOGO_PATH.exists():
            try:
                with open(LOGO_PATH, "rb") as img:
                    img_data = img.read()
                    image = MIMEImage(img_data, name="logo_prosper.png")
                    image.add_header('Content-ID', '<logo_prosper>')
                    image.add_header('Content-Disposition', 'inline', filename="logo_prosper.png")
                    msg.attach(image)
                logger.info(f"Logotipo anexado com sucesso. Caminho: {LOGO_PATH}")
            except Exception as e:
                logger.error(f"Falha ao anexar logotipo: {e}")
        else:
            logger.warning(f"Logotipo não encontrado no caminho: {LOGO_PATH}")

        if MASCOTE_PATH.exists():
            try:
                with open(MASCOTE_PATH, "rb") as img:
                    img_data = img.read()
                    image = MIMEImage(img_data, name="prosperito.png")
                    image.add_header('Content-ID', '<prosperito>')
                    image.add_header('Content-Disposition', 'inline', filename="prosperito.png")
                    msg.attach(image)
                logger.info(f"Mascote anexado com sucesso. Caminho: {MASCOTE_PATH}")
            except Exception as e:
                logger.error(f"Falha ao anexar mascote: {e}")
        else:
            logger.warning(f"Mascote não encontrado no caminho: {MASCOTE_PATH}")

        # Envio via SMTP autenticado
        try:
            with smtplib.SMTP(os.getenv("SMTP_SERVER"), safe_int(os.getenv("SMTP_PORT"), 587)) as smtp:
                smtp.starttls()
                smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
                smtp.send_message(msg)
                logger.info("E-mail enviado com sucesso.")
        except Exception as e:
            logger.error(f"Falha ao enviar e-mail automático: {e}")

    except Exception as e:
        logger.critical(f"Erro inesperado na função enviar_email_falha: {e}")

# =============================================================================================
# 4.0 FUNÇÃO: REGISTRA STATUS FINAL E DISPARA ALERTA SE FALHAR (ROBUSTA)
# =============================================================================================
def log_final_status(modulo: str, resultado_dict: dict) -> None:
    """
    Registra o status final de um módulo em um arquivo CSV e envia alerta por e-mail em caso de falha.

    Parâmetros:
    ----------
    modulo : str
        O nome do módulo executado.
    resultado_dict : dict
        Dicionário contendo 'success' (bool), 'mensagem' (str) e, opcionalmente, 'duracao_segundos' (numérico).
    """
    # Garante que resultado_dict é um dicionário antes de usar .get()
    if not isinstance(resultado_dict, dict):
        logger.error(f"log_final_status: Tipo de 'resultado_dict' inesperado: {type(resultado_dict)}. Esperava dict.")
        resultado_dict = {"success": False, "mensagem": "Erro interno: resultado_dict inválido"}

    status = "OK" if resultado_dict.get("success") else "F"
    mensagem = str(resultado_dict.get("mensagem", "")).strip()
    hoje = datetime.now().strftime("%Y-%m")
    caminho_csv = PROJECT_ROOT / "logs" / f"imports_{hoje}.csv"

    # Cast robusto para duração
    duracao_val = resultado_dict.get("duracao_segundos")
    duracao_segundos = safe_int(duracao_val, 0)

    linha = {
        "data_hora": formatted_now_br(),
        "modulo": modulo,
        "status": status,
        "mensagem": mensagem,
        "duracao": duracao_segundos
    }

    df = pd.DataFrame([linha])
    header = not caminho_csv.exists()
    df.to_csv(caminho_csv, mode="a", header=header, index=False)

    if resultado_dict.get("success") is False:
        assunto = f"[ERRO] Falha no processo: {modulo}"
        enviar_email_falha(assunto, mensagem, str(caminho_csv))

# =============================================================================================
# 5.0 FIM DO ARQUIVO
# =============================================================================================
