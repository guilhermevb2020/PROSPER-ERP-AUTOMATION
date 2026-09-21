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
