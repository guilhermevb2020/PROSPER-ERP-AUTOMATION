# controle — paridade CSV × banco (`comparar_controle_csv_banco`)

**O que faz.** Uma vez por dia útil compara, por família, o que entrou nos CSVs de
controle dos quatro jobs de arquivo com o que entrou em `erp_automation.arquivo`, e sai
com exit 3 se algo só existe de um lado. É a Fase 0 de
[`docs/PLANO_CONTROLE_NO_BANCO.md`](../../../../../docs/PLANO_CONTROLE_NO_BANCO.md): o
CSV só pode ser cortado depois de semanas com as duas fontes iguais, medidas todo dia.

| família | CSV (variável que o job usa) | `arquivo.tipo_arquivo` |
|---|---|---|
| retorno | `ARQ_CONTROLE_RET` → `data/robo_retorno/controle_processados.csv` (`hash`, `quando`) | `retorno_cobranca_cnab_400`, `retorno_bb` |
| remessa | `ARQ_CONTROLE` → `data/robo_remessa/controle_remessas.csv` (`md5`, `baixado_em`) | `remessa_cobranca_cnab_400`, `remessa_bb` |
| pagamento | `ARQ_CONTROLE_PAG` → `data/robo_pagamento/controle_pagamentos.csv` (`md5`, `quando`) | `remessa_pagamento_cnab_240` |
| retorno_pagamento | `ARQ_CONTROLE_RETPAG` → `data/robo_retorno_pagamento/controle.csv` (`hash`, `quando`) | `retorno_pagamento_cnab_240` |

**Chave e dia.** A chave é o md5 do conteúdo, que os dois lados guardam (`detalhe_json.md5`;
coluna gerada `md5` a partir da `erp_005`). O dia é a data local do container
(`America/Sao_Paulo`): linhas do CSV cujo `quando`/`baixado_em` começa pelo dia, e no banco
os arquivos **registrados no dia ou com evento no dia** — um `.RET` re-entregue (o portão
BB recusa os mesmos todo dia) tem linha nova no CSV e uma só em `arquivo`, do primeiro dia.
Linha do CSV sem hash é contada e mostrada, não comparada.

**Como roda.** Sem navegador, sem display, sem trava do Smart; só lê. Registra a própria
execução em `job_execucao` (automação `controle`, `obrigatoria=False`: sem banco, avisa).

```bash
# à mão, como o hub
docker exec erp-automation sh /app/src/processors/db/controle/run_agendado.sh [--dia AAAA-MM-DD] [--json]
# hub: task comparar_controle_csv_banco, 19:35 em dia útil, timeout 300 s
```

**Exit codes.** `0` paridade · `3` divergência (o hub alerta; o output lista o que só existe
de um lado) · `1` erro de leitura (sem banco, CSV ilegível).

**O que fazer com uma divergência.** "Só no CSV" = o job gravou o CSV e não o banco (ver o
aviso `[execucao]` no log daquele job — degradou sem banco, ou a migration não tinha
chegado). "Só no banco" = o contrário, ou um arquivo registrado por caminho novo (ex.:
descarte de remessa, que nunca entrou no CSV — esperado a partir da `erp_005`, e a lista
mostra o nome para conferir). Nunca "corrigir" apagando: evento não se apaga; o CSV é
histórico.

**O que fazer com uma execução abandonada.** O relatório lista o que `vw_job_execucao_abandonada`
mostra (execução `ativa` além do limite da automação: processo morto, ou fechamento perdido —
desde 22/09/2026 o fechamento nunca derruba o job, e a linha fica `ativa` de propósito). Cada uma
conta como divergência (exit 3) **todo dia, até ser encerrada**. Apure o que houve (log do job,
hub, carga histórica se faltou arquivo) e encerre com autor e motivo:
`docker exec -e ERP_OPERADOR=nome -e ERP_MOTIVO="..." erp-automation python
/app/src/processors/db/controle/encerrar_abandonada.py <id> --pra-valer`. Grava `abandonada`
(nunca `sucesso`: a ferramenta não prova o que o processo fez), e quem/por quê ficam no
`detalhe_json` da linha. Nunca `UPDATE` à mão.

**Testes.** `tests/unit/test_comparar_controle_csv_banco.py` (lógica, sem banco) e
`tests/integration/test_erp_005_controle.py::test_consulta_da_paridade_acha_o_arquivo_do_dia`
(a consulta, na bancada).

## Também nesta pasta

- `listar_md5.py` — a memória "já processei" para o wrapper do retorno (`CONTROLE_FONTE_RET=banco`): imprime um md5 por linha; exit 1 = volte ao CSV.
- `encerrar_abandonada.py` — encerra, com `ERP_OPERADOR`/`ERP_MOTIVO`, UMA execução que a `vw_job_execucao_abandonada` lista (o único caminho para fechar uma execução de fora dela). **Ensaio por padrão** (só mostra a linha); `--pra-valer` grava `abandonada` e registra a própria execução (`controle/encerrar_execucao_abandonada`). Exit 2 = faltou operador/motivo; 3 = não está abandonada (nada a fazer). Teste: `tests/unit/test_encerrar_abandonada.py`.
- `carregar_remessas_historicas.py` — carga histórica das remessas de cobrança (45 dias) a partir do `controle_remessas.csv` e dos `.REM` na árvore do Nextcloud montada em `/app/data/cnab_nextcloud/Remessas`; confere md5, pula o que já está (sha256), registra com a data de então. **Ensaio por padrão**; `--pra-valer` registra. Pré-requisito para `CONTROLE_FONTE_REM=banco`. Exit 3 = faltou arquivo ou md5 divergiu (lista no stdout).
