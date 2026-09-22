-- erp_005_controle_no_banco.sql
--
-- O banco passa a ser a FONTE do controle dos jobs (decisao da Gerencia, 22/09/2026):
-- o CSV de cada job vira reserva ate o corte, e o que so existia em JSON no disco
-- ganha evento aqui. Esta migration nao troca nenhuma leitura de job — e a Fase 1
-- de docs/PLANO_CONTROLE_NO_BANCO.md: estrutura primeiro, leituras depois.
--
-- O que muda:
--   arquivo          md5 e id_no_smart viram colunas GERADAS a partir de detalhe_json
--                    (a origem continua sendo o JSON; a coluna e o indice), porque o
--                    wrapper do retorno e o cancelamento procuram por elas.
--   arquivo_evento   eventos novos: intencao_envio (BB, antes do POST), descartado
--                    (remessa que o robo recusou), cancelado, movido.
--   operacao_evento  eventos do credito: documentos_baixados, etapa_movida.
--   job_execucao     operador e motivo (execucao manual: quem e por que); automacao
--                    'controle' para o job de paridade CSV x banco.
--   views            o que hoje se le no CSV, com as MESMAS colunas: vw_controle_retorno,
--                    vw_controle_remessa, vw_controle_pagamento,
--                    vw_controle_retorno_pagamento; e vw_arquivo_dia, vw_job_execucao_ultima.
--
-- Nada e apagado, nenhuma linha muda: ADD COLUMN gerada nao dispara gatilho de linha,
-- e os CHECKs so ganham valores. Re-executavel (IF NOT EXISTS / OR REPLACE /
-- DROP CONSTRAINT IF EXISTS + ADD); o ledger do aplicar.sh garante aplicacao unica.
-- Quem aplica: modelo erp-automation-ddl do Guardian (access_admin + app_erp_automation),
-- como na erp_004. Tudo nasce como app_erp_automation_evento.

BEGIN;
SET LOCAL client_min_messages TO warning;

-- A sessao precisa VESTIR a role dona (SET ROLE). Superusuario nao precisa; a tmp_ do
-- Guardian precisa - e quem tem ADMIN OPTION (access_admin, que a criou na erp_004)
-- concede. 'SET', nao 'MEMBER' (ver a erp_004). A membresia morre com a tmp_ no revogar.
-- Medido em 22/09/2026: sem isto a erp_005 caiu na linha do SET ROLE com "permission
-- denied", dentro da transacao - nada aplicado, ledger intacto.
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

-- ---------------------------------------------------------------------------
-- 1. arquivo: md5 e id_no_smart como colunas geradas + indices
-- ---------------------------------------------------------------------------
ALTER TABLE erp_automation.arquivo
    ADD COLUMN IF NOT EXISTS md5 text
        GENERATED ALWAYS AS (detalhe_json ->> 'md5') STORED,
    ADD COLUMN IF NOT EXISTS id_no_smart text
        GENERATED ALWAYS AS (detalhe_json ->> 'id_no_smart') STORED;
COMMENT ON COLUMN erp_automation.arquivo.md5 IS
  'Gerada de detalhe_json.md5: o hash que o CSV de controle usa (texto, \r\n removido). Chave de paridade CSV x banco.';
COMMENT ON COLUMN erp_automation.arquivo.id_no_smart IS
  'Gerada de detalhe_json.id_no_smart: o id da remessa na tela Download de Remessa do Smart; o cancelamento procura por ele.';
CREATE INDEX IF NOT EXISTS ix_arquivo_tipo_md5
    ON erp_automation.arquivo (tipo_arquivo, md5) WHERE md5 IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_arquivo_id_no_smart
    ON erp_automation.arquivo (id_no_smart) WHERE id_no_smart IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. arquivo_evento: eventos que so existiam em JSON no disco
-- ---------------------------------------------------------------------------
ALTER TABLE erp_automation.arquivo_evento DROP CONSTRAINT IF EXISTS ck_arquivo_evento_tipo;
ALTER TABLE erp_automation.arquivo_evento ADD CONSTRAINT ck_arquivo_evento_tipo CHECK (tipo_evento IN (
    'gerado', 'enviado', 'recebido', 'processado', 'rejeitado', 'retido',
    'intencao_envio',   -- BB: registrado ANTES do POST irreversivel (o recibo em disco continua)
    'descartado',       -- remessa que o Smart gerou e o robo recusou (linha fora dos 400 bytes)
    'cancelado',        -- remessa cancelada na tela Download de Remessa
    'movido'));         -- arquivo movido de pasta (_PROCESSADOS, _REJEITADOS, _INCONCLUSIVOS)
COMMENT ON TABLE erp_automation.arquivo_evento IS
  'O que aconteceu com o arquivo, na ordem: gerado, enviado, recebido, intencao_envio, processado, rejeitado, retido, descartado, cancelado, movido.';

-- ---------------------------------------------------------------------------
-- 3. operacao_evento: o credito passa a registrar aqui (saia do CSV local)
-- ---------------------------------------------------------------------------
ALTER TABLE erp_automation.operacao_evento DROP CONSTRAINT IF EXISTS ck_operacao_evento_tipo;
ALTER TABLE erp_automation.operacao_evento ADD CONSTRAINT ck_operacao_evento_tipo CHECK (tipo_evento IN (
    'avaliada', 'finalizar_clicado', 'finalizada', 'finalizacao_falhou',
    'finalizada_por_outro', 'aviso_enviado',
    'documentos_baixados',   -- credito: NF e/ou resumo baixados (resultado OK|PARCIAL)
    'etapa_movida'));        -- credito: operacao movida para Analise de credito

-- ---------------------------------------------------------------------------
-- 4. job_execucao: quem e por que (manual) + a automacao do job de paridade
-- ---------------------------------------------------------------------------
ALTER TABLE erp_automation.job_execucao
    ADD COLUMN IF NOT EXISTS operador text,
    ADD COLUMN IF NOT EXISTS motivo   text;
COMMENT ON COLUMN erp_automation.job_execucao.operador IS
  'Quem disparou uma execucao manual (ERP_OPERADOR no ambiente). Cron: nulo, o hub e o operador.';
COMMENT ON COLUMN erp_automation.job_execucao.motivo IS
  'Por que foi disparada a mao (ERP_MOTIVO). Auditoria: execucao manual sem motivo e execucao sem explicacao.';
ALTER TABLE erp_automation.job_execucao DROP CONSTRAINT IF EXISTS ck_job_execucao_automacao;
ALTER TABLE erp_automation.job_execucao ADD CONSTRAINT ck_job_execucao_automacao CHECK (automacao IN (
    'boletos', 'doc2you', 'credito', 'remessa_cobranca', 'retorno_cobranca',
    'remessa_pagamento', 'retorno_pagamento', 'finalizar_operacao',
    'controle'));   -- paridade CSV x banco e outras conferencias sem navegador

-- operador e motivo nascem com a execucao e nao mudam no fechamento
CREATE OR REPLACE FUNCTION erp_automation.fn_fechar_job_execucao_uma_vez()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'ativa' THEN
        RAISE EXCEPTION 'job_execucao % ja esta fechada (%); execucao fechada nao muda',
            OLD.id, OLD.status USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'ativa' OR NEW.terminado_em IS NULL THEN
        RAISE EXCEPTION 'job_execucao %: UPDATE so serve para FECHAR (status final + terminado_em)',
            OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.automacao IS DISTINCT FROM OLD.automacao
       OR NEW.job IS DISTINCT FROM OLD.job OR NEW.task_nome IS DISTINCT FROM OLD.task_nome
       OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.gatilho IS DISTINCT FROM OLD.gatilho
       OR NEW.ambiente IS DISTINCT FROM OLD.ambiente OR NEW.flag_ensaio IS DISTINCT FROM OLD.flag_ensaio
       OR NEW.apelido_credencial IS DISTINCT FROM OLD.apelido_credencial
       OR NEW.versao_codigo IS DISTINCT FROM OLD.versao_codigo
       OR NEW.iniciado_em IS DISTINCT FROM OLD.iniciado_em
       OR NEW.operador IS DISTINCT FROM OLD.operador OR NEW.motivo IS DISTINCT FROM OLD.motivo THEN
        RAISE EXCEPTION 'job_execucao %: so terminado_em, status, codigo_saida, qtd_itens e detalhe_json mudam no fechamento',
            OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- 5. Views de controle: as colunas do CSV, lidas do banco
--    "ultimo evento" = o mais recente do arquivo; o que aconteceu no processamento
--    (ocorrencias, criticas, divergencias, motivo) esta no evento, com o arquivo
--    como reserva para o que foi gravado antes desta migration.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW erp_automation.vw_arquivo_dia AS
    SELECT a.id                       AS arquivo_id,
           a.tipo_arquivo,
           a.sentido,
           a.nome_arquivo,
           a.conta_id,
           a.conta_label,
           a.qtd_registros,
           a.valor_total,
           a.md5,
           a.id_no_smart,
           u.tipo_evento              AS ultimo_evento,
           u.resultado                AS ultimo_resultado,
           u.ocorrido_em              AS ultimo_evento_em,
           a.registrado_em,
           a.fk_job_execucao          AS execucao_id,
           j.job,
           j.gatilho,
           j.flag_ensaio
      FROM erp_automation.arquivo a
      JOIN erp_automation.job_execucao j ON j.id = a.fk_job_execucao
      LEFT JOIN LATERAL (
           SELECT e.tipo_evento, e.resultado, e.ocorrido_em, e.detalhe_json
             FROM erp_automation.arquivo_evento e
            WHERE e.fk_arquivo = a.id
            ORDER BY e.ocorrido_em DESC, e.id DESC
            LIMIT 1) u ON true;
COMMENT ON VIEW erp_automation.vw_arquivo_dia IS
  'Um arquivo por linha com o ultimo evento e a execucao que o registrou. Filtre por registrado_em.';

CREATE OR REPLACE VIEW erp_automation.vw_controle_retorno AS
    SELECT a.id                                        AS arquivo_id,
           a.tipo_arquivo,
           a.nome_arquivo                              AS arquivo,
           a.detalhe_json ->> 'nome_smart'             AS nome_smart,
           a.md5                                       AS hash,
           a.sha256,
           a.conta_id                                  AS conta,
           a.qtd_registros                             AS titulos,
           a.valor_total,
           (u.tipo_evento = 'processado')              AS processado,
           u.tipo_evento                               AS ultimo_evento,
           coalesce(u.detalhe_json -> 'ocorrencias', a.detalhe_json -> 'ocorrencias')   AS ocorrencias,
           coalesce((u.detalhe_json ->> 'qtd_criticas')::int,
                    (a.detalhe_json ->> 'qtd_criticas')::int)                          AS criticas,
           coalesce(u.detalhe_json -> 'divergencias', a.detalhe_json -> 'divergencias') AS divergencias,
           coalesce(u.resultado, a.detalhe_json ->> 'motivo')                           AS motivo,
           a.registrado_em                             AS quando,
           a.fk_job_execucao                           AS execucao_id
      FROM erp_automation.arquivo a
      LEFT JOIN LATERAL (
           SELECT e.tipo_evento, e.resultado, e.ocorrido_em, e.detalhe_json
             FROM erp_automation.arquivo_evento e
            WHERE e.fk_arquivo = a.id AND e.tipo_evento <> 'movido'
            ORDER BY e.ocorrido_em DESC, e.id DESC
            LIMIT 1) u ON true
     WHERE a.tipo_arquivo IN ('retorno_cobranca_cnab_400', 'retorno_bb');
COMMENT ON VIEW erp_automation.vw_controle_retorno IS
  'As colunas de data/robo_retorno/controle_processados.csv, lidas do banco (retorno de cobranca e BB).';

CREATE OR REPLACE VIEW erp_automation.vw_controle_remessa AS
    SELECT a.id                                        AS arquivo_id,
           a.tipo_arquivo,
           a.id_no_smart                               AS id,
           a.nome_arquivo                              AS arquivo,
           a.conta_label                               AS tipo,
           a.conta_id                                  AS conta,
           a.qtd_bytes                                 AS bytes,
           a.md5,
           a.qtd_registros                             AS titulos,
           a.registrado_em                             AS baixado_em,
           a.detalhe_json ->> 'nome_no_disco'          AS nome_no_disco,
           u.tipo_evento                               AS ultimo_evento,
           u.resultado                                 AS ultimo_resultado,
           a.fk_job_execucao                           AS execucao_id
      FROM erp_automation.arquivo a
      LEFT JOIN LATERAL (
           SELECT e.tipo_evento, e.resultado, e.ocorrido_em
             FROM erp_automation.arquivo_evento e
            WHERE e.fk_arquivo = a.id
            ORDER BY e.ocorrido_em DESC, e.id DESC
            LIMIT 1) u ON true
     WHERE a.tipo_arquivo IN ('remessa_cobranca_cnab_400', 'remessa_bb');
COMMENT ON VIEW erp_automation.vw_controle_remessa IS
  'As colunas de data/robo_remessa/controle_remessas.csv, lidas do banco; ultimo_evento diz se foi enviada, descartada ou cancelada.';

CREATE OR REPLACE VIEW erp_automation.vw_controle_pagamento AS
    SELECT a.id                                        AS arquivo_id,
           a.nome_arquivo                              AS arquivo,
           a.qtd_bytes                                 AS bytes,
           a.md5,
           a.qtd_registros                             AS titulos,
           (SELECT string_agg(t.id_titulo, ',' ORDER BY t.numero_linha)
              FROM erp_automation.arquivo_titulo t WHERE t.fk_arquivo = a.id) AS ids,
           (a.detalhe_json ->> 'qtd_pix')::int         AS pix,
           a.conta_id                                  AS conta,
           a.registrado_em                             AS quando,
           a.fk_job_execucao                           AS execucao_id
      FROM erp_automation.arquivo a
     WHERE a.tipo_arquivo = 'remessa_pagamento_cnab_240';
COMMENT ON VIEW erp_automation.vw_controle_pagamento IS
  'As colunas de data/robo_pagamento/controle_pagamentos.csv, lidas do banco.';

CREATE OR REPLACE VIEW erp_automation.vw_controle_retorno_pagamento AS
    SELECT a.id                                        AS arquivo_id,
           a.nome_arquivo                              AS arquivo,
           a.md5                                       AS hash,
           u.resultado                                 AS status_http,
           u.tipo_evento                               AS ultimo_evento,
           a.registrado_em                             AS quando,
           a.fk_job_execucao                           AS execucao_id
      FROM erp_automation.arquivo a
      LEFT JOIN LATERAL (
           SELECT e.tipo_evento, e.resultado, e.ocorrido_em
             FROM erp_automation.arquivo_evento e
            WHERE e.fk_arquivo = a.id
            ORDER BY e.ocorrido_em DESC, e.id DESC
            LIMIT 1) u ON true
     WHERE a.tipo_arquivo = 'retorno_pagamento_cnab_240';
COMMENT ON VIEW erp_automation.vw_controle_retorno_pagamento IS
  'As colunas de data/robo_retorno_pagamento/controle.csv, lidas do banco.';

CREATE OR REPLACE VIEW erp_automation.vw_job_execucao_ultima AS
    SELECT DISTINCT ON (j.job)
           j.id, j.automacao, j.job, j.task_nome, j.status, j.codigo_saida, j.gatilho,
           j.operador, j.motivo, j.flag_ensaio, j.iniciado_em, j.terminado_em,
           j.terminado_em - j.iniciado_em AS duracao, j.qtd_itens
      FROM erp_automation.job_execucao j
     ORDER BY j.job, j.iniciado_em DESC, j.id DESC;
COMMENT ON VIEW erp_automation.vw_job_execucao_ultima IS
  'A ultima execucao de cada job: o primeiro lugar a olhar quando alguem pergunta "rodou?".';

-- ---------------------------------------------------------------------------
-- 6. Permissoes: runtime le as views; leitores da casa idem
-- ---------------------------------------------------------------------------
GRANT SELECT ON erp_automation.vw_arquivo_dia,
                erp_automation.vw_controle_retorno,
                erp_automation.vw_controle_remessa,
                erp_automation.vw_controle_pagamento,
                erp_automation.vw_controle_retorno_pagamento,
                erp_automation.vw_job_execucao_ultima TO app_erp_automation;

DO $$
DECLARE
    leitor text;
BEGIN
    FOREACH leitor IN ARRAY ARRAY['dev_user', 'app_process_automation', 'app_data_hub',
                                  'app_hub_orch', 'app_forms_hub', 'app_crm', 'app_metas'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = leitor) THEN
            EXECUTE format('GRANT SELECT ON erp_automation.vw_arquivo_dia, erp_automation.vw_controle_retorno, '
                           'erp_automation.vw_controle_remessa, erp_automation.vw_controle_pagamento, '
                           'erp_automation.vw_controle_retorno_pagamento, erp_automation.vw_job_execucao_ultima TO %I', leitor);
        END IF;
    END LOOP;
END $$;

RESET ROLE;
COMMIT;
