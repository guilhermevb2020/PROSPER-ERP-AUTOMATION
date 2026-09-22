# Envio em lote de boletos — SmartSecurities

Robô que envia boletos do SmartSecurities em massa via POST HTTP direto,
reutilizando a sessão de um Chrome persistente. Substitui o robô local que
rodava na máquina do operador.

## Localização

```
src/processors/web/boletos/
├── _config.py        (interno) constantes, URLs, paths, defaults seguros
├── _sessao.py        (interno) login interativo + keepalive + helpers Playwright
├── _db.py            (interno) conexão Postgres + log em operacional.boleto_envio_log
├── manter_sessao.py  ENTRYPOINT: sobe Chrome persistente, expõe CDP 9222
├── enviar_lote.py    ENTRYPOINT: FASE 1 (preview) + FASE 2 (envio)
└── templates/
    ├── listatitulos.txt   POST body para listatitulosboletos.php
    └── envio.txt          POST body para printcobrancapdf.php
```

Volumes persistentes (no host):
```
data/boletos/
├── perfil_chrome/    user-data-dir do Chrome (cookies, histórico)
├── debug/            screenshots de debug
└── logs/             (vazio — log canônico agora é Postgres)
```

## Arquitetura

```
┌────────────────────────────────────────────────────────────────┐
│ erp-automation container                                       │
│                                                                │
│  ┌────────────┐                                                │
│  │ Xvfb :99   │ ◄─── x11vnc ◄─── noVNC ◄─── nginx ◄─── tunel  │
│  └─────┬──────┘                                                │
│        │                                                       │
│  ┌─────▼──────────┐                                            │
│  │ Chrome         │  ──── CDP 9222 ────► outros processos      │
│  │ perfil persist │  PHPSESSID em memoria                      │
│  └─────┬──────────┘                                            │
│        │                                                       │
│  ┌─────▼─────────────────┐    ┌──────────────────────────┐    │
│  │ manter_sessao.py      │    │ enviar_lote.py           │    │
│  │  - login interativo   │    │  - conecta via CDP       │    │
│  │  - keepalive 120s     │    │  - lista contas + titulos│    │
│  │  - mantem PID vivo    │    │  - filtra cooldown (DB)  │    │
│  └───────────────────────┘    │  - envia via POST HTTP   │    │
│                               │  - grava em DB           │    │
│                               └──────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────────┐
                    │ Postgres             │
                    │ operacional.         │
                    │  boleto_envio_log    │
                    └──────────────────────┘
```

## Travas de segurança (não enviar por acidente)

Pra enviar de verdade, **3 flags** precisam estar setadas ao mesmo tempo:

```bash
DRY_RUN=false  SCAN=false  CONFIRMAR=1
```

Defaults seguros (em `_config.py`):

- `DRY_RUN = True` (preenche e para antes do POST)
- `SCAN = True` (read-only, lista mas não envia)
- `CONFIRMAR = false` (lido só do env)
- `TETO = 800` (aborta se mais que 800 boletos numa execução)

Anti-duplicação: o que já tem status `ok`, `enviado_timeout` ou `incerto` em
`operacional.boleto_envio_log` para a mesma `data_emissao` é pulado.
Status `falha` é re-elegível.

## Fluxo operacional

### 1. Sessão (login uma vez, depois fica viva)

A sessão do Smart usa **cookie de sessão** (`PHPSESSID`, `expires=-1`) — ele
**não persiste após o Chrome fechar**. Por isso:

- Toda vez que o **container reinicia** ou o **Chrome morre**: precisa logar de novo.
- Enquanto o Chrome estiver vivo: o keepalive (`manter_sessao.py`) faz GET a
  cada 120s na URL `frmimpriboleto.php?Via=1` e mantém o cookie ativo no
  servidor do Smart.

#### Como logar

1. Acesse [https://vnc.prospereinvest.com.br/vnc.html](https://vnc.prospereinvest.com.br/vnc.html)
2. Login do Authelia (seu usuário Prospere)
3. Tela noVNC abre. Clique **Connect**. Senha VNC: veja `VNC_PASSWORD` no
   `.env` do `erp-automation` (fora do git)
4. O Chrome do servidor aparece na tela
5. Acesse `https://www.smartsecurities.com.br/smartsecurities/`
6. Faça login normal — credenciais em `config/boletos.env` no servidor
   (`BOLETO_EMAIL` / `BOLETO_SENHA`, fora do git)
7. Resolva o reCAPTCHA na tela
8. Selecione a empresa **PROSPER VETOR SECURITIZADORA S.A.**
9. Pronto. Pode fechar a aba do noVNC — o Chrome continua rodando.

Validação rápida do servidor:
```bash
docker exec erp-automation python -c "
from playwright.sync_api import sync_playwright
from src.processors.web.boletos._sessao import esta_logado
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    print('esta_logado =', esta_logado(b.contexts[0]))
"
```

#### Subir o `manter_sessao.py`

Se o container reiniciou, ou se o Chrome morreu, antes de logar você precisa
subir o keepalive de novo:

```bash
docker exec -d -e DISPLAY=:99 erp-automation \
  python -m src.processors.web.boletos.manter_sessao
```

Ele sobe o Chrome com o perfil persistente. Quando você logar pelo VNC, a
sessão fica viva até o próximo restart.

#### Quando o Chrome trava (CDP meio-morto)

Existe um estado de falha que **não** é "sessão caiu" e **não** é "Chrome
morreu": o processo continua vivo, o endpoint HTTP do CDP responde 200
normalmente, mas o **handshake do WebSocket nunca completa**. Como todo job usa
`connect_over_cdp` (que é WebSocket), tudo trava — mas qualquer diagnóstico
baseado em HTTP diz que está tudo bem.

Sintomas:

- `boletos_healthcheck` sai de ~1s para **exatamente 180s** (timeout interno do
  Playwright) e passa a registrar `needs_login` sem parar
- `emitir_lote` sai com **exit 2** (`nao consegui conectar no CDP`)
- `enviar_lote` sai com **exit 1**, com `Opening in existing browser session` —
  ele caiu no fallback `launch_persistent_context`, que tenta abrir o **mesmo
  perfil** que o Chrome vivo já segura, e portanto falha sempre
- o snippet de validação da seção anterior **pendura** em vez de responder

Diagnóstico em 5s — o HTTP responde, o WebSocket não:

```bash
# 1) HTTP: responde 200 mesmo travado (NAO serve como prova de vida)
docker exec erp-automation curl -s -m 5 http://127.0.0.1:9222/json/version

# 2) WebSocket: e isto que os jobs usam
docker exec erp-automation python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=15000)
    print('CDP ok, contextos =', len(b.contexts))
"
```

Se (1) responde e (2) estoura, o Chrome está travado. **A correção é reiniciar,
não logar de novo:**

```bash
docker exec erp-automation pkill -9 -f manter_sessao
docker exec erp-automation pkill -9 -f "remote-debugging-port=9222"
docker exec erp-automation sh -c 'rm -f /app/data/boletos/perfil_chrome/Singleton*'
docker exec -d -e DISPLAY=:99 erp-automation \
  python -m src.processors.web.boletos.manter_sessao
```

> O padrão `remote-debugging-port=9222` casa **apenas** com o Chrome de boletos.
> O Chrome do `credito` usa `--remote-debugging-pipe`, sem porta, e não é
> atingido — dá para reiniciar boletos com o robô de crédito rodando.

O `manter_sessao` já tenta CapSolver ao subir, então normalmente não precisa de
VNC. Só vá ao VNC se o CapSolver falhar.

##### Incidente 26–27/07/2026 (por que a sonda mudou)

O `chrome_ok()` testava só o HTTP. Resultado: das 20:15 de 26/07 até as 12:08 de
27/07 o healthcheck classificou o travamento como `needs_login` e **nunca chamou
`religar_chrome()`** — a auto-recuperação que já existia e resolveria em um tick
de 15 min. Perderam-se os três lotes do dia (8 boletos entregues contra ~150 de
uma segunda normal).

A aritmética dos timeouts explica o circuit breaker:

| Situação | O que roda | Tempo |
|---|---|---|
| Fora da janela de relogin | `sessao_logada()` travada | 180s → task "passa" |
| Dentro da janela (7h–12h) | `sessao_logada()` **+** segundo `connect_over_cdp` | >240s → **timeout** |

Três timeouts seguidos abriram o circuit breaker e desabilitaram a task. O login
automático **não teve culpa** — a task morria antes de chegar no CapSolver.

Correções aplicadas em `healthcheck.py`:

- `chrome_ok()` agora testa o **WebSocket**, não o HTTP, e trata "browser sem
  contexto" como down (era o `IndexError` por trás do exit 2 do `emitir_lote`)
- todo `connect_over_cdp` do healthcheck tem teto explícito (`CDP_TIMEOUT_MS`,
  20s), para o diagnóstico caber no timeout de 240s da task

### 2. Executar manualmente (sem hub)

#### SCAN read-only (preview do dia, sem enviar)

```bash
docker exec erp-automation python -m src.processors.web.boletos.enviar_lote
```

Defaults: `DRY_RUN=true SCAN=true`. Lista as contas e mostra quantos boletos
existem para o último dia útil. Não envia nada.

#### Envio real (modo "produção" manual)

```bash
docker exec \
  -e DRY_RUN=false -e SCAN=false -e CONFIRMAR=1 \
  -e MODALIDADE=C \
  erp-automation \
  python -m src.processors.web.boletos.enviar_lote
```

#### Envio cirúrgico (1 título específico — para testes)

```bash
docker exec \
  -e DRY_RUN=false -e SCAN=false -e CONFIRMAR=1 \
  -e MODALIDADE=G \
  -e SO_CONTA_ID=290 \
  -e DATA=07/01/2026 -e DATA_FINAL=07/01/2026 \
  -e SO_TITULO_IDS=824062 \
  erp-automation \
  python -m src.processors.web.boletos.enviar_lote
```

### 3. Executar via hub-orchestration

Task registrada como **`enviar_lote_boletos`** com `enabled=false` e
`disabled_reason='aguardando_validacao_pos_migracao'`.

```bash
# Ver estado
docker exec hub-orchestration python run.py tasks show enviar_lote_boletos

# Rodar uma vez manualmente (mesmo desabilitada — usar pra testar)
docker exec hub-orchestration python run.py run enviar_lote_boletos

# Habilitar (passa a respeitar o cron 0 9 * * 1-5)
docker exec hub-orchestration python run.py enable enviar_lote_boletos

# Desabilitar
docker exec hub-orchestration python run.py disable enviar_lote_boletos
```

Cron: **9h de manhã, dias úteis** (`0 9 * * 1-5`).

Comando registrado:
```
env DRY_RUN=false SCAN=false CONFIRMAR=1 MODALIDADE=C
    python -m src.processors.web.boletos.enviar_lote
```

## Variáveis de ambiente

| Var | Default | Significado |
|---|---|---|
| `DRY_RUN` | `true` | Para antes do POST de envio |
| `SCAN` | `true` | Read-only: lista mas não envia |
| `CONFIRMAR` | `(vazio)` | `1` libera envio real |
| `DATA` | último dia útil | DD/MM/YYYY — emissão inicial |
| `DATA_FINAL` | = DATA | DD/MM/YYYY — emissão final |
| `SO_CONTA_ID` | `(vazio)` | Restringe a uma conta específica (id do dropdown) |
| `SO_CONTA` | `(vazio)` | Restringe pelo rótulo da conta (lowercase) |
| `SO_TIPO` | `(vazio)` | `padrao` ou `mp` — filtra tipo de conta |
| `SO_TITULO_IDS` | `(vazio)` | CSV de ids — envio cirúrgico (whitelist) |
| `MODALIDADE` | `C` | `C`=Convencional, `T`=Trustee, `G`=Todas |
| `NOP` | `(vazio)` | Filtro de número de operação no POST de listagem |
| `NUM_DOC` | `(vazio)` | Filtro de número do documento |
| `MAX_CONTAS` | `0` | Limita quantas contas processar (0 = todas) |
| `HEADLESS` | `false` | Precisa false enquanto loga manualmente |
| `DISPLAY` | `:99` | Xvfb |
| `CDP_PORT` | `9222` | Porta do remote debugging |
| `HUB_RUN_ID` | (vazio) | Correlaciona com `task_execucao.run_id` (passado pelo hub) |

## Log canônico

Tabela: **`operacional.boleto_envio_log`**

| Coluna | Tipo | Significado |
|---|---|---|
| `id` | bigserial | PK |
| `id_titulo` | text | id do `checkEnvio` no Smart |
| `conta_id` | text | id no dropdown contaCorrente |
| `conta_label` | text | nome da conta (Banco do Brasil, etc.) |
| `modalidade` | varchar(2) | C / T / G |
| `valor` | numeric(15,2) | valor do boleto |
| `sacado` | text | nome do sacado |
| `data_emissao` | date | data de emissão filtrada |
| `data_envio` | timestamp | quando o POST foi feito |
| `status` | text | `ok` / `enviado_timeout` / `incerto` / `falha` / `pulada` |
| `erro` | text | trecho da exceção/HTTP body, se houver |
| `run_id` | text | run_id da execução (correlaciona com hub) |
| `extras` | jsonb | data_final, nop, num_doc, e qualquer metadado |

Consultas úteis:

```sql
-- envios de hoje
SELECT conta_label, status, COUNT(*), SUM(valor)::numeric(15,2)
FROM operacional.boleto_envio_log
WHERE data_envio::date = CURRENT_DATE
GROUP BY 1, 2 ORDER BY 1, 2;

-- ids já enviados para uma data de emissão
SELECT id_titulo, status
FROM operacional.boleto_envio_log
WHERE data_emissao = '2026-06-03'
  AND status IN ('ok','enviado_timeout','incerto');

-- correlação com hub
SELECT b.*, t.task_nome, t.status AS hub_status, t.duracao_ms
FROM operacional.boleto_envio_log b
LEFT JOIN hub_orchestration.task_execucao t USING (run_id)
WHERE b.data_envio >= NOW() - INTERVAL '7 days'
ORDER BY b.data_envio DESC;
```

## Notificações de resultado

O hub-orchestration já manda **email diário consolidado às 19h** com:
- Execução de cada task: sucesso, falha, duração.
- Inventário dos containers.
- Banner 🟢🟡🔴 conforme severidade.

Quando `enviar_lote_boletos` rodar (`enabled=true`), aparece nesse resumo
automaticamente. Não precisa criar notificação dedicada.

## Troubleshooting

### "Sessão inválida" (`esta_logado=False`)

Causas:
1. Container foi reiniciado → cookie session sumiu → logar de novo no VNC.
2. Chrome crashou → mesmo procedimento.
3. Smart expirou a sessão server-side (raríssimo com keepalive).

**Fix**: subir `manter_sessao.py` + logar no VNC (procedimento acima).

### "Conexão recusada CDP 9222"

O processo `manter_sessao.py` morreu ou nem subiu.

```bash
# Verificar
docker exec erp-automation pgrep -af manter_sessao

# Subir se não tiver
docker exec -d -e DISPLAY=:99 erp-automation \
  python -m src.processors.web.boletos.manter_sessao
```

### "TIMEOUT no envio" (FASE 2)

Contas grandes (ex: BB com 200+ boletos) podem demorar. O código trata
**TIMEOUT como provavelmente-enviado**: gravamos `status='enviado_timeout'` e
não re-enviamos (evita duplicação). Confirmar manualmente no histórico do
Smart se quiser certeza.

### Envio errado / quer re-enviar

Como anti-dup é baseado em (`id_titulo`, `data_emissao`, status not in `falha`),
para re-enviar:

```sql
DELETE FROM operacional.boleto_envio_log
WHERE id_titulo = 'X' AND data_emissao = 'YYYY-MM-DD';
```

Ou mude a `data_emissao` da execução com `DATA=DD/MM/YYYY`.

### Login fica em loop sem detectar

O `manter_sessao.py` espera 600s (10min) o operador resolver o reCAPTCHA.
Se passou disso, o processo morre. Reinicie e tenta de novo, sem fechar a
aba do VNC entre tentativas.

## Histórico de mudanças

- **2026-06-04** — Migração inicial do robô local. Pasta `_testes_boletos/`.
- **2026-06-05** — CSV → Postgres. Saiu do experimental: `boletos/`.
  Task `enviar_lote_boletos` registrada no hub (disabled).
- **2026-06-08** — Auto-recovery via CapSolver + healthcheck + janela 9h-12h. Envio habilitado.
- **2026-06-11** — Robô de EMISSÃO adicionado (cron 09:30, dias úteis). Pasta `boletos/` agora cobre os 2 fluxos (emitir + enviar).

---

# Robô de EMISSÃO (`emitir_lote.py`)

Roda **antes** do envio. Gera/imprime os boletos no Smart pra que o robô de envio consiga pegá-los às 10h.

## Sequência diária em produção

| Hora BRT | Task no hub | O que faz |
|---|---|---|
| `*/15 * * * *` | `boletos_healthcheck` | Verifica/religa sessão Smart |
| `30 9 * * 1-5` | **`emitir_lote_boletos`** 🆕 | Emite tudo que está pendente no dia (BB + MPs) |
| `0 10 * * 1-5` | `enviar_lote_boletos` | Pega o que foi emitido às 09:30 e dispara emails |

## Diferenças vs envio

| | Emissão | Envio |
|---|---|---|
| Endpoint Smart | `Via=1` + `boleto=1` | `Via=2` + email/anexos |
| Modalidade | `G` (Todas) | `C` (Convencional) |
| Grupos | Convencional **e** Oculto | Apenas Convencional Padrão |
| Em nome | `f` (Securitizadora) ou `c` (Cedente) | (não usa) |
| Classes BB | `P`, `T` | `P`, `T`, `CL` |
| Classes MP | `E`, `B`, `BG`, `CL`, `I` | (não usa) |
| Tabela log | `operacional.boleto_emissao_log` | `operacional.boleto_envio_log` |

## Regras de negócio (validadas no código + no banco)

- ✅ **MP → em nome do CEDENTE** (`ImprimirBoletoEmNome=c`)
- ✅ **BB/SICOOB → em nome da SECURITIZADORA** (`ImprimirBoletoEmNome=f`)
- ⛔ **NUNCA classe `C` (Comissária)** nem **`CE` (Comissária com Escrow)** — não estão na lista de classes de nenhum grupo. Mesmo que existam no Smart, não são retornadas no POST de listagem.

## Modos de execução

| Var | Default | Significado |
|---|---|---|
| `SCAN_EMISSAO` | `true` | Read-only: lista pendentes, não emite |
| `DRY_RUN_EMISSAO` | `true` | Para antes do POST de print |
| `CONFIRMAR` | (vazio) | `1` libera emissão real |
| `SO_CONTA_ID` | (vazio) | Restringe a uma conta (id do dropdown) |
| `SO_GRUPO` | (vazio) | `convencional` ou `oculto` |
| `CONTAS_IGNORAR_EMISSAO` | (vazio) | CSV de labels a pular |
| `PASSADAS` | `2` | 1=emite só; 2=valida que sumiu da lista |
| `TETO_CONTAS_EMISSAO` | `70` | Trava — aborta se mais contas que isso |
| `DELAY_ENTRE_CONTAS_EMISSAO` | `3` | Pausa entre contas (s) |
| `DELAY_ENTRE_PASSADAS` | `2` | Pausa entre 1ª e 2ª passada (s) |

## Comandos úteis

```bash
# SCAN read-only (preview do que está pendente)
docker exec -e SCAN_EMISSAO=true erp-automation \
  python -m src.processors.web.boletos.emitir_lote

# SCAN só ocultas
docker exec -e SCAN_EMISSAO=true -e SO_GRUPO=oculto erp-automation \
  python -m src.processors.web.boletos.emitir_lote

# Emitir 1 conta (teste)
docker exec \
  -e SCAN_EMISSAO=false -e DRY_RUN_EMISSAO=false -e CONFIRMAR=1 \
  -e SO_CONTA_ID=290 \
  erp-automation \
  python -m src.processors.web.boletos.emitir_lote

# Rodar via hub (com histórico)
docker exec hub-orchestration python run.py run emitir_lote_boletos

# Desabilitar / habilitar
docker exec hub-orchestration python run.py disable emitir_lote_boletos
docker exec hub-orchestration python run.py enable emitir_lote_boletos
```

## Log canônico

Tabela: **`operacional.boleto_emissao_log`** (migration 081)

| Coluna | Tipo | Significado |
|---|---|---|
| `id` | bigserial | PK |
| `conta_id` | text | value do dropdown contaCorrente |
| `conta_label` | text | nome da conta |
| `grupo` | text | `convencional` ou `oculto` |
| `classes_risco` | text[] | classes emitidas (`{P,T}` ou `{E,B,BG,CL,I}`) |
| `radio_em_nome` | varchar(1) | `f` (Securitizadora) ou `c` (Cedente) |
| `qtd_titulos` | int | IDs detectados na 1ª passada |
| `qtd_apos_2pass` | int | IDs detectados na 2ª passada (deve ser 0) |
| `passada` | int | 1 ou 2 (qual passada gravou) |
| `status` | text | `ok` / `vazio` / `falha` / `alerta_sem_efeito` / `preview` |
| `erro` | text | mensagem se houve erro |
| `content_type` | text | CT do response do print (deve conter `pdf`) |
| `run_id` | text | correlaciona com hub |
| `extras` | jsonb | metadados |

## Defesa em profundidade

`emitir_lote.py` tem **3 camadas** garantindo que a emissão funcione mesmo se algo der errado:

1. **Healthcheck (a cada 15 min)** mantém sessão Smart viva via CapSolver
2. **Fallback in-task**: se ao iniciar `emitir_lote.py` a sessão estiver caída, tenta CapSolver **antes de abortar**
3. **Trava `TETO_CONTAS`**: se a quantidade de contas a processar for absurda (>70), aborta sem fazer nada

## Compartilhamento de sessão com o envio

O `emitir_lote.py` e o `enviar_lote.py` **usam o mesmo Chrome** (PID único do `manter_sessao`, perfil em `/app/data/boletos/perfil_chrome`, CDP na porta 9222). Cookies do Smart (PHPSESSID) são compartilhados — não duplica reCAPTCHA, não abre 2 sessões paralelas.

## Próximo passo após primeiro dia em produção

Olhar nas tabelas:

```sql
-- Resumo de hoje
SELECT
  status, grupo, COUNT(*) AS contas, SUM(qtd_titulos) AS titulos
FROM operacional.boleto_emissao_log
WHERE emitido_em::date = CURRENT_DATE
GROUP BY 1,2 ORDER BY 1,2;

-- Alertas (emissão que pode não ter surtido efeito)
SELECT conta_label, qtd_titulos, qtd_apos_2pass, emitido_em
FROM operacional.boleto_emissao_log
WHERE status = 'alerta_sem_efeito' AND emitido_em > NOW() - INTERVAL '24 hours';
```

## Healthcheck e sessão (medido em 07/09/2026)

O healthcheck efetivo usa a janela 7h–18h (os padrões do módulo são sobrescritos pelo Hub);
`needs_login_fora_janela` com exit 0 **não** significa sessão saudável. O mantenedor loga ao
iniciar; emissão e healthcheck fazem a recuperação posterior. PDFs de emissão ficam em
`/app/data/boletos/emitidos`, com manifesto; não versionar esses documentos.
