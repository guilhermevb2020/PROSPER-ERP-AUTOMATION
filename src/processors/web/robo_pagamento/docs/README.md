# Robô de Remessa de Pagamento (BMP Money Plus)

Gera a remessa de **pagamento** no Smart e salva o `.REM`. Sobe o próprio Chrome
só para ter sessão; o trabalho é por HTTP, em **duas requisições**.

Tela: **Financeiro › Sistemas de pagamento › Pagamento BMP Money Plus › Gerar
Remessa** (`financeiro/pagtobmp/`).

> ⛔ **Não confundir com o `robo_remessa`.** Aquele é a remessa de **cobrança**
> (`financeiro/remessaocorrencia.php`, CNAB-400). Este é pagamento
> (`financeiro/pagtobmp/`, CNAB-240). Cobrança pede dinheiro; pagamento manda.

---

## Estado: EM PRODUÇÃO, agendada e rodando (26/08/2026)

O contrato foi medido contra o Smart real em 21/08/2026 pelo sandbox do host, e
em 25/08/2026 o fluxo completo foi validado com dinheiro de verdade se movendo
(confirmado pelo dono).

| | |
|---|---|
| ✅ Fluxo validado em produção real, dinheiro se moveu | 25/08 |
| ✅ 116 testes no host | |
| ✅ `config/robo_pagamento.env` com a credencial definitiva | 25/08 |
| ✅ As duas chaves de geração ligadas — `DRY_RUN_PAG=False`, `PRA_VALER_PAG=--pra-valer` | 25/08 |
| ✅ Commitado | 25-26/08 |
| ✅ Task no hub — `gerar_remessa_pagamento_bmp`, cron `0,30 8-18 * * 1-5`, **enabled** | 25/08 |
| ✅ `enviar_pagamento` (process-automation) depende desta task (status `success`) | 25/08 |

O que falta é só o item de decisão de dono (quem mais mexe na conta 404) — ver
[`PENDENTE.md`](PENDENTE.md).

O elo seguinte do ciclo — ler o retorno do banco e inserir de volta no Smart —
é o `robo_retorno_pagamento` (task `processar_retorno_pagamento_cnab_240`),
⏪ **produção de verdade desde 26/08/2026** — as duas etapas provadas contra
5 títulos reais, `DRY_RUN_RETPAG=false`. Ver
`../robo_retorno_pagamento/docs/README.md`.

## O ciclo — duas requisições, e acabou

| # | O quê | Endpoint |
|---|---|---|
| 1 | Pesquisa pendentes | `POST financeiro/pagtobmp/pagtobmppesquisa.php` → `pagtobmpgrid.php` |
| 2 | Gera | `POST financeiro/pagtobmp/pagtobmpgrid.php` com `processar=1` e `acao=1` |

**A resposta do passo 2 é o próprio arquivo** — medido:
`application/octet-stream`, `content-disposition: attachment; filename="CP2108000003.REM"`.
Não há segunda tela, não há download separado.

O `GET financeiro/mandarsispag.php?file=<id>` existe e funciona, mas o robô só o
usa para **recuperar** de um POST que foi e não devolveu o arquivo.

---

## ⛔ Os dois perigos desta tela

### 1. O mesmo endpoint consulta e age — e o status decide qual

`pagtobmpgrid.php` responde às duas coisas, e a ação que a tela oferece depende
do status filtrado:

| Filtro | Único botão da tela |
|---|---|
| `P` Pendente | `GerarMultipag(this, 1)` → **Gerar** Pagamento BMP Money Plus |
| `G` Gerado | `GerarMultipag(this, 3)` → **Cancelar** Pagamento BMP Money Plus |

Mesmo form `multipagForm`, mesmos campos, **os mesmos títulos na grade**. Só muda
um dígito. Um robô que fosse a "Gerado" atrás do arquivo e submetesse o form
daquela tela **cancelaria os pagamentos**.

Por isso o robô **nunca lê a ação do HTML**: `acao` é `cfg.ACAO_GERAR`, e
`analise.montar_geracao` **recusa a montagem** se a grade não oferecer o botão
"Gerar". A trava vive no módulo puro — logo, tem teste
(`test_grade_de_GERADO_nunca_e_gerada`).

### 2. A separação PIX decide os lotes do CNAB

`checkeds` (não-PIX) e `checkedsPIX` são listas separadas no `GerarMultipag`.
Não é cosmética: medido no arquivo gerado, **lote 0001 forma 41 (TED)** e
**lote 0002 forma 45 (PIX)**. Mandar tudo em `checkeds` sairia como TED — errado,
e em silêncio.

As vírgulas no fim de cada lista (`"143,"`) são fiéis ao `+=` do JS.

---

## Onde ele vive

| Recurso | Valor |
|---|---|
| Onde roda | container `erp-automation`, agendada pelo hub |
| Display / VNC / noVNC / CDP | `:94` / 5905 / 6085 / 9226 |
| Navegador | Google Chrome (canal `chrome`, `/opt/google/chrome`). No host não existe — daí o `SMART_CHROME_CANAL` vazio, que cai no Chromium da `.venv-sandbox` |
| Perfil Chrome | `/app/data/robo_pagamento/perfil_chrome` |
| **Saída dos `.REM`** | `/app/temp/remessas de pagamento` — host: `erp-automation/temp/remessas de pagamento` |
| Controle | `/app/data/robo_pagamento/controle_pagamentos.csv` |
| Credenciais | `/app/config/robo_pagamento.env` (fora do git) |
| Conta | `404` = `mp prospere \| 274 \| 0001 \| 0986952` |
| Log ao vivo | `/app/logs/robo_pagamento_<data>.log` |

> ⚠️ **O caminho de saída tem espaços.** Em shell, sempre `"$PASTA"`. Há
> precedente: o destino do `robo_remessa` é `remessas a enviar`.
>
> ⚠️ **A pasta não está em share nenhum** — nem Nextcloud, nem Samba. De um
> Windows ninguém a enxerga. O `.REM` sobe pro Nextcloud (`_nextcloud.py`,
> `FINANCEIRO/Pagamentos-MoneyPlus/_A_ENVIAR`) logo depois de gerado — é dali
> que o `enviar_pagamento` (process-automation) lê.

---

## Os arquivos

| Arquivo | Papel |
|---|---|
| `robo_pagamento.py` | entrypoint agendado: sessão, rodada, controle, exit codes |
| `gerar.py` | o ciclo (pesquisa → gera → guarda → recupera) |
| `analise.py` | **puro**, só stdlib: leitura de tela e montagem dos POSTs |
| `pagamento_config.py` | tudo por env, sufixo `_PAG` |
| `_nextcloud.py` | sobe o `.REM` gerado pro Nextcloud (wrapper sobre `NextcloudWebDAV`) |
| `run_agendado.sh` | wrapper agendado (host **ou** container), com **trava de sobreposição** |
| `descobrir.py` + `run_descoberta.sh` | Fase 0 — reconferir a tela quando o Smart mudar |

`analise.py` é puro pelo mesmo motivo do `robo_retorno/portao.py`: o container
não tem pytest, o host tem.

---

## Exit codes

| Código | Significado |
|---|---|
| `0` | gerou, ou **não havia pendente** (o caso da maioria das rodadas) |
| `1` / `2` / `3` | sem navegador / sem sessão / Smart mudo |
| `5` | grade recusada (não é a de Pendente, ou sem o botão Gerar) |
| `6` | **o POST foi e o arquivo não está na pasta** — precisa de gente |

O `6` é o que importa: os títulos já saíram da fila, então a próxima rodada dirá
"nada pendente" e ninguém percebe sozinho.

---

## A cadência de 30 minutos

Nenhum outro robô daqui roda assim. Duas consequências:

**Trava de sobreposição** (`run_agendado.sh`, passo 0). O wrapper mata o Chrome
do próprio perfil na largada; sem trava, uma rodada longa seria morta pela
seguinte — possivelmente entre o gerar e o gravar.

| Situação | Saída |
|---|---|
| Rodada em curso há menos de 45 min | `0` — sobreposição é normal, alarme falso diário ensina a ignorar |
| Rodada presa há mais de 45 min | `6` |
| Trava órfã (pid morto) | remove e segue |

**Janela de horário.** O cron não pode ser `*/30 * * * *`: fora da janela do
usuário o `dologin.php` responde `Usuário com acesso restrito`. O cron
registrado é `0,30 8-18 * * 1-5`. Cada rodada custa um CapSolver — medido: a
sessão do Smart não sobrevive ao fechamento do Chrome, então o perfil
persistente não a reusa.

---

## Testes — no host, sem container

```bash
PYTHONPATH=$PWD .venv-sandbox/bin/pytest tests/unit/test_pagamento_analise.py \
    tests/unit/test_pagamento_config.py tests/unit/test_pagamento_trava.py \
    tests/unit/test_pagamento_sandbox.py tests/unit/test_pagamento_robo.py
```

87 testes. Nenhum fala com o Smart: gerar remessa de pagamento move dinheiro e
não entra em teste automático.

- **`analise`** — campo dentro de `<script>` não vira campo; `Acao` no JS *tem*
  de ser achado; a grade de "Gerado" é recusada; separação PIX; layout deduzido,
  não suposto; nome do arquivo não escapa da pasta.
- **`robo`** — os quatro desfechos do ciclo, com `ctx` dublê: nada pendente,
  dry-run, gerou e gravou, e o POST-foi-sem-arquivo.
- **`trava`** — recorta o trecho **real** do `run_agendado.sh` (marcadores
  `>>> TRAVA` / `<<< TRAVA`) e o roda em `dash`, `sh` e `bash`.

Rodar contra o Smart real é pelo sandbox:
[`scripts/sandbox/pagamento.py`](../../../../../scripts/sandbox/pagamento.py) —
`--gerar` (dry) e `--gerar --pra-valer`. Ele chama o **mesmo** `gerar.ciclo()`
que o robô agendado chama.

---

## Parar, se precisar

Qualquer uma das duas basta: refazer o `upsert-docker` da task com
`--disabled`, ou voltar `DRY_RUN_PAG=True` no `.env`.

Receita geral e armadilhas medidas:
[`docs/COMO_SUBIR_UM_ROBO.md`](../../../../../docs/COMO_SUBIR_UM_ROBO.md).
