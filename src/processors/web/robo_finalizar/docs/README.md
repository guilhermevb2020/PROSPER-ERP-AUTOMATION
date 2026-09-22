# Job de finalizar operação

Confere cada operação na etapa **"Aguardando Ass."** e, se passar em duas
verificações, finaliza no Smart. Se não passar, **não finaliza** e avisa.

> ⚠️ **Estado (21/09/2026): EM DRY, agendado.** Task
> `finalizar_operacao_aguardando_assinatura` habilitada no hub (`*/15 8-18 * * 1-5`),
> comando sem `--executar` e `R7_DRY_RUN=1` no `.env`: confere, registra e **não
> clica**. Primeira rodada em produção: 21/09 19:30 (login via CapSolver OK, fila
> vazia àquela hora). A finalização real continua com **zero execuções** neste
> servidor — ver "O que NÃO foi validado".

Origem: pacote trazido de uma máquina Windows em 01/09/2026, adaptado aqui.

---

## Slot

| DISPLAY | VNC | noVNC | CDP | perfil |
|---|---|---|---|---|
| `:92` | 5907 | 6087 | 9228 | `data/robo_finalizar/perfil_chrome` |

---

## As duas verificações

**1. Documentos assinados** (`checagem_docs.py`) — consulta o doc2you.

| documento | quando é exigido | critério |
|---|---|---|
| Aditivo (`Contrato`) | sempre | **exceção**: falta só a Prosper = OK |
| Nota promissória | sempre | status `Concluído` |
| Duplicata | se houver título `DUR`/`DSR`/`DMR` | status `Concluído` |
| Letra de câmbio | se houver `LCB` | status `Concluído` |

O Aditivo **nunca** fica `Concluído` — a Prosper assina depois. Por isso o
critério dele é **assinante a assinante**: se todos os que não são a Prosper já
assinaram, libera. A Prosper é identificada pelo **papel** (`Contratada`), não
pelo nome, e um assinante cujo nome bate com o cedente é sempre terceiro — sem
isso um cedente "PROSPERIDADE" seria confundido com a Prosper.

**2. Forma de pagamento** (`checagem_pagamento.py`) — a grade PIX.

Tipo `PIX`; Cta. origem `mp prospere`; destino/Bco/Ag/Tp.Conta/CC/Favorecido/
CPF-CNPJ preenchidos; Chave PIX preenchida; **Vencto = hoje**; **SP marcado**.
Vale para **todas as linhas** quando o pagamento é dividido.

A checagem 2 **só roda quando a 1 passa** (`R7_PAGAMENTO_SO_APOS_ASSINATURAS`).
Enquanto ninguém assinou o cadastro de pagamento ainda está sendo montado, e
cobrar dele nessa fase só gera ruído.

---

## O que fica registrado no banco (desde 21/09/2026)

Cada rodada abre uma `erp_automation.job_execucao` (automação `finalizar_operacao`) e a
fecha ao sair, com exit code e quantidade de operações. Por operação, um evento
`avaliada` com o veredito (`FINALIZARIA` / `BARRADA` / `ERRO`), as pendências e a foto da
grade de pagamento (`operacao_pagamento_linha`, leitura restrita); em modo real,
`finalizar_clicado` **antes** do clique e `finalizada` / `finalizacao_falhou` /
`finalizada_por_outro` depois; e `aviso_enviado` quando o WhatsApp sai. Evento nunca
muda. O placar (`vw_operacao_placar`) compara o veredito com o espelho do Smart.

Em DRY o banco pode faltar: a execução degrada, avisa uma vez e o ciclo segue. Em modo
real é obrigatório: sem registro não há clique. Módulo: `src/common/clients/execucao_job.py`;
migration: `database/erp_004_execucao_e_eventos.sql` — **ainda não aplicada em produção**
(exige o Guardian no modelo de administração; provada na bancada com 17 testes).

---

## Dependências — o que ele reusa

Não há cópia de módulo do `credito` aqui. O `r7_config.py` põe
`../credito` no `sys.path` e importa de lá `config`, `banco`, `subfluxos`,
`analisar_credito_operacao` e `smart_session`.

Conferido em 02/09/2026 antes de reusar: `smart_session.py` era **byte a byte
idêntico** ao do pacote de origem, e os símbolos consumidos de `config.py`
(`URL_LOGIN`, `URL_CONSULTA`, `URL_EDITAR`, `VALOR_ETAPA_AGUARDANDO_ASS`) têm
**valores iguais** nas duas versões.

`classe_risco_tool.py` e `verificar_docs.py` moram aqui porque não existiam no
repo — candidatos a `src/common/` quando um segundo job precisar deles.

---

## Rodar

```bash
# confere e avisa, NÃO finaliza (é o default)
sh /app/src/processors/web/robo_finalizar/run_agendado.sh

# finaliza de verdade — só depois de validado
sh /app/src/processors/web/robo_finalizar/run_agendado.sh --executar
```

`--executar` é **ignorado** se `R7_DRY_RUN=1` — e, desde 21/09/2026, a trava vale
**dentro de `finalizar_da_grade()`**: nenhum caminho clica com `R7_DRY_RUN=1`, nem o
`scripts/sandbox/finalizar_op_executar.py --confirmar` (teste `test_finalizar_trava_dry`).

Desde 21/09/2026 o job **sobe a própria sessão** do Smart pelo
`src/common/clients/smart_sessao` (o mesmo do `remessa_pagamento`): abre o Chrome no
display `:92`, loga via CapSolver com a credencial do finalizador e fecha ao terminar.
`--cdp` anexa num Chrome já aberto (desenvolvimento pelo VNC). Antes ele exigia um
Chrome pré-aberto na porta 9228 que, no container, ninguém subia — a primeira rodada
morreu em 4 s antes de logar.

---

## O que FOI validado (01–02/09/2026, sandbox no host)

Dois dias de ciclos contínuos contra o Smart e o doc2you **reais**:

- as duas checagens, em dezenas de operações
- a exceção do Aditivo (`só a Prosper pendente - liberado`), em vários casos
- **transição de estado**: operações barradas viraram aprovadas sozinhas quando
  as assinaturas chegaram, em 12–20 min
- leitura da grade em **4 bancos** (001, 341, 756, 033, 403) e favorecidos
  pessoa física e jurídica, de R$ 2 mil a R$ 795 mil
- login automático via CapSolver — **elimina o reCAPTCHA manual diário** que o
  pacote de origem listava como o bloqueio do 24/7
- sessão contínua: 11 ciclos com 1 login, sem degradação observada

## O que NÃO foi validado

- **A finalização.** O clique em Finalizar tem **zero execuções** neste
  servidor. Tudo foi DRY. O pacote de origem reporta 9 finalizações em
  01/09/2026 na máquina de origem — é o autor dizendo, não nós vendo.
- **O aviso por WhatsApp.** Nenhum envio saiu; falta a `EVOLUTION_API_KEY` no
  sandbox (no container ela vem do `env_file`). Testados só os caminhos de
  erro (401 sem chave / com chave inválida), que falham fechado.
- **Acurácia medida.** O `placar.py` nunca rodou. "A operação sumiu da fila
  depois que o job aprovou" **não é prova** — operações barradas também somem,
  e uma delas saiu e voltou assinada 12 min depois.
- **Volume alto.** As filas observadas tiveram no máximo 7 operações.

---

## Armadilhas medidas

**Operação aberta em outra sessão trava a checagem de pagamento.** O
`#btnPagamento` fica `disabled` — presente no DOM, visível, sem nada por cima —
e o clique morre por timeout de 15s. Produziu 2 `ERRO` numa op que minutos
depois passou sem problema. O job ainda reporta isso como
`Locator.click: Timeout`, mensagem que não diz nada: **o timeout está calibrado
para 15s numa tela que pode travar ~90s.** Corrigir isso é o próximo item.

**Sem banco, o `cedente` sai vazio.** `DB_HOST` vem do `.env` da raiz; no
sandbox não existe e o default (`192.168.50.5`) não responde. Não é defeito de
portabilidade — o `credito` tem o mesmo default. Quem identifica o
recebedor nesse caso é o `favorecido`, lido da grade.

**Screenshot de falha de login vai para `/app`** e falha fora do container.
Perde-se a evidência visual exatamente quando o login quebra.

---

## Pendências para produção

- [x] `config/robo_finalizar.env` (600) a partir do `.example.env` — 07/09/2026; em 21/09 ganhou aspas nos dois valores com espaço (o `sh` os deixava vazios)
- [x] Task no hub, `--timeout-seconds 1500`, começou `--disabled` em 21/09 09:21 e foi habilitada em DRY às 19:32
- [x] `R7_DRY_RUN` efetivo conferido pelo container em 21/09 — `1`
- [ ] `placar.py` por alguns dias úteis antes de sair do DRY (nunca rodou)
- [ ] Limite de hora para clicar (`R7_HORA_LIMITE_FINALIZAR=18:30`): a remessa de pagamento sai a cada 5 min até 18:55 e exige vencimento = hoje
- [ ] Primeira finalização **supervisionada**, uma operação de valor baixo, acompanhada até o retorno do banco
- [ ] Corrigir o timeout de 15s → espera compatível + diagnóstico "operação em uso"
- [ ] `notificar.py` ainda aponta para um `email_config.json` de Windows
- [ ] Renomear `r7_config.py` → `finalizar_config.py` (convenção do guia §2)
