# ==============================================================================
# ARQUIVO DA PÁGINA: 5_Consultar_Dados.py
# Adicionada formatação de data para exibição no padrão DD/MM/YYYY.
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
    if st.button("Logout"):
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

        min_date_banco = pd.to_datetime(opcoes_filtro.get("min_data")).date() if opcoes_filtro.get(
            "min_data") else datetime.date(2020, 1, 1)
        max_date_banco = pd.to_datetime(opcoes_filtro.get("max_data")).date() if opcoes_filtro.get(
            "max_data") else datetime.date.today()

        filtro_data = st.date_input(
            "Intervalo de Data do Relatório",
            value=[],
            min_value=min_date_banco,
            max_value=max_date_banco
        )

    submitted = st.form_submit_button("Buscar no Banco de Dados", use_container_width=True, type="primary")

if submitted:
    data_inicio_selecionada = filtro_data[0] if filtro_data and len(filtro_data) == 2 else None
    data_fim_selecionada = filtro_data[1] if filtro_data and len(filtro_data) == 2 else None

    # --- LÓGICA DE VALIDAÇÃO DE DATA ---
    data_valida = True
    if data_inicio_selecionada and data_fim_selecionada:
        if data_inicio_selecionada < min_date_banco or data_fim_selecionada > max_date_banco:
            st.error(
                f"Intervalo de data inválido. Por favor, selecione datas entre {min_date_banco.strftime('%d/%m/%Y')} e {max_date_banco.strftime('%d/%m/%Y')}.")
            data_valida = False

    if data_valida:
        filters = {
            "semanas": filtro_semanas,
            "municipios": filtro_municipios,
            "escolas": filtro_escolas,
            "disciplinas": filtro_disciplinas,
            "turmas": filtro_turmas,
            "data_inicio": data_inicio_selecionada,
            "data_fim": data_fim_selecionada,
        }

        filters = {k: v for k, v in filters.items() if v}

        if not filters:
            st.warning("Por favor, selecione pelo menos um filtro para iniciar a busca.")
        else:
            with st.spinner("A buscar dados no BigQuery..."):
                st.session_state.search_results = query_data_from_bq(creds, dataset_id, filters)
                # Limpa o estado 'submitted' para evitar re-execução automática
                st.session_state.submitted_form = True

# --- Exibição dos Resultados ---
if 'search_results' in st.session_state and st.session_state.get('submitted_form'):
    st.markdown("---")
    st.header("Resultados da Busca")

    df_results = st.session_state.search_results

    if not df_results.empty:
        st.success(f"{len(df_results)} registros encontrados (limitado aos 1000 resultados mais recentes).")

        # Mantém o dataframe original para o download do CSV
        csv_data = df_results.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar resultados como CSV",
            data=csv_data,
            file_name="consulta_relatorios.csv",
            mime="text/csv",
            use_container_width=True
        )

        # --- ALTERAÇÃO APLICADA AQUI: Formatação de datas para exibição ---
        # Cria uma cópia do DataFrame para formatar a exibição sem alterar os dados originais
        df_display = df_results.copy()

        # Garante que as colunas de data/datetime existem antes de tentar formatá-las
        if 'DATA_DO_RELATORIO' in df_display.columns:
            df_display['DATA_DO_RELATORIO'] = pd.to_datetime(df_display['DATA_DO_RELATORIO']).dt.strftime('%d/%m/%Y')
        if 'REGISTRO_DE_AULA' in df_display.columns:
            df_display['REGISTRO_DE_AULA'] = pd.to_datetime(df_display['REGISTRO_DE_AULA']).dt.strftime(
                '%d/%m/%Y %H:%M:%S').where(df_display['REGISTRO_DE_AULA'].notna())
        if 'REGISTRO_DE_CONTEUDO' in df_display.columns:
            df_display['REGISTRO_DE_CONTEUDO'] = pd.to_datetime(df_display['REGISTRO_DE_CONTEUDO']).dt.strftime(
                '%d/%m/%Y %H:%M:%S').where(df_display['REGISTRO_DE_CONTEUDO'].notna())

        st.dataframe(df_display)
    else:
        st.info("Nenhum registro encontrado com os filtros selecionados.")

