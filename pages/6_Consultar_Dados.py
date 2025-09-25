# ==============================================================================
# ARQUIVO DA PÁGINA: p6_Consultar_Dados.py
# VERSÃO REVISADA: Adicionada estilização condicional para destacar pendências.
# ==============================================================================

import streamlit as st
import pandas as pd
import datetime
from streamlit_autorefresh import st_autorefresh
from services import auth_service
from services.bigquery_service import BigQueryService

st.set_page_config(layout="wide")
st.title("Consulta Avançada de Dados 🔎")

# 1. Autenticação e inicialização padrão
auth_service.autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

user_info = st.session_state.user_info
user_name = user_info.get("name", "Usuário")
with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout"):
        auth_service.logout_usuario()

try:
    user_email = user_info.get("email")
    office_mapping = st.secrets.office_mapping
    if user_email in office_mapping:
        st.session_state.dataset_id = office_mapping[user_email]
    else:
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador.")
        st.stop()
except (AttributeError, KeyError):
    st.error("ERRO DE CONFIGURAÇÃO: O mapeamento [office_mapping] não foi encontrado.")
    st.stop()

if 'bq_service' not in st.session_state:
    st.session_state.bq_service = BigQueryService(
        credentials=st.session_state.credentials,
        dataset_id=st.session_state.dataset_id
    )
bq_service = st.session_state.bq_service

# --- Keep-alive da sessão ---
st_autorefresh(interval=10 * 60 * 1000, key="session_refresher_consulta")

# --- Lógica da Página ---

with st.spinner("Carregando opções de filtro..."):
    opcoes_filtro = bq_service.get_filter_options()

st.header("Filtros de Busca")
st.info("Preencha um ou mais campos para buscar os registros. Deixe em branco para ignorar um filtro.")

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
            options=["Não filtrar", "Falta Registo da Aula", "Falta Registo do Conteúdo", "Falta um ou ambos"]
        )

    min_date = pd.to_datetime(opcoes_filtro.get("min_data")).date() if opcoes_filtro.get("min_data") else datetime.date(
        2020, 1, 1)
    max_date = pd.to_datetime(opcoes_filtro.get("max_data")).date() if opcoes_filtro.get(
        "max_data") else datetime.date.today()
    filtro_data = st.date_input("Intervalo de Data do Relatório", value=[], min_value=min_date, max_value=max_date)

    submitted = st.form_submit_button("Buscar no Banco de Dados", use_container_width=True, type="primary")

if submitted:
    null_filter_map = {"Falta Registo da Aula": "aula", "Falta Registo do Conteúdo": "conteudo",
                       "Falta um ou ambos": "ambos"}
    filters = {
        "semanas": filtro_semanas, "municipios": filtro_municipios, "escolas": filtro_escolas,
        "disciplinas": filtro_disciplinas, "turmas": filtro_turmas,
        "data_inicio": filtro_data[0] if len(filtro_data) == 2 else None,
        "data_fim": filtro_data[1] if len(filtro_data) == 2 else None,
        "null_filter": null_filter_map.get(filtro_nulos_opcao)
    }
    filters = {k: v for k, v in filters.items() if v}

    if not filters:
        st.warning("Por favor, selecione pelo menos um filtro para iniciar a busca.")
    else:
        with st.spinner("Buscando dados no BigQuery..."):
            st.session_state.search_results = bq_service.query_data(filters)
            st.session_state.submitted_form = True

# p6_Consultar_Dados.py -> Substitua esta seção inteira

if 'search_results' in st.session_state and st.session_state.get('submitted_form'):
    st.markdown("---")
    st.header("Resultados da Busca")
    df_results = st.session_state.search_results

    if not df_results.empty:
        st.success(f"{len(df_results)} registros encontrados.")

        # --- LÓGICA DE ESTILIZAÇÃO ROBUSTA (VERSÃO 2) ---

        # 1. Prepara uma cópia para o download em CSV (sem alteração)
        df_for_csv = df_results.copy()
        for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
            df_for_csv[col] = pd.to_datetime(df_for_csv[col]).dt.strftime('%Y-%m-%d %H:%M:%S').fillna("Sem registro")

        csv_data = df_for_csv.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar resultados como CSV",
            data=csv_data,
            file_name="consulta_relatorios.csv",
            mime="text/csv",
            use_container_width=True
        )

        # 2. Prepara um DataFrame para EXIBIÇÃO de forma mais segura
        df_for_display = df_results.copy()


        def formatar_e_preencher(valor):
            """Função para formatar data/hora ou retornar 'Sem registro' se for nulo."""
            if pd.isna(valor):
                return "Sem registro"
            # Converte para datetime e formata. Adiciona-se tz=None para evitar problemas de fuso horário.
            return pd.to_datetime(valor).tz_localize(None).strftime('%d/%m/%Y %H:%M:%S')


        # Aplica a função de formatação segura
        for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
            df_for_display[col] = df_for_display[col].apply(formatar_e_preencher)


        # 3. Define a função de estilo que reage ao TEXTO
        def highlight_sem_registro(cell_value):
            return 'color: red' if cell_value == "Sem registro" else ''


        # 4. Aplica o estilo ao DataFrame de exibição já formatado
        styled_df = df_for_display.style.applymap(highlight_sem_registro,
                                                  subset=['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO'])

        # 5. Exibe o DataFrame estilizado
        st.dataframe(
            styled_df,
            column_config={
                "DATA_DO_RELATORIO": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "HORARIO": st.column_config.TimeColumn("Horário", format="HH:mm"),
                "REGISTRO_DE_AULA": "Registro da Aula",
                "REGISTRO_DE_CONTEUDO": "Registro do Conteúdo"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nenhum registro encontrado com os filtros selecionados.")