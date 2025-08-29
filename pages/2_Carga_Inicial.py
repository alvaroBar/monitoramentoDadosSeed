# ==============================================================================
# PÁGINA 2: CARGA INICIAL (BULK LOAD)
# Esta página permite ao usuário substituir todos os dados no BigQuery
# por um novo arquivo CSV completo.
# ==============================================================================

import streamlit as st
import pandas as pd
import time

# Importa a função de carregamento do módulo principal
# O .. significa "voltar um diretório" para encontrar o bigquery_loader
from ..bigquery_loader import autenticar_e_carregar

st.set_page_config(layout="wide")
st.title("🗂️ Carga Inicial de Dados para o BigQuery")

st.info(
    "Use esta página **apenas uma vez** ou quando precisar substituir **todos os dados** no banco de dados. "
    "Esta operação apagará os dados existentes antes de carregar os novos."
)

# --- Seção de Upload ---
uploaded_csv = st.file_uploader(
    "Selecione o arquivo CSV completo com os dados históricos",
    type=["csv"]
)

if uploaded_csv:
    st.warning("⚠️ **Atenção:** Pressionar o botão abaixo irá substituir todos os dados na tabela `relatorios_lrco`.",
               icon="🚨")

    if st.button("Iniciar Carga Inicial e Substituir Dados"):
        try:
            with st.spinner("Lendo o arquivo CSV... Isso pode levar alguns minutos para arquivos grandes."):
                # Carrega o CSV em um DataFrame do Pandas
                df_inicial = pd.read_csv(uploaded_csv, encoding='utf-8')

            st.success(f"Arquivo lido com sucesso! {len(df_inicial)} linhas encontradas.")

            with st.spinner("Conectando ao BigQuery e enviando os dados... Por favor, aguarde."):
                # Chama a função de carregamento com o modo 'replace'
                sucesso = autenticar_e_carregar(df_inicial, if_exists_mode='replace')

            if sucesso:
                st.success("Carga inicial concluída! Todos os dados foram substituídos no BigQuery.")
                st.balloons()
                time.sleep(5)  # Pausa para o usuário ver a mensagem antes de resetar
                st.rerun()
            else:
                st.error("A carga inicial falhou. Verifique as mensagens de erro acima.")

        except Exception as e:
            st.error(f"Ocorreu um erro durante o processo de carga inicial: {e}")
