import streamlit as st
import pandas as pd
from bigquery_loader import (
    autenticar_usuario,
    get_available_weeks,
    delete_week_data,
    carregar_dados_no_bigquery
)

from streamlit_autorefresh import st_autorefresh

# --- Lógica de Autenticação e Mapeamento ---
autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

if 'dataset_id' not in st.session_state or st.session_state.dataset_id is None:
    try:
        user_email = st.session_state.user_info.get("email")
        office_map = st.secrets.get("office_mapping", {})
        if user_email in office_map:
            st.session_state.dataset_id = office_map[user_email]
        else:
            st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador para obter acesso.")
            st.stop()
    except Exception as e:
        st.error(f"Erro ao obter o mapeamento do escritório: {e}")
        st.stop()

# --- Conteúdo da Página ---
creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

with st.sidebar:
    st.header("Usuário Autenticado")
    user_name = st.session_state.user_info.get("name", "N/A")
    st.write(f"Olá, **{user_name}**")
    if st.button("Logout", key="logout_Manutencao_de_Dados"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()



st.title("⚙️ Manutenção de Dados")
st.warning("Atenção: As operações nesta página modificam permanentemente o banco de dados.")

with st.spinner("A buscar semanas disponíveis..."):
    available_weeks = get_available_weeks(creds, dataset_id)

# --- Secção 1: Apagar Dados de uma Semana ---
st.markdown("---")
with st.expander("Apagar Dados de uma Semana Inteira", expanded=False):
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
                f"Você está prestes a apagar todos os registos da **Semana {week_to_delete}**. Esta ação não pode ser desfeita.")
            if st.checkbox(f"Confirmo que desejo apagar permanentemente os dados da Semana {week_to_delete}."):
                if st.button("Apagar Semana", type="primary"):
                    with st.spinner(f"A apagar dados da Semana {week_to_delete}..."):
                        success, message = delete_week_data(creds, dataset_id, week_to_delete)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

# --- Secção 2: Sobrescrever Dados de uma Semana ---
st.markdown("---")
with st.expander("Sobrescrever Dados de uma Semana com um Ficheiro CSV", expanded=False):
    st.info(
        "Esta operação irá primeiro apagar todos os dados da semana selecionada e depois carregar os novos dados do ficheiro CSV.")

    csv_file = st.file_uploader("Selecione o ficheiro CSV com os dados da semana", type="csv")
    week_to_overwrite = st.number_input(
        "Digite o número da semana que estes dados irão sobrescrever:",
        min_value=1,
        step=1,
        value=None
    )

    if csv_file and week_to_overwrite:
        if st.button(f"Sobrescrever Semana {week_to_overwrite}", type="primary"):
            with st.spinner(f"A iniciar a substituição dos dados da Semana {week_to_overwrite}..."):
                # Passo 1: Apagar dados existentes
                st.write(f"Passo 1/3: A apagar dados existentes da Semana {week_to_overwrite}...")
                delete_success, delete_message = delete_week_data(creds, dataset_id, week_to_overwrite)

                if delete_success:
                    st.write(f"-> {delete_message}")

                    # Passo 2: Ler e preparar novos dados
                    st.write("Passo 2/3: A ler e a preparar os novos dados do ficheiro CSV...")
                    try:
                        df_new_data = pd.read_csv(csv_file)

                        # Limpa os nomes das colunas
                        df_new_data.columns = [col.strip().upper().replace(' ', '_') for col in df_new_data.columns]

                        # Define o número da semana para todas as linhas
                        df_new_data['SEMANA'] = week_to_overwrite

                        st.write(f"-> {len(df_new_data)} novas linhas lidas do ficheiro.")

                        # Passo 3: Carregar os novos dados
                        st.write("Passo 3/3: A carregar os novos dados no BigQuery...")
                        load_success = carregar_dados_no_bigquery(df_new_data, creds, dataset_id, mode='append')

                        if load_success:
                            st.success(
                                f"Operação concluída! Os dados da Semana {week_to_overwrite} foram substituídos com sucesso.")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error(
                                "A carga dos novos dados falhou. A semana pode estar vazia no banco de dados. Verifique os logs de erro acima.")

                    except Exception as e:
                        st.error(f"Erro ao ler ou processar o ficheiro CSV: {e}")
                else:
                    st.error(f"A operação falhou na etapa de exclusão: {delete_message}")