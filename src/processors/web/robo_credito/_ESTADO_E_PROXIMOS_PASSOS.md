# Robô Análise de Crédito (V4) — Estado & Próximos Passos

> **Parado em:** 2026-06-29. **Próxima sessão:** integração formal pra produção.
> **Cópia de trabalho (validada):** `erp-automation/data/robo_credito_teste/`

---

## O que o robô faz (fluxo real)
Roda em **loop contínuo** (alvo: 7:45–18:50). A cada ciclo, lendo SEMPRE do **Smart**
(tela de consulta, abas Home + SmartSecurities — nunca do banco):

1. **Login** (`Raphaelas`, CapSolver) — só reloga se a sessão caiu
2. **"Análise Home"** → por op: **ajusta classe de risco** (maioria E→B, P→T; pula C/CE),
   **SALVA**, **move → "Feedback Análise ROB"** (com verificação + retry)
3. **DIGITAIS** (ops em "Enviar Digitais"): gera **Aditivo→NPP→Duplicata→Carta de Cessão**
   (HTTP direto; Aditivo é portão; anti-duplicação) e **move → "Aguardando Ass."**
4. **"Feedback ROB"** → baixa **NF + Resumo + documentos complementares** e **move → "Análise de crédito"**

**Destinos no Nextcloud** (`CADASTRO/LASTRO DAS OPERACOES/`):
- NF → `nf operacao/NFE<op>.pdf`
- Resumo → `resumo da operacao/resumo<op>.pdf`
- Complementares → `documentos complementares operacoes/<op>/<docs>` (subpasta por op)

> ⚠️ A **conferência por IA (Claude) FOI REMOVIDA** deste robô (29/06). A análise dos
> documentos virou **automação SEPARADA** que lê os PDFs salvos na pasta do Nextcloud.
> Por isso **não precisa mais** de Claude CLI / setup-token / pdfplumber aqui.

---

## ✅ Feito e VALIDADO (em produção, ao vivo)
- [x] Fonte dos ops = **Smart** (corrige o "bug do resumo": banco fica com fantasmas)
- [x] Classe de risco (P→T) + SALVAR + move de etapa (com verificação/retry)
- [x] DIGITAIS — 4 documentos (op 62478, supervisionado)
- [x] NF + Resumo → Nextcloud
- [x] Documentos complementares → Nextcloud (pasta por op) — op 61911
- [x] **Robustez**: `_watchdog.py` (trava > `WATCHDOG_MAX_OCIOSO=360s` sem heartbeat →
      mata o Chrome → `main()` **relança do ZERO**); loop infinito; backoff; limpa zumbis/lock
- [x] **Velocidade**: removida a varredura da conferência (~32s/ciclo); `WAIT_ENTRE_OPERACOES`
      40→12; `WAIT_POS_SALVAR` 5→3; `WAIT_POS_PESQUISA` 2→1.5; `ESPACO_NPP_DUP` 15→10.
      Ciclo ocioso **~84s → ~15-20s** (~4-5×). Tudo tunável por env.
- [x] **Limpeza**: 58 → 10 `.py` (só o núcleo)

**Núcleo (10 arquivos):** `robo_analise_credito_v4.py` → `_v3.py` (hook classe) →
`robo_analise_credito.py` (V1/main/loop/login/watchdog) → `subfluxos.py` (NF/resumo/
complementares/DIGITAIS) → `{banco, _nextcloud, _watchdog, op_docs, smart_session, config}`.

---

## ⏳ FALTA: integração formal (objetivo de amanhã)
1. **Mover** o núcleo (10 .py) p/ `src/processors/web/robo_credito/` (padrão do doc2you)
2. **Wrapper** `run_agendado.sh` que sobe o display **:96** idempotente (Xvfb + x11vnc 5902 +
   websockify 6082; rota nginx `/rc/` já existe) — igual `src/processors/web/doc2you/run_agendado.sh`
3. **Registrar no hub** com cron **7:45–18:50, loop real** (`USAR_BANCO_DOWNLOAD=False`,
   `CLASSE_RISCO_APLICAR=1`, `SALVAR_NEXTCLOUD=True`, `SKIP_DIGITAIS=False`, `DRY_RUN=False`)
4. **Bake no Dockerfile** (já tem `--no-sandbox` no código; `pdfplumber` já removido; claude
   não é mais necessário) — recria o container → **janela de manutenção** (derruba boletos/doc2you por instantes)
5. **Reapar zumbis** no container (init/tini) — opcional

> Decisões do usuário: **sem alertas** (orquestrador já tem) e **sem migrar controles de
> idempotência** (`controle_downloads.csv` fica local).

---

## Como rodar (referência / teste)
Display **:96** (VNC: `https://vnc.prospereinvest.com.br/rc/vnc.html`). Boletos=:99/9222,
doc2you=:98 — **nunca** rodar este no :99.

```bash
docker exec erp-automation sh -c 'pkill -9 -f "user-data-dir=/tmp/rct/perfil"; rm -f /tmp/rct/perfil/Singleton*'
docker exec -e DISPLAY=:96 -e DRY_RUN=False -e CLASSE_RISCO_APLICAR=1 -e SALVAR_NEXTCLOUD=True \
  -e USAR_BANCO_DOWNLOAD=False -e SKIP_DIGITAIS=False \
  -e SMART_EMAIL=Raphaelas -e SMART_SENHA="$SMART_SENHA" -e PGSSLMODE=disable -e DB_USER=prospere \
  -e USER_DATA_DIR=/tmp/rct/perfil -e PYTHONUNBUFFERED=1 \
  -w /app/data/robo_credito_teste erp-automation python -u robo_analise_credito_v4.py
# (loop infinito: MAX_REINICIOS=0. Para testar bounded: -e MAX_REINICIOS=1 -e MAX_OPERACOES=3)
```

Memória completa: `project_robo_analise_credito_v4_migracao` (no diretório de memória do Claude).
Playbook de migração: `erp-automation/docs/MIGRACAO_LOCAL_SERVIDOR.md`.
