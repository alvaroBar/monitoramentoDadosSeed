# ==============================================================================
# ARQUIVO DA PÁGINA: p7_Auditoria_Comparativa.py
# VERSÃO FINAL: Inclui a nova "Auditoria de Validação" e mantém a funcionalidade original.
# ==============================================================================

import streamlit as st
import pandas as pd
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

# --- Seção de Geração de Análise ---
st.info(
    "**Fluxo de Trabalho:**\n"
    "1. Na página `p1`, processe os PDFs e baixe o arquivo `.parquet`.\n"
    "2. Volte aqui, escolha o tipo de análise, faça o upload do arquivo, selecione as semanas e gere o relatório."
)
st.markdown("---")

with st.expander("➕ Gerar Nova Análise", expanded=True):
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
        if 'validation_results' in st.session_state:
            del st.session_state.validation_results

        if not uploaded_parquet:
            st.error("Por favor, carregue o arquivo .parquet.")
        elif not selected_weeks:
            st.error("Por favor, selecione pelo menos uma semana.")
        else:
            with st.spinner("Processando... Esta operação pode levar alguns instantes."):
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
        # --- LÓGICA DE ESTILIZAÇÃO APLICADA AQUI ---

        # 1. Prepara uma cópia do DataFrame para o download em CSV
        df_for_csv = df_pendencias.copy()
        df_for_csv['REGISTRO_DE_AULA'] = pd.to_datetime(df_for_csv['REGISTRO_DE_AULA']).dt.strftime(
            '%Y-%m-%d %H:%M:%S').fillna("Sem registro")
        df_for_csv['REGISTRO_DE_CONTEUDO'] = pd.to_datetime(df_for_csv['REGISTRO_DE_CONTEUDO']).dt.strftime(
            '%Y-%m-%d %H:%M:%S').fillna("Sem registro")

        csv_data = df_for_csv.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Pendências Restantes como CSV", csv_data, "pendencias_restantes.csv", "text/csv",
                           use_container_width=True)


        # 2. Define a função de estilo para destacar nulos
        def highlight_nulls(s):
            is_null = pd.isna(s)
            return ['color: red' if v else '' for v in is_null]


        # 3. Formata e estiliza o DataFrame para exibição
        styled_df = df_pendencias.style.apply(highlight_nulls, subset=['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']) \
            .format({
            "REGISTRO_DE_AULA": lambda x: "Sem registro" if pd.isna(x) else pd.to_datetime(x).strftime(
                '%d/%m/%Y %H:%M:%S'),
            "REGISTRO_DE_CONTEUDO": lambda x: "Sem registro" if pd.isna(x) else pd.to_datetime(x).strftime(
                '%d/%m/%Y %H:%M:%S')
        })

        # 4. Exibe o DataFrame estilizado
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "DATA_DO_RELATORIO": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "HORARIO": st.column_config.TimeColumn("Horário", format="HH:mm"),
                "REGISTRO_DE_AULA": "Registro da Aula",
                "REGISTRO_DE_CONTEUDO": "Registro do Conteúdo"
            }
        )
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

                # --- LÓGICA DE ESTILIZAÇÃO ADICIONADA AQUI ---

                # 1. Cria uma cópia do DataFrame para o CSV e preenche os nulos com texto
                df_for_csv = df_details.copy()
                df_for_csv['REGISTRO_DE_AULA'] = pd.to_datetime(df_for_csv['REGISTRO_DE_AULA']).dt.strftime('%Y-%m-%d %H:%M:%S').fillna("Sem registro")
                df_for_csv['REGISTRO_DE_CONTEUDO'] = pd.to_datetime(df_for_csv['REGISTRO_DE_CONTEUDO']).dt.strftime('%Y-%m-%d %H:%M:%S').fillna("Sem registro")

                csv_data = df_for_csv.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"📥 Baixar detalhes como CSV",
                    data=csv_data,
                    file_name=f"{selected_table}_detalhes.csv",
                    mime="text/csv",
                    use_container_width=True
                )

                # 2. Função para aplicar a cor vermelha em valores nulos
                def highlight_nulls(s):
                    is_null = pd.isna(s)
                    return ['color: red' if v else '' for v in is_null]

                # 3. Preenche os nulos com "Sem registro" e aplica o estilo
                styled_df = df_details.style.apply(highlight_nulls, subset=['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO'])\
                                            .format({
                                                "REGISTRO_DE_AULA": lambda x: "Sem registro" if pd.isna(x) else pd.to_datetime(x).strftime('%d/%m/%Y %H:%M:%S'),
                                                "REGISTRO_DE_CONTEUDO": lambda x: "Sem registro" if pd.isna(x) else pd.to_datetime(x).strftime('%d/%m/%Y %H:%M:%S')
                                            })

                # 4. Exibe o DataFrame estilizado
                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "DATA_DO_RELATORIO": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "HORARIO": st.column_config.TimeColumn("Horário", format="HH:mm"),
                        "REGISTRO_DE_AULA": "Registro da Aula",
                        "REGISTRO_DE_CONTEUDO": "Registro do Conteúdo"
                    }
                )
            else:
                st.success("🎉 Não foram encontrados registros com pendências nesta auditoria.")