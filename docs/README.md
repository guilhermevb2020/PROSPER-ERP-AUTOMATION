# Documentação do erp-automation

Índice do que está vivo. O que descrevia a era 2025 (processadores, stack
antibot, host sem Docker) mora em [`deprecated/`](deprecated/README.md) e não
vale mais como instrução.

## Operar

- [COMO_SUBIR_UM_ROBO.md](COMO_SUBIR_UM_ROBO.md) — a receita para criar e publicar um robô: slots de display, wrapper do hub, exit code, task, teste supervisionado, e as armadilhas medidas
- [CREDENCIAIS_GUARDIAN.md](CREDENCIAIS_GUARDIAN.md) — como o container recebe credenciais (apelidos, login efêmero, SMTP pelo broker) e como operar o Guardian
- [CONVENCOES_PORTAS.md](CONVENCOES_PORTAS.md) — portas e displays
- [hub_orchestration_API.md](hub_orchestration_API.md) — a API do hub para disparar e consultar tasks

## Robôs

Cada robô documenta a si mesmo em `src/processors/web/<robo>/docs/README.md`.
Guia geral dos boletos: [BOLETOS_LOTE.md](BOLETOS_LOTE.md).

## O que foi validado, e os limites

- [VALIDACAO_ERP_2026-09-07.md](VALIDACAO_ERP_2026-09-07.md) — matriz de validação após o Guardian
- [VALIDACAO_FERIADO_2026-09-07.md](VALIDACAO_FERIADO_2026-09-07.md) e [VALIDACAO_OITO_HORAS_2026-09-07.md](VALIDACAO_OITO_HORAS_2026-09-07.md) — as rodadas reais e o que cada uma prova
- [AUDITORIA_CREDENCIAIS_2026-09-07.md](AUDITORIA_CREDENCIAIS_2026-09-07.md) — a limpeza de credenciais em configuração, logs e histórico

## Em andamento

- [NOTIFICACOES.md](NOTIFICACOES.md) — notificações dos robôs (em revisão)
