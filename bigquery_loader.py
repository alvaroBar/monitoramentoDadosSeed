# ==============================================================================
# ARQUIVO: bigquery_loader.py
# CORRIGIDO: Função criar_analise_comparativa refeita para seguir a nova lógica de auditoria de pendências.
# ==============================================================================

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


def carregar_dados_no_bigquery(df: pd.DataFrame, creds, dataset_id, mode='append', table_name='relatorios_lrco'):
    """Carrega um DataFrame do Pandas para uma tabela especificada no BigQuery."""
    destination_table = f"{dataset_id}.{table_name}"
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)
        pandas_gbq.to_gbq(
            df_limpo,
            destination_table=destination_table,
            project_id=PROJECT_ID,
            credentials=creds,
            if_exists=mode,
            progress_bar=False
        )
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados na tabela {destination_table}: {e}")
        return False


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara o DataFrame para ser carregado no BigQuery."""
    df_copy = df.copy()

    if 'SEMANA' in df_copy.columns:
        df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce').fillna(0).astype(int)

    for col in df_copy.select_dtypes(include=['object']).columns:
        if col != 'SEMANA':
            df_copy[col] = df_copy[col].str.strip().str.replace('\r', ' ', regex=False).str.replace('\n', ' ',
                                                                                                    regex=False)

    df_copy.replace("Sem registro", pd.NaT, inplace=True)

    df_copy["DATA_DO_RELATORIO"] = pd.to_datetime(df_copy["DATA_DO_RELATORIO"], format='%d/%m/%Y',
                                                  errors='coerce').dt.date
    df_copy["REGISTRO_DE_AULA"] = pd.to_datetime(df_copy["REGISTRO_DE_AULA"], format='%d/%m/%Y %H:%M:%S',
                                                 errors='coerce')
    df_copy["REGISTRO_DE_CONTEUDO"] = pd.to_datetime(df_copy["REGISTRO_DE_CONTEUDO"], format='%d/%m/%Y %H:%M:%S',
                                                     errors='coerce')
    if 'HORARIO' in df_copy.columns:
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


def list_analysis_tables(creds, dataset_id):
    """Lista todas as tabelas de análise (que começam com 'auditoria_') em um dataset."""
    try:
        client = bigquery.Client(credentials=creds, project=PROJECT_ID)
        tables = client.list_tables(dataset_id)
        analysis_tables = [table.table_id for table in tables if table.table_id.startswith('auditoria_')]
        return analysis_tables
    except Exception as e:
        st.error(f"Erro ao listar as tabelas de análise: {e}")
        return []


@st.cache_data(ttl=600)
def get_analysis_audit_stats(_creds, dataset_id, table_name):
    """
    Busca estatísticas de auditoria (registros nulos) de uma tabela de análise.
    """
    if not table_name.startswith('auditoria_'):
        st.error("Nome de tabela de análise inválido.")
        return None

    table_ref = f"`{PROJECT_ID}.{dataset_id}.{table_name}`"

    try:
        counts_query = f"""
            SELECT
                COUNT(*) AS total_registros,
                COUNTIF(REGISTRO_DE_AULA IS NULL) AS total_sem_aula,
                COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) AS total_sem_conteudo
            FROM {table_ref}
        """
        df_counts = pandas_gbq.read_gbq(counts_query, project_id=PROJECT_ID, credentials=_creds)

        details_query = f"""
            SELECT
                ESCOLA,
                DISCIPLINA,
                TURMA,
                COUNTIF(REGISTRO_DE_AULA IS NULL) AS aulas_faltantes,
                COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) AS conteudos_faltantes
            FROM {table_ref}
            GROUP BY ESCOLA, DISCIPLINA, TURMA
            HAVING aulas_faltantes > 0 OR conteudos_faltantes > 0
            ORDER BY ESCOLA, DISCIPLINA, TURMA
        """
        df_details = pandas_gbq.read_gbq(details_query, project_id=PROJECT_ID, credentials=_creds)

        stats = {
            "counts": df_counts.to_dict('records')[0] if not df_counts.empty else {},
            "details": df_details
        }
        return stats

    except Exception as e:
        st.error(f"Erro ao gerar o relatório de auditoria: {e}")
        return None


# --- FUNÇÃO DE AUDITORIA COMPARATIVA REFEITA ---
def criar_analise_comparativa(creds, dataset_id, analysis_name, weeks_to_compare, df_from_parquet):
    """
    Compara dados de um arquivo Parquet com pendências históricas do BigQuery.
    """
    clean_name = re.sub(r'\W+', '_', analysis_name).lower()
    if not clean_name:
        return False, "O nome da análise é inválido."

    destination_table_name = f"auditoria_{clean_name}"

    try:
        # 1. Buscar do BQ APENAS os registros PENDENTES das semanas selecionadas
        st.write("Passo A: Buscando pendências históricas no BigQuery...")
        weeks_str = ','.join(map(str, weeks_to_compare))
        query_pendentes = f"""
            SELECT *
            FROM `{PROJECT_ID}.{dataset_id}.relatorios_lrco`
            WHERE SEMANA IN ({weeks_str})
            AND (REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL)
        """
        df_historico_pendente = pandas_gbq.read_gbq(query_pendentes, project_id=PROJECT_ID, credentials=creds)

        if df_historico_pendente.empty:
            return True, "Parabéns! Não havia pendências nos dados históricos para as semanas selecionadas."

        # 2. Preparar ambos os DataFrames
        st.write("Passo B: Preparando dados para comparação...")
        df_novo_preparado = preparar_dataframe_para_bigquery(df_from_parquet)
        df_historico_preparado = preparar_dataframe_para_bigquery(df_historico_pendente)

        key_cols = ['DATA_DO_RELATORIO', 'ESCOLA', 'TURMA', 'HORARIO', 'DISCIPLINA']

        # 3. Cruzar as pendências históricas com os novos dados
        st.write("Passo C: Cruzando dados e identificando o que ainda está pendente...")
        df_merged = pd.merge(
            df_historico_preparado[key_cols],  # Usamos apenas as chaves do que estava pendente
            df_novo_preparado,
            on=key_cols,
            how='left'  # Traz os novos registros correspondentes para as pendências antigas
        )

        # 4. Filtrar para encontrar os que AINDA estão com pendências no novo arquivo
        df_ainda_pendente = df_merged[
            pd.isna(df_merged['REGISTRO_DE_AULA']) |
            pd.isna(df_merged['REGISTRO_DE_CONTEUDO'])
            ].copy()

        # 5. Se houver pendências, carregar para uma nova tabela
        if not df_ainda_pendente.empty:
            st.write(
                f"Passo D: Encontradas {len(df_ainda_pendente)} pendências restantes. Carregando para a tabela `{destination_table_name}`...")
            # Adiciona a coluna SEMANA para consistência
            df_ainda_pendente['SEMANA'] = 0  # Auditoria não é vinculada a uma semana específica

            sucesso_carga = carregar_dados_no_bigquery(
                df_ainda_pendente, creds, dataset_id,
                mode='replace', table_name=destination_table_name
            )
            if sucesso_carga:
                return True, f"Auditoria '{analysis_name}' concluída! Uma nova tabela `{destination_table_name}` foi criada com {len(df_ainda_pendente)} pendências."
            else:
                return False, f"Falha ao carregar a tabela de resultados `{destination_table_name}` no BigQuery."
        else:
            return True, "Auditoria concluída com sucesso! Todas as pendências anteriores foram resolvidas nos novos arquivos."

    except Exception as e:
        return False, f"Erro ao criar a análise comparativa: {e}"