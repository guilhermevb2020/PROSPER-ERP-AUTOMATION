# -*- coding: utf-8 -*-
"""
rotina_avisos.py - os avisos que acompanham o DIA do Robo 7, alem do aviso de cada op.

  PIX confirmado pelo banco -> GESTAO: um aviso por rodada com os PIX de ops finalizadas
                               pelo robo que o retorno trouxe com ocorrencia 00.
  PIX recusado              -> OPERACIONAL, por op: o retorno veio com outro codigo.
  PIX que nao saiu          -> OPERACIONAL, por op: finalizada pelo robo ha mais de
                               R7_PIX_ATRASO_MIN min sem retorno; ultima chamada na rodada
                               do resumo do dia.
  pronta depois do corte    -> OPERACIONAL, por op: passou em tudo depois do limite de
                               hora (18:30), quando o robo nao clica mais.
  assinaturas paradas       -> OPERACIONAL, nos horarios de R7_RESUMO_ASSINATURAS_HORAS
                               (11:00 e 15:00): quem falta assinar e desde quando.
  resumo do dia             -> GESTAO, na primeira rodada a partir de R7_RESUMO_DIA_HORA.

Por que existe (22/09/2026): o robo avisava "finalizada" e ninguem confirmava o PIX; os
dois primeiros PIX dele so sairam porque alguem gerou a remessa a mao durante a
manutencao do hub. O relatorio do Financeiro das 18:30 pega op nao paga, mas a ultima
remessa sai 18:55 - sobra pouco tempo para corrigir.

Tudo exige --avisar no comando e sai por WhatsApp (R7_WHATSAPP_ATIVO). GESTAO e
R7_WHATSAPP_DESTINO; OPERACIONAL e R7_WHATSAPP_DESTINO_OPERACIONAL (numero ou id de grupo).
Estado em rotina_avisos.json (bind de src/, gitignorado): o que ja foi avisado, os
retornos ja lidos e quando cada op apareceu na fila. As ops finalizadas pelo robo ficam em
finalizadas_pix.jsonl, com CPF/CNPJ e valor de cada linha de pagamento - e o que casa com
o retorno do banco.
"""
import json
import os
import sys
from datetime import datetime, timedelta, time as dt_time

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import notificar_whatsapp  # noqa: E402
import pix_retorno  # noqa: E402
import r7_config as cfg  # noqa: E402

_DIAS_MEMORIA_FILA = 7
_MAX_LISTA = 15
_MAX_CONSULTAS_ETAPA = 40


# --------------------------------------------------------------------------- #
# estado
# --------------------------------------------------------------------------- #
def carregar_estado():
    try:
        with open(cfg.ARQ_ROTINA, encoding="utf-8") as fh:
            est = json.load(fh)
    except (FileNotFoundError, ValueError):
        est = {}
    for chave in ("primeira_vez", "visto", "avisados", "retornos", "resumos"):
        if not isinstance(est.get(chave), dict):
            est[chave] = {}
    return est


def salvar_estado(est):
    tmp = cfg.ARQ_ROTINA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(est, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, cfg.ARQ_ROTINA)


def podar(est, hoje):
    """Esquece o que nao serve mais: avisos, resumos e retornos de outros dias; ops que
    sumiram da fila ha mais de uma semana."""
    dia = hoje.isoformat()
    for chave in ("avisados", "resumos"):
        est[chave] = {k: v for k, v in est[chave].items() if k.startswith(dia)}
    prefixo = f"CP{hoje:%d%m}"
    est["retornos"] = {k: v for k, v in est["retornos"].items() if k.upper().startswith(prefixo)}
    limite = (datetime.combine(hoje, dt_time()) - timedelta(days=_DIAS_MEMORIA_FILA)).isoformat()
    velhos = [op for op, quando in est["visto"].items() if quando < limite]
    for op in velhos:
        est["visto"].pop(op, None)
        est["primeira_vez"].pop(op, None)


# --------------------------------------------------------------------------- #
# util
# --------------------------------------------------------------------------- #
def valor_br(texto):
    """'12.659,99' / 'R$ 12.659,99' / 12659.99 -> 12659.99; vazio -> None."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    s = str(texto).replace("R$", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def brl(valor):
    if valor is None:
        return "valor ?"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _curto(texto, n=28):
    texto = (texto or "").strip()
    return texto if len(texto) <= n else texto[:n - 1].rstrip() + "…"


def _hora(hhmm):
    try:
        hh, mm = str(hhmm).strip().split(":")
        return dt_time(int(hh), int(mm))
    except (ValueError, TypeError):
        return None


def _hm(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except (ValueError, TypeError):
        return "?"


def _rodape(agora):
    return f"_{agora:%d/%m %H:%M} · Robô 7_"


def _enviar(texto, destinos):
    """-> (ok, detalhe). ok = pelo menos um destino recebeu."""
    n, res = notificar_whatsapp.enviar(texto, destinos)
    detalhe = "; ".join(f"{num}: {'OK' if ok else 'FALHOU'} - {str(d)[:80]}" for num, ok, d in res)
    return bool(n), detalhe


# --------------------------------------------------------------------------- #
# ops finalizadas pelo robo (o lado "nosso" do casamento com o retorno do banco)
# --------------------------------------------------------------------------- #
def registrar_finalizada(op, cedente, valor, linhas_pagamento, quando=None):
    linhas = [{"documento": pix_retorno.documento_normalizado(lin.get("cpf_cnpj")),
               "valor": valor_br(lin.get("valor")),
               "favorecido": (lin.get("favorecido") or "").strip()}
              for lin in (linhas_pagamento or [])]
    reg = {"quando": (quando or datetime.now()).isoformat(timespec="seconds"), "op": str(op),
           "cedente": cedente or "", "valor": valor, "linhas": linhas}
    with open(cfg.ARQ_FINALIZADAS_PIX, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(reg, ensure_ascii=False) + "\n")


def finalizadas_do_dia(hoje):
    dia = hoje.isoformat()
    saida = []
    try:
        with open(cfg.ARQ_FINALIZADAS_PIX, encoding="utf-8") as fh:
            for linha in fh:
                try:
                    reg = json.loads(linha)
                except ValueError:
                    continue
                if str(reg.get("quando", "")).startswith(dia):
                    saida.append(reg)
    except FileNotFoundError:
        pass
    return saida


def _valor_total(finalizada):
    soma = sum(lin["valor"] for lin in finalizada.get("linhas") or [] if lin.get("valor") is not None)
    return soma or finalizada.get("valor")


# --------------------------------------------------------------------------- #
# PIX: casar a op finalizada com o retorno do banco (CPF/CNPJ + valor exato)
# --------------------------------------------------------------------------- #
def situacao_pix(finalizada, pagamentos, usados):
    """-> (situacao, achados). situacao: 'liquidado' (todas as linhas com retorno 00),
    'recusado' (alguma linha com outro codigo), 'sem_retorno' ou 'sem_linha'.
    `pagamentos`: [(chave, pagamento)]; `usados` guarda as chaves ja casadas - um
    pagamento do banco casa com UMA linha so, mesmo se o cedente tiver duas ops iguais."""
    linhas = finalizada.get("linhas") or []
    if not linhas:
        return "sem_linha", []
    achados = []
    for lin in linhas:
        candidatos = [(k, p) for k, p in pagamentos
                      if k not in usados and p.get("documento") and lin.get("documento")
                      and p["documento"] == lin["documento"] and lin.get("valor") is not None
                      and abs(p["valor"] - lin["valor"]) < 0.005]
        candidatos.sort(key=lambda kp: 0 if pix_retorno.efetivado(kp[1]) else 1)
        if candidatos:
            k, p = candidatos[0]
            usados.add(k)
            achados.append((lin, p))
        else:
            achados.append((lin, None))
    if all(p is not None and pix_retorno.efetivado(p) for _, p in achados):
        return "liquidado", achados
    if any(p is not None and not pix_retorno.efetivado(p) for _, p in achados):
        return "recusado", achados
    return "sem_retorno", achados


def conferir_pix(est, finalizadas, retornos, hoje, agora, ultima_chamada):
    """Decide o que avisar. -> {"liquidado": [f], "recusado": [(f, achados)],
    "atrasado": [(f, minutos, final)], "situacoes": {op: situacao}}."""
    dia = hoje.isoformat()
    pagamentos = [((nome, i), p) for nome, lista in sorted(retornos.items())
                  for i, p in enumerate(lista) if p.get("data") == dia]
    usados, novos = set(), {"liquidado": [], "recusado": [], "atrasado": [], "situacoes": {}}
    for f in sorted(finalizadas, key=lambda r: r.get("quando", "")):
        situacao, achados = situacao_pix(f, pagamentos, usados)
        novos["situacoes"][f["op"]] = situacao
        avisado = lambda tipo: f"{dia}|pix_{tipo}|{f['op']}" in est["avisados"]  # noqa: E731
        if situacao == "liquidado" and not avisado("liquidado"):
            novos["liquidado"].append(f)
        elif situacao == "recusado" and not avisado("recusado"):
            novos["recusado"].append((f, achados))
        elif situacao in ("sem_retorno", "sem_linha"):
            try:
                minutos = (agora - datetime.fromisoformat(f["quando"])).total_seconds() / 60
            except (ValueError, TypeError, KeyError):
                continue
            if minutos < cfg.PIX_ATRASO_MIN:
                continue
            if not avisado("atrasado"):
                novos["atrasado"].append((f, minutos, False))
            elif ultima_chamada and not avisado("atrasado_final"):
                novos["atrasado"].append((f, minutos, True))
    return novos


def texto_pix_confirmado(finalizadas, agora):
    linhas = ["💸 *PIX confirmado pelo banco*"]
    for f in finalizadas:
        linhas.append(f"  • {f['op']} {_curto(f.get('cedente'))} · {brl(_valor_total(f))}")
    linhas += ["", _rodape(agora)]
    return "\n".join(linhas)


def texto_pix_recusado(f, achados, agora):
    codigos = sorted({pix_retorno.codigo(p) for _, p in achados
                      if p is not None and not pix_retorno.efetivado(p)})
    explica = "; ".join(f"{c} ({pix_retorno.SIGNIFICADO[c]})" if c in pix_retorno.SIGNIFICADO else c
                        for c in codigos)
    return "\n".join([
        f"❌ *PIX da operação {f['op']} foi recusado pelo banco*",
        f"{_curto(f.get('cedente'), 40)} · {brl(_valor_total(f))}",
        f"Ocorrência no retorno: {explica}",
        f"O robô finalizou às {_hm(f.get('quando'))}. Corrija o cadastro no Smart e refaça o "
        "pagamento.",
        "", _rodape(agora)])


def texto_pix_atrasado(f, minutos, final, agora):
    titulo = ("⚠️ *Última chamada: PIX da operação {op} ainda não saiu*" if final
              else "⚠️ *PIX da operação {op} ainda não saiu*").format(op=f["op"])
    return "\n".join([
        titulo,
        f"{_curto(f.get('cedente'), 40)} · {brl(_valor_total(f))}",
        f"Finalizada pelo robô às {_hm(f.get('quando'))}, há {minutos:.0f} min, e o banco "
        "ainda não devolveu o retorno.",
        "Confira se o pagamento está pendente em Financeiro › Pagamento BMP. A última "
        "remessa do dia sai às 18:55.",
        "", _rodape(agora)])


# --------------------------------------------------------------------------- #
# pronta depois do corte
# --------------------------------------------------------------------------- #
def texto_corte(op, cedente, valor, agora):
    limite = cfg.HORA_LIMITE_FINALIZAR or "o limite"
    return "\n".join([
        f"⏰ *Operação {op} ficou pronta depois das {limite}*",
        f"{_curto(cedente, 40)} · {brl(valor)}",
        "O robô não finaliza depois desse horário, para o PIX não sair amanhã com a data "
        "de hoje. Se o pagamento precisa sair hoje, finalize à mão até 18:50; a última "
        "remessa sai às 18:55.",
        "", _rodape(agora)])


def avisar_corte(op, cedente, valor, registrar=None, agora=None, log=print):
    """Uma vez por op por dia. -> True se avisou agora."""
    agora = agora or datetime.now()
    est = carregar_estado()
    chave = f"{agora.date().isoformat()}|corte|{op}"
    if chave in est["avisados"]:
        return False
    ok, detalhe = _enviar(texto_corte(op, cedente, valor, agora), cfg.WHATSAPP_DESTINO_OPERACIONAL)
    log(f"     [corte] aviso de pronta depois do limite: {'enviado' if ok else 'FALHOU'} ({detalhe})")
    if ok:
        est["avisados"][chave] = agora.isoformat(timespec="seconds")
        salvar_estado(est)
    if registrar:
        registrar(op, "pronta_depois_do_corte", ok, detalhe, cedente, valor)
    return ok


# --------------------------------------------------------------------------- #
# fila: quando cada op apareceu, e o que falta assinar
# --------------------------------------------------------------------------- #
def atualizar_fila(est, laudos, agora):
    iso = agora.isoformat(timespec="seconds")
    for laudo in laudos or []:
        op = str(laudo.get("op"))
        est["primeira_vez"].setdefault(op, iso)
        est["visto"][op] = iso


def faltantes(laudo):
    """(assinantes, documentos) que faltam, lidos das pendencias de documento do laudo."""
    assinantes, documentos = [], []
    for p in laudo.get("pendencias") or []:
        rotulo, _, resto = str(p).partition(":")
        rotulo = rotulo.strip()
        if rotulo and rotulo not in documentos:
            documentos.append(rotulo)
        if rotulo.lower().startswith("aditivo") and "->" in resto:
            for parte in resto.split("->", 1)[1].split(";"):
                nome = parte.replace("Pendente", "").strip()
                if nome and nome not in assinantes:
                    assinantes.append(nome)
    return assinantes, documentos


def resumo_assinaturas_devido(est, agora):
    """O horario de resumo que vale agora e ainda nao foi mandado (ou None). Cada horario
    vale por R7_RESUMO_ASSINATURAS_JANELA_MIN: rodada atrasada nao manda resumo velho."""
    dia = agora.date().isoformat()
    for hhmm in cfg.RESUMO_ASSINATURAS_HORAS:
        h = _hora(hhmm)
        if h is None:
            continue
        inicio = datetime.combine(agora.date(), h)
        if inicio <= agora < inicio + timedelta(minutes=cfg.RESUMO_ASSINATURAS_JANELA_MIN) \
                and f"{dia}|assinaturas|{hhmm}" not in est["resumos"]:
            return hhmm
    return None


def texto_assinaturas(laudos, est, hhmm, agora):
    esperando = [l for l in laudos or [] if l.get("acao") == "aguardando assinatura"]
    esperando.sort(key=lambda l: est["primeira_vez"].get(str(l.get("op")), ""))
    n = len(esperando)
    linhas = [f"✍️ *Assinaturas pendentes · {hhmm}*",
              f"{n} {'operação' if n == 1 else 'operações'} esperando assinatura", ""]
    for laudo in esperando[:_MAX_LISTA]:
        op = str(laudo.get("op"))
        desde = est["primeira_vez"].get(op)
        try:
            desde_txt = datetime.fromisoformat(desde).strftime("%d/%m %H:%M")
        except (TypeError, ValueError):
            desde_txt = "?"
        assinantes, documentos = faltantes(laudo)
        linhas.append(f"• *{op}* {_curto(laudo.get('cedente'))} · na fila desde {desde_txt}")
        if assinantes:
            linhas.append(f"  falta assinar: {', '.join(assinantes)}")
        if documentos:
            linhas.append(f"  documentos: {', '.join(documentos)}")
    if n > _MAX_LISTA:
        linhas.append(f"… e mais {n - _MAX_LISTA}")
    linhas += ["", _rodape(agora)]
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# resumo do dia
# --------------------------------------------------------------------------- #
_SITUACAO_PIX = {"liquidado": "PIX confirmado", "recusado": "PIX RECUSADO",
                 "sem_retorno": "PIX sem retorno", "sem_linha": "sem linha de pagamento"}


def _na_fila_agora(laudos):
    grupos = {"assinatura": [], "pagamento": [], "corte": [], "erro": []}
    for l in laudos or []:
        acao = str(l.get("acao") or "")
        if l.get("erro"):
            grupos["erro"].append(l)
        elif acao == "aguardando assinatura":
            grupos["assinatura"].append(l)
        elif "fora da janela" in acao:
            grupos["corte"].append(l)
        elif acao.startswith("fora da etapa") or acao.startswith("finalizada"):
            continue
        elif l.get("pendencias"):
            grupos["pagamento"].append(l)
    return grupos


def finalizadas_por_operador(est, laudos, finalizadas, hoje, etapa_de, log=print):
    """Ops que o robo viu na fila HOJE, que sairam dela sem ele finalizar e que o Smart
    mostra 'Concluída'. None se nao da para consultar."""
    if etapa_de is None:
        return None
    dia = hoje.isoformat()
    na_fila = {str(l.get("op")) for l in laudos or []}
    do_robo = {f["op"] for f in finalizadas}
    saiu = [op for op, quando in est["visto"].items()
            if quando.startswith(dia) and op not in na_fila and op not in do_robo]
    contagem = 0
    for op in sorted(saiu)[:_MAX_CONSULTAS_ETAPA]:
        try:
            etapa = etapa_de(op)
        except Exception as e:  # noqa: BLE001
            log(f"  [resumo] nao li a etapa da {op}: {str(e)[:80]}")
            continue
        if etapa and "conclu" in etapa.lower():
            contagem += 1
    return contagem


def texto_resumo_dia(finalizadas, situacoes, operador, laudos, agora):
    total = sum(_valor_total(f) or 0 for f in finalizadas)
    linhas = [f"📊 *Robô 7 · resumo de {agora:%d/%m}*", "",
              f"✅ Finalizadas pelo robô: {len(finalizadas)} · {brl(total)}"]
    for f in finalizadas[:_MAX_LISTA]:
        linhas.append(f"  • {f['op']} {_curto(f.get('cedente'), 22)} · {brl(_valor_total(f))}"
                      f" · {_SITUACAO_PIX.get(situacoes.get(f['op']), 'PIX ?')}")
    if operador is not None:
        linhas.append(f"👤 Finalizadas por operador: {operador}")
    grupos = _na_fila_agora(laudos)
    n_fila = sum(len(v) for v in grupos.values())
    linhas += ["", f"⏳ Na fila agora: {n_fila}",
               f"  • esperando assinatura: {len(grupos['assinatura'])}"]
    if grupos["pagamento"]:
        ops = ", ".join(str(l.get("op")) for l in grupos["pagamento"][:10])
        linhas.append(f"  • pagamento travado: {len(grupos['pagamento'])} ({ops})")
    if grupos["corte"]:
        ops = ", ".join(str(l.get("op")) for l in grupos["corte"][:10])
        linhas.append(f"  • prontas depois do corte: {len(grupos['corte'])} ({ops})")
    if grupos["erro"]:
        linhas.append(f"  • erro na conferência: {len(grupos['erro'])}")
    linhas += ["", _rodape(agora)]
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# a rodada: chamada pelo finalizador depois de cada ciclo
# --------------------------------------------------------------------------- #
def depois_do_ciclo(laudos, nuvem=None, etapa_de=None, registrar=None, anotar=None,
                    agora=None, log=print):
    """PIX, resumo de assinaturas e resumo do dia. Nunca levanta para o chamador."""
    agora = agora or datetime.now()
    hoje = agora.date()
    dia = hoje.isoformat()
    est = carregar_estado()
    podar(est, hoje)
    atualizar_fila(est, laudos, agora)
    limite_dia = _hora(cfg.RESUMO_DIA_HORA)
    ultima_chamada = limite_dia is not None and agora.time() >= limite_dia

    # ---- PIX das ops finalizadas pelo robo --------------------------------
    finalizadas = finalizadas_do_dia(hoje)
    situacoes = {}
    if finalizadas and nuvem is not None:
        est["retornos"] = pix_retorno.retornos_do_dia(nuvem, hoje, est["retornos"], log=log)
        novos = conferir_pix(est, finalizadas, est["retornos"], hoje, agora, ultima_chamada)
        situacoes = novos["situacoes"]
        if novos["liquidado"]:
            ok, detalhe = _enviar(texto_pix_confirmado(novos["liquidado"], agora), cfg.WHATSAPP_DESTINO)
            log(f"  [pix] confirmados {[f['op'] for f in novos['liquidado']]}: "
                f"{'enviado' if ok else 'FALHOU'}")
            for f in novos["liquidado"]:
                if ok:
                    est["avisados"][f"{dia}|pix_liquidado|{f['op']}"] = agora.isoformat(timespec="seconds")
                if registrar:
                    registrar(f["op"], "pix_confirmado", ok, detalhe, f.get("cedente"), _valor_total(f))
        for f, achados in novos["recusado"]:
            ok, detalhe = _enviar(texto_pix_recusado(f, achados, agora), cfg.WHATSAPP_DESTINO_OPERACIONAL)
            log(f"  [pix] RECUSADO {f['op']}: aviso {'enviado' if ok else 'FALHOU'}")
            if ok:
                est["avisados"][f"{dia}|pix_recusado|{f['op']}"] = agora.isoformat(timespec="seconds")
            if registrar:
                registrar(f["op"], "pix_recusado", ok, detalhe, f.get("cedente"), _valor_total(f))
        for f, minutos, final in novos["atrasado"]:
            ok, detalhe = _enviar(texto_pix_atrasado(f, minutos, final, agora),
                                  cfg.WHATSAPP_DESTINO_OPERACIONAL)
            log(f"  [pix] {f['op']} sem retorno ha {minutos:.0f} min: aviso "
                f"{'enviado' if ok else 'FALHOU'}{' (ultima chamada)' if final else ''}")
            if ok:
                tipo = "atrasado_final" if final else "atrasado"
                est["avisados"][f"{dia}|pix_{tipo}|{f['op']}"] = agora.isoformat(timespec="seconds")
            if registrar:
                registrar(f["op"], "pix_sem_retorno", ok, detalhe, f.get("cedente"), _valor_total(f))

    # ---- assinaturas paradas ---------------------------------------------
    hhmm = resumo_assinaturas_devido(est, agora)
    if hhmm:
        esperando = [l for l in laudos or [] if l.get("acao") == "aguardando assinatura"]
        chave = f"{dia}|assinaturas|{hhmm}"
        if esperando:
            ok, detalhe = _enviar(texto_assinaturas(laudos, est, hhmm, agora),
                                  cfg.WHATSAPP_DESTINO_OPERACIONAL)
            log(f"  [resumo] assinaturas pendentes ({len(esperando)} op): "
                f"{'enviado' if ok else 'FALHOU'}")
            if ok:
                est["resumos"][chave] = agora.isoformat(timespec="seconds")
            if anotar:
                anotar("resumo_assinaturas", {"horario": hhmm, "ops": len(esperando), "ok": ok})
        else:
            est["resumos"][chave] = "sem operacao esperando assinatura"

    # ---- resumo do dia ---------------------------------------------------
    chave_dia = f"{dia}|resumo_dia"
    if ultima_chamada and chave_dia not in est["resumos"]:
        if finalizadas and not situacoes and nuvem is not None:
            situacoes = conferir_pix(est, finalizadas, est["retornos"], hoje, agora, False)["situacoes"]
        operador = finalizadas_por_operador(est, laudos, finalizadas, hoje, etapa_de, log=log)
        ok, detalhe = _enviar(texto_resumo_dia(finalizadas, situacoes, operador, laudos, agora),
                              cfg.WHATSAPP_DESTINO)
        log(f"  [resumo] resumo do dia: {'enviado' if ok else 'FALHOU'}")
        if ok:
            est["resumos"][chave_dia] = agora.isoformat(timespec="seconds")
        if anotar:
            anotar("resumo_dia", {"finalizadas_robo": len(finalizadas), "operador": operador, "ok": ok})

    salvar_estado(est)
