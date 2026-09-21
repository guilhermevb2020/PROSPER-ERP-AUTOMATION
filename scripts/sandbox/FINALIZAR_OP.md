# Robô de finalizar operação — teste no sandbox

Confere cada operação na etapa **"Aguardando Ass."** e diz quais **seriam
finalizadas**. Registra as **contas a pagar** das aprovadas. **Não finaliza nada.**

> ⛔ **Este script nunca finaliza**, e isso não é só o default: não existe flag
> que ligue a finalização, e `finalizar.finalizar_da_grade` é substituída por um
> stub que levanta exceção se alguém a chamar. Finalizar de verdade é o robô de
> produção, depois da subida por [`docs/COMO_SUBIR_UM_ROBO.md`](../../docs/COMO_SUBIR_UM_ROBO.md).

---

## Rodar

```bash
cd /home/prospere/docker/automation/erp-automation
V="PYTHONPATH=$PWD .venv-sandbox/bin/python"

$V scripts/sandbox/finalizar_op.py                    # uma passada na fila
$V scripts/sandbox/finalizar_op.py --ops 65059        # operações específicas
$V scripts/sandbox/finalizar_op.py --loop             # ciclo contínuo (15 min)
```

No `--loop`, a sessão do Chrome é **mantida entre ciclos** e reciclada a cada 3
(`--reciclar-apos`). São duas restrições reais puxando em sentidos opostos:

- o cookie de sessão do Smart **não é persistente** (medido em 01/09/2026 — o
  perfil guarda só `_gcl_au` e `device_id`), então fechar o Chrome desloga e
  cada ciclo custaria um CapSolver;
- a tela da operação **degrada o Chrome depois de ~20 aberturas** e tudo passa a
  dar timeout — com ~6 ops por ciclo, 3 ciclos já chegam perto.

---

## O que ele grava

### `data/sandbox/finalizar_op/veredito.csv` — o placar

Uma linha por operação por execução: `FINALIZARIA`, `BARRADA` ou `ERRO`, com as
pendências. É a evidência de acurácia para decidir se o robô pode sair do DRY.

### `data/sandbox/finalizar_op/contas_pagamento.csv` — as contas a pagar

```
quando;op;cedente;linha;tipo;tipo_pix;chave_pix;cta_origem;numero;cta_destino;
bco;agencia;tipo_conta;cc;favorecido;cpf_cnpj;id_transacao;vencto;valor;sp
```

Os 16 campos da grade do Smart, na mesma ordem da tela.

**Só entram operações aprovadas.** Uma op barrada tem, por definição, pagamento
incompleto ou errado — mandá-la para a remessa seria pagar exatamente o que o
robô acabou de reprovar.

**Uma gravação por operação**, com dedupe pelo próprio arquivo. Sem isso, a cada
ciclo a mesma op entraria de novo e a remessa pagaria em duplicidade. A foto vale
do momento da aprovação.

⚠️ **Pagamento dividido gera várias linhas para a mesma op** — a coluna `linha`
distingue. Quem gerar a remessa tem de considerar todas, não a primeira.

Caminho configurável por `FINALIZAR_CONTAS`. Hoje aponta para `data/sandbox/`
de propósito: é teste, e não deve ser confundido com dado de produção.

---

## WhatsApp — desligado, e como ligar depois

Hoje o robô **só grava e imprime**. A mensagem que sairia aparece no log a cada
ciclo, então dá para conferir o texto sem enviar nada.

Para ligar o aviso — *"estas operações foram finalizadas e estão prontas para
pagamento"*:

**1. Obter a chave.** Está no `.env` da raiz, que é `600` do usuário `prospere` —
a conta de desenvolvimento não lê. É a mesma `EVOLUTION_API_KEY` que o
[`healthcheck` dos boletos](../../src/processors/web/boletos/healthcheck.py) já
usa dentro do container. Peça a quem tem o acesso.

**2. Escrever em `config/sandbox.env`** (gitignored):

```
SANDBOX_EVOLUTION_API_KEY=<a chave>
```

**3. Rodar com `--whatsapp`:**

```bash
$V scripts/sandbox/finalizar_op.py --loop --whatsapp
```

### O que já está pronto

| item | estado |
|---|---|
| URL da API | `http://127.0.0.1:8085` — a Evolution v2.3.7 responde no host |
| instância | `Prosperito`, resolvida por `EVOLUTION_INST_PROSPERITO_NAME` |
| destino | `5511963226389` (`FINALIZAR_WHATSAPP_DESTINO`) |
| módulo | [`whatsapp_evolution.py`](../../src/common/clients/whatsapp_evolution.py) |

> ⚠️ De **dentro do container** a URL é `http://evolution-api:8080` — esse
> hostname é da rede do Docker e não resolve no host. Por isso o sandbox usa a
> 8085. Quem for subir para produção usa a do container.

### O que NÃO foi testado

O **envio real nunca aconteceu** — sem a chave, o transporte fica sem prova de
ponta a ponta. Testados foram os caminhos de erro: sem chave e com chave inválida
(401), ambos falhando fechado com diagnóstico claro.

Também não dá para saber se a instância `Prosperito` está **pareada** no
WhatsApp sem a chave (a consulta responde 401). Se estiver desconectada, o envio
falha mesmo com a chave certa. Isso só se descobre no primeiro disparo.

### Deduplicação do aviso

Uma op aprovada é anunciada **uma vez**. O controle é o `veredito.csv`:
`--renotificar` ignora o placar e trata todas como novas; `--sempre-avisar` manda
a mensagem mesmo sem op nova.

---

## Armadilhas medidas em 01/09/2026

**Operação aberta em outra sessão trava a checagem de pagamento.** O
`#btnPagamento` fica `disabled` — existe no DOM, visível, sem nada por cima, mas
não clicável — e o clique morre por timeout de 15s. Produziu 2 `ERRO` na mesma
op que minutos depois passou sem problema. **Não deixe a operação aberta no Smart
enquanto o ciclo roda.** O robô ainda reporta isso como `Locator.click: Timeout`,
mensagem que não diz nada; corrigir isso é item da subida para produção.

**O banco de origem não é alcançável daqui.** O `config.py` que veio com o pacote
aponta para `192.168.50.5:5432`. O robô degrada bem (funciona sem banco), mas o
`cedente` sai **vazio** — no placar e na mensagem. O nome do **favorecido**, esse
sim, vem da grade de pagamento e está correto.

**Login custa CapSolver.** Uma credencial por abertura de Chrome. Ver a seção
`--loop` acima.
