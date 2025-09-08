# ==============================================================================
# ARQUIVO DA PÁGINA: 5_Consultar_Dados.py
# Permite ao usuário filtrar e buscar registros no banco de dados.
# ==============================================================================

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import autenticar_usuario, query_data_from_bq

st.set_page_config(layout="wide")
st.title("Consulta de Dados 🔎")

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
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_consulta")

# --- Interface de Filtros ---
st.header("Filtros de Busca")

with st.form(key="search_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        filtro_semana = st.number_input("Filtrar por Semana (0 para ignorar)", min_value=0, step=1, value=0)
        filtro_municipio = st.text_input("Filtrar por Município")

    with col2:
        filtro_escola = st.text_input("Filtrar por Escola")
        filtro_turma = st.text_input("Filtrar por Turma")

    with col3:
        filtro_disciplina = st.text_input("Filtrar por Disciplina")
        filtro_data = st.date_input("Filtrar por Data do Relatório", value=(None, None))

    submitted = st.form_submit_button("Buscar no Banco de Dados")

if submitted:
    # Coleta os filtros do formulário
    filters = {
        "semana": filtro_semana if filtro_semana > 0 else None,
        "municipio": filtro_municipio,
        "escola": filtro_escola,
        "turma": filtro_turma,
        "disciplina": filtro_disciplina,
        "data_inicio": filtro_data[0] if filtro_data and len(filtro_data) == 2 else None,
        "data_fim": filtro_data[1] if filtro_data and len(filtro_data) == 2 else None,
    }

    # Remove filtros vazios para não serem usados na consulta
    filters = {k: v for k, v in filters.items() if v is not None and v != ""}

    if not filters:
        st.warning("Por favor, preencha pelo menos um filtro para iniciar a busca.")
    else:
        with st.spinner("A buscar dados no BigQuery..."):
            creds = st.session_state.credentials
            dataset_id = st.session_state.dataset_id

            # Chama a nova função de busca e armazena os resultados na sessão
            st.session_state.search_results = query_data_from_bq(creds, dataset_id, filters)

# --- Exibição dos Resultados ---
if 'search_results' in st.session_state:
    st.markdown("---")
    st.header("Resultados da Busca")

    df_results = st.session_state.search_results

    if not df_results.empty:
        st.success(f"{len(df_results)} registros encontrados (limitado a 1000 resultados).")

        # Oferece o download dos resultados
        csv_data = df_results.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar resultados como CSV",
            data=csv_data,
            file_name="consulta_relatorios.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.dataframe(df_results)
    else:
        st.info("Nenhum registro encontrado com os filtros selecionados.")
