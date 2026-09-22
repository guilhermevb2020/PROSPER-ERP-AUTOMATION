# Documentação do erp-automation

Índice do que está vivo. O que descrevia a era 2025 (processadores, stack
antibot, host sem Docker) mora em [`deprecated/`](deprecated/README.md) e não
vale mais como instrução.

## Operar

- [COMO_SUBIR_UM_JOB.md](COMO_SUBIR_UM_JOB.md) — a receita para criar e publicar um job: slots de display, wrapper do hub, exit code, task, teste supervisionado, e as armadilhas medidas
- [RENOMEACAO_JOBS_2026-09-21.md](RENOMEACAO_JOBS_2026-09-21.md) — de-para dos nomes dos jobs (`robo_*` → automação / verbo+objeto; logs sem `robo_` desde 22/09), o que ainda falta (pastas `data/robo_*`) e as armadilhas do hub
- [CREDENCIAIS_GUARDIAN.md](CREDENCIAIS_GUARDIAN.md) — como o container recebe credenciais (apelidos, login efêmero, SMTP pelo broker) e como operar o Guardian
- [CONVENCOES_PORTAS.md](CONVENCOES_PORTAS.md) — portas e displays
- [hub_orchestration_API.md](hub_orchestration_API.md) — a API do hub para disparar e consultar tasks
- [PLANO_CONTROLE_NO_BANCO.md](PLANO_CONTROLE_NO_BANCO.md) — o banco como fonte única do controle dos jobs: **concluído em 22/09/2026** (nenhum job lê nem grava CSV de controle); as fases, as provas de cada uma e o que ainda fica em JSON
- [../database/README.md](../database/README.md) — as migrations do schema `erp_automation` (`erp_004` a `erp_008`) e como aplicar com credencial temporária

## Jobs

Cada job documenta a si mesmo em `src/processors/web/<job>/docs/README.md` (jobs sem navegador: `src/processors/db/<job>/docs/README.md`, como a auditoria diária do controle).
Guia geral dos boletos: [BOLETOS_LOTE.md](BOLETOS_LOTE.md).

## O que foi validado, e os limites

- [ESTUDO_SESSOES_SMART_2026-09-22.md](ESTUDO_SESSOES_SMART_2026-09-22.md) — sessões do Smart entre rodadas: quem loga a cada rodada (finalizador: 44 logins CapSolver/dia), o que já reaproveita, o que derruba sessão de `prosperito@`, defeitos do mantenedor e a ordem recomendada (mantenedor por identidade + CDP)
- [VALIDACAO_ERP_2026-09-07.md](VALIDACAO_ERP_2026-09-07.md) — matriz de validação após o Guardian; no anexo, o estado de 07/09 que ficava no `CLAUDE.md`
- [VALIDACAO_FERIADO_2026-09-07.md](VALIDACAO_FERIADO_2026-09-07.md) e [VALIDACAO_OITO_HORAS_2026-09-07.md](VALIDACAO_OITO_HORAS_2026-09-07.md) — as rodadas reais e o que cada uma prova
- [AUDITORIA_CREDENCIAIS_2026-09-07.md](AUDITORIA_CREDENCIAIS_2026-09-07.md) — a limpeza de credenciais em configuração, logs e histórico

## Em andamento

- [NOTIFICACOES.md](NOTIFICACOES.md) — notificações dos jobs (em revisão)
