# ==============================================================================
# PÁGINA 3: BACKUP DE DADOS
# Esta página permite ao usuário baixar um backup completo da tabela
# do BigQuery nos formatos CSV ou Parquet (mais eficiente).
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

# Importa as funções necessárias do módulo principal
from bigquery_loader import autenticar_com_service_account, get_all_data_from_bq

st.set_page_config(layout="wide")
st.title("📥 Backup dos Dados do BigQuery")

st.info(
    "Use esta página para baixar uma cópia de segurança completa de todos os dados "
    "atualmente armazenados na tabela `relatorios_lrco`."
)

# O botão agora tem um texto mais claro sobre o que ele faz
if st.button("Preparar Dados para Download"):
    creds = autenticar_com_service_account()
    if creds:
        with st.spinner("Buscando todos os dados no BigQuery... Esta é a etapa demorada e pode levar um momento."):
            df_backup = get_all_data_from_bq(creds)

        if not df_backup.empty:
            st.success(f"Sucesso! {len(df_backup)} registros encontrados e prontos para download.")
            st.session_state.df_backup = df_backup  # Armazena o dataframe no estado da sessão
        else:
            st.warning("Nenhum dado foi encontrado no BigQuery ou ocorreu um erro na busca.")
    else:
        st.error("Falha na autenticação. Verifique as credenciais da Conta de Serviço.")

# --- Seção de Download ---
# Só mostra os botões se os dados já tiverem sido buscados
if 'df_backup' in st.session_state and not st.session_state.df_backup.empty:
    st.markdown("---")
    st.subheader("Dados Prontos. Escolha o formato para baixar:")
    # Adiciona um texto explicativo
    st.markdown(
        "A etapa demorada (buscar os dados) já foi concluída. Agora, a geração e o download do arquivo final serão rápidos.")

    df_download = st.session_state.df_backup.copy()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    col1, col2 = st.columns(2)

    # --- Opção 1: Download em CSV (com substituição de 'NaT') ---
    with col1:
        st.markdown("##### Formato CSV (Texto, bom para Excel)")

        # Prepara os dados para o CSV
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

    # --- Opção 2: Download em Parquet (Leve e Rápido) ---
    with col2:
        st.markdown("##### Formato Parquet (Comprimido, mais rápido)")

        # Converte o DataFrame para Parquet em memória
        parquet_data = df_download.to_parquet(engine='pyarrow')

        st.download_button(
            label="Baixar .parquet",
            data=parquet_data,
            file_name=f"backup_relatorios_lrco_{timestamp}.parquet",
            mime='application/octet-stream',
            use_container_width=True
        )