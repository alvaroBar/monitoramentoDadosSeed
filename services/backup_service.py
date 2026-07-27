# services/backup_service.py -> VERSÃO ATUALIZADA

import pandas as pd
import io
from datetime import datetime
import streamlit as st
from services.bigquery_service import BigQueryService
from services.drive_service import DriveService


class BackupService:
    def __init__(self, bq_service, drive_service):
        self.bq_service = bq_service
        self.drive_service = drive_service

    def execute_backup(self, dataset_id: str):
        """Executa o processo de backup, salvando apenas o arquivo .parquet."""
        try:
            # 1. Buscar todos os dados do BigQuery
            print("Iniciando busca de dados no BigQuery...")
            df_backup = self.bq_service.get_all_data()
            if df_backup.empty:
                return False, "Nenhum dado encontrado no BigQuery para fazer o backup."

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            base_filename = f"backup_{dataset_id}_{timestamp}"

            # 2. Gerar e fazer upload do arquivo Parquet
            print("Gerando arquivo Parquet...")
            parquet_buffer = io.BytesIO()
            df_backup.to_parquet(parquet_buffer, index=False)
            parquet_bytes = parquet_buffer.getvalue()

            success_parquet, msg_parquet = self.drive_service.upload_file(
                file_name=f"{base_filename}.parquet",
                file_content_bytes=parquet_bytes,
                mime_type='application/octet-stream'
            )
            if not success_parquet:
                return False, msg_parquet

            # Mensagem de sucesso atualizada
            return True, f"Backup concluído com sucesso! O arquivo '{base_filename}.parquet' foi salvo no Google Drive."

        except Exception as e:
            return False, f"Ocorreu um erro geral durante o backup: {e}"


def verificar_e_executar_backup_semanal(forcar_teste=False):
    """
    Executa o backup automático no Google Drive.
    :param forcar_teste: Se True, ignora a trava de dia da semana para testes imediatos.
    """
    # 1. Checa Credenciais
    if 'credentials' not in st.session_state:
        return

    # 2. Busca o dataset_id (Tenta pegar da sessão ou do arquivo de configuração)
    dataset_id = st.session_state.get('dataset_id')
    if not dataset_id:
        from utils import config
        dataset_id = getattr(config, 'DATASET_ID', None)

    if not dataset_id:
        if forcar_teste:
            st.warning("⚠️ Backup cancelado: 'dataset_id' não encontrado na sessão (st.session_state).")
        return

    DIA_DA_SEMANA_DO_BACKUP = 0  # 0 = Segunda-feira
    hoje = datetime.now()
    data_hoje_str = hoje.strftime("%Y-%m-%d")

    # 3. Verifica se hoje é segunda-feira OU se é um teste forçado
    eh_dia_de_backup = (hoje.weekday() == DIA_DA_SEMANA_DO_BACKUP)

    if eh_dia_de_backup or forcar_teste:
        # Trava para não repetir no mesmo dia (desativada no modo forcar_teste)
        if st.session_state.get('ultimo_backup_executado') == data_hoje_str and not forcar_teste:
            return

        try:
            bq_service = BigQueryService(
                credentials=st.session_state.credentials,
                dataset_id=dataset_id
            )
            drive_service = DriveService(credentials=st.session_state.credentials)
            backup_service = BackupService(bq_service, drive_service)

            sucesso, mensagem = backup_service.execute_backup(dataset_id)

            if sucesso:
                st.session_state['ultimo_backup_executado'] = data_hoje_str
                st.toast("🎉 Backup realizado com sucesso no Google Drive!", icon="✅")
            else:
                st.error(f"❌ Falha ao realizar backup no Drive: {mensagem}")

        except Exception as e:
            st.error(f"❌ Erro ao tentar executar a rotina de backup: {e}")