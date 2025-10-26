# src/common/file_utils.py
# (Seu conteúdo existente)

# =============================================================================================
# ARQUIVO: file_utils.py
# CAMINHO: src/common/file_utils.py
# VERSÃO: v1.7 (future-proof, elimina FutureWarning)
# AUTOR: ChatGPT
# DATA: 2025-05-19
# DESCRIÇÃO:
#   - Aplica o mapeamento de colunas conforme definição central
#   - Padroniza DataFrames para staging e inserção no banco SQL
#   - Elimina FutureWarning do Pandas (opção global)
# =============================================================================================

# =============================================================================================
# 1.0 IMPORTAÇÕES
# =============================================================================================
import csv
import pandas as pd
pd.set_option('future.no_silent_downcasting', True)
from typing import Optional
from src.common.column_mappings import get_table_definition
from src.core.logging_config import get_logger
from pathlib import Path # Adicionado para Path

# =============================================================================================
# 2.0 LOGGER LOCAL
# =============================================================================================
logger = get_logger(__name__)

# =============================================================================================
# 2.5 FUNÇÃO: normalizar_nomes_colunas
# =============================================================================================
def normalizar_nomes_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza os nomes das colunas removendo acentos e caracteres especiais.
    Necessário para trabalhar com CSVs que contêm caracteres especiais.
    """
    import unicodedata

    def normalizar_nome(nome):
        # Remover acentos
        nome_sem_acento = unicodedata.normalize('NFD', nome)
        nome_sem_acento = ''.join(c for c in nome_sem_acento if not unicodedata.combining(c))
        # Converter para maiúsculo
        return nome_sem_acento.upper()

    df_normalizado = df.copy()
    df_normalizado.columns = [normalizar_nome(col) for col in df_normalizado.columns]
    return df_normalizado

# =============================================================================================
# 3.0 FUNÇÃO: apply_column_mappings_and_structure
# =============================================================================================
def apply_column_mappings_and_structure(df: pd.DataFrame, source_name: str) -> Optional[pd.DataFrame]:
    """
    Aplica o mapeamento e padronização de colunas com base no nome da fonte declarada.
    Isso inclui:
    - Renomear colunas do CSV para o padrão interno
    - Garantir presença e ordenação das colunas finais
    - Aplicar os tipos corretos definidos no schema
    """
    etapa = "MAPPING"
    try:
        # 3.1 Obtém o mapeamento correspondente à fonte
        definition = get_table_definition(source_name)
        col_map = definition["csv_column_map"]
        final_order = definition["final_columns_ordered"]
        dtypes = definition["target_dtypes"]

        # 3.2 NOVO: Normaliza os nomes das colunas para remover acentos
        df_normalizado = normalizar_nomes_colunas(df)
        logger.debug(f"[{etapa}] Colunas após normalização: {list(df_normalizado.columns)}")

        # 3.3 Valida se todas as colunas do CSV esperadas estão presentes (após normalização)
        missing_cols = [col for col in col_map if col not in df_normalizado.columns]
        if missing_cols:
            logger.error(f"[{etapa}] Colunas ausentes no CSV (pós-normalização): {missing_cols}")
            logger.error(f"[{etapa}] Colunas disponíveis: {list(df_normalizado.columns)}")
            return None

        # 3.4 Renomeia conforme o mapeamento (usando DataFrame normalizado)
        df_renamed = df_normalizado.rename(columns=col_map)

        # 3.5 Adiciona colunas ausentes com valor None
        for col in final_order:
            if col not in df_renamed.columns:
                df_renamed[col] = None

        # 3.6 Reordena e aplica os dtypes definidos
        df_final = df_renamed[final_order].astype(dtypes)

        # 3.7 Substitui espaços/vazios por None e aplica infer_objects para não dar FutureWarning
        df_final = df_final.replace(r'^\s*$', None, regex=True)
        df_final = df_final.infer_objects(copy=False)

        return df_final

    except Exception as e:
        logger.error(f"[{etapa}] apply_column_mappings_and_structure('{source_name}') falhou: {e}", exc_info=True)
        return None

# =============================================================================================
# 4.0 FUNÇÃO: preprocess_df_for_sql
# =============================================================================================
def preprocess_df_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza o DataFrame antes da inserção no banco SQL:
    - Remove espaços dos nomes de colunas
    - Substitui valores vazios ou espaços por None
    - Converte todas as colunas para string (object) quando aplicável
    """
    df = df.copy()
    df.columns = df.columns.str.strip()
    df = df.replace(r'^\s*$', None, regex=True)
    df = df.infer_objects(copy=False)
    df = df.astype(str).where(df.notnull(), None)
    return df

# =============================================================================================
# 5.0 FUNÇÃO: preprocessar_csv_endereco
# =============================================================================================
def preprocessar_csv_endereco(input_path, output_path):
    """
    Substitui vírgulas no campo 'Endereço' do CSV por espaço, garantindo estrutura válida para pandas.
    """
    with open(input_path, 'r', encoding='latin-1', newline='') as infile, \
            open(output_path, 'w', encoding='latin-1', newline='') as outfile:
        reader = csv.reader(infile, delimiter=';')
        writer = csv.writer(outfile, delimiter=';')

        header = next(reader)
        try:
            idx_endereco = header.index('Endereço')
        except ValueError:
            raise Exception("Coluna 'Endereço' não encontrada no cabeçalho do CSV!")
        writer.writerow(header)

        for row in reader:
            if len(row) > idx_endereco:
                row[idx_endereco] = row[idx_endereco].replace(',', ' ')
            writer.writerow(row)

# =============================================================================================
# 6.0 FUNÇÃO: save_csv (Adicionada para resolver ImportError)
# =============================================================================================
def save_csv(file_path: str, content: str, encoding: str = 'utf-8') -> None:
    """
    Salva uma string de conteúdo em um arquivo CSV, garantindo que o diretório exista.

    Args:
        file_path (str): O caminho completo para o arquivo CSV a ser salvo.
        content (str): O conteúdo da string a ser gravado no arquivo.
        encoding (str): A codificação a ser usada para escrever o arquivo. Padrão: 'utf-8'.
    """
    try:
        path = Path(file_path)
        # Garante que o diretório pai exista antes de tentar salvar o arquivo
        path.parent.mkdir(parents=True, exist_ok=True) 
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)
        logger.info(f"Conteúdo salvo em: {file_path}")
    except Exception as e:
        logger.error(f"Erro ao salvar arquivo CSV '{file_path}': {e}", exc_info=True)
        raise # Re-levanta o erro para o chamador lidar com a falha de salvamento


# =============================================================================================
# FIM DO ARQUIVO: file_utils.py
# =============================================================================================