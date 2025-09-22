# ==============================================================================
# ARQUIVO DA PÁGINA: p6_Consultar_Dados.py
# Removido o limite de 1000 linhas na consulta de dados.
# ==============================================================================

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
import datetime

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import autenticar_usuario, get_filter_options, query_data_from_bq

st.set_page_config(layout="wide")
st.title("Consulta Avançada de Dados 🔎")

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
    if st.button("Logout", key="logout_Consultar_Dados"):
        st.session_state.clear()
        st.rerun()

# --- Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_consulta")

# --- Carrega as opções para os filtros ---
creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

with st.spinner("A carregar opções de filtro do banco de dados..."):
    opcoes_filtro = get_filter_options(creds, dataset_id)

# --- Interface de Filtros ---
st.header("Filtros de Busca")
st.info("Preencha um ou mais campos abaixo para buscar os registros. Deixe em branco para ignorar um filtro.")

with st.form(key="search_form"):
    col1, col2 = st.columns(2)

    with col1:
        filtro_semanas = st.multiselect("Semanas", options=opcoes_filtro.get("semanas", []))
        filtro_municipios = st.multiselect("Municípios", options=opcoes_filtro.get("municipios", []))
        filtro_escolas = st.multiselect("Escolas", options=opcoes_filtro.get("escolas", []))

    with col2:
        filtro_disciplinas = st.multiselect("Disciplinas", options=opcoes_filtro.get("disciplinas", []))
        filtro_turmas = st.multiselect("Turmas", options=opcoes_filtro.get("turmas", []))

        filtro_nulos_opcao = st.selectbox(
            "Filtrar por registros não lançados",
            options=["Não filtrar", "Falta Registo da Aula", "Falta Registo do Conteúdo", "Falta um ou ambos"],
            index=0
        )

    min_date_banco = pd.to_datetime(opcoes_filtro.get("min_data")).date() if opcoes_filtro.get(
        "min_data") else datetime.date(2020, 1, 1)
    max_date_banco = pd.to_datetime(opcoes_filtro.get("max_data")).date() if opcoes_filtro.get(
        "max_data") else datetime.date.today()

    filtro_data = st.date_input(
        "Intervalo de Data do Relatório",
        value=[],
        min_value=min_date_banco,
        max_value=max_date_banco,
        format="DD/MM/YYYY"
    )

    submitted = st.form_submit_button("Buscar no Banco de Dados", use_container_width=True, type="primary")

if submitted:
    null_filter_map = {
        "Falta Registo da Aula": "aula",
        "Falta Registo do Conteúdo": "conteudo",
        "Falta um ou ambos": "ambos"
    }

    filters = {
        "semanas": filtro_semanas,
        "municipios": filtro_municipios,
        "escolas": filtro_escolas,
        "disciplinas": filtro_disciplinas,
        "turmas": filtro_turmas,
        "data_inicio": filtro_data[0] if filtro_data and len(filtro_data) == 2 else None,
        "data_fim": filtro_data[1] if filtro_data and len(filtro_data) == 2 else None,
        "null_filter": null_filter_map.get(filtro_nulos_opcao)
    }

    filters = {k: v for k, v in filters.items() if v}

    if not filters:
        st.warning("Por favor, selecione pelo menos um filtro para iniciar a busca.")
    else:
        with st.spinner("A buscar dados no BigQuery..."):
            st.session_state.search_results = query_data_from_bq(creds, dataset_id, filters)
            st.session_state.submitted_form = True

# --- Exibição dos Resultados ---
if 'search_results' in st.session_state and st.session_state.get('submitted_form'):
    st.markdown("---")
    st.header("Resultados da Busca")

    df_results = st.session_state.search_results

    if not df_results.empty:
        # --- ALTERAÇÃO APLICADA AQUI: Mensagem de sucesso atualizada ---
        st.success(f"{len(df_results)} registros encontrados.")

        csv_data = df_results.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar resultados como CSV",
            data=csv_data,
            file_name="consulta_relatorios.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.dataframe(
            df_results,
            column_config={
                "DATA_DO_RELATORIO": st.column_config.DateColumn("Data do Relatório", format="DD/MM/YYYY"),
                "REGISTRO_DE_AULA": st.column_config.DatetimeColumn("Registo da Aula", format="DD/MM/YYYY HH:mm:ss"),
                "REGISTRO_DE_CONTEUDO": st.column_config.DatetimeColumn("Registo do Conteúdo",
                                                                        format="DD/MM/YYYY HH:mm:ss"),
            },
            use_container_width=True
        )
    else:
        st.info("Nenhum registro encontrado com os filtros selecionados.")

