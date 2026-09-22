-- erp_006_run_id_nao_unico.sql
--
-- run_id deixa de ser UNICO em job_execucao. A erp_004 assumiu "uma execucao de job por
-- run do hub", e isso nao e verdade por desenho: o wrapper do retorno de cobranca chama
-- o python UMA VEZ POR PASTA do dia (22/09/2026: #60 e #61 na mesma task das 08:50), e o
-- hub retenta com o mesmo run. Enquanto o hub nao injetava HUB_RUN_ID (medido em
-- 22/09/2026: nenhuma HUB_* chega ao processo), run_id era sempre nulo e o unico nunca
-- mordeu. Com a injecao (frente do hub, pedida em 22/09), a SEGUNDA execucao do mesmo
-- run cairia no unico — e em modo real o job recusa agir sem registro: a segunda pasta
-- do retorno ficaria sem processar, em silencio. Esta migration vem ANTES da imagem do
-- hub que injeta.
--
-- A ligacao continua: (run_id) -> N execucoes de job, cada uma com seu job e horario.
-- Re-executavel; ledger do aplicar.sh garante aplicacao unica.

BEGIN;
SET LOCAL client_min_messages TO warning;

-- A sessao veste a role dona (ver erp_004/erp_005).
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

DROP INDEX IF EXISTS erp_automation.uq_job_execucao_run_id;
CREATE INDEX IF NOT EXISTS ix_job_execucao_run_id
    ON erp_automation.job_execucao (run_id) WHERE run_id IS NOT NULL;
COMMENT ON COLUMN erp_automation.job_execucao.run_id IS
  'Identificador da execucao no hub (HUB_RUN_ID). NAO e unico: um run do hub pode abrir '
  'varias execucoes de job (wrapper que chama o python por pasta; retentativa).';

RESET ROLE;
COMMIT;
