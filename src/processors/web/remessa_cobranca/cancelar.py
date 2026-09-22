# -*- coding: utf-8 -*-
"""
cancelar.py - CANCELA no Smart a remessa que o banco recusou.

POR QUE EXISTE. O Smart marca como "remetido" todo titulo que entrou numa remessa
gerada. Quando o banco recusa o ARQUIVO inteiro, o Smart nao sabe: para ele a
remessa foi entregue. Os titulos ficam num limbo - o ERP nao os oferece de novo, o
banco nao tem o boleto, e o sacado nao consegue pagar. Medido em 21/09/2026 pelo
process-automation: 22 remessas, 449 titulos, R$ 3.001.728,62, a mais antiga parada
desde 20/08.

Cancelar devolve os titulos a fila; a geracao seguinte os inclui e o saneamento do
endereco (process-automation, `saneamento_pagador`) corrige na saida.

COMO A TELA CANCELA. Lido do JS de `downloadremessa.php`, nao suposto:

    function CancelarRemessa(form, bt) {
        ...
        form.checks.value = radioSel;    // o ID da remessa
        form.cancelamento.value = 1;     // liga o cancelamento
        form.submit();                   // POST na MESMA url da listagem
    }

Ou seja: e o mesmo POST que `remessa_cobranca.listar_remessas` ja faz, com dois campos
trocados. Nao ha endpoint proprio nem tela extra.

=============================================================================
 ⛔ O QUE ESTE MODULO NAO FAZ, E E O MAIS IMPORTANTE
=============================================================================

Ele NAO decide o que cancelar. A lista vem PRONTA do process-automation, em
`cancelamentos.json`, e este modulo so executa o que esta la.

A razao e concreta: cancelar devolve a fila TODOS os titulos da remessa, e um
titulo que JA TENHA boleto registrado no banco sairia de novo - dois boletos para o
mesmo sacado, que nao tem culpa nem como saber qual pagar. Quem sabe disso e o
process-automation, que pergunta ao banco (`/BoletosRegistrados`). Medido em
21/09/2026: 25 titulos nessa situacao, um deles numa remessa de 132.

⛔ Varrer a tela e decidir aqui seria refazer essa conta sem os dados. Nao se faz.

SEGURANCA, no molde do `gerar.py`:
  - `dry_run=True` e o padrao: devolve o que MANDARIA, sem tocar no Smart;
  - lista com validade vencida nao executa;
  - um id por vez, com o resultado conferido antes do proximo;
  - timeout NAO e tratado como falha - ver o bloco no `cancelar_uma()`.
"""
import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

import remessa_config as cfg
import login as autenticacao

#: Quantos dias para tras quando o controle nao tem a data — larga de proposito.
DIAS_SEM_DATA_NO_CONTROLE = 60

#: Onde o robo registra o que JA cancelou. ⛔ Sem isso a remessa cancelada continua
#: aparecendo na lista todo dia: o cancelamento acontece no SMART, e a nossa
#: `cnab_remessa_enviada` nao fica sabendo — ela segue com `sucesso = false` para sempre.
#: Cancelar de novo e inocuo (a remessa ja sumiu da grade), mas o log diria "CANCELADA"
#: todo dia sobre coisa nenhuma, e ninguem saberia o que ainda falta fazer.
FEITOS_PADRAO = os.environ.get(
    "CANCELAMENTOS_FEITOS_JSON",
    "/app/data/retornos_a_processar/remessa_cnab_400/cancelamentos_feitos.json")


def ler_feitos(caminho=FEITOS_PADRAO):
    """Os ids que este robo ja cancelou, para nao repetir. Ilegivel = vazio, e segue."""
    try:
        with open(caminho, encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return {}
    feitos = dados.get("feitos") if isinstance(dados, dict) else None
    return feitos if isinstance(feitos, dict) else {}


def registrar_feito(smart_id, arquivo, caminho=FEITOS_PADRAO, agora=None):
    """Anota que ESTE id foi cancelado. Escrita atomica: o robo nunca le metade.

    ⚠️ Falha ao anotar NAO derruba a rodada — o cancelamento ja aconteceu, e
    perder a anotacao custa uma tentativa inocua amanha. Derrubar aqui custaria
    as remessas seguintes da mesma rodada.
    """
    agora = agora or datetime.now(timezone.utc)
    feitos = ler_feitos(caminho)
    feitos[str(smart_id)] = {"arquivo": arquivo, "cancelada_em": agora.isoformat()}
    try:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        temporario = caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as fh:
            json.dump({"versao": 1, "feitos": feitos}, fh, ensure_ascii=False, indent=1)
        os.replace(temporario, caminho)
        return True
    except OSError as e:                                            # noqa: BLE001
        log("  aviso: nao consegui anotar o cancelamento de %s (%s)" % (smart_id, e))
        return False


#: Onde o process-automation escreve a lista. Mesmo bind do `exclusoes.json`.
ARQUIVO_PADRAO = os.environ.get(
    "CANCELAMENTOS_JSON",
    "/app/data/retornos_a_processar/remessa_cnab_400/cancelamentos.json")


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# A lista que vem do process-automation
# ---------------------------------------------------------------------------

def ler_lista(caminho=ARQUIVO_PADRAO, agora=None):
    """Le `cancelamentos.json`. Devolve (remessas, motivo_da_recusa).

    ⛔ Lista vencida NAO executa. A prova de que o boleto nao esta no banco tem
    prazo: entre a resposta do banco e agora, o boleto pode ter sido registrado -
    e aquele titulo passaria a ser uma duplicata esperando acontecer.
    """
    agora = agora or datetime.now(timezone.utc)
    try:
        with open(caminho, encoding="utf-8") as fh:
            dados = json.load(fh)
    except FileNotFoundError:
        return {}, "lista nao existe em %s (o apontar_cancelamentos ja rodou?)" % caminho
    except (OSError, ValueError) as e:
        return {}, "lista ilegivel (%s: %s)" % (type(e).__name__, e)

    gerado = dados.get("gerado_em")
    validade = int(dados.get("validade_horas") or 0)
    if gerado and validade:
        try:
            nascida = datetime.fromisoformat(gerado)
            if nascida.tzinfo is None:
                nascida = nascida.replace(tzinfo=timezone.utc)
            idade = agora - nascida
            if idade > timedelta(hours=validade):
                return {}, ("lista VENCIDA: gerada em %s, validade %d h, idade %s - "
                            "a prova de que o boleto nao esta no banco caducou"
                            % (gerado, validade, str(idade).split(".")[0]))
        except ValueError:
            return {}, "lista com `gerado_em` ilegivel: %r" % gerado

    remessas = dados.get("remessas") or {}
    if not isinstance(remessas, dict):
        return {}, "lista com `remessas` em formato inesperado"
    return remessas, ""


# ---------------------------------------------------------------------------
# O POST
# ---------------------------------------------------------------------------

def conta_do_smart(tipo, contas_mapa):
    """A CONTA do Smart (287, 291, 298...) a partir do `tipo` do controle do robo.

    ⛔ **Nao confundir com o `numero_cedente` do CNAB.** Sao duas chaves diferentes e
    ambas parecem "o cedente":

        numero_cedente  1026716   o numero do cedente NO BANCO (header do .REM)
        conta do Smart  298       a conta no ERP, que e o que `contaSelected` espera

    Mandar a primeira no POST monta a grade de uma conta que nao existe, a remessa
    nao aparece nela, e o cancelamento silenciosamente nao acha o id. O `tipo` do
    `remessas_geradas.json` traz o nome ("mp tapayuna Envio de cobranca registrado")
    e o `contas_carteiras.json` mapeia nome -> numero.

    ⛔ **E o casamento e pelo nome MAIS LONGO que serve, nunca pelo primeiro achado.**
    Medido em 21/09/2026 sobre o `contas_carteiras.json` real: das 57 contas, 4 tem nome
    que e PREFIXO de outra — `293 "mp pradzia"` de `343 "mp pradzia papeis"`,
    `286 "Banco do Brasil"` de duas, `285 "SICOOB"` de `288 "SICOOB ATIVOS"`. Varrendo o
    dicionario na ordem, `"mp pradzia papeis Envio..."` devolvia **293**: conta errada,
    grade errada, o id nao aparece nela, o POST nao faz nada — e o `sumiu_da_grade`,
    que lista a MESMA grade errada, confirma que sumiu. Falso sucesso, exit 0.
    """
    if not tipo:
        return None
    alvo = str(tipo).strip().lower()
    melhor = None
    for numero, nome in (contas_mapa or {}).items():
        n = str(nome).strip().lower()
        if n and alvo.startswith(n) and (melhor is None or len(n) > len(melhor[1])):
            melhor = (str(numero), n)
    return melhor[0] if melhor else None


def montar_post(smart_id, conta, de, ate):
    """O corpo do POST de cancelamento - o mesmo da listagem, com dois campos.

    ⚠️ `checks` leva o id e `cancelamento` vai a 1. Os demais campos continuam os
    da listagem porque a tela e a mesma: sem `contaSelected` e o periodo, o Smart
    nao monta a grade em que o id existe.
    """
    return urllib.parse.urlencode({
        "form_submit": "1",
        "checks": str(smart_id),      # <- o id da remessa a cancelar
        "cancelamento": "1",          # <- liga o cancelamento
        "radioSel": str(smart_id),
        "contaSelected": conta,
        "contaCorrente": conta,
        "periodo_inicial": de,
        "periodo_final": ate,
    })


def cancelar_uma(ctx, smart_id, conta, de, ate, dry_run=True, timeout=180_000):
    """Cancela (ou simula) UMA remessa. Devolve {ok, motivo, corpo, enviado}.

    ⛔ **Timeout nao e falha, e e o pior caso.** Conexao cortada NAO diz se o Smart
    processou. Devolver `ok=False, enviado=False` faria a rodada seguinte tentar de
    novo uma remessa que ja pode ter sido cancelada - e o segundo cancelamento cai
    numa remessa que nao existe mais, ou pior, numa outra que herdou a posicao na
    grade. Por isso `enviado=True`: quem chamou RECONFERE pela listagem, que e a
    unica leitura confiavel do que existe la.
    ⭐ E a mesma regra que o `gerar.py` adotou depois do BUG-681, em que dois
    timeouts fizeram duas contas serem puladas em silencio com a rodada em exit 0.
    """
    corpo = montar_post(smart_id, conta, de, ate)
    if dry_run:
        return {"ok": None, "motivo": "DRY_RUN (nada enviado)", "corpo": corpo,
                "enviado": False}
    try:
        r = ctx.request.post(
            cfg.URL_DOWNLOAD_REMESSA, data=corpo,
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=timeout)
    except Exception as e:                                          # noqa: BLE001
        return {"ok": False, "enviado": True,
                "motivo": "POST nao respondeu (%s: %s) - PODE ter cancelado; reconferir na listagem"
                          % (type(e).__name__, e),
                "corpo": corpo}
    texto = r.body().decode("iso-8859-1", errors="replace")
    if r.status != 200 or autenticacao.parece_deslogado(texto):
        return {"ok": False, "enviado": True,
                "motivo": "resposta sem utilidade (status=%s) - sessao caiu; reconferir" % r.status,
                "corpo": corpo}
    return {"ok": True, "enviado": True, "motivo": "POST aceito", "corpo": corpo,
            "html": texto}


def sumiu_da_grade(ctx, smart_id, conta, de, ate, listar):
    """A remessa deixou de aparecer na tela? E a CONFIRMACAO de que foi cancelada.

    ⛔ `ok=True` do POST diz que o Smart respondeu 200, nao que cancelou. Quem
    confirma e a grade: a remessa cancelada some dela. Sem esta leitura o robo
    afirmaria um cancelamento que pode nao ter acontecido - e a rodada seguinte
    nao tentaria de novo.
    """
    try:
        ainda = [r for r in listar(ctx, conta, de, ate) if str(r.get("id")) == str(smart_id)]
    except Exception as e:                                          # noqa: BLE001
        return None, "nao deu para reconferir a grade (%s)" % type(e).__name__
    return (not ainda), ("sumiu da grade" if not ainda else "AINDA aparece na grade")

#: Folga em dias dos dois lados da data em que o robo baixou a remessa. O `baixado_em`
#: e o horario do robo (UTC no container) e a grade mostra o horario do Smart: um dia de
#: cada lado cobre a virada sem alargar a grade a ponto de trazer remessa de outra conta.
FOLGA_DA_GRADE_DIAS = 1


def entrada_do_controle(controle, arquivo, smart_id):
    """A entrada do `remessas_geradas.json` DAQUELE id — nunca a primeira do nome.

    ⛔ O nome se repete entre contas: em 18/09/2026 o `CB08090000011` era da MP PROSPERE
    e da WJ MOREIRA ao mesmo tempo. Pegar `entrada[0]` devolve o `tipo` de uma conta e o
    id de outra — e o POST vai para a grade errada, onde o id nao existe.
    """
    candidatos = controle.get(arquivo) or []
    if isinstance(candidatos, dict):                      # formato anterior: um por nome
        candidatos = [candidatos]
    alvo = str(smart_id).strip()
    for c in candidatos:
        if isinstance(c, dict) and str(c.get("id") or "").strip() == alvo:
            return c
    return {}


def janela_da_remessa(entrada, de=None, ate=None):
    """O periodo que a grade do Smart precisa receber para conter ESTA remessa.

    ⛔ **A janela do job nao e a do robo, e confundi-las produz falso sucesso.** O
    `apontar_cancelamentos` olha 45 dias para tras; o padrao do robo e `DIAS_REMESSA=7`.
    Medido em 21/09/2026: das 21 remessas apontadas, **18 eram anteriores a 14/09** e
    portanto ficavam fora da grade que o POST montava. O POST nao achava o id, nao
    cancelava nada — e o `sumiu_da_grade`, que lista a MESMA janela curta, confirmava
    que a remessa sumiu. O log diria "CANCELADA" em 18 remessas ainda paradas.

    ⭐ A data vem do proprio controle do robo (`baixado_em`), que e de quando ele a
    baixou — minutos depois de o Smart a gerar, que e a data que a grade mostra.
    ⚠️ `de`/`ate` explicitos mandam: o operador que quer uma janela propria tem a dele.
    """
    if de and ate:
        return de, ate
    bruto = str((entrada or {}).get("baixado_em") or "").strip()
    try:
        dia = datetime.fromisoformat(bruto).date()
    except (TypeError, ValueError):
        # ⛔ Sem data no controle, NAO se inventa janela curta: a larga so deixa a grade
        # maior, a curta esconde a remessa e vira falso sucesso.
        hoje = datetime.now(timezone.utc).date()
        return (de or (hoje - timedelta(days=DIAS_SEM_DATA_NO_CONTROLE)).isoformat(),
                ate or hoje.isoformat())
    folga = timedelta(days=FOLGA_DA_GRADE_DIAS)
    return (de or (dia - folga).isoformat(), ate or (dia + folga).isoformat())
