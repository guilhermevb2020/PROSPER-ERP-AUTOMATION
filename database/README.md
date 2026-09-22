# `database/` — a DDL deste projeto mora aqui

Até 12/08/2026 este repositório **não tinha nenhuma infraestrutura de DDL**: zero
`.sql`, zero runner, zero ledger. As tabelas que ele escreve eram criadas por
migrations de **outro** repositório (`process-automation/database/079`, `080`, `081`)
ou, no caso de `stg.doc2you_execucao`, por ninguém — criada ad-hoc, dono `dev_user`,
sem migration em repo algum.

Quem escreve numa tabela é quem versiona o schema dela. É o que esta pasta corrige.

## Numeração — prefixo `erp_`, e o motivo

O diagnóstico de 03/08 mediu uma colisão real entre repositórios: `data-hub` e
`process-automation` produziram `304_*` no mesmo dia, 45 minutos de diferença,
conteúdos sem relação. O prefixo `erp_` põe este projeto num namespace próprio, de
modo que a colisão não seja possível por construção.

```
erp_001_schema_erp_automation.sql
erp_002_revogar_heranca_dev_user.sql
```

## Como aplicar

```bash
./database/aplicar.sh              # aplica o que falta
./database/aplicar.sh --dry-run    # mostra o que falta, sem aplicar
```

O runner precisa de credencial **administrativa** (`DB_ADMIN_USER` /
`DB_ADMIN_PASSWORD` no `.env`), não da credencial de runtime: `app_erp_automation`
não tem — e não deve ter — poder para conceder e revogar permissão.

## O ledger

`erp_automation.migration_aplicada` registra o que já rodou, com nome de arquivo,
hash do conteúdo e quando. Aplicar duas vezes é no-op. Se o conteúdo de um arquivo já
aplicado mudar, o runner **falha** em vez de reaplicar — migration aplicada é
imutável; correção se faz em arquivo novo.

## O que NÃO se faz aqui

Este projeto escreve em `erp_automation` e **lê** de `stg`, `int` e `trs`. DDL em
schema de outro dono não se escreve aqui — nem em `dwh`/`trs`, onde a norma do
process-automation já proíbe, nem em `stg`, que é camada de staging do ETL.

## `erp_004` — execução e eventos (21/09/2026)

O controle dos jobs sai do CSV e entra no banco, com o vocabulário do Learn:
`job_execucao` (uma linha por execução de job), `operacao_evento`,
`operacao_pagamento_linha`, `arquivo`, `arquivo_titulo`, `arquivo_evento`, e as views
`vw_job_execucao_ativa`, `vw_job_execucao_abandonada`, `vw_operacao_finalizacao_aberta`,
`vw_operacao_ciclo` e `vw_operacao_placar` (esta só onde `trs.operacao_desagio` existe).

- **Dono:** `app_erp_automation_evento`, sem login. O schema `erp_automation` passa a ser
  dela: dono de schema derruba qualquer tabela dele (medido na bancada), e o runtime não
  pode ser dono do próprio histórico. `app_erp_automation` fica com `USAGE` + `CREATE`.
- **Imutável por gatilho:** `UPDATE`, `DELETE` e `TRUNCATE` são recusados nas tabelas de
  evento até para o superusuário; corrigir é gravar outro evento. A execução fecha uma
  vez, só nas colunas de fechamento.
- **Leitores da casa:** `USAGE` no schema e `SELECT` em tudo, menos
  `operacao_pagamento_linha` (CPF, chave PIX).
- **Quem escreve:** `src/common/clients/execucao_job.py`. Em DRY o banco pode faltar
  (a execução degrada e avisa uma vez); em modo real é obrigatório — sem registro não
  há ação irreversível.

### Aplicar em produção

Exige o Guardian no modelo de administração (a senha fica no `.pgpass`, nunca na tela):

```bash
bin/guardian conceder-banco NOME --modelo administracao --horas 1 --para /caminho/NOME.pgpass
DB_ADMIN_HOST=127.0.0.1 DB_ADMIN_USER=tmp_NOME \
  DB_ADMIN_PASSWORD="$(cut -d: -f5 /caminho/NOME.pgpass)" ./database/aplicar.sh --dry-run
DB_ADMIN_HOST=127.0.0.1 DB_ADMIN_USER=tmp_NOME \
  DB_ADMIN_PASSWORD="$(cut -d: -f5 /caminho/NOME.pgpass)" ./database/aplicar.sh
```

Provado antes na bancada (abaixo): 17 testes de integração, reaplicação do SQL sem erro,
ledger segurando a segunda passada.

## A bancada — provar antes de encostar no `prosperedb`

`scripts/bancada_pg.sh subir` sobe um Postgres descartável **da mesma imagem do de
produção** (`postgres-postgres`, 17 + extensões) em `127.0.0.1:55432`, cria as roles que
as migrations citam e aplica `database/erp_*.sql` **pelo mesmo `aplicar.sh`** — a
`erp_001`–`003` entram no ledger como puladas, porque movem tabelas que só existem em
produção. Senhas geradas na hora ficam em `data/bancada_pg.env` (600, ignorado).

```bash
scripts/bancada_pg.sh subir
eval "$(scripts/bancada_pg.sh env)"
PYTHONPATH=$PWD .venv-sandbox/bin/pytest tests/integration/test_execucao_job_bancada.py
scripts/bancada_pg.sh derrubar
```

Sem a bancada no ar, esses testes são **pulados**, não falham.

## `aplicar.sh`: credencial explícita vence os arquivos

`DB_ADMIN_*` já definidos no ambiente fazem o runner **não** ler `shared.env` nem `.env`
— é assim que a bancada o aponta para o Postgres descartável sem risco de o `.env` o
devolver para produção. O runner imprime o alvo antes de qualquer coisa, e
`BANCADA_PULAR` é recusado na porta 5432.
