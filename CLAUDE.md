# PROSPER-ERP-AUTOMATION - Diretrizes para Claude Code

## Em um minuto: as credenciais deste projeto (07/09/2026)

Este container **não carrega o `shared.env` e não tem senha de banco**. Tudo vem do
`access-guardian`: o `.env.guardian` é gerado, nunca editado à mão; o banco
é `DB_HOST=guardian` com senha vazia e login efêmero pelo worker; as integrações são
**apelidos** que o proxy troca na saída (`GSMARTPWD1`/`GSMARTPWD2`/`GSMARTPWD3` para o Smart,
`__GUARDIAN_…__` para CapSolver, Evolution e Nextcloud; SMTP pelo broker, senha vazia).
Só VNC tem entrega de senha real para execução. A página inteira, com os comandos de operar e o molde para
migrar os outros projetos: [`docs/CREDENCIAIS_GUARDIAN.md`](docs/CREDENCIAIS_GUARDIAN.md).

Cinco regras que valem sempre: conferir o ambiente efetivo por nomes e classificação,
sem exibir valores; chave nova entra na fonte e no `gerar:` da política, depois `guardian gerar
erp-automation`; recriar só na janela 19:05–07:30; nada de senha real em `config/*.env`,
código, log ou commit; nunca `dev_user` nem `POSTGRES_PASSWORD` do `shared.env`.

## Credenciais: fonte única no Access Guardian

Credenciais core pertencem à fonte cifrada do Access Guardian. O ERP consome
apelidos, identidade efêmera do banco e relay SMTP; não cadastrar senha real
em configuração, código, documentação ou backup local. Material de sessão e
VNC entregue para execução não constitui uma segunda fonte de administração.

A [auditoria de credenciais](docs/AUDITORIA_CREDENCIAIS_2026-09-07.md) registra
limpeza de configuracoes, logs, traces e historico Git local/GitHub. Sandbox e
finalizador usam a identidade propria GSMARTPWD3; CapSolver proprio por apelido.
A imagem guardian-clean-20260907-v2 esta implantada, a imagem antiga foi removida.
VNC continua entregue pelo Guardian como material de execucao. Nunca misturar
identidades nem reintroduzir senhas reais nos arquivos dos robos.
Reconferência de 16:32:55: 3.735 arquivos; só VNC esperado, sem erros de leitura.
Login do banco: 1h/graca 10min; capability: 4h/graca 5min. Apelido não significa
que a senha do fornecedor seja rotativa; a fonte administrativa fica no Guardian.

## Estado verificado em 07/09/2026

Nova rodada manual autorizada em andamento desde 17:03, dentro da validação de
16:34:17 até 08/09 00:34:17. Abrange as 11 tarefas finitas habilitadas; crédito
foi acompanhado na execução 2665935, sem duplicação, até a saída normal às
18:50:28: success/exit 0, ciclo 306, fim do expediente configurado. Não reiniciar
o robô fora dessa janela para continuar a observação. O histórico abaixo registra
a rodada anterior e não encerra o acompanhamento atual. Resultados e limites:
`docs/VALIDACAO_OITO_HORAS_2026-09-07.md`.

Rodada manual: 11 tarefas finitas conferidas. Emissão adicional 2670656
recuperou sessão expirada via CapSolver e concluiu às 19:21:39, 55 contas vazias.
O healthcheck efetivo usa 7h–18h (padrões do módulo são sobrescritos pelo Hub);
`needs_login_fora_janela` com exit 0 não significa sessão saudável. O mantenedor
loga ao iniciar; emissão e healthcheck fazem a recuperação posterior.

Às 18:13, retorno de pagamento 2669741 falhou por
`ERROR_CAPTCHA_SOLVE_FAILED`; retentativa 2669760 recuperou às 18:15:45.
O solver compartilhado ganhou uma segunda tentativa de desafio, limitada ao
mesmo prazo total, sem repetir erros de chave/saldo. 36 testes isolados sem
rede aprovados; publicação alcança novos processos pelo bind de `/app/src`,
sem reiniciar ERP/crédito. Commit `d244857` aplicado às 18:18:37; retorno
2669905 usou o solver novo, confirmou login e concluiu às 18:24:25, sem arquivo
de entrada. Não precisou da segunda resolução; esse ramo tem prova automatizada.
Não confundir os 11 sucessos manuais com ausência
de falhas posteriores; acompanhar cada tentativa até 00:34:17.

Consulte [a matriz de validação](docs/VALIDACAO_ERP_2026-09-07.md) antes de
repetir testes operacionais: 382 testes no host; 20 tarefas inventariadas, das
quais 12 habilitadas foram alcançadas na rodada real de feriado (11 concluídas
e crédito em execução). Sessão principal saudável às 15:30, após recuperação
automática e emissão da tarde. Veja `docs/VALIDACAO_FERIADO_2026-09-07.md`.
O Smart tem sessão única por identidade; novos logins podem
interromper outro robô. Testes de regressão usam serviços simulados.
Geração e retorno de pagamento usam uma trava financeira comum antes do Chrome
(`src/common/smart_financeiro_lock.sh`). Não remover a trava nem apagar seu
arquivo enquanto houver uso. **Desde 22/09/2026 a trava é por CONTA do Smart:** a
família de pagamento (`prosperito_financeiro`) fica em `/tmp/smart_financeiro.lock`, a
original; a família de cobrança (remessa, retorno, BB, depósito, cancelamento, conta
`prosperito`) usa `/tmp/smart_cobranca.lock`, definida em cada wrapper antes de carregar
a trava. Uma trava só para as duas fazia a remessa de cobrança das 18h derrubar o
pagamento das 18h00–18h20 todo dia útil (exit 6), sem ganho: contas diferentes não
disputam sessão. Gate: `tests/unit/test_trava_por_conta.py`. A falha do aviso de segurança às 16:03 recuperou
na retentativa; retorno e geração concluíram novamente às 16:14 e 16:16.

A rodada real das 12:25–13:15 confirmou 683 documentos enviados,
registro no banco e remessa CNAB400 de 14 títulos entregue ao Nextcloud.
Emissão/envio executaram em modo real sem novos títulos; pagamentos logaram
sem entrada pendente. Retorno e depósito também executaram, sem arquivos novos.
Consulte a matriz para os IDs e limites: isso não comprova baixas sem entrada.
A manutenção manual do Hub pausou o despacho e foi liberada externamente;
a sequência terminou após a retomada. O mantenedor normal do Chrome foi
restaurado com login automático e keepalive válido. Crédito segue o ciclo diário.

O ERP usa o Guardian para banco e integrações. A conta financeira usa
`PAGAMENTO_SENHA=GSMARTPWD2` no ambiente; não restaurar a senha real em
`config/remessa_pagamento.env`. O valor da fonte foi corrigido para respeitar os
11 caracteres efetivamente enviados pelo campo antes da migração. Logins de
pagamento confirmados após a correção. Credenciais nunca devem ser exibidas.

`pytest` coleta somente a suíte automatizada definida em `pytest.ini`.
Scripts manuais de email e browser em `tests/` têm efeitos externos ao importar.
Dependências de teste: `requirements-test.txt`. PDFs de emissão são guardados
em `/app/data/boletos/emitidos`, com manifesto; não versionar esses documentos.


## Como o projeto funciona hoje (21/09/2026)

Jobs Playwright/Chrome que operam o Smart (ERP) e o doc2you. Cada um mora em
`src/processors/web/<job>/` e é disparado pelo `hub-orchestration` por
`docker exec` no container `erp-automation`. O código de 2025 (processadores
`emissao_boleto_*`, `relatorio_*`, `envio_*`, stack antibot em `src/common/*`,
API de controle em `src/api`) foi **removido em 21/09/2026**: nenhuma das 12
entradas que o hub executa importava nada daquilo. Histórico no git (commit da
remoção) e em `backups/organizacao-20260921/legado-2025.tar.gz`. Os docs
daquela era estão em `docs/deprecated/`.

| job | pasta | como o hub chama | display / noVNC |
|---|---|---|---|
| boletos: emissão, envio, healthcheck, mantenedor de sessão | `boletos/` | `python -m src.processors.web.boletos.{emitir_lote,enviar_lote,healthcheck}`; o `manter_sessao` sobe no `scripts/boot_vnc.sh` | `:99` / 6080 |
| doc2you (download diário de documentos) | `doc2you/` | `sh .../doc2you/run_agendado.sh [--antecipado]` | `:98` / 6081 |
| análise de crédito | `credito/` | `sh .../credito/run_agendado.sh` (roda `analisar_credito.py`) | `:96` / 6082 |
| remessa de cobrança CNAB-400, BB e cancelamento | `remessa_cobranca/` | `run_agendado.sh`, `run_bb.sh`, `run_cancelamento.sh` | `:97` / 6083 |
| retorno de cobrança CNAB-400, BB e depósito | `retorno_cobranca/` | `run_agendado.sh --pular-processados`, `run_bb.sh`, `run_deposito.sh` | `:95` / 6084 |
| remessa de pagamento CNAB-240 (BMP) | `remessa_pagamento/` | `run_agendado.sh` — a cada 5 min, 8h–18h55 | `:94` / 6085 |
| retorno de pagamento CNAB-240 | `retorno_pagamento/` | `run_agendado.sh` | `:93` / 6086 |
| finalizar operação (Robô 7) | `finalizar_operacao/` | `run_agendado.sh --executar` — **em produção desde 22/09/2026** (clica até 18:30, só se a etapa lida no Smart for "Aguardando Ass.") | `:92` / 6087 |

Os jobs foram renomeados em 21/09/2026: a pasta leva o nome da automação e a entrada é
verbo + objeto (`robo_retorno/robo_retorno.py` → `retorno_cobranca/processar_retorno_cobranca.py`).
De-para completo, o que não mudou de propósito e as armadilhas do hub:
`docs/RENOMEACAO_JOBS_2026-09-21.md`. A task de crédito no hub chama-se
`analisar_credito_operacao`; `robo_analise_credito` está aposentada.

Só a porta 6080 é publicada pelo container; os outros noVNC se alcançam por
túnel ssh ao IP do container (ver `docs/COMO_SUBIR_UM_JOB.md`).

### Regras que valem para código novo

- **Módulo comum vai em `src/common/clients/`** (`smart_sessao`, `nextcloud_webdav`,
  `whatsapp_evolution`). `src/common/core/config_loader.py` existe só porque o
  doc2you resolve credencial por ele; não é base para job novo.
- **Cada job tem** `run_agendado.sh` (wrapper do hub: display, env, exit code
  propagado com o truque do `$RC`), `<job>_config.py` (tudo por env), módulo
  puro testável sem navegador, e `docs/README.md`. Receita completa e armadilhas
  medidas: `docs/COMO_SUBIR_UM_JOB.md`.
- **Nunca dois Chromes no mesmo display ou perfil.** Slots na tabela acima e no
  guia; quem toma um slot atualiza o guia no mesmo commit.
- **Sessão do Smart é uma por identidade.** Sandbox e finalizador compartilham
  `GSMARTPWD3`: nunca rodar os dois ao mesmo tempo.
- **Dry-run é do ambiente, no ponto da ação.** `DRY_RUN_*` no `config/robo_*.env`
  barra a ação irreversível dentro da função que a executa, não só no `main()`.
- **Toda execução de job se registra no banco** por `src/common/clients/execucao_job.py`
  (`database/erp_004`, **aplicada em produção em 21/09/2026**): abre `job_execucao`, grava
  `operacao_evento`/`arquivo*`, fecha uma vez. Em DRY o banco pode faltar (degrada e avisa);
  em modo real é **obrigatório** — sem registro o job recusa antes de abrir o navegador,
  porque ação irreversível sem rastro é pior do que ação nenhuma. Execução que ficou `ativa`
  (processo morto, fechamento perdido) só se encerra por
  `src/processors/db/controle/encerrar_abandonada.py <id> --pra-valer` com `ERP_OPERADOR`/
  `ERP_MOTIVO` — grava `abandonada`, nunca `sucesso`; sem isso a paridade das 19:35 sai com
  exit 3 todo dia. Nunca `UPDATE` à mão em `job_execucao`.
- **Dupla escrita, desde 22/09/2026.** Os quatro jobs de arquivo (retorno e remessa, de
  cobrança e de pagamento) gravam o CSV de controle **e** as tabelas, no mesmo ponto do
  código. Nada foi retirado do CSV: o corte vem depois de semanas comparando as duas
  fontes. Job novo já nasce registrando; quem mexer nesses quatro mantém os dois lados.
  O `arquivo` é identificado pelo **conteúdo** (sha256), então reprocessar o mesmo arquivo
  devolve a linha existente em vez de duplicar — a mesma regra do `hash` no CSV.
- **O banco é a fonte do controle, desde a `erp_005` (22/09/2026).** Plano e fases em
  `docs/PLANO_CONTROLE_NO_BANCO.md`. O que só existia em JSON no disco virou evento
  (`descartado`, `cancelado`, `intencao_envio` do BB; `documentos_baixados`/`etapa_movida`
  do crédito); o que não tem tabela vai por `execucao_job.anotar()` para o `detalhe_json`
  da execução. As views `vw_controle_*` têm as colunas dos CSVs; `vw_job_execucao_ultima`
  responde "rodou?". A paridade CSV × banco é medida todo dia útil pela task
  `comparar_controle_csv_banco` (19:35; exit 3 = divergência). As leituras de idempotência
  vêm do banco (Fase 2) nos quatro jobs de arquivo: `_RET`, `_RETPAG` e `_REM` desde 22/09/2026
  11h47, `_PAG` desde 17h41 — linha `CONTROLE_FONTE_*=banco` no `config/<job>.env`. Nos
  dois retornos, `banco` = banco ∪ histórico do CSV até a Fase 4 (a memória evita baixa em
  duplicidade); a carga histórica de 45 dias das remessas foi feita (execução #166). O CSV continua
  sendo escrito: quem mexer nos quatro jobs mantém os dois lados.
- **Execução manual em modo real diz quem e por quê:** `docker exec -e ERP_OPERADOR=nome
  -e ERP_MOTIVO="..." erp-automation sh .../run_agendado.sh`. Desde 22/09/2026 ~11h15 o hub
  passa `HUB_RUN_ID` (o id de lock do run, 32 hex) e `HUB_TASK_NOME` no exec: execução dele
  entra como `gatilho cron`, com `run_id` e `task_nome`; `manual` é só quem rodou `docker exec` à mão
  (e, em modo real sem `ERP_OPERADOR`/`ERP_MOTIVO`, o job avisa no log). O retorno BB registra a
  intenção no banco **antes** do recibo e do POST: sem registro, sem POST (arquivo fica pendente).
- **O nome do job na execução tem de casar com a task do hub.** `run_bb.sh` é
  `gerar_remessa_bb`/`processar_retorno_bb`, `run_deposito.sh` é `baixar_deposito_no_erp`.
  Errar isso faz a execução apontar para o job errado, e ninguém percebe até procurar. Tabela de evento nunca muda: corrigir é outro evento.
- **`config/*.env` são carregados com `sh`**: valor com espaço exige aspas, senão
  a variável fica vazia sem erro.

### Comandos

```bash
# rodar um job à mão, como o hub faz
docker exec erp-automation sh /app/src/processors/web/<job>/run_agendado.sh

# ver / registrar task no hub (sempre --timeout-seconds explícito; começar --disabled)
docker exec hub-orchestration python run.py tasks show <task>
docker exec hub-orchestration python run.py tasks upsert-docker <task> --container erp-automation --command "sh /app/src/processors/web/<job>/run_agendado.sh" --cron "..." --timeout-seconds N --disabled --disabled-reason "..."

# testes (no host, sem container; nenhum teste fala com o Smart)
PYTHONPATH=$PWD .venv-sandbox/bin/pytest

# provar migration e integracao num Postgres descartavel (mesma imagem de producao)
scripts/bancada_pg.sh subir && eval "$(scripts/bancada_pg.sh env)" && PYTHONPATH=$PWD .venv-sandbox/bin/pytest tests/integration && scripts/bancada_pg.sh derrubar

# sandbox contra o Smart real (identidade própria; ver scripts/sandbox/README.md)
PYTHONPATH=$PWD .venv-sandbox/bin/python scripts/sandbox/<script>.py
```

### Container

Bind de `/app/src`, `/app/config`, `/app/data`, `/app/logs`: código salvo vale
na próxima execução, sem rebuild. Recriar (`docker compose up -d`) só na janela
19:05–07:30, porque mata o mantenedor de sessão e os displays (o `boot_vnc.sh`
os devolve; o job de crédito não volta até a task das 07:45). `TZ=America/Sao_Paulo`
está no compose desde 21/09/2026 e vale a partir da recriação; antes disso o
container rodava em UTC e todo `datetime.now()` saía 3 h adiantado.

`data/` e `logs/` são ignorados pelo git inteiros (perfis de Chrome, boletos,
prints, CSVs de controle). `config/*.env` idem. Um `git add -A` não leva
credencial — mas confira o `git status` antes de commitar.

### Documentação que vale

`docs/COMO_SUBIR_UM_JOB.md` (receita e armadilhas) · `docs/CREDENCIAIS_GUARDIAN.md`
· `docs/CONVENCOES_PORTAS.md` · `docs/BOLETOS_LOTE.md` · `docs/hub_orchestration_API.md`
· `docs/VALIDACAO_*_2026-09-07.md` · `docs/README.md` (índice). Cada job tem o
seu `docs/README.md`. `docs/deprecated/` é só história.

## Banco — estado atual

O ERP conecta pelo proxy do access-guardian. A identidade efetiva verificada é
`app_erp_automation`, com `session_user` efêmero `gdh_erp_automation_...`.
As variáveis de senha de banco do container ficam vazias; o proxy usa a
capability/passfile. A descrição antiga de conexão como superusuário ficou
obsoleta após a migração.

Emissão/envio escrevem em `erp_automation.boleto_emissao_log` e
`erp_automation.boleto_envio_log`. A leitura legada de
`operacional.boleto_envio_log` usa view de compatibilidade. Não alterar schemas
ou permissões baseado apenas em nomes antigos deste documento.

# hub orchestration

leia a documantecacao da api do hub-orchestration   para acessar via api


voce tem os dados em .env

⛔ **Credencial nunca em arquivo versionado.**

**Registro histórico (03/08; não usar como estado atual):** `operacional.boleto_envio_log` /
`boleto_emissao_log` / `boleto_sessao_healthcheck`, e `stg.doc*` / `stg.robo_analise_*`.
⚠️ A tabela `operacional.boleto_envio_log` foi **criada pela migration 079 do
`process-automation`** e é escrita daqui — dependência cross-repo real, sem contrato de
schema versionado do lado de quem escreve.

Mapa completo: registro
`2026-08-03-quem-escreve-no-banco-o-mapa-que-nunca-existiu` no PostgreSQL do Learn
(`learn contexto "quem escreve no banco"`).
