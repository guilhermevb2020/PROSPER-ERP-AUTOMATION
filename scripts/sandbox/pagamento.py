#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pagamento.py - FASE 0 do robo de pagamento, rodando no sandbox (host).

Descobre a tela Financeiro > Sistemas de pagamento > Pagamento BMP Money Plus >
Gerar Remessa: quais telas existem, que campos elas tem e se o robo sera do
molde `remessa_cobranca` (posta formulario) ou `retorno_cobranca` (conversa por `Acao`).

Escrito a partir de `_modelo_automacao.py`, como manda o COMO_CRIAR_AUTOMACAO.md:
o login, o perfil de Chrome, a deteccao de sessao morta e o video/trace vem do
`_ambiente`. Aqui so mora `trabalho()`.

E `trabalho()` NAO reimplementa a descoberta: ela delega para
`descobrir.executar(ctx, args)`, que e o codigo de PRODUCAO do robo, e cuja
leitura de tela mora no modulo puro `analise.py` (26 testes no host). Rodar aqui
e rodar o que vai para producao — muda so de onde vem o `ctx`, que e o contrato
do sandbox.

    sandbox   -> `_ambiente.sessao`      (Chromium no host, sandbox.env)
    producao  -> `smart_sessao.sessao`   (Chrome no container, robo_pagamento.env)

USO
    PYTHONPATH=$PWD .venv-sandbox/bin/python scripts/sandbox/pagamento.py --links pagamento
    PYTHONPATH=$PWD .venv-sandbox/bin/python scripts/sandbox/pagamento.py \
        --url https://wvw.smartsecurities.com.br/smart/<tela>.php

⚠️ PERMISSAO: o usuario de `config/sandbox.env` precisa alcancar a arvore de
   pagamento. Se nao alcancar, a descoberta volta "tela nao existe" quando o que
   houve foi falta de acesso — e o modo de falha que o `URL_PING` de cada robo
   existe para evitar. Por isso `trabalho()` diz, em voz alta, quando o resultado
   veio vazio.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
# O pacote do robo entra no sys.path porque `descobrir.py` importa os irmaos
# dele por nome simples (`import analise`, `import pagamento_config`) — e assim
# que os robos deste repo se organizam, e o `_AQUI` deles faz o mesmo.
ROBO = RAIZ / "src" / "processors" / "web" / "robo_pagamento"
for _caminho in (RAIZ, ROBO):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))


def log(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# ⬇⬇⬇ A parte que e deste arquivo. ⬇⬇⬇
# --------------------------------------------------------------------------- #
def publicar_env_do_host(log=print) -> None:
    """Aponta as pastas do robo para o `data/sandbox/` do host.

    `pagamento_config` resolve os caminhos NO IMPORT e o default deles e
    `/app/...`, que so existe dentro do container — no host o `ensure_dirs()`
    morre com `PermissionError: '/app'` (medido). Como a config do robo e 100%
    por env com sufixo proprio, basta redirecionar: nenhuma linha do robo muda.

    ORDEM CRITICA: isto roda ANTES de importar `descobrir` (que importa
    `pagamento_config`). E a mesma pegadinha que o `_ambiente.garantir_env`
    resolve para os boletos.
    """
    base = RAIZ / "data" / "sandbox" / "robo_pagamento"
    for chave, valor in {
        "USER_DATA_DIR_PAG": str(base / "perfil_chrome"),
        "PASTA_SAIDA_PAG": str(base / "saida"),
        "ARQ_CONTROLE_PAG": str(base / "controle_pagamentos.csv"),
        "DEBUG_DIR_PAG": str(base / "debug"),
        # o robo nunca le o .env de producao quando roda aqui
        "PAGAMENTO_ENV_FILE": os.environ.get("PAGAMENTO_ENV_FILE", "/dev/null"),
    }.items():
        os.environ.setdefault(chave, valor)   # nao sobrescreve o que veio de fora
    log(f"  pagamento: debug/HTML cru em {base / 'debug'}")


def trabalho(ctx, args, log=print) -> dict:
    """Recebe um `ctx` JA LOGADO e roda a descoberta de producao.

    `descobrir.executar` ja checa `parece_deslogado` em todo ponto que le
    resposta do Smart (regra 2 do COMO_CRIAR_AUTOMACAO), e trata corpo vazio
    como deslogado (regra 3) — porque usa o `smart_sessao.parece_deslogado`
    compartilhado, e nao uma heuristica propria.
    """
    publicar_env_do_host(log=log)

    # import preguicoso: `pagamento_config` resolve os caminhos no import
    import descobrir                                              # noqa: E402

    codigo = descobrir.executar(ctx, args)
    if codigo == descobrir.SAIU_NADA_ACHADO:
        log("")
        log("  NADA ACHADO. Antes de concluir que a tela nao existe, confira se o")
        log(f"  usuario do sandbox ({os.environ.get('BOLETO_EMAIL', '?')}) tem acesso")
        log("  a Financeiro > Sistemas de pagamento. Sem permissao, a resposta e")
        log("  indistinguivel de 'tela vazia' — e essa confusao e a armadilha nº 1.")
    return {"ok": codigo == descobrir.SAIU_OK, "codigo": codigo}
# --------------------------------------------------------------------------- #
# ⬆⬆⬆ FIM. ⬆⬆⬆
# --------------------------------------------------------------------------- #


# Exit codes. `ERRO_TRABALHO` e o "fez pela metade" que a regra 5 pede; a
# descoberta acrescenta o `NADA_ACHADO`, que NAO e falha: e resultado.
OK = 0
SEM_CREDENCIAL = 2
SEM_SESSAO = 3
ERRO_TRABALHO = 6
NADA_ACHADO = 7


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fase 0 do robo de pagamento, no sandbox do host.")
    ap.add_argument("--links", nargs="?", const="pagamento", metavar="TERMO",
                    help="lista os links .php da semente que casam com TERMO "
                         "(padrao: 'pagamento'). NAO visita nenhum.")
    ap.add_argument("--url", help="analisa ESTA tela")
    ap.add_argument("--seguir", action="store_true",
                    help="visita os links que casaram (um nivel, so GET). "
                         "E o passo com efeito possivel: em ERP, link de grade "
                         "as vezes E acao. Por isso e opt-in, como manda a "
                         "regra 4 do COMO_CRIAR_AUTOMACAO.")
    ap.add_argument("--semente", default="",
                    help="ponto de partida (padrao: o do pagamento_config)")
    ap.add_argument("--filtrar", action="store_true",
                    help="submete o form de BUSCA da tela de --url. E o unico "
                         "POST da descoberta, e so passa em form com `pesquisar` "
                         "(as travas vivem em analise.montar_filtro).")
    ap.add_argument("--conta", default="",
                    help="com --filtrar: valor de IdContaBancaria")
    ap.add_argument("--status", default="",
                    help="com --filtrar: valor de pagtobmp (P=Pendente, "
                         "G=Gerado, R=Rejeitado)")
    ap.add_argument("--baixar", default="", metavar="ID",
                    help="baixa `mandarsispag.php?file=ID` e relata o layout. "
                         "So leitura — download nao gera nada.")
    ap.add_argument("--gerar", action="store_true",
                    help="fluxo fechado: pesquisa PENDENTE, seleciona todos, "
                         "monta o POST de geracao e (com --pra-valer) gera e "
                         "baixa o arquivo")
    ap.add_argument("--pra-valer", action="store_true",
                    help="com --gerar: ENVIA de verdade. Gera remessa de "
                         "PAGAMENTO — irreversivel. Sem isto, so mostra o corpo.")
    ap.add_argument("--ver-navegador", action="store_true",
                    help="mostra o Chrome (precisa do display :90 — ver README)")
    args = ap.parse_args()

    if not args.links and not args.url and not args.filtrar and not args.baixar and not args.gerar:
        args.links = "pagamento"      # o padrao util: listar sem visitar nada

    from playwright.sync_api import sync_playwright
    from scripts.sandbox import _ambiente

    # ORDEM CRITICA: publica as envs do sandbox ANTES de qualquer import de
    # `boletos.*`/`smart_sessao` (o _config resolve credencial no import).
    try:
        _ambiente.garantir_env(log=log)
    except _ambiente.SandboxSemCredencial as e:
        log(f"ERRO: {e}")
        return SEM_CREDENCIAL

    # a semente so pode ser lida depois das envs publicadas
    if not args.semente:
        publicar_env_do_host(log=lambda _m: None)
        import pagamento_config as cfg                             # noqa: E402
        args.semente = cfg.URL_SEMENTE

    log(f"── sandbox pagamento | FASE 0 (descoberta, so leitura) ──")

    with sync_playwright() as p:
        try:
            headless = False if args.ver_navegador else None
            with _ambiente.sessao(p, headless=headless, log=log) as ctx:
                try:
                    resultado = trabalho(ctx, args, log=log)
                except Exception as e:                              # noqa: BLE001
                    log(f"ERRO no trabalho: {type(e).__name__}: {e}")
                    return ERRO_TRABALHO
                log(f"\nresultado: {resultado}")
                return OK if resultado["ok"] else NADA_ACHADO
        except _ambiente.SandboxSemSessao as e:
            log(f"ERRO: {e}")
            return SEM_SESSAO


if __name__ == "__main__":
    sys.exit(main())
