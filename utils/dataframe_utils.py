# utils/dataframe_utils.py
import pandas as pd


def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """Limpa e formata um DataFrame para ser carregado no BigQuery."""
    df_copy = df.copy()

    if 'SEMANA' in df_copy.columns:
        df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce').fillna(0).astype(int)

    # Colunas que não devem passar pela limpeza geral de strings
    cols_to_exclude = ['SEMANA', 'DATA_DO_RELATORIO', 'REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO', 'HORARIO']

    # Limpa colunas de texto (object), removendo espaços e quebras de linha
    for col in df_copy.select_dtypes(include=['object']).columns:
        if col not in cols_to_exclude:
            df_copy[col] = df_copy[col].astype(str).str.strip().str.replace('\r', ' ', regex=False).str.replace('\n', ' ', regex=False)

    # --- SUGESTÃO APLICADA AQUI ---
    # Converte as colunas de registro para datetime de forma mais direta
    for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
        if col in df_copy.columns:
            # Substitui "Sem registro" por NaT (Not a Time) do pandas e converte
            df_copy[col] = pd.to_datetime(
                df_copy[col].replace("Sem registro", pd.NaT),
                format='%d/%m/%Y %H:%M:%S',
                errors='coerce'
            )

    # Converte as colunas de data e hora para os tipos corretos
    if "DATA_DO_RELATORIO" in df_copy.columns:
        df_copy["DATA_DO_RELATORIO"] = pd.to_datetime(
            df_copy["DATA_DO_RELATORIO"],
            format='%d/%m/%Y',
            errors='coerce'
        ).dt.date

    if 'HORARIO' in df_copy.columns:
        df_copy['HORARIO'] = pd.to_datetime(
            df_copy['HORARIO'],
            format='%H:%M:%S',
            errors='coerce'
        ).dt.time

    return df_copy