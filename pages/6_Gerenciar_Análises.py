# ==============================================================================
# ARQUIVO DA PÁGINA: 6_Gerenciar_Análises.py
# Transformada em uma página de auditoria que exibe estatísticas de dados nulos.
# ==============================================================================

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import (
    autenticar_usuario,
    get_available_weeks,
    list_analysis_tables,
    create_or_update_analysis,
    get_analysis_audit_stats  # Nova função importada
)

st.set_page_config(layout="wide")
st.title("Auditoria de Análises de Dados 📋")

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
    "Use esta página para criar 'fotografias' dos seus dados para períodos específicos e depois gerar relatórios de auditoria sobre elas, "
    "identificando registros com informações em falta."
)

st.markdown("---")

# --- Secção 1: Criar ou Atualizar uma Análise ---
with st.expander("➕ Criar / Atualizar uma Tabela de Análise", expanded=True):
    with st.form("analysis_form"):
        analysis_name = st.text_input(
            "Nome da Análise (ex: Primeiro Bimestre 2025)",
            placeholder="Digite um nome claro e descritivo"
        )

        with st.spinner("A carregar semanas disponíveis..."):
            available_weeks = get_available_weeks(creds, dataset_id)

        if not available_weeks:
            st.warning("Não há semanas disponíveis na tabela de dados históricos para criar uma análise.")
            selected_weeks = []
        else:
            selected_weeks = st.multiselect(
                "Selecione as semanas para incluir nesta análise:",
                options=available_weeks,
                default=[]
            )

        submit_button = st.form_submit_button("Salvar Tabela de Análise", use_container_width=True, type="primary")

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

# --- Secção 2: Gerar Relatório de Auditoria ---
st.header("Gerar Relatório de Auditoria")

with st.spinner("A buscar análises existentes..."):
    analysis_tables = list_analysis_tables(creds, dataset_id)

if not analysis_tables:
    st.info("Ainda não há nenhuma tabela de análise criada. Crie uma acima para começar.")
else:
    table_options = ["Selecione uma análise para auditar..."] + sorted(analysis_tables)
    selected_table = st.selectbox("Análises Disponíveis:", options=table_options)

    if selected_table != "Selecione uma análise para auditar...":
        with st.spinner(f"A gerar relatório para a análise '{selected_table}'..."):
            audit_stats = get_analysis_audit_stats(creds, dataset_id, selected_table)

        if audit_stats:
            counts = audit_stats.get("counts", {})
            df_details = audit_stats.get("details", pd.DataFrame())

            st.subheader(f"Resultados da Auditoria para '{selected_table}'")

            # Exibe as métricas principais
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Registros na Análise", f"{counts.get('total_registros', 0):,}".replace(",", "."))
            col2.metric("Aulas sem Registro", f"{counts.get('total_sem_aula', 0):,}".replace(",", "."))
            col3.metric("Conteúdos sem Registro", f"{counts.get('total_sem_conteudo', 0):,}".replace(",", "."))

            st.markdown("---")

            # Exibe os detalhes
            st.subheader("Detalhes dos Registros em Falta (por Escola e Disciplina)")

            if not df_details.empty:
                # Oferece o download dos detalhes da auditoria
                csv_data = df_details.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Baixar detalhes da auditoria como CSV",
                    data=csv_data,
                    file_name=f"auditoria_{selected_table}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.dataframe(df_details, use_container_width=True)
            else:
                st.success("🎉 Não foram encontrados registros com aulas ou conteúdos em falta nesta análise.")
        else:
            st.warning("Não foi possível gerar o relatório de auditoria para esta análise.")

