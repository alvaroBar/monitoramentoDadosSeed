# ==============================================================================
# ARQUIVO COMPLETO: bigquery_loader.py (Versão Multilocatário com Depuração)
# Todas as funções agora recebem um 'dataset_id' para operar no
# conjunto de dados correto do usuário.
# ==============================================================================

import streamlit as st
import pandas as pd
import pandas_gbq
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import requests

# --- Bloco de Verificação e Depuração dos Segredos ---
# Esta nova seção irá nos mostrar exatamente o que o Streamlit está lendo.

if "google_oauth" not in st.secrets:
    st.error("ERRO DE CONFIGURAÇÃO: A seção [google_oauth] não foi encontrada nos Segredos do Streamlit.")
    st.info(
        "Por favor, verifique se o cabeçalho `[google_oauth]` está presente e escrito corretamente nos seus segredos.")
    # A linha abaixo é para depuração. Ela mostra todo o conteúdo que o Streamlit conseguiu ler.
    st.write("Conteúdo atual dos segredos que o Streamlit está vendo:", st.secrets.to_dict())
    st.stop()

try:
    CLIENT_ID = st.secrets.google_oauth.client_id
    CLIENT_SECRET = st.secrets.google_oauth.client_secret
    REDIRECT_URI = st.secrets.google_oauth.redirect_uri
    # Verifica se as chaves essenciais dentro da seção existem
    if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI]):
        st.error(
            "ERRO DE CONFIGURAÇÃO: Uma ou mais chaves (client_id, client_secret, redirect_uri) estão faltando dentro da seção [google_oauth].")
        st.stop()
except AttributeError:
    st.error("ERRO DE CONFIGURAÇÃO: A seção [google_oauth] parece estar mal formatada nos Segredos do Streamlit.")
    st.write("Conteúdo atual dos segredos que o Streamlit está vendo:", st.secrets.to_dict())
    st.stop()

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
    "https://www.googleapis.com/auth/bigquery"
]

# --- Configurações do BigQuery ---
TABLE_NAME = "relatorios_lrco"  # O nome da tabela é o mesmo em todos os datasets


def get_google_auth_flow():
    """Cria e retorna o objeto de fluxo de autenticação do Google."""
    # --- CORREÇÃO AQUI ---
    # O nome correto do método é from_client_config
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def autenticar_usuario():
    """Gerencia o fluxo de login/logout do usuário."""
    flow = get_google_auth_flow()
    auth_code = st.query_params.get("code")

    if 'credentials' not in st.session_state:
        if not auth_code:
            auth_url, _ = flow.authorization_url(prompt="consent")
            st.link_button("Login com Google", auth_url, use_container_width=True)
            st.stop()
        else:
            try:
                flow.fetch_token(code=auth_code)
                st.session_state.credentials = flow.credentials
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao buscar o token de autenticação: {e}")
                st.stop()
    else:
        creds = st.session_state.credentials
        if isinstance(creds, Credentials) and creds.valid:
            user_info_req = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            if user_info_req.status_code == 200:
                st.session_state.user_info = user_info_req.json()
            else:  # Token inválido ou expirado
                del st.session_state.credentials
                st.rerun()
        else:  # Credenciais inválidas
            del st.session_state.credentials
            st.rerun()


def get_latest_week(creds, dataset_id):
    """Busca o maior número da coluna 'SEMANA' no dataset do usuário."""
    try:
        project_id = creds.project_id
        full_table_id = f"{project_id}.{dataset_id}.{TABLE_NAME}"
        sql_query = f"SELECT MAX(SEMANA) as ultima_semana FROM `{full_table_id}`"
        df = pandas_gbq.read_gbq(sql_query, project_id=project_id, credentials=creds)
        if df.empty or pd.isna(df['ultima_semana'].iloc[0]):
            return 0
        return int(df['ultima_semana'].iloc[0])
    except Exception:
        # Retorna 0 se a tabela não existir ou estiver vazia
        return 0


def get_available_weeks(creds, dataset_id):
    """Busca todas as semanas únicas presentes no dataset do usuário."""
    try:
        project_id = creds.project_id
        full_table_id = f"{project_id}.{dataset_id}.{TABLE_NAME}"
        sql_query = f"SELECT DISTINCT SEMANA FROM `{full_table_id}` ORDER BY SEMANA"
        df = pandas_gbq.read_gbq(sql_query, project_id=project_id, credentials=creds)
        if df.empty:
            return []
        return sorted([int(week) for week in df['SEMANA'].dropna()])
    except Exception:
        return []


def get_all_data_from_bq(creds, dataset_id, weeks=None):
    """Busca dados do dataset do usuário, com filtro opcional por semanas."""
    try:
        project_id = creds.project_id
        full_table_id = f"{project_id}.{dataset_id}.{TABLE_NAME}"
        sql_query = f"SELECT * FROM `{full_table_id}`"

        if weeks and isinstance(weeks, list) and len(weeks) > 0:
            weeks_tuple_str = str(tuple(weeks))
            if len(weeks) == 1:
                weeks_tuple_str = f"({weeks[0]})"
            sql_query += f" WHERE SEMANA IN {weeks_tuple_str}"

        sql_query += " ORDER BY SEMANA, DATA_DO_RELATORIO"
        df = pandas_gbq.read_gbq(sql_query, project_id=project_id, credentials=creds)
        return df
    except Exception as e:
        st.error(f"Não foi possível buscar os dados do BigQuery. Erro: {e}")
        return pd.DataFrame()


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara o DataFrame para ser carregado no BigQuery."""
    df_copy = df.copy()

    if 'SEMANA' in df_copy.columns:
        df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce').fillna(0).astype(int)

    for col in df_copy.select_dtypes(include=['object']).columns:
        df_copy[col] = df_copy[col].str.strip().str.replace('\r', ' ', regex=False).str.replace('\n', ' ', regex=False)

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


def carregar_dados_no_bigquery(df: pd.DataFrame, creds, dataset_id, if_exists_mode: str):
    """Carrega um DataFrame no dataset do BigQuery do usuário."""
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)
        project_id = creds.project_id
        full_table_id = f"{dataset_id}.{TABLE_NAME}"

        pandas_gbq.to_gbq(
            df_limpo,
            destination_table=full_table_id,
            project_id=project_id,
            credentials=creds,
            if_exists=if_exists_mode
        )
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados no BigQuery: {e}")
        return False