import streamlit as st
import pandas as pd
import pandas_gbq
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.cloud import bigquery
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

        return {**stats_data, "top_disciplinas": df_top_disciplinas, "registros_por_semana": df_registros_semana}

    except Exception as e:
        st.warning(f"Não foi possível buscar as estatísticas: {e}")
        return {}


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


# --- Funções para Gestão de Análises ---

def list_analysis_tables(creds, dataset_id):
    """Lista todas as tabelas de análise em um dataset."""
    try:
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)
        tables = client.list_tables(dataset_id)
        # Lista tabelas que começam com 'analise_' (antigo) ou 'auditoria_' (novo)
        analysis_tables = [table.table_id for table in tables if
                           table.table_id.startswith('analise_') or table.table_id.startswith('auditoria_')]
        return analysis_tables
    except Exception as e:
        st.error(f"Erro ao listar as tabelas de análise: {e}")
        return []


def create_or_update_analysis(creds, dataset_id, analysis_name, weeks):
    """Cria ou substitui uma tabela de análise com dados de semanas específicas."""
    clean_name = re.sub(r'\W+', '_', analysis_name).lower()
    if not clean_name:
        return False, "O nome da análise é inválido."

    destination_table = f"`{PROJECT_ID}.{dataset_id}.analise_{clean_name}`"
    source_table = f"`{PROJECT_ID}.{dataset_id}.relatorios_lrco`"

    if not weeks:
        return False, "Por favor, selecione pelo menos uma semana para incluir na análise."

    weeks_str = ','.join(map(str, weeks))

    query = f"""
        CREATE OR REPLACE TABLE {destination_table} AS
        SELECT *
        FROM {source_table}
        WHERE SEMANA IN ({weeks_str})
    """
    try:
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)
        query_job = client.query(query)
        query_job.result()
        return True, f"Análise '{analysis_name}' criada/atualizada com sucesso!"
    except Exception as e:
        return False, f"Erro ao criar/atualizar a análise: {e}"


@st.cache_data(ttl=600)
def get_analysis_audit_stats(_creds, dataset_id, table_name):
    """
    Busca estatísticas de auditoria (registros nulos) de uma tabela de análise.
    """
    if not (table_name.startswith('analise_') or table_name.startswith('auditoria_')):
        st.error("Nome de tabela de análise inválido.")
        return None

    table_ref = f"`{PROJECT_ID}.{dataset_id}.{table_name}`"

    try:
        # Consulta 1: Contagens gerais
        counts_query = f"""
            SELECT
                COUNT(*) AS total_registros,
                COUNTIF(REGISTRO_DE_AULA IS NULL) AS total_sem_aula,
                COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) AS total_sem_conteudo
            FROM {table_ref}
        """
        df_counts = pandas_gbq.read_gbq(counts_query, project_id=PROJECT_ID, credentials=_creds)

        # Consulta 2: Detalhes dos registros nulos por escola e disciplina
        details_query = f"""
            SELECT
                ESCOLA,
                DISCIPLINA,
                COUNTIF(REGISTRO_DE_AULA IS NULL) AS aulas_faltantes,
                COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) AS conteudos_faltantes
            FROM {table_ref}
            GROUP BY ESCOLA, DISCIPLINA
            HAVING aulas_faltantes > 0 OR conteudos_faltantes > 0
            ORDER BY aulas_faltantes DESC, conteudos_faltantes DESC
        """
        df_details = pandas_gbq.read_gbq(details_query, project_id=PROJECT_ID, credentials=_creds)

        # Junta os resultados num único dicionário
        stats = {
            "counts": df_counts.to_dict('records')[0] if not df_counts.empty else {},
            "details": df_details
        }
        return stats

    except Exception as e:
        st.error(f"Erro ao gerar o relatório de auditoria: {e}")
        return None

# --- NOVA FUNÇÃO PARA AUDITORIA COMPARATIVA ---
def criar_analise_comparativa(creds, dataset_id, analysis_name, weeks_to_compare, df_from_pdfs):
    """
    Compara dados de PDFs com dados históricos do BigQuery para encontrar pendências restantes.
    """
    if not analysis_name:
        return False, "O nome da análise é inválido."
    if not weeks_to_compare:
        return False, "Pelo menos uma semana deve ser selecionada para comparação."
    if df_from_pdfs.empty:
        return False, "Os PDFs processados não resultaram em dados válidos."

    clean_name = re.sub(r'\W+', '_', analysis_name).lower()
    destination_table = f"{dataset_id}.auditoria_{clean_name}"

    try:
        # 1. Buscar dados históricos do BigQuery para as semanas selecionadas
        st.write("Buscando dados históricos do BigQuery...")
        df_historico = get_all_data_from_bq(creds, dataset_id, week_filter=weeks_to_compare)
        if df_historico.empty:
            return False, f"Nenhum dado histórico encontrado para as semanas: {weeks_to_compare}."

        # 2. Preparar ambos os DataFrames para a comparação
        st.write("Preparando dados para comparação...")
        df_novo_preparado = preparar_dataframe_para_bigquery(df_from_pdfs)
        df_historico_preparado = preparar_dataframe_para_bigquery(df_historico)

        # Chave de identificação única para cada aula
        key_cols = ['DATA_DO_RELATORIO', 'ESCOLA', 'TURMA', 'HORARIO', 'DISCIPLINA']

        # 3. Focar apenas nos registros que TINHAM pendências no histórico
        df_historico_pendente = df_historico_preparado[
            df_historico_preparado['REGISTRO_DE_AULA'].isnull() |
            df_historico_preparado['REGISTRO_DE_CONTEUDO'].isnull()
            ].copy()

        if df_historico_pendente.empty:
            return True, "Parabéns! Não havia pendências nos dados históricos para as semanas selecionadas."

        # 4. Cruzar os dados históricos pendentes com os novos dados dos PDFs
        st.write("Cruzando dados e identificando pendências...")
        df_merged = pd.merge(
            df_historico_pendente[key_cols],  # Apenas as chaves de quem tinha pendência
            df_novo_preparado,
            on=key_cols,
            how='left'  # Traz a correspondência dos novos dados para cada pendência antiga
        )

        # 5. Filtrar para encontrar os que AINDA estão com pendências nos novos dados
        df_ainda_pendente = df_merged[
            df_merged['REGISTRO_DE_AULA'].isnull() |
            df_merged['REGISTRO_DE_CONTEUDO'].isnull()
            ].copy()

        # 6. Se houver pendências, carregar para uma nova tabela
        if not df_ainda_pendente.empty:
            st.write(f"Encontradas {len(df_ainda_pendente)} pendências restantes. Carregando para o BigQuery...")
            pandas_gbq.to_gbq(
                df_ainda_pendente,
                destination_table=destination_table,
                project_id=PROJECT_ID,
                credentials=creds,
                if_exists='replace',
                progress_bar=True
            )
            return True, f"Auditoria '{analysis_name}' concluída! Uma nova tabela `{destination_table}` foi criada com {len(df_ainda_pendente)} pendências."
        else:
            return True, "Auditoria concluída com sucesso! Todas as pendências anteriores foram resolvidas nos novos arquivos."

    except Exception as e:
        return False, f"Erro ao criar a análise comparativa: {e}"