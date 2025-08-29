# ==============================================================================
# PÁGINA 3: BACKUP DE DADOS
# Esta página permite ao usuário baixar um backup completo da tabela
# do BigQuery no formato CSV.
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import datetime

# Importa as funções necessárias do módulo principal
from bigquery_loader import autenticar_com_service_account, get_all_data_from_bq

st.set_page_config(layout="wide")
st.title("📥 Backup dos Dados do BigQuery")

st.info(
    "Use esta página para baixar uma cópia de segurança completa de todos os dados "
    "atualmente armazenados na tabela `relatorios_lrco` no formato CSV."
)

if st.button("Baixar Backup Completo (CSV)"):
    creds = autenticar_com_service_account()
    if creds:
        with st.spinner("Buscando todos os dados no BigQuery... Isso pode levar um momento."):
            df_backup = get_all_data_from_bq(creds)

        if not df_backup.empty:
            st.success(f"Sucesso! {len(df_backup)} registros encontrados.")

            # Converte o DataFrame para CSV em memória
            csv_data = df_backup.to_csv(index=False).encode('utf-8')

            # Gera um nome de arquivo com a data e hora atuais
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"backup_relatorios_lrco_{timestamp}.csv"

            # Cria o botão de download
            st.download_button(
                label="Clique aqui para baixar o arquivo CSV",
                data=csv_data,
                file_name=file_name,
                mime='text/csv',
            )
        else:
            st.warning("Nenhum dado foi encontrado no BigQuery ou ocorreu um erro na busca.")
    else:
        st.error("Falha na autenticação. Verifique as credenciais da Conta de Serviço.")