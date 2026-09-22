# O que falta na automação de pagamento — e por que ficou faltando

Escrito em 21/08/2026, **atualizado em 26/08/2026**. Três dos quatro itens
originais já foram resolvidos. Falta só o item 4, que é decisão do dono, não
código — **apague este arquivo quando ele for respondido**.

## ✅ Resolvido (25-26/08/2026)

1. **Task no hub** — registrada e habilitada: `gerar_remessa_pagamento_bmp`
   (`erp-automation`, cron `0,30 8-18 * * 1-5`), com `enviar_pagamento`
   (process-automation) dependendo dela (status `success`).
2. **As duas chaves de geração** — ligadas: `DRY_RUN_PAG=False` e
   `PRA_VALER_PAG=--pra-valer` em `config/robo_pagamento.env`, confirmado
   em 25/08/2026. Fluxo real testado, dinheiro se moveu (confirmado pelo
   dono).
3. **Commit** — feito. `git log` deste projeto tem os commits de 25 e
   26/08/2026 sobre `robo_pagamento/`, `retorno_pagamento/` e
   `src/common/clients/nextcloud_webdav.py`.

## ⛔ Ainda aberto — item 4, é decisão de dono

**Quem mais mexe na conta 404?** Entre duas leituras de 21/08 apareceu um
`file=23` que não foi a automação. Uma automação de 30 em 30 minutos gera
**todos** os pendentes — se alguém estiver marcando títulos à mão, os dois vão
brigar: a pessoa perde os títulos que ia selecionar, e eles saem numa remessa
que ela não pediu.

Não tem solução técnica boa (filtrar por operação? por valor?) sem saber qual
é o combinado. Ninguém respondeu isso ainda — segue em aberto.
