-- erp_004_execucao_e_eventos.sql
--
-- O controle dos jobs sai do CSV e entra no banco, com as palavras do dicionario
-- da casa (decididas em 15-24/08/2026):
--
--   job          a unidade executavel - o que roda com um comando
--   execucao     uma rodada de job, com inicio, fim e resultado
--   evento       fato de negocio, NUNCA se apaga; sufixo _evento no schema do dono
--   auditoria    quem mudou o que; morara no schema `auditoria` quando nascer - NAO e
--                deste projeto criar; ate la, imutabilidade por dono e gatilho
--
-- O que motivou, medido em 18-21/09/2026: cinco jobs guardavam o que fizeram em
-- CSV no disco (368 remessas de pagamento, 772 de cobranca, 14.208 linhas de
-- retorno, 366 de retorno de pagamento, mais o placar do finalizador), sem chave
-- comum, sem integridade (25 linhas sem hash, 99 com dois estados ao mesmo tempo)
-- e com o proprio job podendo reescrever o historico. Padrao seguido: tabela de
-- controle de jobs + eventos so-de-insercao + registro de arquivo com sha256
-- (CYBERTEC "row change auditing", pg-audit-json, "ETL job control table").
--
-- Dono das tabelas: app_erp_automation_evento (sem login). app_erp_automation
-- so INSERE e LE - e fecha a execucao, uma vez, nas colunas de fechamento.
-- Sem posse, o runtime nao consegue devolver a si mesmo um UPDATE nem um DROP.
--
-- Re-executavel: IF NOT EXISTS / OR REPLACE em tudo; o ledger de aplicar.sh e quem
-- garante a aplicacao unica.

BEGIN;
-- os DROP TRIGGER IF EXISTS da primeira aplicacao nao precisam avisar
SET LOCAL client_min_messages TO warning;

-- ---------------------------------------------------------------------------
-- 1. A role dona das tabelas imutaveis
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_erp_automation_evento') THEN
        CREATE ROLE app_erp_automation_evento NOLOGIN;
        COMMENT ON ROLE app_erp_automation_evento IS
          'Dona das tabelas de execucao e evento do erp_automation. Sem login: existe '
          'para que app_erp_automation nao seja dona do proprio historico.';
    END IF;
END $$;

GRANT USAGE ON SCHEMA erp_automation TO app_erp_automation_evento;

-- O DONO DO SCHEMA derruba qualquer tabela dele - inclusive as que nao possui. A
-- erp_001 fez app_erp_automation dona do schema; com isso o runtime conseguiria um
-- DROP TABLE nas tabelas de evento (medido na bancada em 21/09/2026). O schema passa
-- para a role dos eventos; o runtime segue com USAGE e CREATE (o que ele usava).
-- As migrations continuam rodando como administrador, entao nada muda para elas.
ALTER SCHEMA erp_automation OWNER TO app_erp_automation_evento;
GRANT USAGE, CREATE ON SCHEMA erp_automation TO app_erp_automation;

-- ---------------------------------------------------------------------------
-- 2. job_execucao - uma linha por execucao de job (a tabela de controle)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS erp_automation.job_execucao (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    automacao          text        NOT NULL,
    job                text        NOT NULL,
    task_nome          text,
    run_id             text,
    gatilho            text        NOT NULL,
    ambiente           text        NOT NULL,
    flag_ensaio        boolean     NOT NULL,
    apelido_credencial text,
    versao_codigo      text,
    iniciado_em        timestamptz NOT NULL DEFAULT now(),
    terminado_em       timestamptz,
    status             text        NOT NULL DEFAULT 'ativa',
    codigo_saida       integer,
    qtd_itens          integer,
    detalhe_json       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_job_execucao_automacao CHECK (automacao IN (
        'boletos', 'doc2you', 'credito', 'remessa_cobranca', 'retorno_cobranca',
        'remessa_pagamento', 'retorno_pagamento', 'finalizar_operacao')),
    CONSTRAINT ck_job_execucao_gatilho  CHECK (gatilho  IN ('cron', 'manual', 'api')),
    CONSTRAINT ck_job_execucao_ambiente CHECK (ambiente IN ('container', 'sandbox')),
    CONSTRAINT ck_job_execucao_status   CHECK (status   IN ('ativa', 'sucesso', 'falha', 'abandonada')),
    -- "execucao ativa" = comecou e nao terminou; qualquer outro status exige o fim
    CONSTRAINT ck_job_execucao_fechamento CHECK ((status = 'ativa') = (terminado_em IS NULL))
);
ALTER TABLE erp_automation.job_execucao OWNER TO app_erp_automation_evento;

CREATE UNIQUE INDEX IF NOT EXISTS uq_job_execucao_run_id
    ON erp_automation.job_execucao (run_id) WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_job_execucao_job_iniciado_em
    ON erp_automation.job_execucao (job, iniciado_em DESC);
CREATE INDEX IF NOT EXISTS ix_job_execucao_status
    ON erp_automation.job_execucao (status) WHERE status = 'ativa';

COMMENT ON TABLE erp_automation.job_execucao IS
  'Uma linha por execucao de job deste projeto. Abre com status ativa; fecha UMA vez '
  '(sucesso|falha|abandonada), so nas colunas de fechamento. run_id liga a '
  'hub_orchestration.task_execucao quando o gatilho foi o hub.';
COMMENT ON COLUMN erp_automation.job_execucao.automacao IS 'O fluxo a que o job pertence (dicionario: automacao = conjunto de jobs).';
COMMENT ON COLUMN erp_automation.job_execucao.job IS 'Nome do job (verbo_objeto), ex.: finalizar_operacao_aguardando_assinatura.';
COMMENT ON COLUMN erp_automation.job_execucao.gatilho IS 'O que disparou: cron (hub), manual (docker exec a mao) ou api.';
COMMENT ON COLUMN erp_automation.job_execucao.flag_ensaio IS 'true = DRY: conferiu e registrou, nao agiu.';
COMMENT ON COLUMN erp_automation.job_execucao.apelido_credencial IS 'Apelido da identidade usada (ex.: GSMARTPWD3). NUNCA a senha.';
COMMENT ON COLUMN erp_automation.job_execucao.status IS 'ativa | sucesso | falha | abandonada (morreu sem marcar o fim; ver vw_job_execucao_abandonada).';

-- Fecha uma vez, e so nas colunas de fechamento. Tudo o mais e recusado.
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
       OR NEW.iniciado_em IS DISTINCT FROM OLD.iniciado_em THEN
        RAISE EXCEPTION 'job_execucao %: so terminado_em, status, codigo_saida, qtd_itens e detalhe_json mudam no fechamento',
            OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS tg_job_execucao_fecha_uma_vez ON erp_automation.job_execucao;
CREATE TRIGGER tg_job_execucao_fecha_uma_vez
    BEFORE UPDATE ON erp_automation.job_execucao
    FOR EACH ROW EXECUTE FUNCTION erp_automation.fn_fechar_job_execucao_uma_vez();

-- ---------------------------------------------------------------------------
-- 3. O gatilho de imutabilidade das tabelas de evento
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION erp_automation.fn_recusar_alteracao_evento()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% em %.% e proibido: evento nunca se apaga nem muda. Corrigir e gravar OUTRO evento.',
        TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END $$;

-- ---------------------------------------------------------------------------
-- 4. operacao_evento - fato sobre uma operacao do Smart; so insercao
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS erp_automation.operacao_evento (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fk_job_execucao  bigint      NOT NULL REFERENCES erp_automation.job_execucao (id),
    id_operacao      integer     NOT NULL,
    ocorrido_em      timestamptz NOT NULL DEFAULT now(),
    tipo_evento      text        NOT NULL,
    resultado        text,
    cedente          text,
    valor_liquido    numeric(15,2),
    pendencias_json  jsonb,
    hash_pendencias  text,
    detalhe_json     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_operacao_evento_tipo CHECK (tipo_evento IN (
        'avaliada', 'finalizar_clicado', 'finalizada', 'finalizacao_falhou',
        'finalizada_por_outro', 'aviso_enviado')),
    CONSTRAINT ck_operacao_evento_resultado_avaliada CHECK (
        tipo_evento <> 'avaliada' OR resultado IN ('FINALIZARIA', 'BARRADA', 'ERRO'))
);
ALTER TABLE erp_automation.operacao_evento OWNER TO app_erp_automation_evento;

-- uma finalizacao confirmada por operacao; cliques podem repetir (retentativa)
CREATE UNIQUE INDEX IF NOT EXISTS uq_operacao_evento_finalizada
    ON erp_automation.operacao_evento (id_operacao) WHERE tipo_evento = 'finalizada';
-- a mesma pendencia nao e avisada duas vezes para a mesma operacao
CREATE UNIQUE INDEX IF NOT EXISTS uq_operacao_evento_aviso
    ON erp_automation.operacao_evento (id_operacao, hash_pendencias)
    WHERE tipo_evento = 'aviso_enviado' AND hash_pendencias IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_operacao_evento_operacao_ocorrido_em
    ON erp_automation.operacao_evento (id_operacao, ocorrido_em DESC);
CREATE INDEX IF NOT EXISTS ix_operacao_evento_execucao
    ON erp_automation.operacao_evento (fk_job_execucao);

COMMENT ON TABLE erp_automation.operacao_evento IS
  'Fato de negocio sobre uma operacao, gravado pelo job que o produziu. Nunca muda: '
  'correcao e outro evento. avaliada carrega o veredito (resultado) e as pendencias; '
  'finalizar_clicado e o instante ANTES do clique; finalizada e a confirmacao.';
COMMENT ON COLUMN erp_automation.operacao_evento.resultado IS
  'avaliada: FINALIZARIA|BARRADA|ERRO · finalizada: fonte da confirmacao (smart|tela|banco) · aviso_enviado: ok|falhou';
COMMENT ON COLUMN erp_automation.operacao_evento.hash_pendencias IS
  'sha256 das pendencias normalizadas; e o que impede avisar a mesma coisa duas vezes.';

DROP TRIGGER IF EXISTS tg_operacao_evento_so_insere ON erp_automation.operacao_evento;
CREATE TRIGGER tg_operacao_evento_so_insere
    BEFORE UPDATE OR DELETE ON erp_automation.operacao_evento
    FOR EACH ROW EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();
DROP TRIGGER IF EXISTS tg_operacao_evento_sem_truncate ON erp_automation.operacao_evento;
CREATE TRIGGER tg_operacao_evento_sem_truncate
    BEFORE TRUNCATE ON erp_automation.operacao_evento
    FOR EACH STATEMENT EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();

-- ---------------------------------------------------------------------------
-- 5. operacao_pagamento_linha - a grade de pagamento no instante da avaliacao
--    Carrega CPF/CNPJ e chave PIX (mascarada + sha256): leitura RESTRITA.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS erp_automation.operacao_pagamento_linha (
    fk_operacao_evento  bigint   NOT NULL REFERENCES erp_automation.operacao_evento (id),
    numero_linha        smallint NOT NULL,
    tipo_pagamento      text,
    tipo_pix            text,
    chave_pix_mascarada text,
    sha256_chave_pix    text,
    conta_origem        text,
    numero_documento    text,
    conta_destino       text,
    banco               text,
    agencia             text,
    tipo_conta          text,
    conta_corrente      text,
    favorecido          text,
    cpf_cnpj_favorecido text,
    id_transacao        text,
    data_vencimento     date,
    valor_pagamento     numeric(15,2),
    flag_sp             boolean,
    PRIMARY KEY (fk_operacao_evento, numero_linha)
);
ALTER TABLE erp_automation.operacao_pagamento_linha OWNER TO app_erp_automation_evento;
COMMENT ON TABLE erp_automation.operacao_pagamento_linha IS
  'Foto da grade de pagamento no instante da avaliacao (uma op pode ter pagamento '
  'dividido). Dado sensivel: sem SELECT para os leitores gerais do schema.';

DROP TRIGGER IF EXISTS tg_operacao_pagamento_linha_so_insere ON erp_automation.operacao_pagamento_linha;
CREATE TRIGGER tg_operacao_pagamento_linha_so_insere
    BEFORE UPDATE OR DELETE ON erp_automation.operacao_pagamento_linha
    FOR EACH ROW EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();
DROP TRIGGER IF EXISTS tg_operacao_pagamento_linha_sem_truncate ON erp_automation.operacao_pagamento_linha;
CREATE TRIGGER tg_operacao_pagamento_linha_sem_truncate
    BEFORE TRUNCATE ON erp_automation.operacao_pagamento_linha
    FOR EACH STATEMENT EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();

-- ---------------------------------------------------------------------------
-- 6. arquivo - um arquivo gerado ou recebido (o "load control record")
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS erp_automation.arquivo (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fk_job_execucao  bigint      NOT NULL REFERENCES erp_automation.job_execucao (id),
    tipo_arquivo     text        NOT NULL,
    sentido          text        NOT NULL,
    nome_arquivo     text        NOT NULL,
    sha256           text        NOT NULL,
    qtd_bytes        bigint      NOT NULL,
    qtd_registros    integer,
    valor_total      numeric(15,2),
    conta_id         text,
    conta_label      text,
    origem_caminho   text,
    destino_caminho  text,
    registrado_em    timestamptz NOT NULL DEFAULT now(),
    detalhe_json     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_arquivo_tipo CHECK (tipo_arquivo IN (
        'remessa_cobranca_cnab_400', 'retorno_cobranca_cnab_400',
        'remessa_pagamento_cnab_240', 'retorno_pagamento_cnab_240',
        'remessa_bb', 'retorno_bb', 'exportacao_csv')),
    CONSTRAINT ck_arquivo_sentido CHECK (sentido IN ('gerado', 'recebido')),
    CONSTRAINT ck_arquivo_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_arquivo_tipo_sha256 UNIQUE (tipo_arquivo, sha256)
);
ALTER TABLE erp_automation.arquivo OWNER TO app_erp_automation_evento;
CREATE INDEX IF NOT EXISTS ix_arquivo_tipo_registrado_em
    ON erp_automation.arquivo (tipo_arquivo, registrado_em DESC);
COMMENT ON TABLE erp_automation.arquivo IS
  'Um arquivo bancario gerado ou recebido, ou uma exportacao. O mesmo conteudo '
  '(tipo + sha256) nao entra duas vezes. O banco entra no tipo quando o formato e dele (DEC-053).';

DROP TRIGGER IF EXISTS tg_arquivo_so_insere ON erp_automation.arquivo;
CREATE TRIGGER tg_arquivo_so_insere
    BEFORE UPDATE OR DELETE ON erp_automation.arquivo
    FOR EACH ROW EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();
DROP TRIGGER IF EXISTS tg_arquivo_sem_truncate ON erp_automation.arquivo;
CREATE TRIGGER tg_arquivo_sem_truncate
    BEFORE TRUNCATE ON erp_automation.arquivo
    FOR EACH STATEMENT EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();

CREATE TABLE IF NOT EXISTS erp_automation.arquivo_titulo (
    fk_arquivo          bigint  NOT NULL REFERENCES erp_automation.arquivo (id),
    numero_linha        integer NOT NULL,
    id_titulo           text,
    id_operacao         integer,
    id_pagamento_smart  text,
    codigo_ocorrencia   text,
    valor_titulo        numeric(15,2),
    flag_pix            boolean,
    PRIMARY KEY (fk_arquivo, numero_linha)
);
ALTER TABLE erp_automation.arquivo_titulo OWNER TO app_erp_automation_evento;
CREATE INDEX IF NOT EXISTS ix_arquivo_titulo_titulo ON erp_automation.arquivo_titulo (id_titulo);
CREATE INDEX IF NOT EXISTS ix_arquivo_titulo_operacao ON erp_automation.arquivo_titulo (id_operacao);
COMMENT ON TABLE erp_automation.arquivo_titulo IS 'Um titulo dentro de um arquivo; o que hoje e a coluna ids separada por virgula no CSV.';

DROP TRIGGER IF EXISTS tg_arquivo_titulo_so_insere ON erp_automation.arquivo_titulo;
CREATE TRIGGER tg_arquivo_titulo_so_insere
    BEFORE UPDATE OR DELETE ON erp_automation.arquivo_titulo
    FOR EACH ROW EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();

CREATE TABLE IF NOT EXISTS erp_automation.arquivo_evento (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fk_arquivo       bigint      NOT NULL REFERENCES erp_automation.arquivo (id),
    fk_job_execucao  bigint      NOT NULL REFERENCES erp_automation.job_execucao (id),
    ocorrido_em      timestamptz NOT NULL DEFAULT now(),
    tipo_evento      text        NOT NULL,
    resultado        text,
    detalhe_json     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_arquivo_evento_tipo CHECK (tipo_evento IN (
        'gerado', 'enviado', 'recebido', 'processado', 'rejeitado', 'retido'))
);
ALTER TABLE erp_automation.arquivo_evento OWNER TO app_erp_automation_evento;
CREATE INDEX IF NOT EXISTS ix_arquivo_evento_arquivo ON erp_automation.arquivo_evento (fk_arquivo, ocorrido_em DESC);
COMMENT ON TABLE erp_automation.arquivo_evento IS 'O que aconteceu com o arquivo, na ordem: gerado, enviado, recebido, processado, rejeitado, retido.';

DROP TRIGGER IF EXISTS tg_arquivo_evento_so_insere ON erp_automation.arquivo_evento;
CREATE TRIGGER tg_arquivo_evento_so_insere
    BEFORE UPDATE OR DELETE ON erp_automation.arquivo_evento
    FOR EACH ROW EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();
DROP TRIGGER IF EXISTS tg_arquivo_evento_sem_truncate ON erp_automation.arquivo_evento;
CREATE TRIGGER tg_arquivo_evento_sem_truncate
    BEFORE TRUNCATE ON erp_automation.arquivo_evento
    FOR EACH STATEMENT EXECUTE FUNCTION erp_automation.fn_recusar_alteracao_evento();

-- ---------------------------------------------------------------------------
-- 7. Views - leitura para gente (nomes do dicionario: execucao ativa/abandonada)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW erp_automation.vw_job_execucao_ativa AS
    SELECT * FROM erp_automation.job_execucao WHERE status = 'ativa';
COMMENT ON VIEW erp_automation.vw_job_execucao_ativa IS 'Execucoes que comecaram e ainda nao fecharam.';

CREATE OR REPLACE VIEW erp_automation.vw_job_execucao_abandonada AS
    SELECT * FROM erp_automation.job_execucao
     WHERE status = 'ativa' AND iniciado_em < now() - interval '2 hours';
COMMENT ON VIEW erp_automation.vw_job_execucao_abandonada IS
  'Morreu sem marcar o fim: ativa ha mais de 2 h. O timeout mais longo do hub para este container e 45 min.';

CREATE OR REPLACE VIEW erp_automation.vw_operacao_finalizacao_aberta AS
    SELECT c.*
      FROM erp_automation.operacao_evento c
     WHERE c.tipo_evento = 'finalizar_clicado'
       AND NOT EXISTS (
           SELECT 1 FROM erp_automation.operacao_evento t
            WHERE t.id_operacao = c.id_operacao
              AND t.tipo_evento IN ('finalizada', 'finalizacao_falhou', 'finalizada_por_outro')
              AND t.ocorrido_em >= c.ocorrido_em);
COMMENT ON VIEW erp_automation.vw_operacao_finalizacao_aberta IS
  'Clique registrado sem resultado depois: o ciclo seguinte confere no Smart antes de agir.';

CREATE OR REPLACE VIEW erp_automation.vw_operacao_ciclo AS
    SELECT id_operacao,
           max(ocorrido_em) FILTER (WHERE tipo_evento = 'avaliada')          AS avaliada_em,
           (array_agg(resultado ORDER BY ocorrido_em DESC)
                FILTER (WHERE tipo_evento = 'avaliada'))[1]                  AS ultimo_veredito,
           count(*) FILTER (WHERE tipo_evento = 'avaliada')                  AS qtd_avaliacoes,
           max(ocorrido_em) FILTER (WHERE tipo_evento = 'finalizar_clicado') AS clicado_em,
           max(ocorrido_em) FILTER (WHERE tipo_evento = 'finalizada')        AS finalizada_em,
           max(ocorrido_em) FILTER (WHERE tipo_evento = 'finalizada_por_outro') AS finalizada_por_outro_em,
           max(ocorrido_em) FILTER (WHERE tipo_evento = 'aviso_enviado')     AS avisada_em,
           max(cedente)                                                      AS cedente,
           max(valor_liquido)                                                AS valor_liquido
      FROM erp_automation.operacao_evento
     GROUP BY id_operacao;
COMMENT ON VIEW erp_automation.vw_operacao_ciclo IS 'Uma linha por operacao: do veredito ao aviso.';

-- O placar compara o job com o operador, pelo espelho do Smart. So existe onde o
-- espelho existe (na bancada nao existe; em producao e trs.operacao_desagio).
DO $$
BEGIN
    IF to_regclass('trs.operacao_desagio') IS NOT NULL THEN
        EXECUTE $v$
            CREATE OR REPLACE VIEW erp_automation.vw_operacao_placar AS
            SELECT c.id_operacao, c.ultimo_veredito, c.avaliada_em, c.finalizada_em,
                   e.etapa AS etapa_no_espelho, e.flag_operacao_concluida,
                   e.data_finalizacao, e.flag_pagamento_realizado, e.data_pagamento_operacao,
                   CASE
                     WHEN c.ultimo_veredito = 'FINALIZARIA' AND e.flag_operacao_concluida THEN 'concorda'
                     WHEN c.ultimo_veredito = 'BARRADA'     AND e.flag_operacao_concluida THEN 'operador_finalizou_barrada'
                     WHEN c.ultimo_veredito = 'FINALIZARIA' AND NOT coalesce(e.flag_operacao_concluida, false) THEN 'aguardando_operador'
                     ELSE 'sem_comparacao'
                   END AS comparacao
              FROM erp_automation.vw_operacao_ciclo c
              LEFT JOIN trs.operacao_desagio e ON e.id_operacao = c.id_operacao
        $v$;
        EXECUTE 'COMMENT ON VIEW erp_automation.vw_operacao_placar IS '
                '''O veredito do job comparado com o que o operador fez, pelo espelho do Smart '
                '(que atrasa: a data_finalizacao la e so data, sem hora).''';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 8. Permissoes
--    Runtime: insere e le; fecha a execucao (UPDATE limitado pelo gatilho).
--    Leitores da casa: tudo, MENOS a grade de pagamento (CPF, PIX).
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON erp_automation.job_execucao TO app_erp_automation;
GRANT SELECT, INSERT ON erp_automation.operacao_evento,
                       erp_automation.operacao_pagamento_linha,
                       erp_automation.arquivo,
                       erp_automation.arquivo_titulo,
                       erp_automation.arquivo_evento TO app_erp_automation;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA erp_automation TO app_erp_automation;
GRANT SELECT ON erp_automation.vw_job_execucao_ativa,
                erp_automation.vw_job_execucao_abandonada,
                erp_automation.vw_operacao_finalizacao_aberta,
                erp_automation.vw_operacao_ciclo TO app_erp_automation;

DO $$
DECLARE
    leitor text;
BEGIN
    FOREACH leitor IN ARRAY ARRAY['dev_user', 'app_process_automation', 'app_data_hub',
                                  'app_hub_orch', 'app_forms_hub', 'app_crm', 'app_metas'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = leitor) THEN
            -- USAGE no schema: a erp_001 ja dava, mas a ACL real divergiu dela (medido em
            -- 18/09/2026: scatambulo tinha, data_hub e hub nao). Aqui fica explicito.
            EXECUTE format('GRANT USAGE ON SCHEMA erp_automation TO %I', leitor);
            EXECUTE format('GRANT SELECT ON erp_automation.job_execucao, erp_automation.operacao_evento, '
                           'erp_automation.arquivo, erp_automation.arquivo_titulo, erp_automation.arquivo_evento, '
                           'erp_automation.vw_job_execucao_ativa, erp_automation.vw_job_execucao_abandonada, '
                           'erp_automation.vw_operacao_finalizacao_aberta, erp_automation.vw_operacao_ciclo TO %I', leitor);
            IF to_regclass('erp_automation.vw_operacao_placar') IS NOT NULL THEN
                EXECUTE format('GRANT SELECT ON erp_automation.vw_operacao_placar TO %I', leitor);
            END IF;
        END IF;
    END LOOP;
END $$;

-- A erp_001 deixou um DEFAULT PRIVILEGES que da SELECT aos leitores em toda tabela
-- criada por app_erp_automation. As tabelas desta migration sao de outro dono, entao
-- esse default NAO as alcanca - e e por isso que a grade de pagamento fica fechada.
REVOKE ALL ON erp_automation.operacao_pagamento_linha FROM PUBLIC;

COMMIT;
