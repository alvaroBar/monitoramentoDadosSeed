# ==============================================================================
# ARQUIVO DA PÁGINA: p7_Auditoria_Comparativa.py
# VERSÃO REVISADA: Corrigido o AttributeError na função to_excel_auto_width.
# ==============================================================================

import streamlit as st
import pandas as pd
import io
import time
from openpyxl.utils import get_column_letter
from streamlit_autorefresh import st_autorefresh
from services import auth_service
from services.bigquery_service import BigQueryService
from services import analysis_service
from google.cloud import bigquery
from utils import interface

st.set_page_config(layout="wide")
st.title("Auditoria e Validação 🔬")
interface.exibir_cabecalho_ano()

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


# --- FUNÇÕES AUXILIARES GLOBAIS ---

# --- FUNÇÃO CORRIGIDA ---
def to_excel_auto_width(df_or_styler):
    """Converte um DataFrame ou Styler para Excel com auto-ajuste de colunas."""
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')

    # Lógica de extração do DataFrame mais segura
    if hasattr(df_or_styler, 'data'):
        # Provavelmente é um objeto Styler, pega o DataFrame interno
        df_data = df_or_styler.data
    else:
        # Assume que já é um DataFrame
        df_data = df_or_styler

    df_data.to_excel(writer, index=False, sheet_name='Resultados')
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


def formatar_valor(valor):
    """Formata valores de data/hora ou retorna 'Sem registro' para nulos."""
    return "Sem registro" if pd.isna(valor) else pd.to_datetime(valor).strftime('%d/%m/%Y %H:%M:%S')


def highlight_sem_registro(cell):
    """Aplica cor vermelha à célula se o texto for 'Sem registro'."""
    return 'color: red; font-weight: bold;' if cell == "Sem registro" else ''


def apagar_tabela_auditoria(bq_service, nome_tabela):
    """Apaga uma tabela de auditoria do BigQuery."""
    try:
        client = bigquery.Client(credentials=bq_service.creds, project=bq_service.project_id)
        table_ref = f"{bq_service.project_id}.{bq_service.dataset_id}.{nome_tabela}"
        client.delete_table(table_ref, not_found_ok=True)
        return True, f"A auditoria '{nome_tabela}' foi apagada com sucesso."
    except Exception as e:
        return False, f"Erro ao apagar a auditoria '{nome_tabela}': {e}"


# --- Layout Central da Página ---
_, col_main, _ = st.columns([0.1, 0.8, 0.1])
with col_main:
    st.info(
        "**Fluxo de Trabalho:**\n"
        "1. Na página de **Extrair Dados**, processe os PDFs e baixe o arquivo `.parquet`.\n"
        "2. Volte aqui, escolha o tipo de análise, faça o upload do arquivo, selecione as semanas e gere o relatório."
    )

    # --- Seção de Geração de Análise ---
    with st.container(border=True):
        with st.expander("➕ Gerar Nova Análise", expanded=True):
            tipo_auditoria = st.radio(
                "1. Escolha o tipo de análise:",
                options=["Análise de Pendências Históricas (Salva Relatório)",
                         "Validação de Lançamentos (Análise Rápida)"],
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
                if 'validation_results' in st.session_state: del st.session_state.validation_results
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
                                if tipo_auditoria.startswith("Análise de Pendências"):
                                    if not analysis_name:
                                        st.error("O nome da análise é obrigatório para salvar.")
                                    else:
                                        sucesso, msg = analysis_service.criar_analise_comparativa(bq_service,
                                                                                                  analysis_name,
                                                                                                  selected_weeks,
                                                                                                  df_from_parquet)
                                        if sucesso:
                                            st.success(msg);
                                            st.balloons()
                                        else:
                                            st.error(msg)
                                else:
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
        with st.container(border=True):
            st.header("Resultados da Validação de Lançamentos")
            resultados = st.session_state.validation_results
            escolas_auditadas = resultados.get("escolas_auditadas", [])
            with st.expander(f"Análise focada em {len(escolas_auditadas)} escola(s). Clique para ver a lista."):
                for escola in escolas_auditadas: st.write(f"- {escola}")
            col1, col2 = st.columns(2)
            col1.metric("Registros Correspondentes (Matches)", resultados.get("total_matches", 0))
            col2.metric("Registros Corrigidos (Nulos Preenchidos)", resultados.get("nulos_preenchidos", 0))
            df_pendencias = resultados.get("pendencias_restantes", pd.DataFrame())
            st.subheader(f"Pendências Restantes ({len(df_pendencias)})")

            if not df_pendencias.empty:
                df_for_display = df_pendencias.copy()
                for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
                    df_for_display[col] = df_for_display[col].apply(formatar_valor)

                styled_df = df_for_display.style.apply(lambda s: s.map(highlight_sem_registro),
                                                       subset=['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO'])

                _, col_btn_download_val = st.columns([3, 1])
                with col_btn_download_val:
                    st.download_button("Baixar Pendências (.xlsx)", to_excel_auto_width(styled_df),
                                       "pendencias_restantes.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       use_container_width=True)

                st.dataframe(styled_df, use_container_width=True, hide_index=True, column_config={
                    "DATA_DO_RELATORIO": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "HORARIO": st.column_config.TimeColumn("Horário", format="HH:mm")})
            else:
                st.success("🎉 Nenhuma pendência restante encontrada!")

            if st.button("Limpar Resultados da Validação", use_container_width=True):
                del st.session_state.validation_results
                st.rerun()

    # --- Seção de Visualização de Relatórios Salvos ---
    with st.container(border=True):
        st.header("Visualizar Relatórios de Pendências Salvas")
        with st.spinner("Buscando auditorias existentes..."):
            analysis_tables = bq_service.list_analysis_tables()
        if not analysis_tables:
            st.info("Nenhuma auditoria salva foi criada ainda.")
        else:
            table_options = ["Selecione uma auditoria..."] + sorted(analysis_tables)
            selected_table = st.selectbox("Auditorias Disponíveis:", options=table_options,
                                          label_visibility="collapsed")

            if selected_table != "Selecione uma auditoria...":
                with st.spinner(f"Carregando dados de '{selected_table}'..."):
                    audit_stats = bq_service.get_analysis_audit_stats(selected_table)

                if not audit_stats:
                    st.warning("Não foi possível carregar dados para esta auditoria.")
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
                        st.subheader("Detalhes das Pendências (Agrupado)")

                        _, col_btn_download_saved = st.columns([3, 1])
                        with col_btn_download_saved:
                            st.download_button("Baixar detalhes (.xlsx)", to_excel_auto_width(df_details),
                                               f"{selected_table}_detalhes.xlsx",
                                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                               use_container_width=True)

                        st.dataframe(df_details, use_container_width=True, hide_index=True)

                # --- ZONA DE PERIGO: APAGAR AUDITORIA ---
                st.markdown("---")
                st.subheader("⚠️ Zona de Perigo")
                st.error(f"A ação de apagar a auditoria '{selected_table}' é permanente e não pode ser desfeita.",
                         icon="🚨")

                if st.checkbox(f"Confirmo que desejo apagar a auditoria '{selected_table}'.",
                               key=f"delete_confirm_{selected_table}"):
                    if st.button("Apagar Auditoria Permanentemente", type="primary", use_container_width=True,
                                 key=f"delete_btn_{selected_table}"):
                        with st.spinner(f"Apagando '{selected_table}'..."):
                            sucesso, mensagem = apagar_tabela_auditoria(bq_service, selected_table)
                            if sucesso:
                                st.success(mensagem)
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(mensagem)

