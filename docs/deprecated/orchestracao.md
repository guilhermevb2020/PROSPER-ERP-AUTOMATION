# Orquestração dos robôs

Quem agenda os robôs deste container é o **`hub-orchestration`** (tabela
`hub_orchestration.task_config`, no `prosperedb`) — **não** o
`config/processors.yaml`, que este documento apontava como fonte de verdade
enquanto era um rascunho. O hub guarda cron, timeout, retries e, a cada execução,
exit code, log e duração.

```bash
# o que está agendado aqui
docker exec postgres psql -U prospere -d prosperedb -c \
  "SELECT nome, cron, enabled, timeout_seconds FROM hub_orchestration.task_config
   WHERE container='erp-automation' ORDER BY nome;"

# o que rodou hoje
docker exec postgres psql -U prospere -d prosperedb -c \
  "SELECT task_nome, status, inicio::time(0), fim::time(0), exit_code
   FROM hub_orchestration.task_execucao
   WHERE inicio::date = current_date ORDER BY inicio;"
```

## Quem roda quando

Reconstruído em 21/08/2026 a partir dos READMEs de cada robô — **a fonte de
verdade é o hub** (`hub_orchestration.task_config`, consulta acima). Confira lá
antes de escolher o cron de um robô novo.

| Hora (dias úteis) | Task | Display | Duração típica |
|---|---|---|---|
| `*/15 * * * *` | `boletos_healthcheck` | `:99` | segundos — só religa a sessão |
| `30 7` | `baixar_documentos_doc2you` | `:98` | 15–28 min |
| `45 7` | robô de crédito | `:96` | **fica de pé até 18:50** (para sozinho) |
| `30 8` | `processar_retornos_cnab` | `:95` | minutos, cresce com a fila de `.RET` |
| `30 9` | `emitir_lote_boletos` | `:99` | — |
| `0 10` | `enviar_lote_boletos` | `:99` | — |
| `0 18` | robô de remessa | `:97` | ~20 min |
| `0 19` | `baixar_documentos_doc2you_antecipado` | `:98` | 15–28 min |
| *(não agendado)* | `gerar_remessa_pagamento_bmp` | `:94` | segundos — validada, **aguarda registro no hub** |

> **`gerar_remessa_pagamento_bmp` está validada e ainda não está no hub**
> (25/08/2026). O login definitivo foi provado: alcança a tela **e** a conta 404,
> e a tela devolveu o botão «Gerar». O que falta é **registrar a task**, e isso
> exige `docker exec hub-orchestration ... tasks upsert-docker` — que a conta
> `operacional2` não tem, e não vai ter (o grupo `docker` é root sem senha).
>
> **A API HTTP do hub não substitui o CLI para isto:** ela tem `trigger`,
> `GET /api/tasks`, `status` e `history`, mas **nenhum endpoint que crie ou
> altere task**; e o compose faz `expose` sem publicar porta, então nem do host
> se alcança. Escrever direto em `hub_orchestration.task_config` também não — a
> role `app_erp_automation` é confinada ao schema `erp_automation`.
>
> ⛔ **Isso é um PEDIDO a quem administra o hub, não um problema a contornar.**
> Em 25/08 foi montado um agendamento na crontab do próprio `operacional2` e o
> dono **recusou**: sai do padrão das outras 9 automações e fica fora do
> inventário de tasks e do registro de exit code/log/duração. Se um
> `scripts/crontab_operacional2.txt` reaparecer, alguém refez esse raciocínio sem
> ler isto. O comando do pedido está em
> [`robo_pagamento/docs/PENDENTE.md`](../src/processors/web/robo_pagamento/docs/PENDENTE.md).
>
> Três coisas dela que não se parecem com nenhuma outra automação daqui:
>
> - **É a primeira cadência de 30 minutos**, e por isso o wrapper dela é o único
>   com **trava de sobreposição**. Sem ela, uma rodada longa seria morta pela
>   seguinte entre o gerar e o gravar — remessa órfã no Smart.
> - **Cada rodada custa um CapSolver.** Medido em 21/08: a sessão do Smart não
>   sobrevive ao fechamento do Chrome, então o perfil persistente não a reusa.
>   Com `*/30 7-20`, são ~28 CAPTCHAs/dia.
> - **É a única que loga com usuário PRÓPRIO** (`prosperito_financeiro@`), e não
>   com o `prosperito@` compartilhado pelas outras cinco. Efeito colateral bom:
>   não disputa sessão com ninguém.
>
> Ver [`robo_pagamento/docs/README.md`](../src/processors/web/robo_pagamento/docs/README.md)
> e o que falta em [`PENDENTE.md`](../src/processors/web/robo_pagamento/docs/PENDENTE.md).

**O que roda simultâneo, na prática:**

- **O de crédito atravessa o dia** (07:45 → 18:50). Ele se sobrepõe a *todos* os
  outros: doc2you das 07:30, retorno das 08:30, os dois de boletos e a remessa
  das 18:00. Qualquer robô novo em horário comercial vai rodar junto com ele.
- **07:30–07:58**: doc2you e crédito juntos.
- **18:00–18:20**: remessa e crédito juntos.
- **19:00**: doc2you antecipado praticamente sozinho — o crédito já parou e o
  healthcheck dos boletos só re-loga entre 7h e 18h.
- As duas tasks do doc2you dividem o `:98` e **por isso** estão em pontas opostas
  do dia: nunca podem se cruzar.

**Isso é seguro porque display, perfil e porta CDP são próprios de cada robô.**
O que é compartilhado e não escala igual:

- **O usuário do Smart — é UM só, `prosperito@prospereinvest.com.br`.** Não são
  contas dedicadas por automação: conferido nos arquivos de credencial em
  21/08/2026, os cinco robôs logam com a mesma conta.

  | Robô | Onde a credencial é lida | Valor |
  |---|---|---|
  | boletos | `config/boletos.env` → `BOLETO_EMAIL` | `prosperito@…` |
  | robo_credito | `config/robo_credito.env` → `SMART_EMAIL` | `prosperito@…` |
  | robo_remessa | `config/robo_remessa.env` → `REMESSA_EMAIL` | `prosperito@…` |
  | robo_retorno | `config/robo_retorno.env` → `RETORNO_EMAIL` | `prosperito@…` |
  | doc2you | `DOC2YOU_LOGIN` do ambiente, senão `config/credentials.csv` | `prosperito@…` no CSV — **confirmar se o `.env` sobrepõe** |

  Consequências que valem para qualquer robô novo:

  - **A janela de acesso 06:30–21:00 seg–sex é dessa conta**, e um cron fora dela
    faz o `dologin.php` responder `2|Usuário com acesso restrito.` — em qualquer
    robô, não só no doc2you.
  - **Mexer nessa conta (senha, permissão, horário) atinge todos os robôs de uma
    vez.** Não existe raio de dano de um robô só.
  - Ela fica logada em paralelo por até cinco robôs ao longo do dia (o
    `manter_sessao` dos boletos segura uma sessão o dia inteiro). Vem
    funcionando, mas é convivência observada, não garantia do Smart: rode o
    primeiro teste de um robô novo **fora** do horário do crédito.
  - **Menções a `Raphaelas`, `envioboletos` ou `felipe_p`** em comentário ou
    README deste repo são **anteriores** à unificação — não são a conta em uso.
    O `robo_credito/config.py` lê `SMART_EMAIL` **puro**: rodado à mão sem
    carregar `config/robo_credito.env`, ele pega o `SMART_EMAIL` do container
    (`felipe_p`), não o `prosperito`. Só o `run_agendado.sh` faz o `set -a`.
- **A conta do CapSolver** e o próprio container.

---

## Recursos: o que é próprio e o que é compartilhado

**Próprio de cada robô** — display Xvfb, perfil do Chrome e porta CDP. Não é
preciosismo: dois Chromes no mesmo display fazem o login *quicar* de volta para a
landing, e dois no mesmo `user-data-dir` disputam o lock. A tabela de alocação
está em
[`COMO_SUBIR_UM_JOB.md`](COMO_SUBIR_UM_JOB.md#1-reserve-o-slot--display-portas-e-perfil).

**Compartilhado** — a sessão do Smart por usuário, a conta do CapSolver e o
próprio container: `docker compose up -d` derruba todos os robôs em execução, e
nem todos voltam sozinhos.

## Subir um robô novo

Receita de ponta a ponta, com as armadilhas medidas em subidas reais:
[`COMO_SUBIR_UM_JOB.md`](COMO_SUBIR_UM_JOB.md).
