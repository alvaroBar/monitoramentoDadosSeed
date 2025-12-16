# ==============================================================================
# ARQUIVO DA PÁGINA: p6_Consultar_Dados.py
# VERSÃO REVISADA: Aumentado o limite de renderização do Styler.
# ==============================================================================

import streamlit as st
import pandas as pd
import datetime
import io
from streamlit_autorefresh import st_autorefresh
from services import auth_service
from services.bigquery_service import BigQueryService
from openpyxl.utils import get_column_letter
from utils import interface

# Aumenta o limite de células que podem ser estilizadas pelo Pandas
pd.set_option("styler.render.max_elements", 500000)

st.set_page_config(layout="wide")
st.title("Consulta Avançada de Dados 🔎")
interface.exibir_cabecalho_ano()

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

# --- Coluna Central para Melhor Estética ---
_, col_main, _ = st.columns([0.1, 0.8, 0.1])

with col_main:
    with st.container(border=True):
        st.header("Filtros de Busca")
        st.caption("Preencha um ou mais campos para buscar os registros. Deixe em branco para ignorar um filtro.")

        with st.form(key="search_form"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Semanas**")
                filtro_semanas = st.multiselect("Semanas", options=opcoes_filtro.get("semanas", []),
                                                label_visibility="collapsed")
                st.markdown("**Municípios**")
                filtro_municipios = st.multiselect("Municípios", options=opcoes_filtro.get("municipios", []),
                                                   label_visibility="collapsed")
                st.markdown("**Escolas**")
                filtro_escolas = st.multiselect("Escolas", options=opcoes_filtro.get("escolas", []),
                                                label_visibility="collapsed")
            with col2:
                st.markdown("**Disciplinas**")
                filtro_disciplinas = st.multiselect("Disciplinas", options=opcoes_filtro.get("disciplinas", []),
                                                    label_visibility="collapsed")
                st.markdown("**Turmas**")
                filtro_turmas = st.multiselect("Turmas", options=opcoes_filtro.get("turmas", []),
                                               label_visibility="collapsed")
                st.markdown("**Filtrar por registros não lançados**")
                filtro_nulos_opcao = st.selectbox(
                    "Filtrar por registros não lançados",
                    options=["Não filtrar", "Falta Registo da Aula", "Falta Registo do Conteúdo", "Falta um ou ambos"],
                    label_visibility="collapsed"
                )

            st.markdown("**Intervalo de Data do Relatório**")
            min_date = pd.to_datetime(opcoes_filtro.get("min_data")).date() if opcoes_filtro.get(
                "min_data") else datetime.date(2020, 1, 1)
            max_date = pd.to_datetime(opcoes_filtro.get("max_data")).date() if opcoes_filtro.get(
                "max_data") else datetime.date.today()
            filtro_data = st.date_input("Intervalo de Data do Relatório", value=[], min_value=min_date,
                                        max_value=max_date, label_visibility="collapsed")

            _, col_btn_buscar = st.columns([3, 1])
            with col_btn_buscar:
                submitted = st.form_submit_button("Buscar", type="primary", use_container_width=True)

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

    if 'search_results' in st.session_state and st.session_state.get('submitted_form'):
        with st.container(border=True):
            st.header("Resultados da Busca")
            df_results = st.session_state.search_results

            if not df_results.empty:
                st.success(f"{len(df_results)} registros encontrados.")


                def to_excel_auto_width(df_styled):
                    output = io.BytesIO()
                    writer = pd.ExcelWriter(output, engine='openpyxl')
                    df_styled.to_excel(writer, index=False, sheet_name='Resultados')
                    worksheet = writer.sheets['Resultados']
                    for column_cells in worksheet.columns:
                        max_length = 0
                        column_letter = get_column_letter(column_cells[0].column)
                        for cell in column_cells:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = (max_length + 2)
                        worksheet.column_dimensions[column_letter].width = adjusted_width
                    writer.close()
                    return output.getvalue()


                df_for_display = df_results.copy()


                def formatar_e_preencher(valor):
                    if pd.isna(valor): return "Sem registro"
                    return pd.to_datetime(valor).tz_localize(None).strftime('%d/%m/%Y %H:%M:%S')


                for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
                    df_for_display[col] = df_for_display[col].apply(formatar_e_preencher)

                excel_data = to_excel_auto_width(
                    df_for_display.style.map(lambda x: 'color: red' if x == "Sem registro" else '',
                                             subset=['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']))

                _, col_btn_download = st.columns([3, 1])
                with col_btn_download:
                    st.download_button(
                        label="Baixar como Excel (.xlsx)",
                        data=excel_data,
                        file_name="consulta_relatorios.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )


                def highlight_sem_registro(cell_value):
                    return 'color: red' if cell_value == "Sem registro" else ''


                # CORREÇÃO: Substituído .applymap() por .map()
                styled_df = df_for_display.style.map(highlight_sem_registro,
                                                     subset=['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO'])

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

