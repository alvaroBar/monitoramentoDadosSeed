import streamlit as st
import pandas as pd
import pandas_gbq
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.cloud import bigquery
import streamlit.components.v1 as components
import uuid
import re

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

            st.link_button("Login com Google", auth_url, use_container_width=True, type="primary")
            st.info("ℹ️ Uma nova aba será aberta para o login. Após a autenticação, esta aba pode ser fechada.")
            st.stop()


# --- Funções de Interação com o BigQuery ---

def get_dashboard_stats(creds, dataset_id):
    """
    Busca estatísticas agregadas do BigQuery para o dashboard.
    Usa consultas separadas para maior robustez e adiciona contagens de nulos.
    """
    try:
        stats_query = f"""
            SELECT
                COUNT(*) AS total_registros,
                MAX(DATA_DO_RELATORIO) AS ultima_data,
                COUNT(DISTINCT SEMANA) as total_semanas,
                COUNTIF(REGISTRO_DE_AULA IS NULL) as sem_registro_aula,
                COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) as sem_registro_conteudo
            FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco`
        """
        df_stats = pandas_gbq.read_gbq(stats_query, project_id=PROJECT_ID, credentials=creds)
        stats_data = df_stats.to_dict('records')[0] if not df_stats.empty else {}

        disciplinas_query = f"""
            SELECT DISCIPLINA, COUNT(*) AS contagem
            FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco`
            WHERE DISCIPLINA IS NOT NULL
            GROUP BY DISCIPLINA
            ORDER BY contagem DESC
            LIMIT 5
        """
        df_top_disciplinas = pandas_gbq.read_gbq(disciplinas_query, project_id=PROJECT_ID, credentials=creds)

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
            "sem_registro_aula": stats_data.get('sem_registro_aula', 0),
            "sem_registro_conteudo": stats_data.get('sem_registro_conteudo', 0),
            "top_disciplinas": df_top_disciplinas,
            "registros_por_semana": df_registros_semana
        }

    except Exception as e:
        st.warning(f"Não foi possível buscar as estatísticas. A tabela pode estar vazia ou ocorreu um erro: {e}")
        return {
            "total_registros": 0, "ultima_data": None, "total_semanas": 0,
            "sem_registro_aula": 0, "sem_registro_conteudo": 0,
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
    """Carrega um DataFrame do Pandas na tabela histórica (relatorios_lrco)."""
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
        st.error(f"Erro ao carregar dados na tabela histórica: {e}")
        return False


def upsert_dados_bimestre(df: pd.DataFrame, creds, dataset_id):
    """
    Atualiza ou insere (upsert) dados na tabela de bimestre (relatorios_bimestre).
    """
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)

        temp_table_id = f"{PROJECT_ID}.{dataset_id}.temp_upsert_{str(uuid.uuid4()).replace('-', '')}"
        pandas_gbq.to_gbq(df_limpo, temp_table_id, project_id=PROJECT_ID, credentials=creds)

        target_table = f"`{PROJECT_ID}.{dataset_id}.relatorios_bimestre`"
        source_table = f"`{temp_table_id}`"

        merge_query = f"""
            MERGE {target_table} T
            USING {source_table} S
            ON  T.DATA_DO_RELATORIO = S.DATA_DO_RELATORIO
            AND T.ESCOLA = S.ESCOLA AND T.TURMA = S.TURMA
            AND T.HORARIO = S.HORARIO AND T.DISCIPLINA = S.DISCIPLINA
            WHEN MATCHED THEN
                UPDATE SET
                    T.REGISTRO_DE_AULA = S.REGISTRO_DE_AULA,
                    T.REGISTRO_DE_CONTEUDO = S.REGISTRO_DE_CONTEUDO,
                    T.SEMANA = S.SEMANA
            WHEN NOT MATCHED THEN
                INSERT (SEMANA, DATA_DO_RELATORIO, MUNICIPIO, ESCOLA, TURMA, HORARIO, DISCIPLINA, REGISTRO_DE_AULA, REGISTRO_DE_CONTEUDO)
                VALUES (S.SEMANA, S.DATA_DO_RELATORIO, S.MUNICIPIO, S.ESCOLA, S.TURMA, S.HORARIO, S.DISCIPLINA, S.REGISTRO_DE_AULA, S.REGISTRO_DE_CONTEUDO)
        """
        query_job = client.query(merge_query)
        query_job.result()
        client.delete_table(temp_table_id)
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar dados na tabela de bimestre: {e}")
        try:
            client.delete_table(temp_table_id)
        except:
            pass
        return False


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara o DataFrame para ser carregado no BigQuery."""
    df_copy = df.copy()

    df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce').fillna(0).astype(int)

    for col in df_copy.select_dtypes(include=['object']).columns:
        if col != 'SEMANA':
            df_copy[col] = df_copy[col].str.strip().str.replace('\r', ' ', regex=False).str.replace('\n', ' ',
                                                                                                    regex=False)

    df_copy.replace("Sem registro", None, inplace=True)

    df_copy["DATA_DO_RELATORIO"] = pd.to_datetime(df_copy["DATA_DO_RELATORIO"], format='%d/%m/%Y',
                                                  errors='coerce').dt.date
    df_copy["REGISTRO_DE_AULA"] = pd.to_datetime(df_copy["REGISTRO_DE_AULA"], format='%d/%m/%Y %H:%M:%S',
                                                 errors='coerce')
    df_copy["REGISTRO_DE_CONTEUDO"] = pd.to_datetime(df_copy["REGISTRO_DE_CONTEUDO"], format='%d/%m/%Y %H:%M:%S',
                                                     errors='coerce')
    df_copy['HORARIO'] = pd.to_datetime(df_copy['HORARIO'], format='%H:%M:%S', errors='coerce').dt.time

    return df_copy


def get_available_weeks(creds, dataset_id):
    """Busca todas as semanas únicas e ordenadas disponíveis na tabela histórica."""
    sql_query = f"SELECT DISTINCT SEMANA FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco` ORDER BY SEMANA"
    try:
        df = pandas_gbq.read_gbq(sql_query, project_id=PROJECT_ID, credentials=creds)
        return [week for week in df['SEMANA'].tolist() if week is not None]
    except Exception:
        return []


def get_all_data_from_bq(creds, dataset_id, week_filter=None):
    """Busca dados da tabela histórica, com um filtro opcional por semana."""
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
    """Apaga os registros de uma semana específica da tabela histórica."""
    try:
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)
        table_ref = f"`{PROJECT_ID}.{dataset_id}.relatorios_lrco`"
        delete_query = f"DELETE FROM {table_ref} WHERE SEMANA = {week_to_delete}"
        query_job = client.query(delete_query)
        query_job.result()
        return True, f"Registros da semana {week_to_delete} apagados com sucesso."
    except Exception as e:
        return False, f"Erro ao apagar os dados da semana: {e}"


@st.cache_data(ttl=3600)
def get_filter_options(_creds, dataset_id):
    """Busca todos os valores únicos para os filtros da página de consulta de uma só vez."""
    table_ref = f"`{PROJECT_ID}.{dataset_id}.relatorios_lrco`"
    query = f"""
    SELECT
      (SELECT ARRAY_AGG(DISTINCT SEMANA IGNORE NULLS ORDER BY SEMANA) FROM {table_ref}) AS semanas,
      (SELECT ARRAY_AGG(DISTINCT MUNICIPIO IGNORE NULLS ORDER BY MUNICIPIO) FROM {table_ref}) AS municipios,
      (SELECT ARRAY_AGG(DISTINCT ESCOLA IGNORE NULLS ORDER BY ESCOLA) FROM {table_ref}) AS escolas,
      (SELECT ARRAY_AGG(DISTINCT DISCIPLINA IGNORE NULLS ORDER BY DISCIPLINA) FROM {table_ref}) AS disciplinas,
      (SELECT ARRAY_AGG(DISTINCT TURMA IGNORE NULLS ORDER BY TURMA) FROM {table_ref}) AS turmas,
      (SELECT MIN(DATA_DO_RELATORIO) FROM {table_ref}) as min_data,
      (SELECT MAX(DATA_DO_RELATORIO) FROM {table_ref}) as max_data
    """
    try:
        df = pandas_gbq.read_gbq(query, project_id=PROJECT_ID, credentials=_creds)
        if not df.empty:
            return df.to_dict('records')[0]
    except Exception as e:
        st.error(f"Erro ao buscar opções de filtro: {e}")
    return {"semanas": [], "municipios": [], "escolas": [], "disciplinas": [], "turmas": [], "min_data": None,
            "max_data": None}


def _format_sql_in_clause(values):
    """Formata uma lista de valores para uma cláusula IN, tratando aspas."""
    if not values: return "('')"
    formatted_values = [f"'{str(v).replace("'", "''")}'" for v in values]
    return f"({', '.join(formatted_values)})"


def query_data_from_bq(creds, dataset_id, filters):
    """Busca dados do BigQuery com base em um dicionário de filtros dinâmicos."""
    table_ref = f"`{PROJECT_ID}.{dataset_id}.relatorios_lrco`"
    sql_query = f"SELECT * FROM {table_ref}"
    where_clauses = []

    if filters.get("null_filter"):
        null_filter = filters["null_filter"]
        if null_filter == "aula":
            where_clauses.append("REGISTRO_DE_AULA IS NULL")
        elif null_filter == "conteudo":
            where_clauses.append("REGISTRO_DE_CONTEUDO IS NULL")
        elif null_filter == "ambos":
            where_clauses.append("(REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL)")

    if filters.get("semanas"): where_clauses.append(f"SEMANA IN ({','.join(map(str, filters['semanas']))})")
    if filters.get("municipios"): where_clauses.append(f"MUNICIPIO IN {_format_sql_in_clause(filters['municipios'])}")
    if filters.get("escolas"): where_clauses.append(f"ESCOLA IN {_format_sql_in_clause(filters['escolas'])}")
    if filters.get("turmas"): where_clauses.append(f"TURMA IN {_format_sql_in_clause(filters['turmas'])}")
    if filters.get("disciplinas"): where_clauses.append(
        f"DISCIPLINA IN {_format_sql_in_clause(filters['disciplinas'])}")
    if filters.get("data_inicio") and filters.get("data_fim"):
        data_inicio_str = filters['data_inicio'].strftime('%Y-%m-%d')
        data_fim_str = filters['data_fim'].strftime('%Y-%m-%d')
        where_clauses.append(f"DATA_DO_RELATORIO BETWEEN '{data_inicio_str}' AND '{data_fim_str}'")

    if where_clauses: sql_query += " WHERE " + " AND ".join(where_clauses)
    sql_query += " ORDER BY DATA_DO_RELATORIO DESC, HORARIO"
    try:
        return pandas_gbq.read_gbq(sql_query, project_id=PROJECT_ID, credentials=creds)
    except Exception as e:
        st.error(f"Erro ao executar a consulta no BigQuery: {e}")
        return pd.DataFrame()


# --- NOVAS FUNÇÕES PARA GESTÃO DE ANÁLISES ---

def list_analysis_tables(creds, dataset_id):
    """Lista todas as tabelas de análise (que começam com 'analise_') em um dataset."""
    try:
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)
        tables = client.list_tables(dataset_id)
        # Filtra para manter apenas as tabelas que representam análises
        analysis_tables = [table.table_id for table in tables if table.table_id.startswith('analise_')]
        return analysis_tables
    except Exception as e:
        st.error(f"Erro ao listar as tabelas de análise: {e}")
        return []


def create_or_update_analysis(creds, dataset_id, analysis_name, weeks):
    """
    Cria ou substitui uma tabela de análise com dados de semanas específicas
    da tabela histórica.
    """
    # Valida e formata o nome da análise para ser um nome de tabela válido
    clean_name = re.sub(r'\W+', '_', analysis_name).lower()
    if not clean_name:
        return False, "O nome da análise é inválido."

    destination_table = f"`{PROJECT_ID}.{dataset_id}.analise_{clean_name}`"
    source_table = f"`{PROJECT_ID}.{dataset_id}.relatorios_lrco`"

    if not weeks:
        return False, "Por favor, selecione pelo menos uma semana para incluir na análise."

    weeks_str = ','.join(map(str, weeks))

    # Usa 'CREATE OR REPLACE TABLE' para criar ou atualizar a tabela de forma atômica
    query = f"""
        CREATE OR REPLACE TABLE {destination_table} AS
        SELECT *
        FROM {source_table}
        WHERE SEMANA IN ({weeks_str})
    """
    try:
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)
        query_job = client.query(query)
        query_job.result()  # Aguarda a conclusão
        return True, f"Análise '{analysis_name}' criada/atualizada com sucesso!"
    except Exception as e:
        return False, f"Erro ao criar/atualizar a análise: {e}"

