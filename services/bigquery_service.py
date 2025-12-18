import streamlit as st
import pandas as pd
import pandas_gbq
from google.cloud import bigquery
from utils import config
import datetime  # Adicionado para a função de consulta


class BigQueryService:
    def __init__(self, credentials, dataset_id):
        if not credentials:
            raise ValueError("Credenciais necessárias.")
        self.creds = credentials
        self.dataset_id = dataset_id
        self.project_id = config.PROJECT_ID

        # LÓGICA DE SELEÇÃO DE TABELA
        # Tenta pegar da sessão. Se for um script rodando fora do Streamlit, usa o ano do sistema.
        if 'ano_letivo' in st.session_state:
            self.ano_vigente = st.session_state['ano_letivo']
        else:
            self.ano_vigente = datetime.datetime.now().year

        # Define o ID da tabela com o SUFIXO do ano
        # Alterar o nome da tabela para a utilizada pelo nome em produção
        self.table_name_base = f"relatorios_lrco_{self.ano_vigente}"
        self.table_id = f"`{self.project_id}.{self.dataset_id}.{self.table_name_base}`"

    def carregar_dados(self, df: pd.DataFrame, table_name=None, mode='append'):
        """
        Carrega dados no BigQuery.
        Se table_name não for passado, usa a tabela do ano selecionado (ex: relatorios_lrco_2025).
        """
        # Se nenhum nome específico for passado, usa o padrão do ano atual
        if table_name is None or table_name == 'relatorios_lrco':
            destination_table = f"{self.dataset_id}.{self.table_name_base}"
        else:
            # Caso seja uma tabela de auditoria ou específica
            destination_table = f"{self.dataset_id}.{table_name}"

        try:
            pandas_gbq.to_gbq(
                df,
                destination_table,
                self.project_id,
                credentials=self.creds,
                if_exists=mode,
                progress_bar=False
            )
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
        """Busca estatísticas agregadas e acionáveis do BigQuery para o dashboard."""
        try:
            # Query Nova
            stats_query = f"""
                SELECT
                    COUNT(*) AS total_registros,
                    MAX(DATA_DO_RELATORIO) AS ultima_data,
                    COUNT(DISTINCT SEMANA) as total_semanas,
                    MAX(SEMANA) as ultima_semana_lancada,
                    COUNTIF(REGISTRO_DE_AULA IS NULL) as sem_registro_aula,
                    COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) as sem_registro_conteudo
                FROM {self.table_id}
            """
            df_stats = pandas_gbq.read_gbq(stats_query, project_id=self.project_id, credentials=self.creds)
            stats_data = df_stats.to_dict('records')[0] if not df_stats.empty else {}

            disciplinas_query = f"SELECT DISCIPLINA, COUNT(*) AS contagem FROM {self.table_id} WHERE DISCIPLINA IS NOT NULL GROUP BY DISCIPLINA ORDER BY contagem DESC LIMIT 5"
            df_top_disciplinas = pandas_gbq.read_gbq(disciplinas_query, project_id=self.project_id, credentials=self.creds)

            semana_query = f"SELECT SEMANA, COUNT(*) AS contagem FROM {self.table_id} WHERE SEMANA IS NOT NULL GROUP BY SEMANA ORDER BY SEMANA"
            df_registros_semana = pandas_gbq.read_gbq(semana_query, project_id=self.project_id, credentials=self.creds)
            if not df_registros_semana.empty:
                df_registros_semana = df_registros_semana.set_index('SEMANA')

            # CORREÇÃO: Alterado o alias 'pendencias' para 'PENDENCIAS' para consistência.
            escolas_pendentes_query = f"""
                SELECT ESCOLA, COUNT(*) as PENDENCIAS FROM {self.table_id}
                WHERE REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL
                GROUP BY ESCOLA ORDER BY PENDENCIAS DESC LIMIT 5
            """
            df_escolas_pendentes = pandas_gbq.read_gbq(escolas_pendentes_query, project_id=self.project_id, credentials=self.creds)

            # CORREÇÃO: Alterado o alias 'pendencias' para 'PENDENCIAS' para corresponder ao app.py
            municipios_pendentes_query = f"""
                SELECT MUNICIPIO, COUNT(*) as PENDENCIAS FROM {self.table_id}
                WHERE REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL
                GROUP BY MUNICIPIO HAVING PENDENCIAS > 0 ORDER BY PENDENCIAS DESC
            """
            df_municipios_pendentes = pandas_gbq.read_gbq(municipios_pendentes_query, project_id=self.project_id, credentials=self.creds)

            # --- NOVA CONSULTA 6: Contagem total de escolas ÚNICAS com pendências ---
            total_escolas_pendentes_query = f"""
                SELECT COUNT(DISTINCT ESCOLA) as total_escolas
                FROM {self.table_id}
                WHERE REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL
            """
            df_total_escolas = pandas_gbq.read_gbq(total_escolas_pendentes_query, project_id=self.project_id, credentials=self.creds)
            total_escolas_com_pendencias = df_total_escolas['total_escolas'].iloc[0] if not df_total_escolas.empty else 0

            # --- Dicionário de retorno ATUALIZADO ---
            return {
                **stats_data,
                "top_disciplinas": df_top_disciplinas,
                "registros_por_semana": df_registros_semana,
                "escolas_com_pendencias": df_escolas_pendentes, # Para a tabela "Top 5"
                "pendencias_por_municipio": df_municipios_pendentes,
                "total_escolas_com_pendencias": total_escolas_com_pendencias # NOVO: Para o KPI
            }

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

    #@st.cache_data(ttl=3600)
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

    def get_all_data(self, week_filter=None, school_filter=None):
        """Busca todos os dados, com filtros opcionais por semana e/ou escola."""
        sql_query = f"SELECT * FROM {self.table_id}"
        where_clauses = []

        if week_filter:
            weeks_str = ','.join(map(str, week_filter))
            where_clauses.append(f"SEMANA IN ({weeks_str})")

        if school_filter:
            escolas_str = self._format_sql_in_clause(school_filter)
            where_clauses.append(f"ESCOLA IN {escolas_str}")

        if where_clauses:
            sql_query += " WHERE " + " AND ".join(where_clauses)

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

    #@st.cache_data(ttl=600)
    def get_analysis_audit_stats(_self, table_name):
        """Busca estatísticas de uma tabela de auditoria específica."""
        if not table_name.startswith('auditoria_'): return None
        table_ref = f"`{_self.project_id}.{_self.dataset_id}.{table_name}`"
        try:
            # Tenta ler como um relatório detalhado de pendências
            counts_query = f"SELECT COUNT(*) AS total_registros, COUNTIF(REGISTRO_DE_AULA IS NULL) AS total_sem_aula, COUNTIF(REGISTRO_DE_CONTEUDO IS NULL) AS total_sem_conteudo FROM {table_ref}"
            df_counts = pandas_gbq.read_gbq(counts_query, project_id=_self.project_id, credentials=_self.creds)

            # Nova Query (retorna as colunas originais)
            details_query = f"""
                SELECT
                    DATA_DO_RELATORIO,
                    HORARIO,
                    ESCOLA,
                    DISCIPLINA,
                    TURMA,
                    REGISTRO_DE_AULA,
                    REGISTRO_DE_CONTEUDO
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

    def get_pending_historical_data(self, weeks, schools=None):
        """Busca dados históricos pendentes, com filtro opcional por escolas."""
        weeks_str = ','.join(map(str, weeks))
        query = f"SELECT * FROM {self.table_id} WHERE SEMANA IN ({weeks_str}) AND (REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL)"

        if schools:
            escolas_str = self._format_sql_in_clause(schools)
            query += f" AND ESCOLA IN {escolas_str}"

        try:
            return pandas_gbq.read_gbq(query, project_id=self.project_id, credentials=self.creds)
        except Exception as e:
            st.error(f"Erro ao buscar pendências históricas: {e}")
            return pd.DataFrame()
