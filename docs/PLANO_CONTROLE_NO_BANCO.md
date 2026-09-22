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

| fase | o que | estado |
|---|---|---|
| **0** | Paridade CSV × banco automática, diária: job `comparar_controle_csv_banco` (`src/processors/db/controle/`), task no hub 19:35, exit 3 = divergência | **feita em 22/09/2026** |
| **1** | `erp_005`: `md5`/`id_no_smart` como colunas geradas e indexadas; eventos `intencao_envio`, `descartado`, `cancelado`, `movido`; eventos do crédito; `operador`/`motivo` na execução manual (`ERP_OPERADOR`, `ERP_MOTIVO`); automação `controle`; views com as colunas dos CSVs (`vw_controle_retorno`, `vw_controle_remessa`, `vw_controle_pagamento`, `vw_controle_retorno_pagamento`), `vw_arquivo_dia`, `vw_job_execucao_ultima`. Cliente: `atual()`, `anotar()`, `buscar_arquivo()`, evento de arquivo estrito, evento de operação como fato. Jobs: remessa registra descarte, perdida e cancelamento; BB registra a intenção; crédito registra documentos e etapa | **feita em 22/09/2026** (código); migration em produção: ver `database/README.md` |
| **2** | As **leituras** de idempotência migram para o banco, um job por vez, atrás de `CONTROLE_FONTE=csv|banco` (CSV de reserva): retorno de pagamento → remessa de pagamento → retorno de cobrança (o wrapper consulta o banco em vez do grep) → remessa e cancelamento. A intenção do BB vira estrita (sem registro, sem POST) e o recibo em disco deixa de ser a prova. Decidir o ensaio sem banco (banco obrigatório sempre, ou ensaio sem memória) | a fazer, depois de ≥ 2–3 semanas de paridade sem divergência |
| **3** | Contratos entre projetos (`cancelamentos.json`, `exclusoes.json`) viram tabelas em `financeiro.*`; process-automation escreve, ERP lê | a fazer, com o process-automation |
| **4** | Parar de escrever os CSVs; arquivos congelados como histórico | a fazer, ao fim da Fase 2 |

## 4. Regras que valem desde já

- Execução **manual em modo real** informa quem e por quê: `ERP_OPERADOR=nome ERP_MOTIVO="..."`
  no ambiente (`docker exec -e ...`). Sem isso o job roda; a auditoria fica sem autor.
- ⚠️ **O hub ainda não se identifica** (medido em 22/09/2026): o `docker exec` do
  hub-orchestration não passa `HUB_RUN_ID`/`HUB_TASK_NOME`, então toda execução dele é
  registrada como `gatilho manual` e `run_id` fica nulo — a ligação `job_execucao` ↔
  `hub_orchestration.task_execucao` não fecha. Pendência para a frente do hub: passar
  `-e HUB_RUN_ID=<id> -e HUB_TASK_NOME=<task>` no exec; o cliente já lê os dois e o gatilho
  vira `cron` sozinho. Até lá, quem quiser saber se foi o hub olha o horário contra o cron.
- O que aconteceu com um arquivo é **evento**, não coluna do arquivo: o processamento
  grava ocorrências, críticas e divergências no `detalhe_json` do evento `processado`/`retido`.
- Fato sem tabela própria (remessa que não baixou, cancelamento de remessa anterior ao
  registro) vai por `execucao_job.anotar()` para o `detalhe_json` da execução, no fechamento.
- Nada se apaga nem se corrige no lugar: corrigir é outro evento.

## 5. Como conferir

```sql
select * from erp_automation.vw_job_execucao_ultima order by iniciado_em desc;
select * from erp_automation.vw_arquivo_dia where registrado_em >= current_date order by registrado_em;
select * from erp_automation.vw_controle_retorno where quando >= current_date;   -- as colunas do CSV
```
E o job de paridade: `docker exec erp-automation sh /app/src/processors/db/controle/run_agendado.sh --dia AAAA-MM-DD`.
