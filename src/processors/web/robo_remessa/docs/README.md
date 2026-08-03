# Robô de Remessa CNAB — Smart → arquivo

Gera a remessa no Smart Securities e baixa os `.REM` (CNAB-400), **tudo por
HTTP**. Sobe o próprio Chrome só para ter uma sessão logada: nenhuma etapa
depende de clicar em tela.

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
| Destino dos `.REM` | `/app/data/remessas_a_enviar` | bind-mount → `process-automation/tmp/remessas a enviar` |
| Controle | `/app/data/robo_remessa/controle_remessas.csv` | idempotência (id/arquivo/md5) |
| Credenciais | `/app/config/robo_remessa.env` | fora do git |
| Log ao vivo | `/app/logs/robo_remessa_<data>.log` | além do stdout que o hub captura |

---

## Uso

```bash
# produção (é o que o hub chama)
sh /app/src/processors/web/robo_remessa/run_agendado.sh

# manual, dentro do container
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/robo_remessa/robo_remessa.py --contas
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/robo_remessa/robo_remessa.py --gerar --conta tigrao
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/robo_remessa/robo_remessa.py --listar --conta cast --dias 30

# quando abrirem/fecharem conta no Smart
docker exec -e PYTHONPATH=/app erp-automation \
  python /app/src/processors/web/robo_remessa/atualizar_contas.py
```

**`--gerar` é DRY_RUN por padrão.** Sem `--pra-valer` (ou sem
`DRY_RUN_REM=false` no `.env`) ele monta o POST, mostra o que faria e não envia
nada. Gerar **consome sequencial e tira título da fila — não é reversível.**

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

## Armadilhas de operação

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

**Nunca exercitado (vale para esta porta também):**

- `--todas-contas` no ciclo completo — é justamente o que o agendado faz;
- contas com protesto/devolução (`ckNNI7/8/9`);
- contas com mensagem para o banco (`imprimeMensagem=1`);
- `idsErro` não-vazio;
- o auto-login por CapSolver **neste** usuário e nesta tela.

**Desempenho medido no Windows:** ~20s por conta sem títulos, ~45s por conta com
remessa. 51 contas ≈ 18-20 min — daí o timeout de 2700s na task.
