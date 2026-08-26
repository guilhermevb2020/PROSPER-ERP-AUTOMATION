# -*- coding: utf-8 -*-
"""
robo_retorno.py - processa os arquivos de RETORNO (CNAB) no Smart.

Robo do ERP AUTOMATION. Roda DESATENDIDO: sobe o proprio Chrome no display :95,
loga via CapSolver, le os .RET da pasta de entrada e roda, para cada um, a mesma
sequencia que a tela "Financeiro > CNAB > Processar Retorno" faz — mas por HTTP,
sem abrir tela nenhuma (o contrato das chamadas esta em `retorno.py`).

Bonus de nao usar a tela: some o "Debugger pausado em outra guia" que trava o
processamento quando o Playwright esta anexado via CDP (o Chrome trata a conexao
como depurador e qualquer `debugger;` no JS congela a pagina).

SEGURANCA
---------
- DRY_RUN e o padrao. Ele vai ate o UPLOAD (valida banco/conta, monta a grade e
  conta os titulos) e PARA antes do PROCESSAR_ARQUIVO — que e quem da a baixa.
- Identidade do arquivo e o MD5 do CONTEUDO, nunca o nome. Chega arquivo com o
  mesmo nome no mesmo dia e conteudo diferente, e ele TEM que ser processado
  como novo; o `VERIFICAR_ARQUIVO_PROCESSADO` do Smart olha so o nome e diria
  "ja processado".
- Conta nao cadastrada faz a tela PERGUNTAR se prossegue. Sem gente, o robo pula
  e reporta (ligue --aceitar-conta-desconhecida se a resposta for "sim").
- Sessao caida ABORTA a rodada — nunca segue reportando "nada a fazer".
- Timeout NAO e deslogado: o Smart fica lento depois de processar, e o ping
  estourando nao significa sessao morta (ver smart_sessao.sessao_viva).

Uso:
    # producao (o wrapper do hub chama isto)
    sh /app/src/processors/web/robo_retorno/run_agendado.sh

    # manual, dentro do container
    docker exec -e PYTHONPATH=/app erp-automation \\
      python /app/src/processors/web/robo_retorno/robo_retorno.py --limite 3 --detalhes
    ... robo_retorno.py --pra-valer --csv-titulos /app/data/robo_retorno/titulos.csv
"""
import argparse
import csv
import os
import shutil
import sys
import time
from datetime import datetime

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from playwright.sync_api import sync_playwright  # noqa: E402

import retorno as ret                             # noqa: E402
import retorno_config as cfg                      # noqa: E402
from src.common.clients import smart_sessao       # noqa: E402

CABECALHO = ["arquivo", "nome_smart", "hash", "conta", "titulos", "ja_processado",
             "processado", "ocorrencias", "criticas", "divergencias",
             "motivo", "quando"]
COLUNAS_CRITICA = ["arquivo", "conta", "numTitulo", "banco", "nomeBanco",
                   "agencia", "pracaPagto", "tipoCritica1", "tipoCritica2"]

# Codigos de saida (o hub marca a execucao pelo exit code).
SAIU_OK = 0
SAIU_SEM_NAVEGADOR = 1
SAIU_SEM_SESSAO = 2
SAIU_SMART_MUDO = 3
SAIU_PASTA_INVALIDA = 4
SAIU_COM_PENDENCIA = 6


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# controle
# --------------------------------------------------------------------------- #
def gravar_controle(registro):
    """Anexa uma linha no controle.

    CUIDADO (bug ja pego uma vez): se o CSV foi criado por uma versao ANTIGA,
    com menos colunas, anexar linhas novas desalinha o arquivo inteiro — o
    cabecalho diz 8 campos e a linha traz 12. Por isso, quando o cabecalho do
    disco nao bate com o CABECALHO atual, arquiva o antigo e comeca um novo.
    """
    os.makedirs(os.path.dirname(cfg.ARQ_CONTROLE) or ".", exist_ok=True)
    existe = os.path.exists(cfg.ARQ_CONTROLE)
    if existe:
        try:
            with open(cfg.ARQ_CONTROLE, encoding="utf-8", newline="") as f:
                atual = next(csv.reader(f), [])
            if atual and atual != CABECALHO:
                velho = f"{cfg.ARQ_CONTROLE}.{datetime.now():%Y%m%d%H%M%S}.bak"
                os.rename(cfg.ARQ_CONTROLE, velho)
                log(f"  (controle com cabecalho antigo -> arquivado em {velho})")
                existe = False
        except Exception as e:
            log(f"  (aviso ao conferir cabecalho do controle: {e})")
    with open(cfg.ARQ_CONTROLE, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECALHO, extrasaction="ignore")
        if not existe:
            w.writeheader()
        w.writerow(registro)


def _gravar_titulos(caminho, res):
    linhas = res.get("detalhes") or []
    if not linhas:
        return
    campos = ["arquivo", "conta"] + list(linhas[0].keys())
    novo = not os.path.exists(caminho)
    with open(caminho, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        if novo:
            w.writeheader()
        for t in linhas:
            w.writerow({"arquivo": res["arquivo"], "conta": res.get("conta"), **t})


def _gravar_criticas(caminho, res):
    criticas = res.get("criticas") or []
    if not criticas:
        return
    novo = not os.path.exists(caminho)
    with open(caminho, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_CRITICA, extrasaction="ignore")
        if novo:
            w.writeheader()
        for c in criticas:
            w.writerow({"arquivo": res["arquivo"], "conta": res.get("conta"), **c})


def historico_controle():
    """Le o controle -> (hashes ja processados, nome_smart -> {hashes vistos}).

    Serve a regra do negocio: arquivo com o MESMO NOME e conteudo DIFERENTE tem
    que ser processado como NOVO. Como o Smart so compara nome, quem sabe
    diferenciar e o hash guardado aqui.
    """
    hashes, por_nome = set(), {}
    if not os.path.exists(cfg.ARQ_CONTROLE):
        return hashes, por_nome
    try:
        with open(cfg.ARQ_CONTROLE, encoding="utf-8", newline="") as f:
            for linha in csv.DictReader(f):
                h = (linha.get("hash") or "").strip()
                nome = (linha.get("nome_smart") or "").strip()
                if not h:
                    continue
                if str(linha.get("processado", "")).lower() == "true":
                    hashes.add(h)
                por_nome.setdefault(nome, set()).add(h)
    except Exception as e:
        log(f"  (aviso ao ler o controle: {e})")
    return hashes, por_nome


# --------------------------------------------------------------------------- #
# relato de UM arquivo
# --------------------------------------------------------------------------- #
def arquivar(caminho, dry):
    """Tira da entrada o .RET que FOI PROCESSADO -> `_PROCESSADOS/<AAAA-MM>/`.

    Tres cuidados que a decisao exige:

    1. **So move quem processou de verdade.** Em DRY_RUN a pasta nao e tocada —
       um ensaio nunca pode mexer na caixa de entrada de producao.
    2. **Falha nao move.** Fica na entrada, visivel, e a proxima rodada tenta de
       novo. Mover erro para um canto e o jeito de ele nunca mais ser visto.
    3. **Nunca sobrescreve no destino.** Nome repetido com conteudo diferente e
       caso REAL aqui (e a razao de a identidade ser o hash); o que ja esta
       arquivado e a prova do que foi processado, entao o novo ganha sufixo.

    Se o move falhar DEPOIS de processar, o arquivo volta a ser candidato na
    proxima rodada. Quem protege disso e o controle por hash — por isso o
    comando agendado usa `--pular-processados`.
    """
    if dry or not cfg.MOVER_PROCESSADOS:
        return None
    # 4. ⛔ NAO tenta arquivar o que veio de pasta SOMENTE LEITURA. Desde
    #    26/08/2026 o `run_agendado.sh` aponta o robo para
    #    `/app/data/cnab_nextcloud/Retornos`, que e o groupfolder do Nextcloud
    #    montado `rw=false`. Ali o `shutil.move` falha sempre, e como isso
    #    acontece DEPOIS de a baixa ter sido dada, cada arquivo geraria um
    #    "AVISO: processou mas NAO consegui arquivar" — um por arquivo, 82 na
    #    rodada de 26/08. Aviso que sai sempre e aviso que ninguem le.
    #
    #    ⭐ E arquivar dali nao faria sentido nem se desse: a arvore do Nextcloud
    #    JA E o arquivo morto, organizada por ano/mes/dia/banco pelo
    #    `organizar_remessas`. Quem protege contra reprocessar e o controle por
    #    hash, nao o move.
    #
    #    ⚠️ Por isso `MOVER_PROCESSADOS_RET=False` no env NAO e anomalia a
    #    consertar: e o valor certo enquanto a origem for a arvore. Esta guarda
    #    existe para o dia em que alguem o ligar de volta olhando so o default
    #    do codigo.
    origem_dir = os.path.dirname(caminho) or "."
    if not os.access(origem_dir, os.W_OK):
        return None
    destino_dir = os.path.join(cfg.PASTA_PROCESSADOS, datetime.now().strftime("%Y-%m"))
    nome = os.path.basename(caminho)
    destino = os.path.join(destino_dir, nome)
    try:
        os.makedirs(destino_dir, exist_ok=True)
        if os.path.exists(destino):
            base, ext = os.path.splitext(nome)
            destino = os.path.join(destino_dir, f"{base}_{datetime.now():%H%M%S}{ext}")
        shutil.move(caminho, destino)
        return destino
    except OSError as e:
        log(f"            AVISO: processou mas NAO consegui arquivar ({e}). "
            "O arquivo segue na entrada — rode com --pular-processados para "
            "nao reprocessar.")
        return None


def relatar(res, args, dry):
    """Loga o que o Smart vai fazer (ou fez) com o arquivo."""
    acoes = res.get("acoes") or {}
    if acoes:
        log("            acoes: " + ", ".join(f"{k}={v}" for k, v in acoes.items()))
    ocor = res.get("ocorrencias") or {}
    if ocor:
        log("            RESULTADO: " + ", ".join(f"{k}={v}" for k, v in ocor.items()))
    fora = res.get("fora_ok") or []
    if fora:
        log(f"            ATENCAO: {len(fora)} titulo(s) com status != OK")
        for t in fora[:5]:
            log(f"              {t.get('numero_titulo','?'):12} "
                f"{t.get('acao_tomada','?'):26} status={t.get('status','?')}")
    for aviso in (res.get("divergencias") or []):
        log(f"            DIVERGENCIA: {aviso}")
    if res.get("criticas"):
        log(f"            criticas: {len(res['criticas'])}")
        for c in res["criticas"][:3]:
            log(f"              titulo {c.get('numTitulo','?'):10} "
                f"banco {c.get('banco','?')} {c.get('nomeBanco','')[:18]:18} "
                f"ag {c.get('agencia','?'):6} {c.get('pracaPagto','')}")
        if len(res["criticas"]) > 3:
            log(f"              ... (+{len(res['criticas']) - 3}; use --csv-criticas)")
    if args.detalhes:
        for t in (res.get("detalhes") or []):
            log(f"              {t.get('numero_titulo','?'):12} "
                f"venc={t.get('vencimento','?'):10} "
                f"R$ {t.get('valor_titulo','?'):>12} "
                f"pago={t.get('valor_pago','?'):>10} "
                f"{t.get('acao_tomada','?'):26} {t.get('status','?')}")


# --------------------------------------------------------------------------- #
# rodada
# --------------------------------------------------------------------------- #
def rodada(ctx, args, dry):
    """Percorre os arquivos alvo. Retorna o exit code."""
    if args.arquivo:
        alvos = [args.arquivo]
    else:
        alvos = sorted(f for f in os.listdir(args.pasta) if f.upper().endswith(".RET"))
    if args.limite:
        alvos = alvos[:args.limite]
    if not alvos:
        log(f"nenhum .RET em {args.pasta}")
        return SAIU_OK

    log("=" * 66)
    log(f"{'DRY_RUN (nao processa)' if dry else '*** PRA VALER - VAI DAR BAIXA ***'}"
        f"  |  {len(alvos)} arquivo(s)")
    log("=" * 66)

    hashes_feitos, hashes_por_nome = historico_controle()
    resultados, abortou = [], False

    for i, nome in enumerate(alvos, 1):
        caminho = os.path.join(args.pasta, nome)
        if not os.path.exists(caminho):
            log(f"  [{i}/{len(alvos)}] {nome}: nao encontrado")
            continue
        try:
            res = ret.processar(
                ctx, caminho, dry_run=dry,
                pular_se_processado=args.pular_processados,
                aceitar_conta_desconhecida=args.aceitar_conta_desconhecida,
                hashes_ja_feitos=hashes_feitos)
        except ret.ErroRetorno as e:
            res = {"arquivo": nome, "nome_smart": ret.nome_limpo(caminho),
                   "conta": None, "titulos": 0, "ja_processado": False,
                   "processado": False, "motivo": str(e)}
            if "sessao do Smart caiu" in str(e):
                log(f"  [{i}/{len(alvos)}] {nome}: {e}")
                log("ABORTANDO: a sessao morreu no meio da rodada.")
                resultados.append(res)
                abortou = True
                break
        except Exception as e:                                      # noqa: BLE001
            res = {"arquivo": nome, "nome_smart": ret.nome_limpo(caminho),
                   "conta": None, "titulos": 0, "ja_processado": False,
                   "processado": False,
                   "motivo": f"{type(e).__name__}: {str(e)[:120]}"}

        marca = ("PROCESSADO" if res["processado"]
                 else ("dry-run" if dry and not res["motivo"].startswith(
                     ("ja ", "arquivo", "conta")) else "pulado"))
        log(f"  [{i}/{len(alvos)}] {res['arquivo']:24} conta={str(res['conta'] or '-'):>5} "
            f"titulos={res['titulos']:<4} {marca:11} {res['motivo']}")

        vistos = hashes_por_nome.get(res.get("nome_smart"), set())
        if res.get("hash") and vistos and res["hash"] not in vistos:
            log(f"            NOME REPETIDO com CONTEUDO DIFERENTE -> arquivo "
                f"NOVO (hash {res['hash'][:8]})")
        if res.get("hash"):
            hashes_por_nome.setdefault(res.get("nome_smart"), set()).add(res["hash"])
            if res.get("processado"):
                hashes_feitos.add(res["hash"])

        relatar(res, args, dry)
        if args.csv_titulos and res.get("detalhes"):
            _gravar_titulos(args.csv_titulos, res)
        if args.csv_criticas and res.get("criticas"):
            _gravar_criticas(args.csv_criticas, res)

        res["quando"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linha = {k: res.get(k, "") for k in CABECALHO}
        linha["ocorrencias"] = "; ".join(
            f"{k}={v}" for k, v in (res.get("ocorrencias") or {}).items())
        linha["criticas"] = len(res.get("criticas") or [])
        linha["divergencias"] = "; ".join(res.get("divergencias") or [])
        # o controle vem ANTES de mover: se o move falhar, o registro ja existe
        gravar_controle(linha)
        if res.get("processado"):
            destino = arquivar(caminho, dry)
            if destino:
                res["arquivado_em"] = destino
                log(f"            arquivado -> {os.path.relpath(destino, args.pasta)}")
        resultados.append(res)
        if args.pausa and i < len(alvos):
            time.sleep(args.pausa)

    # ----------------------------------------------------------------------- #
    log("=" * 66)
    processados = [r for r in resultados if r["processado"]]
    com_erro = [r for r in resultados if not r["processado"] and r["motivo"]
                and not r["motivo"].startswith("DRY_RUN")
                and r["motivo"] != ret.MOTIVO_JA_PROCESSADO]
    titulos = sum(r["titulos"] for r in resultados)
    log(f"RESUMO: {len(resultados)} arquivo(s) | {len(processados)} processado(s) | "
        f"{titulos} titulo(s) no total")

    total_ocor = {}
    for r in resultados:
        for k, v in (r.get("ocorrencias") or {}).items():
            try:
                total_ocor[k] = total_ocor.get(k, 0) + int(v)
            except (TypeError, ValueError):
                total_ocor[k] = total_ocor.get(k, 0)
    if total_ocor:
        log("  ocorrencias: " + ", ".join(
            f"{k}={v}" for k, v in sorted(total_ocor.items(), key=lambda x: -x[1])))

    n_crit = sum(len(r.get("criticas") or []) for r in resultados)
    if n_crit:
        arq_crit = sum(1 for r in resultados if r.get("criticas"))
        log(f"  criticas: {n_crit} em {arq_crit} arquivo(s)"
            + (f" -> {args.csv_criticas}" if args.csv_criticas
               else "  (use --csv-criticas p/ detalhar)"))
    div = [(r["arquivo"], d) for r in resultados for d in (r.get("divergencias") or [])]
    if div:
        log(f"  DIVERGENCIAS grade x contador: {len(div)}")
        for arq, d in div:
            log(f"    {arq:24} {d}")
    if com_erro:
        log(f"  {len(com_erro)} com aviso/erro:")
        for r in com_erro:
            log(f"    {r['arquivo']:24} {r['motivo']}")
    if dry:
        log("(DRY_RUN: nada foi processado. Use --pra-valer quando quiser valer.)")

    # Sai != 0 quando a rodada ficou incompleta ou algo pede gente.
    if abortou or (not dry and com_erro):
        return SAIU_COM_PENDENCIA
    return SAIU_OK


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def montar_parser():
    ap = argparse.ArgumentParser(description="Processa retornos CNAB no Smart.")
    ap.add_argument("--pasta", default=cfg.PASTA_ENTRADA,
                    help=f"pasta dos .RET (padrao: {cfg.PASTA_ENTRADA})")
    ap.add_argument("--arquivo", help="processa so este arquivo (nome dentro da pasta)")
    ap.add_argument("--limite", type=int, help="processa no maximo N arquivos")
    ap.add_argument("--pra-valer", action="store_true",
                    help="desliga o DRY_RUN: PROCESSA de verdade (da baixa)")
    ap.add_argument("--pular-processados", action="store_true",
                    help="pula arquivo cujo CONTEUDO (hash) ja consta processado")
    ap.add_argument("--aceitar-conta-desconhecida",
                    action="store_true", default=cfg.ACEITAR_CONTA_DESCONHECIDA,
                    help="segue mesmo quando o retorno nao casa com conta cadastrada")
    ap.add_argument("--pausa", type=float, default=cfg.PAUSA_ENTRE_ARQUIVOS,
                    help=f"segundos entre arquivos (padrao {cfg.PAUSA_ENTRE_ARQUIVOS})")
    ap.add_argument("--detalhes", action="store_true",
                    help="mostra TITULO A TITULO (acao tomada / status / valor)")
    ap.add_argument("--csv-titulos", help="grava os titulos detalhados neste CSV")
    ap.add_argument("--csv-criticas", help="grava as criticas neste CSV")
    ap.add_argument("--cdp", action="store_true",
                    help="usa um Chrome JA ABERTO (dev/VNC) em vez de subir o proprio")
    return ap


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                               # noqa: BLE001
        pass

    args = montar_parser().parse_args()
    dry = cfg.DRY_RUN and not args.pra_valer

    if not os.path.isdir(args.pasta):
        log(f"ERRO: pasta nao existe: {args.pasta}")
        return SAIU_PASTA_INVALIDA
    log(f"pasta   : {args.pasta}")
    log(f"controle: {cfg.ARQ_CONTROLE}")

    with sync_playwright() as p:
        try:
            with smart_sessao.sessao(p, cfg, usar_cdp=args.cdp, log=log) as ctx:
                # Timeout NAO e deslogado — o Smart fica lento depois de
                # processar. So aborta quando a RESPOSTA diz que caiu.
                estado = smart_sessao.sessao_viva(ctx, cfg, log=log)
                if estado == "deslogado":
                    log("ERRO: a sessao do Smart nao esta logada.")
                    return SAIU_SEM_SESSAO
                if estado is None:
                    log("ERRO: nao consegui falar com o Smart. Rede? Smart fora? "
                        "(isto NAO quer dizer deslogado)")
                    return SAIU_SMART_MUDO
                log("sessao do Smart OK (logada).")
                return rodada(ctx, args, dry)
        except smart_sessao.SemSessao as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_SESSAO
        except smart_sessao.SemNavegador as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_NAVEGADOR


if __name__ == "__main__":
    sys.exit(main())
