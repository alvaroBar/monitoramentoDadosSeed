# services/backup_service.py -> VERSÃO ATUALIZADA

import pandas as pd
import io
from datetime import datetime


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