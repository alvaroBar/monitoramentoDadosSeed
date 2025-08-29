# ==============================================================================
# ARQUIVO ATUALIZADO: bigquery_loader.py
# Adicionada função para buscar semanas disponíveis e filtrar backup por semana.
# ==============================================================================

import pandas as pd
import pandas_gbq
import streamlit as st
from google.oauth2 import service_account

# --- Configurações ---
TABLE_ID = "Lancamentos_lrco.relatorios_lrco"


def autenticar_com_service_account():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return creds
    except Exception as e:
        st.error("Erro ao carregar as credenciais da Conta de Serviço.")
        st.error(f"Detalhe: {e}")
        return None


def get_latest_week(creds):
    try:
        project_id = creds.project_id
        sql_query = f"SELECT MAX(SEMANA) as ultima_semana FROM `{project_id}.{TABLE_ID}`"
        df = pandas_gbq.read_gbq(sql_query, project_id=project_id, credentials=creds)
        if df.empty or pd.isna(df['ultima_semana'].iloc[0]):
            return 0
        return int(df['ultima_semana'].iloc[0])
    except Exception as e:
        st.warning(f"Não foi possível buscar a última semana. Erro: {e}")
        return 0


def get_available_weeks(creds):
    """
    Busca todas as semanas únicas presentes na tabela do BigQuery.
    """
    try:
        project_id = creds.project_id
        sql_query = f"SELECT DISTINCT SEMANA FROM `{project_id}.{TABLE_ID}` ORDER BY SEMANA"
        df = pandas_gbq.read_gbq(sql_query, project_id=project_id, credentials=creds)
        if df.empty:
            return []
        # Converte para int para garantir que sejam números e remove nulos
        return sorted([int(week) for week in df['SEMANA'].dropna()])
    except Exception as e:
        st.error(f"Não foi possível buscar a lista de semanas. Erro: {e}")
        return []


def get_all_data_from_bq(creds, weeks=None):
    """
    Busca dados da tabela no BigQuery. Se 'weeks' for fornecido,
    filtra por essas semanas. Caso contrário, busca todos os dados.
    """
    try:
        project_id = creds.project_id
        sql_query = f"SELECT * FROM `{project_id}.{TABLE_ID}`"

        # Adiciona o filtro de semanas se uma lista de semanas for fornecida
        if weeks and isinstance(weeks, list) and len(weeks) > 0:
            numeric_weeks = [int(w) for w in weeks]
            weeks_tuple_str = str(tuple(numeric_weeks))
            # Lida com o caso de tupla de um único elemento que precisa de uma vírgula
            if len(numeric_weeks) == 1:
                weeks_tuple_str = f"({numeric_weeks[0]})"
            sql_query += f" WHERE SEMANA IN {weeks_tuple_str}"

        sql_query += " ORDER BY SEMANA, DATA_DO_RELATORIO"

        df = pandas_gbq.read_gbq(sql_query, project_id=project_id, credentials=creds)
        return df
    except Exception as e:
        st.error(f"Não foi possível buscar os dados do BigQuery. Erro: {e}")
        return pd.DataFrame()


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    df_copy = df.copy()

    if 'SEMANA' in df_copy.columns:
        df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce').fillna(0).astype(int)

    for col in df_copy.select_dtypes(include=['object']).columns:
        if col != 'SEMANA':
            df_copy[col] = df_copy[col].str.strip()
            df_copy[col] = df_copy[col].str.replace('\r', ' ', regex=False).str.replace('\n', ' ', regex=False)

    df_copy.replace("Sem registro", None, inplace=True)

    if 'DATA_DO_RELATORIO' in df_copy.columns:
        df_copy["DATA_DO_RELATORIO"] = pd.to_datetime(df_copy["DATA_DO_RELATORIO"], format='%d/%m/%Y',
                                                      errors='coerce').dt.date
    if 'REGISTRO_DE_AULA' in df_copy.columns:
        df_copy["REGISTRO_DE_AULA"] = pd.to_datetime(df_copy["REGISTRO_DE_AULA"], format='%d/%m/%Y %H:%M:%S',
                                                     errors='coerce')
    if 'REGISTRO_DE_CONTEUDO' in df_copy.columns:
        df_copy["REGISTRO_DE_CONTEUDO"] = pd.to_datetime(df_copy["REGISTRO_DE_CONTEUDO"], format='%d/%m/%Y %H:%M:%S',
                                                         errors='coerce')
    if 'HORARIO' in df_copy.columns:
        df_copy['HORARIO'] = pd.to_datetime(df_copy['HORARIO'], format='%H:%M:%S', errors='coerce').dt.time

    return df_copy


def carregar_dados_no_bigquery(df: pd.DataFrame, creds, if_exists_mode: str):
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)
        project_id = creds.project_id

        pandas_gbq.to_gbq(
            df_limpo,
            destination_table=TABLE_ID,
            project_id=project_id,
            credentials=creds,
            if_exists=if_exists_mode
        )
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados no BigQuery: {e}")
        return False


def autenticar_e_carregar(df, if_exists_mode='append'):
    creds = autenticar_com_service_account()
    if creds:
        return carregar_dados_no_bigquery(df, creds, if_exists_mode)
    return False