-- erp_003_limpar_acl_herdada_da_mudanca.sql
--
-- Fecha um buraco aberto pela propria erp_001.
--
-- O QUE ACONTECEU
-- ---------------------------------------------------------------------------------
-- `ALTER TABLE ... SET SCHEMA` move a tabela e **mantem o `relacl`**. As 4 tabelas
-- chegaram em `erp_automation` carregando as permissoes que `operacional` e `stg`
-- haviam concedido a outros projetos. Medido em 12/08/2026:
--
--   boleto_envio_log            app_forms_hub:      INSERT/UPDATE/DELETE
--   boleto_emissao_log          app_process_autom.: INSERT/UPDATE/DELETE
--   boleto_sessao_healthcheck   dev_user:           INSERT
--   doc2you_execucao            app_data_hub:       INSERT/UPDATE/DELETE
--
-- O padrao confirma a causa: as 3 que vieram de `operacional` trouxeram exatamente
-- quem escrevia em `operacional`; a que veio de `stg` trouxe quem escrevia em `stg`.
--
-- O CONTROLE QUE PROVA O DIAGNOSTICO
-- ---------------------------------------------------------------------------------
-- `migration_aplicada` NASCEU neste schema, e por isso tem zero escrita de terceiros.
-- Tabela movida carrega ACL; tabela criada aqui, nao.
--
-- POR QUE ISSO IMPORTA
-- ---------------------------------------------------------------------------------
-- Sem esta migration, "um schema, um dono que escreve" era verdade so no papel: tres
-- outros projetos podiam apagar o log de boleto deste robo. A leitura continua
-- aberta — e por desenho.
--
-- LICAO GERAL, valida para qualquer projeto que faca a mesma mudanca:
-- mover tabela para o schema proprio NAO limpa quem podia escrever nela. Sao dois
-- passos, e o segundo e facil de esquecer porque a primeira query de conferencia
-- (dono da tabela) da o resultado certo mesmo com o buraco aberto.

BEGIN;

-- ---------------------------------------------------------------------------
-- Escrita: so o dono. Nominal e explicito, para ficar auditavel no git.
-- ---------------------------------------------------------------------------
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA erp_automation
    FROM dev_user, app_process_automation, app_data_hub, app_hub_orch,
         app_forms_hub, app_crm, app_metas, app_scatambulo, PUBLIC;

REVOKE USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA erp_automation
    FROM dev_user, app_process_automation, app_data_hub, app_hub_orch,
         app_forms_hub, app_crm, app_metas, app_scatambulo, PUBLIC;

-- ---------------------------------------------------------------------------
-- Rede de seguranca: se sobrou algum papel que a lista acima nao previu, cai aqui.
-- Custa uma varredura de catalogo e cobre role criada depois desta migration.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT DISTINCT c.oid::regclass AS tabela, a.grantee::regrole::text AS papel
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(c.relacl) a
        WHERE n.nspname = 'erp_automation'
          AND c.relkind = 'r'
          AND a.privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE')
          AND a.grantee <> 0                                   -- PUBLIC ja tratado
          AND a.grantee::regrole::text <> 'app_erp_automation'  -- o dono fica
    LOOP
        EXECUTE format(
            'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON %s FROM %I',
            r.tabela, r.papel);
        RAISE NOTICE 'escrita removida: % em %', r.papel, r.tabela;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- A leitura permanece aberta — e o outro lado do desenho.
-- ---------------------------------------------------------------------------
GRANT SELECT ON ALL TABLES IN SCHEMA erp_automation TO
    dev_user, app_process_automation, app_data_hub, app_hub_orch,
    app_forms_hub, app_crm, app_metas;

COMMIT;

-- ---------------------------------------------------------------------------
-- VERIFICACAO — deve voltar ZERO linhas.
-- ---------------------------------------------------------------------------
--   SELECT c.relname, a.grantee::regrole::text, a.privilege_type
--   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
--   CROSS JOIN LATERAL aclexplode(c.relacl) a
--   WHERE n.nspname='erp_automation' AND c.relkind='r'
--     AND a.privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE')
--     AND a.grantee::regrole::text <> 'app_erp_automation';
