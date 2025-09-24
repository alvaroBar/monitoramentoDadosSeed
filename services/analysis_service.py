# services/analysis_service.py
import pandas as pd
import re
from datetime import date
from utils.dataframe_utils import preparar_dataframe_para_bigquery
from services.bigquery_service import BigQueryService


def criar_analise_comparativa(bq_service: BigQueryService, analysis_name: str, weeks_to_compare: list,
                              df_from_parquet: pd.DataFrame):
    clean_name = re.sub(r'\W+', '_', analysis_name).lower()
    if not clean_name:
        return False, "O nome da análise é inválido."

    destination_table_name = f"auditoria_{clean_name}"

    try:
        # Passo A: Usar o serviço de BQ para buscar dados
        df_historico_pendente = bq_service.get_pending_historical_data(weeks_to_compare)

        if df_historico_pendente.empty:
            # ... (lógica para criar relatório "limpo")
            return True, "Nenhuma pendência histórica encontrada."

        # Passo B: Usar o utilitário de DataFrame para preparar os dados
        df_novo_preparado = preparar_dataframe_para_bigquery(df_from_parquet)
        df_historico_preparado = preparar_dataframe_para_bigquery(df_historico_pendente)

        # Passo C & D: Lógica de negócio (merge, filtro, etc.)
        key_cols = ['DATA_DO_RELATORIO', 'MUNICIPIO', 'ESCOLA', 'TURMA', 'HORARIO', 'DISCIPLINA']
        df_merged = pd.merge(df_historico_preparado, df_novo_preparado.rename(
            columns={'REGISTRO_DE_AULA': 'NOVO_REGISTRO_AULA', 'REGISTRO_DE_CONTEUDO': 'NOVO_REGISTRO_CONTEUDO'}),
                             on=key_cols, how='left')

        mascara_ainda_pendente = pd.isna(df_merged['NOVO_REGISTRO_AULA']) | pd.isna(df_merged['NOVO_REGISTRO_CONTEUDO'])
        df_para_salvar = df_merged[mascara_ainda_pendente][df_historico_preparado.columns]

        if not df_para_salvar.empty:
            # Usar o serviço de BQ para carregar o resultado
            sucesso_carga = bq_service.carregar_dados(df_para_salvar, table_name=destination_table_name, mode='replace')
            if sucesso_carga:
                return True, f"Auditoria concluída! Nova tabela `{destination_table_name}` criada com {len(df_para_salvar)} pendências."
            else:
                return False, "Falha ao carregar a tabela de resultados."
        else:
            # ... (lógica para criar relatório "limpo")
            return True, "Todas as pendências foram resolvidas."

    except Exception as e:
        return False, f"Erro ao criar a análise comparativa: {e}"