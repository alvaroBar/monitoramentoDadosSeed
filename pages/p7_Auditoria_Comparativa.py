# ==============================================================================
# ARQUIVO DA PÁGINA: p7_Auditoria_Comparativa.py
# CORRIGIDO: Seção de visualização agora é capaz de exibir tanto relatórios
# com pendências quanto relatórios "limpos" (sem pendências).
# ==============================================================================

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# Importa as funções necessárias
from bigquery_loader import (
    autenticar_usuario,
    get_available_weeks,
    criar_analise_comparativa,
    list_analysis_tables,
    get_analysis_audit_stats
)

st.set_page_config(layout="wide")
st.title("Auditoria Comparativa de Pendências 🔍")

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
    if st.button("Logout", key="logout_auditoria"):
        st.session_state.clear()
        st.rerun()

st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_auditoria")

creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

st.info(
    "**Fluxo de Trabalho de Auditoria:**\n\n"
    "1. **Vá para a página `p1_Extrair_Dados_PDF`:** Processe os novos relatórios PDF e baixe o arquivo `dados_extraidos.parquet`.\n\n"
    "2. **Volte para esta página:** Faça o upload do arquivo `.parquet` que você acabou de baixar, selecione as semanas e gere o relatório de pendências."
)

st.markdown("---")

# --- Secção 1: Criar uma Auditoria Comparativa ---
with st.expander("➕ Gerar Nova Auditoria de Pendências", expanded=True):
    analysis_name = st.text_input(
        "1. Dê um nome para a Auditoria (ex: Verificação Semanas 30-35)",
        placeholder="Digite um nome claro e descritivo"
    )

    uploaded_parquet = st.file_uploader(
        "2. Carregue o arquivo `dados_extraidos.parquet` com os dados atualizados",
        type=["parquet"]
    )

    st.write("3. Selecione as semanas no banco de dados que correspondem a estes relatórios.")
    with st.spinner("A carregar semanas disponíveis..."):
        available_weeks = get_available_weeks(creds, dataset_id)

    if not available_weeks:
        st.warning("Não há semanas disponíveis no histórico para comparar.")
        selected_weeks = []
    else:
        selected_weeks = st.multiselect(
            "Semanas do histórico para comparar:",
            options=available_weeks
        )

    st.markdown("---")

    if st.button("Gerar Relatório de Pendências", use_container_width=True, type="primary"):
        # Validação dos inputs
        if not analysis_name:
            st.error("Por favor, forneça um nome para a auditoria.")
        elif not uploaded_parquet:
            st.error("Por favor, carregue o arquivo .parquet gerado na página de extração.")
        elif not selected_weeks:
            st.error("Por favor, selecione pelo menos uma semana para comparar.")
        else:
            with st.spinner("Iniciando processo de auditoria..."):
                try:
                    df_from_parquet = pd.read_parquet(uploaded_parquet)

                    if df_from_parquet.empty:
                        st.error("O arquivo Parquet está vazio ou corrompido.")
                    else:
                        sucesso, mensagem = criar_analise_comparativa(creds, dataset_id, analysis_name, selected_weeks,
                                                                      df_from_parquet)
                        if sucesso:
                            st.success(mensagem)
                            st.balloons()
                        else:
                            st.error(mensagem)
                except Exception as e:
                    st.error(f"Ocorreu um erro inesperado durante a auditoria: {e}")

st.markdown("---")

# --- Secção 2: Visualizar Relatórios de Auditoria Gerados ---
st.header("Visualizar Auditorias Salvas")

with st.spinner("A buscar auditorias existentes..."):
    analysis_tables = list_analysis_tables(creds, dataset_id)

if not analysis_tables:
    st.info("Ainda não há nenhuma auditoria criada. Gere uma acima para começar.")
else:
    table_options = ["Selecione uma auditoria para visualizar..."] + sorted(analysis_tables)
    selected_table = st.selectbox("Auditorias Disponíveis:", options=table_options)

    if selected_table != "Selecione uma auditoria para visualizar...":
        with st.spinner(f"A gerar resumo para a auditoria '{selected_table}'..."):
            audit_stats = get_analysis_audit_stats(creds, dataset_id, selected_table)

        if not audit_stats:
            st.warning("Não foi possível gerar o resumo para esta auditoria.")

        # --- LÓGICA DE EXIBIÇÃO ATUALIZADA ---
        elif audit_stats.get("type") == "clean":
            st.subheader(f"Relatório da Auditoria '{selected_table}'")
            st.success("🎉 Esta auditoria foi concluída sem nenhuma pendência encontrada.")
            st.dataframe(audit_stats.get("data"), use_container_width=True, hide_index=True)

        elif audit_stats.get("type") == "detailed":
            counts = audit_stats.get("counts", {})
            df_details = audit_stats.get("details", pd.DataFrame())

            st.subheader(f"Resumo das Pendências em '{selected_table}'")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Registros Pendentes", f"{counts.get('total_registros', 0):,}".replace(",", "."))
            col2.metric("Aulas sem Registro", f"{counts.get('total_sem_aula', 0):,}".replace(",", "."))
            col3.metric("Conteúdos sem Registro", f"{counts.get('total_sem_conteudo', 0):,}".replace(",", "."))

            st.markdown("---")
            st.subheader("Detalhes das Pendências (por Escola, Disciplina e Turma)")

            if not df_details.empty:
                csv_data = df_details.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Baixar detalhes da auditoria como CSV",
                    data=csv_data,
                    file_name=f"{selected_table}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.dataframe(df_details, use_container_width=True, hide_index=True)
            else:
                # Este caso pode ocorrer se a tabela existir mas os detalhes estiverem vazios
                st.success("🎉 Não foram encontrados registros com pendências nesta auditoria.")

        else:
            st.warning("Formato de relatório de auditoria desconhecido.")