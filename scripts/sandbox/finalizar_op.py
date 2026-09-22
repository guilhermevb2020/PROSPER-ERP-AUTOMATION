#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalizar_op.py - roda o robo de FINALIZAR OPERACAO no sandbox, sem finalizar.

O QUE FAZ: percorre a fila da etapa "Aguardando Ass.", roda as DUAS checagens
do robo (1: documentos assinados no doc2you; 2: forma de pagamento PIX) e diz
quais operacoes SERIAM finalizadas. Manda UM WhatsApp com essa lista e grava um
arquivo local, para medirmos a acuracia ao longo dos dias antes de subir.

⛔ NAO FINALIZA NADA - e isso nao e so o default:
   - nao existe flag para ligar a finalizacao neste script;
   - `finalizar.finalizar_da_grade` e substituida por um stub que LEVANTA se
     alguem a chamar (cinto de seguranca contra edicao futura distraida).
   Finalizar de verdade e o robo de producao, depois da subida pelo
   docs/COMO_SUBIR_UM_ROBO.md.

ADEQUACOES ao servidor, feitas aqui (o pacote original e de Windows + keep-alive):
   - sessao: `scripts/sandbox/_ambiente` (Chrome no host + login CapSolver) no
     lugar do `sessao_r7.py`, que exigia reCAPTCHA manual diario;
   - WhatsApp: `src/common/clients/whatsapp_evolution` (instancia Prosperito) no
     lugar do provider `baileys_local`, que roda `node` e consulta o PowerShell;
   - `load_dotenv()` do config do robo1 e neutralizado: quem publica credencial
     no sandbox e o `_ambiente`, e o `.env` da raiz nem e legivel por nos.

O QUE ELE GRAVA (os dois arquivos que interessam):
   - data/sandbox/finalizar_op/veredito.csv        placar: op x veredito x pendencias
   - data/sandbox/finalizar_op/contas_pagamento.csv  CONTAS das ops aprovadas,
     16 campos da grade (bco/ag/tp.conta/cc/favorecido/cpf-cnpj/chave PIX/valor/
     vencto) - o insumo da remessa bancaria. Uma linha por linha da grade:
     pagamento DIVIDIDO gera varias para a mesma op.

WHATSAPP: DESLIGADO POR PADRAO.
   Hoje o robo so grava e imprime. Para LIGAR o aviso depois - "estas operacoes
   foram finalizadas e estao prontas para pagamento":

     1) peca a EVOLUTION_API_KEY a quem tem acesso ao .env da raiz (600 do
        usuario `prospere`) e escreva em config/sandbox.env:
             SANDBOX_EVOLUTION_API_KEY=<a chave>
     2) rode com --whatsapp

   Sem a chave a Evolution devolve 401 e o robo AVISA que nao enviou - nunca
   finge ter enviado. Destino e instancia: FINALIZAR_WHATSAPP_DESTINO (default
   5511963226389) e a instancia `Prosperito`, a mesma do healthcheck dos
   boletos. Detalhes em scripts/sandbox/FINALIZAR_OP.md.

Uso:
    PYTHONPATH=$PWD .venv-sandbox/bin/python scripts/sandbox/finalizar_op.py
    ... scripts/sandbox/finalizar_op.py --ops 64882,64887   # ops especificas
    ... scripts/sandbox/finalizar_op.py --loop              # ciclo continuo
    ... scripts/sandbox/finalizar_op.py --whatsapp          # LIGA o aviso

Guia: scripts/sandbox/COMO_CRIAR_AUTOMACAO.md
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

#: O robo, agora versionado no repo. As dependencias que ele consome do
#: `credito` sao resolvidas pelo proprio `r7_config` (ver la o porque).
PACOTE_R7 = Path(os.environ.get(
    "R7_PACOTE_DIR", str(RAIZ / "src" / "processors" / "web" / "finalizar_operacao")))

#: Placar local: uma linha por op por execucao. E a evidencia de acuracia.
LEDGER = Path(os.environ.get(
    "FINALIZAR_LEDGER", str(RAIZ / "data" / "sandbox" / "finalizar_op" / "veredito.csv")))

#: Destino do aviso. Default = o numero do operacional (o mesmo do healthcheck).
DESTINO_WHATSAPP = os.environ.get("FINALIZAR_WHATSAPP_DESTINO", "5511963226389")

CABECALHO = ["quando", "op", "cedente", "veredito", "pagamento_conferido", "pendencias"]

#: Tabela das CONTAS a pagar - a materia-prima da remessa bancaria.
#: Uma linha por linha da grade de pagamento (uma op pode ter pagamento dividido).
CONTAS = Path(os.environ.get(
    "FINALIZAR_CONTAS",
    str(RAIZ / "data" / "sandbox" / "finalizar_op" / "contas_pagamento.csv")))

#: Ordem dos campos = a da grade do Smart, para conferencia visual lado a lado.
#: Ops cujo aviso de WhatsApp REALMENTE saiu. Separado do placar de proposito
#: - ver `_ja_avisadas`.
AVISADAS = Path(os.environ.get(
    "FINALIZAR_AVISADAS",
    str(RAIZ / "data" / "sandbox" / "finalizar_op" / "avisadas.txt")))

CAMPOS_CONTA = ["tipo", "tipo_pix", "chave_pix", "cta_origem", "numero",
                "cta_destino", "bco", "agencia", "tipo_conta", "cc",
                "favorecido", "cpf_cnpj", "id_transacao", "vencto", "valor", "sp"]
CABECALHO_CONTAS = ["quando", "op", "cedente", "linha"] + CAMPOS_CONTA


def log(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# Preparar o import do pacote do robo
# --------------------------------------------------------------------------- #
def _preparar_pacote(log=print) -> None:
    """Publica envs e sys.path para `import finalizar_operacao` funcionar.

    Chamar SO DEPOIS de `_ambiente.garantir_env()`, que e quem resolve a
    credencial do Smart.
    """
    if not PACOTE_R7.is_dir():
        raise RuntimeError(f"pacote do robo nao encontrado em {PACOTE_R7} "
                           f"(ajuste R7_PACOTE_DIR)")

    # O config do robo1 le SMART_EMAIL/SMART_SENHA; o sandbox publicou o mesmo
    # par como BOLETO_*. Uma credencial so, dois nomes.
    for destino, origem in (("SMART_EMAIL", "BOLETO_EMAIL"),
                            ("SMART_SENHA", "BOLETO_SENHA")):
        if os.environ.get(origem):
            os.environ.setdefault(destino, os.environ[origem])

    # `credito/config.py` chama `load_dotenv()`, que sobe a arvore
    # e acha o `.env` da raiz - 600 do usuario `prospere`, ILEGIVEL por nos:
    # PermissionError no import. E, mesmo legivel, puxar credencial do container
    # por engano e exatamente o que o sandbox evita (ver BOLETO_ENV_FILE no
    # _ambiente). O sandbox ja publicou tudo, entao dotenv aqui e ruido.
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False  # noqa: ARG005

    # Debug do robo vai para data/sandbox, nunca para o cwd do repo.
    debug = RAIZ / "data" / "sandbox" / "finalizar_op" / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DEBUG_DIR_R7", str(debug))

    # Um diretorio so: o `r7_config` do robo poe o `credito` no path.
    if str(PACOTE_R7) not in sys.path:
        sys.path.insert(0, str(PACOTE_R7))
    log(f"  robo: {PACOTE_R7}")


def _publicar_evolution(log=print) -> None:
    """Publica a credencial do WhatsApp lida do `config/sandbox.env`.

    O `_ambiente` publica so o que o login do Smart precisa; o canal de aviso e
    deste script. Chaves aceitas no sandbox.env:
        SANDBOX_EVOLUTION_API_URL   (default abaixo)
        SANDBOX_EVOLUTION_API_KEY
        SANDBOX_EVOLUTION_INSTANCIA (nome real, se diferir de 'Prosperito')

    ⚠️ O default NAO e o do container: `evolution-api:8080` e hostname da rede
    do Docker e nao resolve no host. Do host, a MESMA Evolution responde em
    127.0.0.1:8085 (conferido em 01/09/2026, v2.3.7).
    """
    from scripts.sandbox import _ambiente

    try:
        cfg = _ambiente._ler_env_file(_ambiente.ENV_SANDBOX)
    except Exception:  # noqa: BLE001 - sem o arquivo, seguem os defaults
        cfg = {}

    os.environ.setdefault(
        "EVOLUTION_API_URL",
        cfg.get("SANDBOX_EVOLUTION_API_URL", "http://127.0.0.1:8085"))
    if cfg.get("SANDBOX_EVOLUTION_API_KEY"):
        os.environ.setdefault("EVOLUTION_API_KEY", cfg["SANDBOX_EVOLUTION_API_KEY"])
    if cfg.get("SANDBOX_EVOLUTION_INSTANCIA"):
        os.environ.setdefault("EVOLUTION_INST_PROSPERITO_NAME",
                              cfg["SANDBOX_EVOLUTION_INSTANCIA"])

    tem = "definida" if os.environ.get("EVOLUTION_API_KEY") else "AUSENTE"
    log(f"  whatsapp: {os.environ['EVOLUTION_API_URL']} | apikey {tem} "
        f"| destino {DESTINO_WHATSAPP}")


def _travar_finalizacao(log=print) -> None:
    """Cinto de seguranca: torna a finalizacao IMPOSSIVEL, nao so desligada.

    `ciclo(executar=False)` ja nao finaliza. Isto protege contra a edicao
    futura que liga o executar sem perceber que esta no sandbox.
    """
    import finalizar as fin

    def _proibido(*_a, **_k):
        raise RuntimeError(
            "BLOQUEIO DO SANDBOX: finalizar_da_grade foi chamada. Este script "
            "nunca finaliza operacao - use o robo de producao.")

    fin.finalizar_da_grade = _proibido
    log("  trava: finalizar_da_grade substituida por stub que levanta")


# --------------------------------------------------------------------------- #
# Placar local
# --------------------------------------------------------------------------- #
def _ja_avisadas() -> set[str]:
    """Ops cujo aviso REALMENTE saiu por WhatsApp.

    ⚠️ Nao usar o `veredito.csv` para isto. Ele registra toda AVALIACAO,
    inclusive as feitas com o WhatsApp desligado - e ai uma op aprovada durante
    o periodo sem chave ja nasceria marcada como "avisada". O efeito, medido em
    02/09/2026: com 3 ops aprovadas na fila, a mensagem dizia "nenhuma operacao
    nova passaria" e a primeira mensagem real do dia sairia inutil.

    Avisado = mensagem entregue. So isso entra aqui.
    """
    if not AVISADAS.exists():
        return set()
    try:
        return {l.strip() for l in AVISADAS.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")}
    except Exception as e:  # noqa: BLE001 - arquivo ilegivel nao derruba o run
        log(f"  [!] registro de avisos ilegivel ({str(e)[:80]}) - seguindo sem deduplicar")
        return set()


def _marcar_avisadas(ops, log=print) -> None:
    """Grava as ops cujo aviso saiu. Chamar SO depois da entrega confirmada."""
    if not ops:
        return
    AVISADAS.parent.mkdir(parents=True, exist_ok=True)
    novo = not AVISADAS.exists()
    with AVISADAS.open("a", encoding="utf-8") as fh:
        if novo:
            fh.write("# ops cujo aviso de WhatsApp foi ENTREGUE (uma por linha)\n")
        for op in ops:
            fh.write(f"{op}\n")
    log(f"  marcadas como avisadas: {', '.join(ops)}")


def _gravar(laudos: list[dict]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    novo = not LEDGER.exists()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LEDGER.open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        if novo:
            w.writerow(CABECALHO)
        for l in laudos:
            w.writerow([agora, l["op"], l.get("cedente") or "", _veredito(l),
                        "" if l.get("pagamento_conferido") is None
                        else ("sim" if l.get("pagamento_conferido") else "nao"),
                        " | ".join(l.get("pendencias") or [])])


def _contas_ja_registradas() -> set[str]:
    """Ops que ja estao na tabela de contas - nao duplicar na remessa."""
    if not CONTAS.exists():
        return set()
    try:
        with CONTAS.open(encoding="utf-8", newline="") as fh:
            return {(l.get("op") or "").strip() for l in csv.DictReader(fh, delimiter=";")}
    except Exception as e:  # noqa: BLE001
        log(f"  [!] tabela de contas ilegivel ({str(e)[:80]})")
        return set()


def _gravar_contas(laudos: list[dict], log=print) -> int:
    """Registra as CONTAS das operacoes aprovadas - o insumo da remessa.

    So entram ops com veredito FINALIZARIA: sao as que vao ser pagas. Uma op
    barrada tem, por definicao, o pagamento incompleto ou errado - manda-la
    para a remessa seria pagar o que o robo acabou de reprovar.

    Grava UMA VEZ por op (dedupe pelo proprio arquivo): a foto vale do momento
    da aprovacao. Se a grade mudar depois, isso e outro evento - e a linha
    velha continua sendo o que foi aprovado.

    ⚠️ Pagamento DIVIDIDO gera varias linhas para a mesma op. A remessa tem de
    considerar todas, nao a primeira.
    """
    ja = _contas_ja_registradas()
    novas = []
    for l in laudos:
        op = str(l["op"])
        if _veredito(l) != "FINALIZARIA" or op in ja:
            continue
        linhas = (l.get("detalhes") or {}).get("linhas_pagamento") or []
        if not linhas:
            log(f"  [!] op {op} aprovada mas SEM linha de pagamento lida - nao registrei")
            continue
        for linha in linhas:
            novas.append((op, l.get("cedente") or "", linha))

    if not novas:
        return 0
    CONTAS.parent.mkdir(parents=True, exist_ok=True)
    novo = not CONTAS.exists()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with CONTAS.open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        if novo:
            w.writerow(CABECALHO_CONTAS)
        for op, cedente, linha in novas:
            w.writerow([agora, op, cedente, linha.get("_linha", "")]
                       + [linha.get(c, "") or "" for c in CAMPOS_CONTA])
    ops = sorted({op for op, _c, _l in novas})
    log(f"  contas registradas: {len(novas)} linha(s) de {len(ops)} op(s) "
        f"({', '.join(ops)}) em {CONTAS}")
    return len(novas)


def _veredito(laudo: dict) -> str:
    if laudo.get("erro"):
        return "ERRO"
    if laudo.get("pendencias"):
        return "BARRADA"
    return "FINALIZARIA"


# --------------------------------------------------------------------------- #
# Mensagem
# --------------------------------------------------------------------------- #
def _texto_whatsapp(passariam: list[dict], barradas: list[dict],
                    erros: list[dict], novas: list[dict]) -> str:
    linhas = ["🤖 *Robô Finalizar Operação* — teste em sandbox",
              "_Nenhuma operação foi finalizada._", ""]
    # Lista TODAS as aprovadas, nao so as novas: a mensagem tem de bastar por si.
    # Quem a le precisa saber o que esta pronto para pagamento AGORA - relegar as
    # ja avisadas a um parentese escondia justamente o que interessa.
    if passariam:
        ids_novas = {str(l["op"]) for l in novas}
        linhas.append(f"*{len(passariam)} operação(ões) prontas para pagamento:*")
        for l in passariam:
            ced = (l.get("cedente") or "").strip()
            # sem banco, o cedente vem vazio; o favorecido da grade identifica
            if not ced:
                pag = ((l.get("detalhes") or {}).get("linhas_pagamento") or [{}])[0]
                ced = (pag.get("favorecido") or "").strip()
            marca = " 🆕" if str(l["op"]) in ids_novas else ""
            linhas.append(f"• op {l['op']}" + (f" — {ced[:38]}" if ced else "") + marca)
    else:
        linhas.append("*Nenhuma operação passaria nas duas checagens.*")

    linhas += ["", f"Barradas: {len(barradas)} | Erros: {len(erros)}"]
    if barradas:
        linhas.append("")
        for l in barradas[:5]:
            pend = (l.get("pendencias") or ["?"])[0]
            linhas.append(f"⛔ op {l['op']}: {pend[:70]}")
        if len(barradas) > 5:
            linhas.append(f"… e mais {len(barradas) - 5}")
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# O trabalho
# --------------------------------------------------------------------------- #
def trabalho(ctx, args, log=print) -> dict:
    """Roda o ciclo do robo em DRY sobre o `ctx` ja logado do sandbox."""
    _travar_finalizacao(log=log)

    import finalizar_operacao as robo

    ops = [o.strip() for o in args.ops.split(",") if o.strip()] or None
    if ops:
        log(f"  ops informadas: {', '.join(ops)}")

    # executar=False -> DRY. mandar_email=False -> o e-mail de pendencia do
    # pacote aponta para um email_config.json de Windows; o aviso deste teste
    # sai por WhatsApp.
    laudos = robo.ciclo(ctx, ops=ops, executar=False, mandar_email=False)
    if not laudos:
        log("\n  fila vazia - nada a conferir")
        return {"ok": True, "total": 0, "passariam": 0, "avisou": False}

    passariam = [l for l in laudos if _veredito(l) == "FINALIZARIA"]
    barradas = [l for l in laudos if _veredito(l) == "BARRADA"]
    erros = [l for l in laudos if _veredito(l) == "ERRO"]

    vistas = set() if args.renotificar else _ja_avisadas()
    novas = [l for l in passariam if str(l["op"]) not in vistas]

    _gravar(laudos)
    log(f"\n  placar gravado em {LEDGER}")
    _gravar_contas(laudos, log=log)

    log(f"\n  {len(laudos)} op(s): {len(passariam)} passariam "
        f"({len(novas)} nova(s)), {len(barradas)} barradas, {len(erros)} com erro")

    avisou = False
    if not args.whatsapp:
        log("\n  WhatsApp DESLIGADO (use --whatsapp para ligar). A mensagem seria:")
        log("  " + _texto_whatsapp(passariam, barradas, erros, novas).replace("\n", "\n  "))
    elif not novas and not args.sempre_avisar:
        log("\n  nada novo para avisar (use --sempre-avisar para mandar assim mesmo)")
    else:
        from src.common.clients import whatsapp_evolution as wpp
        texto = _texto_whatsapp(passariam, barradas, erros, novas)
        n, resultados = wpp.enviar(DESTINO_WHATSAPP, texto)
        for numero, ok, detalhe in resultados:
            log(f"  whatsapp {numero}: {'OK' if ok else 'FALHOU'} - {detalhe}")
        avisou = n > 0
        # So marca depois da ENTREGA: falha de envio tem de reaparecer no
        # proximo ciclo, nao sumir por ter sido "avisada".
        if avisou:
            _marcar_avisadas([str(l["op"]) for l in novas], log=log)

    return {"ok": True, "total": len(laudos), "passariam": len(passariam),
            "novas": len(novas), "barradas": len(barradas), "erros": len(erros),
            "avisou": avisou}


# Exit codes
OK = 0
SEM_CREDENCIAL = 2
SEM_SESSAO = 3
ERRO_TRABALHO = 6
AVISO_NAO_SAIU = 7          # conferiu, mas o WhatsApp nao foi entregue


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Robo de finalizar operacao, no sandbox e SEM finalizar.")
    ap.add_argument("--ops", default="",
                    help="ops especificas (virgula). Vazio = fila da etapa")
    ap.add_argument("--whatsapp", action="store_true",
                    help="LIGA o aviso por WhatsApp (desligado por padrao; "
                         "exige SANDBOX_EVOLUTION_API_KEY - ver FINALIZAR_OP.md)")
    ap.add_argument("--sempre-avisar", action="store_true",
                    help="manda o WhatsApp mesmo sem op nova")
    ap.add_argument("--renotificar", action="store_true",
                    help="ignora o placar e trata todas as ops como novas")
    ap.add_argument("--ver-navegador", action="store_true",
                    help="mostra o Chrome (precisa do display :90 - ver README)")
    ap.add_argument("--loop", action="store_true",
                    help="repete a cada --intervalo, ate ser interrompido")
    ap.add_argument("--intervalo", type=int, default=900,
                    help="segundos entre ciclos no --loop (default 900)")
    ap.add_argument("--reciclar-apos", type=int, default=3,
                    help="ciclos por sessao antes de reabrir o Chrome (default 3; "
                         "0 = nunca reciclar, so reabre se a sessao falhar)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    log("=== ROBO FINALIZAR OPERACAO | SANDBOX | NAO FINALIZA ===")

    from playwright.sync_api import sync_playwright

    from scripts.sandbox import _ambiente

    # ORDEM CRITICA: publica as envs ANTES de qualquer import do pacote do robo.
    try:
        _ambiente.garantir_env(log=log)
        _preparar_pacote(log=log)
        _publicar_evolution(log=log)
    except _ambiente.SandboxSemCredencial as e:
        log(f"ERRO: {e}")
        return SEM_CREDENCIAL
    except Exception as e:  # noqa: BLE001
        log(f"ERRO ao preparar o pacote: {type(e).__name__}: {e}")
        return ERRO_TRABALHO

    def _uma_vez() -> int:
        with sync_playwright() as p:
            try:
                headless = False if args.ver_navegador else None
                with _ambiente.sessao(p, headless=headless, log=log) as ctx:
                    try:
                        r = trabalho(ctx, args, log=log)
                    except Exception as e:  # noqa: BLE001
                        log(f"ERRO no trabalho: {type(e).__name__}: {e}")
                        import traceback
                        traceback.print_exc()
                        return ERRO_TRABALHO
                    log(f"\nresultado: {r}")
                    if r.get("novas") and not r.get("avisou") and args.whatsapp:
                        log("AVISO: havia op nova e o WhatsApp NAO saiu.")
                        return AVISO_NAO_SAIU
                    return OK
            except _ambiente.SandboxSemSessao as e:
                log(f"ERRO: {e}")
                return SEM_SESSAO

    if not args.loop:
        return _uma_vez()

    # SESSAO SEGURADA entre ciclos, reciclando a cada --reciclar-apos.
    #
    # Por que segurar: o cookie de sessao do Smart NAO e persistente (medido em
    # 01/09/2026 - o perfil so guarda `_gcl_au` e `device_id`). Fechar o Chrome
    # desloga, e cada ciclo custaria um CapSolver.
    #
    # Por que reciclar mesmo assim: o README do robo mede que a tela da operacao
    # DEGRADA o Chrome depois de ~20 aberturas e tudo passa a dar timeout. Com
    # ~6 ops por ciclo, 3 ciclos ja chegam perto disso.
    import itertools
    import time
    ciclo = 0
    headless = False if args.ver_navegador else None
    while True:
        try:
            with sync_playwright() as p:
                with _ambiente.sessao(p, headless=headless, log=log) as ctx:
                    # 0 = sessao continua: nunca recicla por contagem. A rede de
                    # seguranca passa a ser o `break` do except abaixo - se o
                    # Chrome degradar (o README do robo mede isso depois de ~20
                    # aberturas da tela) o ciclo falha e a sessao e reaberta.
                    quantos = (itertools.count() if args.reciclar_apos <= 0
                               else range(args.reciclar_apos))
                    for _ in quantos:
                        ciclo += 1
                        log(f"\n{'#' * 60}\n#  CICLO {ciclo} | "
                            f"{datetime.now():%H:%M:%S}\n{'#' * 60}")
                        try:
                            r = trabalho(ctx, args, log=log)
                            log(f"\nresultado: {r}")
                        except Exception as e:  # noqa: BLE001
                            # Sessao caida ou tela travada: reabre o Chrome em
                            # vez de insistir num contexto que ja era.
                            log(f"CICLO {ciclo} falhou ({type(e).__name__}: "
                                f"{str(e)[:130]}) - reabrindo a sessao")
                            break
                        log(f"#  fim do ciclo {ciclo}; proximo em {args.intervalo}s")
                        time.sleep(args.intervalo)
                    else:
                        log(f"#  reciclando o Chrome apos {args.reciclar_apos} ciclo(s)")
        except KeyboardInterrupt:
            log("\ninterrompido.")
            return OK
        except Exception as e:  # noqa: BLE001 - nem sessao ruim mata o loop
            log(f"sessao falhou ({type(e).__name__}: {str(e)[:130]}); "
                f"nova tentativa em {args.intervalo}s")
            time.sleep(args.intervalo)


if __name__ == "__main__":
    sys.exit(main())
