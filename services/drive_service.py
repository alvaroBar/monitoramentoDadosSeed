# services/drive_service.py

import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


class DriveService:
    def __init__(self, credentials):
        if not credentials:
            raise ValueError("Credenciais são necessárias para inicializar o DriveService.")
        self.service = build('drive', 'v3', credentials=credentials)

    def _find_or_create_folder(self, folder_name):
        """Busca por uma pasta pelo nome. Se não encontrar, cria uma."""
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        response = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])

        if files:
            return files[0].get('id')
        else:
            file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
            folder = self.service.files().create(body=file_metadata, fields='id').execute()
            return folder.get('id')

    def upload_file(self, file_name, file_content_bytes, folder_name="Backups App LRCO",
                    mime_type='application/octet-stream'):
        """Faz o upload de um arquivo para uma pasta específica no Google Drive."""
        try:
            folder_id = self._find_or_create_folder(folder_name)

            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }

            media = MediaIoBaseUpload(io.BytesIO(file_content_bytes), mimetype=mime_type, resumable=True)

            file = self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            return True, f"Arquivo '{file_name}' enviado com sucesso!"
        except Exception as e:
            return False, f"Erro ao enviar arquivo para o Google Drive: {e}"