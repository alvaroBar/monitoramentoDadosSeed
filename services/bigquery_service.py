# services/bigquery_service.py
import streamlit as st
import pandas as pd
import pandas_gbq
from google.cloud import bigquery
from utils import config


# É uma boa prática encapsular a lógica de acesso a dados em uma classe.
class BigQueryService:
    def __init__(self, credentials, dataset_id):
        if not credentials:
            raise ValueError("Credenciais são necessárias para inicializar o BigQueryService.")
        self.creds = credentials
        self.dataset_id = dataset_id
        self.project_id = config.PROJECT_ID
        self.table_id = f"{self.project_id}.{self.dataset_id}.relatorios_lrco"

    # --- Métodos de Escrita e Deleção ---
    def carregar_dados(self, df: pd.DataFrame, table_name='relatorios_lrco', mode='append'):
        destination_table = f"{self.dataset_id}.{table_name}"
        try:
            # Note que a preparação do DF não está mais aqui!
            pandas_gbq.to_gbq(df, destination_table, self.project_id, credentials=self.creds, if_exists=mode,
                              progress_bar=False)
            return True
        except Exception as e:
            st.error(f"Erro ao carregar dados na tabela {destination_table}: {e}")
            return False

    def delete_week_data(self, week_to_delete):
        try:
            client = bigquery.Client(credentials=self.creds, project=self.project_id)
            delete_query = f"DELETE FROM `{self.table_id}` WHERE SEMANA = {week_to_delete}"
            query_job = client.query(delete_query)
            query_job.result()  # Espera a conclusão
            return True, f"Registros da semana {week_to_delete} apagados."
        except Exception as e:
            return False, f"Erro ao apagar os dados da semana: {e}"

    # --- Métodos de Leitura (Queries) ---
    def get_dashboard_stats(self):
        # ... (código da função get_dashboard_stats, mas usando self.table_id, etc.)
        pass

    def get_latest_week(self):
        # ... (código da função get_latest_week)
        pass

    @st.cache_data(ttl=3600)
    def get_filter_options(_self):  # Use _self para agradar o cache do Streamlit
        # ... (código da função get_filter_options)
        pass

    def query_data(self, filters):
        # ... (código da função query_data_from_bq)
        pass

    def get_all_data(self, week_filter=None):
        # ... (código da função get_all_data_from_bq)
        pass

    def list_analysis_tables(self):
        # ... (código da função list_analysis_tables)
        pass

    def get_analysis_audit_stats(self, table_name):
        # ... (código da função get_analysis_audit_stats)
        pass

    def get_pending_historical_data(self, weeks):
        """Busca dados históricos que estão com pendências."""
        weeks_str = ','.join(map(str, weeks))
        query = f"SELECT * FROM `{self.table_id}` WHERE SEMANA IN ({weeks_str}) AND (REGISTRO_DE_AULA IS NULL OR REGISTRO_DE_CONTEUDO IS NULL)"
        try:
            return pandas_gbq.read_gbq(query, project_id=self.project_id, credentials=self.creds)
        except Exception as e:
            st.error(f"Erro ao buscar pendências históricas: {e}")
            return pd.DataFrame()