# ==============================================================================
# ARQUIVO DA PÁGINA PRINCIPAL: app.py
# Versão final e unificada.
# ==============================================================================

import streamlit as st
import pandas as pd
from services import auth_service
from services.bigquery_service import BigQueryService
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Dashboard")

# --- CSS customizado para os cartões de métrica ---
st.markdown("""
<style>
.metric-card {
    background-color: #262730;
    border-radius: 10px;
    padding: 20px;
    margin: 10px 0;
    border: 1px solid #3c3f4b;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    text-align: center;
    height: 150px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.metric-card p {
    margin: 0;
    font-size: 1.1em;
    color: #a0a4b8;
}
.metric-card h2 {
    margin: 5px 0 0 0;
    font-size: 2.5em;
    color: #ffffff;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# 1. Autenticação
auth_service.autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# 2. Lógica de Mapeamento do Usuário para o Dataset
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
        "ERRO DE CONFIGURAÇÃO: O mapeamento [office_mapping] não foi encontrado nos Segredos do Streamlit.")
    st.stop()

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout"):
        auth_service.logout_usuario()

# --- Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_dashboard")

# 3. Inicialização do Serviço do BigQuery
if 'bq_service' not in st.session_state:
    st.session_state.bq_service = BigQueryService(
        credentials=st.session_state.credentials,
        dataset_id=st.session_state.dataset_id
    )
bq_service = st.session_state.bq_service

# app.py -> trecho de código do conteúdo do dashboard

# --- Conteúdo do Dashboard ---
st.markdown(f"Visão geral dos dados para o seu escritório (Dataset: `{st.session_state.dataset_id}`).")

with st.spinner("A carregar estatísticas..."):
    stats = bq_service.get_dashboard_stats()

if stats and stats.get('total_registros', 0) > 0:
    st.markdown("---")

    # --- NOVOS KPIs ---
    total_registros = stats.get('total_registros', 0)
    sem_registro_aula = stats.get('sem_registro_aula', 0)
    sem_registro_conteudo = stats.get('sem_registro_conteudo', 0)

    # Calcula as taxas de adesão
    taxa_adesao_aula = ((total_registros - sem_registro_aula) / total_registros) * 100 if total_registros > 0 else 0
    taxa_adesao_conteudo = ((
                                        total_registros - sem_registro_conteudo) / total_registros) * 100 if total_registros > 0 else 0

    # Busca o número de escolas com problemas
    df_escolas_pendentes = stats.get("escolas_com_pendencias")
    num_escolas_pendentes = len(df_escolas_pendentes) if df_escolas_pendentes is not None else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Total de Registros", value=f"{total_registros:,}".replace(",", "."))
    with col2:
        st.metric(label="Adesão de Aulas", value=f"{taxa_adesao_aula:.1f}%",
                  help="Percentual de registros de aulas preenchidos.")
    with col3:
        st.metric(label="Adesão de Conteúdos", value=f"{taxa_adesao_conteudo:.1f}%",
                  help="Percentual de registros de conteúdos preenchidos.")
    with col4:
        st.metric(label="Escolas com Pendências", value=num_escolas_pendentes,
                  help="Número de escolas com pelo menos um registro de aula ou conteúdo faltando.")

    st.markdown("---")

    # --- NOVOS GRÁFICOS E TABELAS ACIONÁVEIS ---
    st.header("Análises de Pendências")

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Top 5 Escolas com Mais Pendências")
        if df_escolas_pendentes is not None and not df_escolas_pendentes.empty:
            st.dataframe(df_escolas_pendentes, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma escola com pendências encontrada.")

    with col_chart2:
        st.subheader("Pendências por Município")
        df_municipios_pendentes = stats.get("pendencias_por_municipio")
        if df_municipios_pendentes is not None and not df_municipios_pendentes.empty:
            st.bar_chart(df_municipios_pendentes.set_index("MUNICIPIO"))
        else:
            st.info("Nenhum município com pendências encontrado.")

    st.markdown("---")

    # --- GRÁFICOS ORIGINAIS ---
    st.header("Análises Gerais")
    col_geral1, col_geral2 = st.columns(2)

    with col_geral1:
        st.subheader("Lançamentos por Semana")
        df_registros_semana = stats.get("registros_por_semana")
        if df_registros_semana is not None and not df_registros_semana.empty:
            st.bar_chart(df_registros_semana)
        else:
            st.info("Não há dados de registros por semana para exibir.")

    with col_geral2:
        st.subheader("Disciplinas com mais Lançamentos")
        df_top_disciplinas = stats.get("top_disciplinas")
        if df_top_disciplinas is not None and not df_top_disciplinas.empty:
            st.dataframe(df_top_disciplinas, use_container_width=True, hide_index=True)
        else:
            st.info("Não há dados de disciplinas para exibir.")
else:
    st.info("Ainda não há dados lançados para este escritório.")