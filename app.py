import streamlit as st
import pandas as pd
from services import auth_service
from services.bigquery_service import BigQueryService
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Dashboard de Acompanhamento",
    layout="wide"
)

# --- CSS customizado (pode manter ou remover) ---
st.markdown("""
<style>
/* ... seu CSS ... */
</style>
""", unsafe_allow_html=True)

# 1. Autenticação
auth_service.autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica de Mapeamento CORRETA ---
user_info = st.session_state.user_info
user_email = user_info.get("email")
user_name = user_info.get("name", "Usuário")

try:
    office_mapping = st.secrets.office_mapping
    if user_email in office_mapping:
        st.session_state.dataset_id = office_mapping[user_email]
    else:
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador.")
        st.stop()
except (AttributeError, KeyError):
    st.error("ERRO DE CONFIGURAÇÃO: O mapeamento [office_mapping] não foi encontrado nos Segredos do Streamlit.")
    st.stop()

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- Inicialização CORRETA do Serviço ---
if 'bq_service' not in st.session_state:
    st.session_state.bq_service = BigQueryService(
        credentials=st.session_state.credentials,
        dataset_id=st.session_state.dataset_id # Agora usa o dataset_id correto
    )
bq_service = st.session_state.bq_service


# --- Conteúdo do Dashboard ---
st.title("Dashboard de Acompanhamento LRCO")

with st.spinner("A carregar estatísticas..."):
    # Agora a chamada ao método funcionará corretamente
    stats = bq_service.get_dashboard_stats()

if stats:
    # ... O resto da sua lógica para exibir os cartões e gráficos ...
    pass
else:
    st.info("Ainda não há dados lançados para este escritório.")