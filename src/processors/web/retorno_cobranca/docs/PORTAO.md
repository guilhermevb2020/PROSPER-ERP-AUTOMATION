# Portão — a última conferência antes da baixa

> ## ⚠️ CORREÇÃO 26/08/2026 — leia antes do resto
>
> **A maior parte deste documento descreve uma integração que NÃO EXISTE no
> código hoje.** Verificado lendo `retorno.py` e `processar_retorno_cobranca.py` INTEIROS em
> 26/08/2026: não há `--portao`, `--sem-portao`, `--portao-status-ok`, nem
> leitura de `PORTAO`/`PORTAO_STATUS_OK` em lugar nenhum dos dois arquivos.
> `MOTIVOS_BENIGNOS` (citado abaixo) também não existe. As chaves
> `PORTAO_RET`/`PORTAO_STATUS_OK_RET` **existem** em `retorno_config.py` (ver
> `PORTAO = _b("PORTAO_RET", "False")`), mas nada as lê — são flags mortas.
>
> **O que aconteceu:** o commit `3f72b99` (21/08/2026) escreveu `portao.py` +
> este documento + os 45 testes — e escreveu TAMBÉM a integração em
> `retorno.py`/`processar_retorno_cobranca.py` que este documento descreve, mas **deixou os
> dois de fora do commit de propósito** (mensagem do commit: *"os dois já
> carregavam trabalho não commitado de outra pessoa antes desta sessão, e
> commitá-los varreria esse trabalho para dentro deste commit"*). Ficou como
> edição não commitada — e depois se perdeu, sobrescrita por edições
> seguintes nos mesmos dois arquivos. Ninguém percebeu até hoje.
>
> **O que EXISTE de verdade hoje:** um portão diferente e mais simples, para
> um job diferente — `baixar_deposito_no_erp` (`run_deposito.sh`), não
> `processar_retorno_cobranca_cnab_400` (nome atual; era `processar_retornos_cnab`
> até 26/08, renomeado duas vezes no mesmo dia). Ver
> [seção nova abaixo](#o-portão-que-existe-de-verdade-hoje-26082026).
>
> **O resto deste documento continua valendo como REFERÊNCIA DE DESENHO** — o
> raciocínio do BUG-548, os números medidos (0 recusa falsa em 1.238 títulos),
> o que o portão garante e não garante. Só não confie nos comandos `--portao`/
> `--sem-portao`/`PORTAO_RET` contra `processar_retorno_cobranca.py`: eles não fazem nada
> até alguém reescrever a integração — do zero, seguindo este documento como
> especificação.

O `PROCESSAR_ARQUIVO` é o único passo irreversível da automação de retorno: depois dele o título
está baixado no Smart. O **portão** fica exatamente ali, entre o upload e a
baixa. Ele lê a grade que o upload devolveu, compara **o título que o Smart
resolveu** com **a linha que o arquivo mandou**, e recusa o arquivo quando os
dois discordam.

O *porquê* e as medições estão no docstring de
[`portao.py`](../portao.py). Este documento é o outro lado: **como operar**
— **quando a integração abaixo existir de verdade.**

## O portão que existe DE VERDADE hoje (26/08/2026)

Wiring mínimo, feito hoje para destravar `baixar_deposito_no_erp` (desabilitada
pelo circuit breaker após 3 falhas — `run_deposito.sh` chamava `--portao` que
o argparse não reconhecia, exit 2 determinístico, 100% das vezes).

| | Este (hoje) | O que o resto do doc descreve (não existe) |
|---|---|---|
| Flag | `--portao` (`store_true`, sem oposto) | `--portao` / `--sem-portao`, "última flag vence" |
| Config | nenhuma — sempre chumbado no wrapper | `PORTAO_RET` / `PORTAO_STATUS_OK_RET` no `.env` |
| Job | `baixar_deposito_no_erp` (`run_deposito.sh`, `--portao` fixo na linha) | `processar_retorno_cobranca_cnab_400` |
| `exigir_status_ok` | sempre `False` (não exposto) | `--portao-status-ok` opcional |
| Ponto de entrada | `retorno.py::processar()`, param `usar_portao`, entre o corte do `dry_run` e `processar_arquivo` | mesmo lugar, mesma ideia |
| Motivo gravado | `"RECUSADO PELO PORTAO: {sumario}"` | `"PORTAO recusou: ..."` (texto diferente) |
| Log por título recusado | `processar_retorno_cobranca.py::relatar()`, bloco `PORTAO RECUSOU O ARQUIVO` | formato "três vezes" descrito abaixo (não existe) |

Reusa o **mesmo** `portao.py`/`avaliar_grade()` — o módulo puro é o mesmo para
os dois jobs, só a chamada (`retorno.py`) e a exposição (`processar_retorno_cobranca.py`)
divergem. Commit: `2be6786`. Verificado com import real dentro do container e
a suíte de 45 testes de `portao.py` (inalterada, ainda passa).

⛔ **Se alguém quiser o portão em `processar_retorno_cobranca_cnab_400`** (o
job que este documento originalmente descreve — hourly, `50 8-18 * * 1-5`,
retorno bancário real), a integração completa (`--sem-portao`,
`PORTAO_STATUS_OK`, o formato de log "três vezes", `MOTIVOS_BENIGNOS`) precisa
ser **escrita de novo** em `retorno.py`/`processar_retorno_cobranca.py` — nada disso
sobrevive hoje. É trabalho novo, não é ligar uma chave.

---

> ⛔ **Descrição original (21/08/2026) — não reflete o código atual, ver
> correção acima.** Hoje o portão está DESLIGADO para o job abaixo porque a
> integração nunca chegou a ser commitada. Não há chave
> `PORTAO_RET` em `config/retorno_cobranca.env`, e `retorno_config` dentro do
> container devolve `PORTAO = False` / `PORTAO_STATUS_OK = False` — mas isso é
> irrelevante hoje: mesmo `True`, nada leria essas chaves.

## ⭐ Chegou aqui por um alarme?

Vá direto:

1. **[Como ler uma recusa](#como-ler-uma-recusa)** — o formato no log e os três
   motivos.
2. **[O que fazer com uma recusa](#o-que-fazer-com-uma-recusa)** — o passo a
   passo, e por que a recusa **não** se resolve sozinha.
3. **[Exit code](#exit-code-e-o-que-o-hub-faz)** — a task já repetiu sozinha; não
   há baixa dupla.

⛔ **Antes de rodar qualquer coisa à mão:** este container está com
`DRY_RUN_RET=false`. **Toda rodada manual dá baixa de verdade.** Leia
[a armadilha do dry-run](#-a-armadilha-do-dry-run) e
[a janela segura](#-a-janela-segura-é-do-minuto-20-ao-40) primeiro.

---

## Antes de qualquer coisa: onde este automação roda

⛔ **`src/` deste projeto é bind-mount `rw`.** Salvar um arquivo aqui **publica
na hora**. Não há imagem, não há `docker compose build`, não há passo de deploy.

```
/home/prospere/docker/automation/erp-automation/src  ->  /app/src   (bind, rw)
```

Isto é o **oposto** do `process-automation`, onde `setores/` vem da imagem e só
entra no ar com `deploy_process_automation.sh`. Aqui, editar `portao.py` muda o
comportamento da próxima rodada — que sai **daqui a menos de uma hora**.

⭐ **Consequência prática, quando a integração existir:** editar `retorno.py`/
`processar_retorno_cobranca.py` muda o comportamento da próxima rodada — que sai em menos de
uma hora. Não exige publicar nada. ⛔ **Hoje (26/08/2026) só o módulo
(`portao.py`) está lá — as flags dos dois arquivos não** (ver correção no
topo).

E o job que ele guarda não é ensaio:

| | |
|---|---|
| Task no hub | `processar_retornos_cnab` (container `erp-automation`) |
| Comando | `sh /app/src/processors/web/retorno_cobranca/run_agendado.sh --pular-processados` |
| Cron | `50 8-18 * * 1-5` — **de hora em hora, dias úteis**, das 08:50 às 18:50 |
| Duração medida | mediana **5,9 min**, média **7,4 min**, máxima **27,0 min** (34 execuções em 14 dias) |
| Timeout / retries | 1800 s · `max_retries=2`, 60 s de intervalo |
| `DRY_RUN_RET` | **`false`** (`config/retorno_cobranca.env`, linha 12) |

⛔ **`DRY_RUN_RET=false` quer dizer que ele DÁ BAIXA DE VERDADE, 11 vezes por dia
útil.** É por isso que o portão nasceu desligado: ligá-lo muda o comportamento de
um job que mexe em produção sozinho, de hora em hora.

---

## Onde ele entra

```
1..5  VERIFICAR / VALIDAR_BANCO_CONTA        nada efetivado
6     UPLOAD_ARQUIVO                          <- devolve a GRADE, ainda nada efetivado
      └─ PORTÃO         confere a grade  ──►  veredito
         ├─ dry_run=True?  RELATA o veredito e para aqui (não dá baixa)
         └─ rodada de verdade: RECUSOU? o arquivo não sobe
8     PROCESSAR_ARQUIVO                       <- AQUI DÁ BAIXA
9     RETIRAR_EM_PROCESSAMENTO
```

O portão está em [`retorno.py`](../retorno.py), dentro de `processar()`, **antes**
do corte do `dry_run` e **antes** do `processar_arquivo`.

⭐ **Em ensaio o portão RODA e RELATA — só não recusa.** É de propósito, e é para
isto que o ensaio existe: *sobe em ensaio, lê a grade, decide*. Rodar com
`-e DRY_RUN_RET=true --portao` mostra, título a título, o que o portão faria numa
rodada de verdade, sem tocar em nada. Quem recusa de fato é a rodada de verdade.

⭐ Quer só a grade crua, sem veredito? `--csv-titulos` continua fazendo isso.

---

## O que ele GARANTE

**Que o título que o Smart resolveu bate com o que o arquivo mandou** — e isso é
conferido *antes* do passo irreversível.

A grade do upload traz os dois lados lado a lado:

```
valor_titulo / vencimento / sacado ......... o título que o SMART resolveu
numero_titulo / valor_titulo_arq / ......... a linha que o ARQUIVO mandou
valor_pago / data_ocorrencia / ...
```

Quando o Smart casa a linha no título errado, os dois lados discordam. Foi
exatamente o que se viu no `BUG-548`: R$ 4.033,33 do lado do Smart contra
R$ 6.108,23 do lado do arquivo, título de outro sacado.

O portão não tenta reproduzir o critério de casamento do Smart. Ele **lê o que o
Smart decidiu e confere contra o que mandamos**.

---

## O que ele NÃO garante

⭐ **Esta é a parte mais útil do documento.** O portão é uma trava estreita.
Saber o que ele não vê evita confiar nele para o que ele não faz.

**1. Não valida se o pagamento existiu.** Ele confere casamento, não realidade.
Arquivo com uma liquidação que o banco nunca processou passa liso, desde que os
dois lados da grade concordem.

**2. Não confere o sacado contra a nossa base.** A grade só traz o sacado **do
lado do Smart** — não há coluna de sacado do lado do arquivo. Comparar
`sacado × sacado` é impossível com o que o upload devolve. O discriminador é o
**valor**.

**3. ⛔ Não pega erro em que o Smart e o arquivo CONCORDEM.** Se o defeito está
*a montante* — o arquivo já saiu apontando para o título errado — o Smart resolve
aquele título errado com o valor errado, os dois lados batem, e o portão aprova.
Este caso é real e tem nome: o `BUG-569` (a conciliação escolhia o título errado
em `importar_retornos_cnab`; foi corrigido lá, não aqui). **O portão é a última
trava, não a única.**

**4. Não reescreve arquivo.** O veredito é **por ARQUIVO, tudo ou nada**: um
título recusado e o arquivo inteiro não sobe. Filtrar as linhas boas exigiria
recomputar o trailer do CNAB-400 — fabricar um arquivo terceiro, que é a mesma
classe de defeito do `BUG-548`. No arquivo que **nós** geramos é mais barato
regerar sem a linha ruim; no arquivo **do banco**, apagar linha apaga ocorrência
que ele reportou.

**5. Não bloqueia nada em DRY_RUN** — ver acima.

---

## As duas chaves

| Chave (`config/retorno_cobranca.env`) | Flag | Padrão | O que faz |
|---|---|---|---|
| `PORTAO_RET` | `--portao` / `--sem-portao` | `False` | liga o portão: recusa por **valor divergente** e por **título não resolvido** |
| `PORTAO_STATUS_OK_RET` | `--portao-status-ok` | `False` | **além** do acima, recusa quem tem `status != OK` |

**Por que duas e não uma:** porque uma delas não custa nada e a outra custa.
Medido em 21/08/2026 sobre as três capturas reais de banco
(`titulos_prod_0408.csv`, `titulos_0508.csv`, `titulos_teste.csv`): **1.238
títulos em 257 arquivos**.

- critério padrão (valor): **0 arquivos recusados de 257**;
- com `PORTAO_STATUS_OK_RET`: **5 arquivos recusados de 257**, todos por
  `Data de vencimento diferente` — que é **liquidação legítima**.

⭐ **Ligue `PORTAO_RET`. Deixe `PORTAO_STATUS_OK_RET` desligado**, a menos que
alguém decida que 5 arquivos represados em 257 é o preço aceitável.

⛔ **`PORTAO_STATUS_OK_RET` sozinho NÃO liga o portão.** Sem `PORTAO_RET`, todo o
bloco é pulado ([`retorno.py:376`](../retorno.py)) e a chave não faz efeito
nenhum. O mesmo vale para `--portao-status-ok` sem `--portao`.

---

## Como ligar

⛔ **É ato do dono.** Ligar muda o comportamento de um job que dá baixa em
produção 11 vezes por dia útil, e a mudança vale **na próxima rodada** — sem
publicar, sem reiniciar, sem ninguém revisar.

### Permanente (é este o jeito certo)

Acrescente a linha ao arquivo de credenciais — ela **não existe lá**, não é
questão de descomentar:

```bash
# host
echo 'PORTAO_RET=true' >> /home/prospere/docker/automation/erp-automation/config/retorno_cobranca.env
```

Confira o valor efetivo **dentro do container**, que é onde ele conta:

```bash
docker exec -e PYTHONPATH=/app erp-automation python -c "
import sys; sys.path.insert(0,'/app/src/processors/web/retorno_cobranca')
import retorno_config as c; print('PORTAO =', c.PORTAO, '| STATUS_OK =', c.PORTAO_STATUS_OK)"
```

⭐ `config/` também é bind-mount `rw`: **vale na próxima rodada**, sem restart. O
`run_agendado.sh` relê o `.env` a cada execução.

Valores aceitos como verdadeiro: `1`, `true`, `sim`, `yes` (maiúsculas dão no
mesmo). Qualquer outra coisa é falso.

### Só numa rodada manual

```bash
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py \
    --pasta /app/data/cnab_nextcloud/Retornos/2026/08-Agosto/21/MoneyPlus \
    --portao
```

### Desligar

Tire a linha do `.env`, ou ponha `PORTAO_RET=False`. Numa rodada manual, use
`--sem-portao`.

⭐ **A última flag da linha de comando vence.** `--portao --sem-portao` desliga;
`--sem-portao --portao` liga. Verificado no parser.

---

## Como ler uma recusa

Ela aparece **três vezes** no log, com o mesmo texto. Este é o formato exato,
gerado pelo próprio código:

```
[12:42:10]   [1/20] CP2108000797.RET         conta=  314 titulos=3    RECUSADO    PORTAO recusou: 2 de 3 titulo(s) recusado(s): o Smart nao resolveu titulo para esta linha (1), valor no Smart diverge do valor no arquivo (1)
[12:42:10]             acoes: Liquidado=3
[12:42:10]             PORTAO RECUSOU: 2 de 3 titulo(s) recusado(s): o Smart nao resolveu titulo para esta linha (1), valor no Smart diverge do valor no arquivo (1)
[12:42:10]               titulo 12594-003    valor no Smart diverge do valor no arquivo | smart=4033.33 arquivo=6108.23 sacado=CONSORCIO DCDC COMERCIO
[12:42:10]               titulo 99881-002    o Smart nao resolveu titulo para esta linha | arquivo=1.200,00 smart=(vazio)
...
[12:42:10]   1 com aviso/erro:
[12:42:10]     CP2108000797.RET         PORTAO recusou: 2 de 3 titulo(s) recusado(s): ...
```

- coluna `RECUSADO` na linha do arquivo;
- `PORTAO RECUSOU:` com o sumário e **até 10 títulos**, um por linha (acima de
  10 ele diz quantos ficaram de fora e manda usar `--csv-titulos`);
- o arquivo reaparece na lista `com aviso/erro` do resumo final.

**Onde procurar:**

```bash
grep -i 'PORTAO' /home/prospere/docker/automation/erp-automation/logs/robo_retorno_$(date +%F).log
grep    'PORTAO' /home/prospere/docker/automation/erp-automation/data/robo_retorno/controle_processados.csv
```

O `controle_processados.csv` guarda uma linha por arquivo, com `motivo` e
`quando` — é lá que estão as recusas de dias anteriores.

### Os três motivos

| Motivo no log | O que aconteceu | O que fazer |
|---|---|---|
| `valor no Smart diverge do valor no arquivo` | O Smart resolveu **outro título**. É a forma do `BUG-548`. | ⛔ **Não force.** O erro é a montante, no arquivo que geramos. |
| `o Smart nao resolveu titulo para esta linha` | O Smart não achou título nenhum para aquela linha. | Nada seria baixado *naquela linha* — mas o arquivo inteiro está barrado. Descubra por que o título sumiu. |
| `status diferente de OK` | Só aparece com `PORTAO_STATUS_OK_RET` (ou no ramo BB API, que exige status OK). Quase sempre `Data de vencimento diferente`. | Liquidação legítima. ⏪ Desde 17/09/2026 a linha `Liquidado` com esse status **passa** mesmo com o status exigido (`portao.STATUS_TOLERADOS_NA_LIQUIDACAO`): a entrega BB 38, 67 pagamentos, caiu inteira pelo 11893-001 (boleto vencendo 14/09 no banco e 30/09 no ERP, pago em 17/09). Em `Prorrogado`/`Entrada …` o status continua recusando. |

---

## O que fazer com uma recusa

**1. Pegue a grade inteira do arquivo recusado.** O CSV é gravado mesmo quando o
portão recusa — a grade vem do upload, que já aconteceu:

```bash
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py \
    --pasta /app/data/cnab_nextcloud/Retornos/2026/08-Agosto/21/MoneyPlus \
    --arquivo CP2108000797.RET --portao \
    --csv-titulos /app/data/robo_retorno/recusa_$(date +%F).csv
```

**2. Decida pela origem do arquivo.**

- **Arquivo que NÓS geramos** (`gerar_retorno_erp`, no `process-automation`) →
  ⭐ **regere sem a linha ruim.** Não filtre à mão: recomputar o trailer do
  CNAB-400 é fabricar arquivo terceiro. Corrija a causa no gerador.
- **Arquivo do BANCO** → ⛔ **não apague linha.** Apagar linha apaga ocorrência
  que o banco reportou. Escale.

**3. Se decidir que a recusa é falso positivo**, e só então, deixe passar de
propósito, com o arquivo nomeado:

```bash
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py \
    --pasta <a pasta do dia> --arquivo <o arquivo> --sem-portao
```

⛔ Isto **dá baixa de verdade** (`DRY_RUN_RET=false`). Não é um teste.

### ⛔ A recusa não se resolve sozinha — e depois some

Um arquivo recusado **não entra no controle como processado** — o hash só é
marcado quando a baixa acontece. Consequência, em cadeia:

1. `--pular-processados` **não** o pula na rodada seguinte;
2. ele é reprocessado **de hora em hora**, recusa de novo, e a task falha de novo
   — 11 alarmes por dia útil;
3. **até que a pasta do dia saia da janela retroativa.** O `run_agendado.sh`
   varre `DIAS_RETROATIVOS_RET` dias (padrão **5**). No sexto dia a pasta sai da
   varredura, **o alarme para sozinho — e o arquivo nunca foi processado.**

⭐ **Trate a recusa em até 5 dias.** Depois disso o silêncio não significa que
alguém resolveu.

---

## Exit code, e o que o hub faz

Recusa de portão **não é motivo benigno**. Confirmado lendo o código:

- o `motivo` gravado é `"PORTAO recusou: ..."`;
- `MOTIVOS_BENIGNOS` ([`processar_retorno_cobranca.py:165`](../processar_retorno_cobranca.py)) só contém
  `DRY_RUN`, `conteudo identico ja processado` e
  `ja esta em processamento no Smart`;
- logo `_e_pendencia()` devolve **`True`**, o arquivo entra em `com_erro`, e a
  rodada retorna **`SAIU_COM_PENDENCIA` = 6**;
- o `run_agendado.sh` guarda o **maior** exit code das 5 pastas-dia
  (`run_agendado.sh:122`), e 6 é o maior que a automação de retorno usa — basta **uma** recusa em
  **qualquer** dia para o wrapper inteiro sair com 6.

**O hub marca a execução como `failed`** e, por `max_retries=2`, **repete a
rodada 60 s depois**. Verificado no histórico: em 19/08/2026 a execução das
16:50 saiu com 6 e a tentativa 2 subiu às 16:56.

⛔ **A repetição não conserta uma recusa de portão** — o mesmo arquivo é lido de
novo e recusa de novo. Ela só é *segura*: os arquivos que já foram baixados na
tentativa 1 são pulados pelo `--pular-processados`, então **não há baixa dupla**.

Para ver o estado no hub:

```bash
docker exec postgres psql -U prospere -d prosperedb -c "
SELECT inicio, tentativa, status, exit_code
  FROM hub_orchestration.task_execucao
 WHERE task_nome='processar_retornos_cnab'
 ORDER BY inicio DESC LIMIT 10;"
```

⭐ **Exit 6 não é exclusivo do portão.** Sessão do Smart caída, arquivo vazio,
acima do limite de linhas e conta não cadastrada também dão 6. Leia a lista
`com aviso/erro` do log antes de concluir que foi o portão.

---

## Rodar à mão: a janela segura

⛔ **A automação de retorno agendado MATA qualquer Chrome do perfil dele na largada.**
`run_agendado.sh:26` faz `pkill -f "user-data-dir=$PERFIL"`, porque um perfil com
lock não sobe. Não há negociação: quem chegou primeiro perde.

Portanto, rodar à mão perto do minuto **:50**:

- **antes de :50** → a rodada agendada mata a sua no meio, possivelmente entre o
  upload e a baixa;
- **em cima de :50** → a sua tenta subir num perfil travado e falha;
- **depois de :50** → você mata a rodada de produção em voo.

### ⭐ A janela segura é do minuto :20 ao :40

A conta: a agendada começa em `:50`; a mediana é 5,9 min (termina ~`:56`), mas a
**máxima medida foi 27 min** — ou seja, pode invadir até o `:17` da hora
seguinte. E, se falhar, uma tentativa 2 sobe 60 s depois.

**Sempre confirme antes de começar:**

```bash
docker exec erp-automation pgrep -af 'processar_retorno_cobranca.py'   # vazio = nada rodando
```

Fora do horário da task (antes das 08:50, depois das ~19:20 — a última rodada
começa 18:50 e pode levar 27 min —, fins de semana) a pista está livre. **Mas** o
`config/retorno_cobranca.example.env` registra que a janela do usuário do Smart é
**06:30–21:00, seg-sex**. Fora dela o login não passa.

### ⛔⛔ A armadilha do dry-run

**Não existe flag `--dry-run`.** A automação de retorno calcula `dry = cfg.DRY_RUN and not
args.pra_valer`, e `cfg.DRY_RUN` é **`False`** neste container. Ou seja:
**qualquer rodada manual aqui dá baixa de verdade, por padrão.**

Para forçar ensaio, a variável tem de vir no `docker exec` — e **só funciona
chamando o Python direto**:

| Como você chama | `-e DRY_RUN_RET=true` funciona? |
|---|---|
| `python .../processar_retorno_cobranca.py` | ✅ **sim** — `load_dotenv` não sobrescreve o ambiente |
| `sh .../run_agendado.sh` | ⛔ **NÃO** — o wrapper faz `set -a; . retorno_cobranca.env` e o arquivo (`DRY_RUN_RET=false`) **sobrescreve o seu `-e`**, em silêncio |

Verificado nos dois caminhos em 21/08/2026.

```bash
# ENSAIO de verdade — Python direto, nunca o wrapper
docker exec -e PYTHONPATH=/app -e DRY_RUN_RET=true erp-automation \
  python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py \
    --pasta /app/data/cnab_nextcloud/Retornos/2026/08-Agosto/21/MoneyPlus \
    --limite 3 --detalhes
```

⭐ Confirme na primeira linha do bloco: a automação de retorno imprime
`DRY_RUN (nao processa)` ou `*** PRA VALER - VAI DAR BAIXA ***`. **Leia essa
linha antes de sair de perto.**

---

## Referência rápida

| Quero… | Comando |
|---|---|
| saber se o portão está ligado | `docker exec -e PYTHONPATH=/app erp-automation python -c "import sys;sys.path.insert(0,'/app/src/processors/web/retorno_cobranca');import retorno_config as c;print(c.PORTAO, c.PORTAO_STATUS_OK)"` |
| ligar em definitivo | `echo 'PORTAO_RET=true' >> .../config/retorno_cobranca.env` |
| ligar só nesta rodada | `--portao` |
| desligar só nesta rodada | `--sem-portao` |
| ver recusas de hoje | `grep -i PORTAO .../logs/robo_retorno_$(date +%F).log` |
| ver recusas antigas | `grep PORTAO .../data/robo_retorno/controle_processados.csv` |
| a grade inteira de um arquivo | `--arquivo X.RET --csv-titulos /app/data/robo_retorno/x.csv` |
| ver se há rodada em voo | `docker exec erp-automation pgrep -af processar_retorno_cobranca.py` |
| rodar um ensaio de verdade | `-e DRY_RUN_RET=true` **+ Python direto** (nunca o wrapper) |

### Arquivos

| | |
|---|---|
| Módulo | [`../portao.py`](../portao.py) — puro, só stdlib |
| Ponto de entrada | [`../retorno.py:376`](../retorno.py) (dentro de `processar()`) |
| Flags | [`../processar_retorno_cobranca.py:500-509`](../processar_retorno_cobranca.py) |
| Chaves | [`../retorno_config.py:86-87`](../retorno_config.py) |
| Testes | `tests/unit/test_portao_retorno.py` — **45 testes, rodam no HOST** (o container não tem pytest): `cd /home/prospere/docker/automation/erp-automation && python3 -m pytest -q tests/unit/test_portao_retorno.py` |
| Visão geral da automação de retorno | [`README.md`](README.md) |
