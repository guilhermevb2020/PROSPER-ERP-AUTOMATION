-- erp_002_revogar_heranca_dev_user.sql
--
-- Fecha a fronteira que a role app_erp_automation existe para criar, e que hoje NAO
-- existe na pratica.
--
-- O DIAGNOSTICO, medido ao vivo em 12/08/2026
-- ---------------------------------------------------------------------------------
-- `app_erp_automation` e membro de `dev_user` com `rolinherit = t` — o "andaime"
-- registrado no CLAUDE.md, posto para que a troca de credencial nao mudasse
-- comportamento nenhum. Ele cumpriu esse papel, e o efeito colateral e que a role
-- herda TUDO o que `dev_user` pode. Provado por transacao com ROLLBACK:
--
--     SET ROLE app_erp_automation;
--     DELETE FROM dwh.dim_cedentes          WHERE false;  -->  DELETE 0   (permitido)
--     DELETE FROM dwh.fct_titulos_quitados  WHERE false;  -->  DELETE 0   (permitido)
--     DELETE FROM trs.bancos_cobradores     WHERE false;  -->  DELETE 0   (permitido)
--     CREATE TABLE stg.zz_teste_permissao (x int);        -->  CREATE TABLE
--
-- `dwh.fct_titulos_quitados` e a tabela que decide se um titulo foi pago — base da
-- medicao de cobranca indevida do ADR-016. Um robo de boleto podia apaga-la.
--
-- ⚠️ Isto ATUALIZA o teste registrado no diagnostico de 03/08, que mediu
-- `app_erp_automation -> UPDATE trs.bancos_cobradores` como `permission denied`.
-- Aquele resultado era verdadeiro no momento em que foi medido; a heranca de
-- `dev_user` foi concedida depois, e o negou-se virou permite-se sem que nada no
-- desenho tivesse mudado.
--
-- Alcance efetivo de escrita hoje, so nos 13 schemas principais: 386 tabelas.
-- Alcance usado: 4.
--
-- POR QUE REVOGAR CONCESSAO DIRETA NAO BASTARIA
-- ---------------------------------------------------------------------------------
-- Enquanto a heranca existir, revogar GRANT direto e teatro: a permissao volta por
-- `dev_user`. A revogacao da associacao e o unico passo que muda o comportamento.
--
-- POR QUE E SEGURO — medido, nao inferido
-- ---------------------------------------------------------------------------------
-- Censo do codigo casado contra os 836 objetos reais do banco (nao grep por lista de
-- schemas): este projeto escreve em 4 objetos e le 10. Nenhum usa `search_path` —
-- toda referencia e qualificada, entao o censo e completo.
--
--   * os 4 de escrita: movidos para `erp_automation` na erp_001, onde a role e DONA
--   * os 10 de leitura: todos com SELECT concedido DIRETAMENTE (verificado em
--     `aclexplode(relacl)`), nenhum dependente da herança
--   * `USAGE` de schema: direto em api, bi, int, stg, trs, operacional, public
--
-- REVERSAO, se algo inesperado quebrar
-- ---------------------------------------------------------------------------------
--     GRANT dev_user TO app_erp_automation;
--
-- Uma linha, efeito imediato, sem restart.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. A herança — o passo que de fato cria a fronteira
-- ---------------------------------------------------------------------------
REVOKE dev_user FROM app_erp_automation;

-- ---------------------------------------------------------------------------
-- 2. A escrita direta que sobrou e nao e usada
--
--    Concessoes diretas de escrita medidas em 12/08, DEPOIS da erp_001 mover as 4
--    tabelas para fora: data_hub 26, stg 30 (+27 views), operacional 3, int 4.
--    Nenhuma e usada por este projeto. SELECT fica — leitura e por desenho.
-- ---------------------------------------------------------------------------
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA data_hub, stg, operacional, int
    FROM app_erp_automation;

REVOKE USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA data_hub, stg, operacional, int
    FROM app_erp_automation;

-- ---------------------------------------------------------------------------
-- 3. Privilegio-padrao — sem isto, a folga volta sozinha
--
--    `ALTER DEFAULT PRIVILEGES` de `prospere` e de `dev_user` reconcedia `arwd` a
--    esta role em toda tabela NOVA de stg, int e operacional. Revogar so o presente
--    deixaria a proxima tabela criada reabrir o buraco, em silencio.
-- ---------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE prospere IN SCHEMA stg, int, operacional
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLES FROM app_erp_automation;

ALTER DEFAULT PRIVILEGES FOR ROLE dev_user IN SCHEMA stg, int, operacional
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLES FROM app_erp_automation;

-- ---------------------------------------------------------------------------
-- 4. Garantir a leitura de que o projeto realmente depende
--    Explicito, para nao depender de ACL herdada de lugar nenhum.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA api, bi, int, stg, trs TO app_erp_automation;

GRANT SELECT ON
    api.prosper_erp_titulos_aberto_conta_bancaria,
    api.erp_operacoes_padrao_dia_anterior,
    api.erp_operacoes_ocultas_dia_anterior,
    api.erp_financeiro_logins_atrasos_oculto,
    bi.operacional_operacao_desagio,
    trs.operacao_desagio,
    stg.doc2you_pendencia,
    stg.robo_analise_cedente,
    stg.robo_analise_sacado,
    int.enriquecimento_sacado
    TO app_erp_automation;

COMMIT;

-- ---------------------------------------------------------------------------
-- VERIFICACAO — rode depois de aplicar. O esperado esta ao lado de cada linha.
-- ---------------------------------------------------------------------------
--   BEGIN;
--   SET ROLE app_erp_automation;
--   INSERT INTO erp_automation.boleto_envio_log (...);            -- permitido
--   SELECT count(*) FROM trs.operacao_desagio;                   -- permitido
--   SELECT count(*) FROM api.erp_operacoes_padrao_dia_anterior;   -- permitido
--   DELETE FROM dwh.fct_titulos_quitados WHERE false;             -- permission denied
--   CREATE TABLE stg.zz (x int);                                  -- permission denied
--   ROLLBACK;
