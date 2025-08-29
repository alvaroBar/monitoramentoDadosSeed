# ==============================================================================
# PÁGINA 3: BACKUP DE DADOS
# Esta página permite ao usuário baixar um backup completo da tabela
# do BigQuery no formato Excel, com formatação especial.
# ==============================================================================

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from openpyxl.styles import Font

# Importa as funções necessárias do módulo principal
from bigquery_loader import autenticar_com_service_account, get_all_data_from_bq

st.set_page_config(layout="wide")
st.title("📥 Backup dos Dados do BigQuery")

st.info(
    "Use esta página para baixar uma cópia de segurança completa de todos os dados "
    "atualmente armazenados na tabela `relatorios_lrco` no formato Excel (.xlsx)."
)

if st.button("Baixar Backup Completo (Excel)"):
    creds = autenticar_com_service_account()
    if creds:
        with st.spinner("Buscando todos os dados no BigQuery... Isso pode levar um momento."):
            df_backup = get_all_data_from_bq(creds)

        if not df_backup.empty:
            st.success(f"Sucesso! {len(df_backup)} registros encontrados.")

            # Preenche valores nulos/vazios com 'Sem registro'
            df_backup.fillna("Sem registro", inplace=True)

            # --- Lógica para criar um arquivo Excel com formatação ---
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_backup.to_excel(writer, index=False, sheet_name='Backup')

                # Acessa a planilha para aplicar o estilo
                worksheet = writer.sheets['Backup']

                # Define a fonte vermelha
                red_font = Font(color="FF0000")

                # Itera sobre todas as células para encontrar e colorir "Sem registro"
                for row in worksheet.iter_rows():
                    for cell in row:
                        if cell.value == "Sem registro":
                            cell.font = red_font

            output.seek(0)
            # --- Fim da lógica do Excel ---

            # Gera um nome de arquivo com a data e hora atuais
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"backup_relatorios_lrco_{timestamp}.xlsx"

            # Cria o botão de download para o arquivo Excel
            st.download_button(
                label="Clique aqui para baixar o arquivo Excel",
                data=output,
                file_name=file_name,
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
        else:
            st.warning("Nenhum dado foi encontrado no BigQuery ou ocorreu um erro na busca.")
    else:
        st.error("Falha na autenticação. Verifique as credenciais da Conta de Serviço.")