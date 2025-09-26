# ==============================================================================
# ARQUIVO DA PÁGINA: p7_Auditoria_Comparativa.py
# VERSÃO REVISADA: Adicionada exportação para Excel com auto-ajuste de colunas.
# ==============================================================================

import streamlit as st
import pandas as pd
import io
from openpyxl.utils import get_column_letter
from streamlit_autorefresh import st_autorefresh
from services import auth_service
from services.bigquery_service import BigQueryService
from services import analysis_service

st.set_page_config(layout="wide")
st.title("Auditoria e Validação 🔬")

# --- Bloco de Inicialização Padrão ---
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
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado.");
        st.stop()
except (AttributeError, KeyError):
    st.error("ERRO DE CONFIGURAÇÃO: O mapeamento [office_mapping] não foi encontrado.");
    st.stop()

if 'bq_service' not in st.session_state:
    st.session_state.bq_service = BigQueryService(
        credentials=st.session_state.credentials,
        dataset_id=st.session_state.dataset_id
    )
bq_service = st.session_state.bq_service
st_autorefresh(interval=10 * 60 * 1000, key="session_refresher_auditoria")


# --- FUNÇÃO AUXILIAR REUTILIZÁVEL PARA EXCEL ---
def to_excel_auto_width(df_styled):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    # Escreve o DataFrame com a formatação de cores para a planilha
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


# --- Seção de Geração de Análise ---
st.info(
    "**Fluxo de Trabalho:**\n"
    "1. Na página `p1`, processe os PDFs e baixe o arquivo `.parquet`.\n"
    "2. Volte aqui, escolha o tipo de análise, faça o upload do arquivo, selecione as semanas e gere o relatório."
)
st.markdown("---")

with st.expander("➕ Gerar Nova Análise", expanded=True):
    # ... (código para os inputs da análise permanece o mesmo) ...
    tipo_auditoria = st.radio(
        "1. Escolha o tipo de análise:",
        options=["Análise de Pendências Históricas (Salva Relatório)", "Validação de Lançamentos (Análise Rápida)"],
        horizontal=True,
    )
    analysis_name = st.text_input("2. Dê um nome para a análise (obrigatório para salvar relatório)",
                                  placeholder="Ex: Verificação Semanas 30-35")
    uploaded_parquet = st.file_uploader("3. Carregue o arquivo `dados_extraidos.parquet`", type=["parquet"])
    st.write("4. Selecione as semanas do histórico para comparar.")
    with st.spinner("Carregando semanas disponíveis..."):
        available_weeks = bq_service.get_available_weeks()
    selected_weeks = st.multiselect("Semanas:", options=available_weeks if available_weeks else [])

    if st.button("Executar Análise", use_container_width=True, type="primary"):
        # ... (lógica de execução da análise permanece a mesma) ...
        if 'validation_results' in st.session_state:
            del st.session_state.validation_results
        if not uploaded_parquet:
            st.error("Por favor, carregue o arquivo .parquet.")
        elif not selected_weeks:
            st.error("Por favor, selecione pelo menos uma semana.")
        else:
            with st.spinner("Processando..."):
                try:
                    df_from_parquet = pd.read_parquet(uploaded_parquet)
                    if df_from_parquet.empty:
                        st.error("O arquivo Parquet está vazio.")
                    else:
                        if tipo_auditoria == "Análise de Pendências Históricas (Salva Relatório)":
                            if not analysis_name:
                                st.error("O nome da análise é obrigatório para salvar o relatório.")
                            else:
                                sucesso, mensagem = analysis_service.criar_analise_comparativa(bq_service,
                                                                                               analysis_name,
                                                                                               selected_weeks,
                                                                                               df_from_parquet)
                                if sucesso:
                                    st.success(mensagem);
                                    st.balloons()
                                else:
                                    st.error(mensagem)
                        elif tipo_auditoria == "Validação de Lançamentos (Análise Rápida)":
                            sucesso, resultados = analysis_service.executar_validacao_de_lancamentos(bq_service,
                                                                                                     selected_weeks,
                                                                                                     df_from_parquet)
                            if sucesso:
                                st.session_state.validation_results = resultados
                            else:
                                st.error(resultados)
                except Exception as e:
                    st.error(f"Ocorreu um erro inesperado: {e}")

# --- Seção de Resultados da Validação Rápida ---
if 'validation_results' in st.session_state:
    st.markdown("---")
    st.header("Resultados da Validação de Lançamentos")
    resultados = st.session_state.validation_results
    escolas_auditadas = resultados.get("escolas_auditadas", [])
    with st.expander(f"Análise focada em {len(escolas_auditadas)} escola(s). Clique para ver a lista."):
        for escola in escolas_auditadas:
            st.write(f"- {escola}")
    col1, col2 = st.columns(2)
    col1.metric("Registros Correspondentes (Matches)", resultados.get("total_matches", 0))
    col2.metric("Registros Corrigidos (Nulos Preenchidos)", resultados.get("nulos_preenchidos", 0))
    df_pendencias = resultados.get("pendencias_restantes", pd.DataFrame())
    st.subheader(f"Pendências Restantes ({len(df_pendencias)})")

    if not df_pendencias.empty:
        df_for_display = df_pendencias.copy()


        def formatar_e_preencher_validacao(valor):
            if pd.isna(valor): return "Sem registro"
            return pd.to_datetime(valor).tz_localize(None).strftime('%d/%m/%Y %H:%M:%S')


        for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
            df_for_display[col] = df_for_display[col].apply(formatar_e_preencher_validacao)


        def highlight_sem_registro_validacao(cell_value):
            return 'color: red' if cell_value == "Sem registro" else ''


        styled_df_validacao = df_for_display.style.applymap(highlight_sem_registro_validacao,
                                                            subset=['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO'])

        # ALTERADO: Botão de download para Excel
        excel_data_validacao = to_excel_auto_width(styled_df_validacao)
        st.download_button("📥 Baixar Pendências como Excel (.xlsx)", excel_data_validacao, "pendencias_restantes.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

        st.dataframe(styled_df_validacao, use_container_width=True, hide_index=True,
                     column_config={"DATA_DO_RELATORIO": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                    "HORARIO": st.column_config.TimeColumn("Horário", format="HH:mm")})
    else:
        st.success("🎉 Nenhuma pendência restante encontrada para as escolas do arquivo analisado!")
    if st.button("Limpar Resultados da Validação"):
        del st.session_state.validation_results
        st.rerun()

# --- Seção de Visualização de Relatórios Salvos ---
st.markdown("---")
st.header("Visualizar Relatórios de Pendências Salvas")
with st.spinner("Buscando auditorias existentes..."):
    analysis_tables = bq_service.list_analysis_tables()
if not analysis_tables:
    st.info("Nenhuma auditoria salva foi criada ainda.")
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

                df_for_display_saved = df_details.copy()


                def formatar_e_preencher_saved(valor):
                    if pd.isna(valor): return "Sem registro"
                    return pd.to_datetime(valor).tz_localize(None).strftime('%d/%m/%Y %H:%M:%S')


                for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
                    df_for_display_saved[col] = df_for_display_saved[col].apply(formatar_e_preencher_saved)


                def highlight_sem_registro_saved(cell_value):
                    return 'color: red' if cell_value == "Sem registro" else ''


                styled_df_saved = df_for_display_saved.style.applymap(highlight_sem_registro_saved,
                                                                      subset=['REGISTRO_DE_AULA',
                                                                              'REGISTRO_DE_CONTEUDO'])

                # ALTERADO: Botão de download para Excel
                excel_data_saved = to_excel_auto_width(styled_df_saved)
                st.download_button(label="📥 Baixar detalhes como Excel (.xlsx)", data=excel_data_saved,
                                   file_name=f"{selected_table}_detalhes.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   use_container_width=True)

                st.dataframe(styled_df_saved, use_container_width=True, hide_index=True, column_config={
                    "DATA_DO_RELATORIO": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "HORARIO": st.column_config.TimeColumn("Horário", format="HH:mm")})
            else:
                st.success("🎉 Todos os registros nesta auditoria estão completos.")
        else:
            st.warning("Formato de relatório de auditoria desconhecido.")