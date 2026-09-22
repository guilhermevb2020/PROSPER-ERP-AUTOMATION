# Robô de Retorno de Pagamento (BMP Money Plus)

Insere o retorno CNAB 240 de pagamento no Smart — dá baixa. Sobe o próprio
Chrome só para ter sessão; o trabalho é **duas etapas de POST** (upload +
confirmar).

Tela: **Financeiro › Sistemas de pagamento › Pagamento BMP Money Plus ›
Processar Retorno** (`financeiro/pagtobmp/retornopagtobmp.php`).

> ⛔ **Não confundir com o `robo_retorno`.** Aquele é o retorno de **cobrança**
> (`financeiro/retornoocorrencia.php`, CNAB-400, via AJAX). Este é pagamento
> (`financeiro/pagtobmp/retornopagtobmp.php`, CNAB-240, upload de arquivo
> clássico em 2 etapas). Cobrança recebe dinheiro; pagamento manda.

**O robô INSERE — não julga o resultado.** Decisão do dono, 26/08/2026:
ninguém revisa fila de resultado incerto, então o robô não cria uma. Uma vez
que a etapa 2 (confirmação) chegou ao servidor e teve resposta, o arquivo sai
da entrada e nunca é reenviado — não importa o que o Smart tenha respondido.

---

## Estado: EM PRODUÇÃO DE VERDADE — as duas etapas provadas (26/08/2026)

| | |
|---|---|
| ✅ Contrato de ENVIO medido (`descobrir.py --url`, GET, sem submeter nada) | 26/08 |
| ✅ Ciclo completo testado em DRY_RUN — Nextcloud → Smart (login OK, permissão confirmada) | 26/08 |
| ✅ Etapa 1 (upload) rodada `--pra-valer` de verdade — HTTP 200, devolveu a prévia | 26/08 |
| ✅ **Etapa 2 (confirmar) rodada `--pra-valer` de verdade, 5 arquivos** — HTTP 200 nas duas etapas, nos 5 | 26/08, 21:29 |
| ✅ Task no hub (`processar_retorno_pagamento_cnab_240` — renomeada, era `retorno_pagamento`; depende de `receber_retorno_pagamento_cnab_240`, cron `55 8-18 * * 1-5`, **enabled**) | 26/08 |
| ✅ **`DRY_RUN_RETPAG=false` persistido em `config/retorno_pagamento.env`** — próximas rodadas agendadas dão baixa de verdade | 26/08, 18:44 |

### Como a etapa 2 foi validada, já que a resposta HTML não distingue sucesso de erro

O robô **insere, não julga** — a resposta da etapa 2 é sempre a mesma casca de
página (`title` = "Processar Retorno"), byte-a-byte quase idêntica entre um
arquivo e outro. **Não confie em grep por "sucesso"/"erro" no HTML** — essas
palavras aparecem em JavaScript de template (`if(sucesso){...}`), não como
mensagem de resultado.

O sinal real está no `window.open('popuppagtobmp.php?...&entrej=N&liquid=N...')`
embutido na resposta — um contador por tipo de ação. Nos 5 arquivos de
26/08/2026, `liquid=N` bateu **exatamente** com o nº de pagamentos código-00
de cada remessa (2, 1, 4), e o único rejeitado pelo BMP (ANFEER, código 55)
caiu em `entrej=1` em vez de `liquid` — o Smart tratou o caso corretamente.
Não é confirmação 100% (não há acesso direto ao banco do Smart), mas é o sinal
mais forte disponível sem entrar na tela.

```bash
# extrair o contador de uma resposta salva em DEBUG_DIR
grep -oE "popuppagtobmp.php\?[^']*" /app/data/robo_retorno_pagamento/debug/<arquivo>.etapa2_confirmado.html
```

## Por que a etapa 2 existe — descoberta em 26/08/2026

O upload (etapa 1) **não efetiva nada**: o Smart parseia o `.RET`, casa com os
títulos que reconhece e devolve uma PRÉVIA — um novo `retornoSispag` (mesmo
nome, campos diferentes: sem arquivo, com um `target` oculto apontando pro
`.txt` que o Smart deixou staged no servidor) e um botão "Continuar" que
resubmete esse form. Medido com um arquivo de teste SINTÉTICO (sem título real
casando — `seu_numero` fabricado por mim numa sessão anterior, não uma remessa
real do Smart): a prévia veio com as colunas de Título vazias e as do arquivo
preenchidas (`Ação tomada: Pagamento rejeitado`, `Status: Código do Banco
Favorecido... Inválido` — batendo com o que `financeiro.cnab240_pagamento` já
tinha decodificado, boa validação cruzada). **Não cliquei "Continuar"** — meu
teste não tinha título real casando, então o efeito de confirmar era
desconhecido; parei ali por cautela. O código da etapa 2 (`ret.confirmar`) foi
escrito DEPOIS, a partir do HTML da prévia, mas nunca rodou contra o Smart.

**Não repita esse teste no arquivo sintético para validar a etapa 2** — ele já
foi consumido (está em `_PROCESSADOS`) e não tem título real para provar nada
novo. O teste que falta é com um retorno de um pagamento REAL (gerado pelo
`robo_pagamento`, não por script de teste).

## O ciclo — duas etapas

| # | O quê | Como |
|---|---|---|
| 1 | Lista `.RET` pendentes | `NextcloudWebDAV.listar_nomes` em `_RETORNOS` |
| 2 | Baixa o arquivo | `NextcloudWebDAV.baixar` |
| 3 | Etapa 1 — upload | `POST retornopagtobmp.php`, multipart, campo `avatar_file` → devolve prévia com `target` |
| 4 | Etapa 2 — confirmar | `POST retornopagtobmp.php`, urlencoded, `origem`+`target` → efetiva de verdade |
| 5 | Move para `_PROCESSADOS` | sempre que a etapa 2 teve resposta do servidor |

Campos da etapa 1 (form `retornoSispag`, `enctype=multipart/form-data`) — medidos em 26/08/2026:

```
MAX_FILE_SIZE = "15728640"   (hidden)
form_submit   = "1"          (hidden)
origem        = ""           (hidden — SEMPRE vazio, sem JS que o preencha)
avatar_file   = <o .RET>     (file)
```

Campos da etapa 2 (a PRÉVIA devolve um `retornoSispag` DIFERENTE — sem
`enctype`, ou seja, POST urlencoded comum, não multipart):

```
origem = ""                                            (hidden)
target = "/var/app/current/.../retorno/RET....txt"      (hidden — o staged do Smart)
```

## O que É seguro reenviar, e o que NÃO é

| Situação | O que o robô faz |
|---|---|
| Falha de rede na etapa 1 ou 2 | Fica na entrada — tenta de novo (reenviar a etapa 1 é inofensivo, só re-stagea) |
| Sessão caiu em qualquer etapa | Fica na entrada — não dá para saber se chegou a efetivar |
| Etapa 2 teve resposta do servidor | Sai da entrada, grava no controle — **nunca reenviado** |

A regra de ouro: **uma vez que a etapa 2 respondeu, a inserção já aconteceu** —
reenviar é processar duas vezes, não corrigir um erro. As respostas cruas de
AMBAS as etapas são salvas em `DEBUG_DIR` (evidência, não fila de rotina).

---

## Onde ele vive

| Recurso | Valor |
|---|---|
| Onde roda | container `erp-automation`, agendado pelo hub — task `retorno_pagamento`, `55 8-18 * * 1-5`, depende de `baixar_retorno_pagamento` (status success) |
| Display / VNC / noVNC / CDP | `:93` / 5906 / 6086 / 9227 |
| Perfil Chrome | `/app/data/robo_retorno_pagamento/perfil_chrome` |
| Credenciais | `config/robo_pagamento.env` (MESMA conta do robô de geração — mesma tela, mesmo módulo) |
| Entrada (Nextcloud) | `FINANCEIRO/Pagamentos-MoneyPlus/_RETORNOS` |
| Saída (Nextcloud) | `.../_RETORNOS/_PROCESSADOS` |
| Controle | `/app/data/robo_retorno_pagamento/controle.csv` |
| Debug (HTML de resposta, das duas etapas) | `/app/data/robo_retorno_pagamento/debug/` |

## Os arquivos

| Arquivo | Papel |
|---|---|
| `processar_retorno_pagamento.py` | entrypoint agendado: sessão, rodada (2 etapas), controle, exit codes |
| `retorno_pagamento.py` | monta o multipart (etapa 1), extrai `target`, confirma (etapa 2) — não classifica resposta |
| `retorno_pagamento_config.py` | tudo por env, sufixo `_RETPAG`, credencial reaproveitada do `robo_pagamento` |
| `_nextcloud.py` | wrapper fino sobre `NextcloudWebDAV` (que ganhou `baixar`/`mover` para este robô) |
| `run_agendado.sh` | wrapper agendado (display + env + python) |

## ✅ Como foi ligado de verdade (feito em 26/08/2026)

1. Esperou 5 retornos de pagamento REAIS chegarem em `_RETORNOS` (via
   `receber_retorno_pagamento_cnab_240`, automático).
2. Rodou `--pra-valer` (sem `--limite`, os 5 pendentes) supervisionado, via
   `run_agendado.sh` — todos HTTP 200 nas duas etapas; conferido o HTML da
   etapa 2 salvo em `DEBUG_DIR` (o contador `liquid=N`, ver seção acima).
3. Criado `config/retorno_pagamento.env` com `DRY_RUN_RETPAG=false` —
   tirou o robô do padrão seguro. Confirmado o valor efetivo dentro do
   container antes de considerar feito.

⭐ **Próxima pessoa que mexer aqui:** o robô agora dá baixa de verdade a cada
hora (`55 8-18 * * 1-5`), sem fila de revisão. Ver a seção
["O robô INSERE — não julga o resultado"](#robô-de-retorno-de-pagamento-bmp-money-plus)
no topo antes de mudar qualquer coisa no fluxo das duas etapas.

## Exit codes

| Código | Significado |
|---|---|
| `0` | rodou limpo (nada pendente, ou tudo terminou em `_PROCESSADOS`) |
| `1` / `2` / `3` | sem navegador / sem sessão / Smart mudo |
| `6` | falha de rede/sessão deixou arquivo pendente para a próxima rodada |
