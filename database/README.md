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

- **Dono das tabelas:** `app_erp_automation_evento`, sem login — o runtime não é dono do
  próprio histórico: não altera estrutura nem desliga gatilho. **Limite conhecido:** o
  schema continua da `app_erp_automation` (erp_001), e dono de schema pode dar `DROP TABLE`
  explícito; mudar o dono do schema exige `CREATE` no banco, que a sessão do Guardian não
  tem — só superusuário: `ALTER SCHEMA erp_automation OWNER TO app_erp_automation_evento;`.
- **Quem aplica:** sob o Guardian, DDL num schema de projeto exige sessão que herde
  `access_admin` (para criar a role) **e** `app_erp_automation` (dona do schema). Nada fica
  de posse da sessão: os objetos nascem da role dona (`SET ROLE`), porque o revogar da
  `tmp_` faz `DROP OWNED`. A bancada ensaia exatamente essa sessão (`tmp_teste`).
- **Imutável por gatilho:** `UPDATE`, `DELETE` e `TRUNCATE` são recusados nas tabelas de
  evento até para o superusuário; corrigir é gravar outro evento. A execução fecha uma
  vez, só nas colunas de fechamento.
- **Leitores da casa:** `USAGE` no schema e `SELECT` em tudo, menos
  `operacao_pagamento_linha` (CPF, chave PIX).
- **Quem escreve:** `src/common/clients/execucao_job.py`. Em DRY o banco pode faltar
  (a execução degrada e avisa uma vez); em modo real é obrigatório — sem registro não
  há ação irreversível.

### Aplicar em produção

Exige um modelo do Guardian que herde a camada 1 **e** a dona do schema — o
`administracao` sozinho não faz DDL em schema de projeto. Uma vez no `roles.yaml`
(curadoria da Gerência):

```yaml
  erp-automation-ddl:
    herda: [access_admin, app_erp_automation]
    conexoes: 2
    horas_max: 2
    permanente: false
    nota: aplicar database/erp_*.sql; DDL em schema de projeto exige ser dona do schema
```

A senha fica no `.pgpass`, nunca na tela:

```bash
bin/guardian conceder-banco NOME --modelo erp-automation-ddl --horas 1 --para /caminho/NOME.pgpass
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
## Aplicada em produção em 21/09/2026

A `erp_004` está no `prosperedb`: 6 tabelas e 4 views da `app_erp_automation_evento`,
`vw_operacao_placar` da `app_erp_automation`, 10 gatilhos, os 4 índices únicos de regra.
Provado logo após aplicar, como `app_erp_automation` e dentro de transação desfeita:
abre execução e grava evento (permitido), fecha uma vez (a segunda o gatilho recusa),
`UPDATE`/`DELETE` em `operacao_evento` negados por privilégio, `DISABLE TRIGGER` negado
por não ser dona. A primeira execução real registrada é a #2, do finalizador pelo hub.

⚠️ **Lacuna conhecida em `arquivo_titulo`:** os arquivos `id` 1 a 21 (retorno de cobrança
e retorno BB, de 21/09 até 22/09 08:43) têm os títulos gravados só com `numero_linha` —
`id_titulo`, `codigo_ocorrencia` e `valor_titulo` vazios, 95 linhas. O job lia as chaves
das *críticas* (`numTitulo`/`ocorrencia`/`valor`) em vez das da *grade* do Smart
(`numero_titulo`/`acao_tomada`/`valor_titulo`), e o teste de integração não viu porque
alimentava o cliente com dicionários já mapeados. Corrigido em 22/09/2026 (teste
`tests/unit/test_retorno_registro_banco.py` parte do HTML em base64, como o upload devolve).
A tabela não aceita `UPDATE`, então essas 95 linhas ficam como estão: a contagem por
arquivo está certa e o CSV de controle tem os títulos. Para o retorno, `codigo_ocorrencia`
carrega a **ação tomada** do Smart (Liquidado, Entrada Confirmada…): a grade não traz o
código CNAB. Arquivo grande (518 títulos) vem sem grade — o Smart devolve só a linha
"Visualizar Títulos" — e então `arquivo_titulo` fica vazio para ele, de propósito;
`qtd_registros` continua sendo o contador do Smart (o arquivo 67 entrou com essa
pseudolinha antes da regra, e fica assim).

O modelo `erp-automation-ddl` **existe** no `roles.yaml` do Guardian desde 21/09/2026
(`herda: [access_admin, app_erp_automation]`, 2 h, sem permanente). Para aplicar:

```bash
bin/guardian conceder-banco NOME --modelo erp-automation-ddl --horas 2 --para ~/NOME.pgpass
DB_ADMIN_HOST=127.0.0.1 DB_ADMIN_USER=tmp_NOME \
  DB_ADMIN_PASSWORD="$(cut -d: -f5 ~/NOME.pgpass)" ./database/aplicar.sh --dry-run
# sem --dry-run para aplicar; ao terminar:
bin/guardian revogar-banco NOME && shred -u ~/NOME.pgpass
```

⚠️ `DB_PORT` é o nome da variável de porta, não `DB_ADMIN_PORT`. Errar isso aponta o
aplicador para a 5432, que é produção.

## erp_005 — o banco como fonte do controle (22/09/2026)

`database/erp_005_controle_no_banco.sql`, Fase 1 de `docs/PLANO_CONTROLE_NO_BANCO.md`:
`arquivo.md5` e `arquivo.id_no_smart` como colunas **geradas** de `detalhe_json` (a origem
segue sendo o JSON; a coluna é o índice — `ADD COLUMN` gerada não dispara gatilho de linha);
eventos novos em `arquivo_evento` (`intencao_envio`, `descartado`, `cancelado`, `movido`) e
em `operacao_evento` (`documentos_baixados`, `etapa_movida`); `job_execucao.operador` e
`.motivo` (imutáveis no fechamento, o gatilho foi estendido); automação `controle`; views
`vw_controle_retorno`, `vw_controle_remessa`, `vw_controle_pagamento`,
`vw_controle_retorno_pagamento`, `vw_arquivo_dia`, `vw_job_execucao_ultima`. Nada é apagado,
nenhuma linha muda. Re-executável. Aplica-se como a erp_004 (modelo `erp-automation-ddl`).

**Ordem de implantação:** a migration entra em produção **antes** do código que a usa. O
cliente tolera o banco sem ela (o INSERT da execução repete sem `operador`/`motivo` e avisa
`erp_005 nao aplicada`; os eventos novos falham como fato consumado, com aviso), então uma
inversão não derruba job — mas deixa buraco no registro. Provada na bancada em 22/09/2026
(`tests/integration/test_erp_005_controle.py`).

## erp_006 — `run_id` deixa de ser único (pré-requisito da identificação do hub)

`database/erp_006_run_id_nao_unico.sql`: troca `uq_job_execucao_run_id` por um índice
comum. Um run do hub abre **várias** execuções de job (o wrapper do retorno chama o python
uma vez por pasta; a retentativa reaproveita o run), e com o `HUB_RUN_ID` injetado pelo hub
a segunda cairia no único — em modo real o job recusa agir sem registro. **Aplicada em
produção em 22/09/2026 às 10:50**, antes da imagem do hub que passa `HUB_RUN_ID`/
`HUB_TASK_NOME` (pedido em 22/09/2026). Prova: `tests/integration/test_erp_006_run_id.py`.

## erp_007 — abandonada por automação

`database/erp_007_abandonada_por_automacao.sql`: `vw_job_execucao_abandonada` passa a usar
limite por automação (crédito 13 h — o ciclo diário é de ~11 h e aparecia como abandonado
todo dia —, doc2you e boletos 1 h, demais 2 h). Só a view muda. Prova:
`tests/integration/test_erp_005_controle.py::test_abandonada_respeita_o_limite_da_automacao`.
**Aplicada em produção em 22/09/2026 às 17:40** (credencial `tmp_erpddl`, modelo
`erp-automation-ddl`, revogada em seguida). Conferido com a identidade do ERP: a view traz
`CASE automacao WHEN 'credito' THEN '13:00:00'` e o crédito das 07:45 deixou de aparecer como
abandonado. O filtro do crédito que a paridade e `encerrar_abandonada.py` repetem no código
ficou redundante e é inofensivo.

## erp_008 — o histórico dos CSVs de controle

`database/erp_008_historico_do_csv.sql`: `erp_automation.arquivo_historico`, o que só os CSVs
de controle sabiam dos arquivos tratados antes do registro no banco (21/09/2026): md5 do
conteúdo, nome, quando (`tratado_em`) e o que a memória do job usa (`detalhe_json`:
`processado`, `nomes_smart` no retorno de cobrança). Uma linha por (`tipo_arquivo`, `md5`),
append-only como os eventos; o ERP insere e lê, os leitores de sempre leem. Para a maioria
desses arquivos o conteúdo já não está no disco, então não cabem em `arquivo` (que exige o
sha256). Carga: `src/processors/db/controle/carregar_historico_csv.py` (um comando por família,
tudo ou nada, repetível). Com ela feita, `listar_md5` une as duas tabelas e os retornos param de
ler o CSV sozinhos (`historico_carregado`); sem ela, continuam no CSV congelado. Prova:
`tests/integration/test_erp_008_historico.py` (bancada, 22/09/2026). **Aplicada em produção em
22/09/2026 às 19:31** (credencial `tmp_erpddl`, modelo `erp-automation-ddl`, revogada em
seguida). Carga no mesmo minuto, execução #457: 1.885 md5 do retorno de cobrança (102 do BB) e 416
do retorno de pagamento. Prova no container com as funções dos jobs: a memória nova é igual à que
vinha do CSV — 1.795 processados e 1.878 nomes no retorno de cobrança, 418 md5 no de pagamento,
zero diferenças; `listar_md5 --com-historico` sai com 0 (1.890 md5).

### Quando o ledger diz que o conteúdo mudou

Migration aplicada é imutável e a guarda barra — é isso que se quer. Só existe uma saída,
e ela não executa SQL nenhum: `RECONCILIAR="<arquivo>" RECONCILIAR_MOTIVO="<por quê>"`
atualiza o hash no ledger e grava o motivo em `aplicada_por`. Serve para o caso em que a
migration foi editada **antes de o `database/` ser versionado** e o original não existe
mais para comparar — nunca para fazer passar uma alteração que você quer ver aplicada,
que vai em arquivo novo.

Foi usada uma vez, na `erp_002`: editada depois de aplicada em 12/08/2026, sem original.
Antes de reconciliar, o estado foi conferido no banco (herança de `dev_user` revogada,
`USAGE` nos 5 schemas, leituras diretas concedidas). Reaplicar era impossível: ela cita
`api.erp_operacoes_ocultas_dia_anterior` e `dwh.fct_titulos_quitados`, que não existem
mais — outros projetos renomearam esses objetos depois.

