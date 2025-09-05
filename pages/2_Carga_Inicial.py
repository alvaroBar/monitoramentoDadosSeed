import streamlit as st
import pandas as pd
from bigquery_loader import autenticar_usuario, carregar_dados_no_bigquery
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")
st.title("Carga Inicial de Dados Históricos")

autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica da Aplicação (Visível apenas após o login) ---
user_info = st.session_state.user_info
user_email = user_info.get("email")
user_name = user_info.get("name", "Usuário")

# --- CORREÇÃO: Mapeia o e-mail para o dataset_id em cada execução ---
try:
    office_mapping = st.secrets.office_mapping
    if user_email in office_mapping:
        st.session_state.dataset_id = office_mapping[user_email]
    else:
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador.")
        st.stop()
except (AttributeError, KeyError):
    st.error(
        "ERRO DE CONFIGURAÇÃO: O mapeamento de escritórios [office_mapping] não foi encontrado nos Segredos do Streamlit.")
    st.stop()

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- ALTERAÇÃO APLICADA AQUI: Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_processar")

st.warning(
    "Use esta página apenas uma vez ou quando precisar substituir todos os dados no banco de dados. Esta operação apagará os dados existentes antes de carregar os novos.")

uploaded_file = st.file_uploader("Selecione o arquivo CSV completo com os dados históricos", type="csv")

if uploaded_file is not None:
    if st.button("Iniciar Carga Inicial e Substituir Dados", use_container_width=True):
        try:
            with st.spinner("Lendo arquivo CSV... Isso pode demorar alguns minutos para arquivos grandes."):
                df = pd.read_csv(uploaded_file)
            st.success(f"Arquivo lido com sucesso! {len(df)} linhas encontradas.")

            with st.spinner("Enviando dados para o BigQuery... Este processo substituirá todos os dados existentes."):
                creds = st.session_state.credentials
                dataset_id = st.session_state.dataset_id

                # Padroniza as colunas do CSV
                df.columns = [col.upper().replace(' ', '_') for col in df.columns]

                # Garante que a coluna 'SEMANA' é numérica antes de ordenar
                df['SEMANA'] = pd.to_numeric(df['SEMANA'], errors='coerce').fillna(0).astype(int)

                # Ordena o DataFrame pela semana
                df = df.sort_values(by='SEMANA').reset_index(drop=True)

                sucesso = carregar_dados_no_bigquery(df, creds, dataset_id, 'replace')

            if sucesso:
                st.success("Carga inicial concluída com sucesso! Todos os dados foram substituídos no BigQuery.")
                st.balloons()
            else:
                st.error("A carga inicial falhou. Verifique as mensagens de erro acima.")

        except Exception as e:
            st.error(f"Ocorreu um erro durante a carga inicial: {e}")