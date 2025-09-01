# ==============================================================================
# ARQUIVO COMPLETO: pages/3_Backup_de_Dados.py (Versão Multilocatário)
# Página para baixar backups dos dados do BigQuery.
# ==============================================================================

import streamlit as st
import pandas as pd
from bigquery_loader import autenticar_usuario, get_available_weeks, get_all_data_from_bq

st.set_page_config(layout="wide")
st.title("Página de Backup de Dados")
st.info("Use esta página para baixar um backup dos dados armazenados no seu banco de dados do BigQuery.")

# --- Lógica de Autenticação e Mapeamento ---
autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com sua conta Google para continuar.")
    st.stop()

user_email = st.session_state.user_info.get("email", "Email não encontrado")
user_name = st.session_state.user_info.get("name", "Usuário")

OFFICE_MAPPING = st.secrets.get("office_mapping", {})
if user_email not in OFFICE_MAPPING:
    st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador para obter acesso.")
    st.stop()

dataset_id = OFFICE_MAPPING[user_email]

# --- Interface da Barra Lateral ---
st.sidebar.success(f"Olá, {user_name}!")
if st.sidebar.button("Logout"):
    del st.session_state.credentials
    if 'user_info' in st.session_state:
        del st.session_state.user_info
    st.rerun()

# --- Lógica da Página ---
if 'backup_data' not in st.session_state:
    st.session_state.backup_data = None

st.markdown("---")
st.subheader("Passo 1: Selecione as Semanas e Busque os Dados")

try:
    with st.spinner("Buscando semanas disponíveis no seu dataset..."):
        semanas_disponiveis = get_available_weeks(st.session_state.credentials, dataset_id)

    if not semanas_disponiveis:
        st.warning("Nenhum dado encontrado no seu banco de dados para backup.")
    else:
        todas_as_semanas = st.checkbox("Selecionar todas as semanas")

        if todas_as_semanas:
            semanas_selecionadas = st.multiselect(
                "Semanas a serem incluídas no backup:",
                options=semanas_disponiveis,
                default=semanas_disponiveis,
                disabled=True
            )
        else:
            semanas_selecionadas = st.multiselect(
                "Semanas a serem incluídas no backup:",
                options=semanas_disponiveis
            )

        if st.button("Buscar Dados para Backup"):
            if not semanas_selecionadas:
                st.error("Por favor, selecione pelo menos uma semana.")
            else:
                with st.spinner(f"Buscando dados das semanas selecionadas... Isso pode demorar um pouco."):
                    df_backup = get_all_data_from_bq(st.session_state.credentials, dataset_id, semanas_selecionadas)
                    if not df_backup.empty:
                        st.session_state.backup_data = df_backup
                        st.rerun()
                    else:
                        st.warning("Nenhum dado encontrado para as semanas selecionadas.")
except Exception as e:
    st.error(f"Ocorreu um erro ao buscar as semanas: {e}")

if st.session_state.backup_data is not None:
    st.markdown("---")
    st.subheader("Passo 2: Baixe o Arquivo de Backup")
    st.success(f"{len(st.session_state.backup_data)} registros prontos para download.")
    st.dataframe(st.session_state.backup_data.head())

    # --- Lógica de Download ---
    df_para_download = st.session_state.backup_data.copy()

    # Opção 1: CSV (Rápido e leve)
    df_csv = df_para_download.copy()
    for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
        # Converte a coluna para string para poder usar .str
        df_csv[col] = df_csv[col].astype(str).str.replace('NaT', 'Sem registro', regex=False)

    csv_data = df_csv.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Baixar Backup em formato .csv (Recomendado)",
        data=csv_data,
        file_name=f"backup_semanas_{dataset_id}.csv",
        mime="text/csv",
        use_container_width=True
    )

    # Opção 2: Parquet (Eficiente)
    parquet_data = df_para_download.to_parquet(engine='pyarrow')
    st.download_button(
        label="📦 Baixar Backup em formato .parquet (Menor e mais rápido)",
        data=parquet_data,
        file_name=f"backup_semanas_{dataset_id}.parquet",
        mime="application/octet-stream",
        use_container_width=True
    )

    if st.button("Limpar e Começar de Novo"):
        st.session_state.backup_data = None
        st.rerun()