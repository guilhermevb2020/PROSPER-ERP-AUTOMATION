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

Credenciais core pertencem à fonte cifrada do Access Guardian. O ERP consome apelidos,
identidade efêmera do banco e relay SMTP; não cadastrar senha real em configuração, código,
documentação ou backup local. Material de sessão e VNC entregue para execução não constitui
uma segunda fonte de administração. Identidades do Smart: principal `GSMARTPWD1` (`prosperito`:
boletos, cobrança, crédito), financeira `PAGAMENTO_SENHA=GSMARTPWD2` (não restaurar a senha real em `config/remessa_pagamento.env`),
sandbox e finalizador `GSMARTPWD3`. Nunca misturar identidades. Login do banco: 1h/graça 10min;
capability: 4h/graça 5min. Apelido não significa que a senha do fornecedor seja rotativa.
Credenciais nunca devem ser exibidas. Limpeza de 07/09/2026:
[`docs/AUDITORIA_CREDENCIAIS_2026-09-07.md`](docs/AUDITORIA_CREDENCIAIS_2026-09-07.md).

Precisa de DDL no banco (migration nova)? Não há credencial no servidor: peça à Gerência
`bin/guardian conceder-banco erpddl --modelo erp-automation-ddl --horas 2 --para
/home/prospere/.erpddl.pgpass` (no `access-guardian`), aplique com `database/aplicar.sh` e, ao
terminar, `bin/guardian revogar-banco erpddl` e `shred -u` no arquivo.

## Como o projeto funciona hoje (22/09/2026)

Jobs Playwright/Chrome que operam o Smart (ERP) e o doc2you. Cada um mora em
`src/processors/web/<job>/` e é disparado pelo `hub-orchestration` por
`docker exec` no container `erp-automation`. O código de 2025 foi **removido em 21/09/2026**
(histórico no git e em `backups/organizacao-20260921/legado-2025.tar.gz`; docs daquela era em
`docs/deprecated/`).

| job | pasta | como o hub chama | display / noVNC |
|---|---|---|---|
| boletos: emissão, envio, healthcheck, mantenedor de sessão | `boletos/` | `python -m src.processors.web.boletos.{emitir_lote,enviar_lote,healthcheck}`; o `manter_sessao` sobe no `scripts/boot_vnc.sh` | `:99` / 6080 |
| doc2you (download diário de documentos) | `doc2you/` | `sh .../doc2you/run_agendado.sh [--antecipado]` | `:98` / 6081 |
| análise de crédito | `credito/` | `sh .../credito/run_agendado.sh` (roda `analisar_credito.py`) | `:96` / 6082 |
| remessa de cobrança CNAB-400, BB e cancelamento | `remessa_cobranca/` | `run_agendado.sh`, `run_bb.sh`, `run_cancelamento.sh` | `:97` / 6083 |
| retorno de cobrança CNAB-400, BB e depósito | `retorno_cobranca/` | `run_agendado.sh --pular-processados`, `run_bb.sh`, `run_deposito.sh` | `:95` / 6084 |
| remessa de pagamento CNAB-240 (BMP) | `remessa_pagamento/` | `run_agendado.sh` — a cada 5 min, 8h–18h55 | `:94` / 6085 |
| retorno de pagamento CNAB-240 | `retorno_pagamento/` | `run_agendado.sh` | `:93` / 6086 |
| finalizar operação | `finalizar_operacao/` | `run_agendado.sh --executar` — **em produção desde 22/09/2026** (clica até 18:30, só se a etapa lida no Smart for "Aguardando Ass.") | `:92` / 6087 |
| controle (sem navegador) | `src/processors/db/controle/` | `run_agendado.sh` — auditoria diária 19:35; também `encerrar_abandonada.py`, `carregar_historico_csv.py`, `listar_md5.py` | — |

Os jobs foram renomeados em 21/09/2026: a pasta leva o nome da automação e a entrada é
verbo + objeto (`retorno_cobranca/processar_retorno_cobranca.py`). De-para e armadilhas do hub:
`docs/RENOMEACAO_JOBS_2026-09-21.md`. A task de crédito no hub chama-se
`analisar_credito_operacao`. Só a porta 6080 é publicada pelo container; os outros noVNC se
alcançam por túnel ssh ao IP do container (ver `docs/COMO_SUBIR_UM_JOB.md`).

### Regras que valem para código novo

- **Vocabulário: "job", nunca "robô".** No código, comentário, log e nome de arquivo novo é
  "job"; para pessoas, "automação <nome>". Logs: `logs/<job>_<data>.log` (desde 22/09/2026).
  Só as pastas `data/robo_*` ainda levam o nome antigo, por serem armazenamento (perfis de
  Chrome logados) a mover numa janela própria.
- **Módulo comum vai em `src/common/clients/`** (`smart_sessao`, `nextcloud_webdav`,
  `whatsapp_evolution`, `execucao_job`). `src/common/core/config_loader.py` existe só porque o
  doc2you resolve credencial por ele; não é base para job novo.
- **Cada job tem** `run_agendado.sh` (wrapper do hub: display, env, exit code
  propagado com o truque do `$RC`), `<job>_config.py` (tudo por env), módulo
  puro testável sem navegador, e `docs/README.md`. Receita completa e armadilhas
  medidas: `docs/COMO_SUBIR_UM_JOB.md`.
- **Nunca dois Chromes no mesmo display ou perfil.** Slots na tabela acima e no
  guia; quem toma um slot atualiza o guia no mesmo commit.
- **Sessão do Smart é uma por identidade**: um login novo derruba o outro job da mesma conta.
  Sandbox e finalizador compartilham `GSMARTPWD3`: nunca rodar os dois ao mesmo tempo. Estudo
  das sessões entre rodadas: `docs/ESTUDO_SESSOES_SMART_2026-09-22.md`.
- **Trava por CONTA do Smart antes do Chrome** (`src/common/smart_financeiro_lock.sh`, desde
  22/09/2026): pagamento (`prosperito_financeiro`) em `/tmp/smart_financeiro.lock`; cobrança
  (remessa, retorno, BB, depósito, cancelamento — conta `prosperito`) em
  `/tmp/smart_cobranca.lock`, definida em cada wrapper. Não remover a trava nem apagar o
  arquivo em uso. Gate: `tests/unit/test_trava_por_conta.py`. O hub ainda segura a família de
  pagamento enquanto a remessa de cobrança roda (`pre_condition_sql`, desde 17/09).
- **Dry-run é do ambiente, no ponto da ação.** `DRY_RUN_*` no `config/<job>.env`
  barra a ação irreversível dentro da função que a executa, não só no `main()`.
- **Toda execução de job se registra no banco** por `src/common/clients/execucao_job.py`
  (`database/erp_004` a `erp_008`): abre `job_execucao`, grava `operacao_evento`/`arquivo*`,
  fecha uma vez. Em DRY o banco pode faltar (degrada e avisa); em modo real é **obrigatório** —
  sem registro o job recusa antes de abrir o navegador. Execução que ficou `ativa` (processo
  morto, fechamento perdido) só se encerra por `src/processors/db/controle/encerrar_abandonada.py
  <id> --pra-valer` com `ERP_OPERADOR`/`ERP_MOTIVO` — grava `abandonada`, nunca `sucesso`; sem
  isso a auditoria das 19:35 sai com exit 3 todo dia. Nunca `UPDATE` à mão em `job_execucao`.
  Evento nunca muda: corrigir é gravar outro.
- **Controle só no banco, desde 22/09/2026: nenhum job lê nem grava CSV de controle.** A
  memória "já fiz?" é o banco: `listar_md5` (une `arquivo` e `arquivo_historico`, onde está o
  que as planilhas sabiam de antes de 21/09), `listar_controle` (views `vw_controle_*`, com as
  colunas das antigas planilhas), `listar_eventos_operacao` (crédito e avisos do finalizador).
  O `arquivo` é identificado pelo **conteúdo** (sha256). As listas de exclusão e cancelamento
  do process-automation vêm de `financeiro.remessa_*_apontad*`. Chaves no `config/<job>.env`
  (`CONTROLE_FONTE_*=banco`, `CONTRATO_FONTE_REM=banco`, `ESCREVER_CSV_*=False`); voltar é
  apagar a linha. As planilhas antigas ficaram congeladas em `data/` só como histórico. Ainda
  gravam JSON ao lado dos eventos: `remessas_geradas.json`, `cancelamentos_feitos.json`,
  `falhas/<id>.json` (lido pelo process-automation), recibos do BB e a rotina de avisos do
  finalizador. Plano, fases e provas: `docs/PLANO_CONTROLE_NO_BANCO.md`.
- **Execução manual em modo real diz quem e por quê:** `docker exec -e ERP_OPERADOR=nome
  -e ERP_MOTIVO="..." erp-automation sh .../run_agendado.sh`. O hub passa `HUB_RUN_ID` e
  `HUB_TASK_NOME` no exec: execução dele entra como `gatilho cron`; `manual` é só quem rodou
  `docker exec` à mão. O retorno BB registra a intenção no banco **antes** do recibo e do POST:
  sem registro, sem POST (arquivo fica pendente).
- **O nome do job na execução tem de casar com a task do hub.** `run_bb.sh` é
  `gerar_remessa_bb`/`processar_retorno_bb`, `run_deposito.sh` é `baixar_deposito_no_erp`.
  Errar isso faz a execução apontar para o job errado, e ninguém percebe até procurar.
- **`config/*.env` são carregados com `sh`**: valor com espaço exige aspas, senão
  a variável fica vazia sem erro.
- **Testes:** `pytest` coleta só a suíte de `pytest.ini`; scripts manuais de e-mail e browser
  em `tests/` têm efeitos externos ao importar. Dependências: `requirements-test.txt`. Nenhum
  teste fala com o Smart; os de integração usam a bancada (Postgres descartável).

### Comandos

```bash
# rodar um job à mão, como o hub faz
docker exec erp-automation sh /app/src/processors/web/<job>/run_agendado.sh

# ver / registrar task no hub (sempre --timeout-seconds explícito; começar --disabled)
docker exec hub-orchestration python run.py tasks show <task>
docker exec hub-orchestration python run.py tasks upsert-docker <task> --container erp-automation --command "sh /app/src/processors/web/<job>/run_agendado.sh" --cron "..." --timeout-seconds N --disabled --disabled-reason "..."

# auditoria do controle (o que a task das 19:35 roda)
docker exec erp-automation sh /app/src/processors/db/controle/run_agendado.sh --dia AAAA-MM-DD

# testes (no host, sem container; nenhum teste fala com o Smart)
PYTHONPATH=$PWD .venv-sandbox/bin/pytest

# provar migration e integracao num Postgres descartavel (mesma imagem de producao)
scripts/bancada_pg.sh subir && eval "$(scripts/bancada_pg.sh env)" && PYTHONPATH=$PWD .venv-sandbox/bin/pytest tests/integration && scripts/bancada_pg.sh derrubar

# sandbox contra o Smart real (identidade própria; ver scripts/sandbox/README.md)
PYTHONPATH=$PWD .venv-sandbox/bin/python scripts/sandbox/<script>.py
```

### Container

Bind de `/app/src`, `/app/config`, `/app/data`, `/app/logs`: código salvo vale
na próxima execução, sem rebuild — publique por cópia atômica (temporário + `mv`). Recriar
(`docker compose up -d`) só na janela 19:05–07:30, porque mata o mantenedor de sessão e os
displays (o `boot_vnc.sh` os devolve; o job de crédito não volta até a task das 07:45).
`TZ=America/Sao_Paulo` vale desde a recriação de 21/09/2026 às 21:41; antes disso o container
rodava em UTC e todo texto de data que ele gravou antes de 22/09 está em UTC.

`data/` e `logs/` são ignorados pelo git inteiros (perfis de Chrome, boletos,
prints, planilhas congeladas). `config/*.env` idem. Um `git add -A` não leva
credencial — mas confira o `git status` antes de commitar.

### Documentação que vale

`docs/README.md` é o índice. Os principais: `docs/COMO_SUBIR_UM_JOB.md` (receita e
armadilhas) · `docs/PLANO_CONTROLE_NO_BANCO.md` (controle no banco) ·
`docs/CREDENCIAIS_GUARDIAN.md` · `docs/CONVENCOES_PORTAS.md` · `docs/BOLETOS_LOTE.md` ·
`docs/hub_orchestration_API.md` · `database/README.md` (migrations). Cada job tem o seu
`docs/README.md`. `docs/deprecated/` e os `docs/VALIDACAO_*_2026-09-07.md` são história.

## Banco — estado atual

O ERP conecta pelo proxy do access-guardian. A identidade efetiva verificada é
`app_erp_automation`, com `session_user` efêmero `gdh_erp_automation_...`.
As variáveis de senha de banco do container ficam vazias; o proxy usa a
capability/passfile. Schema próprio `erp_automation` (migrations em `database/`, uma vez cada,
pelo `database/aplicar.sh`).

Emissão/envio de boletos escrevem em `erp_automation.boleto_emissao_log` e
`erp_automation.boleto_envio_log`. A leitura legada de
`operacional.boleto_envio_log` usa view de compatibilidade. Não alterar schemas
ou permissões baseado apenas em nomes antigos. Quem escreve o quê no banco: registro
`2026-08-03-quem-escreve-no-banco-o-mapa-que-nunca-existiu` no Learn
(`learn contexto "quem escreve no banco"`).

## Hub orchestration

A API do hub está em `docs/hub_orchestration_API.md`; a chave de acesso fica no `.env` do
projeto. ⛔ **Credencial nunca em arquivo versionado.** Pela CLI:
`docker exec hub-orchestration python run.py history|status|tasks show <task>`.

## Histórico

O estado verificado em 07/09/2026 (rodadas de validação depois do Guardian) e o registro de
03/08 sobre as tabelas de log, que ficavam aqui, estão no anexo de
`docs/VALIDACAO_ERP_2026-09-07.md`.
