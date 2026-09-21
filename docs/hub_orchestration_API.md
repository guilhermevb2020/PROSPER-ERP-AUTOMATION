# API HTTP — Hub-Orchestration

API interna para disparar tasks sob demanda e consultar execuções.

## Estado Atual

- Base URL: `http://hub-orchestration:8080`
- Auth: header `X-API-Key`
- API key: `HUB_ORCH_API_KEY`
- Catálogo persistido em `hub_orchestration.task_config`
- Endpoint canônico: `/api/tasks`
- Aliases legados mantidos: `/api/jobs`, `/api/jobs/trigger`, `/api/jobs/{exec_id}/status`, `/api/jobs/history`
- `POST /api/tasks/trigger` usa o mesmo gate de despacho do scheduler (`dependencies -> pre_condition -> capacity -> lock`)
- tasks da Smart API respeitam a mesma serialização do scheduler via `resource:smart_api` e `RESOURCE_CAPACITY_SMART_API=1`
- `GET /api/tasks/{exec_id}/status` e `GET /api/tasks/history` expõem `executor_type` e `execution_target` a partir do snapshot persistido em `task_execucao`

## Endpoints

### Probes sem autenticação

Os três endpoints têm responsabilidades diferentes:

| Endpoint | HTTP `200` significa | Comportamento de falha |
|---|---|---|
| `GET /live` | o processo da API HTTP está respondendo | não há dependências consultadas; falha de conexão já representa liveness perdida |
| `GET /health` | heartbeat do loop do scheduler recente e lease renewer saudável | scheduler não iniciou, está em `startup_stale`, `stale` ou `stopping`, ou o heartbeat de lease perdeu saúde |
| `GET /ready` | `/health` saudável, ciclo bem-sucedido recente, lifecycle em `running` e pool PostgreSQL aceitando o probe | maintenance/drain ativo, ciclo sem sucesso recente, pool indisponível ou qualquer check de saúde falhou |

O Docker `HEALTHCHECK` consulta `/health`. Assim, maintenance planejada mantém o
container saudável, enquanto `/ready` fecha para novas submissões. O probe
direto do pool existe somente em `/ready`.

#### `GET /live`

```json
{"status": "alive"}
```

#### `GET /health`

Resposta saudável:

```json
{
  "status": "ok",
  "healthy": true,
  "degraded": false,
  "checks": {
    "scheduler": {
      "ready": true,
      "state": "ready",
      "last_cycle_succeeded": true,
      "success_recent": true,
      "consecutive_errors": 0,
      "timeout_seconds": 120.0
    },
    "lease_renewer": {
      "healthy": true,
      "reason": "último heartbeat há 2s (limite 75s)"
    }
  }
}
```

Se o loop continuar avançando, mas não houver ciclo bem-sucedido recente,
`/health` mantém HTTP `200` com `"status": "degraded"` e
`"degraded": true`. Isso preserva a distinção entre processo saudável e
readiness operacional. Maintenance, por si só, não altera `/health`.

#### `GET /ready`

Resposta pronta:

```json
{
  "status": "ready",
  "ready": true,
  "checks": {
    "scheduler": {
      "ready": true,
      "success_recent": true,
      "consecutive_errors": 0
    },
    "lease_renewer": {
      "healthy": true,
      "reason": "último heartbeat há 2s (limite 75s)"
    },
    "lifecycle": {
      "state": "running",
      "ready": true
    },
    "database_pool": {
      "checked": true,
      "ready": true,
      "reason": "ok"
    }
  }
}
```

Durante maintenance ou drain, `/ready` retorna HTTP `503`; nesse caso o probe
do pool é curto-circuitado e `database_pool.checked` fica `false`. Quando o
runtime está apto, o probe do pool executa uma consulta mínima com
`statement_timeout` de no máximo 5 segundos, além do `connect_timeout`
configurado para a eventual criação de conexões do pool.

### `POST /api/tasks/trigger`

Enfileira uma task para execução assíncrona.
Para compatibilidade, `POST /api/jobs/trigger` continua aceitando o mesmo payload.

Request:

```json
{
  "task": "onboarding",
  "job": "onboarding",
  "params": {
    "cnpj": "48594412000123",
    "reprocess": true
  },
  "initiated_by": "forms-hub:ester@prospereinvest.com.br"
}
```

Campos:

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `task` | Sim* | Nome lógico da task em `hub_orchestration.task_config.nome` |
| `job` | Sim* | Alias legado de `task` |
| `params` | Não | Parâmetros validados e convertidos em argumentos CLI e/ou env vars, conforme `input_schema_json` da task |
| `initiated_by` | Não | Origem da execução; default `api:unknown` |

\* Um dos dois campos é obrigatório. Se ambos forem enviados, `task` tem precedência.

Parâmetros globais aceitos em `params`:

| Param | Tipo | Regra |
|-------|------|-------|
| `cnpj` | string | 14 dígitos |
| `cnpjs` | string[] | até 100 CNPJs |
| `reprocess` | boolean | vira `--reprocess` quando `true` |
| `profile` | string | `preview`, `test`, `pilot`, `prod` |
| `limit` | integer | `1..10000` |
| `date_from` | string | `YYYY-MM-DD` |
| `date_to` | string | `YYYY-MM-DD` |

Tasks podem expor parâmetros adicionais no catálogo vivo. Exemplos atuais:

| Task | Parâmetros extras |
|------|-------------------|
| `consultar_processos` | `query` obrigatório, `caso`, `processo`, `area`, `top_k` |
| `resumir_movimentacao` | `caso` opcional |
| `sugerir_peticao` | `caso` obrigatório |
| `limpar_duplicatas_escavador` | `executar` opcional; sem ele roda em dry-run |

Exemplo RAG:

```json
{
  "task": "consultar_processos",
  "params": {
    "query": "qual o ultimo despacho?",
    "caso": "EL CAMINO MADEIRAS LTDA",
    "top_k": 10
  }
}
```

Exemplo simples de trigger para `data-hub`:

```json
{
  "task": "dh_ciclo_cadastros",
  "initiated_by": "manual:ops"
}
```

Respostas:

| HTTP | Cenário |
|------|---------|
| `202` | Task enfileirada |
| `400` | Payload inválido |
| `401` | API key ausente ou inválida |
| `404` | Task não encontrada no catálogo |
| `409` | Task desabilitada, com dependência pendente, `pre_condition_sql` falso, lock ativo ou sem recurso disponível |
| `500` | Falha interna ao registrar/enfileirar |

Exemplo `202`:

```json
{
  "ok": true,
  "exec_id": 1234,
  "run_id": "c5f7b8d02d8f4dc6bb6ca4b5d9328ef6",
  "task": "onboarding",
  "job": "onboarding",
  "status": "pending",
  "mensagem": "Task 'onboarding' enfileirada para execucao"
}
```

### `GET /api/tasks/{exec_id}/status`

Retorna o estado atual de uma execução.

Exemplo:

```json
{
  "exec_id": 1234,
  "current_exec_id": 1234,
  "run_id": "c5f7b8d02d8f4dc6bb6ca4b5d9328ef6",
  "task": "onboarding",
  "job": "onboarding",
  "status": "success",
  "inicio": "2026-03-24T15:00:00.123456",
  "fim": "2026-03-24T15:00:06.789012",
  "duracao_ms": 6665,
  "tentativa": 1,
  "exit_code": 0,
  "executor_type": "docker_exec",
  "execution_target": "process-automation",
  "output": "...",
  "erro": null,
  "post_checks_status": "passed",
  "post_checks_result": {
    "status": "passed",
    "total_checks": 1,
    "executed_checks": 1,
    "skipped_checks": 0,
    "checks": [
      {
        "name": "fct_metas_atualizada_recente",
        "severity": "error",
        "status": "passed",
        "value": true,
        "duration_ms": 42
      }
    ]
  },
  "initiated_by": "forms-hub:ester@prospereinvest.com.br",
  "params": {"cnpj": "48594412000123", "reprocess": true}
}
```

Status possíveis:

| Status | Significado |
|--------|-------------|
| `pending` | Registrada e aguardando worker |
| `running` | Em execução |
| `success` | Finalizada com sucesso |
| `failed` | Falhou após as tentativas configuradas |
| `timeout` | Excedeu o timeout configurado |

Campos adicionais de correlação:

| Campo | Significado |
|-------|-------------|
| `exec_id` | identificador público estável da execução requisitada |
| `current_exec_id` | linha mais recente da tentativa atual/final |
| `run_id` | correlaciona todas as tentativas do mesmo disparo |
| `executor_type` | executor efetivo persistido no histórico (`docker_exec`, `sql_procedure`) |
| `execution_target` | alvo efetivo persistido no histórico (container ou statement resumido) |
| `post_checks_status` | resultado ortogonal da validação pós-execução |
| `post_checks_result` | detalhes dos checks, inclusive skips por cooldown |

### `GET /api/tasks`

Lista o inventário vivo do catálogo.
Para compatibilidade, `GET /api/jobs` devolve o mesmo payload com as chaves `tasks` e `jobs`.

Exemplo:

```json
{
  "tasks": [
        {
            "nome": "gerar_metas_proximo_mes",
            "container": null,
            "grupo": "metas",
            "descricao": "Importado de pg_cron jobid=2, jobname=gerar_metas_proximo_mes, owner=prospere, active=true",
            "enabled": true,
            "cron": "0 7 1 * *",
      "prioridade": "medium",
      "timeout_seconds": 600,
      "max_retries": 2,
      "executor_type": "sql_procedure",
      "post_checks": [
        {
          "name": "fct_metas_atualizada_recente",
          "sql": "SELECT EXISTS(...)",
          "severity": "error",
          "cooldown_minutes": 30,
          "timeout_seconds": 30
        }
      ],
      "dependencies": [],
      "params_aceitos": ["profile"]
    },
    {
      "nome": "consultar_processos",
      "container": "process-automation",
      "project_slug": "process-automation",
      "runtime_kind": "python",
      "entrypoint": "python run.py consultar_processos",
      "setor": "juridico",
      "modulo": "processos",
      "submodulo": null,
      "source_kind": "python_job",
      "source_ref": "setores/juridico/processos/consultar_processos/consultar_processos.py",
      "taxonomy_origin": "derived",
      "classification_path": "juridico > processos",
      "schedule_origin": "manual",
      "disabled_reason": null,
      "replacement_tasks": [],
      "owner_team": "juridico",
      "grupo": "juridico",
      "descricao": "Busca semântica nos processos indexados via RAG com contexto completo ou híbrido; executa sob demanda.",
      "enabled": true,
      "cron": null,
      "prioridade": "medium",
      "timeout_seconds": 1800,
      "max_retries": 1,
      "executor_type": "docker_exec",
      "dependencies": [],
      "params_aceitos": ["area", "caso", "processo", "profile", "query", "top_k"],
      "input_schema": {
        "required": ["query"],
        "properties": {
          "query": {"transport": "env", "env": "RAG_QUERY"},
          "caso": {"transport": "env", "env": "RAG_CASO"}
        }
      }
    }
  ],
  "params_aceitos": ["area", "caso", "cnpj", "cnpjs", "date_from", "date_to", "executar", "limit", "processo", "profile", "query", "reprocess", "top_k"],
  "params_aceitos_globais": ["cnpj", "cnpjs", "date_from", "date_to", "limit", "profile", "reprocess"]
}
```

Nota:
- No `process-automation`, `source_ref` canônico agora aponta para `setores/...`.
- Referências antigas a `jobs/...` devem ser tratadas como compatibilidade histórica.

Metadados adicionais do inventário:

| Campo | Significado |
|-------|-------------|
| `project_slug` | projeto/owner lógico da task |
| `runtime_kind` | `python`, `shell`, `sql_procedure` ou `docker_exec` |
| `entrypoint` | comando/statement normalizado |
| `schedule_origin` | `hub`, `pg_cron_migrated` ou `manual` |
| `disabled_reason` | motivo estruturado quando `enabled=false` |
| `replacement_tasks` | tasks substitutas para legado/deprecated |
| `owner_team` | time/domínio responsável |
| `setor` | setor funcional da task |
| `modulo` | módulo funcional principal |
| `submodulo` | agrupamento intermediário opcional |
| `source_kind` | tipo de origem técnica do executável |
| `source_ref` | caminho/identificador técnico canônico |
| `taxonomy_origin` | origem da classificação taxonômica |
| `classification_path` | caminho funcional consolidado (`setor > modulo > submodulo`) |
| `post_checks` | validações SQL pós-execução cadastradas no catálogo |

Para detalhes completos de uma task, incluindo `executor_config.connection_user`
quando presente, use `GET /api/tasks` junto com `docker exec hub-orchestration python run.py tasks show <task>`.

### `GET /api/tasks/history`

Retorna execuções recentes.

Query params:

| Param | Default | Descrição |
|-------|---------|-----------|
| `task` | todos | Filtra por nome da task |
| `limit` | `20` | Máximo `500` |

Exemplo:

`GET /api/tasks/history?task=gerar_metas_proximo_mes&limit=5`

O alias legado `GET /api/jobs/history?job=gerar_metas_proximo_mes&limit=5` continua aceito.

Exemplo de resposta:

```json
{
  "execucoes": [
    {
      "exec_id": 4321,
      "run_id": "c5f7b8d02d8f4dc6bb6ca4b5d9328ef6",
      "task": "gerar_metas_proximo_mes",
      "job": "gerar_metas_proximo_mes",
      "status": "success",
      "inicio": "2026-04-19T09:20:00",
      "fim": "2026-04-19T09:20:04",
      "duracao_ms": 4012,
      "exit_code": 0,
      "tentativa": 1,
      "initiated_by": "cron",
      "worker_id": "scheduler-worker_0",
      "executor_type": "sql_procedure",
      "execution_target": "CALL metas.sp_gerar_metas_proximo_mes()",
      "post_checks_status": "passed"
    }
  ]
}
```

## Exemplo Python

```python
import os
import requests

ORCH_URL = "http://hub-orchestration:8080"
API_KEY = os.getenv("HUB_ORCH_API_KEY")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def disparar(task: str, params: dict | None = None, initiated_by: str = "meu-servico") -> dict:
    resp = requests.post(
        f"{ORCH_URL}/api/tasks/trigger",
        json={"task": task, "job": task, "params": params or {}, "initiated_by": initiated_by},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def status(exec_id: int) -> dict:
    resp = requests.get(
        f"{ORCH_URL}/api/tasks/{exec_id}/status",
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

## Notas

1. A API é assíncrona: `trigger` retorna `202` e a execução continua em background.
2. O lock impede concorrência da mesma task e a aquisição também serializa recursos compartilhados para fechar corridas entre scheduler e API.
3. Scheduler e API passam pelo mesmo gate de despacho; um trigger manual não contorna dependências, `pre_condition_sql`, capacidade nem lock.
4. O retry e o circuit breaker seguem a configuração da task no catálogo.
5. Tasks que usam a Smart API concorrem pelo mesmo recurso `resource:smart_api`; com `RESOURCE_CAPACITY_SMART_API=1`, apenas uma roda por vez, inclusive sob chamadas concorrentes.
6. O inventário de tasks e seus contratos de entrada não deve ser mantido manualmente em documentação externa; a fonte viva é `GET /api/tasks`.
7. Tasks `sql_procedure` executam com conexão dedicada `DB_HUB_*`; opcionalmente podem assumir `connection_user` via `SET ROLE`.
8. Retries são persistidos como tentativas separadas em `task_execucao`, correlacionadas por `run_id`.
9. `executor_type` e `execution_target` vêm de snapshot do momento do disparo; continuam estáveis mesmo se a task for editada ou removida do catálogo depois.
10. Post-checks não mudam o `status` principal da execução; use `post_checks_status` para distinguir sucesso técnico de sucesso de qualidade.
