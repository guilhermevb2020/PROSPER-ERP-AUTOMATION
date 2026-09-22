-- erp_007_abandonada_por_automacao.sql
--
-- vw_job_execucao_abandonada com limite POR AUTOMACAO. A erp_004 usou 2 h para tudo, e o
-- credito roda um ciclo de ~11 h por dia util (07:45 -> fim do expediente; timeout do hub
-- 43200 s): aparecia como "abandonado" todo dia a partir das 09:45, e a lista virava
-- ruido. Desde a reconexao do cliente (22/09/2026) o fechamento pode falhar e deixar a
-- linha `ativa` de proposito — a view e quem denuncia isso, entao ela precisa ser limpa.
--
-- Limites (folga sobre o timeout do hub): credito 13 h; doc2you 1 h (timeout 2700 s);
-- boletos 1 h (1800 s); demais 2 h. Re-executavel; ledger do aplicar.sh.

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

CREATE OR REPLACE VIEW erp_automation.vw_job_execucao_abandonada AS
    SELECT j.*
      FROM erp_automation.job_execucao j
     WHERE j.status = 'ativa'
       AND j.iniciado_em < now() - CASE j.automacao
                                      WHEN 'credito' THEN interval '13 hours'
                                      WHEN 'doc2you' THEN interval '1 hour'
                                      WHEN 'boletos' THEN interval '1 hour'
                                      ELSE interval '2 hours'
                                   END;
COMMENT ON VIEW erp_automation.vw_job_execucao_abandonada IS
  'Morreu sem marcar o fim: ativa alem do limite da automacao (credito 13 h, doc2you e boletos 1 h, demais 2 h — folga sobre o timeout do hub). A paridade diaria (comparar_controle_csv_banco) lista estas linhas.';

RESET ROLE;
COMMIT;
