# ==============================================================================
# ARQUIVO DA PÁGINA PRINCIPAL: 0_Dashboard.py
# O estilo foi aprimorado para corresponder ao layout de exemplo.
# ==============================================================================

import streamlit as st
import pandas as pd
from bigquery_loader import autenticar_usuario, get_dashboard_stats
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Dashboard de Acompanhamento",
    layout="wide"
)

# --- CSS customizado para os cartões de métrica ---
# Este bloco de código injeta CSS para estilizar os nossos cartões de métrica
# para que se pareçam com o exemplo, com um fundo escuro e bordas.
st.markdown("""
<style>
.metric-card {
    background-color: #262730; /* Cor de fundo escura */
    border-radius: 10px;
    padding: 20px;
    margin: 10px 0;
    border: 1px solid #3c3f4b;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    text-align: center;
    height: 150px; /* Garante que todos os cartões tenham a mesma altura */
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.metric-card p {
    margin: 0;
    font-size: 1.1em;
    color: #a0a4b8; /* Cor do rótulo */
}
.metric-card h2 {
    margin: 5px 0 0 0;
    font-size: 2.5em;
    color: #ffffff; /* Cor do valor */
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# --- Autenticação e Lógica de Mapeamento ---
autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# Visível apenas após o login
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
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_dashboard")

# --- Conteúdo do Dashboard ---

st.title("Dashboard de Acompanhamento LRCO")
st.markdown(f"Visão geral dos dados para o seu escritório (Dataset: `{st.session_state.dataset_id}`).")

# Busca os dados para o dashboard
creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

with st.spinner("A carregar estatísticas..."):
    stats = get_dashboard_stats(creds, dataset_id)

if stats:
    st.markdown("---")

    # --- ALTERAÇÃO APLICADA AQUI: Métricas exibidas como cartões estilizados ---
    total_registros = stats.get('total_registros', 0)
    total_semanas = stats.get('total_semanas', 0)
    sem_registro_aula = stats.get('sem_registro_aula', 0)
    sem_registro_conteudo = stats.get('sem_registro_conteudo', 0)

    ultima_data_str = "N/A"
    ultima_data_val = stats.get('ultima_data')
    if pd.notna(ultima_data_val):
        ultima_data_str = pd.to_datetime(ultima_data_val).strftime('%d/%m/%Y')

    # Cria 5 colunas para as 5 métricas
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <p>Total de Registros</p>
            <h2>{total_registros:,}</h2>
        </div>
        """.replace(",", "."), unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <p>Semanas Lançadas</p>
            <h2>{total_semanas}</h2>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <p>Último Lançamento</p>
            <h2>{ultima_data_str}</h2>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <p>Aulas sem Registro</p>
            <h2>{sem_registro_aula:,}</h2>
        </div>
        """.replace(",", "."), unsafe_allow_html=True)

    with col5:
        st.markdown(f"""
        <div class="metric-card">
            <p>Conteúdos sem Registro</p>
            <h2>{sem_registro_conteudo:,}</h2>
        </div>
        """.replace(",", "."), unsafe_allow_html=True)


    st.markdown("---")

    # --- Gráficos ---
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Lançamentos por Semana")
        df_registros_semana = stats.get("registros_por_semana")
        if df_registros_semana is not None and not df_registros_semana.empty:
            st.bar_chart(df_registros_semana)
        else:
            st.info("Não há dados de registros por semana para exibir.")

    with col_chart2:
        st.subheader("Disciplinas com mais Lançamentos")
        df_top_disciplinas = stats.get("top_disciplinas")
        if df_top_disciplinas is not None and not df_top_disciplinas.empty:
            st.dataframe(df_top_disciplinas, use_container_width=True, hide_index=True)
        else:
            st.info("Não há dados de disciplinas para exibir.")

else:
    st.info("Ainda não há dados lançados para este escritório.")

