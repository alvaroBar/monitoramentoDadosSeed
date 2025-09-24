# services/bigquery_service.py
import streamlit as st
import pandas as pd
import pandas_gbq
from google.cloud import bigquery
from utils import config
import datetime  # Adicionado para a função de consulta


class BigQueryService:
    def __init__(self, credentials, dataset_id):
        if not credentials:
            raise ValueError("Credenciais são necessárias para inicializar o BigQueryService.")
        self.creds = credentials
        self.dataset_id = dataset_id
        self.project_id = config.PROJECT_ID
        self.table_id = f"`{self.project_id}.{self.dataset_id}.relatorios_lrco`"

    # --- Métodos de Escrita e Deleção ---

    def carregar_dados(self, df: pd.DataFrame, table_name='relatorios_lrco', mode='append'):
        destination_table = f"{self.dataset_id}.{table_name}"
        try:
            pandas_gbq.to_gbq(df, destination_table, self.project_id, credentials=self.creds, if_exists=mode,
                              progress_bar=False)
            return True
        except Exception as e:
            st.error(f"Erro ao carregar dados na tabela {destination_table}: {e}")
            return False

    def delete_week_data(self, week_to_delete):
        try:
            client = bigquery.Client(credentials=self.creds, project=self.project_id)
            delete_query = f"DELETE FROM {self.table_id} WHERE SEMANA = {week_to_delete}"
            query_job = client.query(delete_query)
            query_job.result()
            return True, f"Registros da semana {week_to_delete} apagados."
        except Exception as e:
            return False, f"Erro ao apagar os dados da semana: {e}"

    # --- Métodos de Leitura (Queries) ---

    def get_dashboard_stats(self):
        """Busca estatísticas agregadas do BigQuery para o dashboard."""
        try:
            stats_query = f"""
                SELECT
                    COUNT(*) AS total_registros,
                    MAX(DATA_DO_RELATORIO) AS ultima_data,
                    COUNT(DISTINCT SEMANA) as total_semanas,
                    COUNTIF(REGISTRO_DE_AULA IS NULL) as sem_registro_aula,
                    COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) as sem_registro_conteudo
                FROM {self.table_id}
            """
            df_stats = pandas_gbq.read_gbq(stats_query, project_id=self.project_id, credentials=self.creds)
            stats_data = df_stats.to_dict('records')[0] if not df_stats.empty else {}

            disciplinas_query = f"""
                SELECT DISCIPLINA, COUNT(*) AS contagem FROM {self.table_id}
                WHERE DISCIPLINA IS NOT NULL GROUP BY DISCIPLINA ORDER BY contagem DESC LIMIT 5
            """
            df_top_disciplinas = pandas_gbq.read_gbq(disciplinas_query, project_id=self.project_id,
                                                     credentials=self.creds)

            semana_query = f"""
                SELECT SEMANA, COUNT(*) AS contagem FROM {self.table_id}
                WHERE SEMANA IS NOT NULL GROUP BY SEMANA ORDER BY SEMANA
            """
            df_registros_semana = pandas_gbq.read_gbq(semana_query, project_id=self.project_id, credentials=self.creds)
            if not df_registros_semana.empty:
                df_registros_semana = df_registros_semana.set_index('SEMANA')

            return {**stats_data, "top_disciplinas": df_top_disciplinas, "registros_por_semana": df_registros_semana}
        except Exception as e:
            st.warning(f"Não foi possível buscar as estatísticas do dashboard: {e}")
            return {}

    def get_latest_week(self):
        """Busca o maior número da coluna 'SEMANA' no BigQuery."""
        sql_query = f"SELECT MAX(SEMANA) as max_semana FROM {self.table_id}"
        try:
            df = pandas_gbq.read_gbq(sql_query, project_id=self.project_id, credentials=self.creds)
            latest_week = df['max_semana'].iloc[0]
            return int(latest_week) if pd.notna(latest_week) else 0
        except Exception:
            return 0

    @st.cache_data(ttl=3600)
    def get_filter_options(_self):
        """Busca todos os valores únicos para os filtros da página de consulta."""
        query = f"""
        SELECT
          (SELECT ARRAY_AGG(DISTINCT SEMANA IGNORE NULLS ORDER BY SEMANA) FROM {_self.table_id}) AS semanas,
          (SELECT ARRAY_AGG(DISTINCT MUNICIPIO IGNORE NULLS ORDER BY MUNICIPIO) FROM {_self.table_id}) AS municipios,
          (SELECT ARRAY_AGG(DISTINCT ESCOLA IGNORE NULLS ORDER BY ESCOLA) FROM {_self.table_id}) AS escolas,
          (SELECT ARRAY_AGG(DISTINCT DISCIPLINA IGNORE NULLS ORDER BY DISCIPLINA) FROM {_self.table_id}) AS disciplinas,
          (SELECT ARRAY_AGG(DISTINCT TURMA IGNORE NULLS ORDER BY TURMA) FROM {_self.table_id}) AS turmas,
          (SELECT MIN(DATA_DO_RELATORIO) FROM {_self.table_id}) as min_data,
          (SELECT MAX(DATA_DO_RELATORIO) FROM {_self.table_id}) as max_data
        """
        try:
            df = pandas_gbq.read_gbq(query, project_id=_self.project_id, credentials=_self.creds)
            if not df.empty:
                return df.to_dict('records')[0]
        except Exception as e:
            st.error(f"Erro ao buscar opções de filtro: {e}")
        return {"semanas": [], "municipios": [], "escolas": [], "disciplinas": [], "turmas": [], "min_data": None,
                "max_data": None}

    def _format_sql_in_clause(self, values):
        """Função auxiliar para formatar listas para cláusulas IN do SQL."""
        if not values: return "('')"
        formatted_values = [f"'{str(v).replace("'", "''")}'" for v in values]
        return f"({', '.join(formatted_values)})"

    def query_data(self, filters):
        """Busca dados do BigQuery com base em um dicionário de filtros dinâmicos."""
        sql_query = f"SELECT * FROM {self.table_id}"
        where_clauses = []

        if filters.get("semanas"): where_clauses.append(f"SEMANA IN ({','.join(map(str, filters['semanas']))})")
        if filters.get("municipios"): where_clauses.append(
            f"MUNICIPIO IN {self._format_sql_in_clause(filters['municipios'])}")
        if filters.get("escolas"): where_clauses.append(f"ESCOLA IN {self._format_sql_in_clause(filters['escolas'])}")
        if filters.get("turmas"): where_clauses.append(f"TURMA IN {self._format_sql_in_clause(filters['turmas'])}")
        if filters.get("disciplinas"): where_clauses.append(
            f"DISCIPLINA IN {self._format_sql_in_clause(filters['disciplinas'])}")
        if filters.get("data_inicio") and filters.get("data_fim"):
            where_clauses.append(f"DATA_DO_RELATORIO BETWEEN '{filters['data_inicio']}' AND '{filters['data_fim']}'")
        if filters.get("null_filter"):
            null_map = {"aula": "REGISTRO_DE_AULA IS NULL", "conteudo": "REGISTRO_DE_CONTEUDO IS NULL",
                        "ambos": "(REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL)"}
            if filters["null_filter"] in null_map:
                where_clauses.append(null_map[filters["null_filter"]])

        if where_clauses: sql_query += " WHERE " + " AND ".join(where_clauses)
        sql_query += " ORDER BY DATA_DO_RELATORIO DESC, HORARIO"

        try:
            return pandas_gbq.read_gbq(sql_query, project_id=self.project_id, credentials=self.creds)
        except Exception as e:
            st.error(f"Erro ao executar a consulta no BigQuery: {e}")
            return pd.DataFrame()

    def get_all_data(self, week_filter=None):
        """Busca todos os dados da tabela histórica, com um filtro opcional por semana."""
        sql_query = f"SELECT * FROM {self.table_id}"
        if week_filter:
            weeks_str = ','.join(map(str, week_filter))
            sql_query += f" WHERE SEMANA IN ({weeks_str})"
        try:
            return pandas_gbq.read_gbq(sql_query, project_id=self.project_id, credentials=self.creds)
        except Exception as e:
            st.error(f"Erro ao buscar dados do BigQuery: {e}")
            return pd.DataFrame()

    def list_analysis_tables(self):
        """Lista todas as tabelas de análise (que começam com 'auditoria_') em um dataset."""
        try:
            client = bigquery.Client(credentials=self.creds, project=self.project_id)
            tables = client.list_tables(self.dataset_id)
            return [table.table_id for table in tables if table.table_id.startswith('auditoria_')]
        except Exception as e:
            st.error(f"Erro ao listar as tabelas de análise: {e}")
            return []

    @st.cache_data(ttl=600)
    def get_analysis_audit_stats(_self, table_name):
        """Busca estatísticas de uma tabela de auditoria específica."""
        if not table_name.startswith('auditoria_'): return None
        table_ref = f"`{_self.project_id}.{_self.dataset_id}.{table_name}`"
        try:
            # Tenta ler como um relatório detalhado de pendências
            counts_query = f"SELECT COUNT(*) AS total_registros, COUNTIF(REGISTRO_DE_AULA IS NULL) AS total_sem_aula, COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) AS total_sem_conteudo FROM {table_ref}"
            df_counts = pandas_gbq.read_gbq(counts_query, project_id=_self.project_id, credentials=_self.creds)

            details_query = f"""
                SELECT
                    DATA_DO_RELATORIO,
                    HORARIO,
                    ESCOLA,
                    DISCIPLINA,
                    TURMA,
                    CASE WHEN REGISTRO_DE_AULA IS NULL THEN 'Sim' ELSE 'Não' END as PENDENCIA_AULA,
                    CASE WHEN REGISTRO_DE_CONTEUDO IS NULL THEN 'Sim' ELSE 'Não' END as PENDENCIA_CONTEUDO
                FROM {table_ref}
                WHERE REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL
                ORDER BY DATA_DO_RELATORIO, HORARIO, ESCOLA
            """
            df_details = pandas_gbq.read_gbq(details_query, project_id=_self.project_id, credentials=_self.creds)
            return {"type": "detailed", "counts": df_counts.to_dict('records')[0], "details": df_details}
        except Exception:
            try:
                # Se falhar, tenta ler como um relatório "limpo" (sem pendências)
                clean_report_query = f"SELECT * FROM {table_ref}"
                df_clean = pandas_gbq.read_gbq(clean_report_query, project_id=_self.project_id, credentials=_self.creds)
                return {"type": "clean", "data": df_clean}
            except Exception as e:
                st.error(f"Não foi possível ler a tabela de auditoria '{table_name}': {e}")
                return None

    def get_available_weeks(self):
        """Busca todas as semanas únicas e ordenadas disponíveis na tabela histórica."""
        sql_query = f"SELECT DISTINCT SEMANA FROM {self.table_id} ORDER BY SEMANA"
        try:
            df = pandas_gbq.read_gbq(sql_query, project_id=self.project_id, credentials=self.creds)
            return [week for week in df['SEMANA'].tolist() if week is not None]
        except Exception as e:
            st.error(f"Erro ao buscar semanas disponíveis: {e}")
            return []

    def get_pending_historical_data(self, weeks):
        """Busca dados históricos que estão com pendências."""
        weeks_str = ','.join(map(str, weeks))
        query = f"SELECT * FROM {self.table_id} WHERE SEMANA IN ({weeks_str}) AND (REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL)"
        try:
            return pandas_gbq.read_gbq(query, project_id=self.project_id, credentials=self.creds)
        except Exception as e:
            st.error(f"Erro ao buscar pendências históricas: {e}")
            return pd.DataFrame()