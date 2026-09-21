# Robô doc2you (baixar_dia)

Baixa os documentos das operações do Smart e sobe no Nextcloud (groupfolder CADASTRO).
Self-contained: abre o Chrome no display isolado `:98`, faz auto-login (CapSolver),
SSO da ponte Doc2You (`wvw`), baixa, classifica/nomeia, sobe via WebDAV e fecha.

Entrypoint: [`baixar_dia.py`](../baixar_dia.py). Módulos privados (`_`): `_login`,
`_nextcloud`, `_complementares`; auxiliares: `classificar`, `download`, `dias_uteis`.

## Runs agendados (hub-orchestration)

| Task | Cron | O que faz |
|------|------|-----------|
| `baixar_documentos_doc2you` | `30 7 * * 1-5` | **Canônico.** Data-alvo = 2 dias úteis atrás (dá tempo dos docs ficarem assinados). Baixa os CONCLUÍDOS (status C) + **retry** do backlog de pendências. Grava `stg.doc2you_execucao`. |
| `baixar_documentos_doc2you_antecipado` | `0 19 * * 1-5` | **Antecipada.** Data = HOJE. Baixa o que já está assinado no dia (Duplicata/NP/Carta; Aditivo normalmente ainda não) **+ os anexos das operações do dia**. NÃO faz retry e NÃO grava execucao. Só roda em **dia útil** (feriado → sai sem abrir browser; `--force` ignora). `timeout=2700s`, `max_retries=2`. |

Ambas usam o mesmo `:98` (não se sobrepõem no tempo). Wrapper: `run_agendado.sh`.

> **⚠️ Janela de acesso do usuário no Smart.** O auto-login (usuário `Raphaelas`) só
> é aceito dentro do horário de acesso configurado no **cadastro do usuário no Smart** —
> atualmente **06:30–21:00 (BRT), seg–sex**. Fora dessa janela o `smart/dologin.php`
> responde `2|Usuário com acesso restrito.` e o login falha em todas as 3 tentativas
> (não é captcha nem credencial — o CapSolver resolve normalmente). O run das **19:00
> depende dessa janela**; ao adiantar/atrasar o cron ou trocar o usuário, revalidar o
> horário de acesso no Smart. Histórico: em 06–09/07/2026 a janela fechava antes das
> 19:00, o auto-login falhou todo dia e o circuit breaker (hub-orchestration) desativou
> a task antecipada após 3 falhas consecutivas (exit -99 sintético no alerta) — resolvido
> ampliando a janela até 21:00.

## Fases do `executar()`

1. **Download do dia** (`_processar_docs`) — lista `status=C` da data-alvo, baixa e sobe
   em `DOCUMENTOS ASSINADOS/<op>/`.
2. **Retry** (`_retry_pendencias`, só no run das 07:30) — lê `stg.doc2you_pendencia`
   (aberto, ≤ `DOC2YOU_RETRY_MAX_DIAS`=20d) e re-baixa por operação (`numOperacao`) só
   os tipos que faltam. Erros do retry não derrubam `sucesso`.
   > ⚠️ A janela de re-listagem vai **`DOC2YOU_RETRY_JANELA_DIAS` (730d) pra trás**, e
   > **não** a partir do `data_alvo`. Motivo: uma operação ANTIGA pode voltar ao backlog
   > (ex.: op 61200, criada 27/05, cartas assinadas 14/07 → `data_alvo`=14/07), e seus
   > documentos originais (Aditivo/NP/Duplicata) são datados **antes** do `data_alvo` —
   > com janela curta a listagem não achava nada e a pendência travava pra sempre.
   > Alargar é barato porque o filtro `numOperacao` já restringe à operação.
3. **Complementares** (`_baixar_complementares`, só no run das 19:00) — para cada operação
   do dia (**fonte = DWH `_operacoes_do_dia`, a MESMA das NFs** — não o `operacoes` set),
   baixa os anexos da aba "Outros documentos" do Smart (ver abaixo).
4. **NF** (`_baixar_nfs`, só no run das 19:00) — rede de segurança: baixa a NF (DANFEs)
   de **TODA operação do dia**. A lista vem do **DWH** (`_operacoes_do_dia` →
   `bi.operacional_operacao_desagio` com `data_operacao >= hoje - DOC2YOU_NF_JANELA_DIAS`),
   **não** do `operacoes` set — a NF existe desde a criação da operação (independe de doc
   assinado), então o DWH garante que nenhuma passe despercebida.
   `GET /smart/operacaoajax/web/gerardanfes.php?NumOperacao=<op>` → `nf operacao/NFE<op>.pdf`
   (flat, igual robô de crédito). Skip-existing (lista a pasta 1×). Op sem títulos/DANFE
   devolve 0B → "sem NF" (não é erro). Módulo [`_nfs.py`](../_nfs.py). Teste: `--nf-op <op>`.
5. **XML** (`_baixar_xmls`, só no run das 19:00) — XMLs das notas de operação FINALIZADA
   na janela (`DOC2YOU_XML_JANELA_DIAS`=1: hoje+ontem). Fluxo Smart Financeiro (1 lote por
   dia, não itera operação): `gridmonitoramentonota.php` (listar paginado — ⚠️ página além
   da última REPETE a última, para quando não há id novo) → `gridmonitoramentonotaajax.php`
   `acao=GET_LINK_FILE_ZIP` → `financeiro/<link>.zip` → descompacta `nota<n>_op<op>.xml`.
   Destino `CADASTRO/LASTRO DAS OPERACOES/xml operacao/nota<n>_op<op>.xml` (flat, skip-existing).
   Detecta sessão caída (`expira.php`). Módulo [`_xml_notas.py`](../_xml_notas.py). Teste:
   `--xml-dia <YYYY-MM-DD>`. Mapa do fluxo: process-automation `tmp/docs/DOWNLOAD_XML_MONITORAMENTO_NOTAS.md`.

## Documentos complementares (anexos das operações)

Não estão no Doc2You — ficam na operação (aba **Outros documentos** / ANEXAR DOCUMENTOS).
Mecânica em [`_complementares.py`](../_complementares.py) (HTTP puro, portada async do
robô de crédito `robo_credito/op_docs.py`):

```
GET /smart/operacao/popupdocumentos.php?Op=<op>&Tipo=OUT   (iso-8859-1!) → viewDoc(idDoc)
GET /smart/operacao/viewdoc.php?idDoc=<id>                 → <iframe src="documento.php/...">
GET <src>                                                  → bytes (%PDF/imagem)
```

- **Destino:** `CADASTRO/LASTRO DAS OPERACOES/documentos complementares operacoes/<op>/<doc>`
  (via `src/common/clients/nextcloud_webdav.py` compartilhado).
- **Skip-existing:** `listar_nomes` (PROPFIND) da pasta; só baixa o que falta — nunca
  sobrescreve. Pasta inexistente = baixa tudo.
- Sobreposição com o robô de crédito (que baixa complementares só das ops em "Feedback
  Análise ROB") é inofensiva: mesmo destino, idempotente.

## Flags / envs úteis

- `--data YYYY-MM-DD` · `--estrutura operacao|tipo|data` · `--limite N` · `--force`
- `--no-retry` — não roda o retry do backlog.
- `--antecipado` — passada da noite (data=hoje, +anexos, sem execucao/retry).
- `--complementares-op <op>` — DEBUG: loga e baixa só os anexos daquela operação.
- Envs: `DOC2YOU_RETRY_PENDENCIAS`, `DOC2YOU_RETRY_MAX_DIAS`, `DOC2YOU_COMPL_NC_DEST`.

## Ponte de dados p/ os jobs de process-automation

`stg.doc2you_execucao` (resumo do run canônico) e `stg.doc2you_pendencia` (backlog,
dono = `doc2you_verificacao`). Gravação via psycopg2 direto **`sslmode=disable`** (o
SQLAlchemy do erp exige SSL, que o postgres LOCAL não tem).

Regras de completude que a verificação aplica: [`regras_completude_documentos.md`](regras_completude_documentos.md).
