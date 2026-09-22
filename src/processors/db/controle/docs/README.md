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

**Testes.** `tests/unit/test_comparar_controle_csv_banco.py` (lógica, sem banco) e
`tests/integration/test_erp_005_controle.py::test_consulta_da_paridade_acha_o_arquivo_do_dia`
(a consulta, na bancada).
