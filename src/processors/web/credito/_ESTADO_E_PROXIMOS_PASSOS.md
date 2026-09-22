# Robô Análise de Crédito (V4) — Estado & Próximos Passos

> **Parado em:** 2026-06-29. **Próxima sessão:** integração formal pra produção.
> **Cópia de trabalho (validada):** `erp-automation/data/robo_credito_teste/`

---

## ⚠️ 22/09/2026 — a consulta lia a tabela errada, e o robô mexeu em operação de outra etapa

A busca por etapa (`_buscar_numeros_uma`, a mesma do finalizador) lia a tabela 1,5 s
depois de Pesquisar. O Pesquisar recarrega o frame `pesq` (POST `conoperacao.php`), e antes
da recarga esse frame mostra as **10 operações mais recentes, de qualquer etapa e das duas
securitizadoras**. Quando o Smart passava de 1,5 s, o robô lia essa tabela e pegava a
primeira como se estivesse em "Análise Home". Aconteceu 9 vezes em 22/09:

| ciclo | op | o que o robô fez fora da etapa |
|---|---|---|
| 193 | 65854 | classe P→T (1 título), Salvar, moveu para "Análise de crédito" |
| 369 e 375 | 65877 | classe P→T (13 títulos), Salvar, moveu para "Análise de crédito" duas vezes |
| 409 | 65883 | classe E→B (5 títulos), Salvar, moveu para "Análise de crédito" |
| 447 | 65893 | classe E→B (15 títulos), Salvar, moveu para "Análise de crédito" |
| 17, 26, 107, 153 | 65850 | já concluída: Salvar e etapa bloqueados, sem dano |

65854 e 65877 estavam em "Aguardando Ass." (o finalizador as via lá); 65883 e 65893 em
"Feedback Analise ROB" (o próprio crédito as listou lá pouco antes). Às 16:35 as cinco
estavam `Concluída` no Smart; **a classe de risco trocada ficou** e precisa ser conferida
por quem define a classe.

**Correção, em produção desde 22/09 16:31:** a busca só lê depois que o frame de resultado
troca de documento (teto `WAIT_MAX_PESQUISA`, 20 s; sem recarga, falha e tenta de novo uma
vez) e só devolve a linha cuja **coluna Etapa** é a pesquisada; sem a coluna, não devolve
nada. Medido no Smart real: a primeira pesquisa numa aba nova levou 2,52 s para recarregar.
Teste: `tests/unit/test_busca_consulta_etapa.py`. O processo que rodava desde 07:45 foi
interrompido entre ciclos às 16:28 e o hub o relançou às 16:31 (execução #365); a #19 dele
fica `ativa` até entrar no limite de 13 h (20:45) e se encerra com
`encerrar_abandonada.py 19 --pra-valer`.

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

**Núcleo (10 arquivos):** `analisar_credito.py` → `_v3.py` (hook classe) →
`_analisar_credito_base.py` (V1/main/loop/login/watchdog) → `subfluxos.py` (NF/resumo/
complementares/DIGITAIS) → `{banco, _nextcloud, _watchdog, op_docs, smart_session, config}`.

---

## ⏳ FALTA: integração formal (objetivo de amanhã)
1. **Mover** o núcleo (10 .py) p/ `src/processors/web/credito/` (padrão do doc2you)
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
  -w /app/data/robo_credito_teste erp-automation python -u analisar_credito.py
# (loop infinito: MAX_REINICIOS=0. Para testar bounded: -e MAX_REINICIOS=1 -e MAX_OPERACOES=3)
```

Memória completa: `project_robo_analise_credito_v4_migracao` (no diretório de memória do Claude).
Playbook de migração: `erp-automation/docs/MIGRACAO_LOCAL_SERVIDOR.md`.
