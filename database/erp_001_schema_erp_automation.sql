-- erp_001_schema_erp_automation.sql
--
-- Da a este projeto um schema proprio, do qual ele e DONO.
--
-- Antes desta migration, as 4 tabelas que o erp-automation escreve moravam em dois
-- schemas de outros donos:
--
--   operacional.boleto_envio_log           15.955 linhas, desde 05/06/2026
--   operacional.boleto_emissao_log          4.628 linhas, desde 11/06/2026
--   operacional.boleto_sessao_healthcheck   6.230 linhas, desde 08/06/2026
--   stg.doc2you_execucao                       37 linhas, desde 23/06/2026
--
-- Tres problemas distintos, medidos em 12/08/2026:
--
--   1. LOCALIZACAO. Em `operacional`, 3 das 6 tabelas eram deste robo — metade do
--      schema. Em `stg` (camada de staging do ETL), `doc2you_execucao` nao e staging
--      de nada: e log de execucao de robo, lido por um job de saude.
--
--   2. POSSE. Quem CRIAVA era o process-automation (migrations 079/080/081); quem
--      ESCREVE e este repositorio, que nao tinha DDL nenhuma. `doc2you_execucao` era
--      pior: dono `dev_user`, sem migration em repositorio algum.
--
--   3. PERMISSAO. Tratada na erp_002 — e o problema maior dos tres.
--
-- SEGURO POR MEDICAO: as 4 tabelas nao tem NENHUMA view, foreign key ou procedure
-- dependente (verificado em pg_depend e pg_constraint, 12/08). `SET SCHEMA` e
-- atualizacao de catalogo: instantanea, sem copia, leva junto indices e sequences.
--
-- Os leitores do process-automation (resumo_diario_boletos, _reenvio_erp,
-- doc2you_saude) continuam funcionando pelas views de compatibilidade abaixo.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. O schema
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS erp_automation AUTHORIZATION app_erp_automation;

COMMENT ON SCHEMA erp_automation IS
  'Robos do ERP (Smart Securities). Dono e unico escritor: app_erp_automation, '
  'a role do repositorio automation/erp-automation. Todos os outros projetos LEEM. '
  'DDL versionada em erp-automation/database/.';

-- ---------------------------------------------------------------------------
-- 2. Mover as tabelas
--    Guardado por to_regclass para o arquivo ser re-executavel sem estrago.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    origem TEXT;
    destino TEXT;
    par TEXT[];
BEGIN
    FOREACH par SLICE 1 IN ARRAY ARRAY[
        ['operacional.boleto_envio_log',          'boleto_envio_log'],
        ['operacional.boleto_emissao_log',        'boleto_emissao_log'],
        ['operacional.boleto_sessao_healthcheck', 'boleto_sessao_healthcheck'],
        ['stg.doc2you_execucao',                  'doc2you_execucao']
    ] LOOP
        origem  := par[1];
        destino := par[2];

        IF to_regclass('erp_automation.' || destino) IS NOT NULL THEN
            RAISE NOTICE 'erp_automation.% ja existe — pulando', destino;
            CONTINUE;
        END IF;

        IF to_regclass(origem) IS NULL THEN
            RAISE EXCEPTION '% nao existe e o destino tambem nao — abortando', origem;
        END IF;

        EXECUTE format('ALTER TABLE %s SET SCHEMA erp_automation', origem);
        RAISE NOTICE 'movida: % -> erp_automation.%', origem, destino;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 3. Posse
--    Sem posse, app_erp_automation nao pode alterar as proprias tabelas — e este
--    projeto volta a depender de migration de outro repositorio. E o bloqueio que
--    o diagnostico de 03/08 registrou como item 8, aqui resolvido de forma barata
--    porque sao 4 tabelas e nenhuma procedure.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    obj RECORD;
BEGIN
    FOR obj IN
        SELECT c.oid::regclass AS nome, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'erp_automation'
          AND c.relkind IN ('r', 'S')
          AND pg_get_userbyid(c.relowner) <> 'app_erp_automation'
    LOOP
        IF obj.relkind = 'r' THEN
            EXECUTE format('ALTER TABLE %s OWNER TO app_erp_automation', obj.nome);
        ELSE
            EXECUTE format('ALTER SEQUENCE %s OWNER TO app_erp_automation', obj.nome);
        END IF;
        RAISE NOTICE 'posse: % -> app_erp_automation', obj.nome;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 4. Views de compatibilidade — TEMPORARIAS
--
--    O process-automation le estas tabelas em 3 jobs:
--      setores/operacional/boletos/resumo_diario_boletos/_queries.py
--      setores/TI/monitoramento/monitorar_email_notificacoes/_reenvio_erp.py
--      setores/operacional/doc2you_saude/doc2you_saude.py
--
--    As views existem para que nada quebre no instante da migracao. Elas devem cair
--    numa erp_003, depois que aquele repositorio apontar para erp_automation.*.
--
--    ⚠️ PRAZO: remover ate 30/09/2026. View de compatibilidade sem prazo vira
--    permanente, e a mistura que esta migration corrige volta pela porta dos fundos.
--
--    Nao ha risco de escrita acidental por elas: o unico escritor destas tabelas e
--    este repositorio, e ele passa a usar o nome novo.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW operacional.boleto_envio_log AS
    SELECT * FROM erp_automation.boleto_envio_log;
CREATE OR REPLACE VIEW operacional.boleto_emissao_log AS
    SELECT * FROM erp_automation.boleto_emissao_log;
CREATE OR REPLACE VIEW operacional.boleto_sessao_healthcheck AS
    SELECT * FROM erp_automation.boleto_sessao_healthcheck;
CREATE OR REPLACE VIEW stg.doc2you_execucao AS
    SELECT * FROM erp_automation.doc2you_execucao;

COMMENT ON VIEW operacional.boleto_envio_log IS
  'COMPATIBILIDADE — a tabela mudou para erp_automation.boleto_envio_log em 12/08/2026. '
  'Remover ate 30/09/2026.';
COMMENT ON VIEW operacional.boleto_emissao_log IS
  'COMPATIBILIDADE — a tabela mudou para erp_automation.boleto_emissao_log em 12/08/2026. '
  'Remover ate 30/09/2026.';
COMMENT ON VIEW operacional.boleto_sessao_healthcheck IS
  'COMPATIBILIDADE — a tabela mudou para erp_automation.boleto_sessao_healthcheck em 12/08/2026. '
  'Remover ate 30/09/2026.';
COMMENT ON VIEW stg.doc2you_execucao IS
  'COMPATIBILIDADE — a tabela mudou para erp_automation.doc2you_execucao em 12/08/2026. '
  'Remover ate 30/09/2026.';

-- ---------------------------------------------------------------------------
-- 5. Leitura para os outros projetos
--
--    Implementa o desenho registrado em 03/08: "um schema, um dono que escreve;
--    todos os outros leem". `app_scatambulo` fica de fora por desenho — o
--    isolamento que aquele projeto ja tinha e preservado.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA erp_automation TO
    dev_user, app_process_automation, app_data_hub, app_hub_orch,
    app_forms_hub, app_crm, app_metas;

GRANT SELECT ON ALL TABLES IN SCHEMA erp_automation TO
    dev_user, app_process_automation, app_data_hub, app_hub_orch,
    app_forms_hub, app_crm, app_metas;

ALTER DEFAULT PRIVILEGES FOR ROLE app_erp_automation IN SCHEMA erp_automation
    GRANT SELECT ON TABLES TO
    dev_user, app_process_automation, app_data_hub, app_hub_orch,
    app_forms_hub, app_crm, app_metas;

-- As views ficam no schema antigo, de dono `prospere` (quem roda esta migration).
-- Os leitores precisam de SELECT nelas enquanto existirem.
GRANT SELECT ON operacional.boleto_envio_log,
                operacional.boleto_emissao_log,
                operacional.boleto_sessao_healthcheck,
                stg.doc2you_execucao
    TO dev_user, app_process_automation, app_data_hub, app_hub_orch,
       app_forms_hub, app_crm, app_metas, app_erp_automation;

COMMIT;
