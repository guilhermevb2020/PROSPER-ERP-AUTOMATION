# Sessões do Smart entre rodadas — o que se mede hoje e o que dá para reaproveitar

Estudo de 22/09/2026, a pedido da Gerência ("mais algumas sessões poderiam ser reaproveitadas;
entenda melhor"). Tudo abaixo foi medido nos logs de `logs/`, no hub e no banco de hoje; o que
é hipótese está marcado como hipótese. Nada foi alterado em produção para medir — a única
intervenção foi um ping **sem login** no perfil do finalizador depois de duas rodadas (§4, F5).

## 1. Três desenhos de login convivem no container

| desenho | quem usa | como fica a sessão |
|---|---|---|
| **mantenedor 24/7 + CDP** (`boletos/manter_sessao`, display `:99`, CDP 9222) | emissão, envio e healthcheck de boletos anexam por `connect_over_cdp` | 1 login por dia + relogins do healthcheck quando a sessão cai (14 dias: 1 a 7 por dia) |
| **self-contained com perfil persistente** (`src/common/clients/smart_sessao.sessao`) | remessa e retorno de cobrança, BB, depósito, cancelamento, pagamento, retorno de pagamento, finalizador | cada rodada sobe o Chrome do job, **pinga**; se o cookie do perfil ainda vale, segue sem login; senão CapSolver (~53 s) e fecha |
| **sessão longa do dia** (`credito/`) | análise de crédito, 07:45 → fim do expediente | 1 login + relogin sempre que é derrubada |

O cliente comum **já reaproveita a sessão quando ela sobrevive**: `smart_sessao.login()` pinga
antes e loga só se a resposta disser "deslogado" (`sessao ja valida -> sem novo login`). A
pergunta certa, portanto, não é "como reaproveitar" e sim **"para quem a sessão não sobrevive
entre rodadas, e por quê"**.

## 2. Medido em 22/09 (até 14:20)

| job | identidade | cadência no hub | rodadas | logins CapSolver | rodadas sem login | custo de cada login |
|---|---|---|---|---|---|---|
| finalizar operação (DRY) | `operacional2@` (GSMARTPWD3) | `*/15 8-18` (44/dia) | 28 | **28 (100 %)** | 0 | mediana **53 s** (40–98); 26 min até 14 h ≈ **39 min/dia** |
| gerar remessa de pagamento | `prosperito_financeiro@` (GSMARTPWD2) | 5 em 5 min, 8–18 (132/dia) | 67 | 1 (08:00) | 66 | rodada inteira: **2 s** |
| retorno de pagamento | idem | 5 em 5 min (132/dia) | 68 | 1 (08:03) | 64 | 1 s |
| remessa de cobrança / cancelamento | `prosperito@` (GSMARTPWD1) | 11:30, 17:10, 18:00, 18:30 | 3 | 2 (09:27 manual, 11:29) | 1 | 40–68 s |
| retorno de cobrança CNAB | `prosperito@` | `50 8-18` (11/dia) | 3 | 0 | 3 | — |
| retorno BB | `prosperito@` | 5 em 5 min, 7–17 e 19 h (~130/dia) | 22 desde 12 h | não conferido (saída só no hub); o código abre a sessão em toda rodada | — | rodada 1m17–2m43 |
| análise de crédito | `prosperito@` | sessão do dia | 1 | **3** (07:45 + 2 relogins) | 360 pings ok | — |
| boletos (mantenedor) | `prosperito@` | 24/7 | — | 1 (07:19) + **2 relogins** do healthcheck (09:45, 12:01) | — | — |
| doc2you | `prosperito@` | 07:30 (+19:00) | 1 | 1 | — | — |

Somando o dia inteiro: **~45 logins CapSolver/dia, dos quais 44 são do finalizador** — três
quartos do total, num robô que hoje está em DRY (confere e não clica).

## 3. Quanto custa um login

- **Tempo:** 53 s de mediana no finalizador (a rodada dele leva 1m17–2m43; metade é login).
  O `ACHADO-124` já media isso no retorno CNAB: login de 36 s para um lote de 37 s.
- **CapSolver:** um desafio por login (o solver tem direito a um segundo, no mesmo prazo).
- **Risco:** cada login é uma chance de falhar — janela de horário da conta (`PROC-015`),
  `ERROR_CAPTCHA_SOLVE_FAILED` (07/09 18:13), aviso de segurança — e, para `prosperito@`,
  um login novo **derruba outra sessão da mesma identidade** (§4, F4): o custo real não é o
  login que se faz, é a cascata que ele dispara.

## 4. O que o Smart faz com as sessões — fatos e hipóteses

- **F1 — o cookie sobrevive ao fechar o Chrome.** `PHPSESSID` é cookie de sessão (sem
  validade; `is_persistent=0` em todos os perfis), mas o perfil persistente do Playwright o
  devolve na rodada seguinte: é por isso que pagamento e retorno de pagamento rodam 131 de
  133 rodadas sem login. Reaproveitar entre rodadas **já funciona** onde a sessão não morre.
- **F2 — tempo ocioso tolerado ≥ 33 min** (para `prosperito_financeiro@`): a sessão do
  pagamento sobreviveu a intervalos de 25 min (hoje 11:50) e 33 min (ontem 23:36). Não há
  medida direta para `prosperito@` nem para `operacional2@`.
- **F3 — sessões da mesma identidade convivem.** Pagamento logou 08:00, retorno de pagamento
  logou 08:03 (perfil e cookie próprios), e às 08:05 a sessão do pagamento seguia válida.
  `prosperito@` teve mantenedor, crédito e retorno BB vivos ao mesmo tempo o dia inteiro.
  Logo **não é "uma sessão por identidade"** no sentido estrito.
- **F4 — mas login NOVO de `prosperito@` coincide com quedas, 3 de 3 hoje:**

  | login novo (navegador novo) | quem caiu | quando |
  |---|---|---|
  | crédito 07:45 | mantenedor (`keepalive: logado=False`) | 07:45:55 |
  | cancelamento manual 09:27–09:28 | crédito relogou (ciclo 111 ≈ 09:4x); mantenedor | 09:36:12 |
  | cancelamento 11:29 | crédito relogou (ciclo 219 ≈ 11:3x); mantenedor | entre 11:17 e 12:01 (healthcheck "busy" no meio) |

  Relogins **no mesmo navegador** (healthcheck via CDP às 09:45 e 12:01; emissão às 08:01)
  não derrubaram ninguém. **Hipótese:** um login a partir de um navegador novo (cookie/device
  novo) evicta uma sessão antiga da mesma identidade — provavelmente a mais velha — e o
  relogin dentro de um navegador já conhecido não. A regra exata não está provada, e há outra
  causa além dos logins: o healthcheck reloga 1–3 vezes por dia também aos sábados e domingos,
  quando nenhum outro robô de `prosperito@` roda.
- **F5 — a sessão do finalizador morre no fim da própria rodada, não por ociosidade.** Ping
  sem login no perfil dele, depois das rodadas das 14:30 e 14:45:

  | depois do fim da rodada | resultado |
  |---|---|
  | 10 s | deslogado |
  | 90 s | deslogado |
  | 3 min | deslogado |
  | 9 min | deslogado |

  Os oito perfis registram o último fechamento do Chrome do mesmo jeito, e é isso que faz o
  navegador devolver a sessão ao reabrir: esse lado é igual para todos, e no financeiro a
  sessão volta viva. A diferença está no servidor ou no que a rodada faz antes de fechar; o
  mecanismo **não foi isolado**. Hipóteses, nenhuma provada: a identidade `operacional2@` tem
  regra de sessão própria no Smart (ela já tem janela de horário, `PROC-015`, e é a única com o
  modal de segurança em todo login, F6); ou a rodada encerra a sessão ao sair das telas do Smart
  (`about:blank` antes de fechar a página da grade).
- **F6 — o modal "Procedimento de segurança"** aparece em todo login do finalizador (29/29) e
  nos do financeiro (2/2), e em nenhum dos de `prosperito@`. Não é o mecanismo de derrubada
  (o financeiro convive depois dele); parece aviso por dispositivo/conta.

## 5. Defeitos encontrados no caminho (no mantenedor dos boletos)

- **D1 — o keepalive travou em silêncio às 10:11** e às 15:04 seguia travado: cinco timeouts de 30 s
  durante o envio das 10:00, depois nenhuma linha no log (o loop imprime a cada 120 s). O
  processo está vivo e o CDP responde, então o healthcheck (que só reinicia quando o CDP cai)
  o dá por saudável. A sessão só continua viva pelos pings do próprio healthcheck a cada
  15 min — e quando ele se declara "busy" (11:30 e 11:45) fica 43 min sem ping. Falta um
  watchdog pela idade do log.
- **D2 — o log do mantenedor expõe o `PHPSESSID`** em 8 linhas: a exceção do Playwright é
  impressa inteira (`keepalive falhou: {e}`) e traz os cabeçalhos da requisição, cookie
  incluído. É token de sessão vivo em arquivo legível pelo grupo. `smart_sessao.sessao_viva`
  já imprime só o tipo da exceção pelo mesmo motivo; `manter_sessao_viva` não.
  ✅ **Corrigido em `95e1e11`:** os sete `print` do módulo passam por `_resumo_excecao` (tipo
  e primeira linha, cortada antes de qualquer cabeçalho de cookie), com gate de fonte em
  `tests/unit/test_sessao_log_sem_cookie.py`; as 8 linhas de hoje foram redigidas no próprio
  arquivo. O healthcheck pega a correção na próxima rodada; o mantenedor em execução, só no
  próximo reinício (janela 19:05–07:30).

## 6. Opções

- **A. Mantenedor por identidade + anexar por CDP** (o desenho dos boletos) **para o
  finalizador.** Display `:92` e CDP 9225 já são dele; `finalizar_operacao.py` já aceita
  `--cdp`; `smart_sessao.sessao(usar_cdp=True)` já anexa e reloga no lugar se a sessão
  cair. Ganho medido: **−44 logins/dia, −39 min/dia, −44 desafios CapSolver/dia**, rodada de
  ~1m35 para ~45 s. Custo: um Chrome a mais 24/7 (1,3–1,5 GB; o container usa 3,1 GiB de
  251), um mantenedor **genérico** em `src/common/clients/` (hoje `manter_sessao_viva` é dos
  boletos e lê `boletos._config`), o boot em `scripts/boot_vnc.sh` e o comando da task com
  `--cdp`. Conflito conhecido: o sandbox usa a mesma identidade — já é regra não rodar os dois
  juntos; com CDP, se o sandbox derrubar a sessão, a rodada seguinte reloga no lugar.
  ⚠️ **Por F5, o ganho não está garantido:** se é a própria rodada que encerra a sessão, um
  Chrome mantido aberto relogaria toda rodada do mesmo jeito. Antes de construir qualquer
  mantenedor: uma rodada supervisionada com `--cdp` num Chrome deixado aberto no `:92`, e um
  ping um minuto depois. Sessão viva, A vale; morta, o problema é a identidade ou a rodada, e
  A não resolve. Desde 14:36 de 22/09 outra frente está editando os arquivos do finalizador
  (`finalizar_operacao.py`, `r7_config.py`, `finalizar.py`): o teste e qualquer mudança são
  dela, ou combinados com ela.
- **B. Família de cobrança anexada ao mantenedor dos boletos** (CDP 9222) em vez de Chrome
  próprio. Remessa, retorno CNAB, BB, depósito e cancelamento são **só HTTP** (0 `new_page`,
  `goto` ou `click` fora do login) e levam conta e carteira explícitas em cada POST
  (`gerar.py` `contaCorrente`/`NumCarteira`, `retorno.py` `numConta`); a única escolha por
  sessão é a empresa, feita no login e a mesma para todos. Ganho: −3 a −6 logins/dia e, o
  que importa, **fim da cascata de F4** (cancelamento → crédito reloga → mantenedor cai →
  healthcheck reloga = 3 CapSolver e janelas em que emissão/envio falham). Cautela: sessão
  compartilhada com emissão/envio (que mexem em DOM) — a trava por conta já serializa a
  família, e o healthcheck já reconhece "em andamento"; precisa de ensaio antes.
- **C. Crédito:** fica como está; com B deixa de ser derrubado (se F4 valer).
- **D. Financeiro** (pagamento e retorno de pagamento): já reaproveita; nada a fazer.
- **E. Cadência do finalizador em DRY:** 44 conferências por dia sem clique é decisão de
  operação, não técnica; não muda o desenho.

## 7. Recomendação e ordem

1. **F5 está meio fechado:** a sessão morre no fim da rodada (medido); o porquê falta. O
   próximo passo é o teste supervisionado com `--cdp` descrito em A, na frente que está
   editando o finalizador, mais a pergunta ao fornecedor abaixo. F4 pede um dia de observação
   com a saída do hub (quem logou, quem caiu, em que ordem).
2. **A (finalizador)**, se o teste de `--cdp` mostrar a sessão viva entre rodadas: maior
   ganho, identidade isolada, peças já existentes. Gate: uma semana de `--cdp` com zero login
   por rodada no log e o healthcheck do `:92` relatando.
3. **D1 e D2 no mantenedor** — watchdog pela idade do log (o healthcheck reinicia se o log
   parar por > 10 min) e exceção impressa só pelo tipo; limpar as 8 linhas de hoje. Entra na
   janela 19:05–07:30, porque reiniciar o mantenedor derruba a sessão dos boletos.
4. **B** depois de A, atrás de ensaio.

## 8. Perguntas para a Gerência (fecham F3/F4 e F5)

- O Smart tem **limite de sessões simultâneas por usuário** configurável? Isso explicaria por
  que `prosperito_financeiro@` convive e `prosperito@` derruba.
- `operacional2@` tem **regra de sessão própria** (como tem janela de horário), por exemplo
  sessão encerrada ao fechar a janela, ou um login só por vez? Isso explicaria F5 sem precisar
  de mais experimento.
