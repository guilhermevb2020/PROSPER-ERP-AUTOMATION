# -*- coding: utf-8 -*-
"""
Ambiente de TESTE dos robos, rodando no HOST — sem Docker.

POR QUE EXISTE
--------------
A conta de desenvolvimento (`operacional2`) nao tem acesso ao Docker, e por
desenho: o grupo `docker` e root sem senha (`docker run -v /:/host` le o
`shared.env` inteiro). Sem `docker exec` nao havia como RODAR um robo antes de
ele ir para producao — so ler codigo e torcer. O bind-mount de `src/` piora
isso: salvar publica na hora, entao o primeiro teste de um robo novo era
direto no cron.

Este pacote fecha esse buraco pelo unico caminho que sobra: subir o Chrome
AQUI, no host, sob a nossa conta. Provado em 21/08/2026 — Playwright + Chromium
rodam no host e o host alcanca o Smart (HTTP 200 em smartsecurities.com.br).

O QUE ELE NAO E
---------------
Nao e um segundo robo, nem uma copia. Ele IMPORTA os modulos de producao
(`_emissao_core`, `_sessao`, `emissao_evidencia`) e roda O MESMO codigo que o
container roda. Testar aqui e testar o que vai para producao — muda so onde o
Chrome sobe e de onde vem a credencial.

AS TRES DIFERENCAS EM RELACAO AO CONTAINER
------------------------------------------
1. Chrome no host, perfil proprio em `data/sandbox/perfil_chrome` — NUNCA o
   perfil dos boletos (`data/boletos/perfil_chrome`), que o container usa. Dois
   Chromes no mesmo perfil travam no lock.
2. Credencial de `config/sandbox.env` (600, fora do git), nao do `boletos.env`
   do container. Assim o sandbox pode usar ate um usuario Smart de teste.
3. `BOLETO_DATA_DIR` aponta para o `data/` do host, para o `_config` dos
   boletos nao tentar criar `/app/...`, que nao existe aqui.

⚠️ A sessao do sandbox e uma sessao a MAIS da mesma conta no Smart. Se usar a
mesma conta dos robos, vale o que ja se mediu: sessoes simultaneas convivem,
mas um login novo pode derrubar a sessao de outro robo (custa um CapSolver, nao
resultado). Um usuario Smart proprio para o sandbox evita isso.
"""
