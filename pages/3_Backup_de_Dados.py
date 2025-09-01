# ==============================================================================
# ARQUIVO COMPLETO: pages/3_Backup_de_Dados.py (Versão Multilocatário)
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from bigquery_loader import autenticar_usuario, get_available_weeks, get_all_data_from_bq

st.set_page_config(layout="wide")
st.title("📥 Backup dos Dados do BigQuery")

# --- Lógica de Autenticação e Mapeamento ---
autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com sua conta Google para continuar.")
    st.stop()

user_email = st.session_state.user_info['email']
creds = st.session_state.credentials

try:
    dataset_id = st.secrets.office_mapping[user_email]
except KeyError:
    st.error(f"O e-mail **{user_email}** não está autorizado a usar esta funcionalidade.")
    st.stop()

st.sidebar.success(f"Logado como: **{user_email}**")
st.sidebar.info(f"Dataset: **{dataset_id}**")
if st.sidebar.button("Logout", key="logout_backup"):
    del st.session_state.credentials
    if 'user_info' in st.session_state: del st.session_state.user_info
    st.rerun()

# --- Lógica da Página de Backup ---
st.info("Use esta página para baixar uma cópia de segurança dos seus dados.")

with st.spinner("Buscando semanas disponíveis..."):
    available_weeks = get_available_weeks(creds, dataset_id)

if not available_weeks:
    st.warning("Nenhuma semana encontrada para o seu usuário.")
else:
    st.subheader("Passo 1: Selecione as semanas para o backup")
    selected_weeks = st.multiselect("Deixe em branco para baixar o backup completo.", options=available_weeks)

    st.subheader("Passo 2: Prepare e baixe os dados")
    if st.button("Preparar Dados para Download"):
        weeks_to_fetch = selected_weeks if selected_weeks else None
        with st.spinner("Buscando dados no BigQuery... (Isso pode levar um tempo)"):
            st.session_state.df_backup = get_all_data_from_bq(creds, dataset_id, weeks=weeks_to_fetch)
        if st.session_state.df_backup.empty:
            st.warning("Nenhum dado encontrado para a seleção.")

if 'df_backup' in st.session_state and not st.session_state.df_backup.empty:
    st.markdown("---")
    st.subheader("Dados Prontos. Escolha o formato para baixar:")

    df_download = st.session_state.df_backup.copy()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Formato CSV (Texto, bom para Excel)")
        df_csv = df_download.copy()
        df_csv['REGISTRO_DE_AULA'] = df_csv['REGISTRO_DE_AULA'].astype(str).str.replace('NaT', 'Sem registro',
                                                                                        regex=False)
        df_csv['REGISTRO_DE_CONTEUDO'] = df_csv['REGISTRO_DE_CONTEUDO'].astype(str).str.replace('NaT', 'Sem registro',
                                                                                                regex=False)
        csv_data = df_csv.to_csv(index=False).encode('utf-8')
        st.download_button(label="Baixar .csv", data=csv_data, file_name=f"backup_relatorios_lrco_{timestamp}.csv",
                           mime='text/csv', use_container_width=True)

    with col2:
        st.markdown("##### Formato Parquet (Comprimido, mais rápido)")
        parquet_data = df_download.to_parquet(engine='pyarrow')
        st.download_button(label="Baixar .parquet", data=parquet_data,
                           file_name=f"backup_relatorios_lrco_{timestamp}.parquet", mime='application/octet-stream',
                           use_container_width=True)