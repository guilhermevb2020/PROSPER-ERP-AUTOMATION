-- erp_008 — o historico que so existia nos CSVs de controle entra no banco.
--
-- Em 22/09/2026 os quatro jobs de arquivo pararam de gravar CSV (Fase 4, a pedido da
-- Gerencia). Faltava o que veio ANTES do registro no banco (21/09): os dois retornos ainda
-- liam o CSV antigo para nao dar baixa em duplicidade num .RET re-entregue — 1.729 arquivos
-- distintos do retorno de cobranca e 390 do retorno de pagamento existiam so no CSV, e para a
-- maioria o arquivo ja nao esta no disco, entao nao da para registra-los em `arquivo` (que
-- exige o sha256 do conteudo).
--
-- `arquivo_historico` guarda so o que o CSV sabia: o md5 do conteudo, o nome e quando foi
-- tratado. E memoria de idempotencia, nao arquivo: a `listar_md5` passa a unir as duas
-- tabelas e o CSV deixa de ser lido. Append-only como os eventos. Re-executavel; ledger do
-- aplicar.sh.

BEGIN;
SET LOCAL client_min_messages TO warning;

DO $$
DECLARE
    eu_super boolean := (SELECT rolsuper FROM pg_roles WHERE rolname = session_user);
BEGIN
    IF NOT eu_super AND NOT pg_has_role(session_user, 'app_erp_automation_evento', 'SET') THEN
        EXECUTE 'SET LOCAL ROLE access_admin';
        EXECUTE format('GRANT app_erp_automation_evento TO %I', session_user);
        EXECUTE 'RESET ROLE';
    END IF;
END $$;

SET LOCAL ROLE app_erp_automation_evento;

CREATE TABLE IF NOT EXISTS erp_automation.arquivo_historico (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fk_job_execucao  bigint      NOT NULL REFERENCES erp_automation.job_execucao (id),
    tipo_arquivo     text        NOT NULL,
    md5              text        NOT NULL,
    nome_arquivo     text        NOT NULL,
    tratado_em       timestamptz,
    origem           text        NOT NULL,
    detalhe_json     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    carregado_em     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_arquivo_historico_tipo CHECK (tipo_arquivo IN (
        'remessa_cobranca_cnab_400', 'retorno_cobranca_cnab_400',
        'remessa_pagamento_cnab_240', 'retorno_pagamento_cnab_240',
        'remessa_bb', 'retorno_bb')),
    CONSTRAINT ck_arquivo_historico_md5 CHECK (md5 ~ '^[0-9a-f]{32}$'),
    CONSTRAINT uq_arquivo_historico_tipo_md5 UNIQUE (tipo_arquivo, md5)
);
COMMENT ON TABLE erp_automation.arquivo_historico IS
  'O que os CSVs de controle sabiam de arquivos tratados antes do registro no banco (21/09/2026): '
  'md5 do conteudo, nome e quando. Memoria de idempotencia dos retornos; o arquivo em si, quando '
  'existe, esta em erp_automation.arquivo. Append-only.';

DROP TRIGGER IF EXISTS tg_arquivo_historico_so_insere ON erp_automation.arquivo_historico;
CREATE TRIGGER tg_arquivo_historico_so_insere
    BEFORE UPDATE OR DELETE ON erp_automation.arquivo_historico
    FOR EACH ROW EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();
DROP TRIGGER IF EXISTS tg_arquivo_historico_sem_truncate ON erp_automation.arquivo_historico;
CREATE TRIGGER tg_arquivo_historico_sem_truncate
    BEFORE TRUNCATE ON erp_automation.arquivo_historico
    FOR EACH STATEMENT EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();

GRANT SELECT, INSERT ON erp_automation.arquivo_historico TO app_erp_automation;
GRANT USAGE, SELECT ON SEQUENCE erp_automation.arquivo_historico_id_seq TO app_erp_automation;
DO $$
DECLARE
    leitor text;
BEGIN
    FOREACH leitor IN ARRAY ARRAY['dev_user', 'app_process_automation', 'app_data_hub',
                                  'app_hub_orch', 'app_forms_hub', 'app_crm', 'app_metas', 'hub_sql'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = leitor) THEN
            EXECUTE format('GRANT SELECT ON erp_automation.arquivo_historico TO %I', leitor);
        END IF;
    END LOOP;
END $$;

RESET ROLE;
COMMIT;
