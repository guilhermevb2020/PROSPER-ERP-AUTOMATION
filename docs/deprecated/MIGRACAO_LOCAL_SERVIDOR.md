# Migração de Automação: Local (bruta) → Servidor (erp-automation)

> Playbook das mudanças que SEMPRE precisamos fazer pra tirar uma automação do
> "rodava na máquina do dev" e colocar rodando sozinha no servidor. Baseado nas
> migrações do **doc2you** e dos **boletos**. Use como checklist pra próximas.
>
> **Referência canônica de web-automation no servidor:** `src/processors/web/boletos/`
> (login persistente/CapSolver em `_sessao.py`, config em `_config.py`, keepalive em
> `manter_sessao.py`). O **doc2you** (`src/processors/web/doc2you/`) é o exemplo do
> modelo "loga 1×/dia e fecha".

---

## 0. Princípio
**Não reescrever — adaptar e reusar o framework.** O código bruto resolve o "o quê"
(parsing, fluxo da tela); o servidor já tem o "como" (browser stealth, CapSolver,
login, logs, agendamento). A migração é 80% **jogar fora** o que o framework já faz.

---

## 1. Triagem do código bruto
O zip do dev vem com 3 categorias. Classifique cada arquivo:

| Categoria | O que fazer | Exemplos (doc2you) |
|-----------|-------------|--------------------|
| **Lógica de negócio pura** (parsing, classificação, regras) | **Portar quase verbatim** | `classificar.py`, `dias_uteis.py`, o core de `baixar_documentos.py` |
| **Infra local** (browser, login, file lock, config) | **Descartar e usar o framework** | `comum.py` (tinha `import msvcrt` = Windows!), `config.py` |
| **Scripts descartáveis** (dev/debug/.bat) | **Apagar** | `inspecionar_*.py`, `extrair_captura.py`, `analisar_*.py`, `reparar_vazios.py`, `renomear_*.py`, todos os `.bat` |

⚠️ Sinais de "infra local a descartar": `import msvcrt`/`winreg`, caminhos `C:\`,
`input()` esperando humano, `.bat`, `time.sleep` gigante pra "esperar o operador",
reCAPTCHA resolvido à mão, `import config` com credencial hardcoded.

---

## 2. Reusar o framework (NÃO duplicar)
| Preciso de... | Usar |
|---|---|
| Browser stealth (score anti-bot) | `src.common.browser`: `create_stealth_browser/context/page` |
| Resolver reCAPTCHA | `src.common.captcha.playwright_captcha_manager.PlaywrightCaptchaManager` (CapSolver) |
| Login no Smart | **copiar de `boletos/_sessao.py`** (não inventar) |
| Logs de execução | `src.common.core.execution_logger.setup_execution_logger` |
| Screenshots | `src.common.core.screenshot_manager.setup_screenshot_manager` |
| Credenciais + config do processor | `src.common.core.config_loader.get_config_loader` |
| Esperas robustas | `src.common.utils.wait_utils` (`wait_for_page_ready`, `smart_wait`, `wait_for_iframe_content`, `wait_for_frame`) |
| Anti-detecção / fingerprints | `src.common.anti_detection.*` (já dentro do stealth browser) |

---

## 3. Login no Smart Securities — **o ponto MAIS crítico** (gastamos 8 CapSolver aqui)
Replicar **exatamente** o fluxo de `boletos/_sessao.py`. Pegadinhas que derrubam:

1. **Passar o IFRAME, não a page**, pro `resolver_com_fallback` — o captcha vive no
   iframe `loginsec.php`.
2. **Re-obter o iframe APÓS clicar #OK** — ele recarrega; o captcha aparece num iframe NOVO.
3. **Acionar os `data-callback` do reCAPTCHA** depois de injetar o token — senão o
   Smart **não habilita** o botão "Acessar"/#OKExtra. (era a causa do "bounce".)
4. **Tela de seleção de empresa** — clicar "Acessar" na empresa após o login.
5. **Modal "Procedimento de segurança"** — clicar PROSSEGUIR.
6. **Detecção de logado** trata o redirect JS pra `expira.php` (senão dá falso-positivo).
7. **Retry**: CapSolver às vezes falha (erro `1001`, transitório) → **3 tentativas**.
8. **Ponte/URLs internas usam `wvw` (não `www`)**: `https://wvw.smartsecurities.com.br/smart/...`.
   O **login** é `www.smartsecurities.com.br/smartsecurities/`; o **app interno** é `wvw`.
   (Errar isso faz o SSO não pegar cookies.)

---

## 4. Isolamento de display (Xvfb / VNC) — **2 Chromes no mesmo display = login bounce**
Cada automação web headed precisa do **seu próprio display**:
- Boletos rodam no `:99` (VNC `vnc.prospereinvest.com.br/vnc.html`).
- doc2you roda no **`:98`** (VNC `/d2/`, porta noVNC 6081, rota nginx adicionada sem restart).
- **Rodar a nova no `:99` junto dos boletos causou bounce no login.** Sempre display próprio.
- O **wrapper** (`run_agendado.sh`) sobe o Xvfb/x11vnc/noVNC do display **idempotente**,
  sem depender do boot e **sem reiniciar o container** (não derruba os boletos).

---

## 5. Credenciais e config
- O **`.env` do dev NÃO vem no zip** — recriar os segredos.
- Login do Smart → `config/credentials.csv` (linha por processador) + entrada no
  `config/processors.yaml` (⚠️ **sem a entrada, `get_credentials` cai em KeyError** e
  usa o fallback errado do `.env`).
- Secrets que o robô lê em runtime (ex.: WebDAV) → arquivo **montado** (`config/*.env`,
  gitignored) lido com `load_dotenv`, pra **não exigir restart** (o `env_file` do compose
  só recarrega no boot).
- Constantes (`import config`) → `os.getenv("X", default)`.

---

## 6. Destino dos arquivos → Nextcloud via WebDAV (não montar pasta)
- Subir via **WebDAV** como `automacao@prospereinvest.com.br` (está em cadastro+gestores →
  escreve no groupfolder CADASTRO). `requests.put(.../remote.php/dav/files/<user>/<path>)`.
- **Vantagens:** sem montar pasta, **sem restart**, e o Nextcloud **indexa sozinho** (sem `occ scan`).
- Montar a pasta no container exigiria editar o compose + **reiniciar** (mata os boletos). Evitar.

---

## 7. Gravar execução no banco — **GOTCHA do SSL**
- O módulo `src.common.core.database` (SQLAlchemy) **exige SSL**, mas o **postgres LOCAL**
  (host `postgres`) **não suporta SSL** → grava com **psycopg2 direto + `sslmode=disable`**
  (`DB_USER=prospere`, `DB_PASSWORD` no env). A gravação numa tabela de execução
  (ex.: `stg.doc2you_execucao`) é a **ponte** para os jobs de notificação lerem.

---

## 8. Agendamento (hub-orchestration)
- Registrar com a CLI:
  ```bash
  docker exec hub-orchestration python run.py tasks upsert-docker <nome> \
    --container erp-automation \
    --command "sh /app/src/processors/web/<pacote>/run_agendado.sh" \
    --cron "30 7 * * 1-5" --timeout-seconds 2700 --group operacional
  ```
- O **comando deve ser o wrapper** que garante o display, não o `python` direto.
- O robô **mira a data certa internamente** (ex.: `dia_alvo_download` = 2 dias úteis atrás)
  e tem **guarda de dia útil** (sai limpo em feriado).

---

## 9. Robustez obrigatória
- **Guarda de dia útil** (`eh_dia_util(hoje)`), exceto se `--data`/`--force`.
- **Retry de login** (CapSolver transitório).
- **Dedup de nomes de arquivo** — se 2 docs geram o mesmo nome, anexar o id único
  (senão o WebDAV PUT **sobrescreve e perde** documento).
- **Trava de integridade** — descartar arquivo < 1 KB / desempacotar ZIP antes de subir.
- **Self-contained vs. sessão viva**: "loga 1×/dia e fecha" (doc2you) é mais simples que
  manter sessão 24/7 (boletos via `manter_sessao` + CDP). Escolher conforme a frequência.

---

## 10. Notificações = **jobs SEPARADOS** (em process-automation)
- O robô **só faz o trabalho**; quem avisa é outro job (igual `resumo_diario_boletos`).
- Vivem em `process-automation/setores/<setor>/<job>/` (herdam `BaseJob`), pois lá está o
  **DWH** + o **WhatsApp** (`src.clients.whatsapp.WhatsAppClient(instancia="Prosperito")`).
- **Dry-run**: `--profile preview` → `self.is_preview()` mostra a mensagem **sem enviar**.
  Sempre validar o texto em preview antes de ligar o envio real.
- Lêem a tabela de execução do robô (a ponte do passo 7).

---

## 11. Checklist final de validação
- [ ] Descartou scripts `.bat`/dev e `import msvcrt`/`config`.
- [ ] Login copiado do `boletos/_sessao.py` (callbacks + empresa + segurança + retry + `wvw`).
- [ ] Display próprio (`:9X`) + wrapper que o sobe idempotente.
- [ ] `credentials.csv` + entrada no `processors.yaml`.
- [ ] Destino Nextcloud WebDAV (automacao), sem mount/restart.
- [ ] Grava execução (psycopg2 `sslmode=disable`).
- [ ] Guarda de dia útil + retry + dedup + trava de integridade.
- [ ] Registrado no hub (wrapper, cron, grupo).
- [ ] **Testado de verdade** 1 dia (login → trabalho → grava) e o resultado no destino.
- [ ] Jobs de notificação validados em **preview** antes do envio real.
- [ ] **Boletos intactos** (CDP 9222 vivo; nunca rodar a nova no `:99`).

---

## Gotchas Smart Securities (resumo rápido)
- `www` = login · **`wvw` = app interno** (relatórios, doc2you, financeiro).
- reCAPTCHA precisa do **callback acionado**, não só do token na textarea.
- Pós-login tem **seleção de empresa** + às vezes **modal de segurança**.
- **Sessão única / por conta**: rodar 2 logins da mesma conta ao mesmo tempo dá bounce →
  conta dedicada por automação (doc2you=`Raphaelas`, boletos=`envioboletos`).
- CapSolver erro `1001` = transitório → retry.
