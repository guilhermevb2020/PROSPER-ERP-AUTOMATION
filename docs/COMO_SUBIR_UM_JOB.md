# Como subir um job do ERP para o servidor

Receita de ponta a ponta para transformar um pacote que roda no Windows com login
manual num robô que roda **sozinho** no container `erp-automation`, agendado pelo
`hub-orchestration`.

Escrita a partir da subida do **robô de remessa** em 31/07–03/08/2026. As
armadilhas do fim do documento **não são hipóteses** — cada uma custou tempo numa
subida real, e três delas produzem *falha que parece sucesso*, que é a pior
espécie.

> **Antes de começar, leia o robô que mais se parece com o seu.**
> `src/processors/web/retorno_cobranca/` é o mais recente e o molde deste guia — é o
> primeiro a consumir a sessão compartilhada (`src/common/clients/smart_sessao.py`),
> e por isso tem só 4 arquivos. `remessa_cobranca/` é anterior a esse módulo: copie
> dele a **lógica de tela** (`gerar.py`), não a sessão. `doc2you/` é o modelo de
> "loga 1×/dia, faz o trabalho e fecha".

---

## 0. O anatomia de um robô daqui

Todos têm a mesma forma:

- **Playwright + Chrome** com perfil persistente, num **display Xvfb próprio**;
- **login automático via CapSolver**, sem gente;
- **trabalho por HTTP** sobre os cookies da sessão (não por clique em tela);
- **um wrapper `run_agendado.sh`** que garante o display e chama o Python;
- **uma task no hub**, que dispara por cron e registra exit code, log e duração.

O que **não** é robô daqui: script que precisa de alguém olhando, ou que só roda
na máquina de uma pessoa.

---

## 1. Reserve o slot — display, portas e perfil

**Nunca compartilhe display nem perfil com outro robô.** Dois Chromes no mesmo
display fazem o login *quicar* de volta para a landing (custou dias no doc2you), e
dois no mesmo `user-data-dir` disputam o lock — um simplesmente não sobe.

| Robô | DISPLAY | VNC | noVNC | CDP | Perfil |
|---|---|---|---|---|---|
| `boletos` | `:99` | 5900 | 6080 | 9222 | `data/boletos/perfil_chrome` |
| `doc2you` | `:98` | 5901 | 6081 | 9223 | `data/doc2you/perfil_chrome` |
| `remessa_cobranca` | `:97` | 5903 | 6083 | 9224 | `data/robo_remessa/perfil_chrome` |
| `credito` | `:96` | 5902 | 6082 | *(pipe)* | `data/robo_credito/perfil_chrome` |
| `retorno_cobranca` | `:95` | 5904 | 6084 | 9225 | `data/robo_retorno/perfil_chrome` |
| `remessa_pagamento` | `:94` | 5905 | 6085 | 9226 | `data/robo_pagamento/perfil_chrome` |
| `retorno_pagamento` | `:93` | 5906 | 6086 | 9227 | `data/robo_retorno_pagamento/perfil_chrome` |
| **próximo livre** | **`:92`** | **5907** | **6087** | **9228** | `data/<job>/perfil_chrome` |

> Atualizada em 26/08/2026, quando o `retorno_pagamento` ocupou o `:93` que
> esta tabela anunciava como livre. **Quem toma um slot atualiza esta linha no
> mesmo commit** —
> tabela desatualizada aqui é dois Chromes no mesmo display, que é a falha nº 1 do §1.
> Quem roda junto com quem (horários): [`orchestracao.md`](orchestracao.md#quem-roda-quando).

Confira antes de assumir que está livre:

```bash
docker exec erp-automation sh -c 'pgrep -a Xvfb; ss -ltnp 2>/dev/null | grep -E "59[0-9]{2}|60[89][0-9]|92[0-9]{2}"'
```

O noVNC é exposto por rota no nginx (`/d2/` → 6081, `/rc/` → 6082). Se quiser VNC
de acompanhamento para o robô novo, peça a rota — sem ela a porta só existe dentro
da rede do container.

---

## 2. Estrutura do pacote

```
src/processors/web/<job>/
├── __init__.py           docstring: o que faz, qual o entrypoint agendado
├── <job>.py             entrypoint: main() + exit codes
├── <job>_config.py      TUDO por env; zero caminho de Windows
├── run_agendado.sh       wrapper do hub (display + env + python)
└── docs/README.md        obrigatório — inclusive o que NÃO foi testado
```

Prefixo `_` = privado ao robô. Sem prefixo = alguém de fora pode importar.

**Sem `_sessao.py` e sem `login.py` próprios.** Subir o Chrome, detectar sessão
morta e logar já são de `src/common/clients/smart_sessao.py` (§4 e §5). O
`remessa_cobranca` ainda tem os dois porque é anterior a esse módulo; o `retorno_cobranca`
é o primeiro a consumi-lo e por isso é **o molde a copiar**.

---

## 3. Config: tudo por env, e a var do display é **própria**

```python
DISPLAY = _s("DISPLAY_REM", ":97")     # ✅ var própria
DISPLAY = _s("DISPLAY", ":97")         # ❌ herda :99 dos boletos
```

O `docker-compose.yml` define `DISPLAY=:99` para **todo processo** do container.
Se o seu config ler `DISPLAY`, um `docker exec` sem `-e` sobe o seu Chrome em cima
do dos boletos. Use sufixo (`_REM`, `_PROC`, …) em tudo: display, porta CDP,
perfil, `DRY_RUN`, pastas.

E o `_sessao.py` deve **publicar** o valor antes de subir o Chrome, porque o
Chrome herda o `DISPLAY` do processo:

```python
os.environ["DISPLAY"] = cfg.DISPLAY
```

### Credenciais

Nunca no fonte — **este repo tem remote público**.

```
config/<job>.env           real, modo 600, gitignored por `config/*.env`
config/<job>.example.env   template com campos vazios, versionado
```

O `.gitignore` já re-inclui `!config/*.example.*`, então o exemplo entra sozinho.

---

## 4. Login e sessão: **não reimplemente — importe**

O login do Smart já tem duas implementações (a sync em `boletos/_sessao.py`, a
async em `doc2you/_login.py`). Uma terceira é o que a regra 3 do `CLAUDE.md`
proíbe. Desde 08/2026 nem é preciso delegar à mão: está tudo em
`src/common/clients/smart_sessao.py`, que entrega

| função | o que resolve |
|---|---|
| `parece_deslogado(html)` | o `expira.php` — a armadilha nº 1 lá embaixo |
| `esta_logado(ctx, cfg)` | ping HTTP autenticado contra a tela do robô |
| `sessao_viva(ctx, cfg)` | ping com retentativa (timeout ≠ sessão morta) |
| `login(ctx, cfg)` | delega ao fluxo CapSolver já em produção (boletos) |
| `abrir_chrome(p, cfg)` / `anexar(p, cfg)` | launch com os 2 args do container |
| `sessao(p, cfg)` | context manager: entrega `ctx` logado e fecha no fim |

```python
from src.common.clients import smart_sessao

with smart_sessao.sessao(p, cfg, log=log) as ctx:
    if not smart_sessao.sessao_viva(ctx, cfg, log=log):
        return 3
    ...          # ctx.request.get/post autenticados
```

O `cfg` do seu robô só precisa expor: `EMAIL`, `SENHA`, `URL_PING`, `URL_LOGIN`,
`USER_DATA_DIR`, `CDP_PORT`, `CDP_URL`, `DISPLAY`, `HEADLESS` e `ensure_dirs()`.

Aponte `URL_PING` para **a tela que o seu robô precisa**. Assim "logado" passa a
significar "alcança a tela", e um usuário sem permissão falha no começo, com
mensagem clara — em vez de virar "não há nada a fazer" lá na frente.

Efeito colateral conhecido: screenshot de falha de login cai em
`data/boletos/debug/`, porque o `DEBUG_DIR` é constante lá.

---

## 5. Sessão própria, e o Chrome precisa de dois argumentos

É o que `smart_sessao.abrir_chrome()` faz por você — está aqui para você
reconhecer os dois argumentos que **não** podem sumir se algum dia editar aquilo:

```python
ctx = p.chromium.launch_persistent_context(
    user_data_dir=cfg.USER_DATA_DIR,
    headless=cfg.HEADLESS, channel="chrome",
    args=[f"--remote-debugging-port={cfg.CDP_PORT}", "--start-maximized",
          "--no-sandbox",             # roda como root no container
          "--disable-dev-shm-usage"], # /dev/shm pequeno mata o Chrome
    no_viewport=True)
```

**Modelo de produção: self-contained.** Sobe, loga, trabalha, **fecha**. Nada de
keep-alive 24/7 — é o desenho do `doc2you` e do `remessa_cobranca`. Keep-alive só onde
já existe (boletos), porque alguém precisa da sessão o dia inteiro.

---

## 6. `run_agendado.sh`

Copie de `retorno_cobranca/run_agendado.sh` e troque display/portas/nome. Os pontos
que **não** podem ser simplificados:

```sh
#!/bin/sh
set -u
cd /app || exit 1
LOG=/app/logs/vnc; mkdir -p "$LOG"

# 1) credenciais (arquivo montado, fora do git)
[ -f /app/config/<job>.env ] && { set -a; . /app/config/<job>.env; set +a; }

# 2) mata Chrome órfão SÓ do seu perfil (nunca pkill genérico de chrome!)
PERFIL="${USER_DATA_DIR_X:-/app/data/<job>/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1; rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# 3-6) Xvfb :94 + fluxbox + x11vnc 5905 + websockify 6085 (idempotente)
if ! pgrep -f "Xvfb :94" >/dev/null 2>&1; then
    rm -f /tmp/.X94-lock /tmp/.X11-unix/X94 2>/dev/null || true
    Xvfb :94 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb94.log" 2>&1 &
    sleep 3
fi
pgrep -f "fluxbox.*:94" >/dev/null 2>&1 || (DISPLAY=:94 fluxbox > "$LOG/fluxbox94.log" 2>&1 &)

# 7) ambiente
export DISPLAY=:94
export PYTHONPATH=/app          # resolve `src.processors.web.boletos...`
export PYTHONUNBUFFERED=1

# 8) roda e PROPAGA O EXIT CODE do python (não o do tee)
LOGROBO="/app/logs/<job>_$(date +%Y-%m-%d).log"
RC="/tmp/<job>_rc.$$"
{ python /app/src/processors/web/<job>/<job>.py "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1); rm -f "$RC"
exit "$CODIGO"
```

O truque do `$RC` existe porque **o hub chama o wrapper com `sh`, que aqui é
`dash`** — o shebang não vale nessa invocação e `${PIPESTATUS[0]}` é bashism.
Sem isso o hub vê o exit code do `tee`, que é **sempre 0**: o robô falha e a task
fica verde.

### Exit codes

Defina-os e documente-os. O que importa é ter um código para *"fez algo pela
metade e precisa de gente"*, distinto de *"não tinha nada a fazer"*.

---

## 7. Registrar no hub

```bash
docker exec hub-orchestration python run.py tasks upsert-docker <nome_task> \
  --container erp-automation \
  --command "sh /app/src/processors/web/<job>/run_agendado.sh" \
  --cron "0 18 * * 1-5" \
  --timeout-seconds 2700 \
  --max-retries 1 \
  --group operacional \
  --disabled --disabled-reason "aguarda run supervisionado" \
  --description "..."
```

- **`--timeout-seconds` sempre explícito.** O default é **600s**, curto para
  qualquer robô de navegador — o de remessa leva ~20 min e o doc2you 15-28 min.
- **Comece `--disabled`.** Habilitar é uma linha; desfazer uma rodada que escreveu
  no ERP não é.
- **Não existe `tasks enable`.** Para habilitar, refaça o `upsert-docker` **sem**
  `--disabled`.
- Aposentar é `--disabled --lifecycle-state paused --replacement-task <outra>`.
  **Nunca `DELETE`.**

---

## 8. Teste supervisionado, depois habilite

```bash
# 1) escopo mínimo, à mão, olhando
docker exec erp-automation sh /app/src/processors/web/<job>/run_agendado.sh --so-um-caso

# 2) o log tem de provar que FEZ, não só que rodou
docker exec erp-automation tail -40 /app/logs/<job>_$(date +%F).log
```

Só então habilite. E **na primeira execução agendada, leia o log** — não confie no
exit code (ver armadilha 6).

---

## 9. Commit

Enumere os arquivos, um a um. Nunca `git add -A`: a árvore do `erp-automation`
carrega muita coisa não commitada de outras frentes.

```bash
git add src/processors/web/<job>/*.py src/processors/web/<job>/run_agendado.sh \
        src/processors/web/<job>/docs/README.md config/<job>.example.env
git diff --cached --name-only     # confira ANTES de commitar
git commit -m "feat(<job>): ..." ; echo "exit=$?"
```

---

## Armadilhas medidas — as três primeiras produzem sucesso falso

**1. Sessão morta responde HTTP 200.** Quando a sessão do Smart expira, ele
devolve 93 bytes:

```html
<script>top.location.href='.../smart/php/expira.php';</script>
```

Sem `recaptcha`, sem status de erro, e sem a palavra `expirou` — é *"expira"*, sem
o U. Quem não checa isso lê toda tela como vazia e conclui *"não há nada a
fazer"*: a rodada termina com cara de sucesso **sem ter olhado nada**. Use
`remessa_cobranca/login.py::parece_deslogado` como referência, e chame-a em **todo**
ponto que lê resposta do Smart.

**2. `DRY_RUN` no `.env` + comando agendado sem a flag.** O robô de remessa ficou
com `DRY_RUN_REM=True` no `.env` e a task chamava `sh run_agendado.sh` sem
`--pra-valer`. A execução sairia com `exit=0` e um resumo bonito — **sem gerar
nada**. Depois de habilitar, confira o valor efetivo:

```bash
docker exec -e PYTHONPATH=/app erp-automation python -c \
 "import sys; sys.path.insert(0,'/app/src/processors/web/<job>'); import <job>_config as c; print(c.DRY_RUN)"
```

**3. `tee` engole o exit code.** Ver §6. O hub marca `success` num robô que
morreu.

**4. O Chrome sobe mesmo sem Xvfb.** Sem o display no ar, o `launch_persistent_context`
**não falha** — devolve um contexto e o problema aparece torta depois. Quem sobe o
Xvfb é o wrapper; num teste manual avulso, ninguém sobe. Avise:

```python
if not cfg.HEADLESS and not os.path.exists(f"/tmp/.X11-unix/X{cfg.DISPLAY.lstrip(':')}"):
    log(f"AVISO: display {cfg.DISPLAY} não está no ar")
```

**5. `pgrep -f <script>.py` casa consigo mesmo.** Um `docker exec sh -c 'pgrep -f
robo.py'` encontra o próprio `sh -c`, porque a string está na linha de comando
dele. Loops de "espere o processo sumir" nunca terminam. Case por algo específico
(`user-data-dir=<perfil>`) ou use um marcador no log.

**6. Janela de horário do usuário no Smart.** O Smart só aceita login dentro do
horário cadastrado **no usuário**. Fora dela o `dologin.php` responde
`2|Usuário com acesso restrito.` e o login falha — **não é o CapSolver**. Ao
escolher o cron, confirme que o horário cabe na janela do usuário.

**7. O healthcheck dos boletos só re-loga entre 7h e 18h** (`AUTO_RELOGIN_HORA_INICIO`
/ `_FIM`). Fora dessa faixa ele não gasta CapSolver — apenas reporta
`needs_login_fora_janela`. Se o seu robô roda fora dela, ele **precisa** saber
re-logar sozinho.

**8. `docker compose up -d` mata tudo dentro do container.** Adicionar um volume
exige recriar, e o Docker não sabe fazer isso com o container no ar. Ao recriar:
`manter_sessao` e os displays voltam sozinhos (`boot_vnc.sh`), **o robô de crédito
não** — a task dele dispara 07:45 e ele fica fora o resto do dia. Janela barata:
depois das 19:30 ou antes das 07:30.

**9. Volume declarado e não aplicado muda o destino no futuro.** Se você deixar um
bind-mount no compose sem recriar, ele entra em vigor na próxima recriação — e o
robô passa a gravar em outro lugar, **sem mudança de código e sem aviso**. Ou
recria na hora, ou não declara.

---

## Checklist

- [ ] Slot reservado (display, VNC, noVNC, CDP, perfil) e conferido no container
- [ ] Config 100% por env, com **sufixo próprio** — nada de `DISPLAY` puro
- [ ] `config/<job>.env` (600, gitignored) + `.example.env` versionado
- [ ] Login **delegado**, com `URL_SESSAO` apontando para a tela do robô
- [ ] `--no-sandbox --disable-dev-shm-usage` no Chrome
- [ ] `parece_deslogado()` em todo ponto que lê resposta do Smart
- [ ] `run_agendado.sh` propagando o exit code do Python (`$RC`, não `PIPESTATUS`)
- [ ] Task no hub com `--timeout-seconds` explícito e **começando desabilitada**
- [ ] `DRY_RUN` efetivo conferido **depois** de escrever o `.env`
- [ ] Run supervisionado, com o **log** provando que fez — não só o exit code
- [ ] `docs/README.md` com o que foi validado **e o que não foi**
- [ ] Commit com os arquivos enumerados, `git diff --cached --name-only` antes


---

## 10. Registre a execução no banco (desde 21/09/2026)

Todo job abre uma `job_execucao` ao começar e a fecha ao sair, e grava como evento cada
fato de negócio (operação avaliada, clique, finalização, arquivo gerado/enviado/recebido).
É `src/common/clients/execucao_job.py`, sobre as tabelas da `database/erp_004`. O
finalizador é o primeiro; os outros migram do CSV um a um (pagamento primeiro).

```python
from src.common.clients import execucao_job
ex = execucao_job.abrir_execucao("remessa_pagamento", "gerar_remessa_pagamento_cnab_240",
                                 flag_ensaio=cfg.DRY_RUN, obrigatoria=not cfg.DRY_RUN,
                                 apelido_credencial=os.environ.get("PAGAMENTO_SENHA"))
aid = execucao_job.registrar_arquivo(ex, "remessa_pagamento_cnab_240", "gerado",
                                     nome_arquivo=nome, conteudo=dados, titulos=[...])
execucao_job.registrar_evento_arquivo(ex, aid, "enviado")
execucao_job.fechar_execucao(ex, "sucesso", codigo_saida=0, qtd_itens=1)
```

Regras: em DRY o banco pode faltar (a execução degrada e avisa uma vez); em modo real é
obrigatório — `obrigatoria=True` faz `abrir` levantar e `registrar` recusar antes da ação.
Evento nunca muda: corrigir é gravar outro. O apelido da credencial se registra; a senha,
nunca (`apelido_seguro` recusa o que não tiver forma de apelido).

Desde a `erp_005` (22/09/2026): `execucao_job.atual()` devolve a execução aberta neste
processo — módulos fundos (o `banco.py` do crédito, o `bb_entrega.py`) registram sem
receber `execucao` por quatro assinaturas; `anotar(ex, chave, valor)` guarda o que não
tem tabela própria e vai para `detalhe_json` no fechamento; `buscar_arquivo(ex, tipo,
sha256=|md5=|id_no_smart=)` acha um arquivo já registrado; `registrar_evento_arquivo(...,
estrito=True)` é intenção (levanta em modo real); `registrar_evento_operacao(..., fato=True)`
é o que já aconteceu (avisa, nunca derruba). Execução manual real: `ERP_OPERADOR` e
`ERP_MOTIVO` no ambiente. Job sem navegador (conferência) mora em `src/processors/db/<job>/`
e usa a automação `controle` — modelo: `src/processors/db/controle/`.
