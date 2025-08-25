import pandas as pd
import pandas_gbq
from google.oauth2 import credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os

# --- Configurações ---
# Substitua pelo seu ID do projeto, dataset e tabela do BigQuery
PROJECT_ID = "monitoramento-lancamentos-rco"
TABLE_ID = "Lancamentos_lrco.relatorios_lrco"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/drive",
]
# Este arquivo irá armazenar os tokens de acesso do usuário para reutilização
CREDS_TOKEN_PATH = "token.json"
# Este arquivo é o JSON de credenciais que você baixa do Google Cloud Console
# (Vá para APIs e Serviços > Credenciais > Criar Credenciais > ID do cliente OAuth)
CLIENT_SECRETS_PATH = "client_secrets.json"


def autenticar_e_obter_credenciais():
    """
    Realiza o fluxo de autenticação OAuth 2.0 do usuário.
    Reutiliza tokens salvos se disponíveis, ou solicita novo login.
    """
    creds = None
    if os.path.exists(CREDS_TOKEN_PATH):
        creds = credentials.Credentials.from_authorized_user_file(CREDS_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(CREDS_TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    return creds



# VERSÃO FINAL COM VALIDAÇÃO DA COLUNA 'SEMANA'
def preparar_dataframe_para_bigquery(df: pd.DataFrame) -> pd.DataFrame:
    """
    Versão final e robusta: Valida a coluna SEMANA, sanitiza todas as
    colunas de texto, converte tipos e garante compatibilidade total.
    """
    df_copy = df.copy()

    # --- NOVO BLOCO DE VALIDAÇÃO ---
    # 1. Garante que a coluna SEMANA seja um número inteiro limpo.
    # Converte para numérico, transformando erros (texto, etc.) em NaN (Nulo).
    df_copy['SEMANA'] = pd.to_numeric(df_copy['SEMANA'], errors='coerce')
    # Substitui qualquer valor Nulo (células vazias/erros) por 0.
    df_copy['SEMANA'] = df_copy['SEMANA'].fillna(0)
    # Garante que o tipo final da coluna seja inteiro.
    df_copy['SEMANA'] = df_copy['SEMANA'].astype(int)
    # --- FIM DO NOVO BLOCO ---

    # 2. Limpeza profunda de todas as colunas de texto (strings)
    for col in df_copy.select_dtypes(include=['object']).columns:
        if col != 'SEMANA': # A coluna SEMANA já foi tratada
            df_copy[col] = df_copy[col].str.strip()
            df_copy[col] = df_copy[col].str.replace('\r', ' ', regex=False).str.replace('\n', ' ', regex=False)

    # 3. Substitui 'Sem registro' por None
    df_copy.replace("Sem registro", None, inplace=True)

    # 4. Converte os demais tipos de dados
    df_copy["DATA_DO_RELATORIO"] = pd.to_datetime(df_copy["DATA_DO_RELATORIO"], format='%d/%m/%Y', errors='coerce').dt.date
    df_copy["REGISTRO_DE_AULA"] = pd.to_datetime(df_copy["REGISTRO_DE_AULA"], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    df_copy["REGISTRO_DE_CONTEUDO"] = pd.to_datetime(df_copy["REGISTRO_DE_CONTEUDO"], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    df_copy['HORARIO'] = pd.to_datetime(df_copy['HORARIO'], format='%H:%M:%S', errors='coerce').dt.time

    return df_copy


def carregar_dados_no_bigquery(df: pd.DataFrame, creds):
    """
    Carrega um DataFrame do Pandas em uma tabela do BigQuery.
    """
    try:
        df_limpo = preparar_dataframe_para_bigquery(df)

        pandas_gbq.to_gbq(
            df_limpo,
            destination_table=TABLE_ID,
            project_id=PROJECT_ID,
            credentials=creds,
            if_exists='append',  # 'append' para adicionar, 'replace' para substituir
            progress_bar=True
        )
        print(f"✅ Sucesso! {len(df_limpo)} linhas carregadas em '{TABLE_ID}'.")
        return True
    except Exception as e:
        print(f"❌ Erro ao carregar dados no BigQuery: {e}")
        return False