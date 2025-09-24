# ==============================================================================
# ARQUIVO DA PÁGINA: 2_Carregar_Dados_BigQuery.py
# VERSÃO REVISADA: Padronizada a inicialização e adicionado sidebar.
# ==============================================================================

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh

from services import auth_service
from services.bigquery_service import BigQueryService
from utils.dataframe_utils import preparar_dataframe_para_bigquery

st.set_page_config(layout="wide")
st.title("Passo 2: Carregar Dados para o BigQuery ☁️")

# 1. Autenticação
auth_service.autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Sidebar Padrão ---
user_info = st.session_state.user_info
user_name = user_info.get("name", "Usuário")
with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout"):
        auth_service.logout_usuario()

# 2. Mapeamento de Usuário e Dataset
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

st_autorefresh(interval=10 * 60 * 1000, key="refresher_carregador_bigQuerry")
# 3. Inicialização Padrão do Serviço
if 'bq_service' not in st.session_state:
    st.session_state.bq_service = BigQueryService(
        credentials=st.session_state.credentials,
        dataset_id=st.session_state.dataset_id
    )
bq_service = st.session_state.bq_service

# --- Lógica da Página ---
st.info("Faça o upload do arquivo `dados_extraidos.parquet` que você baixou na etapa anterior.")

uploaded_parquet = st.file_uploader("Selecione o arquivo .parquet", type=["parquet"])

if uploaded_parquet:
    df_para_envio = pd.read_parquet(uploaded_parquet)
    st.dataframe(df_para_envio.head())

    st.markdown("---")
    st.header("Configure e Envie")

    ultima_semana = bq_service.get_latest_week()
    semana_sugerida = ultima_semana + 1

    semana_para_envio = st.number_input(
        "Confirme o número da semana para estes registros:",
        min_value=1, value=semana_sugerida, step=1
    )

    # --- LÓGICA DE FILTRO (Permanece inalterada) ---
    termos_para_excluir = ['aut', 'mec', 'eja', 'ali', 'gas', 'eletrom']
    regex_pattern = '|'.join(termos_para_excluir)
    mascara_keywords = df_para_envio['TURMA'].str.contains(regex_pattern, case=False, na=False)

    turmas_escolas_excluir = [
        ('6º Ano - Integral - D', 'ANTONIO M CERETTA, C E-EF M PROFIS'),
        ('3ª Série - Noite - E - ENSINO MEDIO', 'ARTHUR C E SILVA, C E PRES-EF M'),
        ('3ª Série - Noite - C - ENSINO MEDIO', 'ARTHUR C E SILVA, C E PRES-EF M')
    ]
    mascara_especifica = pd.Series([False] * len(df_para_envio), index=df_para_envio.index)
    for turma_prefixo, escola in turmas_escolas_excluir:
        mascara_especifica |= (df_para_envio['TURMA'].str.startswith(turma_prefixo, na=False)) & (df_para_envio['ESCOLA'] == escola)

    turmas_exatas_excluir = ['Sem Seriação - Tarde - A - PROGRAMA ATIVIDADE COMPLEMENTAR CONTRATURNO PERIODICA']
    mascara_exata = df_para_envio['TURMA'].isin(turmas_exatas_excluir)

    mascara_total_exclusao = mascara_keywords | mascara_especifica | mascara_exata
    df_filtrado = df_para_envio[~mascara_total_exclusao]
    turmas_excluidas = sorted(df_para_envio[mascara_total_exclusao]['TURMA'].unique())

    if turmas_excluidas:
        with st.expander(f"ℹ️ {len(turmas_excluidas)} turmas foram removidas pelo filtro. Clique para ver a lista."):
            cols = st.columns(3)
            for i, turma in enumerate(turmas_excluidas):
                cols[i % 3].write(f"- {turma}")

    df_filtrado_final = df_filtrado.copy()
    df_filtrado_final['SEMANA'] = semana_para_envio

    st.markdown("---")
    st.write(f"**Total de registros a serem enviados: {len(df_filtrado_final)}**")

    if st.button("Enviar para o BigQuery", use_container_width=True, type="primary"):
        with st.spinner("Conectando e carregando dados..."):
            df_preparado = preparar_dataframe_para_bigquery(df_filtrado_final)
            sucesso = bq_service.carregar_dados(df_preparado, mode='append')
            if sucesso:
                st.success(f"Dados da semana {semana_para_envio} enviados com sucesso!")
                st.balloons()
            else:
                st.error("Falha no envio dos dados. Verifique a mensagem de erro acima.")