# ==============================================================================
# ARQUIVO DA PÁGINA: 7_Auditoria_Comparativa.py
# VERSÃO REVISADA: Arquitetura finalizada e padronizada.
# ==============================================================================

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from services import auth_service
from services.bigquery_service import BigQueryService
from services import analysis_service

st.set_page_config(layout="wide")
st.title("Auditoria Comparativa de Pendências 🔍")

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
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_auditoria")

# --- Lógica da Página ---
st.info(
    "**Fluxo de Trabalho:**\n"
    "1. Na página `p1`, processe os PDFs e baixe o arquivo `.parquet`.\n"
    "2. Volte aqui, faça o upload do arquivo, selecione as semanas e gere o relatório."
)
st.markdown("---")

# --- Seção 1: Criar uma Auditoria Comparativa ---
with st.expander("➕ Gerar Nova Auditoria de Pendências", expanded=True):
    analysis_name = st.text_input("1. Dê um nome para a Auditoria", placeholder="Ex: Verificação Semanas 30-35")
    uploaded_parquet = st.file_uploader("2. Carregue o arquivo `dados_extraidos.parquet`", type=["parquet"])

    st.write("3. Selecione as semanas do histórico para comparar.")
    with st.spinner("Carregando semanas disponíveis..."):
        available_weeks = bq_service.get_available_weeks()

    if available_weeks:
        selected_weeks = st.multiselect("Semanas:", options=available_weeks)
    else:
        st.warning("Não há semanas no histórico para comparar.")
        selected_weeks = []

    if st.button("Gerar Relatório de Pendências", use_container_width=True, type="primary"):
        if not analysis_name:
            st.error("Por favor, forneça um nome para a auditoria.")
        elif not uploaded_parquet:
            st.error("Por favor, carregue o arquivo .parquet.")
        elif not selected_weeks:
            st.error("Por favor, selecione pelo menos uma semana.")
        else:
            with st.spinner("Iniciando processo de auditoria..."):
                try:
                    df_from_parquet = pd.read_parquet(uploaded_parquet)
                    if df_from_parquet.empty:
                        st.error("O arquivo Parquet está vazio.")
                    else:
                        sucesso, mensagem = analysis_service.criar_analise_comparativa(
                            bq_service, analysis_name, selected_weeks, df_from_parquet
                        )
                        if sucesso:
                            st.success(mensagem)
                            st.balloons()
                        else:
                            st.error(mensagem)
                except Exception as e:
                    st.error(f"Ocorreu um erro inesperado durante a auditoria: {e}")

st.markdown("---")

# --- Seção 2: Visualizar Relatórios de Auditoria Gerados ---
st.header("Visualizar Auditorias Salvas")

with st.spinner("Buscando auditorias existentes..."):
    analysis_tables = bq_service.list_analysis_tables()

if not analysis_tables:
    st.info("Nenhuma auditoria foi criada ainda.")
else:
    table_options = ["Selecione uma auditoria para visualizar..."] + sorted(analysis_tables)
    selected_table = st.selectbox("Auditorias Disponíveis:", options=table_options)

    if selected_table != "Selecione uma auditoria para visualizar...":
        with st.spinner(f"Gerando resumo para '{selected_table}'..."):
            audit_stats = bq_service.get_analysis_audit_stats(selected_table)

        if not audit_stats:
            st.warning("Não foi possível gerar o resumo para esta auditoria.")
        elif audit_stats.get("type") == "clean":
            st.subheader(f"Relatório: '{selected_table}'")
            st.success("🎉 Esta auditoria foi concluída sem nenhuma pendência.")
            st.dataframe(audit_stats.get("data"), use_container_width=True, hide_index=True)
        elif audit_stats.get("type") == "detailed":
            counts = audit_stats.get("counts", {})
            df_details = audit_stats.get("details", pd.DataFrame())
            st.subheader(f"Resumo das Pendências em '{selected_table}'")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Pendências", f"{counts.get('total_registros', 0):,}".replace(",", "."))
            col2.metric("Aulas sem Registro", f"{counts.get('total_sem_aula', 0):,}".replace(",", "."))
            col3.metric("Conteúdos sem Registro", f"{counts.get('total_sem_conteudo', 0):,}".replace(",", "."))

            if not df_details.empty:
                st.markdown("---")
                st.subheader("Detalhes das Pendências")
                csv_data = df_details.to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Baixar detalhes como CSV", data=csv_data, file_name=f"{selected_table}.csv",
                                   mime="text/csv", use_container_width=True)
                st.dataframe(df_details, use_container_width=True, hide_index=True)
            else:
                st.success("🎉 Todos os registros nesta auditoria estão completos.")
        else:
            st.warning("Formato de relatório de auditoria desconhecido.")