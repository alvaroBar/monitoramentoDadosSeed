# ==============================================================================
# ARQUIVO CORRIGIDO: bigquery_loader.py (Versão Multilocatário)
# Corrigido o NameError na função de autenticação.
# ==============================================================================

import streamlit as st
import pandas as pd
import pandas_gbq
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import google.auth
import requests

# --- Configurações de Autenticação ---
# Lidas a partir dos Segredos do Streamlit
try:
    CLIENT_ID = st.secrets.google_oauth.client_id
    CLIENT_SECRET = st.secrets.google_oauth.client_secret
    REDIRECT_URI = st.secrets.google_oauth.redirect_uri
    SCOPES = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        "https://www.googleapis.com/auth/cloud-platform"
    ]
except (AttributeError, KeyError):
    # Este bloco evita que o app quebre se os segredos não estiverem definidos
    CLIENT_ID = None
    CLIENT_SECRET = None
    REDIRECT_URI = None
    st.error("ERRO DE CONFIGURAÇÃO: As credenciais [google_oauth] não foram encontradas nos Segredos do Streamlit.")


def get_google_auth_flow():
    """Cria e retorna o objeto de fluxo de autenticação do Google."""
    if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI]):
        return None

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
    auth_code = st.query_params.get("code")

    if 'credentials' not in st.session_state:
        # Se o código de autorização está na URL, o usuário retornou do login
        if auth_code:
            try:
                flow = get_google_auth_flow()
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
                st.session_state.credentials = creds

                # Busca as informações do usuário
                user_info_endpoint = 'https://www.googleapis.com/oauth2/v1/userinfo'
                headers = {'Authorization': f'Bearer {creds.token}'}
                user_info = requests.get(user_info_endpoint, headers=headers).json()
                st.session_state.user_info = user_info

                # Limpa os parâmetros da URL e reinicia o script
                st.query_params.clear()
                st.rerun()

            except Exception as e:
                st.error(f"Erro ao autenticar o token: {e}")
        else:
            # Se não há credenciais nem código, mostra o botão de login
            flow = get_google_auth_flow()
            if flow:
                auth_url, _ = flow.authorization_url(prompt="consent")
                st.link_button("Login com Google", auth_url, use_container_width=True)


# --- Funções de Interação com o BigQuery ---

def get_latest_week(creds, dataset_id):
    """Busca o maior número de semana na tabela do BigQuery."""
    try:
        project_id = creds.project_id
        query = f"SELECT MAX(SEMANA) as ultima_semana FROM `{project_id}.{dataset_id}.relatorios_lrco`"
        df = pandas_gbq.read_gbq(query, project_id=project_id, credentials=creds)
        if df.empty or pd.isna(df['ultima_semana'][0]):
            return 0
        return int(df['ultima_semana'][0])
    except Exception:
        return 0


def get_available_weeks(creds, dataset_id):
    """Busca todas as semanas únicas e ordenadas da tabela."""
    try:
        project_id = creds.project_id
        query = f"SELECT DISTINCT SEMANA FROM `{project_id}.{dataset_id}.relatorios_lrco` ORDER BY SEMANA"
        df = pandas_gbq.read_gbq(query, project_id=project_id, credentials=creds)
        return df['SEMANA'].dropna().astype(int).tolist()
    except Exception as e:
        st.error(f"Erro ao buscar semanas disponíveis: {e}")
        return []


def get_all_data_from_bq(creds, dataset_id, week_filter=None):
    """Busca dados do BigQuery, opcionalmente filtrando por semana."""
    try:
        project_id = creds.project_id
        week_clause = ""
        if week_filter:
            week_clause = f"WHERE SEMANA IN ({','.join(map(str, week_filter))})"

        query = f"SELECT * FROM `{project_id}.{dataset_id}.relatorios_lrco` {week_clause} ORDER BY SEMANA"
        df = pandas_gbq.read_gbq(query, project_id=project_id, credentials=creds)
        return df
    except Exception as e:
        st.error(f"Erro ao buscar dados do BigQuery: {e}")
        return pd.DataFrame()


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """Versão final: Valida, sanitiza e converte os tipos de dados para a carga."""
    df_copy = df.copy()

    df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce').fillna(0).astype(int)

    for col in df_copy.select_dtypes(include=['object']).columns:
        if col != 'SEMANA':
            df_copy[col] = df_copy[col].str.strip()
            df_copy[col] = df_copy[col].str.replace('\r', ' ', regex=False).str.replace('\n', ' ', regex=False)

    df_copy.replace("Sem registro", None, inplace=True)

    df_copy["DATA_DO_RELATORIO"] = pd.to_datetime(df_copy["DATA_DO_RELATORIO"], format='%d/%m/%Y',
                                                  errors='coerce').dt.date
    df_copy["REGISTRO_DE_AULA"] = pd.to_datetime(df_copy["REGISTRO_DE_AULA"], format='%d/%m/%Y %H:%M:%S',
                                                 errors='coerce')
    df_copy["REGISTRO_DE_CONTEUDO"] = pd.to_datetime(df_copy["REGISTRO_DE_CONTEUDO"], format='%d/%m/%Y %H:%M:%S',
                                                     errors='coerce')
    df_copy['HORARIO'] = pd.to_datetime(df_copy['HORARIO'], format='%H:%M:%S', errors='coerce').dt.time

    return df_copy


def carregar_dados_no_bigquery(df: pd.DataFrame, creds, dataset_id: str, write_mode: str):
    """Carrega um DataFrame do Pandas em uma tabela do BigQuery."""
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)
        project_id = creds.project_id
        table_path = f"{dataset_id}.relatorios_lrco"

        pandas_gbq.to_gbq(
            df_limpo,
            destination_table=table_path,
            project_id=project_id,
            credentials=creds,
            if_exists=write_mode
        )
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados no BigQuery: {e}")
        return False