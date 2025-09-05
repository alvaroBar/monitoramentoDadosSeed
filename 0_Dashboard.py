import streamlit as st
import pandas as pd
from bigquery_loader import autenticar_usuario, get_dashboard_stats
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Dashboard de Relatórios",
    layout="wide"
)

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

# --- ALTERAÇÃO APLICADA AQUI: Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_processar")

# --- Conteúdo do Dashboard ---

st.title("📊 Dashboard de Relatórios LRCO")
st.markdown(
    f"Bem-vindo(a)! Estes são os dados atuais para o seu escritório (Dataset: `{st.session_state.dataset_id}`).")

# Busca os dados para o dashboard
creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

with st.spinner("Carregando estatísticas..."):
    stats = get_dashboard_stats(creds, dataset_id)

if stats:
    st.markdown("---")

    # --- Métricas Principais ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Registros", f"{stats.get('total_registros', 0):,}".replace(",", "."))
    col2.metric("Total de Semanas Lançadas", stats.get('total_semanas', 0))

    # Formata a data para o padrão brasileiro
    ultima_data_str = "N/A"
    ultima_data_val = stats.get('ultima_data')
    if pd.notna(ultima_data_val):
        ultima_data_str = pd.to_datetime(ultima_data_val).strftime('%d/%m/%Y')
    col3.metric("Último Relatório Recebido", ultima_data_str)

    st.markdown("---")

    # --- Gráficos ---
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Registros por Semana")
        df_registros_semana = stats.get("registros_por_semana")
        if df_registros_semana is not None and not df_registros_semana.empty:
            st.bar_chart(df_registros_semana)
        else:
            st.info("Não há dados de registros por semana para exibir.")

    with col_chart2:
        st.subheader("Top 5 Disciplinas com Mais Lançamentos")
        df_top_disciplinas = stats.get("top_disciplinas")
        if df_top_disciplinas is not None and not df_top_disciplinas.empty:
            st.dataframe(df_top_disciplinas, use_container_width=True, hide_index=True)
        else:
            st.info("Não há dados de disciplinas para exibir.")

else:
    st.info("Ainda não há dados lançados para este escritório.")