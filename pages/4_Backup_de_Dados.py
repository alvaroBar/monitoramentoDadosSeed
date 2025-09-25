# ==============================================================================
# ARQUIVO DA PÁGINA: 4_Backup_de_Dados.py
# VERSÃO REVISADA: Código limpo e totalmente alinhado à arquitetura.
# ==============================================================================

import streamlit as st
import pandas as pd
from services import auth_service
from services.bigquery_service import BigQueryService
from streamlit_autorefresh import st_autorefresh
from services.drive_service import DriveService
from services.backup_service import BackupService
from datetime import datetime

st.set_page_config(layout="wide")
st.title("Backup de Dados do BigQuery 💾")

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
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador.")
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
st_autorefresh(interval=10 * 60 * 1000, key="session_refresher_backup")

# --- Lógica da Página ---
# Inicializa os novos serviços
if 'drive_service' not in st.session_state:
    st.session_state.drive_service = DriveService(credentials=st.session_state.credentials)
drive_service = st.session_state.drive_service

if 'backup_service' not in st.session_state:
    st.session_state.backup_service = BackupService(bq_service, drive_service)
backup_service = st.session_state.backup_service

# --- NOVA SEÇÃO: Backup Automático e Manual ---
st.markdown("---")
st.header("Backup para o Google Drive")

# Lógica de Agendamento "Gatilho na Visita"
DIA_DA_SEMANA_DO_BACKUP = 0 # 0 = Segunda-feira
hoje = datetime.now()

if 'last_backup_check' not in st.session_state:
    st.session_state.last_backup_check = None

# Verifica se hoje é o dia do backup e se o backup para esta semana ainda não foi feito
if hoje.weekday() == DIA_DA_SEMANA_DO_BACKUP and (st.session_state.last_backup_check is None or (hoje - st.session_state.last_backup_check).days >= 7):
    st.info("Hoje é dia de backup semanal. Iniciando o processo em segundo plano...")
    with st.spinner("Realizando backup para o Google Drive... Por favor, não feche esta página."):
        success, message = backup_service.execute_backup(st.session_state.dataset_id)
        if success:
            st.success(message)
            st.session_state.last_backup_check = hoje # Marca que o backup desta semana foi feito
        else:
            st.error(message)

# Opção de Backup Manual
if st.button("Executar Backup Manual Agora", use_container_width=True):
    with st.spinner("Realizando backup manual para o Google Drive..."):
        success, message = backup_service.execute_backup(st.session_state.dataset_id)
        if success:
            st.success(message)
            st.session_state.last_backup_check = hoje
        else:
            st.error(message)

if 'backup_data' not in st.session_state:
    st.session_state.backup_data = None

# --- Passo 1: Seleção de Semanas ---
if st.session_state.backup_data is None:
    st.header("Passo 1: Selecione as Semanas para o Backup")
    try:
        with st.spinner("Buscando semanas disponíveis..."):
            available_weeks = bq_service.get_available_weeks()

        if available_weeks:
            selected_weeks = st.multiselect(
                "Selecione as semanas para incluir no backup (deixe em branco para todas):",
                options=available_weeks
            )

            if st.button("Buscar Dados para Backup", use_container_width=True, type="primary"):
                week_filter = selected_weeks if selected_weeks else None
                with st.spinner("Buscando dados do BigQuery... Isso pode levar algum tempo."):
                    df_backup = bq_service.get_all_data(week_filter=week_filter)
                    if not df_backup.empty:
                        st.session_state.backup_data = df_backup
                        st.rerun()
                    else:
                        st.warning("Nenhum dado encontrado para as semanas selecionadas.")
        else:
            st.info("Nenhuma semana encontrada no banco de dados para este usuário.")
    except Exception as e:
        st.error(f"Não foi possível buscar as semanas do BigQuery. Erro: {e}")

# --- Passo 2: Download dos Dados ---
if st.session_state.backup_data is not None:
    df_backup = st.session_state.backup_data
    st.success(f"✅ Dados prontos! {len(df_backup)} registros foram encontrados.")
    st.dataframe(df_backup.head())

    st.header("Passo 2: Escolha o Formato do Backup")

    col1, col2 = st.columns(2)
    with col1:
        df_csv = df_backup.copy()
        for col in ['REGISTRO_DE_AULA', 'REGISTRO_DE_CONTEUDO']:
            if col in df_csv.columns:
                df_csv[col] = df_csv[col].astype(str).replace('NaT', 'Sem registro')
        csv_data = df_csv.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar Backup em .csv",
            data=csv_data,
            file_name="backup_relatorios.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col2:
        parquet_data = df_backup.to_parquet(index=False)
        st.download_button(
            label="⚡️ Baixar Backup em .parquet (Mais Rápido/Leve)",
            data=parquet_data,
            file_name="backup_relatorios.parquet",
            mime="application/octet-stream",
            use_container_width=True
        )

    if st.button("Limpar e Iniciar Nova Busca", use_container_width=True):
        st.session_state.backup_data = None
        st.rerun()