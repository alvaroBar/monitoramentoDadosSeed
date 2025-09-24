# ==============================================================================
# ARQUIVO DA PÁGINA: 5_Manutencao_de_Dados.py
# VERSÃO REVISADA: Bug crítico corrigido e arquitetura padronizada.
# ==============================================================================

import streamlit as st
import pandas as pd
from services import auth_service
from services.bigquery_service import BigQueryService
from utils.dataframe_utils import preparar_dataframe_para_bigquery
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")
st.title("⚙️ Manutenção de Dados")

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
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado.")
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
st_autorefresh(interval=10 * 60 * 1000, key="session_refresher_manutencao")

# --- Lógica da Página ---
st.warning("Atenção: As operações nesta página modificam permanentemente o banco de dados.")

try:
    with st.spinner("Buscando semanas disponíveis..."):
        available_weeks = bq_service.get_available_weeks()
except Exception as e:
    st.error(f"Não foi possível buscar as semanas do BigQuery. Erro: {e}")
    available_weeks = []  # Garante que a lista exista para evitar outros erros

# --- Seção 1: Apagar Dados de uma Semana ---
st.markdown("---")
with st.expander("Apagar Dados de uma Semana Inteira", expanded=True):
    if not available_weeks:
        st.info("Não há semanas com dados para apagar.")
    else:
        week_to_delete = st.selectbox(
            "Selecione a semana que deseja apagar:",
            options=available_weeks,
            index=None,
            placeholder="Escolha uma semana..."
        )

        if week_to_delete:
            st.error(
                f"Você está prestes a apagar todos os registros da Semana {week_to_delete}. Esta ação não pode ser desfeita.")
            if st.checkbox(f"Confirmo que desejo apagar os dados da Semana {week_to_delete}."):
                if st.button("Apagar Semana", type="primary"):
                    with st.spinner(f"Apagando dados da Semana {week_to_delete}..."):
                        success, message = bq_service.delete_week_data(week_to_delete)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

# --- Seção 2: Sobrescrever Dados de uma Semana ---
st.markdown("---")
with st.expander("Sobrescrever Dados de uma Semana com um Arquivo CSV"):
    st.info(
        "Esta operação irá primeiro apagar todos os dados da semana selecionada e depois carregar os novos dados do arquivo.")

    csv_file = st.file_uploader("Selecione o arquivo CSV", type="csv")
    week_to_overwrite = st.number_input(
        "Digite o número da semana para sobrescrever:",
        min_value=1,
        step=1,
        value=None
    )

    if csv_file and week_to_overwrite:
        if st.button(f"Sobrescrever Semana {week_to_overwrite}", type="primary"):
            with st.spinner(f"Iniciando a substituição da Semana {week_to_overwrite}..."):
                st.write(f"Passo 1/3: Apagando dados existentes da Semana {week_to_overwrite}...")

                # BUG CORRIGIDO AQUI: Usando a variável correta 'week_to_overwrite'
                delete_success, delete_message = bq_service.delete_week_data(week_to_overwrite)

                if delete_success:
                    st.write(f"-> {delete_message}")
                    st.write("Passo 2/3: Lendo e preparando os novos dados...")
                    try:
                        df_new_data = pd.read_csv(csv_file)
                        df_new_data.columns = [col.strip().upper().replace(' ', '_') for col in df_new_data.columns]
                        df_new_data['SEMANA'] = week_to_overwrite
                        st.write(f"-> {len(df_new_data)} novas linhas lidas.")

                        st.write("Passo 3/3: Carregando os novos dados no BigQuery...")
                        df_preparado = preparar_dataframe_para_bigquery(df_new_data)
                        load_success = bq_service.carregar_dados(df_preparado, mode='append')

                        if load_success:
                            st.success(
                                f"Operação concluída! Os dados da Semana {week_to_overwrite} foram substituídos.")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("A carga dos novos dados falhou. A semana pode estar vazia no banco de dados.")
                    except Exception as e:
                        st.error(f"Erro ao ler ou processar o arquivo CSV: {e}")
                else:
                    st.error(f"A operação falhou na etapa de exclusão: {delete_message}")