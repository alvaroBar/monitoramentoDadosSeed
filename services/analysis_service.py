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
        # Passo A: Usar o serviço de BQ para buscar dados pendentes históricos
        df_historico_pendente = bq_service.get_pending_historical_data(weeks_to_compare)

        if df_historico_pendente.empty:
            # CHAMA A FUNÇÃO AUXILIAR QUANDO NÃO HÁ PENDÊNCIAS HISTÓRICAS
            return _criar_e_carregar_relatorio_limpo(
                bq_service,
                destination_table_name,
                analysis_name,
                "Nenhuma pendência histórica encontrada para as semanas selecionadas."
            )

        # Passo B: Usar o utilitário de DataFrame para preparar os dados
        df_novo_preparado = preparar_dataframe_para_bigquery(df_from_parquet)
        df_historico_preparado = preparar_dataframe_para_bigquery(df_historico_pendente)

        # Passo C & D: Lógica de negócio (merge, filtro, etc.)
        key_cols = ['DATA_DO_RELATORIO', 'MUNICIPIO', 'ESCOLA', 'TURMA', 'HORARIO', 'DISCIPLINA']
        df_merged = pd.merge(df_historico_preparado, df_novo_preparado.rename(
            columns={'REGISTRO_DE_AULA': 'NOVO_REGISTRO_AULA', 'REGISTRO_DE_CONTEUDO': 'NOVO_REGISTRO_CONTEUDO'}),
                             on=key_cols, how='left')

        mascara_ainda_pendente = pd.isna(df_merged['NOVO_REGISTRO_AULA']) & pd.isna(df_merged['NOVO_REGISTRO_CONTEUDO'])
        df_para_salvar = df_merged[mascara_ainda_pendente][df_historico_preparado.columns]

        if not df_para_salvar.empty:
            # Usar o serviço de BQ para carregar o resultado com as pendências restantes
            sucesso_carga = bq_service.carregar_dados(df_para_salvar, table_name=destination_table_name, mode='replace')
            if sucesso_carga:
                return True, f"Auditoria '{analysis_name}' concluída! Nova tabela `{destination_table_name}` criada com {len(df_para_salvar)} pendências restantes."
            else:
                return False, "Falha ao carregar a tabela de resultados com as pendências."
        else:
            # CHAMA A FUNÇÃO AUXILIAR QUANDO TODAS AS PENDÊNCIAS FORAM RESOLVIDAS
            return _criar_e_carregar_relatorio_limpo(
                bq_service,
                destination_table_name,
                analysis_name,
                "Todas as pendências anteriores foram resolvidas nos novos arquivos."
            )

    except Exception as e:
        return False, f"Erro ao criar a análise comparativa: {e}"


def executar_validacao_de_lancamentos(bq_service: BigQueryService, weeks_to_compare: list, df_from_parquet: pd.DataFrame):
    """
    Compara um arquivo Parquet com dados do BigQuery para validar lançamentos.
    Retorna métricas e uma lista de pendências restantes.
    """
    try:
        # 1. Buscar todos os dados históricos das semanas selecionadas
        df_historico_total = bq_service.get_all_data(week_filter=weeks_to_compare)
        if df_historico_total.empty:
            return False, "Não foram encontrados dados históricos para as semanas selecionadas no BigQuery."

        # 2. Preparar ambos os DataFrames para garantir consistência
        df_novo = preparar_dataframe_para_bigquery(df_from_parquet)
        df_historico = preparar_dataframe_para_bigquery(df_historico_total)

        # 3. Identificar as colunas chave para o merge
        key_cols = ['DATA_DO_RELATORIO', 'MUNICIPIO', 'ESCOLA', 'TURMA', 'HORARIO', 'DISCIPLINA']

        # 4. Fazer o merge para encontrar correspondências (matches)
        df_merged = pd.merge(
            df_historico,
            df_novo,
            on=key_cols,
            how='inner', # 'inner' merge nos dá apenas os registros que existem em ambos
            suffixes=('_db', '_novo')
        )
        total_matches = len(df_merged)
        if total_matches == 0:
            return False, "Nenhum registro correspondente (match) encontrado entre o arquivo e os dados do BigQuery."

        # 5. Calcular quantos valores nulos foram preenchidos
        aulas_preenchidas = df_merged.query("REGISTRO_DE_AULA_db.isnull() and REGISTRO_DE_AULA_novo.notnull()").shape[0]
        conteudos_preenchidos = df_merged.query("REGISTRO_DE_CONTEUDO_db.isnull() and REGISTRO_DE_CONTEUDO_novo.notnull()").shape[0]
        total_preenchido = aulas_preenchidas + conteudos_preenchidos

        # 6. Encontrar pendências restantes nas escolas do arquivo novo
        escolas_no_arquivo_novo = df_novo['ESCOLA'].unique()
        df_pendencias_restantes = df_historico[
            (df_historico['ESCOLA'].isin(escolas_no_arquivo_novo)) &
            (df_historico['REGISTRO_DE_AULA'].isnull() | df_historico['REGISTRO_DE_CONTEUDO'].isnull())
        ]

        # 7. Montar o dicionário de resultados
        resultados = {
            "total_matches": total_matches,
            "nulos_preenchidos": total_preenchido,
            "pendencias_restantes": df_pendencias_restantes
        }

        return True, resultados

    except Exception as e:
        return False, f"Ocorreu um erro durante a validação: {e}"