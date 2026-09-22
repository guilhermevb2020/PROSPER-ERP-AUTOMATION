# -*- coding: utf-8 -*-
"""
conta_operacao.py - hook PRE-SALVAR: destrava a operacao cujo campo Conta esta vazio.

O PROBLEMA, medido nos logs
---------------------------
Quando a operacao chega na edicao com o campo **Conta** ainda em «Selecione a
conta», o Smart mantem o `#SalvarOperacaoButton` DESABILITADO. O robo espera 8s,
desiste e segue:

    [salvar] botao continua desabilitado p/ op 62932; seguindo

A operacao nao e salva, nao muda de etapa e **volta na proxima varredura** — a op
62932 aparece 11 vezes nos logs de 20 a 26/08. Nao e uma falha barulhenta: o
ciclo termina com cara de sucesso e a op fica parada indefinidamente.

A CORRECAO
----------
Antes do clique no SALVAR, se — e SOMENTE se — a Conta estiver no placeholder,
seleciona «Informar posteriormente», que e a opcao que o proprio Smart oferece
para esse caso. O `onchange` do campo e disparado, o Smart reabilita o botao, e o
fluxo de sempre segue.

⛔ A REGRA QUE NAO PODE SER QUEBRADA: conta JA PREENCHIDA nunca e tocada. Se a op
   ja aponta para «Caixa» ou «Banco do Brasil Prospere», o hook nao faz nada.
   Trocar a conta de uma operacao e mexer em para onde o dinheiro vai — e isso
   nao e trabalho de robo. Por isso a decisao mora em `decidir_conta()`, que e
   funcao PURA e tem teste (`tests/unit/test_conta_operacao.py`).

Segue o mesmo desenho do ajuste de classe de risco (`robo_analise_credito_v3`):
best-effort (nunca derruba o robo) e **desligado por padrao** — com
`CONTA_PADRAO_APLICAR=0` ele so registra no log o que faria.
"""
import os
import time

# Ligar a aplicacao REAL: CONTA_PADRAO_APLICAR=1. Padrao = so LOG (read-only),
# igual a CLASSE_RISCO_APLICAR. Ver o rollout no README do robo.
APLICAR = os.getenv("CONTA_PADRAO_APLICAR", "0").strip().lower() in (
    "1", "true", "sim", "yes", "on")

# Texto da opcao a escolher quando a conta esta vazia. Por env para o dia em que
# o Smart renomear o rotulo — sem precisar de deploy de codigo.
ALVO = os.getenv("CONTA_PADRAO_TEXTO", "informar posteriormente").strip().lower()

# Como reconhecer "nenhuma conta escolhida". O value vazio e o sinal forte; o
# texto e o reforco para o caso de o Smart usar um value tipo "0" no placeholder.
PLACEHOLDER = "selecione a conta"

# O grid da edicao carrega por ajax: quanto esperar o <select> aparecer.
ESPERA_S = int(os.getenv("CONTA_ESPERA_S", "12"))


# --------------------------------------------------------------------------- #
# decisao — PURA (sem Playwright, sem rede). E o que tem teste.
# --------------------------------------------------------------------------- #
def decidir_conta(opcoes, valor_atual, texto_atual):
    """Decide se ha algo a fazer no campo Conta, e o que.

    `opcoes`: lista de dicts {"value": str, "texto": str}, na ordem da tela.
    `valor_atual` / `texto_atual`: o que esta selecionado agora.

    Devolve `(valor_alvo, motivo)`. `valor_alvo` e None quando NAO se deve mexer
    — e nesse caso `motivo` explica porque, para o log.
    """
    atual_txt = (texto_atual or "").strip().lower()
    atual_val = (valor_atual or "").strip()

    # 1) Conta ja escolhida -> NAO MEXE. E a regra mais importante deste modulo.
    vazio = (not atual_val) or atual_val == "0" or atual_txt == PLACEHOLDER
    if not vazio:
        return None, f"conta ja preenchida ('{texto_atual}') -> nao mexe"

    # 2) Achar a opcao alvo pelo TEXTO, nao por value: o value e um id do banco e
    #    muda entre ambientes; o rotulo e o que o usuario ve na tela.
    for op in opcoes or []:
        if ALVO in (op.get("texto") or "").strip().lower():
            valor = (op.get("value") or "").strip()
            if not valor:
                # Opcao existe mas sem value: selecionar nao mudaria nada, e o
                # botao continuaria desabilitado. Melhor dizer isso no log.
                return None, f"opcao '{op.get('texto')}' existe mas tem value vazio"
            return valor, f"conta vazia -> selecionar '{op.get('texto')}'"

    return None, (f"conta vazia, mas nenhuma opcao casa com '{ALVO}' "
                  f"(opcoes: {[o.get('texto') for o in opcoes or []]})")


# --------------------------------------------------------------------------- #
# tela — o que fala com o Playwright
# --------------------------------------------------------------------------- #
_JS_LER = """
() => {
  // Acha o <select> da Conta pelo CONTEUDO, nao por id: o id nao esta
  // documentado em lugar nenhum deste repo e o rotulo, sim (esta na tela).
  // Criterio: um <select> que ofereca a opcao alvo.
  const alvo = %s;
  const selects = [...document.querySelectorAll('select')];
  for (const s of selects) {
    const opcoes = [...s.options].map(o => ({value: o.value, texto: o.text}));
    if (!opcoes.some(o => (o.texto || '').trim().toLowerCase().includes(alvo)))
      continue;
    return {
      achou: true,
      id: s.id || s.name || '(sem id)',
      valor_atual: s.value,
      texto_atual: s.selectedIndex >= 0 ? s.options[s.selectedIndex].text : '',
      opcoes: opcoes,
    };
  }
  return {achou: false};
}
"""

_JS_APLICAR = """
(args) => {
  const [id, valor] = args;
  const s = document.getElementById(id)
        || document.querySelector(`select[name="${id}"]`);
  if (!s) return 'select sumiu da tela';
  s.value = valor;
  if (s.value !== valor) return 'o value nao colou (opcao removida?)';
  // O Smart reabilita o SALVAR no onchange. Sem disparar o evento, o campo fica
  // visualmente certo e o botao continua desabilitado — que e o bug original.
  s.dispatchEvent(new Event('input',  {bubbles: true}));
  s.dispatchEvent(new Event('change', {bubbles: true}));
  return 'ok';
}
"""


def _frame_da_conta(page):
    """Acha o frame que tem o <select> da Conta. A edicao do Smart usa iframes."""
    js = _JS_LER % repr(ALVO).replace("'", '"')
    for fr in page.frames:
        try:
            r = fr.evaluate(js)
            if r and r.get("achou"):
                return fr, r
        except Exception:
            continue
    return None, None


def ajustar_conta(page_edit, op):
    """Hook pre-salvar: destrava a op cuja Conta esta em «Selecione a conta».

    Best-effort — qualquer erro vira log e o robo segue, exatamente como o hook
    de classe de risco. Nunca levanta.
    """
    fr = leitura = None
    fim = time.time() + ESPERA_S
    while time.time() < fim:
        fr, leitura = _frame_da_conta(page_edit)
        if fr:
            break
        time.sleep(1)

    if not fr:
        print(f"  [conta op {op}] campo Conta nao encontrado na tela -> pula")
        return

    valor_alvo, motivo = decidir_conta(
        leitura.get("opcoes"), leitura.get("valor_atual"), leitura.get("texto_atual"))

    if not valor_alvo:
        print(f"  [conta op {op}] {motivo}")
        return

    if not APLICAR:
        print(f"  [conta op {op}] [DRY conta] {motivo} "
              f"(CONTA_PADRAO_APLICAR=0; nao aplicado)")
        return

    try:
        r = fr.evaluate(_JS_APLICAR, [leitura.get("id"), valor_alvo])
    except Exception as e:
        print(f"  [conta op {op}] erro ao aplicar: {e}")
        return

    if r == "ok":
        print(f"  [conta op {op}] APLICADO: {motivo}")
    else:
        print(f"  [conta op {op}] NAO aplicado: {r}")
