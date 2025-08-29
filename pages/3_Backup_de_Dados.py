# ==============================================================================
# PÁGINA 3: BACKUP DE DADOS
# Esta página permite ao usuário baixar um backup da tabela do BigQuery,
# com a opção de filtrar por semanas.
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

# Importa as funções necessárias do módulo principal
from bigquery_loader import autenticar_com_service_account, get_available_weeks, get_all_data_from_bq

st.set_page_config(layout="wide")
st.title("📥 Backup dos Dados do BigQuery")

st.info(
    "Use esta página para baixar uma cópia de segurança de todos os dados "
    "atualmente armazenados na tabela `relatorios_lrco`."
)

# --- Passo 1: Selecionar Semanas ---
creds = autenticar_com_service_account()
available_weeks = []
if creds:
    with st.spinner("Buscando semanas disponíveis no BigQuery..."):
        available_weeks = get_available_weeks(creds)

if not available_weeks:
    st.warning("Nenhuma semana encontrada no banco de dados ou falha na autenticação.")
else:
    st.subheader("Passo 1: Selecione as semanas para o backup")

    selected_weeks = st.multiselect(
        "Selecione uma ou mais semanas. Deixe em branco para baixar o backup completo.",
        options=available_weeks
    )

    # --- Passo 2: Preparar e Baixar ---
    st.subheader("Passo 2: Prepare e baixe os dados")
    if st.button("Preparar Dados para Download"):
        if creds:
            # Se nenhuma semana for selecionada, busca todas. Caso contrário, busca as selecionadas.
            weeks_to_fetch = selected_weeks if selected_weeks else None

            with st.spinner("Buscando dados no BigQuery... Isso pode levar um momento."):
                df_backup = get_all_data_from_bq(creds, weeks=weeks_to_fetch)

            if not df_backup.empty:
                st.success(f"Sucesso! {len(df_backup)} registros encontrados e prontos para download.")
                st.session_state.df_backup = df_backup  # Armazena o dataframe no estado da sessão
            else:
                st.warning("Nenhum dado encontrado para as semanas selecionadas ou ocorreu um erro na busca.")
        else:
            st.error("Falha na autenticação.")

# --- Seção de Download (só aparece após os dados serem preparados) ---
if 'df_backup' in st.session_state and not st.session_state.df_backup.empty:
    st.markdown("---")
    st.subheader("Dados Prontos. Escolha o formato para baixar:")
    st.markdown(
        "A etapa demorada (buscar os dados) já foi concluída. Agora, a geração e o download do arquivo final serão rápidos.")

    df_download = st.session_state.df_backup.copy()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    col1, col2 = st.columns(2)

    # Opção 1: Download em CSV
    with col1:
        st.markdown("##### Formato CSV (Texto, bom para Excel)")
        df_csv = df_download.copy()
        df_csv['REGISTRO_DE_AULA'] = df_csv['REGISTRO_DE_AULA'].astype(str).str.replace('NaT', 'Sem registro',
                                                                                        regex=False)
        df_csv['REGISTRO_DE_CONTEUDO'] = df_csv['REGISTRO_DE_CONTEUDO'].astype(str).str.replace('NaT', 'Sem registro',
                                                                                                regex=False)
        csv_data = df_csv.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="Baixar .csv",
            data=csv_data,
            file_name=f"backup_relatorios_lrco_{timestamp}.csv",
            mime='text/csv',
            use_container_width=True
        )

    # Opção 2: Download em Parquet
    with col2:
        st.markdown("##### Formato Parquet (Comprimido, mais rápido)")
        parquet_data = df_download.to_parquet(engine='pyarrow')

        st.download_button(
            label="Baixar .parquet",
            data=parquet_data,
            file_name=f"backup_relatorios_lrco_{timestamp}.parquet",
            mime='application/octet-stream',
            use_container_width=True
        )