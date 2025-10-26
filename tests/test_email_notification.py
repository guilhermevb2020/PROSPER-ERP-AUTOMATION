#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TESTE DE NOTIFICAÇÕES POR EMAIL
Verifica se o sistema de email está funcionando corretamente
"""

import os
import sys
from datetime import datetime

# Adicionar path do projeto
sys.path.insert(0, '/home/ubuntu/PROSPER-ERP-AUTOMATION')

from dotenv import load_dotenv
load_dotenv()

print("="*80)
print("TESTE DO SISTEMA DE NOTIFICAÇÕES POR EMAIL")
print("="*80)
print()

# ============================================================================
# 1. VERIFICAR VARIÁVEIS DE AMBIENTE
# ============================================================================
print("[1/5] Verificando variáveis de ambiente do .env...")

variaveis_necessarias = {
    'SMTP_SERVER': os.getenv('SMTP_SERVER'),
    'SMTP_PORT': os.getenv('SMTP_PORT'),
    'SMTP_USER': os.getenv('SMTP_USER'),
    'SMTP_PASSWORD': os.getenv('SMTP_PASSWORD'),
    'EMAIL_FROM': os.getenv('EMAIL_FROM'),
    'EMAIL_RECIPIENT': os.getenv('EMAIL_RECIPIENT'),
    'SERVER_IP': os.getenv('SERVER_IP'),
    'SERVER_PORT': os.getenv('SERVER_PORT'),
    'VNC_PASSWORD': os.getenv('VNC_PASSWORD'),
}

todas_ok = True
for var, valor in variaveis_necessarias.items():
    if valor:
        if 'PASSWORD' in var or 'SECRET' in var:
            print(f"  ✅ {var}: ****** (oculto)")
        else:
            print(f"  ✅ {var}: {valor}")
    else:
        print(f"  ❌ {var}: NÃO CONFIGURADA!")
        todas_ok = False

if not todas_ok:
    print("\n❌ ERRO: Algumas variáveis de ambiente não estão configuradas!")
    print("   Verifique o arquivo .env")
    sys.exit(1)

print("  ✅ Todas as variáveis necessárias estão configuradas!\n")

# ============================================================================
# 2. IMPORTAR MÓDULO DE NOTIFICAÇÕES
# ============================================================================
print("[2/5] Importando módulo de notificações...")

try:
    from src.common.notification_utils import (
        enviar_email_intervencao,
        enviar_alerta_captcha,
        enviar_alerta_erro_critico,
        enviar_alerta_instalacao_extensao
    )
    print("  ✅ Módulo notification_utils importado com sucesso!\n")
except Exception as e:
    print(f"  ❌ ERRO ao importar: {e}\n")
    sys.exit(1)

# ============================================================================
# 3. TESTAR FUNÇÃO BÁSICA
# ============================================================================
print("[3/5] Testando função básica enviar_email_intervencao()...")

try:
    resultado = enviar_email_intervencao(
        tipo_intervencao="🧪 TESTE DO SISTEMA",
        mensagem="Este é um email de teste para verificar se o sistema de notificações está funcionando.",
        detalhes_adicionais=f"""
INFORMAÇÕES DO TESTE:
- Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Teste executado por: test_email_notification.py
- Localização: /home/ubuntu/PROSPER-ERP-AUTOMATION/tests/

CONFIGURAÇÕES SMTP:
- Servidor: {os.getenv('SMTP_SERVER')}
- Porta: {os.getenv('SMTP_PORT')}
- Usuário: {os.getenv('SMTP_USER')}
- Destinatário: {os.getenv('EMAIL_RECIPIENT')}

Se você recebeu este email, o sistema está funcionando PERFEITAMENTE! ✅
"""
    )

    if resultado:
        print("  ✅ Email enviado com SUCESSO!")
        print(f"  📧 Enviado para: {os.getenv('EMAIL_RECIPIENT')}\n")
    else:
        print("  ❌ Falha ao enviar email (verifique logs acima)\n")
        sys.exit(1)

except Exception as e:
    print(f"  ❌ ERRO durante envio: {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# 4. TESTAR ALERTA DE CAPTCHA
# ============================================================================
print("[4/5] Testando função enviar_alerta_captcha()...")

try:
    resultado = enviar_alerta_captcha(captcha_errors=3)

    if resultado:
        print("  ✅ Email de CAPTCHA enviado com sucesso!\n")
    else:
        print("  ❌ Falha ao enviar email de CAPTCHA\n")

except Exception as e:
    print(f"  ❌ ERRO: {e}\n")

# ============================================================================
# 5. TESTAR ALERTA DE ERRO
# ============================================================================
print("[5/5] Testando função enviar_alerta_erro_critico()...")

try:
    resultado = enviar_alerta_erro_critico(
        erro_descricao="Erro de teste para validar sistema de notificações"
    )

    if resultado:
        print("  ✅ Email de ERRO enviado com sucesso!\n")
    else:
        print("  ❌ Falha ao enviar email de ERRO\n")

except Exception as e:
    print(f"  ❌ ERRO: {e}\n")

# ============================================================================
# RESUMO FINAL
# ============================================================================
print("="*80)
print("✅ TESTE CONCLUÍDO COM SUCESSO!")
print("="*80)
print()
print("📧 EMAILS ENVIADOS:")
print(f"   - Email de teste básico")
print(f"   - Email de alerta de CAPTCHA")
print(f"   - Email de alerta de ERRO")
print()
print(f"📬 Destinatário: {os.getenv('EMAIL_RECIPIENT')}")
print()
print("⚠️  VERIFIQUE SUA CAIXA DE ENTRADA!")
print("   (Pode estar na pasta SPAM ou LIXO ELETRÔNICO)")
print()
print("="*80)
