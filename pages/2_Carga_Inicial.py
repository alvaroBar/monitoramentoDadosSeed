# ==============================================================================
# ARQUIVO COMPLETO: pages/2_Carga_Inicial.py (Versão Multilocatário)
# Página para realizar a carga inicial (substituição) de dados de um CSV.
# ==============================================================================

import streamlit as st
import pandas as pd
from bigquery_loader import autenticar_usuario, carregar_dados_no_bigquery

st.set_page_config(layout="wide")
st.title("Página de Carga Inicial (Bulk Load)")
st.info(
    "Use esta página apenas quando precisar substituir todos os dados no seu banco de dados. Esta operação apagará todos os dados existentes antes de carregar os novos.")

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

st.markdown("---")

# --- Lógica da Página ---
uploaded_csv = st.file_uploader("Selecione o arquivo CSV completo com os dados históricos", type=["csv"])

if uploaded_csv:
    st.warning(
        f"**Atenção:** Pressionar o botão abaixo irá substituir todos os dados na tabela `relatorios_lrco` do seu dataset (`{dataset_id}`).")

    if st.button("Iniciar Carga Inicial e Substituir Dados"):
        try:
            with st.spinner("Lendo arquivo CSV..."):
                df = pd.read_csv(uploaded_csv, encoding='utf-8')
                st.success(f"Arquivo lido com sucesso! {len(df)} linhas encontradas.")

            # Padroniza os nomes das colunas para o formato esperado pelo loader
            df.columns = [
                "SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA",
                "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"
            ]

            # Garante que a coluna SEMANA seja numérica antes de ordenar
            df['SEMANA'] = pd.to_numeric(df['SEMANA'], errors='coerce').fillna(0).astype(int)
            df.sort_values(by="SEMANA", inplace=True)

            with st.spinner(
                    f"Carregando {len(df)} registros para o dataset '{dataset_id}'... Esta operação pode demorar vários minutos."):
                sucesso = carregar_dados_no_bigquery(df, st.session_state.credentials, dataset_id, 'replace')

                if sucesso:
                    st.success("Carga inicial concluída com sucesso! Todos os dados foram substituídos.")
                    st.balloons()
                else:
                    st.error("A carga inicial falhou. Verifique as mensagens de erro acima.")

        except Exception as e:
            st.error(f"Ocorreu um erro durante a carga inicial: {e}")
