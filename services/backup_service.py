# services/backup_service.py

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

            return True, f"Backup concluído com sucesso! O arquivo '{base_filename}.parquet' foi salvo no Google Drive."

        except Exception as e:
            return False, f"Ocorreu um erro geral durante o backup: {e}"


from datetime import datetime
import streamlit as st

def verificar_e_executar_backup_semanal(forcar_teste=False):
    """
    Verifica e executa o backup semanal.
    Consulta a memória da sessão E o Google Drive para evitar duplicidade.
    """
    # 1. Validação de Autenticação
    if 'credentials' not in st.session_state or 'user_info' not in st.session_state:
        if forcar_teste:
            st.warning("⚠️ [Backup] Usuário não está autenticado na sessão.")
        return

    # 2. Resgate do dataset_id
    dataset_id = st.session_state.get('dataset_id')
    if not dataset_id:
        try:
            user_email = st.session_state.user_info.get("email")
            office_mapping = st.secrets.office_mapping
            if user_email in office_mapping:
                dataset_id = office_mapping[user_email]
                st.session_state.dataset_id = dataset_id
        except Exception as e:
            if forcar_teste:
                st.warning(f"⚠️ [Backup] Não foi possível obter o mapeamento: {e}")

    if not dataset_id:
        if forcar_teste:
            st.warning("⚠️ [Backup] 'dataset_id' não encontrado.")
        return

    # 3. Identificador da semana atual (Ano + Semana ISO)
    hoje = datetime.now()
    ano, numero_semana, _ = hoje.isocalendar()
    semana_chave = f"backup_checado_{dataset_id}_{ano}_W{numero_semana:02d}"

    # 4. CHECAGEM RÁPIDA (Session State)
    # Se nesta mesma navegação/sessão já verificamos que o backup está ok, nem vai ao Drive.
    if st.session_state.get(semana_chave) is True and not forcar_teste:
        return

    try:
        drive_service = DriveService(credentials=st.session_state.credentials)

        # 5. CHECAGEM PERSISTENTE (Google Drive)
        # Se não estamos forçando o teste, verifica se o arquivo já existe no Drive desde segunda-feira
        if not forcar_teste:
            if ja_existe_backup_na_semana_no_drive(drive_service, dataset_id):
                # Marca na sessão para não ficar fazendo requisições à API do Drive em cada reload
                st.session_state[semana_chave] = True
                return

        # Marca na sessão que a execução vai começar
        st.session_state[semana_chave] = True

        bq_service = BigQueryService(
            credentials=st.session_state.credentials,
            dataset_id=dataset_id
        )
        backup_service = BackupService(bq_service, drive_service)

        # 6. Executa o backup
        sucesso, mensagem = backup_service.execute_backup(dataset_id)

        if sucesso:
            st.toast("🎉 Backup semanal realizado com sucesso no Google Drive!", icon="✅")
        else:
            # Em caso de erro, desfaz a trava da sessão
            st.session_state[semana_chave] = False
            st.error(f"❌ Falha ao realizar backup no Drive: {mensagem}")

    except Exception as e:
        st.session_state[semana_chave] = False
        st.error(f"❌ Erro ao tentar executar a rotina de backup: {e}")


from datetime import datetime, timedelta


def ja_existe_backup_na_semana_no_drive(drive_service, dataset_id):
    """
    Consulta o Google Drive para verificar se já existe algum arquivo de backup
    criado a partir da segunda-feira da semana atual.
    """
    try:
        hoje = datetime.now()
        # Data/hora de início da segunda-feira desta semana (00:00:00)
        segunda_feira = hoje - timedelta(days=hoje.weekday())
        inicio_da_semana = segunda_feira.replace(hour=0, minute=0, second=0, microsecond=0)

        # O 'Z' no final é OBRIGATÓRIO para a API do Google Drive
        data_corte_iso = inicio_da_semana.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Query corrigida com o sufixo 'Z' e filtro pelo padrão exato 'backup_DATASET'
        query = (
            f"name contains 'backup_{dataset_id}' and "
            f"createdTime >= '{data_corte_iso}' and "
            f"trashed = false"
        )

        arquivos = drive_service.buscar_arquivos(query)

        # Retorna True se encontrou 1 ou mais arquivos criados nesta semana
        return len(arquivos) > 0

    except Exception as e:
        # Exibe o erro na tela do Streamlit para sabermos caso ocorra alguma falha na API
        st.error(f"⚠️ [Debug Backup] Erro ao consultar o Google Drive: {e}")

        # RETORNO DE SEGURANÇA:
        # Em caso de erro de API, retornamos True temporariamente para EVITAR
        # que o sistema gere múltiplos backups indesejados.
        return True