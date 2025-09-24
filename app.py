# app.py
import streamlit as st
from services import auth_service
from services.bigquery_service import BigQueryService
from services.analysis_service import criar_analise_comparativa
from utils.dataframe_utils import preparar_dataframe_para_bigquery

st.set_page_config(layout="wide")
st.title("Meu App de Análise de Dados")

# 1. Autenticação é a primeira coisa
auth_service.autenticar_usuario()

# Se chegou aqui, o usuário está autenticado.
# As credenciais estão em st.session_state.credentials

# 2. Inicializar os serviços com as credenciais
# Você pode querer colocar isso no cache da sessão para não recriar a cada rerun
if 'bq_service' not in st.session_state:
    DATASET_ID = "seu_dataset_aqui" # Pode vir de um selectbox ou config
    st.session_state.bq_service = BigQueryService(
        credentials=st.session_state.credentials,
        dataset_id=DATASET_ID
    )

bq_service = st.session_state.bq_service

# 3. Construir a UI e chamar os serviços
st.header("Dashboard")
stats = bq_service.get_dashboard_stats()
# ... exibir as estatísticas ...

st.header("Análise Comparativa")
# ... widgets para upload de arquivo e seleção de semanas ...
if st.button("Executar Análise"):
    # Supondo que df_parquet e weeks foram preenchidos pela UI
    sucesso, mensagem = criar_analise_comparativa(
        bq_service,
        "Nome da Analise",
        weeks,
        df_parquet
    )
    if sucesso:
        st.success(mensagem)
    else:
        st.error(mensagem)