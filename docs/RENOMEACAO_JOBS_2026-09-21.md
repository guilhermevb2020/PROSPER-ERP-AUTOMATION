# Renomeação dos jobs — 21/09/2026

**Por quê.** O dicionário do Learn (15–24/08/2026) aposentou "robô": a unidade que o hub
dispara é um *job*, nomeado por **verbo no infinitivo + objeto**; o fluxo a que ele pertence
é a *automação* (o nome da pasta). As tasks do hub já obedeciam
(`processar_retorno_cobranca_cnab_400`, `gerar_remessa_bb`…); as pastas e os arquivos de
entrada não. Apontado pela Gerência em 21/09/2026 ("`robo_retorno` viola a regra").

## De-para

| automação | pasta | entrada (o que o wrapper roda) | env em `config/` |
|---|---|---|---|
| retorno de cobrança | `robo_retorno` → `retorno_cobranca` | `robo_retorno.py` → `processar_retorno_cobranca.py` | `robo_retorno[.example].env` → `retorno_cobranca[.example].env` |
| retorno de pagamento | `robo_retorno_pagamento` → `retorno_pagamento` | `robo_retorno_pagamento.py` → `processar_retorno_pagamento.py` | `robo_retorno_pagamento.env` → `retorno_pagamento.env` |
| remessa de cobrança | `robo_remessa` → `remessa_cobranca` | `robo_remessa.py` → `gerar_remessa_cobranca.py` | `robo_remessa[.example].env` → `remessa_cobranca[.example].env` |
| remessa de pagamento | `robo_pagamento` → `remessa_pagamento` | `robo_pagamento.py` → `gerar_remessa_pagamento.py` | `robo_pagamento[.example].env` → `remessa_pagamento[.example].env` |
| crédito | `robo_credito` → `credito` | `robo_analise_credito_v4.py` → `analisar_credito.py`; `_v3.py` → `_analisar_credito_v3.py`; `robo_analise_credito.py` → `_analisar_credito_base.py` (módulos privados: a v4 é a única entrada pública) | `robo_credito.env` → `credito.env` |
| finalizar operação | `robo_finalizar` → `finalizar_operacao` | `robo_finalizar.py` → `finalizar_operacao.py` | `robo_finalizar[.example].env` → `finalizar_operacao[.example].env` |

Também: `scripts/mover_estado_robo_credito.sh` → `mover_estado_credito.sh`;
`tests/unit/test_pagamento_robo.py` → `test_gerar_remessa_pagamento.py`;
`docs/COMO_SUBIR_UM_ROBO.md` → `COMO_SUBIR_UM_JOB.md`. Os wrappers (`run_*.sh`), os
`<pasta>_config.py` e os módulos puros mantêm o nome.

## No hub (fora deste repositório)

| task | o que mudou |
|---|---|
| 14 tasks com caminho `robo_*` no comando (10 ligadas, 4 aposentadas) | só `comando`, `entrypoint` e `source_ref` trocaram de caminho; cron, timeout, retries, pré-condição e taxonomia ficaram iguais, provado por diff campo a campo antes/depois |
| `analisar_credito_operacao` | **criada** como cópia de `robo_analise_credito` (cron `*/15 7-18 * * 1-5`, pré-condição 07:45–18:15 apontando para o nome novo, timeout 12 h) |
| `robo_analise_credito` | aposentada: desligada, `lifecycle_state=retired`, `replacement_task=analisar_credito_operacao`; o histórico de execuções fica sob o nome antigo |
| `robo_retorno_pagamento` (já desligada, duplicata) | aposentada com `replacement_task=processar_retorno_pagamento_cnab_240` |
| `state/operator_tasks.json` (lista que o operador pode religar) | `robo_analise_credito` → `analisar_credito_operacao` (o authz lê o arquivo a quente) |

⚠️ **Armadilha do hub, medida em 21/09/2026.** `run.py tasks upsert-docker` sobrescreve
**todos** os campos da task (`ON CONFLICT DO UPDATE SET … = EXCLUDED.…`) e grava
`concurrency_key = nome`. Para mudar só o comando é preciso reenviar cada campo como está,
e `gerar_remessa_cobranca_cnab_400` e `cancelar_remessa_recusada_cnab_400` compartilham a
chave `smart_remessa_financeiro`: ela foi restaurada por SQL logo após o reenvio e conferida.
Não há `delete` nem `rename` na CLI: renomear task é criar a nova e aposentar a velha.

## O que NÃO mudou, de propósito

- **Caminhos de estado e de log**: `data/robo_*`, `logs/robo_*_<data>.log`,
  `data/sandbox/robo_pagamento`. São armazenamento, não nome de job; renomear moveria perfis
  de Chrome logados e CSVs de controle. Fica para uma janela própria.
- **Nomes de variáveis de ambiente** (`DRY_RUN_RET`, `USER_DATA_DIR_PAG`, `R7_*`…). O retorno
  roda com dry-run desligado em produção (ACHADO-123); uma variável renomeada cairia no
  default sem erro (LIC-058).
- Displays e portas VNC; `TRAVA_SMART_FINANCEIRO`.
- Docs datados (`VALIDACAO_*`, `AUDITORIA_*`, `docs/deprecated/`) guardam os nomes da época.
- Comentários dentro dos `config/*.env` reais (modo 600, de operacional2) ainda citam os
  nomes velhos: são comentários.

## Prova

- Suíte no host: 6 failed, 634 passed, 18 skipped, 4 warnings in 2.95s (as 6 falhas em `test_doc2you_fluxo` são anteriores à renomeação).
- Dentro do container, o que está em execução (LIC-056): `grep -rE 'robo_…' /app/src
  /app/config` só devolve comentários e caminhos de dados.
- Import dos 10 módulos (as 6 entradas, a cadeia v4 → v3 → base do crédito, `listar_fila`
  e `placar`) dentro do container: ok. `sh -n` nos 11 wrappers: ok.
- Nada em voo no hub no momento da troca (21/09, ~22:50); primeira execução real com os
  nomes novos é o crédito às 07:45 de 22/09.

## Como foi feito (para a próxima vez)

- Um alvo por vez: `git mv` da pasta, da entrada e do `.example.env`; `mv` do `.env` real;
  substituição por regex em bytes (CRLF preservado) sobre os arquivos rastreados, com guardas
  para `data/`, `logs/`, `sandbox/` e distinguindo módulo de pasta (`x.py`, `import x`,
  `import_module("x")`). Nome antigo sai sem alias (DEC-030).
- Duas pastas são de operacional2: rodar sob `sg proj-erp-automation`. Um arquivo de root
  (`remessa_pagamento/_nextcloud.py`, 644) não aceita escrita no lugar e interrompeu uma
  passada no meio: foi trocado por cópia do grupo (664). Conferir `git ls-files | xargs ls -l
  | awk '$3=="root"'` antes.
- Teste que fazia `import robo_pagamento` sem alias usava o nome depois: virou o nome da
  pasta e quebrou com `NameError`. Procurar o identificador bare, não só `nome.`.

## Sobras para uma próxima passada

- `robo_smart_ativo()` em `boletos/healthcheck.py` (nome de função) e as expressões
  "Robô 7" / "Robo 1" em prosa e docstrings; `r7_config.py`.
- `data/robo_*` e `logs/robo_*` (ver acima).
- `hub-orchestration` (docs, testes, comentários) e `access-guardian` (comentários em
  `projetos.yaml`, nota em `contas.yaml`) ainda citam `robo_analise_credito` e `robo_credito`.
