# =============================================================================================
# ARQUIVO: titulos_abertos_dias_corridos.py
# CAMINHO: src/processors/api/titulos_abertos_dias_corridos.py
# VERSÃO: v5.4 (Padronizado com extração de schema como operacao_desagio)
# AUTOR: ChatGPT (padrão Gemini) & Guilherme Veloso
# DATA: 2025-01-05 (MODIFICADO: Schema extraído do nome completo da tabela/procedure)
# DESCRIÇÃO:
#   ETL para títulos em aberto - Dias Corridos.
#   - 100% via settings: url_base, campos de data, tipo, flags, etc.
#   - Requisições via api_utils + smart_auth (OAuth2).
#   - Retry visual, replace_table, logs, status final, tempo de execução.
#   - Remoção de CSV conforme flag do recurso.
#   - Suporte a --simulacao (MODIFICADO: agora executa operações BD em simulação).
#   - Terminal com exibição limpa usando blocos e truncamento de URLs.
#   - Extração automática de schema quando especificado no formato "schema.tabela"
# =============================================================================================

# =============================================================================================
# 1.0 IMPORTAÇÕES BÁSICAS E CONFIGS DE AMBIENTE
# =============================================================================================
import os
import sys
import time
import pandas as pd
pd.set_option('future.no_silent_downcasting', True)
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
import logging

# =============================================================================================
# 2.0 IMPORTS DO PROJETO (TRY/EXCEPT PADRÃO)
# =============================================================================================
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)
try:
    from src.config import settings as config
    from src.common import repository as repo
    from src.common.file_utils import apply_column_mappings_and_structure
    from src.core.logging_config import get_logger
    from src.common.reporting_utils import log_final_status
    from src.common.execution_tracker import registrar_execucao
    from src.common.api_utils import api_request
    from src.common.smart_auth import renovar_token_auto
    from src.common.display_utils import bloco_api, bloco_api_inicio, bloco_bd, bloco_resumo_final
except ImportError as e:
    logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    logging.critical(f"Erro crítico importação: {e}.", exc_info=True)
    sys.exit(10)

# =============================================================================================
# 3.0 CONFIGURAÇÃO DO SCRIPT E LOGGING
# =============================================================================================
logger = get_logger(__name__)
CFG_SCRIPT_NAME = "titulos_abertos_dias_corridos"
PROCESSADOR = CFG_SCRIPT_NAME
try:
    CFG_SCRIPT = config.recursos[CFG_SCRIPT_NAME]
except KeyError:
    logger.critical(f"Config para '{CFG_SCRIPT_NAME}' não encontrada.")
    sys.exit(11)

# =============================================================================================
# 4.0 FUNÇÃO PRINCIPAL DE PROCESSAMENTO DO SCRIPT (SETTINGS-DRIVEN)
# =============================================================================================
def processar_titulos_abertos_dias_corridos(modo_simulacao: bool = False) -> dict:
    script_start_time = time.time()
    logger.info(f"Função ETL '{CFG_SCRIPT_NAME}' EXECUTANDO. Modo Simulação ATIVO: {modo_simulacao}")

    URL_DISPLAY_MAX_LEN = 100

    mensagens_api_bloco: List[str] = []
    mensagens_bd_bloco: List[str] = []

    try:
        # 4.1 Definição do período de consulta
        dias_retroativos = int(getattr(CFG_SCRIPT, "dias_retroativos", 30))
        hoje = datetime.today()
        data_fim_obj = hoje
        data_inicio_obj = hoje - timedelta(days=dias_retroativos)
        ini_str = data_inicio_obj.strftime("%d/%m/%Y")
        fim_str = data_fim_obj.strftime("%d/%m/%Y")
        referencia_periodo_log = f"[{ini_str} → {fim_str}]"

        csv_base_name = getattr(CFG_SCRIPT, "csv_base_filename", CFG_SCRIPT_NAME)
        nome_arquivo_periodo = f"{csv_base_name}_{data_inicio_obj.strftime('%Y_%m_%d')}.csv"
        download_dir_path_str = getattr(config, "DOWNLOAD_ROOT", os.path.join(os.getcwd(), "data", "raw_inputs"))
        download_dir = Path(download_dir_path_str)
        download_dir.mkdir(parents=True, exist_ok=True)
        temp_path = download_dir / nome_arquivo_periodo

        sucesso_execucao = False
        df = pd.DataFrame()
        
        logger.info(f"ETL '{CFG_SCRIPT_NAME}' p/ {dias_retroativos}d: {referencia_periodo_log}. Sim: {modo_simulacao}")
        logger.info(f"Arquivo CSV destino: {temp_path}")

        # 4.2 Montagem dinâmica da URL da API (100% settings)
        url_base_api = getattr(CFG_SCRIPT, "url_base", None)
        if not url_base_api:
            raise RuntimeError("Configuração API: URL base não definida.")

        param_tipo_nome = "tipo"
        param_tipo_valor = getattr(CFG_SCRIPT, "param_tipo_api", "abertos")
        param_data_inicio_nome = getattr(CFG_SCRIPT, "param_data_inicio_nome", "emissaoIni")
        param_data_fim_nome = getattr(CFG_SCRIPT, "param_data_fim_nome", "emissaoFim")
        params_api_dict = {
            param_tipo_nome: param_tipo_valor,
            "tipoSaida": getattr(CFG_SCRIPT, "tipo_saida_param", "csv"),
            param_data_inicio_nome: ini_str,
            param_data_fim_nome: fim_str
        }
        url_api_final = url_base_api.rstrip("/") + "?" + urlencode(params_api_dict)
        headers_api = getattr(CFG_SCRIPT, "headers", {"Accept": "application/json"})
        max_retries_api = int(getattr(CFG_SCRIPT, "max_attempts", 10))
        timeout_req = getattr(CFG_SCRIPT, "timeout_request", 60)

        # 4.3 Obtenção do CSV (Normal ou Simulação)
        bloco_api_inicio(PROCESSADOR)
        mensagens_api_bloco.append(f"Solicitando link CSV para o período: {referencia_periodo_log}")
        
        if len(url_api_final) > URL_DISPLAY_MAX_LEN:
            url_display = url_api_final[:URL_DISPLAY_MAX_LEN - 3] + "..."
            mensagens_api_bloco.append(f"URL da API (truncada para terminal): {url_display}")
            logger.info(f"URL da API (completa no log de arquivo): {url_api_final}")
        else:
            mensagens_api_bloco.append(f"URL da API: {url_api_final}")

        csv_url = None
        if not modo_simulacao:
            resp = api_request(
                url=url_api_final,
                method="GET",
                token_func=lambda: renovar_token_auto(),
                renovar_token_func=lambda: renovar_token_auto(),
                headers=headers_api,
                params=None,
                max_retries=max_retries_api,
                timeout=timeout_req,
                ciclo=referencia_periodo_log
            )
            
            mensagens_api_bloco.append(f"Resposta JSON da API (primeiros 500 caracteres): {str(resp.get('json'))[:500]}")
            
            if resp.get("success") and "url" in resp.get("json", {}).get("relatorio", {}):
                csv_url = resp["json"]["relatorio"]["url"]
                if len(csv_url) > URL_DISPLAY_MAX_LEN:
                    csv_url_display = csv_url[:URL_DISPLAY_MAX_LEN - 3] + "..."
                    mensagens_api_bloco.append(f"Link CSV retornado (truncado para terminal): {csv_url_display}")
                    logger.info(f"Link CSV retornado (completo no log de arquivo): {csv_url}")
                else:
                    mensagens_api_bloco.append(f"Link CSV retornado: {csv_url}")
                mensagens_api_bloco.append("Link do CSV recebido (tentando baixar arquivo...)")
            else:
                msg_falha_api = resp.get("mensagem") or "Falha desconhecida ao obter link CSV"
                mensagens_api_bloco.append(f"Falha ao obter o link CSV. Erro: {msg_falha_api}")
                bloco_api(mensagens_api_bloco)
                raise RuntimeError(f"Falha ao obter link CSV da API após {max_retries_api} tentativas: {msg_falha_api}")
            
            # Baixar CSV
            timeout_download_cfg = getattr(CFG_SCRIPT, "timeout_download", 300)
            try:
                import requests
                with requests.get(csv_url, stream=True, timeout=timeout_download_cfg) as r_download:
                    r_download.raise_for_status()
                    with open(temp_path, "wb") as f_csv:
                        for chunk in r_download.iter_content(chunk_size=8192): f_csv.write(chunk)
                mensagens_api_bloco.append(f"CSV baixado com sucesso para: {temp_path.name}")
            except Exception as e_download:
                raise RuntimeError(f"Download CSV falhou ({csv_url}): {e_download}")

        else: # Modo Simulação
            mensagens_api_bloco.append(f"[SIMULAÇÃO] Operação de API ignorada. Usando CSV local: {temp_path.name}")
            if not temp_path.exists():
                mensagens_api_bloco.append(f"Simulação: CSV '{temp_path.name}' ausente. DataFrame estará vazio.")
            else:
                mensagens_api_bloco.append(f"Simulação: CSV '{temp_path.name}' encontrado localmente para processamento.")

        bloco_api(mensagens_api_bloco)

        # 4.4 Leitura, Mapeamento e Staging
        num_linhas_lidas = 0
        num_linhas_mapeadas = 0

        mensagens_bd_bloco.append(f"Verificando arquivo CSV: {temp_path.name}")
        if not temp_path.exists():
            raise RuntimeError(f"Arquivo CSV '{temp_path.name}' não foi baixado ou está ausente.")

        try:
            mensagens_bd_bloco.append(f"Lendo CSV: {temp_path.name}")
            df = pd.read_csv(temp_path, sep=";", encoding="latin-1", dtype=str, keep_default_na=False, na_values=[''], on_bad_lines='skip')
            # Remove linhas totalmente em branco
            df = df.dropna(how='all')
            df = df[~df.apply(lambda row: row.astype(str).str.strip().eq('').all(), axis=1)]
            df = df.replace(r'^\s*$', None, regex=True)
            df = df.infer_objects(copy=False)
            num_linhas_lidas = len(df)
            mensagens_bd_bloco.append(f"CSV lido. Total de {num_linhas_lidas} linhas.")
        except pd.errors.EmptyDataError:
            mensagens_bd_bloco.append(f"CSV '{temp_path.name}' vazio. Nenhum dado para processar.")
            df = pd.DataFrame()
        except Exception as e_read_real:
            raise RuntimeError(f"Erro ao ler CSV '{temp_path.name}': {e_read_real}")

        mensagens_bd_bloco.append(f"Aplicando mapeamento para {CFG_SCRIPT_NAME}...")
        try:
            df_proc = apply_column_mappings_and_structure(df, CFG_SCRIPT_NAME)
            if df_proc is None or not isinstance(df_proc, pd.DataFrame):
                raise ValueError("Mapeamento retornou tipo inesperado.")
            num_linhas_mapeadas = len(df_proc)
            mensagens_bd_bloco.append(f"Mapeamento concluído. DataFrame com {num_linhas_mapeadas} linhas processadas e prontas para staging.")
            if df_proc.empty and not df.empty:
                logger.warning(f"DataFrame zerado APÓS mapeamento, mas tinha {len(df)} linhas antes.")
                mensagens_bd_bloco.append("Atenção: DataFrame zerado APÓS mapeamento (verifique o log de arquivo).")
        except Exception as e_map:
            raise RuntimeError(f"Mapeamento falhou para {CFG_SCRIPT_NAME}: {e_map}") from e_map

        staging_table = getattr(CFG_SCRIPT, "staging_table", None)
        if not staging_table:
            raise RuntimeError("Config Staging: 'staging_table' não definida.")
        
        # Extrair schema e tabela se contiver '.'
        if '.' in staging_table:
            staging_schema, staging_table_name = staging_table.split('.', 1)
        else:
            staging_schema = 'dbo'  # schema padrão se não especificado
            staging_table_name = staging_table
        
        # TRUNCATE e INSERT em uma única transação
        from sqlalchemy import text as sa_text

        if df_proc.empty:
            mensagens_bd_bloco.append(f"Sem dados para inserir na tabela de staging '{staging_schema}.{staging_table_name}'.")
        else:
            mensagens_bd_bloco.append(f"🗑️ LIMPANDO e INSERINDO em {staging_schema}.{staging_table_name}...")

            try:
                db_engine = repo.connect_db()

                with db_engine.begin() as conn:
                    # 1. Verificar antes do TRUNCATE
                    count_antes = conn.execute(sa_text(f"SELECT COUNT(*) FROM {staging_schema}.{staging_table_name}")).scalar()
                    mensagens_bd_bloco.append(f"   Antes: {count_antes} registros")

                    # 2. TRUNCATE com reset de IDENTITY (PostgreSQL)
                    conn.execute(sa_text(f"TRUNCATE TABLE {staging_schema}.{staging_table_name} RESTART IDENTITY CASCADE"))

                    # 3. Verificar se limpou
                    count_depois = conn.execute(sa_text(f"SELECT COUNT(*) FROM {staging_schema}.{staging_table_name}")).scalar()
                    mensagens_bd_bloco.append(f"   Depois do TRUNCATE: {count_depois} registros")

                    if count_depois != 0:
                        raise RuntimeError(f"TRUNCATE falhou! Ainda há {count_depois} registros!")

                    # 4. INSERT usando a mesma conexão/transação
                    df_proc.to_sql(
                        name=staging_table_name,
                        con=conn,  # Mesma conexão/transação
                        if_exists='append',
                        index=False,
                        chunksize=1000,
                        schema=staging_schema
                    )

                    # 5. Verificar após INSERT
                    count_final = conn.execute(sa_text(f"SELECT COUNT(*) FROM {staging_schema}.{staging_table_name}")).scalar()
                    mensagens_bd_bloco.append(f"✅ Inserção concluída: {count_final} registros")

                    if count_final != len(df_proc):
                        logger.warning(f"Divergência: esperado {len(df_proc)}, inserido {count_final}")

            except Exception as e_staging:
                raise RuntimeError(f"Erro na operação TRUNCATE/INSERT: {e_staging}") from e_staging

        
        # =============================================================================================
        # EXECUÇÃO DA STORED PROCEDURE NO POSTGRESQL
        # =============================================================================================
        # Usar o nome correto da procedure para PostgreSQL
        procedure_name = "sp_executar_fluxo_titulos_abertos"  # Nome correto da procedure
        procedure_schema = "etl"

        if procedure_name:
            mensagens_bd_bloco.append(f"Executando stored procedure: {procedure_schema}.{procedure_name}")
            try:
                # Chamar a procedure sem parâmetros (PostgreSQL)
                repo.run_stored_procedure(
                    proc_name=procedure_name,
                    schema=procedure_schema,
                    params=None  # Procedure não requer parâmetros
                )
                mensagens_bd_bloco.append(f"✅ Procedure '{procedure_schema}.{procedure_name}' executada com sucesso")
                logger.info(f"Procedure '{procedure_schema}.{procedure_name}' executada com sucesso para títulos abertos")

                # Verificar resultado na tabela final
                tabela_final = getattr(CFG_SCRIPT, "tabela_final", "dwh.fct_titulos_abertos")
                if tabela_final:
                    try:
                        db_engine = repo.connect_db()
                        with db_engine.connect() as conn:
                            from sqlalchemy import text as sa_text
                            result = conn.execute(sa_text(f"SELECT COUNT(*) FROM {tabela_final}"))
                            linhas_final = result.scalar()
                            mensagens_bd_bloco.append(f"✅ Total de linhas na tabela final '{tabela_final}': {linhas_final}")
                            logger.info(f"Tabela final '{tabela_final}' contém {linhas_final} linhas após procedure")
                    except Exception as e:
                        logger.warning(f"Erro ao verificar tabela final: {e}")
                        mensagens_bd_bloco.append(f"⚠️ Não foi possível verificar tabela final: {e}")

            except Exception as e:
                logger.error(f"Erro ao executar procedure '{procedure_schema}.{procedure_name}': {e}")
                mensagens_bd_bloco.append(f"❌ Falha na execução da procedure: {e}")
                raise RuntimeError(f"Falha na execução da procedure: {e}") from e
        else:
            mensagens_bd_bloco.append("Nome da stored procedure não configurado, pulando execução da procedure.")

        # Verificar quantidade de linhas inseridas na tabela de staging para controle
        try:
            from sqlalchemy import text as sa_text
            db_engine = repo.connect_db()
            with db_engine.connect() as conn_verify:
                tabela_staging = getattr(CFG_SCRIPT, "staging_table", "stg.erp_titulos_aberto")
                result_verify = conn_verify.execute(sa_text(f"SELECT COUNT(*) FROM {tabela_staging}"))
                linhas_staging = result_verify.scalar()
                mensagens_bd_bloco.append(f"✅ Total de linhas inseridas na staging '{tabela_staging}': {linhas_staging}")
        except Exception as e_verify:
            logger.error(f"Erro ao verificar linhas na staging: {e_verify}")
            mensagens_bd_bloco.append(f"⚠️ Não foi possível verificar linhas na staging: {e_verify}")


        bloco_bd(mensagens_bd_bloco)

        # 4.6 Remoção do CSV temporário
        sucesso_execucao = True
        remover_cfg = getattr(CFG_SCRIPT, "remover_csv_apos_processamento", True)
        if temp_path.exists():
            if sucesso_execucao and remover_cfg:
                try: 
                    os.remove(temp_path)
                    logger.info(f"CSV temporário removido: {temp_path}")
                except Exception as e_rem: 
                    logger.warning(f"Falha ao remover CSV '{temp_path}': {e_rem}", exc_info=True)
            elif not sucesso_execucao:
                logger.info(f"CSV temporário mantido devido a falha: {temp_path}")
            elif not remover_cfg: 
                logger.info(f"CSV temporário mantido por configuração: {temp_path}")

        tempo_exec = time.time() - script_start_time
        mensagem_final_sucesso = f"Processamento concluído com sucesso para {referencia_periodo_log}."
        logger.info(f"'{CFG_SCRIPT_NAME}' (ETL) finalizado. Resultado: {mensagem_final_sucesso}")
        return {
            "success": sucesso_execucao,
            "mensagem": mensagem_final_sucesso,
            "periodo": referencia_periodo_log,
            "tempo_execucao": tempo_exec
        }

    except Exception as e_exec:
        tempo_exec = time.time() - script_start_time
        mensagem_final_falha = f"Falha ETL: {e_exec}"
        logger.error(f"Erro crítico no processamento de {CFG_SCRIPT_NAME}: {e_exec}", exc_info=True)
        
        if not mensagens_bd_bloco:
            mensagens_bd_bloco.append(f"Falha inesperada no processamento: {str(e_exec)}")
            bloco_bd(mensagens_bd_bloco) 
        
        return {"success": False, "mensagem": mensagem_final_falha, "periodo": referencia_periodo_log, "tempo_execucao": tempo_exec}

# =============================================================================================
# 5.0 BLOCO DE EXECUÇÃO DIRETA (Main)
# =============================================================================================
if __name__ == "__main__":
    script_start_time = time.time()
    nome_recurso_execucao = CFG_SCRIPT_NAME
    print(f"📌 Iniciando execução de '{nome_recurso_execucao}'...")
    simulacao_ativa = "--simulacao" in sys.argv or "-s" in sys.argv
    print(f"Modo Simulação ATUAL: {simulacao_ativa}")

    resultado = processar_titulos_abertos_dias_corridos(modo_simulacao=simulacao_ativa)

    mensagens_resumo_final_bloco = []
    if resultado.get("success"):
        mensagens_resumo_final_bloco.append("✅ Processamento concluído com SUCESSO!")
    else:
        mensagens_resumo_final_bloco.append("❌ Processamento FALHOU!")
    mensagens_resumo_final_bloco.append(f"Mensagem Final: {resultado.get('mensagem')}")
    mensagens_resumo_final_bloco.append(f"Total do período processado: {resultado.get('periodo')}")
    mensagens_resumo_final_bloco.append(f"Tempo total de execução: {int(resultado.get('tempo_execucao', 0)//60):02d}:{int(resultado.get('tempo_execucao', 0)%60):02d}")
    bloco_resumo_final(mensagens_resumo_final_bloco)

    try:
        log_final_status(nome_recurso_execucao, resultado)
        if resultado.get("success"):
            print("✅ Status final logado com sucesso.")
        else:
            print("❌ Status de falha registrado. Verifique os logs.")
    except Exception as e_log_status:
        logger.error(f"Falha crítica ao registrar status final '{nome_recurso_execucao}': {e_log_status}", exc_info=True)
        print(f"⚠️ Falha crítica ao registrar status final. Verifique logs.")

    script_end_time = time.time()
    total_duration_seconds = script_end_time - script_start_time
    mmss = f"{int(total_duration_seconds // 60):02d}:{int(total_duration_seconds % 60):02d}"
    print(f"\n⏱️ Tempo total de execução: {total_duration_seconds:.2f} segundos ({mmss})\n")
    try:
        registrar_execucao(nome_recurso_execucao, total_duration_seconds)
    except NameError:
        logger.warning(f"Função 'registrar_execucao' não encontrada.", exc_info=False)
    except Exception as e_registrar_tempo:
        logger.warning(f"Falha ao registrar tempo de execução '{nome_recurso_execucao}': {e_registrar_tempo}", exc_info=True)

# =============================================================================================
# 6.0 FIM DE ARQUIVO
# =============================================================================================