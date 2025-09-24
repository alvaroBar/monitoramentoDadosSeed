import streamlit as st
import pandas as pd
from services import auth_service
from services.bigquery_service import BigQueryService
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")
st.title("Backup de Dados do BigQuery")

# 1. Autenticação é a primeira coisa
auth_service.autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica da Aplicação (Visível apenas após o login) ---
user_info = st.session_state.user_info
user_email = user_info.get("email")
user_name = user_info.get("name", "Usuário")

# Mapeia o e-mail para o dataset_id em cada execução
try:
    office_mapping = st.secrets.office_mapping
    if user_email in office_mapping:
        st.session_state.dataset_id = office_mapping[user_email]
    else:
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador.")
        st.stop()
except (AttributeError, KeyError):
    st.error("ERRO DE CONFIGURAÇÃO: O mapeamento de escritórios [office_mapping] não foi encontrado nos Segredos do Streamlit.")
    st.stop()

# 2. Inicializar o serviço do BigQuery e guardá-lo na sessão
if 'bq_service' not in st.session_state:
    st.session_state.bq_service = BigQueryService(
        credentials=st.session_state.credentials,
        dataset_id=st.session_state.dataset_id
    )
bq_service = st.session_state.bq_service

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout", key="logout_Backup_de_Dados"):
        st.session_state.clear()
        st.rerun()

# --- ALTERAÇÃO APLICADA AQUI: Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_processar")

# --- Lógica de Estado para o fluxo da página ---
if 'backup_data' not in st.session_state:
    st.session_state.backup_data = None

st.header("Passo 1: Selecione as Semanas para o Backup")

creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

try:
    with st.spinner("Buscando semanas disponíveis no BigQuery..."):
        available_weeks = bq_service.get_available_weeks()

    if available_weeks:
        selected_weeks = st.multiselect(
            "Selecione as semanas que deseja incluir no backup (deixe em branco para todas):",
            options=available_weeks,
            default=[]
        )

        if st.button("Buscar Dados para Backup", use_container_width=True):
            week_filter = selected_weeks if selected_weeks else None
            with st.spinner("Buscando dados do BigQuery... Isso pode levar um tempo."):
                df_backup = bq_service.get_all_data(week_filter=week_filter)
                if not df_backup.empty:
                    st.session_state.backup_data = df_backup
                    st.rerun()
                else:
                    st.warning("Nenhum dado encontrado para as semanas selecionadas.")

    else:
        st.info("Nenhuma semana encontrada no banco de dados para este usuário.")

except Exception as e:
    st.error(f"Não foi possível buscar as semanas do BigQuery. Erro: {e}")


# --- Passo 2: Download dos Dados ---
if st.session_state.backup_data is not None:
    df_backup = st.session_state.backup_data
    st.success(f"✅ Dados prontos! {len(df_backup)} registros foram encontrados.")
    st.dataframe(df_backup.head())

    st.header("Passo 2: Escolha o Formato do Backup")

    col1, col2 = st.columns(2)

    with col1:
        # Lógica para CSV
        df_csv = df_backup.copy()

        cols_to_fill = ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']
        for col in cols_to_fill:
            if col in df_csv.columns:
                df_csv[col] = df_csv[col].astype(str).replace('NaT', 'Sem registro')

        csv_data = df_csv.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar Backup em .csv",
            data=csv_data,
            file_name="backup_relatorios.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col2:
        # Lógica para Parquet
        parquet_data = df_backup.to_parquet(index=False)
        st.download_button(
            label="⚡️ Baixar Backup em .parquet (Mais Rápido/Leve)",
            data=parquet_data,
            file_name="backup_relatorios.parquet",
            mime="application/octet-stream",
            use_container_width=True
        )

    if st.button("Limpar e Iniciar Nova Busca", use_container_width=True):
        st.session_state.backup_data = None
        st.rerun()