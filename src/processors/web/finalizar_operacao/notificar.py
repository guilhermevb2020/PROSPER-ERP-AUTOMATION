# -*- coding: utf-8 -*-
"""
notificar.py - avisa o OPERADOR por e-mail quando uma operacao NAO pode ser
finalizada (algum documento sem assinatura ou a forma de pagamento incompleta).

Reusa as credenciais SMTP do prospercredit (C:\\ProsperAI\\code\\email_config.json)
p/ nao duplicar senha em dois lugares. Override por env:
  R7_EMAIL_CONFIG_JSON, R7_SMTP_SERVER/PORT/USER/SENHA/REMETENTE, R7_EMAIL_DESTINO.

Anti-repeticao: nao manda o MESMO aviso (mesma op + mesmas pendencias) duas
vezes no mesmo dia - registro em avisos_enviados.csv.

Uso isolado:
  python finalizar_operacao/notificar.py --teste
"""
import argparse
import csv
import hashlib
import json
import os
import smtplib
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import r7_config as cfg  # noqa: E402

_CABECALHO = ["quando", "op", "hash_pendencias", "n_avisos", "destinatarios"]


# --------------------------------------------------------------------------- #
# Configuracao SMTP
# --------------------------------------------------------------------------- #
def _smtp_config():
    """Le o SMTP do email_config.json do prospercredit; env sobrescreve."""
    base = {}
    try:
        with open(cfg.EMAIL_CONFIG_JSON, encoding="utf-8") as fh:
            base = (json.load(fh) or {}).get("email", {}) or {}
    except Exception as e:
        print(f"  [notificar] nao li {cfg.EMAIL_CONFIG_JSON} ({e}) - uso so as env")
    env = os.environ.get
    return {
        "server": env("R7_SMTP_SERVER", base.get("smtp_server", "")),
        "port": int(env("R7_SMTP_PORT", str(base.get("smtp_port", 465)))),
        "user": env("R7_SMTP_USER", base.get("sender_email", "")),
        "senha": env("R7_SMTP_SENHA", base.get("sender_password", "")),
        "remetente": env("R7_SMTP_REMETENTE", base.get("sender_email", "")),
        "nome": env("R7_SMTP_NOME", base.get("sender_name", "Prosper - Robo 7")),
    }


# --------------------------------------------------------------------------- #
# Controle de reenvio com espacamento DOBRADO
#
# A op que continua pendente e cobrada de novo, cada vez mais espacado:
#   1o aviso na hora -> 2h -> 4h -> 8h -> 16h -> ... ate o teto (24h).
# Se as PENDENCIAS MUDAREM (o operador resolveu uma e sobrou outra), o contador
# ZERA e o aviso sai na hora - e uma cobranca nova, nao repeticao.
# --------------------------------------------------------------------------- #
_FMT = "%Y-%m-%d %H:%M:%S"


def _hash(pendencias):
    return hashlib.sha1("|".join(sorted(pendencias)).encode("utf-8")).hexdigest()[:12]


def _ultimo_aviso(op):
    """Ultima linha registrada p/ a op: (hash, quando: datetime, n_avisos)."""
    ultimo = None
    try:
        with open(cfg.ARQ_AVISOS, encoding="utf-8", newline="") as fh:
            for linha in csv.DictReader(fh, delimiter=";"):
                if str(linha.get("op")) != str(op):
                    continue
                try:
                    quando = datetime.strptime(linha["quando"], _FMT)
                    n = int(linha.get("n_avisos") or 1)
                except Exception:
                    continue
                ultimo = (linha.get("hash_pendencias"), quando, n)
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return ultimo


def espera_minutos(n_avisos):
    """Espacamento ate o proximo reenvio, dobrando a cada aviso ja mandado."""
    minutos = cfg.AVISO_INTERVALO_BASE_MIN * (2 ** max(0, n_avisos - 1))
    return min(minutos, cfg.AVISO_INTERVALO_TETO_H * 60)


def pode_avisar(op, pendencias, agora=None):
    """(pode: bool, motivo: str, n_avisos_anteriores: int)."""
    agora = agora or datetime.now()
    ultimo = _ultimo_aviso(op)
    if ultimo is None:
        return True, "1o aviso", 0
    h_ant, quando, n = ultimo
    if h_ant != _hash(pendencias):
        return True, "pendencias mudaram (contador zerado)", 0
    espera = espera_minutos(n)
    falta = espera - (agora - quando).total_seconds() / 60.0
    if falta <= 0:
        return True, f"reenvio #{n + 1} (espacamento de {espera / 60:.0f}h cumprido)", n
    return False, (f"aguardando espacamento: faltam {falta / 60:.1f}h "
                   f"(aviso #{n} foi {quando.strftime('%d/%m %H:%M')})"), n


def _registrar(op, pendencias, destinatarios, n_anterior):
    novo = not os.path.exists(cfg.ARQ_AVISOS)
    with open(cfg.ARQ_AVISOS, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        if novo:
            w.writerow(_CABECALHO)
        w.writerow([datetime.now().strftime(_FMT), str(op), _hash(pendencias),
                    n_anterior + 1, ",".join(destinatarios)])


# --------------------------------------------------------------------------- #
# Montagem e envio
# --------------------------------------------------------------------------- #
def montar_corpo(op, cedente, pendencias, contexto=None):
    ctx = contexto or {}
    linhas = [
        f"A operacao {op} NAO foi finalizada porque falta o seguinte:",
        "",
    ]
    linhas += [f"  - {p}" for p in pendencias]
    linhas += [
        "",
        "Dados da operacao:",
        f"  Cedente ....... {cedente or '(nao identificado)'}",
        f"  Etapa ......... {ctx.get('etapa', cfg.ROTULO_ETAPA_ENTRADA)}",
    ]
    if ctx.get("valor"):
        linhas.append(f"  Valor ......... {ctx['valor']}")
    if ctx.get("tipos_titulos"):
        linhas.append(f"  Tipos titulos . {', '.join(sorted(set(ctx['tipos_titulos'])))}")
    linhas += [
        "",
        "Resolva os itens acima na tela da operacao. O robo confere de novo no",
        "proximo ciclo e finaliza sozinho quando estiver tudo certo.",
        "",
        "-- ",
        "Robo 7 (finalizar operacao) - ProsperAI",
    ]
    return "\n".join(linhas)


def resumo_das_checagens(detalhes):
    """Texto do MOTIVO: o que foi conferido e por que a op passou.

    detalhes = {"exigidos": [...], "encontrados": {...}, "observacoes": [...],
                "linhas_pagamento": [...], "tipos_titulos": [...]}
    """
    d = detalhes or {}
    linhas = ["DOCUMENTOS (doc2you)"]
    rot = {"aditivo": "Aditivo", "nota_promissoria": "Nota promissoria",
           "duplicata": "Duplicata", "letra_cambio": "Letra de cambio",
           "carta_cessao": "Carta de cessao"}
    enc = d.get("encontrados") or {}
    for canon in (d.get("exigidos") or list(enc)):
        info = enc.get(canon)
        nome = rot.get(canon, canon)
        if info:
            linhas.append(f"  {nome:.<24} {info['assinados']}/{info['total']} assinado(s)")
        else:
            linhas.append(f"  {nome:.<24} (nao encontrado)")
    if d.get("tipos_titulos"):
        linhas.append(f"  exigidos por causa dos titulos: {', '.join(d['tipos_titulos'])}")
    for obs in (d.get("observacoes") or []):
        linhas.append(f"  * {obs}")

    linhas.append("")
    linhas.append("FORMA DE PAGAMENTO")
    for lin in (d.get("linhas_pagamento") or []):
        if len(d.get("linhas_pagamento") or []) > 1:
            linhas.append(f"  -- linha {lin.get('_linha')} --")
        venc = lin.get("vencto") or ""
        venc_br = "-".join(reversed(venc.split("-"))) if venc else "(vazio)"
        linhas += [
            f"  {'Tipo':.<24} {lin.get('tipo') or '(vazio)'}",
            f"  {'Cta. origem':.<24} {lin.get('cta_origem') or '(vazio)'}",
            f"  {'Favorecido':.<24} {lin.get('favorecido') or '(vazio)'}",
            f"  {'CPF/CNPJ':.<24} {lin.get('cpf_cnpj') or '(vazio)'}",
            f"  {'Bco/Ag/Conta':.<24} {lin.get('bco') or '-'} / {lin.get('agencia') or '-'}"
            f" / {lin.get('cc') or '-'} ({lin.get('tipo_conta') or '-'})",
            f"  {'Vencto':.<24} {venc_br} (data de hoje)",
            f"  {'Valor':.<24} {lin.get('valor') or '(vazio)'}",
            f"  {'SP':.<24} {'marcado' if lin.get('sp') == 'SIM' else 'NAO marcado'}",
        ]
    return "\n".join(linhas)


def montar_corpo_finalizada(op, cedente, contexto=None, detalhes=None):
    ctx = contexto or {}
    linhas = [
        f"A operacao {op} foi FINALIZADA pelo Robo 7.",
        "",
        "MOTIVO: as duas verificacoes passaram.",
        "",
        resumo_das_checagens(detalhes),
        "",
        "Dados da operacao:",
        f"  Cedente ....... {cedente or '(nao identificado)'}",
    ]
    if ctx.get("valor"):
        linhas.append(f"  Valor ......... {ctx['valor']}")
    if ctx.get("confirmacao"):
        linhas += ["", f"Confirmacao: {ctx['confirmacao']}"]
    linhas += ["", "-- ", "Robo 7 (finalizar operacao) - ProsperAI"]
    return "\n".join(linhas)


_ROTULO_DOC = {"aditivo": "Aditivo", "nota_promissoria": "Nota promissória",
               "duplicata": "Duplicata", "letra_cambio": "Letra de câmbio",
               "carta_cessao": "Carta de cessão"}


def _data_br(iso):
    """AAAA-MM-DD -> DD/MM/AAAA (o input date do Smart vem em ISO)."""
    if not iso:
        return ""
    p = str(iso).split("-")
    return "/".join(reversed(p)) if len(p) == 3 else str(iso)


def texto_whatsapp_finalizada(op, cedente, contexto=None, detalhes=None):
    """Mensagem de WhatsApp da finalizacao.

    Feita p/ BATER O OLHO E ENTENDER: cada bloco responde uma pergunta - o que
    foi finalizado, os documentos estavam assinados, e para onde o dinheiro vai.

    Cuidado que motivou o formato: mostrar "Aditivo 0/1" assustava, porque 0 de 1
    assinado e o estado NORMAL do aditivo (falta so a Prosper, que assina depois).
    Aqui isso vira "Aditivo OK - faltava so a Prosper", que e o que de fato
    aconteceu. Contagem X/Y so aparece quando ha mais de um documento.
    """
    ctx = contexto or {}
    d = detalhes or {}
    enc = d.get("encontrados") or {}
    exigidos = d.get("exigidos") or list(enc)
    obs_txt = " ".join(d.get("observacoes") or [])
    aditivo_por_excecao = "so a prosper" in _norm_txt(obs_txt)

    linhas = [f"✅ *Operação {op} finalizada*"]
    if cedente:
        linhas.append(f"{cedente}")
    if ctx.get("valor"):
        linhas.append(f"💰 {ctx['valor']}")

    # --- documentos ---
    linhas += ["", "📄 *Documentos* — todos assinados"]
    for canon in exigidos:
        info = enc.get(canon)
        nome = _ROTULO_DOC.get(canon, canon)
        if not info:
            continue
        total = info.get("total", 0)
        quantos = f" ({total})" if total > 1 else ""
        nota = ""
        if canon == "aditivo" and info.get("assinados", 0) < total and aditivo_por_excecao:
            nota = " — faltava só a Prosper"
        linhas.append(f"  • {nome}{quantos} ✓{nota}")

    # --- pagamento: CONFIRMACAO do que foi checado, nao despejo de campos ---
    # Se a op chegou aqui, cada regra passou. Entao a mensagem confirma as
    # regras (e o que o operador quer saber) em vez de listar banco/ag/conta,
    # que ele nao vai conferir no celular.
    pagamentos = d.get("linhas_pagamento") or []
    for i, lin in enumerate(pagamentos, 1):
        titulo = "🏦 *Pagamento*" if len(pagamentos) == 1 else f"🏦 *Pagamento {i}/{len(pagamentos)}*"
        # o valor ja aparece no topo; aqui so quando ha VARIAS linhas de
        # pagamento, em que saber quanto vai em cada uma faz diferenca.
        valor = f" — {lin['valor']}" if (lin.get("valor") and len(pagamentos) > 1) else ""
        linhas += ["", f"{titulo}{valor}"]
        linhas.append(f"  • {lin.get('tipo') or 'PIX'} selecionado ✓")
        linhas.append(f"  • Origem: {lin.get('cta_origem') or '?'} ✓")
        favorecido = (lin.get("favorecido") or "?").strip()
        if len(favorecido) > 30:
            favorecido = favorecido[:29].rstrip() + "…"
        linhas.append(f"  • Favorecido: {favorecido}")
        linhas.append("  • Dados bancários completos ✓")
        linhas.append(f"  • SP {'marcado ✓' if lin.get('sp') == 'SIM' else 'NÃO marcado'}")
        linhas.append("  • Vencimento hoje ✓")

    linhas += ["", f"_{datetime.now():%d/%m %H:%M} · Robô 7_"]
    return "\n".join(linhas)


def _norm_txt(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def enviar_finalizada(op, cedente, contexto=None, detalhes=None, destinatarios=None):
    """E-mail avisando que a op FOI finalizada, com o motivo. -> (ok, motivo)."""
    destinatarios = destinatarios or cfg.EMAIL_DESTINO_FINALIZACAO
    if not (cfg.EMAIL_ATIVO and cfg.AVISAR_FINALIZACAO and cfg.EMAIL_FINALIZACAO_ATIVO):
        return False, "e-mail de finalizacao desligado (R7_EMAIL_FINALIZACAO=0)"
    smtp = _smtp_config()
    if not (smtp["server"] and smtp["user"] and smtp["senha"]):
        return False, f"SMTP incompleto em {cfg.EMAIL_CONFIG_JSON}"

    corpo = montar_corpo_finalizada(op, cedente, contexto, detalhes)
    msg = MIMEMultipart()
    msg["From"] = f"{smtp['nome']} <{smtp['remetente']}>"
    msg["To"] = ", ".join(destinatarios)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = f"[Robo 7] Operacao {op} FINALIZADA - {cedente or ''}".strip()
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    try:
        if smtp["port"] == 465:
            srv = smtplib.SMTP_SSL(smtp["server"], smtp["port"], timeout=30)
        else:
            srv = smtplib.SMTP(smtp["server"], smtp["port"], timeout=30)
            srv.starttls()
        with srv:
            srv.login(smtp["user"], smtp["senha"])
            srv.sendmail(smtp["remetente"], destinatarios, msg.as_string())
    except Exception as e:
        return False, f"falha SMTP: {e}"
    return True, "ok"


def enviar(op, cedente, pendencias, contexto=None, destinatarios=None, forcar=False,
           prefixo_assunto=""):
    """Manda o aviso. Retorna (enviado: bool, motivo: str)."""
    destinatarios = destinatarios or cfg.EMAIL_DESTINO
    if not pendencias:
        return False, "sem pendencias"
    if not cfg.EMAIL_ATIVO:
        print(f"  [notificar] EMAIL DESLIGADO (R7_EMAIL_ATIVO=0) - aviso da op {op} nao enviado")
        return False, "email desligado"

    n_anterior = 0
    if forcar:
        motivo_envio = "forcado"
    else:
        pode, motivo_envio, n_anterior = pode_avisar(op, pendencias)
        if not pode:
            return False, motivo_envio

    smtp = _smtp_config()
    if not (smtp["server"] and smtp["user"] and smtp["senha"]):
        return False, f"SMTP incompleto (server/user/senha) em {cfg.EMAIL_CONFIG_JSON}"

    corpo = montar_corpo(op, cedente, pendencias, contexto)
    msg = MIMEMultipart()
    msg["From"] = f"{smtp['nome']} <{smtp['remetente']}>"
    msg["To"] = ", ".join(destinatarios)
    msg["Date"] = formatdate(localtime=True)
    reforco = f" (cobranca #{n_anterior + 1})" if n_anterior else ""
    msg["Subject"] = (f"{prefixo_assunto}[Robo 7] Operacao {op} NAO finalizada - "
                      f"{len(pendencias)} pendencia(s){reforco}")
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    try:
        if smtp["port"] == 465:
            srv = smtplib.SMTP_SSL(smtp["server"], smtp["port"], timeout=30)
        else:
            srv = smtplib.SMTP(smtp["server"], smtp["port"], timeout=30)
            srv.starttls()
        with srv:
            srv.login(smtp["user"], smtp["senha"])
            srv.sendmail(smtp["remetente"], destinatarios, msg.as_string())
    except Exception as e:
        return False, f"falha SMTP: {e}"

    _registrar(op, pendencias, destinatarios, n_anterior)
    proxima = espera_minutos(n_anterior + 1) / 60.0
    print(f"  [notificar] aviso da op {op} enviado p/ {', '.join(destinatarios)} "
          f"({motivo_envio}; se continuar pendente, cobra de novo em {proxima:.0f}h)")
    return True, "ok"


def main():
    ap = argparse.ArgumentParser(description="Envia (ou simula) o aviso de pendencia do Robo 7.")
    ap.add_argument("--teste", action="store_true", help="manda um e-mail de teste")
    ap.add_argument("--op", default="00000")
    ap.add_argument("--para", default="", help="destinatario(s) separados por virgula")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    smtp = _smtp_config()
    print(f"SMTP: {smtp['server']}:{smtp['port']} como {smtp['user']} "
          f"(senha {'OK' if smtp['senha'] else 'FALTANDO'})")
    print(f"Destino padrao: {cfg.EMAIL_DESTINO}")
    if not args.teste:
        print("\n(use --teste para enviar um e-mail de verdade)")
        return 0

    destino = [e.strip() for e in args.para.split(",") if e.strip()] or cfg.EMAIL_DESTINO
    pend = ["Aditivo: falta assinatura de terceiro(s) -> GIGA PAPER COMERCIO (Pendente)",
            "Pagamento: campo 'Favorecido' esta vazio",
            "Pagamento: Vencto = 27/08/2026, deveria ser a data de hoje"]
    ok, motivo = enviar(args.op, "CEDENTE DE TESTE", pend,
                        {"valor": "R$ 3.537,26", "tipos_titulos": ["DUR"]},
                        destino, forcar=True, prefixo_assunto="[TESTE] ")
    print(f">> enviado={ok} | {motivo}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
