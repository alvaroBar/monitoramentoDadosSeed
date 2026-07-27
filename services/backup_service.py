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

def verificar_e_executar_backup_semanal():
        """
        Executa o backup automático no Google Drive caso seja o dia configurado (segunda-feira)
        e o backup do dia ainda não tenha sido realizado nesta sessão.
        """
        # Garante que o usuário esteja autenticado e com as credenciais/dataset na sessão
        if 'credentials' not in st.session_state or 'dataset_id' not in st.session_state:
            return

        DIA_DA_SEMANA_DO_BACKUP = 0  # 0 = Segunda-feira
        hoje = datetime.now()
        data_hoje_str = hoje.strftime("%Y-%m-%d")

        # 1. Verifica se hoje é o dia programado
        if hoje.weekday() == DIA_DA_SEMANA_DO_BACKUP:
            # 2. Trava para evitar reexecutar toda vez que o Streamlit recarregar a página no mesmo dia
            if st.session_state.get('ultimo_backup_executado') == data_hoje_str:
                return

            try:
                # Inicializa os serviços com as credenciais do usuário logado
                bq_service = BigQueryService(
                    credentials=st.session_state.credentials,
                    dataset_id=st.session_state.dataset_id
                )
                drive_service = DriveService(credentials=st.session_state.credentials)
                backup_service = BackupService(bq_service, drive_service)

                # Executa o backup
                sucesso, mensagem = backup_service.execute_backup(st.session_state.dataset_id)

                if sucesso:
                    # Marca que o backup de hoje já foi feito
                    st.session_state['ultimo_backup_executado'] = data_hoje_str
                    st.toast("🔄 Backup semanal automático realizado no Google Drive!", icon="✅")
                else:
                    st.warning(f"⚠️ Tentativa de backup automático: {mensagem}")

            except Exception as e:
                # Silencioso ou log de erro para não travar o carregamento do usuário
                print(f"Erro ao executar backup automático de início: {e}")