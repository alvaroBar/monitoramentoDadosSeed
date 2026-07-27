# services/analysis_service.py
import pandas as pd
import re
from datetime import date
from utils.dataframe_utils import preparar_dataframe_para_bigquery
from services.bigquery_service import BigQueryService

def _criar_e_carregar_relatorio_limpo(bq_service: BigQueryService, destination_table_name: str, analysis_name: str, mensagem_status: str):
    """
    Função auxiliar interna para criar e carregar uma tabela de auditoria "limpa",
    indicando que não foram encontradas pendências.
    """
    df_sem_pendencias = pd.DataFrame([{'DATA_AUDITORIA': date.today(), 'STATUS': mensagem_status}])
    df_sem_pendencias['DATA_AUDITORIA'] = pd.to_datetime(df_sem_pendencias['DATA_AUDITORIA'])

    sucesso_carga = bq_service.carregar_dados(
        df_sem_pendencias,
        table_name=destination_table_name,
        mode='replace'
    )
    if sucesso_carga:
        return True, f"Auditoria '{analysis_name}' concluída! Um relatório foi gerado em `{destination_table_name}` indicando: '{mensagem_status}'."
    else:
        return False, "Falha ao carregar o relatório de auditoria sem pendências."


def criar_analise_comparativa(bq_service: BigQueryService, analysis_name: str, weeks_to_compare: list,
                              df_from_parquet: pd.DataFrame):
    clean_name = re.sub(r'\W+', '_', analysis_name).lower()
    if not clean_name:
        return False, "O nome da análise é inválido."
    destination_table_name = f"auditoria_{clean_name}"
    try:
        df_novo_preparado = preparar_dataframe_para_bigquery(df_from_parquet)

        # 1. Identifica as escolas a serem auditadas a partir do arquivo
        escolas_para_auditar = df_novo_preparado['ESCOLA'].unique().tolist()
        if not escolas_para_auditar:
            return False, "Nenhuma escola encontrada no arquivo Parquet."

        # 2. Busca dados históricos pendentes APENAS para as escolas relevantes
        df_historico_pendente = bq_service.get_pending_historical_data(weeks_to_compare, schools=escolas_para_auditar)

        if df_historico_pendente.empty:
            return _criar_e_carregar_relatorio_limpo(bq_service, destination_table_name, analysis_name,
                                                     "Nenhuma pendência histórica encontrada para as escolas e semanas selecionadas.")

        df_historico_preparado = preparar_dataframe_para_bigquery(df_historico_pendente)
        key_cols = ['DATA_DO_RELATORIO', 'MUNICIPIO', 'ESCOLA', 'TURMA', 'HORARIO', 'DISCIPLINA']

        df_merged = pd.merge(df_historico_preparado, df_novo_preparado.rename(
            columns={'REGISTRO_DE_AULA': 'NOVO_REGISTRO_AULA', 'REGISTRO_DE_CONTEUDO': 'NOVO_REGISTRO_CONTEUDO'}),
                             on=key_cols, how='left')

        mascara_ainda_pendente = pd.isna(df_merged['NOVO_REGISTRO_AULA']) | pd.isna(df_merged['NOVO_REGISTRO_CONTEUDO'])
        df_para_salvar = df_merged[mascara_ainda_pendente][df_historico_preparado.columns]

        if not df_para_salvar.empty:
            sucesso_carga = bq_service.carregar_dados(df_para_salvar, table_name=destination_table_name, mode='replace')
            if sucesso_carga:
                return True, f"Auditoria concluída! Nova tabela `{destination_table_name}` criada com {len(df_para_salvar)} pendências restantes para as escolas auditadas."
            else:
                return False, "Falha ao carregar a tabela de resultados com as pendências."
        else:
            return _criar_e_carregar_relatorio_limpo(bq_service, destination_table_name, analysis_name,
                                                     "Todas as pendências anteriores foram resolvidas para as escolas auditadas.")
    except Exception as e:
        return False, f"Erro ao criar a análise comparativa: {e}"


# services/analysis_service.py -> SUBSTITUA A FUNÇÃO INTEIRA POR ESTA

def executar_validacao_de_lancamentos(bq_service: BigQueryService, weeks_to_compare: list,
                                      df_from_parquet: pd.DataFrame):
    try:
        df_novo = preparar_dataframe_para_bigquery(df_from_parquet)

        # 1. Identifica as escolas a serem validadas a partir do arquivo
        escolas_para_validar = df_novo['ESCOLA'].unique().tolist()
        if not escolas_para_validar:
            return False, "Nenhuma escola encontrada no arquivo Parquet."

        # 2. Buscar dados históricos APENAS para as escolas e semanas relevantes
        df_historico_total = bq_service.get_all_data(week_filter=weeks_to_compare, school_filter=escolas_para_validar)
        if df_historico_total.empty:
            return False, "Não foram encontrados dados históricos para as escolas e semanas selecionadas."

        df_historico = preparar_dataframe_para_bigquery(df_historico_total)
        key_cols = ['DATA_DO_RELATORIO', 'MUNICIPIO', 'ESCOLA', 'TURMA', 'HORARIO', 'DISCIPLINA']

        # 3. Fazer o merge 'inner' para encontrar correspondências (matches)
        df_merged_inner = pd.merge(df_historico, df_novo, on=key_cols, how='inner', suffixes=('_db', '_novo'))
        total_matches = len(df_merged_inner)

        if total_matches == 0:
            return False, "Nenhum registro correspondente (match) encontrado entre o arquivo e os dados do BigQuery para as escolas analisadas."

        # 4. Calcular nulos preenchidos
        aulas_preenchidas = \
        df_merged_inner.query("REGISTRO_DE_AULA_db.isnull() and REGISTRO_DE_AULA_novo.notnull()").shape[0]
        conteudos_preenchidos = \
        df_merged_inner.query("REGISTRO_DE_CONTEUDO_db.isnull() and REGISTRO_DE_CONTEUDO_novo.notnull()").shape[0]
        total_preenchido = aulas_preenchidas + conteudos_preenchidos

        # 5. Encontrar pendências REAIS restantes
        df_historico_pendente = df_historico[
            df_historico['REGISTRO_DE_AULA'].isnull() | df_historico['REGISTRO_DE_CONTEUDO'].isnull()].copy()
        df_merged_pendencias = pd.merge(df_historico_pendente, df_novo.rename(
            columns={'REGISTRO_DE_AULA': 'REGISTRO_DE_AULA_novo', 'REGISTRO_DE_CONTEUDO': 'REGISTRO_DE_CONTEUDO_novo'}),
                                        on=key_cols, how='left')
        mascara_ainda_pendente = df_merged_pendencias['REGISTRO_DE_AULA_novo'].isnull() | df_merged_pendencias[
            'REGISTRO_DE_CONTEUDO_novo'].isnull()
        df_pendencias_restantes = df_merged_pendencias[mascara_ainda_pendente][df_historico_pendente.columns]

        # 6. Montar o dicionário de resultados
        resultados = {
            "escolas_auditadas": escolas_para_validar,  # Informação extra para a UI
            "total_matches": total_matches,
            "nulos_preenchidos": total_preenchido,
            "pendencias_restantes": df_pendencias_restantes
        }
        return True, resultados
    except Exception as e:
        return False, f"Ocorreu um erro durante a validação: {e}"