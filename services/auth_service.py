# services/auth_service.py
import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from utils import config  # Importa as configurações centralizadas

def get_google_auth_flow():
    """Cria e retorna o objeto de fluxo de autenticação do Google."""
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": config.CLIENT_ID,
                "client_secret": config.CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uri": config.REDIRECT_URI,
            }
        },
        scopes=config.SCOPES,
        redirect_uri=config.REDIRECT_URI,
    )

def autenticar_usuario():
    """Gerencia o fluxo de login/logout do usuário e armazena credenciais na sessão."""
    if 'credentials' in st.session_state:
        return # Usuário já autenticado

    flow = get_google_auth_flow()
    auth_code = st.query_params.get("code")

    if auth_code:
        try:
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            st.session_state.credentials = creds

            user_info_service = build('oauth2', 'v2', credentials=creds)
            user_info = user_info_service.userinfo().get().execute()

            st.session_state.user_info = user_info
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao obter o token de acesso: {e}")
            st.stop()
    else:
        auth_url, _ = flow.authorization_url(prompt="select_account")
        st.link_button("Login com Google", auth_url, use_container_width=True, type="primary")
        st.info("ℹ️ Uma nova aba será aberta para o login. Após a autenticação, esta aba pode ser fechada.")
        st.stop()