# boletos

Robô de envio em lote de boletos do SmartSecurities — versão produção (rodando no servidor via `erp-automation` + `hub-orchestration`).

Documentação operacional completa: [`docs/BOLETOS_LOTE.md`](../../../../docs/BOLETOS_LOTE.md).

## Arquivos

| Arquivo | Função |
|---|---|
| `_config.py` | Constantes, URLs, seletores, classes de risco, paths persistentes (interno) |
| `_sessao.py` | Login interativo + keepalive, helpers Playwright (interno) |
| `_db.py` | Conexão Postgres + funções de log `operacional.boleto_envio_log` (interno) |
| `manter_sessao.py` | **Entrypoint**: sobe Chrome com perfil persistente + CDP, mantém sessão viva |
| `enviar_lote.py` | **Entrypoint**: lista contas/títulos (FASE 1) e envia em lote (FASE 2) |
| `templates/listatitulos.txt` | Corpo bruto do POST para `listatitulosboletos.php` |
| `templates/envio.txt` | Corpo bruto do POST para `printcobrancapdf.php` |

## Volumes persistentes (no host)

```
/home/prospere/docker/automation/erp-automation/data/boletos/
├── perfil_chrome/    # user-data-dir do Chrome (cookies, sessão)
├── debug/            # screenshots
└── logs/             # enviados_boletos.csv (anti-duplicação)
```

Dentro do container são acessíveis em `/app/data/boletos/...`.

## Fluxo dos testes (passo a passo)

1. **Smoke test**: importar os módulos sem rodar nada.
2. **Subir Xvfb** dentro do container (display virtual).
3. **Login inicial**: rodar `manter_sessao` com display visível (VNC). O operador faz o reCAPTCHA + escolhe a empresa **uma vez**. Os cookies ficam salvos em `perfil_chrome/`.
4. **Validar keepalive**: deixar `manter_sessao` rodando algumas horas e confirmar que a sessão não cai.
5. **SCAN (preview)**: rodar `enviar_lote` com `SCAN=true`. Lista contas + títulos do dia, sem enviar.
6. **Envio teste**: rodar `enviar_lote` com `SO_CONTA_ID=<X>` e `CONFIRMAR=1` para enviar **uma conta** específica como teste.

## Variáveis de ambiente principais

| Var | Default | Significado |
|---|---|---|
| `DRY_RUN` | true | Para antes de enviar (preenche e para) |
| `SCAN` | true | Read-only: lista mas não envia |
| `CONFIRMAR` | (vazio) | `1` libera o envio real (junto com `DRY_RUN=false SCAN=false`) |
| `DATA` | último dia útil | DD/MM/YYYY — emissão inicial |
| `DATA_FINAL` | = DATA | DD/MM/YYYY — emissão final |
| `SO_CONTA_ID` | (vazio) | Restringe a uma conta específica (id do dropdown) |
| `SO_TIPO` | (vazio) | `padrao` ou `mp` — filtra tipo de conta |
| `MODALIDADE` | C | C=Convencional, T=Trustee, G=Todas |
| `HEADLESS` | false | Precisa false enquanto loga manualmente |
| `DISPLAY` | :99 | Xvfb |
| `CDP_PORT` | 9222 | Porta do remote debugging |
