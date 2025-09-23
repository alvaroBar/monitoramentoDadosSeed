# ==============================================================================
# ARQUIVO DA PÁGINA: p2_Carregar_Dados_BigQuery.py
# CORRIGIDO: Adicionada mais uma turma específica à lista de exclusão.
# ==============================================================================

import streamlit as st
import pandas as pd
from bigquery_loader import autenticar_usuario, get_latest_week, carregar_dados_no_bigquery

st.set_page_config(layout="wide")
st.title("Passo 2: Carregar Dados para o BigQuery ☁️")

autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica de Autenticação e Mapeamento ---
try:
    user_info = st.session_state.user_info
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

st.info("Faça o upload do arquivo `dados_extraidos.parquet` que você baixou na etapa anterior.")

uploaded_parquet = st.file_uploader("Selecione o arquivo .parquet", type=["parquet"])

if uploaded_parquet:
    df_para_envio = pd.read_parquet(uploaded_parquet)
    st.dataframe(df_para_envio.head())

    st.markdown("---")
    st.header("Configure e Envie")

    creds = st.session_state.credentials
    dataset_id = st.session_state.dataset_id
    ultima_semana = get_latest_week(creds, dataset_id)
    semana_sugerida = ultima_semana + 1

    semana_para_envio = st.number_input(
        "Confirme o número da semana para estes registros:",
        min_value=1, value=semana_sugerida, step=1
    )

    # --- LÓGICA DE FILTRO ATUALIZADA ---

    # Filtro 1: Por palavras-chave no nome da turma
    termos_para_excluir = ['aut', 'mec', 'eja', 'ali', 'gas', 'eletrom']
    regex_pattern = '|'.join(termos_para_excluir)
    mascara_keywords = df_para_envio['TURMA'].str.contains(regex_pattern, case=False, na=False)

    # Filtro 2: Por combinação específica de prefixo da Turma e nome exato da Escola
    turmas_escolas_excluir = [
        ('6º Ano - Integral - D', 'ANTONIO M CERETTA, C E-EF M PROFIS'),
        ('3ª Série - Noite - E - ENSINO MEDIO', 'ARTHUR C E SILVA, C E PRES-EF M'),
        ('3ª Série - Noite - C - ENSINO MEDIO', 'ARTHUR C E SILVA, C E PRES-EF M')
    ]
    mascara_especifica = pd.Series([False] * len(df_para_envio), index=df_para_envio.index)
    for turma_prefixo, escola in turmas_escolas_excluir:
        mascara_especifica |= (df_para_envio['TURMA'].str.startswith(turma_prefixo, na=False)) & (
                    df_para_envio['ESCOLA'] == escola)

    # --- ALTERAÇÃO APLICADA AQUI ---
    # Filtro 3: Por nome exato da Turma, independentemente da escola
    turmas_exatas_excluir = [
        'Sem Seriação - Tarde - A - PROGRAMA ATIVIDADE COMPLEMENTAR CONTRATURNO PERIODICA'
    ]
    mascara_exata = df_para_envio['TURMA'].isin(turmas_exatas_excluir)

    # Combina todas as máscaras de exclusão
    mascara_total_exclusao = mascara_keywords | mascara_especifica | mascara_exata

    df_filtrado = df_para_envio[~mascara_total_exclusao]

    turmas_excluidas = sorted(df_para_envio[mascara_total_exclusao]['TURMA'].unique())

    if turmas_excluidas:
        with st.expander(
                f"ℹ️ {len(turmas_excluidas)} turmas foram removidas pelo filtro automático. Clique para ver a lista."):
            num_cols = 3
            cols = st.columns(num_cols)
            for i, turma in enumerate(turmas_excluidas):
                cols[i % num_cols].write(f"- {turma}")

    # --- FIM DA LÓGICA DE FILTRO ---

    df_filtrado_final = df_filtrado.copy()
    df_filtrado_final['SEMANA'] = semana_para_envio

    st.markdown("---")
    st.write(f"**Total de registros a serem enviados: {len(df_filtrado_final)}**")

    if st.button("Enviar para o BigQuery", use_container_width=True, type="primary"):
        with st.spinner("Conectando e carregando dados... Este processo é rápido."):
            sucesso = carregar_dados_no_bigquery(df_filtrado_final, creds, dataset_id, mode='append')
            if sucesso:
                st.success(f"Dados da semana {semana_para_envio} enviados com sucesso!")
                st.balloons()
            else:
                st.error("Falha no envio dos dados. Verifique a mensagem de erro no terminal ou nos logs.")