# erp-automation

Jobs que operam o Smart Securities (o ERP da Prospere) e o doc2you: emitem e
enviam boletos, baixam documentos, analisam crédito, geram e processam remessas
e retornos bancários (CNAB-400 de cobrança, CNAB-240 de pagamento, BB) e
finalizam operações. Rodam com Playwright/Chrome dentro do container
`erp-automation`, disparados pelo `hub-orchestration`.

## Como está organizado

```
src/processors/web/<job>/   um job por pasta: run_agendado.sh, <job>_config.py,
                             módulo puro (testável sem navegador), docs/README.md
src/common/clients/          o que é compartilhado: sessão do Smart, Nextcloud, WhatsApp
config/                      processors.yaml e os robo_*.env (gitignored, apelidos do Guardian)
database/                    migrations do schema erp_automation, com o ledger de aplicação
scripts/sandbox/             rodar os jobs no host, contra o Smart real, com identidade própria
tests/unit, tests/integration  suíte automatizada (pytest); nenhum teste fala com o Smart
docs/                        guias vivos; docs/deprecated/ é história (2025)
data/, logs/                 saída dos jobs: perfis de Chrome, boletos, prints, CSVs; fora do git
```

| job | o que faz | task no hub |
|---|---|---|
| `boletos/` | emite e envia boletos em lote, mantém a sessão do Smart, healthcheck a cada 15 min | `emitir_lote_boletos*`, `enviar_lote_boletos`, `boletos_healthcheck` |
| `doc2you/` | baixa os documentos do dia (e o antecipado) e sobe ao Nextcloud | `baixar_documentos_doc2you*` |
| `credito/` | análise de crédito das operações | `analisar_credito_operacao` |
| `remessa_cobranca/` | remessa de cobrança CNAB-400 e BB; cancela remessa recusada | `gerar_remessa_cobranca_cnab_400`, `gerar_remessa_bb`, `cancelar_remessa_recusada_cnab_400` |
| `retorno_cobranca/` | processa retornos de cobrança CNAB-400 e BB; baixa depósito no ERP | `processar_retorno_cobranca_cnab_400`, `processar_retorno_bb`, `baixar_deposito_no_erp` |
| `remessa_pagamento/` | remessa de pagamento CNAB-240 (BMP Money Plus), a cada 5 min | `gerar_remessa_pagamento_cnab_240` |
| `retorno_pagamento/` | retorno de pagamento CNAB-240 | `processar_retorno_pagamento_cnab_240` |
| `finalizar_operacao/` | confere documentos e grade de pagamento e finaliza a operação (em DRY) | `finalizar_operacao_aguardando_assinatura` |

## Rodar

```bash
# como o hub faz, à mão
docker exec erp-automation sh /app/src/processors/web/<job>/run_agendado.sh

# testes, no host
PYTHONPATH=$PWD .venv-sandbox/bin/pytest

# ver a task no hub
docker exec hub-orchestration python run.py tasks show <task>
```

O código de `src/`, `config/`, `data/` e `logs/` entra no container por bind
mount: arquivo salvo vale na próxima execução. Recriar o container só entre
19:05 e 07:30 (`docs/COMO_SUBIR_UM_JOB.md`, §8).

## Credenciais

Nenhuma senha real fica neste repositório nem nos `config/*.env`: o container
recebe apelidos que o proxy do Access Guardian troca na saída, e o banco é
acessado por login efêmero. Como funciona e como operar:
`docs/CREDENCIAIS_GUARDIAN.md`.

## Ver um job trabalhando

Cada job tem um display virtual e um noVNC próprios (tabela em
`docs/COMO_SUBIR_UM_JOB.md`). Só a porta 6080 (boletos) é publicada; para os
outros, túnel ssh ao IP do container: `ssh -L 6087:<ip-do-container>:6087 prospere@192.168.50.5`
e `http://localhost:6087/vnc.html`.

## Documentação

- `docs/COMO_SUBIR_UM_JOB.md` — a receita para criar e publicar um job, com as armadilhas medidas
- `docs/CREDENCIAIS_GUARDIAN.md` — credenciais, apelidos e o que nunca pode entrar em arquivo
- `docs/CONVENCOES_PORTAS.md`, `docs/BOLETOS_LOTE.md`, `docs/hub_orchestration_API.md`
- `docs/VALIDACAO_*_2026-09-07.md` — o que foi validado em produção e os limites de cada prova
- `CLAUDE.md` — as regras para quem programa aqui, humano ou IA
- `docs/deprecated/` — a era 2025 (processadores, stack antibot, host sem Docker); removida do código em 21/09/2026
