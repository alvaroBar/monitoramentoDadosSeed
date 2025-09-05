import streamlit as st
import pandas as pd
import pandas_gbq
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.cloud import bigquery
import streamlit.components.v1 as components

# --- Configurações de Autenticação (Lidas dos Segredos do Streamlit) ---
try:
    CLIENT_ID = st.secrets.google_oauth.client_id
    CLIENT_SECRET = st.secrets.google_oauth.client_secret
    PROJECT_ID = st.secrets.google_oauth.project_id
    REDIRECT_URI = st.secrets.google_oauth.redirect_uri
    SCOPES = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        "https://www.googleapis.com/auth/bigquery",
    ]
except (AttributeError, KeyError):
    st.error(
        "ERRO DE CONFIGURAÇÃO: A seção [google_oauth] não foi encontrada ou está incompleta nos Segredos do Streamlit.")
    st.stop()


# --- Funções de Autenticação ---

def get_google_auth_flow():
    """Cria e retorna o objeto de fluxo de autenticação do Google."""
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uri": REDIRECT_URI,
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
        if auth_code:
            try:
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
                st.session_state.credentials = creds

                user_info_service = build('oauth2', 'v2', credentials=creds)
                user_info = user_info_service.userinfo().get().execute()

                st.session_state.user_info = user_info
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao obter o token de acesso: {e}")
                st.stop()
        else:
            auth_url, _ = flow.authorization_url(prompt="select_account")

            # --- SOLUÇÃO ROBUSTA: Usa o st.link_button e melhora a experiência do usuário ---
            st.link_button("Login com Google", auth_url, use_container_width=True, type="primary")

            # Exibe uma mensagem clara para guiar o usuário
            st.info(
                "ℹ️ Uma nova aba será aberta para o login com o Google. Após a autenticação, pode fechar a aba de login e voltar para esta, que será atualizada automaticamente.")
            st.stop()


# --- Funções de Interação com o BigQuery ---

def get_dashboard_stats(creds, dataset_id):
    """
    Busca estatísticas agregadas do BigQuery para o dashboard.
    Usa consultas separadas para maior robustez.
    """
    try:
        # Consulta 1: Estatísticas gerais
        stats_query = f"""
            SELECT
                COUNT(*) AS total_registros,
                MAX(DATA_DO_RELATORIO) AS ultima_data,
                COUNT(DISTINCT SEMANA) as total_semanas
            FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco`
        """
        df_stats = pandas_gbq.read_gbq(stats_query, project_id=PROJECT_ID, credentials=creds)
        stats_data = df_stats.to_dict('records')[0] if not df_stats.empty else {}

        # Consulta 2: Top 5 Disciplinas
        disciplinas_query = f"""
            SELECT DISCIPLINA, COUNT(*) AS contagem
            FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco`
            WHERE DISCIPLINA IS NOT NULL
            GROUP BY DISCIPLINA
            ORDER BY contagem DESC
            LIMIT 5
        """
        df_top_disciplinas = pandas_gbq.read_gbq(disciplinas_query, project_id=PROJECT_ID, credentials=creds)

        # Consulta 3: Registros por semana
        semana_query = f"""
            SELECT SEMANA, COUNT(*) AS contagem
            FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco`
            WHERE SEMANA IS NOT NULL
            GROUP BY SEMANA
            ORDER BY SEMANA
        """
        df_registros_semana = pandas_gbq.read_gbq(semana_query, project_id=PROJECT_ID, credentials=creds)
        if not df_registros_semana.empty:
            df_registros_semana = df_registros_semana.set_index('SEMANA')

        return {
            "total_registros": stats_data.get('total_registros', 0),
            "ultima_data": stats_data.get('ultima_data'),
            "total_semanas": stats_data.get('total_semanas', 0),
            "top_disciplinas": df_top_disciplinas,
            "registros_por_semana": df_registros_semana
        }

    except Exception as e:
        st.warning(f"Não foi possível buscar as estatísticas. A tabela pode estar vazia ou ocorreu um erro: {e}")
        return {
            "total_registros": 0, "ultima_data": None, "total_semanas": 0,
            "top_disciplinas": pd.DataFrame(columns=['DISCIPLINA', 'contagem']),
            "registros_por_semana": pd.DataFrame(columns=['contagem'])
        }


def get_latest_week(creds, dataset_id):
    """Busca o maior número da coluna 'SEMANA' no BigQuery."""
    sql_query = f"SELECT MAX(SEMANA) as max_semana FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco`"
    try:
        df = pandas_gbq.read_gbq(sql_query, project_id=PROJECT_ID, credentials=creds)
        latest_week = df['max_semana'].iloc[0]
        return int(latest_week) if pd.notna(latest_week) else 0
    except Exception:
        return 0


def carregar_dados_no_bigquery(df: pd.DataFrame, creds, dataset_id, mode='append'):
    """Carrega um DataFrame do Pandas em uma tabela do BigQuery."""
    destination_table = f"{dataset_id}.relatorios_lrco"
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)
        pandas_gbq.to_gbq(
            df_limpo,
            destination_table=destination_table,
            project_id=PROJECT_ID,
            credentials=creds,
            if_exists=mode,
            progress_bar=True
        )
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados no BigQuery: {e}")
        return False


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara o DataFrame para ser carregado no BigQuery."""
    df_copy = df.copy()

    # Validação da coluna SEMANA
    df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce').fillna(0).astype(int)

    # Limpeza de colunas de texto
    for col in df_copy.select_dtypes(include=['object']).columns:
        if col != 'SEMANA':
            df_copy[col] = df_copy[col].str.strip().str.replace('\r', ' ', regex=False).str.replace('\n', ' ',
                                                                                                    regex=False)

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


def get_available_weeks(creds, dataset_id):
    """Busca todas as semanas únicas e ordenadas disponíveis no BigQuery."""
    sql_query = f"SELECT DISTINCT SEMANA FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco` ORDER BY SEMANA"
    try:
        df = pandas_gbq.read_gbq(sql_query, project_id=PROJECT_ID, credentials=creds)
        return df['SEMANA'].tolist()
    except Exception:
        return []


def get_all_data_from_bq(creds, dataset_id, week_filter=None):
    """Busca dados do BigQuery, com um filtro opcional por semana."""
    table_ref = f"`{PROJECT_ID}.{dataset_id}.relatorios_lrco`"
    sql_query = f"SELECT * FROM {table_ref}"

    if week_filter:
        sql_query += f" WHERE SEMANA IN ({','.join(map(str, week_filter))})"

    try:
        df = pandas_gbq.read_gbq(sql_query, project_id=PROJECT_ID, credentials=creds)
        return df
    except Exception:
        return pd.DataFrame()


def delete_week_data(creds, dataset_id, week_to_delete):
    """Apaga todos os registros de uma semana específica no BigQuery."""
    try:
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)
        table_ref = f"`{PROJECT_ID}.{dataset_id}.relatorios_lrco`"

        delete_query = f"DELETE FROM {table_ref} WHERE SEMANA = {week_to_delete}"

        query_job = client.query(delete_query)
        query_job.result()

        return True, f"Registros da semana {week_to_delete} apagados com sucesso."
    except Exception as e:
        return False, f"Erro ao apagar os dados da semana: {e}"

