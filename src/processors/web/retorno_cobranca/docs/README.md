# Robô de Processar Retorno (CNAB)

Lê os arquivos de **retorno** do banco (`.RET`) e dá baixa nos títulos no Smart
Securities, **inteiramente por HTTP**. Sobe o próprio Chrome só para ter sessão;
nunca abre a tela nem clica em nada.

O **download** dos `.RET` no banco não é deste robô — os arquivos chegam prontos
na pasta de entrada.

---

## Como funciona

A tela *Financeiro > CNAB > Processar Retorno* não posta formulário: ela conversa
com `financeiro/ajax/ajaxretornocnab.php` mudando o parâmetro `Acao`. O robô faz
as mesmas chamadas, na mesma ordem:

| # | Ação | O que faz |
|---|---|---|
| 1 | `VERIFICAR_ARQUIVO_EM_PROCESSAMENTO` | trava anti-concorrência |
| 2 | `VERIFICAR_ARQUIVO_PROCESSADO` | já rodou? — **só informativo**, ver abaixo |
| 3 | *(cliente)* | conta linhas — limite 5000 |
| 4 | `VALIDAR_BANCO_CONTA` | manda o **header** e recebe a conta |
| 5 | `UPLOAD_ARQUIVO` | envia o conteúdo como **texto** (não é multipart) |
| 6 | `PROCESSAR_ARQUIVO` | **← é aqui que dá baixa** |
| 7 | `VERIFICAR_CRITICAS` + `RETIRAR_EM_PROCESSAMENTO` | confere e solta a trava |

Até o passo 5 nada é efetivado — por isso o `DRY_RUN` para exatamente ali.

---

## Onde ele vive

| Recurso | Valor |
|---|---|
| Display / VNC / noVNC / CDP | `:95` / 5904 / 6084 / 9225 |
| Perfil Chrome | `/app/data/robo_retorno/perfil_chrome` |
| **Entrada dos `.RET`** | `/app/data/retornos_a_processar` — host: `erp-automation/data/retornos_a_processar` |
| Arquivo processado | `_PROCESSADOS/<AAAA-MM>/` dentro da entrada |
| Controle | `/app/data/robo_retorno/controle_processados.csv` |
| Credenciais | `/app/config/retorno_cobranca.env` (fora do git) |
| Task no hub | `processar_retorno_cobranca_cnab_400` ⏪ renomeada 2× em 26/08/2026, era `processar_retornos_cnab` → `processar_retornos_cnab400` → nome atual. Cron real: `50 8-18 * * 1-5` (hora em hora, não `30 8`) |

Os arquivos vão **soltos** na raiz da entrada — o robô não desce um nível. É por
isso que `_PROCESSADOS/` pode morar lá dentro sem atrapalhar.

⭐ **Este script tem um SEGUNDO consumidor desde 26/08/2026:** `baixar_deposito_no_erp`
(`run_deposito.sh`, pasta `_deposito`, `--deposito` e `--portao` sempre ligados)
chama o mesmo `processar_retorno_cobranca.py`/`retorno.py`. O modo depósito é estrito e não
altera o retorno bancário: exige CNAB-400 com identificador de 25 dígitos,
quantidade idêntica no arquivo/upload/grade, valor legível e igual, ação
`Liquidado`, status `OK` e, depois do passo irreversível, `message=OK`,
`liquidacao=quantidade` e `refinan=0`.

---

## Ciclo de vida do arquivo

```
entrada/ARQ.RET  --processa-->  _PROCESSADOS/2026-08/ARQ.RET
                 --falha----->  fica na entrada (a próxima rodada tenta de novo)
```

Três cuidados no arquivamento, e cada um tem motivo:

1. **DRY_RUN nunca move.** Ensaio não mexe em caixa de entrada de produção.
2. **Falha não move.** Mover erro para um canto é o jeito de ele nunca mais ser
   visto. Fica na entrada, visível.
3. **Nunca sobrescreve no destino.** Nome repetido com conteúdo diferente é caso
   real aqui; o que já está arquivado é a prova do que foi processado, então o
   novo ganha sufixo de hora.

Se o move falhar **depois** de processar, o arquivo volta a ser candidato na
rodada seguinte. Quem protege é o controle por hash — por isso o comando
agendado usa **`--pular-processados`**.

Na rota de **depósito**, o ciclo é deliberadamente mais fechado e o movimento é
individual — uma recusa não prende os arquivos bons da mesma rodada:

```text
_deposito/ARQ.RET --comprovado no Smart--> _PROCESSADOS/AAAA-MM/
                  --portão recusou-------> _REJEITADOS/AAAA-MM/
                  --resposta inconclusiva
                    após PROCESSAR--------> _INCONCLUSIVOS/AAAA-MM/
                  --erro antes de PROCESSAR-> fica na entrada para retry

cada tentativa --------------------------> _RESULTADOS/AAAA-MM-DD/*.json
```

O recibo registra os hashes, a grade, o portão e a resposta bruta. Ele não
afirma sozinho que o DWH já refletiu a baixa; o `process-automation` só confirma
`enviado_erp_em` quando o recibo comprova a liquidação **e** o título saiu de
aberto e apareceu em quitado.

---

## Uso

```bash
# produção (o hub chama isto)
sh /app/src/processors/web/retorno_cobranca/run_agendado.sh --pular-processados

# manual
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py --limite 5 --detalhes
docker exec erp-automation sh /app/src/processors/web/retorno_cobranca/run_agendado.sh \
  --pra-valer --csv-titulos /app/data/robo_retorno/titulos.csv
```

**`--pra-valer` é obrigatório para dar baixa** — ou `DRY_RUN_RET=false` no
`.env`. Sem isso o robô valida, mostra o que faria e não toca em nada.

### Códigos de saída

| Código | Significa |
|---|---|
| 0 | rodada completa |
| 1 | não consegui um navegador |
| 2 | sessão não logada |
| 3 | **não consegui falar com o Smart** — ≠ deslogado |
| 4 | pasta de entrada não existe |
| 6 | abortou no meio, ou arquivo com erro num run real |

---

## Armadilhas já resolvidas (não desfazer sem ler)

**1. Identidade é o CONTEÚDO, nunca o nome.** Chega arquivo com o mesmo nome no
mesmo dia e conteúdo diferente — e ele **tem** que ser processado como novo. O
`VERIFICAR_ARQUIVO_PROCESSADO` do Smart compara só o nome e responde "já
processado" nesse caso. Por isso o controle guarda o **md5 do conteúdo**, e o
`ja_processado` do Smart é apenas informativo.

**2. O POST precisa ir urlencodado.** Passar `data={dict}` para o Playwright
serializa como JSON, o PHP não acha nada em `$_POST` e responde
`{"message": "UNKNOW_ACTION"}` — fácil de confundir com "não tem nada", porque
`EmProcessamento` também volta vazio. O robô urlencoda na mão **e** trata
`UNKNOW_ACTION` como erro explícito.

**3. Sessão morta responde HTTP 200**, com um redirect JS para `expira.php`. Sem
`recaptcha`, sem `expirou` (é *"expira"*, sem o U). Ver
`src/common/clients/smart_sessao.py::parece_deslogado`.

**4. Timeout ≠ deslogado.** O Smart fica lento logo depois de processar e o ping
estourava; o robô anunciava "sessão não está logada" com a sessão perfeita.
`sessao_viva()` tenta 3× com 45s e separa três estados: logado, deslogado (a
resposta disse) e "não consegui falar" (exit 3).

**5. Cabeçalho do CSV.** Controle criado por uma versão com menos colunas
desalinha o arquivo inteiro ao receber linhas novas. O robô compara o cabeçalho
do disco e arquiva o antigo antes de continuar.

**6. Não use a tela com o Playwright anexado.** O Chrome trata a conexão CDP como
depurador e qualquer `debugger;` no JS congela a página. Como o robô é 100% HTTP,
o problema não existe — mas vale saber para quem for automatizar pela interface.

---

## Estado

**Validado no container em 03/08/2026, em DRY_RUN**, com 71 `.RET` reais (CAST
METAIS, banco 274): 149 títulos, R$ 1.264.199,18, todos `Liquidado` com status
OK, 61 críticas em 42 arquivos, **zero erro e zero divergência**, exit 0. O
auto-login CapSolver no display `:95` funcionou de primeira.

**NÃO exercitado nesta instalação:**

- **o `PROCESSAR_ARQUIVO`** — nenhuma baixa foi dada aqui ainda. 73 dos 76
  registros do teste voltaram `ja_processado=True`, porque esses arquivos já
  tinham sido processados em 31/07 no ambiente do autor;
- **o arquivamento** em `_PROCESSADOS/` (só roda depois de processar de verdade);
- **a regra do hash** (mesmo nome, conteúdo diferente). Os três arquivos com
  `(1)` no nome *não* servem de teste: o saneamento do Smart remove espaço e
  parênteses, então `CP3007000239 (1).RET` vira `CP30070002391.RET` — um nome
  diferente do original;
- **conta não cadastrada** (`--aceitar-conta-desconhecida`). No ambiente do autor
  5 arquivos param aí, de cedentes PHINTER e PROSPER GESTÃO;
- **divergência grade × contador** — vista 2× em 31/07 (17 previstas × 12
  registradas), sem explicação. Reprocessar dá o mesmo número. O robô registra e
  segue.

**Desempenho medido:** ~4s por arquivo em DRY_RUN; 71 arquivos em ~5 min.

**Fonte do "já processei" (Fase 2 de `docs/PLANO_CONTROLE_NO_BANCO.md`):** `CONTROLE_FONTE_RET` = `csv` (padrão) ou `banco`: o Python lê `erp_automation.vw_controle_retorno` (uma linha por arquivo, `processado` = último evento) e o wrapper lê a lista de md5 do banco (`src/processors/db/controle/listar_md5.py`) em vez do `grep` no CSV; sem banco, os dois voltam ao CSV avisando. O CSV é escrito nos dois modos até o corte. Vale para `run_agendado.sh`, `run_bb.sh` e `run_deposito.sh` (os três chamam o mesmo Python). Em `banco` a memória é **banco ∪ histórico do CSV** até a Fase 4 (o banco só conhece o que entrou desde 21/09/2026; um `.RET` antigo re-entregue não pode virar novidade — seria baixa em duplicidade).
