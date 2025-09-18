# ==============================================================================
# ARQUIVO DA PÁGINA: 6_Gerenciar_Análises.py
# Permite ao usuário criar e atualizar tabelas de análise personalizadas.
# ==============================================================================

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import autenticar_usuario, get_available_weeks, list_analysis_tables, create_or_update_analysis

st.set_page_config(layout="wide")
st.title("Gestão de Análises 🗂️")

autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica da Aplicação (Visível apenas após o login) ---
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
    st.error(
        "ERRO DE CONFIGURAÇÃO: O mapeamento de escritórios [office_mapping] não foi encontrado nos Segredos do Streamlit.")
    st.stop()

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_analise")

creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

st.info(
    "Use esta página para criar ou atualizar 'fotografias' dos seus dados para períodos específicos (ex: um bimestre ou trimestre). "
    "Estas tabelas de análise podem ser usadas para comparações e relatórios."
)

st.markdown("---")

# --- Secção 1: Criar ou Atualizar uma Análise ---
st.header("Criar / Atualizar uma Análise")

with st.form("analysis_form"):
    # Campo para o usuário dar um nome à sua análise
    analysis_name = st.text_input(
        "Nome da Análise (ex: Primeiro Bimestre 2025)",
        placeholder="Digite um nome claro e descritivo"
    )

    # Busca as semanas disponíveis na tabela histórica
    with st.spinner("A carregar semanas disponíveis..."):
        available_weeks = get_available_weeks(creds, dataset_id)

    if not available_weeks:
        st.warning("Não há semanas disponíveis na tabela de dados históricos para criar uma análise.")
    else:
        # Seletor para o usuário escolher as semanas a incluir
        selected_weeks = st.multiselect(
            "Selecione as semanas para incluir nesta análise:",
            options=available_weeks,
            default=[]
        )

    submit_button = st.form_submit_button("Salvar Análise", use_container_width=True, type="primary")

if submit_button:
    if not analysis_name:
        st.error("Por favor, forneça um nome para a análise.")
    elif not selected_weeks:
        st.error("Por favor, selecione pelo menos uma semana para incluir na análise.")
    else:
        with st.spinner(f"A criar/atualizar a análise '{analysis_name}'..."):
            sucesso, mensagem = create_or_update_analysis(creds, dataset_id, analysis_name, selected_weeks)

        if sucesso:
            st.success(mensagem)
            st.balloons()
        else:
            st.error(mensagem)

st.markdown("---")

# --- Secção 2: Listar Análises Existentes ---
st.header("Análises Salvas")

with st.spinner("A buscar análises existentes..."):
    analysis_tables = list_analysis_tables(creds, dataset_id)

if not analysis_tables:
    st.info("Ainda não há nenhuma tabela de análise criada para este escritório.")
else:
    st.write("As seguintes tabelas de análise foram encontradas no seu dataset:")
    # Exibe as tabelas em formato de lista
    for table in sorted(analysis_tables):
        st.code(table, language=None)
