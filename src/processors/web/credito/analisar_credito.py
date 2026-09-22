# -*- coding: utf-8 -*-
"""
analisar_credito.py - Robo 1 VERSAO 4.

V4 = V3 (conferencia expandida em TODA op com doc + analise de contrato) MAIS o
AJUSTE DE CLASSE DE RISCO dos titulos ATIVO no momento do SALVAR:
  - le a classe de risco de TODOS os titulos da operacao (botoes #classeRisco_*);
  - pela MAIORIA: maioria 'E' -> muda todos p/ 'B'; maioria 'P' -> muda todos p/ 'T';
  - se houver QUALQUER titulo em 'C' ou 'CE' -> NAO mexe na operacao;
  - aplica via SelecionarClasseRiscoMaster ANTES do clique no SALVAR (que persiste).

Diferenca p/ a V3: aqui a troca e APLICADA DE VERDADE (a V3 so loga, read-only).
Reusa TODA a logica da V3 ligando a flag CLASSE_RISCO_APLICAR=1.

Uso (rodar da RAIZ; PARAR a V3/V2 antes - mesmo perfil .perfil_chrome):
  python credito/analisar_credito.py
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

# ATIVA a aplicacao REAL da classe de risco ANTES de importar a V3
# (a V3 le a flag CLASSE_RISCO_APLICAR no momento do import).
os.environ["CLASSE_RISCO_APLICAR"] = "1"

# ATIVA o preenchimento do campo Conta quando ele chega vazio: seleciona
# «Informar posteriormente» antes do SALVAR. Mesma exigencia de ordem — o
# `conta_operacao` le CONTA_PADRAO_APLICAR no import, e a V3 o importa.
#
# ⚠️ O QUE ISTO NAO FAZ: nao destrava a op cujo SALVAR fica desabilitado. Essa
# era a hipotese original e ela foi REFUTADA em 27/08/2026 — as tres ops com
# conta vazia daquele dia (64829, 64830, 64838) salvaram normalmente, e o dia
# fechou com 8 SALVAR e ZERO botao desabilitado. A causa do travamento segue
# desconhecida.
#
# Ligado assim mesmo por decisao do dono, com o argumento de que op salva com
# conta vazia ja significa «a informar», entao tornar isso explicito nao muda o
# sentido do dado.
#
# ⚠️ Efeito colateral a vigiar: consulta que procure operacao «sem conta» por
# campo VAZIO/NULL deixa de encontrar estas — elas passam a ter valor.
#
# Conta JA preenchida nunca e tocada (regra travada em
# tests/unit/test_conta_operacao.py). Desligar = apagar esta linha.
os.environ["CONTA_PADRAO_APLICAR"] = "1"

import _analisar_credito_v3 as v3   # noqa: E402
from src.common.clients import execucao_job   # noqa: E402

# Os modos de conferencia da V3 (`--classe`, `--conta`) leem UMA operacao e nao salvam.
# Nao sao execucao de job: nao abrem linha em job_execucao.
_MODOS_DE_CONFERENCIA = ("--classe", "--conta")


def main():
    print("[V4] = V3 + ajuste de CLASSE DE RISCO ATIVO no SALVAR "
          "(maioria E->B, P->T; pula C/CE).", flush=True)
    if any(a.split("=")[0] in _MODOS_DE_CONFERENCIA for a in sys.argv[1:]):
        return v3.main()

    # A execucao cobre o PROCESSO inteiro, nao cada reinicio interno: o robo e um laco
    # de ~11h que relanca o Chrome quantas vezes precisar e so encerra no fim do
    # expediente. Enquanto ele trabalha a linha fica `ativa` — e e isso que a
    # vw_job_execucao_ativa mostra. Morreu sem fechar (timeout do hub, container
    # recriado), a vw_job_execucao_abandonada acusa depois de 2h.
    #
    # `obrigatoria=False` de proposito: o credito nao move dinheiro, e derrubar 11h de
    # trabalho porque o banco piscou as 7h seria trocar um risco pequeno (perder o
    # registro de UMA rodada) por um grande (o dia inteiro sem analise). Quem exige
    # registro sao os quatro jobs de arquivo, onde o rastro e a unica prova do que
    # foi enviado ao banco.
    execucao = execucao_job.abrir_execucao(
        "credito", "analisar_credito_operacao",
        flag_ensaio=False, obrigatoria=False,
        apelido_credencial=os.environ.get("SMART_SENHA"),
        detalhe={"classe_risco_aplicar": True, "conta_padrao_aplicar": True})
    codigo = 0
    try:
        v3.main()
    except SystemExit as e:                                    # sys.exit() da V1
        codigo = int(e.code or 0)
        raise
    except BaseException:                                      # noqa: BLE001
        codigo = 1
        raise
    finally:
        execucao_job.fechar_execucao(
            execucao, "sucesso" if codigo == 0 else "falha", codigo_saida=codigo)


if __name__ == "__main__":
    main()
