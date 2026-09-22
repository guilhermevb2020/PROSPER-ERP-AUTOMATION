# Job de finalizar operação

Confere cada operação na etapa **"Aguardando Ass."** e, se passar em duas
verificações, finaliza no Smart. Se não passar, **não finaliza** e avisa.

> ⚠️ **Estado (22/09/2026): EM PRODUÇÃO, por decisão do usuário.** Desde 14:37 a task
> `finalizar_operacao_aguardando_assinatura` (`*/15 8-18 * * 1-5`) roda com `--executar`
> e o `.env` tem `R7_DRY_RUN=0`: as duas trancas estão abertas e o robô **clica** em
> Finalizar quando as checagens passam, a etapa lida no Smart é a de entrada e o
> relógio não passou de `R7_HORA_LIMITE_FINALIZAR` (18:30). Voltar ao DRY é fechar
> **uma** tranca: tirar `--executar` da task **ou** `R7_DRY_RUN=1`.
>
> **Primeiras finalizações reais, 22/09:** 65879 às 15:46 e 65876 às 15:47, as duas
> `Concluída` no Smart. Os dois PIX (R$ 12.659,99 e R$ 27.424,40) voltaram
> `Liquidado` no retorno `CP2209000505.RET`, importado às 15:58. A remessa deles não foi
> a do robô: o hub ficou em manutenção das 15:48 às 15:53 (deploy do
> `process-automation`) e a remessa foi gerada fora dele. Antes disso, nenhum clique: as
> rodadas das 14:45 e 15:15 só tinham operações sem assinatura, e as seis que passaram às
> 15:00 já tinham sido finalizadas pelos operadores e pagas das 12:50 às 14:45 (vieram na
> tabela errada da fila, ver "Armadilhas medidas"). **Enquanto os operadores finalizarem
> à mão, eles podem chegar antes**: o robô passa a cada 15 min. Mas nem sempre chegam:
> ainda em DRY, o robô deu `PASSARIA` para XAVANTES (65864) e COTRI (65871) desde 13:45
> de 22/09, e um operador só as finalizou perto de 14:20 e 14:40 (pagas nessas remessas).

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
migration: `database/erp_004_execucao_e_eventos.sql`, aplicada em produção em 21/09/2026.
Desde 22/09 a avaliação leva também a `etapa` lida no Smart.

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
sh /app/src/processors/web/finalizar_operacao/run_agendado.sh

# finaliza de verdade — só depois de validado
sh /app/src/processors/web/finalizar_operacao/run_agendado.sh --executar
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

- **A finalização.** Ligada em 22/09/2026 14:37; as primeiras finalizações reais
  neste servidor foram às 15:46 e 15:47 do mesmo dia (ver "Estado"). Antes disso, tudo foi DRY. O pacote de origem reporta 9 finalizações em
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
depois passou sem problema. Até 22/09/2026 o job reportava isso como
`Locator.click: Timeout`, mensagem que não diz nada, com 15 s de espera numa tela que
pode travar ~90 s (a 65854 deu esse erro a tarde inteira de 22/09). Desde então ele
espera até `R7_ESPERA_BTN_PAGAMENTO_S` (90 s) o botão liberar e, se não liberar, o `ERRO`
diz "botão Pagamento desabilitado: a operação deve estar aberta por outro usuário no
Smart" (teste `test_finalizar_botao_pagamento`).

**Sem banco, o `cedente` sai vazio.** `DB_HOST` vem do `.env` da raiz; no
sandbox não existe e o default (`192.168.50.5`) não responde. Não é defeito de
portabilidade — o `credito` tem o mesmo default. Quem identifica o
recebedor nesse caso é o `favorecido`, lido da grade.

**Screenshot de falha de login vai para `/app`** e falha fora do container.
Perde-se a evidência visual exatamente quando o login quebra.

---

**A fila às vezes é a tabela errada.** A consulta (`_buscar_numeros_uma`, no
`credito`) lê a tabela 1,5 s depois de Pesquisar. Quando o Smart demora, lê a tabela
que já estava na tela: as ~10 operações mais recentes, **das duas securitizadoras e
de qualquer etapa**. Medido 3x em 22/09/2026 (11:00, 14:30, 15:00): a lista "Home"
veio com exatamente 10 operações, incluindo 65877/65876 e 65875/65874, que são da
SmartSecurities. As 65875/65874 estavam na lista certa às 12:45, saíram às 13:00 depois
de finalizadas (pagas na remessa das 12:50) e só voltaram nessas listas de 10. O
custo, até a trava de etapa: em DRY, `PASSARIA` para operação já paga; em modo real,
~45 s por operação esperando um botão que não existe, e um `finalizar_clicado` +
`finalizada_por_outro` no banco para cada uma (a mensagem diz "durante a checagem",
mas eram horas antes). **O risco**, com o clique ligado: operação que o operador tirou
da etapa de propósito, com tudo pronto, ao alcance do Finalizar. Desde 22/09 15:36 a
etapa é lida no Smart **antes de abrir a grade**: a opção marcada no `<select
id="etapaOperacao">` do HTML da tela de edição, a mesma que o robô já baixa por HTTP.
Fora da etapa de entrada, ou sem leitura, não finaliza (teste `test_finalizar_trava_etapa`).
Conferido no Smart em 22/09 15:35: 65879 e 65877 em `Aguardando Ass.`; 65875 e 65846,
já pagas, em `Concluída`, que é para onde a operação vai ao ser finalizada. Desde 22/09
16:21 a própria consulta espera o frame de resultado recarregar e confere a coluna Etapa
de cada linha (ver `credito/_ESTADO_E_PROXIMOS_PASSOS.md`, que tem o dano que a tabela
errada causou no robô de crédito); a leitura da etapa na operação ficou como segunda
barreira.

**Pelo DOM a etapa some depois da grade.** O formulário de edição mora no frame
`stage`, e o Resumir (`novoresumir.php`) e a grade (`gridpagamentodinheirocheque.php`)
abrem nesse **mesmo** frame. A primeira versão da trava lia o `#etapaOperacao` pelo DOM
depois da grade, não achou nada e barrou a 65879, pronta, às 15:31 de 22/09. Qualquer
leitura da tela de edição tem de ser feita antes do Resumir, ou por HTTP.

**Título não lido encolhia a lista de documentos exigidos.** Duplicata e Letra de
câmbio só são exigidas se o tipo dos títulos (`DUR`/`DSR`/`DMR`, `LCB`) for lido na tela.
Até 22/09/2026, título não lido seguia com a lista vazia, que pede só Aditivo + Nota
promissória: uma operação com duplicatas sem assinatura passaria. Não aconteceu em 21 e
22/09 (nenhum "nao li os titulos" no log), mas com o clique ligado a porta tinha de
fechar: desde 22/09 15:30, sem os tipos o veredito é `ERRO` e nada é conferido nem
clicado (teste `test_finalizar_trava_titulos`).

## Pendências para produção

- [x] `config/finalizar_operacao.env` (600) a partir do `.example.env` — 07/09/2026; em 21/09 ganhou aspas nos dois valores com espaço (o `sh` os deixava vazios)
- [x] Task no hub, `--timeout-seconds 1500`, começou `--disabled` em 21/09 09:21 e foi habilitada em DRY às 19:32
- [x] `R7_DRY_RUN` efetivo conferido pelo container em 21/09 — `1`
- [x] Limite de hora para clicar (`R7_HORA_LIMITE_FINALIZAR=18:30`) — 22/09/2026. Vale em `finalizar_da_grade()`, em `finalizar()` e antes do evento `finalizar_clicado`; vazio desliga, valor inválido fecha a porta (teste `test_finalizar_trava_horario`)
- [x] Etapa conferida no Smart (HTML da tela de edição) antes de abrir a grade — 22/09/2026 (teste `test_finalizar_trava_etapa`)
- [x] Títulos não lidos fecham a porta — 22/09/2026 (teste `test_finalizar_trava_titulos`)
- [x] Produção: `R7_DRY_RUN=0` no `.env` e `--executar` na task — 22/09/2026 14:37, por decisão do usuário
- [ ] `placar.py` por alguns dias úteis e a primeira finalização **supervisionada** — dispensados pelo usuário ao ligar a produção em 22/09; acompanhar a primeira finalização real até o retorno do banco
- [x] Consulta da fila: espera a recarga do frame de resultado e confere a coluna Etapa, em vez de 1,5 s fixos — 22/09/2026 (`_buscar_numeros_uma`, compartilhada com o `credito`; teste `test_busca_consulta_etapa`)
- [x] Botão Pagamento desabilitado: espera até 90 s e diagnóstico "operação aberta por outro usuário" — 22/09/2026
- [ ] `notificar.py` ainda aponta para um `email_config.json` de Windows
- [ ] Renomear `r7_config.py` → `finalizar_config.py` (convenção do guia §2)
