import streamlit as st
import pandas as pd
import plotly.express as px
from services import auth_service
from services.bigquery_service import BigQueryService
from streamlit_autorefresh import st_autorefresh
import datetime
import time  # Adicionado para controle de fluxo na troca de ano
from utils import config
from utils import interface

# ------------------ Configuração da Página ------------------
st.set_page_config(
    page_title="Dashboard",
    page_icon="📊",
    layout="wide"
)

# ------------------ Estilo Customizado ------------------
st.markdown("""
<style>
.metric-card {
    background-color: #f8f9fa;
    border-radius: 15px;
    padding: 20px;
    margin: 5px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.metric-card h2 {
    margin: 0;
    font-size: 2em;
    color: #2c3e50;
}
.metric-card p {
    margin: 0;
    color: #6c757d;
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Dashboard de Monitoramento")
interface.exibir_cabecalho_ano()

# ------------------ Autenticação ------------------
auth_service.autenticar_usuario()

if 'user_info' in st.session_state:
    user_info = st.session_state.user_info
    user_email = user_info.get("email")
    user_name = user_info.get("name", "Usuário")

    # Mapeamento de dataset
    try:
        office_mapping = st.secrets.office_mapping
        if user_email in office_mapping:
            st.session_state.dataset_id = office_mapping[user_email]
        else:
            st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador.")
            st.stop()
    except (AttributeError, KeyError):
        st.error("ERRO DE CONFIGURAÇÃO: O mapeamento [office_mapping] não foi encontrado.")
        st.stop()

    # ------------------ Sidebar com Seletor de Ano ------------------
    with st.sidebar:
        st.subheader(f"👋 Olá, {user_name}")
        st.caption(f"Dataset ativo: `{st.session_state.dataset_id}`")

        st.divider()
        st.header("📅 Ano de Referência")

        # 1. Inicializa o ano na sessão se não existir (Padrão: Ano Atual)
        if 'ano_letivo' not in st.session_state:
            st.session_state['ano_letivo'] = datetime.datetime.now().year

        # 2. Define o índice padrão do selectbox baseado na sessão
        try:
            # Tenta achar o ano da sessão na lista configurada
            index_padrao = config.ANOS_DISPONIVEIS.index(st.session_state['ano_letivo'])
        except (ValueError, AttributeError):
            # Se der erro (ex: ano atual não está na lista), usa o primeiro da lista
            index_padrao = 0

        # 3. Cria o Seletor
        ano_selecionado = st.selectbox(
            "Trabalhar com dados de:",
            options=config.ANOS_DISPONIVEIS,
            index=index_padrao,
            help="O sistema seleciona automaticamente o ano atual. Mude apenas para consultar ou corrigir anos anteriores."
        )

        # 4. Lógica de Troca de Ano
        if ano_selecionado != st.session_state['ano_letivo']:
            st.session_state['ano_letivo'] = ano_selecionado

            # CRÍTICO: Remove o serviço antigo da memória para forçar reconexão na nova tabela
            if 'bq_service' in st.session_state:
                del st.session_state['bq_service']

            st.toast(f"Carregando base de dados de {ano_selecionado}...", icon="🔄")
            time.sleep(1)  # Pausa breve para o usuário ver o aviso
            st.rerun()

        st.caption(f"📌 Tabela: `relatorios_lrco_{ano_selecionado}`")
        st.divider()

        if st.button("🔒 Logout"):
            auth_service.logout_usuario()

    # Mantém a sessão ativa
    st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_dashboard")

    # ------------------ Inicialização do Serviço BigQuery ------------------
    # Como deletamos 'bq_service' na sidebar ao trocar o ano, este bloco rodará novamente
    # criando uma nova instância que aponta para a tabela do ano correto.
    if 'bq_service' not in st.session_state:
        st.session_state.bq_service = BigQueryService(
            credentials=st.session_state.credentials,
            dataset_id=st.session_state.dataset_id
        )
    bq_service = st.session_state.bq_service

    # ------------------ Estatísticas ------------------
    with st.spinner(f"🔄 Carregando estatísticas de {st.session_state['ano_letivo']}..."):
        stats = bq_service.get_dashboard_stats()

    if stats and stats.get('total_registros', 0) > 0:
        total_registros = stats.get('total_registros', 0)
        sem_registro_aula = stats.get('sem_registro_aula', 0)
        sem_registro_conteudo = stats.get('sem_registro_conteudo', 0)
        taxa_adesao_aula = ((total_registros - sem_registro_aula) / total_registros) * 100 if total_registros > 0 else 0
        taxa_adesao_conteudo = ((
                                            total_registros - sem_registro_conteudo) / total_registros) * 100 if total_registros > 0 else 0

        dados_escolas_pendentes = stats.get("escolas_com_pendencias")
        df_escolas_pendentes = pd.DataFrame(dados_escolas_pendentes)

        num_escolas_pendentes = stats.get("total_escolas_com_pendencias", 0)
        ultima_semana = stats.get("ultima_semana_lancada", 0)

        # ------------------ KPIs ------------------
        st.markdown(f"### 📌 Visão Geral ({st.session_state['ano_letivo']})")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.markdown(f"<div class='metric-card'><p>Total de Registros</p><h2>{total_registros:,}</h2></div>",
                        unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='metric-card'><p>Adesão de Aulas</p><h2>{taxa_adesao_aula:.1f}%</h2></div>",
                        unsafe_allow_html=True)
        with col3:
            st.markdown(
                f"<div class='metric-card'><p>Adesão de Conteúdos</p><h2>{taxa_adesao_conteudo:.1f}%</h2></div>",
                unsafe_allow_html=True)
        with col4:
            st.markdown(f"<div class='metric-card'><p>Escolas com Pendências</p><h2>{num_escolas_pendentes}</h2></div>",
                        unsafe_allow_html=True)
        with col5:
            st.markdown(
                f"<div class='metric-card'><p>Última Semana</p><h2>{int(ultima_semana) if ultima_semana else 0}</h2></div>",
                unsafe_allow_html=True)

        # ------------------ Abas ------------------
        tab1, tab2 = st.tabs(["🏫 Pendências", "📊 Análises Gerais"])

        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Top 5 Escolas com Mais Pendências")
                if not df_escolas_pendentes.empty:
                    st.dataframe(df_escolas_pendentes, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhuma escola com pendências encontrada.")
            with col2:
                st.subheader("Pendências por Município")
                dados_municipios = stats.get("pendencias_por_municipio")
                df_municipios_pendentes = pd.DataFrame(dados_municipios)
                if not df_municipios_pendentes.empty:
                    required_cols = ["MUNICIPIO", "PENDENCIAS"]
                    if all(col in df_municipios_pendentes.columns for col in required_cols):
                        fig = px.bar(df_municipios_pendentes, x="MUNICIPIO", y="PENDENCIAS",
                                     title="Pendências por Município")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning(
                            f"Os dados de pendências por município não estão no formato esperado. Colunas necessárias: {required_cols}.")
                else:
                    st.info("Nenhum município com pendências encontrado.")

        with tab2:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Lançamentos por Semana")
                dados_registros_semana = stats.get("registros_por_semana")
                df_registros_semana = pd.DataFrame(dados_registros_semana)
                if not df_registros_semana.empty:
                    fig = px.bar(df_registros_semana, x=df_registros_semana.index, y=df_registros_semana.columns[0],
                                 title="Registros por Semana", labels={'x': 'Semana', 'y': 'Quantidade'})
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Não há dados de registros por semana.")

            with col2:
                st.subheader("Disciplinas com mais Lançamentos")
                dados_top_disciplinas = stats.get("top_disciplinas")
                df_top_disciplinas = pd.DataFrame(dados_top_disciplinas)
                if not df_top_disciplinas.empty:
                    st.dataframe(df_top_disciplinas, use_container_width=True, hide_index=True)
                else:
                    st.info("Não há dados de disciplinas disponíveis.")
    else:
        st.info(f"Ainda não há dados lançados para o ano de {st.session_state['ano_letivo']}.")