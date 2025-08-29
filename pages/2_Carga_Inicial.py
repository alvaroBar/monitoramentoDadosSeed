# ==============================================================================
# ARQUIVO COMPLETO: pages/2_Carga_Inicial.py (Versão Multilocatário)
# ==============================================================================

import streamlit as st
import pandas as pd
import time
from bigquery_loader import autenticar_usuario, carregar_dados_no_bigquery

st.set_page_config(layout="wide")
st.title("🗂️ Carga Inicial de Dados para o BigQuery")

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
st.sidebar.info(f"Dataset Alvo: **{dataset_id}**")
if st.sidebar.button("Logout", key="logout_carga_inicial"):
    del st.session_state.credentials
    if 'user_info' in st.session_state: del st.session_state.user_info
    st.rerun()

# --- Lógica da Página de Carga Inicial ---
st.info(
    "Use esta página para substituir **todos os dados** no seu banco de dados. "
    "Esta operação apagará os dados existentes antes de carregar os novos."
)

uploaded_csv = st.file_uploader("Selecione o arquivo CSV completo com os dados históricos", type=["csv"])

if uploaded_csv:
    st.warning(f"⚠️ **Atenção:** Pressionar o botão abaixo irá substituir todos os dados no dataset `{dataset_id}`.",
               icon="🚨")

    if st.button("Iniciar Carga Inicial e Substituir Dados"):
        try:
            with st.spinner("Lendo o arquivo CSV..."):
                df_inicial = pd.read_csv(uploaded_csv, encoding='utf-8')
            st.success(f"Arquivo lido! {len(df_inicial)} linhas encontradas.")

            colunas_esperadas = [
                "SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA",
                "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"
            ]
            if len(df_inicial.columns) == len(colunas_esperadas):
                df_inicial.columns = colunas_esperadas
            else:
                st.error("O número de colunas no CSV não corresponde ao esperado.")
                st.stop()

            with st.spinner("Conectando ao BigQuery e enviando os dados..."):
                sucesso = carregar_dados_no_bigquery(df_inicial, creds, dataset_id, 'replace')

            if sucesso:
                st.success("Carga inicial concluída! Todos os dados foram substituídos.")
                st.balloons()
                time.sleep(3)
                st.rerun()
            else:
                st.error("A carga inicial falhou.")
        except Exception as e:
            st.error(f"Ocorreu um erro durante o processo: {e}")