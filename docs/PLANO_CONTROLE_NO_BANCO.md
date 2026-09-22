# Plano — o banco como fonte única do controle dos jobs

Decisão da Gerência em 22/09/2026: centralizar no banco o controle de idempotência, o
estado e a auditoria de cada job do erp-automation; os CSVs e JSONs de controle viram
passado. Este plano diz o que existe hoje fora do banco, o que a `erp_004`/`erp_005` já
cobrem, e em que ordem o resto entra — **sem tirar o CSV até a última fase**, porque ele
é hoje a memória de idempotência dos jobs, não só um registro.

## 1. O que existia fora do banco (medido em 22/09/2026)

| onde | job | o que guarda | quem lê | volume | no banco? |
|---|---|---|---|---|---|
| `controle_processados.csv` | retorno cobrança, BB, depósito | arquivo, nome no Smart, md5, conta, títulos, processado, ocorrências, críticas, divergências, motivo, quando | o job (não reprocessar) e o **wrapper** (grep do md5 na descoberta) | 14.496 | sim: `arquivo` + `arquivo_evento` + `arquivo_titulo` |
| `controle_remessas.csv` + `remessas_geradas.json` | remessa cobrança | id no Smart, arquivo, tipo (→ conta), md5, títulos, data | geração (não rebaixar) e **cancelamento** (tipo, data) | 809 + 807 | sim: `arquivo` (`id_no_smart`, `conta_label`) |
| `falhas/<id>.json` | remessa cobrança | remessa gerada pelo Smart e descartada/perdida, com títulos culpados | vigia do process-automation; cancelamento | 1 | **erp_005**: evento `descartado`; perdida → `detalhe_json` da execução |
| `cancelamentos_feitos.json` | cancelamento | ids cancelados e quando | o próprio | 24 | **erp_005**: evento `cancelado` |
| `cancelamentos.json`, `exclusoes.json` | remessa/cancelamento | contratos entre projetos (process-automation escreve, ERP lê) | ERP | 7 / 8 | não — Fase 3 (tabela em `financeiro.*`, como `cnab_entrega_bb`) |
| recibos BB (`<conta>/<sha>/*.json`) | retorno BB | intenção durável + recibo: **uma única tentativa** do POST | `bb_entrega` | 253 | **erp_005**: evento `intencao_envio` (registro; o recibo segue sendo a prova) |
| `_PROCESSADOS/_REJEITADOS/_INCONCLUSIVOS` | retorno | estado por localização | pessoas, reprocessos | 199/13/3 | sim (evento + caminho de destino) |
| `controle_pagamentos.csv` | remessa pagamento | arquivo, md5, títulos, ids, pix, quando | o próprio | 393 | sim |
| `controle.csv` | retorno pagamento | arquivo, hash, HTTP, quando | o próprio | 391 | sim |
| `controle_downloads.csv` | crédito | operação, data, NF/resumo, etapa movida | o próprio | 35 | **erp_005**: `operacao_evento` (`documentos_baixados`, `etapa_movida`) |
| `finalizadas.csv`, `avisos_enviados.csv` | finalizador | finalizadas, avisos | o próprio | vazios (DRY) | sim (`operacao_evento`) |
| já no banco | doc2you, boletos | `doc2you_execucao`, `boleto_*` | — | — | sim |
| hub | todos | output, exit, duração, tentativas | — | — | `hub_orchestration.task_execucao` (por `run_id`) |

Ninguém de fora lê esses CSVs (o process-automation só os cita em comentário).

## 2. O que a `erp_004` já dá para auditoria

Cada execução com gatilho (hub/manual), ambiente, ensaio ou real, task, `run_id`, versão
do código, início/fim, exit; cada arquivo pelo conteúdo (sha256), com eventos append-only;
cada operação com eventos; tudo imutável por dono separado e gatilho.

## 3. As fases

> **Ligadas em 22/09/2026 às 11h47** (linha `CONTROLE_FONTE_*=banco` no `config/<job>.env`;
> reverter = apagar a linha): `_RET` (`retorno_cobranca.env`, vale para retorno, BB e depósito),
> `_RETPAG` (`retorno_pagamento.env`), `_REM` (`remessa_cobranca.env`, vale para remessa, BB e
> cancelamento). **`_PAG` ligada em 22/09/2026 às 17:41**, a pedido da Gerência, depois da
> paridade das quatro famílias OK no mesmo minuto (execução #411: pagamento 25 × 25):
> `config/remessa_pagamento.env` é de `operacional2` (600), então a linha entrou pelo
> container, com dono e modo preservados (cópia do anterior em `/tmp` do container). É a de
> menor risco: o controle só é lido depois que o arquivo já foi gerado. **A Fase 2 está
> completa nos quatro jobs de arquivo.**

| fase | o que | estado |
|---|---|---|
| **0** | Paridade CSV × banco automática, diária: job `comparar_controle_csv_banco` (`src/processors/db/controle/`), task no hub 19:35, exit 3 = divergência | **feita em 22/09/2026** |
| **1** | `erp_005`: `md5`/`id_no_smart` como colunas geradas e indexadas; eventos `intencao_envio`, `descartado`, `cancelado`, `movido`; eventos do crédito; `operador`/`motivo` na execução manual (`ERP_OPERADOR`, `ERP_MOTIVO`); automação `controle`; views com as colunas dos CSVs (`vw_controle_retorno`, `vw_controle_remessa`, `vw_controle_pagamento`, `vw_controle_retorno_pagamento`), `vw_arquivo_dia`, `vw_job_execucao_ultima`. Cliente: `atual()`, `anotar()`, `buscar_arquivo()`, evento de arquivo estrito, evento de operação como fato. Jobs: remessa registra descarte, perdida e cancelamento; BB registra a intenção; crédito registra documentos e etapa | **feita em 22/09/2026** (código); migration em produção: ver `database/README.md` |
| **2** | As **leituras** de idempotência migram para o banco, um job por vez, atrás de `CONTROLE_FONTE=csv|banco` (CSV de reserva): retorno de pagamento → remessa de pagamento → retorno de cobrança (o wrapper consulta o banco em vez do grep) → remessa e cancelamento. A intenção do BB vira estrita (sem registro, sem POST) e o recibo em disco deixa de ser a prova. Decidir o ensaio sem banco (banco obrigatório sempre, ou ensaio sem memória) | **em andamento**, tudo publicado inerte em 22/09/2026 (padrão `csv`): retorno de pagamento (`CONTROLE_FONTE_RETPAG`), remessa de pagamento (`CONTROLE_FONTE_PAG`), retorno de cobrança e BB (`CONTROLE_FONTE_RET`, no Python e na descoberta do wrapper, que lê a lista de md5 do banco por `src/processors/db/controle/listar_md5.py`). Ligar = pôr a chave em `banco` no `config/<job>.env` depois de ≥ 1 semana de paridade. Remessa de cobrança e cancelamento (`CONTROLE_FONTE_REM`): `ler_controle` pela `vw_controle_remessa` e o controle do cancelamento reagrupado por arquivo; **carga histórica feita em 22/09/2026 ~11h35** (execução #166: 671 linhas de 45 dias → 668 registradas, 3 já existiam, 0 sem arquivo, 0 md5 divergente) por `src/processors/db/controle/carregar_remessas_historicas.py` — lê os `.REM` da árvore do Nextcloud montada no container, confere md5, registra com `registrado_em = baixado_em`; idempotente, pode ser repetida. A intenção do BB é **estrita desde 22/09/2026** (registrada no banco antes do recibo e do POST; sem registro, sem POST — o arquivo fica pendente, exit 6, e a próxima rodada tenta limpa) |
| **3** | Contratos entre projetos (`cancelamentos.json`, `exclusoes.json`) viram tabelas em `financeiro.*`; process-automation escreve, ERP lê | a fazer, com o process-automation |
| **4** | Parar de escrever os CSVs; arquivos congelados como histórico | **preparada em 22/09/2026**: chave `ESCREVER_CSV_RET/_RETPAG/_PAG/_REM` (ou `ESCREVER_CSV` global), padrão `True`; `False` congela o CSV daquele job (gravar_controle vira no-op com aviso; a leitura banco ∪ histórico continua). Desligar só com `CONTROLE_FONTE=banco` e paridade limpa por semanas |

## 4. Regras que valem desde já

- **Memória de idempotência em `banco` = banco ∪ histórico do CSV, até a Fase 4** — nos dois
  retornos (`_RET`, `_RETPAG`), onde a memória é o que impede **baixa em duplicidade** de um
  `.RET` re-entregue: o banco só conhece o que entrou desde 21/09/2026, e o CSV entra como
  história congelada, não como decisão. Na Fase 4 o CSV para de ser escrito, é renomeado
  como histórico e continua lido até uma carga histórica o substituir. Remessa de pagamento
  (controle informativo) e remessa de cobrança (carga de 45 dias feita) não precisam disso.

- Execução **manual em modo real** informa quem e por quê: `ERP_OPERADOR=nome ERP_MOTIVO="..."`
  no ambiente (`docker exec -e ...`). Sem isso o job roda e **avisa no log** (desde que o hub se
  identifica, `manual` é só quem rodou à mão); a auditoria fica sem autor.
- ✅ **O hub se identifica desde 22/09/2026 ~11h15** (frente do hub, a pedido desta): o
  `docker exec` passa `HUB_RUN_ID` (id de lock do run, 32 hex) e `HUB_TASK_NOME`; a execução
  entra como `gatilho cron` com `run_id` e `task_nome` (primeira medida: #153, 11h17). Antes
  disso toda execução do hub está gravada como `manual` com `run_id` nulo. A `erp_006`
  (índice de `run_id` não único) foi aplicada antes, porque um run abre várias execuções.
- O que aconteceu com um arquivo é **evento**, não coluna do arquivo: o processamento
  grava ocorrências, críticas e divergências no `detalhe_json` do evento `processado`/`retido`.
- Fato sem tabela própria (remessa que não baixou, cancelamento de remessa anterior ao
  registro) vai por `execucao_job.anotar()` para o `detalhe_json` da execução, no fechamento.
- Nada se apaga nem se corrige no lugar: corrigir é outro evento.
- **A conexão do registro pode cair numa rodada longa** (22/09/2026, remessa das 11h30: o
  servidor fechou após 12 min ociosos). O cliente reconecta e repete o comando uma vez;
  o **fechamento nunca derruba o job** (falha vira aviso e a linha fica `ativa` — a
  `vw_job_execucao_abandonada` a mostra depois de 2 h). Registro que se perdeu no meio
  de uma rodada entra depois pela carga histórica (`--dias 1`), pelo CSV.

## 4b. Execuções abandonadas

`vw_job_execucao_abandonada` (erp_007) lista execução `ativa` além do limite da automação
(crédito 13 h, doc2you e boletos 1 h, demais 2 h — folga sobre o timeout do hub). É onde
aparece o job que morreu sem fechar e o fechamento que falhou (o cliente deixa a linha
`ativa` de propósito). A paridade diária lista essas linhas e trata qualquer uma como
divergência (exit 3) — **todo dia, até alguém encerrar**. O encerramento é administrativo e
tem autor: `encerrar_abandonada.py <id> --pra-valer` com `ERP_OPERADOR`/`ERP_MOTIVO`
(`execucao_job.encerrar_abandonada`), que grava `abandonada` (nunca `sucesso`) e deixa
quem/por quê no `detalhe_json` da linha. Só o que a view lista se encerra; nunca `UPDATE` à
mão. Caso concreto: #164 (remessa das 11h30 de 22/09, conexão caída no fechamento; as 9
remessas estão no banco pela carga `--dias 1`, execução #176).

## 5. Como conferir

```sql
select * from erp_automation.vw_job_execucao_ultima order by iniciado_em desc;
select * from erp_automation.vw_arquivo_dia where registrado_em >= current_date order by registrado_em;
select * from erp_automation.vw_controle_retorno where quando >= current_date;   -- as colunas do CSV
```
E o job de paridade: `docker exec erp-automation sh /app/src/processors/db/controle/run_agendado.sh --dia AAAA-MM-DD`.
