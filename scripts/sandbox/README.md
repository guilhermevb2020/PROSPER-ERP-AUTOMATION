# Sandbox — rodar os robôs no host, sem Docker

Ambiente para **testar um robô contra o Smart real antes de subir para
produção**, rodando o Chrome aqui no host. Existe porque a conta de
desenvolvimento não tem acesso ao Docker (e não vai ter: o grupo `docker` é root
sem senha) e `src/` é bind-mount — sem isto, o primeiro teste de um robô é
direto no cron.

**Não é uma cópia dos robôs.** Ele importa os módulos de produção
(`_emissao_core`, `_sessao`, `emissao_evidencia`) e roda o mesmo código. Testar
aqui é testar o que vai para produção.

## O que já foi provado (21/08/2026)

- Playwright + Chromium rodam no host, como `operacional2`, sem Docker.
- O host alcança o Smart (`HTTP 200` em `smartsecurities.com.br`).
- A esteira carrega `config/sandbox.env`, publica as envs e o `_config` de
  produção roda fora do container (`BOLETO_DATA_DIR` no lugar de `/app`).
- Com credencial falsa, o login vai até o CapSolver e **falha fechado**
  (`SandboxSemSessao`) — não finge estar logado.

## Setup (uma vez)

**1. venv do host com Playwright + Chromium** (fora do git, `.venv-sandbox/`):

```bash
cd /home/prospere/docker/automation/erp-automation
python3 -m venv .venv-sandbox
.venv-sandbox/bin/pip install playwright python-dotenv psycopg2-binary
.venv-sandbox/bin/playwright install chromium
```

**2. credencial** — copie o template e preencha:

```bash
cp config/sandbox.example.env config/sandbox.env
chmod 640 config/sandbox.env        # o grupo proj-erp-automation lê
# preencha SANDBOX_EMAIL, SANDBOX_SENHA, SANDBOX_CAPSOLVER_API_KEY
```

`config/sandbox.env` é gitignored. Use, de preferência, um **usuário Smart de
teste** — assim a sessão do sandbox nunca disputa com a dos robôs de produção
(sessões simultâneas da mesma conta convivem, mas um login novo pode derrubar a
de outro robô e gastar um CapSolver).

## Uso

```bash
V=.venv-sandbox/bin/python

# 1) só LISTAR o que o filtro pega (não imprime nada)
$V scripts/sandbox/emissao.py --conta 290 --num-doc 15652-001

# 2) IMPRIMIR esse título e conferir o nome impresso
$V scripts/sandbox/emissao.py --conta 290 --num-doc 15652-001 --imprimir

# 3) lote inteiro, imprimindo (equivale ao que o cron faz às 09:30)
$V scripts/sandbox/emissao.py --todas-contas --imprimir

# ver o navegador (precisa de display gráfico / VNC)
$V scripts/sandbox/emissao.py --conta 290 --num-doc 15652-001 --imprimir --ver-navegador
```

Sem `--imprimir` é **dry-run**: lista e para. Com `--imprimir`, gera os PDFs em
`data/sandbox/emitidos/<dia>/` e roda o conferidor, que diz por conta se o nome
impresso bate com a regra (BB → securitizadora, `mp ` → cedente).

## Ver o que o robô faz — VNC ao vivo ou vídeo/trace

O sandbox tem **slot de display próprio** reservado, que não colide com o
container (`:99`/5900/6080):

| | display | VNC | noVNC |
|---|---|---|---|
| sandbox (host) | `:90` | 5910 | 6090 |

**Hoje, sem root — vídeo + trace (headless).** Ligado por padrão
(`SANDBOX_GRAVAR=true`). Cada run grava em `data/sandbox/trace/`:

```bash
# .webm da sessão + trace navegável (rede, DOM, screenshots por passo)
.venv-sandbox/bin/playwright show-trace data/sandbox/trace/trace_<ts>.zip
```

Para desenvolver automação, o trace costuma ser **mais** útil que o VNC: para em
cada passo, mostra o request/response e o DOM.

**VNC ao vivo — precisa de um `apt` (uma vez, com root):**

```bash
sudo apt-get update && sudo apt-get install -y xvfb x11vnc websockify novnc fluxbox
```

Depois, a cada sessão de trabalho:

```bash
sh scripts/sandbox/vnc.sh                 # sobe Xvfb :90 + x11vnc 5910 + noVNC 6090
# no config/sandbox.env:  SANDBOX_HEADLESS=false  e  SANDBOX_DISPLAY=:90
.venv-sandbox/bin/python scripts/sandbox/emissao.py --conta 395 --ver-navegador
# assista em http://<host>:6090/vnc.html
```

O `vnc.sh` é idempotente e, **sem os binários, não instala nada** (não tem root)
— avisa e sai; o sandbox segue headless com vídeo/trace até o `apt` ser feito.

## ⚠️ Riscos, ditos por inteiro

- **`--imprimir` EMITE.** Num título já emitido é 2ª via (inofensivo — ideal
  para conferir o nome). Num título nunca emitido, **emite de verdade**: consome
  nosso número e entra no fluxo de remessa. Por isso `--imprimir` é explícito e
  separado do dry-run.
- **Não dispara e-mail** para sacado: emissão é `Via=1`; o envio (`Via=2`) é
  outro robô.
- **É uma sessão a mais** da conta no Smart. Prefira um usuário de teste.

## Defeito latente que o sandbox revelou

`boletos._sessao.esta_logado` faz checagem **negativa** e um corpo HTTP 200
**vazio** (que o Smart devolve na emissão sem sessão) passa por "logado". No
container quase não aparece porque a sessão costuma estar viva; no sandbox, com
perfil novo, aparece na primeira tentativa. O sandbox se protege com
`_ambiente.alcanca_emissao()` (checagem **positiva**: a tela tem de conter o
`contaCorrente`). O robô de produção ainda tem o buraco — candidato a corrigir,
alinhando com `smart_sessao.parece_deslogado`, que já trata vazio como
deslogado.
