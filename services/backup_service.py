# services/backup_service.py

import pandas as pd
import io
from datetime import datetime


class BackupService:
    def __init__(self, bq_service, drive_service):
        self.bq_service = bq_service
        self.drive_service = drive_service

    def _generate_sql_from_dataframe(self, df: pd.DataFrame, table_name: str) -> str:
        """Gera uma string com comandos SQL INSERT a partir de um DataFrame."""
        sql_statements = []
        for index, row in df.iterrows():
            columns = ', '.join(f"`{col}`" for col in row.index)
            values = ', '.join(
                f"'{str(val).replace('\'', '\'\'')}'" if val is not None else "NULL" for val in row.values)
            sql_statements.append(f"INSERT INTO `{table_name}` ({columns}) VALUES ({values});")
        return '\n'.join(sql_statements)

    def execute_backup(self, dataset_id: str):
        """Executa o processo completo de backup."""
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

            # 3. Gerar e fazer upload do arquivo SQL
            print("Gerando arquivo SQL...")
            sql_content = self._generate_sql_from_dataframe(df_backup, "relatorios_lrco")
            sql_bytes = sql_content.encode('utf-8')

            success_sql, msg_sql = self.drive_service.upload_file(
                file_name=f"{base_filename}.sql",
                file_content_bytes=sql_bytes,
                mime_type='text/plain'
            )
            if not success_sql:
                return False, msg_sql

            return True, f"Backup concluído com sucesso! Arquivos '{base_filename}.parquet' e '.sql' foram salvos."

        except Exception as e:
            return False, f"Ocorreu um erro geral durante o backup: {e}"