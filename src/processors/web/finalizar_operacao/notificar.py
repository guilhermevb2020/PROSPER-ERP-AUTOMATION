# -*- coding: utf-8 -*-
"""
notificar.py - os AVISOS do Robo 7 (finalizar operacao): quem fica sabendo do que.

  op FINALIZADA pelo robo          -> WhatsApp (texto_whatsapp_finalizada; quem envia e o
                                      notificar_whatsapp). Ha tambem um e-mail de
                                      finalizacao, desligado (R7_EMAIL_FINALIZACAO=0).
  documentos assinados, mas o      -> WhatsApp e/ou e-mail (avisar_pagamento_pendente):
  PAGAMENTO impede a finalizacao      so o operador corrige a grade PIX, e enquanto ele
                                      nao corrige o dinheiro nao sai. E o unico aviso de
                                      pendencia; exige --avisar no comando. Canais em
                                      R7_AVISO_PENDENCIA_CANAIS, cada um com a sua chave.
  esperando ASSINATURA             -> nenhum aviso: e o estado normal da etapa (horas ou
                                      dias), e cobrar o operador por isso so gera ruido.

E-mail: broker SMTP do Access Guardian (SMTP_SERVER/SMTP_PORT, SMTP_PASSWORD vazia de
proposito; ele repassa ao MailerSend), remetente EMAIL_FROM. Ate 22/09/2026 este modulo
lia a senha de um email_config.json da maquina Windows de origem, que nao existe no
servidor: nenhum aviso por e-mail tinha saido daqui. Em 22/09 o broker aceitou a conversa
mas o servidor de saida recusou (451): o e-mail fica DESLIGADO (R7_EMAIL_ATIVO=0) ate a
Gerencia consertar o relay ou dar ao erp a API HTTP do MailerSend. WhatsApp: Evolution,
o mesmo canal das finalizacoes (notificar_whatsapp).

Anti-repeticao: a mesma op com as MESMAS pendencias e cobrada de novo cada vez mais
espacado (na hora, 2h, 4h, ... ate 1x/dia); pendencias diferentes zeram o contador.
Registro em avisos_enviados.csv; o finalizador grava cada envio como evento
aviso_enviado no banco.

Uso isolado (mostra o SMTP; com --teste manda UM e-mail para R7_EMAIL_TESTE):
  python finalizar_operacao/notificar.py --teste [--para endereco]
"""
import argparse
import csv
import hashlib
import os
import re
import smtplib
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import notificar_whatsapp  # noqa: E402
import r7_config as cfg  # noqa: E402

_CABECALHO = ["quando", "op", "hash_pendencias", "n_avisos", "destinatarios"]


# --------------------------------------------------------------------------- #
# Configuracao SMTP
# --------------------------------------------------------------------------- #
def _smtp_config():
    """Broker SMTP do Access Guardian: servidor, porta e remetente do ambiente, senha
    vazia (o broker reconhece o container e fala com o MailerSend). R7_SMTP_* sobrescreve."""
    env = os.environ.get
    return {
        "server": env("R7_SMTP_SERVER") or env("SMTP_SERVER", ""),
        "port": int(env("R7_SMTP_PORT") or env("SMTP_PORT") or 2525),
        "user": env("R7_SMTP_USER") or env("SMTP_USER", ""),
        "senha": env("R7_SMTP_SENHA") or env("SMTP_PASSWORD", ""),
        "remetente": env("R7_SMTP_REMETENTE") or env("EMAIL_FROM", ""),
        "nome": env("R7_SMTP_NOME", "Robo 7 - Prospere"),
        "starttls": env("R7_SMTP_STARTTLS", "0").strip().lower() in ("1", "true", "sim"),
    }


def _enviar_email(assunto, corpo, destinatarios):
    """Um e-mail texto pelo broker. -> (ok, motivo). Nunca levanta."""
    smtp = _smtp_config()
    if not (smtp["server"] and smtp["remetente"]):
        return False, "SMTP sem servidor ou remetente no ambiente (SMTP_SERVER / EMAIL_FROM)"
    if not destinatarios:
        return False, "sem destinatario"
    msg = MIMEMultipart()
    msg["From"] = f"{smtp['nome']} <{smtp['remetente']}>"
    msg["To"] = ", ".join(destinatarios)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    try:
        if smtp["port"] == 465:
            srv = smtplib.SMTP_SSL(smtp["server"], smtp["port"], timeout=30)
        else:
            srv = smtplib.SMTP(smtp["server"], smtp["port"], timeout=30)
            if smtp["starttls"]:
                srv.starttls()
        with srv:
            # o broker do Guardian dispensa AUTH: a senha vazia e de proposito
            if smtp["user"] and smtp["senha"]:
                srv.login(smtp["user"], smtp["senha"])
            srv.sendmail(smtp["remetente"], destinatarios, msg.as_string())
    except Exception as e:  # noqa: BLE001
        return False, f"falha SMTP: {str(e)[:160]}"
    return True, "ok"


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
    corpo = montar_corpo_finalizada(op, cedente, contexto, detalhes)
    return _enviar_email(f"[Robo 7] Operacao {op} FINALIZADA - {cedente or ''}".strip(),
                         corpo, destinatarios)


def montar_corpo_pagamento(op, cedente, pendencias, contexto=None):
    """Texto do aviso de PAGAMENTO pendente: a op so nao foi finalizada por causa dele."""
    ctx = contexto or {}
    linhas = [
        f"Todos os documentos da operacao {op} estao assinados, mas o Robo 7 NAO a",
        "finalizou porque a forma de pagamento tem pendencia:",
        "",
    ]
    linhas += [f"  - {p}" for p in pendencias]
    linhas += ["", "Dados da operacao:", f"  Cedente ....... {cedente or '(nao identificado)'}"]
    if ctx.get("valor"):
        linhas.append(f"  Valor ......... {ctx['valor']}")
    for lin in ctx.get("linhas_pagamento") or []:
        linhas.append(
            f"  Pagamento {lin.get('_linha')}: {lin.get('tipo') or '(sem tipo)'}"
            f" | origem {lin.get('cta_origem') or '(vazia)'}"
            f" | vencimento {_data_br(lin.get('vencto')) or '(vazio)'}"
            f" | SP {'marcado' if lin.get('sp') == 'SIM' else 'NAO marcado'}")
    limite = cfg.HORA_LIMITE_FINALIZAR or "o fim do expediente"
    linhas += [
        "",
        "Corrija na tela da operacao (Resumir > Pagamento). O robo confere de novo a cada",
        f"15 minutos e finaliza sozinho quando estiver certo, ate as {limite}. Depois desse",
        "horario ele nao clica: finalize a mao se o pagamento precisar sair hoje.",
        "",
        "-- ",
        "Robo 7 (finalizar operacao) - Prospere",
    ]
    return "\n".join(linhas)


def _pendencia_curta(p):
    """Tira o prefixo que so atrapalha no celular: 'Pagamento: X' -> 'X';
    'Pagamento (linha 2): X' -> 'linha 2: X'; 'Forma de pagamento: X' -> 'X'."""
    m = re.match(r"Pagamento \((linha \d+)\): (.*)", p)
    if m:
        return f"{m.group(1)}: {m.group(2)}"
    for prefixo in ("Forma de pagamento: ", "Pagamento: "):
        if p.startswith(prefixo):
            return p[len(prefixo):]
    return p


def texto_whatsapp_pagamento_pendente(op, cedente, pendencias, contexto=None):
    """WhatsApp do aviso de PAGAMENTO pendente: o que trava e o que fazer, no celular."""
    ctx = contexto or {}
    linhas = [f"⚠️ *Operação {op} pronta, mas o pagamento trava*"]
    if cedente:
        linhas.append(f"{cedente}")
    if ctx.get("valor"):
        linhas.append(f"💰 {ctx['valor']}")
    linhas += ["", "📄 Documentos: todos assinados ✓", "", "🏦 *Falta no pagamento*"]
    for p in pendencias:
        linhas.append(f"  • {_pendencia_curta(p)}")
    limite = cfg.HORA_LIMITE_FINALIZAR or "o fim do expediente"
    linhas += ["", f"Corrija no Smart (Resumir › Pagamento). O robô confere a cada 15 min e "
                   f"finaliza sozinho até as {limite}; depois disso, só à mão.",
               "", f"_{datetime.now():%d/%m %H:%M} · Robô 7_"]
    return "\n".join(linhas)


def _canais_ligados(tem_whatsapp):
    """Canais do aviso de pendencia que vao mesmo sair: pedidos E com a chave ligada."""
    canais = []
    if "whatsapp" in cfg.AVISO_PENDENCIA_CANAIS and tem_whatsapp and cfg.WHATSAPP_ATIVO:
        canais.append("whatsapp")
    if "email" in cfg.AVISO_PENDENCIA_CANAIS and cfg.EMAIL_ATIVO:
        canais.append("email")
    return canais


def _avisar(op, pendencias, assunto, corpo, destinatarios, texto_whatsapp=None, forcar=False):
    """Liga/desliga, espacamento, envio e registro de UM aviso, por canal.
    -> {"enviado", "tentou", "motivo", "destinatarios", "canais"}. `tentou` = chegou a
    falar com algum canal; `enviado` = pelo menos um entregou (e ai conta no espacamento).
    Um canal que falha nao impede o outro."""
    r = {"enviado": False, "tentou": False, "motivo": "", "destinatarios": list(destinatarios),
         "canais": {}}
    if not pendencias:
        r["motivo"] = "sem pendencias"
        return r
    canais = _canais_ligados(bool(texto_whatsapp))
    if not canais:
        r["motivo"] = ("nenhum canal de aviso ligado (R7_AVISO_PENDENCIA_CANAIS, "
                       "R7_WHATSAPP_ATIVO, R7_EMAIL_ATIVO)")
        return r
    n_anterior = 0
    if forcar:
        motivo_envio = "forcado"
    else:
        pode, motivo_envio, n_anterior = pode_avisar(op, pendencias)
        if not pode:
            r["motivo"] = motivo_envio
            return r
    reforco = f" (cobranca #{n_anterior + 1})" if n_anterior else ""
    r["tentou"] = True
    if "whatsapp" in canais:
        n_ok, res = notificar_whatsapp.enviar(texto_whatsapp, cfg.WHATSAPP_DESTINO_OPERACIONAL)
        r["canais"]["whatsapp"] = {"ok": bool(n_ok), "detalhe": "; ".join(
            f"{num}: {'OK' if ok else 'FALHOU'} - {str(d)[:80]}" for num, ok, d in res)}
    if "email" in canais:
        ok, motivo = _enviar_email(assunto + reforco, corpo, destinatarios)
        r["canais"]["email"] = {"ok": ok, "detalhe": motivo}
    r["enviado"] = any(c["ok"] for c in r["canais"].values())
    resumo = " | ".join(f"{canal}: {'ok' if c['ok'] else c['detalhe']}"
                        for canal, c in r["canais"].items())
    if not r["enviado"]:
        r["motivo"] = f"nenhum canal entregou ({resumo})"
        return r
    _registrar(op, pendencias, [c for c, v in r["canais"].items() if v["ok"]], n_anterior)
    proxima = espera_minutos(n_anterior + 1) / 60.0
    r["motivo"] = (f"enviado ({resumo}; {motivo_envio}; se continuar pendente, cobra de "
                   f"novo em {proxima:.0f}h)")
    return r


def avisar_pagamento_pendente(op, cedente, pendencias, contexto=None, destinatarios=None):
    """O aviso de pendencia que vale: documentos assinados e o PAGAMENTO travando."""
    destinatarios = destinatarios or cfg.EMAIL_DESTINO
    assunto = (f"[Robo 7] Operacao {op} pronta, mas o PAGAMENTO impede a finalizacao - "
               f"{len(pendencias)} pendencia(s)")
    return _avisar(op, pendencias, assunto,
                   montar_corpo_pagamento(op, cedente, pendencias, contexto), destinatarios,
                   texto_whatsapp=texto_whatsapp_pagamento_pendente(op, cedente, pendencias,
                                                                    contexto))


def enviar(op, cedente, pendencias, contexto=None, destinatarios=None, forcar=False,
           prefixo_assunto=""):
    """Aviso generico de pendencia (compatibilidade). Retorna (enviado, motivo)."""
    destinatarios = destinatarios or cfg.EMAIL_DESTINO
    assunto = (f"{prefixo_assunto}[Robo 7] Operacao {op} NAO finalizada - "
               f"{len(pendencias)} pendencia(s)")
    r = _avisar(op, pendencias, assunto, montar_corpo(op, cedente, pendencias, contexto),
                destinatarios, forcar=forcar)
    return r["enviado"], r["motivo"]


def main():
    ap = argparse.ArgumentParser(description="Mostra o SMTP do Robo 7; com --teste, manda um e-mail de teste.")
    ap.add_argument("--teste", action="store_true", help="manda UM e-mail de teste (R7_EMAIL_TESTE)")
    ap.add_argument("--op", default="00000")
    ap.add_argument("--para", default="", help="destinatario(s) separados por virgula")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    smtp = _smtp_config()
    print(f"SMTP: servidor {'definido' if smtp['server'] else 'AUSENTE'}, porta {smtp['port']}, "
          f"remetente {'definido' if smtp['remetente'] else 'AUSENTE'}, "
          f"senha {'definida' if smtp['senha'] else 'vazia (broker do Guardian)'}")
    print(f"Aviso de pagamento: {', '.join(cfg.EMAIL_DESTINO)} | "
          f"e-mail {'LIGADO' if cfg.EMAIL_ATIVO else 'desligado'} (R7_EMAIL_ATIVO)")
    if not args.teste:
        print("\n(use --teste para mandar um e-mail de teste)")
        return 0

    destino = [e.strip() for e in args.para.split(",") if e.strip()] or cfg.EMAIL_TESTE
    pend = ["Pagamento: Vencto = 21/09/2026, deveria ser a data de hoje",
            "Pagamento: SP nao esta marcado"]
    ctx = {"valor": "R$ 3.537,26",
           "linhas_pagamento": [{"_linha": "1", "tipo": "PIX", "cta_origem": "mp prospere",
                                 "vencto": "2026-09-21", "sp": "NAO"}]}
    ok, motivo = _enviar_email(
        f"[TESTE] [Robo 7] Operacao {args.op} pronta, mas o PAGAMENTO impede a finalizacao - "
        f"{len(pend)} pendencia(s)",
        montar_corpo_pagamento(args.op, "CEDENTE DE TESTE", pend, ctx), destino)
    print(f">> enviado={ok} | {motivo} | para {', '.join(destino)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
