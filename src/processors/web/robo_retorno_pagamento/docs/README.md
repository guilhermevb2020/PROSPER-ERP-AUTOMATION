# Robô de Retorno de Pagamento (BMP Money Plus)

Insere o retorno CNAB 240 de pagamento no Smart — dá baixa. Sobe o próprio
Chrome só para ter sessão; o trabalho é **um único POST multipart**.

Tela: **Financeiro › Sistemas de pagamento › Pagamento BMP Money Plus ›
Processar Retorno** (`financeiro/pagtobmp/retornopagtobmp.php`).

> ⛔ **Não confundir com o `robo_retorno`.** Aquele é o retorno de **cobrança**
> (`financeiro/retornoocorrencia.php`, CNAB-400, via AJAX). Este é pagamento
> (`financeiro/pagtobmp/retornopagtobmp.php`, CNAB-240, upload de arquivo
> clássico). Cobrança recebe dinheiro; pagamento manda.

**O robô INSERE — não julga o resultado.** Decisão do dono, 26/08/2026:
ninguém revisa fila de resultado incerto, então o robô não cria uma. Uma vez
que o POST chegou ao servidor e teve resposta, o arquivo sai da entrada e
nunca é reenviado — não importa o que o Smart tenha respondido.

---

## Estado: construído, `--pra-valer` real ainda não rodado (26/08/2026)

| | |
|---|---|
| ✅ Contrato de ENVIO medido (`descobrir.py --url`, GET, sem submeter nada) | 26/08 |
| ✅ Ciclo completo testado em DRY_RUN — Nextcloud → Smart (login OK, permissão confirmada) | 26/08 |
| ❌ `--pra-valer` rodado de verdade | — |
| ❌ Task no hub | não registrada ainda |

## O ciclo — um único POST, e acabou

| # | O quê | Como |
|---|---|---|
| 1 | Lista `.RET` pendentes | `NextcloudWebDAV.listar_nomes` em `_RETORNOS` |
| 2 | Baixa o arquivo | `NextcloudWebDAV.baixar` |
| 3 | Sobe no Smart | `POST retornopagtobmp.php`, multipart, campo `avatar_file` |
| 4 | Move para `_PROCESSADOS` | sempre que o POST teve resposta do servidor |

O form (`retornoSispag`) tem 4 campos — medidos em 26/08/2026:

```
MAX_FILE_SIZE = "15728640"   (hidden)
form_submit   = "1"          (hidden)
origem        = ""           (hidden — SEMPRE vazio, sem JS que o preencha)
avatar_file   = <o .RET>     (file)
```

## O que É seguro reenviar, e o que NÃO é

| Situação | O que o robô faz |
|---|---|
| Falha de rede (POST nem saiu) | Fica na entrada — tenta de novo |
| Sessão caiu NO MEIO do upload | Fica na entrada — não dá para saber se chegou a sair |
| Chegou QUALQUER resposta do servidor | Sai da entrada, grava no controle — **nunca reenviado** |

A regra de ouro: **uma vez que o servidor respondeu, o upload já aconteceu** —
reenviar um arquivo que o Smart já viu do lado dele é processar duas vezes,
não corrigir um erro. A resposta crua ainda é salva em `DEBUG_DIR` (evidência,
não fila de rotina).

---

## Onde ele vive

| Recurso | Valor |
|---|---|
| Onde roda | container `erp-automation`, agendado pelo hub (quando registrado) |
| Display / VNC / noVNC / CDP | `:93` / 5906 / 6086 / 9227 |
| Perfil Chrome | `/app/data/robo_retorno_pagamento/perfil_chrome` |
| Credenciais | `config/robo_pagamento.env` (MESMA conta do robô de geração — mesma tela, mesmo módulo) |
| Entrada (Nextcloud) | `FINANCEIRO/Pagamentos-MoneyPlus/_RETORNOS` |
| Saída (Nextcloud) | `.../_RETORNOS/_PROCESSADOS` |
| Controle | `/app/data/robo_retorno_pagamento/controle.csv` |
| Debug (HTML de resposta) | `/app/data/robo_retorno_pagamento/debug/` |

## Os arquivos

| Arquivo | Papel |
|---|---|
| `robo_retorno_pagamento.py` | entrypoint agendado: sessão, rodada, controle, exit codes |
| `retorno_pagamento.py` | monta o multipart e envia — não classifica resposta |
| `retorno_pagamento_config.py` | tudo por env, sufixo `_RETPAG`, credencial reaproveitada do `robo_pagamento` |
| `_nextcloud.py` | wrapper fino sobre `NextcloudWebDAV` (que ganhou `baixar`/`mover` para este robô) |
| `run_agendado.sh` | wrapper agendado (display + env + python) |

## Como ligar

1. `--listar` para conferir que enxerga a fila.
2. Rodar sem `--pra-valer` (dry-run) e conferir o log.
3. Rodar `--pra-valer --limite 1` em um arquivo, e olhar o HTML salvo em
   `DEBUG_DIR` se quiser ver o que a tela devolveu.
4. Registrar a task no hub.

## Exit codes

| Código | Significado |
|---|---|
| `0` | rodou limpo (nada pendente, ou tudo terminou em `_PROCESSADOS`) |
| `1` / `2` / `3` | sem navegador / sem sessão / Smart mudo |
| `6` | falha de rede/sessão deixou arquivo pendente para a próxima rodada |
