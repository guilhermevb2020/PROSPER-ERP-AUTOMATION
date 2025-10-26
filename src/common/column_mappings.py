# -*- coding: utf-8 -*-
# =============================================================================================
# ARQUIVO: column_mappings.py
# CAMINHO: src/common/column_mappings.py
# VERSÃO: v1.2
# AUTOR: ChatGPT
# DATA: 2025-05-14
# DESCRIÇÃO:
#   - Armazena os mapeamentos (CSV → tabela staging)
#   - Unifica schemas para títulos quitados, rejeitados e prorrogados
# =============================================================================================

from typing import Dict
import pandas as pd


# =============================================================================================
# 7.0 MAPEAMENTO — SACADOS DIAS CORRIDOS (COMPARTILHADO)
# =============================================================================================
SACADOS_DIAS_CORRIDOS_COLUMN_MAP = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (nomes atuais da tabela)
    "ID": "id_sacado",
    "NOME": "sacado",                       # CORRIGIDO: nome → sacado
    "CPF/CNPJ": "cpf_cnpj",
    "ENDERECO": "endereco",                 # ENDEREÇO normalizado
    "CEP": "cep",
    "CIDADE": "cidade",
    "UF": "uf",
    "EMAIL": "email",
    "TELEFONE": "telefone",
    "SMS": "sms",
    "DATA DE CADASTRO": "data_cadastro",
    "ID GRUPO ECONOMICO": "id_grupo_economico_sacado"  # ID GRUPO ECONÔMICO normalizado
}

SACADOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED = list(SACADOS_DIAS_CORRIDOS_COLUMN_MAP.values())

SACADOS_DIAS_CORRIDOS_DTYPES_TARGET = {
    col: "object" for col in SACADOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED
}
# =============================================================================================
# 4.x MAPEAMENTO — CEDENTES DIAS CORRIDOS (CORRIGIDO APÓS ANÁLISE DO CSV REAL)
# =============================================================================================
CEDENTES_DIAS_CORRIDOS_COLUMN_MAP = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (nomes atuais da tabela)
    "NOME": "cedente",                          # CORRIGIDO: nome → cedente
    "CPF/CNPJ": "cpf_cnpj",
    "ENDERECO": "endereco",                     # ENDEREÇO normalizado
    "CEP": "cep",
    "CIDADE": "cidade",
    "UF": "uf",
    "EMAIL": "email",
    "TELEFONE": "telefone",
    "GERENTE": "gerente",
    "OPERADOR": "operador",
    "CAPTADOR": "captador",
    "RESPONSAVEL_CONFIRMACAO": "confirmador",
    "RESPONSAVEL_COBRANCA": "cobrador",
    "FATOR (%)": "fator",
    "AD-VALOREM (%)": "ad_valorem",
    "DATA DE CADASTRO": "data_cadastro",        # CORRIGIDO: data_de_cadastro → data_cadastro
    "FONTE DE CAPTACAO": "fonte_de_captacao",   # FONTE DE CAPTAÇÃO normalizado
    "SETOR": "setor",
    "GRUPO ECONOMICO": "grupo_economico",       # GRUPO ECONÔMICO normalizado
    "BLOQUEADO": "bloqueado",
    "PRIMEIRA OPERACAO": "data_primeira_operacao",  # CORRIGIDO: primeira_operacao → data_primeira_operacao
    "LIMITE GLOBAL": "limite_global",
    "LIMITE BOLETO ESPECIAL": "limite_boleto_especial",
    "LIMITE COMISSARIA": "limite_comissaria",   # LIMITE COMISSÁRIA normalizado
    "LIMITE TRANCHE": "limite_tranche",
    "LIMITE BOLETO ESPECIAL TRANCHE": "limite_boleto_especial_tranche",
    "LIMITE BOLETO GARANTIDO": "limite_boleto_garantido",
    "LIMITE OPERACAO CLEAN": "limite_operacao_clean",
    "RISCO ATUAL": "risco_atual",
    "SALDO": "saldo",
    "VENCIMENTO DO CONTRATO": "data_vencimento_contrato",  # CORRIGIDO: vencimento_do_contrato → data_vencimento_contrato
    "ID CEDENTE": "id_cedente",
    "ID GRUPO ECONOMICO": "id_grupo_economico"  # ID GRUPO ECONÔMICO normalizado
}
CEDENTES_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED = list(CEDENTES_DIAS_CORRIDOS_COLUMN_MAP.values())
CEDENTES_DIAS_CORRIDOS_DTYPES_TARGET = {col: "object" for col in CEDENTES_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED}


# =============================================================================================
# 1.0 MAPEAMENTO — TÍTULOS EM ABERTOS DIAS CORRIDOS (CORRIGIDO PARA POSTGRESQL)
# =============================================================================================
TITULOS_ABERTOS_DIAS_CORRIDOS_COLUMN_MAP: Dict[str, str] = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (nomes atuais da tabela)
    'ID_TITULO':               'id_titulo',
    'DOCUMENTO':               'numero_documento',     # CORRIGIDO: documento → numero_documento
    'CONF':                    'conf',
    'ETAPA':                   'etapa',
    'CR':                      'classe_risco',        # CORRIGIDO: cr → classe_risco
    'M':                       'm',
    'TIPO':                    'tipo_titulo',         # CORRIGIDO: tipo → tipo_titulo
    'CPF/CNPJ SACADO':         'cpf_cnpj_sacado',
    'SACADO':                  'sacado',
    'CPF/CNPJ CEDENTE':        'cpf_cnpj_cedente',
    'CEDENTE':                 'cedente',
    'NOSSO Nº':                'nosso_numero',
    'DATA EMISSAO':            'data_emissao',        # CORRIGIDO: sem acento
    'ORIGINAL':                'data_original',
    'VENCIMENTO':              'data_vencimento',
    'SITUACAO':                'situacao',            # CORRIGIDO: sem acento
    'OP':                      'id_operacao',
    'CONTA':                   'conta_bancaria',
    'DESAGIO':                 'valor_desconto',      # CORRIGIDO: sem acento
    'VALOR(R$)':               'valor_face',
    'MULTA(R$)':               'valor_multa',
    'JUROS(R$)':               'valor_juros',
    'TARIFAS(R$)':             'valor_tarifas',
    'TOTAL(R$)':               'valor_total',
    'HISTORICO':               'historico',
    'MOTIVO':                  'motivo',
    'ID_TITULO_ORIGINAL':      'id_titulo_original',
    'TIPO_OPERACAO':           'tipo_operacao'        # ADICIONADO: coluna faltante
}
TITULOS_ABERTOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED = list(TITULOS_ABERTOS_DIAS_CORRIDOS_COLUMN_MAP.values())
TITULOS_ABERTOS_DIAS_CORRIDOS_DTYPES_TARGET: Dict[str, str] = {
    col: 'object' for col in TITULOS_ABERTOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED
}

# =============================================================================================
# 2.0 MAPEAMENTO — OPERAÇÃO DESÁGIO
# =============================================================================================
OPERACAO_DESAGIO_COLUMN_MAP: Dict[str, str] = {
    'OPERACAO':                  'id_operacao',
    'ETAPA':                     'etapa',
    'DATA':                      'data_operacao',
    'CEDENTE':                   'cedente',
    'CPF_CNPJ_CEDENTE':          'cpf_cnpj_cedente',
    'PRAZO_MEDIO':               'prazo_medio',
    'VALOR_BRUTO':               'valor_bruto',
    'VALOR_TAXA':                'valor_taxa',
    'VALOR_COBRANCAS':           'valor_cobrancas',
    'VALOR_JUROS_ANTECIPACAO':   'valor_juros_antecipacao',
    'VALOR_LIQUIDO':             'valor_liquido',
    'VALOR_RECOMPRA_PENDENCIA':  'valor_recompra_pendencia',
    'CRED_CEDENTE':              'valor_credito_cedente',
    'VALOR_PAGTO_OPERACAO':      'valor_pagamento_operacao',
    'VALOR_SALDO':               'valor_saldo',
    'FINALIZACAO':               'data_finalizacao',
    'PAGAMENTO_OPERACAO':        'data_pagamento_operacao',
    'INICIO':                    'data_inicio',
    'CONTA_PAGTO':               'conta_bancaria_pg',
    'TIPO_OPERACAO':             'tipo_operacao'
}
OPERACAO_DESAGIO_FINAL_COLUMNS_ORDERED = list(OPERACAO_DESAGIO_COLUMN_MAP.values())
OPERACAO_DESAGIO_DTYPES_TARGET: Dict[str, str] = {
    col: 'object' for col in OPERACAO_DESAGIO_FINAL_COLUMNS_ORDERED
}

# =============================================================================================
# 3.0 MAPEAMENTO — TÍTULOS QUITADOS (COMPARTILHADO)
# =============================================================================================
TITULOS_QUITADOS_COLUMN_MAP: Dict[str, str] = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (nomes atuais da tabela)
    "NUMERO": "numero_documento",                         # CORRIGIDO: numero → numero_documento
    "CONF": "conf",
    "M": "m",
    "CLASSE DE RISCO": "classe_risco",                    # CORRIGIDO: classe_de_risco → classe_risco
    "TIPO": "tipo_titulo",                                # CORRIGIDO: tipo → tipo_titulo
    "CPF/CNPJ SACADO": "cpf_cnpj_sacado",
    "SACADO": "sacado",
    "CPF/CNPJ CEDENTE": "cpf_cnpj_cedente",
    "CEDENTE": "cedente",
    "NOSSO Nº": "nosso_numero",
    "ORIGINAL": "data_original",                          # CORRIGIDO: original → data_original
    "VENCIMENTO": "data_vencimento",                      # CORRIGIDO: vencimento → data_vencimento
    "QUITACAO": "data_quitacao",                          # CORRIGIDO: quitacao → data_quitacao
    "STATUS": "status",
    "EMISSAO": "data_emissao",                            # CORRIGIDO: emissao → data_emissao
    "VALOR FACE(R$)": "valor_face",
    "JUROS(R$)": "valor_juros",
    "MULTA(R$)": "valor_multa",
    "TARIFAS(R$)": "valor_tarifas",
    "DESCONTO(R$)": "valor_desconto",
    "TOTAL(R$)": "valor_total",
    "LIQUIDADO(R$)": "valor_liquidado",
    "OP": "id_operacao",
    "SITUACAO": "situacao",
    "TIPO QUITACAO": "tipo_quitacao",
    "DATA DA CUSTODIA": "data_custodia",                  # CORRIGIDO: data_da_custodia → data_custodia
    "OP DE PAGAMENTO": "cod_operacao_pg",                 # CORRIGIDO: op_de_pagamento → cod_operacao_pg
    "OBSERVACAO": "observacao",
    "CONTA": "conta_bancaria",                            # CORRIGIDO: conta → conta_bancaria
    "TAR. DEV. CHEQUE(R$)": "valor_tarifa_devolucao_cheque",
    "TAR. RECOMPRA(R$)": "valor_tarifa_recompra",
    "CATEGORIA": "categoria",
    "BANCO COBRADOR": "banco_cobrador",
    "AGENCIA COBRADORA": "agencia_cobradora",
    "MOTIVO DA DEVOLUCAO": "motivo_devolucao",
    "ID_TITULO": "id_titulo"
}
TITULOS_QUITADOS_FINAL_COLUMNS_ORDERED = list(TITULOS_QUITADOS_COLUMN_MAP.values())
TITULOS_QUITADOS_DTYPES_TARGET: Dict[str, str] = {
    col: "object" for col in TITULOS_QUITADOS_FINAL_COLUMNS_ORDERED
}

# =============================================================================================
# 4.0 MAPEAMENTO — TÍTULOS REJEITADOS (COMPARTILHADO)
# =============================================================================================
TITULOS_REJEITADOS_COLUMN_MAP = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (nomes atuais da tabela)
    "DOCUMENTO": "numero_documento",           # CORRIGIDO: NOSSO_NUMERO → numero_documento
    "M": "m",                                 # CORRIGIDO: M → m (minúsculo)
    "TIPO": "tipo_titulo",                    # CORRIGIDO: TIPO → tipo_titulo
    "SACADO": "sacado",                       # CORRIGIDO: SACADO → sacado (minúsculo)
    "CPF_CNPJ_SACADO": "cpf_cnpj_sacado",     # CORRIGIDO: CPF_CNPJ_SACADO → cpf_cnpj_sacado
    "CEDENTE": "cedente",                     # CORRIGIDO: CEDENTE → cedente (minúsculo)
    "CPF_CNPJ_CEDENTE": "cpf_cnpj_cedente",   # CORRIGIDO: CPF_CNPJ_CEDENTE → cpf_cnpj_cedente
    "VENCIMENTO": "data_vencimento",          # CORRIGIDO: VENCIMENTO → data_vencimento
    "EMISSAO": "data_emissao",                # CORRIGIDO: EMISSAO → data_emissao (versão normalizada)
    "CONTA": "conta_bancaria",                # CORRIGIDO: CONTA → conta_bancaria
    "OP": "id_operacao",                      # CORRIGIDO: OP → id_operacao
    "VALOR(R$)": "valor_face"                 # CORRIGIDO: valor_rejeitado → valor_face (conforme tabela PostgreSQL)
}
# Colunas finais sem nosso_numero (removida) e com id_auto
TITULOS_REJEITADOS_FINAL_COLUMNS_ORDERED = [
    "numero_documento", "m", "tipo_titulo", "sacado", "cpf_cnpj_sacado",
    "cedente", "cpf_cnpj_cedente", "data_vencimento", "data_emissao",
    "conta_bancaria", "id_operacao", "valor_face"
]
TITULOS_REJEITADOS_DTYPES_TARGET = {
    col: "object" for col in TITULOS_REJEITADOS_FINAL_COLUMNS_ORDERED
}

# =============================================================================================
# 4.1 MAPEAMENTO — TÍTULOS PRORROGADOS (COMPARTILHADO)
# =============================================================================================
TITULOS_PRORROGADOS_COLUMN_MAP: Dict[str, str] = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (conforme tabela no banco)
    "NUMERO": "numero_documento",                          # CORRIGIDO: numero → numero_documento
    "M": "m",
    "TIPO": "tipo_titulo",                                 # CORRIGIDO: tipo → tipo_titulo
    "CPF/CNPJ SACADO": "cpf_cnpj_sacado",
    "SACADO": "sacado",
    "CPF/CNPJ CEDENTE": "cpf_cnpj_cedente",
    "CEDENTE": "cedente",
    "VENCIMENTO": "data_vencimento",                       # CORRIGIDO: vencimento → data_vencimento
    "EMISSAO": "data_emissao",                            # CORRIGIDO: emissao → data_emissao
    "DATA PRORROGACAO": "data_prorrogacao",               # OK: já com prefixo data_
    "CONTA": "conta_bancaria",                            # CORRIGIDO: conta → conta_bancaria
    "VALOR FACE(R$)": "valor_face",                       # OK: já com prefixo valor_
    "VENCIMENTO ANTERIOR": "data_vencimento_anterior",     # CORRIGIDO: vencimento_anterior → data_vencimento_anterior
    "VALOR FACE ANTERIOR(R$)": "valor_face_anterior",     # OK: já com prefixo valor_
    "TARIFAS(R$)": "valor_tarifas",                       # CORRIGIDO: tarifas → valor_tarifas
    "JUROS(R$)": "valor_juros",                           # CORRIGIDO: juros → valor_juros
    "MULTA(R$)": "valor_multa",                           # CORRIGIDO: multa → valor_multa
    "IOF(R$)": "valor_iof",                               # CORRIGIDO: iof → valor_iof
    "CONF": "conf",
    "ETAPA": "etapa"
}
TITULOS_PRORROGADOS_FINAL_COLUMNS_ORDERED = list(TITULOS_PRORROGADOS_COLUMN_MAP.values())
TITULOS_PRORROGADOS_DTYPES_TARGET: Dict[str, str] = {
    col: "object" for col in TITULOS_PRORROGADOS_FINAL_COLUMNS_ORDERED
}

# =============================================================================================
# 6.0 MAPEAMENTO — TÍTULOS RECOMPRADOS (COMPARTILHADO)
# =============================================================================================
TITULOS_RECOMPRADOS_COLUMN_MAP: Dict[str, str] = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (snake_case minúsculo)
    "NUMERO": "numero_documento",
    "M": "m",
    "CLASSE DE RISCO": "classe_risco",
    "TIPO": "tipo_titulo",
    "CPF/CNPJ SACADO": "cpf_cnpj_sacado",
    "SACADO": "sacado",
    "CPF/CNPJ CEDENTE": "cpf_cnpj_cedente",
    "CEDENTE": "cedente",
    "NOSSO Nº": "nosso_numero",                        # CORRIGIDO: versão normalizada
    "VENCIMENTO": "data_vencimento",
    "RECOMPRA": "data_recompra",
    "EMISSAO": "data_emissao",                         # CORRIGIDO: versão normalizada (sem acento)
    "VALOR FACE(R$)": "valor_face",
    "JUROS(R$)": "valor_juros",
    "MULTA(R$)": "valor_multa",
    "DESCONTO(R$)": "valor_desconto",
    "TARIFA(R$)": "valor_tarifas",
    "TOTAL(R$)": "valor_total",
    "LIQUIDADO(R$)": "valor_liquidado",
    "OP": "id_operacao",
    "SITUACAO": "situacao",                           # CORRIGIDO: versão normalizada (sem acento)
    "OP DE PAGAMENTO": "cod_operacao_pg",
    "OBSERVACAO": "observacao",                       # CORRIGIDO: versão normalizada (sem acento)
    "CONTA": "conta_bancaria",
    "CATEGORIA": "categoria",
    "MOTIVO": "motivo"
}


TITULOS_RECOMPRADOS_FINAL_COLUMNS_ORDERED = list(TITULOS_RECOMPRADOS_COLUMN_MAP.values())

TITULOS_RECOMPRADOS_DTYPES_TARGET: Dict[str, str] = {
    col: "object" for col in TITULOS_RECOMPRADOS_FINAL_COLUMNS_ORDERED
}

# =============================================================================================
# 4.4 MAPEAMENTO — TÍTULOS QUITADOS SUSPEITOS (COMPARTILHADO)
# =============================================================================================
TITULOS_QUITADOS_SUSPEITOS_COLUMN_MAP: Dict[str, str] = {
    # Mapeamento CSV (normalizado sem acentos) → PostgreSQL (snake_case minúsculo)
    "Nº DOCUMENTO": "numero_documento",                    # CORRIGIDO: versão normalizada
    "VENCIMENTO": "data_vencimento",                       # CORRIGIDO: → data_vencimento
    "VALOR": "valor_face",                                 # CORRIGIDO: → valor_face
    "DATA QUITACAO": "data_quitacao",                      # CORRIGIDO: versão normalizada
    "SACADO": "sacado",
    "CPF/CNPJ SACADO": "cpf_cnpj_sacado",                 # CORRIGIDO: versão normalizada
    "CEDENTE": "cedente",
    "CPF/CNPJ CEDENTE": "cpf_cnpj_cedente",               # CORRIGIDO: versão normalizada
    "SETOR": "setor",
    "BANCO COBRADOR": "banco_cobrador",
    "AG COBRADORA": "agencia_cobradora",                   # CORRIGIDO: → agencia_cobradora
    "PRACA DE PAGAMENTO": "praca_pagamento",               # CORRIGIDO: versão normalizada
    "LOCALIDADE SACADO": "localidade_sacado",
    "CRITICA(S)": "critica"                               # CORRIGIDO: versão normalizada
}

TITULOS_QUITADOS_SUSPEITOS_FINAL_COLUMNS_ORDERED = list(TITULOS_QUITADOS_SUSPEITOS_COLUMN_MAP.values())

TITULOS_QUITADOS_SUSPEITOS_DTYPES_TARGET: Dict[str, str] = {
    col: "object" for col in TITULOS_QUITADOS_SUSPEITOS_FINAL_COLUMNS_ORDERED
}
# =============================================================================================
# 8.0 MAPEAMENTO — CEDENTE DETAILS (PESSOAS RELACIONADAS)
# =============================================================================================
CEDENTE_DETAILS_COLUMN_MAP = {
    "documento": "cpf_cnpj",
    "nome": "nome_participante_relacionado",
    "tipoRelacionamento": "tipo_relacionamento"
}

CEDENTE_DETAILS_FINAL_COLUMNS_ORDERED = [
    "cpf_cnpj",
    "nome_participante_relacionado",
    "tipo_relacionamento",
    "id_cedente"
]

CEDENTE_DETAILS_DTYPES_TARGET = {
    "cpf_cnpj": "object",
    "nome_participante_relacionado": "object",
    "tipo_relacionamento": "object",
    "id_cedente": "object"
}

# =============================================================================================
# 4.4 MAPEAMENTO — TÍTULOS BAIXADOS (COMPARTILHADO)
# =============================================================================================

TITULOS_BAIXADOS_DIAS_CORRIDOS_COLUMN_MAP: Dict[str, str] = {
    # Mapeamento CSV (normalizado) → PostgreSQL (snake_case minúsculo)
    "DOCUMENTO": "numero_documento",  # DOCUMENTO → numero_documento conforme tabela PostgreSQL
    "TIPO": "tipo_titulo",  # TIPO → tipo_titulo conforme tabela PostgreSQL
    "M": "m",
    "DATA": "data_emissao",  # DATA → data_emissao conforme tabela PostgreSQL
    "VENCIMENTO": "data_vencimento",  # VENCIMENTO → data_vencimento conforme tabela
    "DOC_CEDENTE": "cpf_cnpj_cedente",  # DOC_CEDENTE → cpf_cnpj_cedente conforme tabela
    "CEDENTE": "cedente",
    "DOC_SACADO": "cpf_cnpj_sacado",  # DOC_SACADO → cpf_cnpj_sacado conforme tabela
    "SACADO": "sacado",
    "CUSTODIA": "custodia",
    "DATA_BAIXA": "data_baixa",
    "MOTIVO_BAIXA": "motivo_baixa",
    "VALOR": "valor_face",
    "NOSSO_NUMERO": "nosso_numero",
    "CATEGORIA": "categoria"
}

TITULOS_BAIXADOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED = list(TITULOS_BAIXADOS_DIAS_CORRIDOS_COLUMN_MAP.values())

TITULOS_BAIXADOS_DIAS_CORRIDOS_DTYPES_TARGET: Dict[str, str] = {
    col: "object" for col in TITULOS_BAIXADOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED
}
# =============================================================================================
# 5.0 DICIONÁRIO CENTRALIZADO DE DEFINIÇÕES
# =============================================================================================
ALL_TABLE_DEFINITIONS = {
    "cedentes_dias_corridos": {
        "csv_column_map": CEDENTES_DIAS_CORRIDOS_COLUMN_MAP,
        "final_columns_ordered": CEDENTES_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": CEDENTES_DIAS_CORRIDOS_DTYPES_TARGET
    },
    "sacados_dias_corridos": {
        "csv_column_map": SACADOS_DIAS_CORRIDOS_COLUMN_MAP,
        "final_columns_ordered": SACADOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": SACADOS_DIAS_CORRIDOS_DTYPES_TARGET
    },
    "titulos_abertos_dias_corridos": {
        "csv_column_map": TITULOS_ABERTOS_DIAS_CORRIDOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_ABERTOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_ABERTOS_DIAS_CORRIDOS_DTYPES_TARGET
    },
     "operacao_desagio_dias_corridos": {
        "csv_column_map": OPERACAO_DESAGIO_COLUMN_MAP,
        "final_columns_ordered": OPERACAO_DESAGIO_FINAL_COLUMNS_ORDERED,
        "target_dtypes": OPERACAO_DESAGIO_DTYPES_TARGET
    },
    "operacao_desagio_acumulado": {   # <------ Adicione esta chave!
        "csv_column_map": OPERACAO_DESAGIO_COLUMN_MAP,
        "final_columns_ordered": OPERACAO_DESAGIO_FINAL_COLUMNS_ORDERED,
        "target_dtypes": OPERACAO_DESAGIO_DTYPES_TARGET
    },
    "titulos_quitados_dias_corridos": {
        "csv_column_map": TITULOS_QUITADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_QUITADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_QUITADOS_DTYPES_TARGET
    },
    "titulos_quitados_acumulado": {
        "csv_column_map": TITULOS_QUITADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_QUITADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_QUITADOS_DTYPES_TARGET
    },
    "titulos_rejeitados_dias_corridos": {
        "csv_column_map": TITULOS_REJEITADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_REJEITADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_REJEITADOS_DTYPES_TARGET
    },
    "titulos_rejeitados_acumulado": {
        "csv_column_map": TITULOS_REJEITADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_REJEITADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_REJEITADOS_DTYPES_TARGET
    },
    "titulos_prorrogados_dias_corridos": {
        "csv_column_map": TITULOS_PRORROGADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_PRORROGADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_PRORROGADOS_DTYPES_TARGET
    },
    "titulos_prorrogados_acumulado": {
        "csv_column_map": TITULOS_PRORROGADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_PRORROGADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_PRORROGADOS_DTYPES_TARGET
    },
    "titulos_recomprados_dias_corridos": {
        "csv_column_map": TITULOS_RECOMPRADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_RECOMPRADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_RECOMPRADOS_DTYPES_TARGET
    },
    "titulos_recomprados_acumulado": {
        "csv_column_map": TITULOS_RECOMPRADOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_RECOMPRADOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_RECOMPRADOS_DTYPES_TARGET
    },
    "titulos_quitados_suspeitos_acumulado": {
        "csv_column_map": TITULOS_QUITADOS_SUSPEITOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_QUITADOS_SUSPEITOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_QUITADOS_SUSPEITOS_DTYPES_TARGET
    },
    "titulos_quitados_suspeitos_dias_corridos": {
        "csv_column_map": TITULOS_QUITADOS_SUSPEITOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_QUITADOS_SUSPEITOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_QUITADOS_SUSPEITOS_DTYPES_TARGET
    },
    "cedente_details": {
        "csv_column_map": CEDENTE_DETAILS_COLUMN_MAP,
        "final_columns_ordered": CEDENTE_DETAILS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": CEDENTE_DETAILS_DTYPES_TARGET
    },
    "titulos_baixados_dias_corridos": {
        "csv_column_map": TITULOS_BAIXADOS_DIAS_CORRIDOS_COLUMN_MAP,
        "final_columns_ordered": TITULOS_BAIXADOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_BAIXADOS_DIAS_CORRIDOS_DTYPES_TARGET
    },
    "titulos_baixados_acumulado": {
        "csv_column_map": TITULOS_BAIXADOS_DIAS_CORRIDOS_COLUMN_MAP,  # Usa o mesmo mapeamento
        "final_columns_ordered": TITULOS_BAIXADOS_DIAS_CORRIDOS_FINAL_COLUMNS_ORDERED,
        "target_dtypes": TITULOS_BAIXADOS_DIAS_CORRIDOS_DTYPES_TARGET
    }
}

# =============================================================================================
# 6.0 FUNÇÃO DE ACESSO
# =============================================================================================
def get_table_definition(source_name: str) -> dict:
    """
    Retorna o dicionário de mapeamento completo da tabela:
    - csv_column_map
    - final_columns_ordered
    - target_dtypes
    """
    definition = ALL_TABLE_DEFINITIONS.get(source_name)
    if definition is None:
        raise ValueError(
            f"Definição de schema não encontrada para a fonte: '{source_name}'. "
            "Verifique src/common/column_mappings.py."
        )

    expected_keys = {"csv_column_map", "final_columns_ordered", "target_dtypes"}
    missing = expected_keys - set(definition.keys())
    if missing:
        raise ValueError(
            f"Definição de schema para '{source_name}' incompleta. "
            f"Faltando chaves: {missing}."
        )

    if set(definition["final_columns_ordered"]) != set(definition["target_dtypes"].keys()):
        raise ValueError(
            f"Inconsistência em '{source_name}': "
            "'final_columns_ordered' e 'target_dtypes' diferem."
        )

    return definition
# =============================================================================================