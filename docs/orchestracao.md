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

## Recursos: o que é próprio e o que é compartilhado

**Próprio de cada robô** — display Xvfb, perfil do Chrome e porta CDP. Não é
preciosismo: dois Chromes no mesmo display fazem o login *quicar* de volta para a
landing, e dois no mesmo `user-data-dir` disputam o lock. A tabela de alocação
está em
[`COMO_SUBIR_UM_ROBO.md`](COMO_SUBIR_UM_ROBO.md#1-reserve-o-slot--display-portas-e-perfil).

**Compartilhado** — a sessão do Smart por usuário, a conta do CapSolver e o
próprio container: `docker compose up -d` derruba todos os robôs em execução, e
nem todos voltam sozinhos.

## Subir um robô novo

Receita de ponta a ponta, com as armadilhas medidas em subidas reais:
[`COMO_SUBIR_UM_ROBO.md`](COMO_SUBIR_UM_ROBO.md).
