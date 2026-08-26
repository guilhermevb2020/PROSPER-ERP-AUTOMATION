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

## Estado: registrado no hub, etapa 1 provada de verdade, etapa 2 nunca rodou (26/08/2026)

| | |
|---|---|
| ✅ Contrato de ENVIO medido (`descobrir.py --url`, GET, sem submeter nada) | 26/08 |
| ✅ Ciclo completo testado em DRY_RUN — Nextcloud → Smart (login OK, permissão confirmada) | 26/08 |
| ✅ **Etapa 1 (upload) rodada `--pra-valer` de verdade** — HTTP 200, devolveu a prévia | 26/08 |
| ✅ Task no hub (`robo_retorno_pagamento`, depende de `baixar_retorno_pagamento`, cron `55 8-18 * * 1-5`, **enabled**) | 26/08 |
| ❌ **Etapa 2 (confirmar) nunca rodou de verdade** — código escrito depois de ver a prévia, sem teste real ainda | — |

⚠️ **Rodar agendado hoje é seguro mesmo sem a etapa 2 provada**: `DRY_RUN_RETPAG`
fica `True` por padrão (não existe `config/robo_retorno_pagamento.env` ainda),
então o cron só loga intenção — não faz POST nenhum. Só liga de verdade
mudando essa chave.

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
| Onde roda | container `erp-automation`, agendado pelo hub — task `robo_retorno_pagamento`, `55 8-18 * * 1-5`, depende de `baixar_retorno_pagamento` (status success) |
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
| `robo_retorno_pagamento.py` | entrypoint agendado: sessão, rodada (2 etapas), controle, exit codes |
| `retorno_pagamento.py` | monta o multipart (etapa 1), extrai `target`, confirma (etapa 2) — não classifica resposta |
| `retorno_pagamento_config.py` | tudo por env, sufixo `_RETPAG`, credencial reaproveitada do `robo_pagamento` |
| `_nextcloud.py` | wrapper fino sobre `NextcloudWebDAV` (que ganhou `baixar`/`mover` para este robô) |
| `run_agendado.sh` | wrapper agendado (display + env + python) |

## Como ligar de verdade (falta só isto)

1. Esperar um retorno de pagamento REAL chegar em `_RETORNOS` (via
   `baixar_retorno_pagamento`, automático).
2. Rodar `--pra-valer --limite 1` nesse arquivo, supervisionado — olhar o HTML
   da etapa 2 salvo em `DEBUG_DIR` pra confirmar que o "Continuar" realmente
   dá baixa (é a etapa nunca testada).
3. Só depois disso considerar tirar `DRY_RUN_RETPAG` do padrão `True` — hoje
   ele já está agendado no hub, mas em modo seguro.

## Exit codes

| Código | Significado |
|---|---|
| `0` | rodou limpo (nada pendente, ou tudo terminou em `_PROCESSADOS`) |
| `1` / `2` / `3` | sem navegador / sem sessão / Smart mudo |
| `6` | falha de rede/sessão deixou arquivo pendente para a próxima rodada |
