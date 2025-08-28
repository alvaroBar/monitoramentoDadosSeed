# ==============================================================================
# ARQUIVO ATUALIZADO: bigquery_loader.py
# Adicionada função para buscar a última semana registrada no BigQuery.
# ==============================================================================

import pandas as pd
import pandas_gbq
import streamlit as st
from google.oauth2 import service_account

# --- Configurações ---
TABLE_ID = "Lancamentos_lrco.relatorios_lrco"


def autenticar_com_service_account():
    """
    Autentica no Google Cloud usando as credenciais da Conta de Serviço
    armazenadas nos Segredos do Streamlit.
    """
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return creds
    except Exception as e:
        st.error("Erro ao carregar as credenciais da Conta de Serviço.")
        st.error(f"Detalhe: {e}")
        return None


def get_latest_week(creds):
    """
    Busca o maior número da coluna 'SEMANA' na tabela do BigQuery.
    """
    try:
        project_id = creds.project_id
        sql_query = f"SELECT MAX(SEMANA) as ultima_semana FROM `{project_id}.{TABLE_ID}`"

        df = pandas_gbq.read_gbq(sql_query, project_id=project_id, credentials=creds)

        # Se a tabela estiver vazia, o resultado será None/NaN.
        if df.empty or pd.isna(df['ultima_semana'].iloc[0]):
            return 0

        return int(df['ultima_semana'].iloc[0])
    except Exception as e:
        st.warning(f"Não foi possível buscar a última semana. Erro: {e}")
        return 0


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """
    Versão final: Valida a coluna SEMANA, sanitiza todas as
    colunas de texto, converte tipos e garante compatibilidade total.
    """
    df_copy = df.copy()

    # Validação da coluna SEMANA
    df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce')
    df_copy['SEMANA'] = df_copy['SEMANA'].fillna(0)
    df_copy['SEMANA'] = df_copy['SEMANA'].astype(int)

    # Limpeza de todas as colunas de texto
    for col in df_copy.select_dtypes(include=['object']).columns:
        if col != 'SEMANA':
            df_copy[col] = df_copy[col].str.strip()
            df_copy[col] = df_copy[col].str.replace('\r', ' ', regex=False).str.replace('\n', ' ', regex=False)

    df_copy.replace("Sem registro", None, inplace=True)

    # Conversão de tipos de dados
    df_copy["DATA_DO_RELATORIO"] = pd.to_datetime(df_copy["DATA_DO_RELATORIO"], format='%d/%m/%Y',
                                                  errors='coerce').dt.date
    df_copy["REGISTRO_DE_AULA"] = pd.to_datetime(df_copy["REGISTRO_DE_AULA"], format='%d/%m/%Y %H:%M:%S',
                                                 errors='coerce')
    df_copy["REGISTRO_DE_CONTEUDO"] = pd.to_datetime(df_copy["REGISTRO_DE_CONTEUDO"], format='%d/%m/%Y %H:%M:%S',
                                                     errors='coerce')
    df_copy['HORARIO'] = pd.to_datetime(df_copy['HORARIO'], format='%H:%M:%S', errors='coerce').dt.time

    return df_copy


def carregar_dados_no_bigquery(df: pd.DataFrame, creds):
    """
    Carrega um DataFrame do Pandas em uma tabela do BigQuery.
    """
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)
        project_id = creds.project_id

        pandas_gbq.to_gbq(
            df_limpo,
            destination_table=TABLE_ID,
            project_id=project_id,
            credentials=creds,
            if_exists='append'
        )
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados no BigQuery: {e}")
        return False


def autenticar_e_carregar(df):
    creds = autenticar_com_service_account()
    if creds:
        return carregar_dados_no_bigquery(df, creds)
    return False