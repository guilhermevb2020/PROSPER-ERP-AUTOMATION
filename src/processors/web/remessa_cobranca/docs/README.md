# Robô de Remessa CNAB — Smart → disco → Nextcloud

Gera a remessa no Smart Securities, baixa os `.REM` (CNAB-400) e os publica no
Nextcloud do Financeiro, **tudo por HTTP**. Sobe o próprio Chrome só para ter uma
sessão logada: nenhuma etapa depende de clicar em tela.

**O envio ao banco não é deste robô.** Quem sobe o arquivo para a API do BMP é o
job `enviar_remessas`, no `process-automation` — hoje em `modo_teste` e não
agendado.

---

## O ciclo

| Etapa | Endpoint | Observação |
|---|---|---|
| Filtrar | `POST financeiro/confirmardadosremessa.php` | conta + carteira + classes de risco |
| Gerar | `POST` no mesmo endpoint | form inteiro + títulos + `submit_prazo=0` |
| Resultado | `gridremessagerada.php?resultado=<base64>` | `{"idsSucesso": {"<tipo>": <id>}}` |
| Listar | `POST financeiro/downloadremessa.php` | por conta + período |
| Baixar | `GET financeiro/mandarremessa.php?file=<id>` | **sem** `confirmar=1` (ver abaixo) |
| Publicar | `PUT` WebDAV no Nextcloud | `FINANCEIRO/CNAB/Remessas/<ano>/<MM-Mês>/<DD>/<Banco>/` |

Cada geração produz **um arquivo por tipo de ocorrência** — ex.: `01` envio de
cobrança e `02` quitação/cancelamento. Nome: `CB` + `DDMM` + sequencial(7) +
`.REM`. Cada conta tem seu **próprio** número sequencial.

---

## Onde ele vive no servidor

| Recurso | Valor | Por quê |
|---|---|---|
| Display | `:97` | `:96` crédito, `:98` doc2you, `:99` boletos |
| VNC / noVNC | 5903 / 6083 | debug: dá para ver o robô trabalhando |
| CDP | 9224 | 9222 boletos, 9223 doc2you |
| Perfil Chrome | `/app/data/robo_remessa/perfil_chrome` | perfil compartilhado trava no lock |
| Destino 1 — disco | `/app/data/remessas_a_enviar` | fonte de verdade da idempotência |
| Destino 2 — Nextcloud | `FINANCEIRO/CNAB/Remessas/…` | **é onde o Financeiro enxerga** |
| Controle | `/app/data/robo_remessa/controle_remessas.csv` | idempotência (id/arquivo/md5) |
| Credenciais Smart | `/app/config/remessa_cobranca.env` | fora do git |
| Credenciais Nextcloud | `/app/config/nextcloud.env` | usuário `automacao`, fora do git |
| Log ao vivo | `/app/logs/robo_remessa_<data>.log` | além do stdout que o hub captura |

> ### O destino no disco JÁ MUDOU — e a pasta não está em share nenhum
>
> `/app/data/remessas_a_enviar` resolve hoje para
> **`process-automation/tmp/remessas a enviar`** no host, e não para
> `erp-automation/data/`. O bind-mount que este README avisava que entraria em vigor
> "na próxima recriação" entrou: conferido em 17/08/2026, com arquivos de 31/07 a
> 17/08 do lado de lá e só resto velho (31/07 e 03/08) do lado de cá.
>
> ```bash
> docker inspect erp-automation --format \
>   '{{range .Mounts}}{{if eq .Destination "/app/data/remessas_a_enviar"}}{{.Source}}{{end}}{{end}}'
> ```
>
> ⚠️ **Essa pasta não está no Nextcloud nem em share Samba** — os shares expõem só
> os groupfolders do Nextcloud. De um Windows ninguém a enxerga; só quem tem acesso
> ao servidor. Foi exatamente por isso que o envio ao Nextcloud passou a existir.

---

## Uso

```bash
# produção (é o que o hub chama)
sh /app/src/processors/web/remessa_cobranca/run_agendado.sh

# manual, dentro do container
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/remessa_cobranca/gerar_remessa_cobranca.py --contas
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/remessa_cobranca/gerar_remessa_cobranca.py --gerar --conta tigrao
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/remessa_cobranca/gerar_remessa_cobranca.py --listar --conta cast --dias 30

# sobe para o Nextcloud o que JÁ está na pasta local (não abre navegador,
# não fala com o Smart). Serve p/ histórico e p/ tentar de novo o que falhou.
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/remessa_cobranca/gerar_remessa_cobranca.py --subir-pendentes

# quando abrirem/fecharem conta no Smart
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/remessa_cobranca/atualizar_contas.py
```

**`--gerar` é DRY_RUN por padrão.** Sem `--pra-valer` (ou sem
`DRY_RUN_REM=false` no `.env`) ele monta o POST, mostra o que faria e não envia
nada. Gerar **consome sequencial e tira título da fila — não é reversível.**

### Origem das remessas novas do BB — preparação de 09/09/2026

O modo `--bb-api-convenio` usa `bb_geracao.py` para preservar a origem antes do
envio bancário. Exige `--gerar`, `--bb-api-ambiente` e conta/carteira numéricas
exatas. **Só gera com `--pra-valer`**, mesmo se `DRY_RUN_REM=false`. Sem essa
flag, consulta a fila sem gravar intenção nem chamar a geração.

Parâmetros específicos:

- `--bb-api-convenio`: convênio BB com sete posições.
- `--bb-api-ambiente`: `producao` ou `homologacao`, sem padrão implícito.
- `--bb-api-origem`: pasta persistente da caixa de saída; padrão
  `PASTA_REMESSAS/bb_api`. A implantação deve garantir que o consumidor do
  process-automation consiga ler a mesma pasta.

Não combina com `--ids`, `--resultado`, `--da-tela`, `--listar`, `--contas`,
`--todas-contas`, `--forcar`, `--vigiar`, `--subir-pendentes`, `--de` ou `--ate`.
O caminho comum de sessão continua exigindo a trava financeira antes do Chrome.
O wrapper específico `run_bb.sh` liga esses argumentos à conta 395, convênio
3770013, ambiente produção e carteira 17 (`BB_REMESSA_CARTEIRA` aceita 11/17/18).
Sem argumento ou com `--simular`, faz prévia; só `--pra-valer` gera. Usa Chrome
headless e a trava financeira comum, também acrescentada ao wrapper MoneyPlus
antes de tocar no perfil. Ainda sem publicação/agendamento.

O wrapper BB usa explicitamente a caixa compartilhada
`/app/data/retornos_a_processar/bb_api/origens`, montada nos dois containers.

A estrutura é `<pasta>/<ambiente>/<convenio>/<conta Smart>/<UUID>/`:
`intencao.json` precede o POST; `resultado.json` preserva sua resposta;
`<ID>.REM` e `<ID>.json` guardam download e identidade. Após entregar os arquivos
pelo uploader Nextcloud existente, `pronta.json` disponibiliza o lote ao
consumidor. Isso significa origem preparada, não instruções aceitas pelo banco.

As evidências são publicadas completas, com sincronização em disco e sem
sobrescrever versões diferentes. Uma intenção sem resposta bloqueia a próxima
geração nessa conta; não usa o histórico para adivinhar seus IDs. Havendo
resposta salva, retoma apenas os downloads/uploads pendentes, sem novo POST de
geração. Erros parciais do Smart preservam os arquivos, mas impedem publicar o
manifesto. Uma carteira não ultrapassa pendência de outra na mesma conta.

Desde a correção de 10/09/2026, o modo BB também preserva em `resultado.json`
a resposta HTTP integral, URL final e cabeçalhos de conteúdo (sem cookies).
Se a resposta for o próprio CNAB, relaciona seus bytes a um único download da
conta/data da geração. Grava `download_direto.json` com o ID da listagem e o
hash antes de publicar `pronta.json`. Arquivos diferentes ou ambíguos não são
liberados. A retomada revalida a prova salva e não repete o POST.

Remessa BB pode reunir entradas, baixas e alterações no mesmo arquivo. A
conferência da resposta direta compara os controles das entradas (comando 01)
com os checkboxes `tituloN` e os demais controles com o campo `instrucoes` do
POST, conferido também contra o resumo. Os grupos devem corresponder por inteiro,
sem títulos extras ou ausentes; complemento tipo 5 não é outra entrada. Remessas
somente de alterações usam a mesma conferência, sem exigir títulos novos.

Para uma resposta legada truncada, a recuperação é explícita por
`bb_geracao.recuperar_download_direto(robo, ctx, pasta=..., smart_id=...)`, sob a
trava financeira. Exige os 1500 bytes originais, conta, data/hora da geração e
o conjunto completo de títulos selecionados. Mantém o resultado original;
a prova adicional usa `metodo=legado_conferido`. Sem essa conferência, o wrapper
continua bloqueando nova geração. Não serve para importar remessa histórica.

Regressão dessas correções: 75 testes de origem BB, ciclo de remessa e wrapper
aprovados, com Smart e Nextcloud simulados e persistência real em disco.
O leitor também exclui inputs `disabled`, como o FormData do navegador.
Conferência offline em Chrome com o formulário BB real mostrou o robô antigo
enviando `qtdDias=` apesar de os dois campos de prazo estarem desabilitados;
o navegador omite esse campo. O campo ativo, quando existe, é preservado e não
pode ser sobrescrito por outro desabilitado de mesmo nome.

No process-automation, `cnab/bb_origem.py` confere intenção, resposta, IDs,
conta, convênio, carteira, data, hashes e bytes; traduz o lote inteiro antes de
`preparar_origem_bb` chamar o controle persistente de remessas. O consumidor e
o gerador foram ensaiados juntos em processos separados, com HTTP simulado.
Os jobs consumidores de envio/confirmação foram preparados e testados no PA.
Ainda faltam publicação/agendamento e uma geração real nova. A entrega de retorno
com recibos está descrita em [BB_API.md](../../retorno_cobranca/docs/BB_API.md).

Verificação desta alteração: 41 testes de geração e origem BB passaram em
container efêmero; incluem timeout, resposta sem IDs, falha de persistência,
download inválido, upload interrompido e retomada sem nova geração. Ruff E9/F
passou nos arquivos desta alteração. Nenhuma chamada bancária real foi feita
por esse modo nesta validação.

### Códigos de saída

O hub marca a execução pelo exit code.

| Código | Significa |
|---|---|
| 0 | rodada completa |
| 1 | não consegui um navegador |
| 2 | sessão não logada (auto-login falhou) |
| 5 | conta não resolvida / `contas_carteiras.json` sem conta com o prefixo |
| 6 | **rodada incompleta**: abortou por sessão caída, ou alguma conta gerou e não baixou |

O 6 é o que precisa de gente: os títulos já saíram da fila e o arquivo não está
na pasta.

---

## Decisões que não são óbvias

**A sessão expirada se disfarça de "conta sem título".** Quando a sessão morre,
o Smart responde **HTTP 200** com 93 bytes:

```html
<script>top.location.href='.../smart/php/expira.php';</script>
```

Sem `recaptcha`, sem status de erro, e sem a palavra `expirou` — é *"expira"*,
sem o U. Quem não checa isso vê toda tela como vazia, conclui *"essa conta não
tem título"* e a rodada inteira termina dizendo "nenhuma remessa" **sem ter
olhado nada**. É o que `login.parece_deslogado()` existe para impedir, e ela é
usada nos quatro pontos que leem resposta do Smart.

**Remessa gerada que não devolveu os ids não pode virar órfã.** Se o POST foi
(status 200) mas o robô não leu o `resultado`, a remessa **existe** no Smart: o
sequencial foi consumido e os títulos saíram da fila. Tratar como falha faria a
próxima rodada dizer "nada a fazer" e o arquivo nunca sairia. Por isso
`gerar()` devolve `enviado=True` e o ciclo **recupera pela tela de listagem**.
⚠️ A recuperação pega o que apareceu **hoje** naquela conta e não está no
controle — inclusive remessa que uma pessoa gerou à mão de manhã. Fechar isso
exigiria fotografar os ids da conta antes do POST e recuperar só o delta.

**O formulário é lido do HTML, não montado à mão.** A tela muda conforme
conta/banco (protesto, dias, mensagens). Três armadilhas já resolvidas:

1. A página tem **dois forms** — `ConfirmarDadosConta` (certo) e `aux` (tem um
   `contaCorrente2` que não pode ir junto).
2. `Mens01..05` só existem **dentro de `<script>`** — sem remover os scripts,
   entra campo-fantasma no POST.
3. `instrucao` vem de `ckNNI7/8/9`, e no ramo do *negativar* o JS testa se o
   elemento **existe**, não se está marcado. Errar isso grava instrução de
   protesto errada no CNAB.

**Download sem `confirmar=1`.** O link da tela é
`mandarremessa.php?file=<id>&confirmar=1`. Testado: funciona sem o parâmetro e o
arquivo vem byte-idêntico. Como não foi confirmado se `confirmar=1` marca a
remessa como enviada no Smart, o robô não usa.

**O Nextcloud é cópia, nunca substituto.** O `.REM` é gravado no disco primeiro e
só depois sobe (`_nextcloud.py`, por WebDAV, com o cliente compartilhado). Falha no
upload é **aviso**, não falha de rodada: o arquivo já está salvo, o controle já tem
a linha, e `--subir-pendentes` alcança depois. O contrário — subir antes de gravar —
faria uma queda de rede virar arquivo perdido.

**O caminho no Nextcloud sai do ARQUIVO, não do relógio.** Empresa, banco e data de
geração vêm do header do próprio `.REM` (posições 47-76, 77-79 e 95-100), medidas em
17/08/2026 e idênticas às do `.RET`:

```
FINANCEIRO/CNAB/Remessas/<ano>/<MM-Mês>/<DD>/<Banco>/<Empresa> - <arquivo>.REM
```

É a mesma convenção que o `organizar_remessas` (process-automation) já usa em
`FINANCEIRO/CNAB/Retornos` desde 13/08 — inclusive o eixo pela DATA e não pelo
banco, para a pergunta *"saiu tudo hoje?"* se responder abrindo uma pasta só.
Consequência prática: remessa rebaixada dias depois cai na pasta do dia em que foi
**gerada**, e subir duas vezes sobrescreve o mesmo destino em vez de duplicar.

**O `_dup` do disco não sobe.** A pasta local é plana, então quando duas contas geram
o mesmo sequencial no mesmo dia o segundo arquivo é salvo como
`CB<ddmm><seq7>_dup<HHMMSS>.REM` para não sobrescrever o primeiro — e o controle guarda
esse nome, porque é o que está no disco. No Nextcloud o caminho já separa por empresa,
e o nome vai **como o Smart o deu** (`nome_para_nuvem`, nas duas pernas: rodada e
`--subir-pendentes`). Motivo medido em 08/09/2026: a WJ MOREIRA e a MP PROSPERE geraram
`CB08090000011.REM` no mesmo dia; a da WJ subiu como `CB08090000011_dup212306.REM` e o
`enviar_remessa_400` (process-automation), que lê o sequencial dos 7 últimos dígitos do
nome, descartou-a — *"sequencial do nome (1212306) difere do header (0000011)"* — até
alguém renomear à mão. Gate: `tests/integration/test_remessa_cobranca_simulada.py`.

⛔ **O destino é env (`REMESSA_NC_DEST`), nunca fixo no fonte.** Quando essa árvore
mudou em 13/08, caminho embutido em código fez 67 `.RET` sumirem em silêncio
(BUG-566, 282 liquidações, R$ 1.084.030,81). `ENVIAR_NEXTCLOUD_REM=false` desliga o
envio sem tocar em código.

**Validação antes de salvar.** Confere header `01REMESSA` e linhas de 400 chars.
Se a sessão cair, o Smart devolve HTML — o robô descarta em vez de salvar lixo
com nome de `.REM`.

**O login não é reimplementado.** `login.login()` delega para
`boletos._sessao.login_automatico_capsolver`, que já está em produção e resolve
o iframe `loginsec.php`, o acionamento dos `data-callback` do reCAPTCHA e a
seleção de empresa. Como aquele módulo lê credencial de `boletos._config` (que é
env-driven), publicamos as nossas envs **antes** de importá-lo — por isso o
import está dentro da função. Efeito colateral conhecido: screenshot de falha de
login cai em `/app/data/boletos/debug/autologin_*.png`, porque `DEBUG_DIR` é
constante lá.

---

## As duas listas vêm do banco — Fase 3, 22/09/2026 18:31

A lista de exclusão e a de cancelamentos (seções abaixo) continuam sendo escritas pelo
process-automation, mas o ERP as lê de `financeiro.remessa_exclusao_apontada` e
`financeiro.remessa_cancelamento_apontado` (a lista de produção mais recente; `payload` é o
mesmo JSON do arquivo), por `execucao_job.ler_contrato`, com `CONTRATO_FONTE_REM=banco` no
`config/remessa_cobranca.env`. A validade e as mensagens são as de sempre
(`exclusoes.validar`, `cancelar.validar_lista`). Se o banco não responder, a rodada volta ao
JSON do bind e diz no log. Um `--cancelamentos-json` explícito vale sobre a fonte.
Reverter = apagar a linha. Plano: `docs/PLANO_CONTROLE_NO_BANCO.md`.

## A lista de exclusão, a retenção por vencimento e a tela guardada — 17 e 18/09/2026

O MoneyPlus recusa o arquivo INTEIRO por um sacado cujo endereço sai sem número do
pagador (09/09: 166 títulos; 17/09: 175 títulos e R$ 953 mil, com boleto já no sacado).
O process-automation (`apontar_exclusoes_remessa_400`, dia útil 17:30) escreve em
`ARQ_EXCLUSOES` (`/app/data/retornos_a_processar/remessa_cnab_400/exclusoes.json`, o
bind compartilhado) os títulos abertos desses sacados. No `ciclo_conta`, logo depois de
ler o formulário e ANTES de validar, `exclusoes.aplicar` desmarca os títulos casados e
recalcula o resumo; o `RESUMO` da rodada mostra `excluidos=N` por conta.

- **Validade dentro da lista** (`gerado_em` + `validade_horas`): lista velha é ignorada
  com aviso — gerar como sempre é melhor do que gerar com a lista de anteontem.
- **Casamento pela LINHA da grade**, não pelo `value` do checkbox: o value é o id da
  ocorrência no Smart (897629), não o id do título do ERP (934235). `gerar.ler_form`
  devolve `celulas` (os textos da linha) e `colunas` ({cabeçalho: texto}); casa quem tem
  o **documento numa célula exata E o CNPJ do sacado**. ⚠️ A grade real (18/09/2026,
  40 telas) é `| | Instrução | Tipo | Nº | M | Sacado | Vencimento | Valor (R$) | Cedente
  | Operação | Data | Prazo | Juros | Multa |`, e "Sacado" é o CNPJ — sem nome, sem
  nosso número. A versão de 17/09 casava por nome/nosso número/id e não acharia nenhuma
  linha real (nenhum título da lista tinha aparecido ainda).
- **Entrada que vence hoje ou antes fica retida** (só `numBanco` 274, só "Envio de
  cobrança"): o MoneyPlus processa o arquivo no mesmo dia e recusa com 16/92 o vencimento
  que não é posterior. O vencimento vem da coluna "Vencimento" pelo cabeçalho; o dia é o
  de São Paulo (o container roda em UTC). Retido, o título continua na fila do Smart e
  sai na geração seguinte à prorrogação no ERP; a saída da rodada lista cada um
  (`RETIDO NA FILA`). Grade sem cabeçalho legível: nada é retido, com aviso. Caso que
  obrigou: 13274-001 TECNOMIDIA, 18/09/2026.
- **Tela guardada**: `guardar_tela` grava a tela de confirmação de cada conta em
  `DEBUG_DIR` (`form_<conta>_<data>.html`, 7 dias). É a única forma de ver a grade real
  — ela só aparece com título na fila, e a fila esvazia na rodada das 18:00. Serve para
  conferir o casamento e para ler a grade quando o Smart mudar.
- ⚠️ Baixas e alterações vão no campo `instrucoes`, sem mapa para o título: a lista não
  as segura. Conserto é o endereço, no ERP.
- Desde 18/09 a lista também traz o título com **nosso número de outro banco** (mais de 11
  dígitos) — quem decide é o `apontar_exclusoes_remessa_400`; aqui nada mudou, o casamento
  continua documento + CNPJ.

Gates: `tests/integration/test_remessa_cobranca_simulada.py` — lista (exclui e não
posta, exclui um e gera o outro, lista velha/ausente, documento igual de outro sacado,
documento + CNPJ na grade real) e vencimento (retido e o resto sai, tudo retido não gera,
amanhã/outro banco/outra instrução não retêm, grade sem cabeçalho não retém).

## Remessa gerada e não levada deixa rastro — `falhas.py`, 18/09/2026

Em 15/09 o Smart gerou a remessa da MP PROSPERE (id 26381, `CB15090000021.REM`, 60 títulos,
R$ 492.734,47) e o robô a **descartou**: dois registros com 406 bytes, porque os títulos
104-001 e 105-001 da NATURAL FOODS traziam o nosso número de 17 dígitos da BB Ativos num
campo de 11. O Smart já dava os 60 títulos por despachados, o arquivo nunca foi ao banco, e
o rastro era uma linha de log (`DESCARTADO - 2 linha(s) fora dos 400 chars (1a: linha 118)`).

Agora toda geração que o robô **não baixou** (download falho), **descartou** (validação do
CNAB) ou deixou **incerta** (o POST de geração falhou e a listagem não mostrou remessa nova)
grava em `PASTA_FALHAS` (`/app/data/retornos_a_processar/remessa_cnab_400/falhas`, o bind
compartilhado com o process-automation):

- `<id>.json` — conta, rótulo, nome do arquivo, quando, o motivo, os títulos que a geração
  levou (lidos da GRADE, que só descreve entradas; sem grade, do próprio arquivo) e os
  **culpados**: linha, bytes, documento, nosso número, sacado e o porquê
  («nosso numero de 17 digitos … precisa de boleto novo nesta conta»);
- `<id>.REM` — os bytes, quando houve download.

O envio incerto usa o id `incerto-<conta>-<AAAAMMDDhhmmss>`: não há id do Smart para citar.
Corpo que não é CNAB (o Smart devolve HTML quando a sessão cai) não tem culpado nem `.REM`
(`conteudo_cnab: false`): o arquivo no Smart está íntegro e basta baixá-lo de novo. A saída do
`DESCARTADO` passou a nomear o culpado. No fim de cada rodada o robô exporta
`ARQ_REMESSAS_GERADAS` (`remessas_geradas.json`: nome do arquivo no Smart → LISTA de {id,
tipo, md5, bytes, baixado_em}), para quem precisa cancelar a remessa na tela Download de
Remessa saber qual é. ⛔ Lista porque o nome se repete entre contas (18/09/2026:
`CB08090000011` da mp prospere e da mp wj moreira; `CB09090000013` da mp prospere e da mp
relvaplac) — o process-automation escolhe pelo md5 dos bytes que subiram ao banco.
Escrita atômica, arquivos 0644; nada disso levanta — registrar a falha não derruba a rodada.

Quem lê: o vigia do process-automation (`vigiar_boletos_sem_registro`), que investiga todo
dia cada remessa que não chegou ao banco — recusada ou não levada — e diz o que fazer.

Gates: `tests/integration/test_remessa_cobranca_simulada.py` — descartado vira falha com os
culpados e o nome do arquivo, download falho vira falha com os títulos da grade, download que
volta HTML não aponta culpado nem grava `.REM`, o arquivo de baixas não leva os títulos da
grade (e o retido por vencimento fica fora da falha), `exportar_controle` tira o `_dup` do
nome e guarda as duas remessas de mesmo nome.

## Armadilhas de operação

**`--gerar` sem flag, dentro do container, é PRA VALER.** O `remessa_cobranca.env` de
produção tem `DRY_RUN_REM=false` e o módulo o carrega via dotenv, então o padrão
`DRY_RUN=True` do fonte não vale ali. Chamada direta para olhar a fila leva `--simular`,
que força a simulação; `--pra-valer` e `--simular` não convivem. Medido em 08/09/2026:
uma "simulação" sem a flag rodou de verdade e só não gerou porque a fila estava vazia.

**Janela de horário do usuário no Smart.** O Smart só aceita o login dentro do
horário de acesso cadastrado no usuário. Rodando às 18:00, a janela dele tem de
cobrir as 18:00 — senão o `dologin.php` responde `2|Usuário com acesso
restrito.` e o login falha **sem ser culpa do CapSolver**. Foi a causa-raiz de
4 dias de falha do doc2you em julho/2026.

**`contas_carteiras.json` desatualizado.** `--todas-contas` percorre a lista
desse arquivo, não o select ao vivo. Conta nova não entra na rodada e ninguém
avisa. Rode `atualizar_contas.py` quando abrirem ou fecharem conta.

**Feriado.** O robô **não** checa dia útil hoje — o cron `1-5` cobre fim de
semana, mas não feriado. Em feriado ele sobe, gasta um login e não acha título.

**Teste manual sem o wrapper.** Quem sobe o Xvfb `:97` é o `run_agendado.sh`.
Medido em 31/07/2026: sem o display no ar o Chrome **ainda sobe** e o Playwright
devolve um contexto — a falha não aparece na hora, aparece torta depois. Por
isso `_sessao.abrir_propria` avisa quando `/tmp/.X11-unix/X97` não existe. Para
teste avulso, prefira o wrapper ou `HEADLESS_REM=true`.

---

## Estado

**Validado pelo autor em 31/07/2026, no Windows com login manual:** geração
ponta a ponta na conta `mp tigrao` (4 títulos → 2 arquivos, conferidos contra a
listagem do próprio Smart), listagem, download com MD5 idêntico ao manual,
idempotência e validação CNAB.

**Em produção desde 03/08/2026**, `0 18 * * 1-5`. Medido em 17/08: 12 rodadas, 11
com `exit 0` e uma falha (14/08, `exit 2`, auto-login devolveu "Login inválido"); 235
arquivos baixados, 235 linhas no controle. `--todas-contas` e o auto-login por
CapSolver, que este bloco listava como nunca exercitados, rodam **todo dia útil**.

**Envio ao Nextcloud — validado em 17/08/2026**, nas duas pernas:

- upload puro (`--subir-pendentes`): **235 de 235, zero falha**, criando a árvore de
  31/07 a 17/08 — conferido pelo PROPFIND, ou seja, indexado e visível na interface;
- ponta a ponta (`--ids 25831`): login real → download do Smart → validação CNAB →
  disco → Nextcloud, com pasta e controle temporários (produção intocada).

**Nunca exercitado:**

- a **rodada agendada com o envio ligado** — a primeira é 18/08 às 18:00. Não dá para
  ensaiar sem gerar: o wrapper força `--gerar --todas-contas` e o `DRY_RUN_REM=false`
  do `.env` sobrescreve qualquer variável passada por fora;
- contas com protesto/devolução (`ckNNI7/8/9`);
- contas com mensagem para o banco (`imprimeMensagem=1`);
- `idsErro` não-vazio;
- upload de arquivo cujo header não decodifica — o caminho vira `SEM-DATA/Banco ???`
  de propósito (pasta feia é recuperável, arquivo não enviado não), mas nunca aconteceu.

**Desempenho medido no Windows:** ~20s por conta sem títulos, ~45s por conta com
remessa. 51 contas ≈ 18-20 min — daí o timeout de 2700s na task.

**Fonte do controle (Fase 2 de `docs/PLANO_CONTROLE_NO_BANCO.md`):** `CONTROLE_FONTE_REM` = `csv` (padrão: `controle_remessas.csv` e `remessas_geradas.json`) ou `banco` (`erp_automation.vw_controle_remessa`; sem banco, volta aos arquivos avisando). ⛔ Só ligue `banco` depois da carga histórica de 45 dias: `docker exec erp-automation sh -c 'PYTHONPATH=/app python /app/src/processors/db/controle/carregar_remessas_historicas.py'` (ensaio) e depois `--pra-valer`. O CSV e o JSON continuam sendo escritos nos dois modos até o corte.
