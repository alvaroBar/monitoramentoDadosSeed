# ==============================================================================
# ARQUIVO DA PÁGINA: p6_Auditoria_Comparativa.py
# Funcionalidade: Compara novos PDFs com dados históricos para gerar uma
# lista de pendências (registros ainda nulos).
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
# Importa a função de processamento de PDF da página 1
from pages.p1_Processar_Relatórios_PDF import processar_pdfs

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

# --- Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_auditoria")

creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id

st.info(
    "Esta ferramenta compara relatórios PDF atualizados com os dados históricos no BigQuery. "
    "Ela gera uma nova tabela contendo apenas os registros que **ainda possuem pendências** (aula ou conteúdo sem registro), "
    "facilitando a cobrança."
)

st.markdown("---")

# --- Secção 1: Criar uma Auditoria Comparativa ---
with st.expander("➕ Gerar Nova Auditoria de Pendências", expanded=True):
    with st.form("audit_form"):
        analysis_name = st.text_input(
            "Nome da Auditoria (ex: Verificação Bimestral Setembro)",
            placeholder="Digite um nome claro e descritivo"
        )

        st.write("Faça o upload dos arquivos PDF **atualizados** que você baixou do sistema.")
        col1, col2 = st.columns(2)
        with col1:
            uploaded_files = st.file_uploader(
                "1. Selecione os relatórios PDF atualizados",
                type="pdf",
                accept_multiple_files=True
            )
        with col2:
            disciplinas_file = st.file_uploader(
                "2. Selecione a planilha de disciplinas",
                type=["xlsx"]
            )

        st.write("Selecione as semanas no banco de dados que correspondem a estes relatórios.")
        with st.spinner("A carregar semanas disponíveis..."):
            available_weeks = get_available_weeks(creds, dataset_id)

        if not available_weeks:
            st.warning("Não há semanas disponíveis no histórico para comparar.")
            selected_weeks = []
        else:
            selected_weeks = st.multiselect(
                "3. Selecione as semanas do histórico para comparar:",
                options=available_weeks
            )

        submit_button = st.form_submit_button("Gerar Relatório de Pendências", use_container_width=True, type="primary")

    if submit_button:
        # Validação dos inputs
        if not analysis_name:
            st.error("Por favor, forneça um nome para a auditoria.")
        elif not uploaded_files:
            st.error("Por favor, carregue pelo menos um arquivo PDF.")
        elif not disciplinas_file:
            st.error("Por favor, carregue a planilha de disciplinas.")
        elif not selected_weeks:
            st.error("Por favor, selecione pelo menos uma semana para comparar.")
        else:
            with st.spinner("Iniciando processo de auditoria... Isso pode levar alguns minutos."):
                try:
                    # 1. Processar os PDFs para extrair os dados atualizados
                    st.write("Passo 1/4: Lendo e processando arquivos PDF...")
                    disciplinas_df = pd.read_excel(disciplinas_file)
                    lista_disciplinas_validas = [str(d).strip().upper() for d in
                                                 disciplinas_df.iloc[:, 0].dropna().unique()]

                    progress_bar = st.progress(0, text="Processando PDFs...")
                    status_text = st.empty()
                    df_dos_pdfs = processar_pdfs(uploaded_files, lista_disciplinas_validas, progress_bar, status_text)

                    if df_dos_pdfs.empty:
                        st.error("Nenhum dado válido foi extraído dos PDFs. Verifique os arquivos.")
                    else:
                        st.write("Passo 2/4: PDFs processados com sucesso!")
                        # 2. Chamar a função principal de comparação
                        st.write("Passo 3/4: Comparando com o BigQuery e gerando a tabela de pendências...")
                        sucesso, mensagem = criar_analise_comparativa(creds, dataset_id, analysis_name, selected_weeks, df_dos_pdfs)

                        st.write("Passo 4/4: Finalizado!")
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
    # Filtra para mostrar apenas as tabelas de auditoria
    audit_tables = sorted([t for t in analysis_tables if t.startswith('auditoria_')])


if not audit_tables:
    st.info("Ainda não há nenhuma auditoria criada. Gere uma acima para começar.")
else:
    table_options = ["Selecione uma auditoria para visualizar..."] + audit_tables
    selected_table = st.selectbox("Auditorias Disponíveis:", options=table_options)

    if selected_table != "Selecione uma auditoria para visualizar...":
        with st.spinner(f"A gerar resumo para a auditoria '{selected_table}'..."):
            audit_stats = get_analysis_audit_stats(creds, dataset_id, selected_table)

        if audit_stats:
            counts = audit_stats.get("counts", {})
            df_details = audit_stats.get("details", pd.DataFrame())

            st.subheader(f"Resumo das Pendências em '{selected_table}'")

            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Registros Pendentes", f"{counts.get('total_registros', 0):,}".replace(",", "."))
            col2.metric("Aulas sem Registro", f"{counts.get('total_sem_aula', 0):,}".replace(",", "."))
            col3.metric("Conteúdos sem Registro", f"{counts.get('total_sem_conteudo', 0):,}".replace(",", "."))

            st.markdown("---")

            st.subheader("Detalhes das Pendências (por Escola e Disciplina)")
            if not df_details.empty:
                csv_data = df_details.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Baixar detalhes da auditoria como CSV",
                    data=csv_data,
                    file_name=f"{selected_table}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.dataframe(df_details, use_container_width=True)
            else:
                st.success("🎉 Não foram encontrados registros com pendências nesta auditoria.")
        else:
            st.warning("Não foi possível gerar o resumo para esta auditoria.")