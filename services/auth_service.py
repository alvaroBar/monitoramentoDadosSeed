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


# services/auth_service.py -> Substitua a função inteira por esta

def autenticar_usuario():
    """Gerencia o fluxo de login do usuário, com tentativa de login automático."""
    # Se já possui credenciais na sessão, o usuário já está logado.
    if 'credentials' in st.session_state:
        return

    flow = get_google_auth_flow()
    auth_code = st.query_params.get("code")

    if auth_code:
        # Etapa 2: O usuário retornou do Google com um código de autorização
        try:
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            st.session_state.credentials = creds

            user_info_service = build('oauth2', 'v2', credentials=creds)
            user_info = user_info_service.userinfo().get().execute()

            st.session_state.user_info = user_info
            st.query_params.clear()  # Limpa o código da URL
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao obter o token de acesso: {e}")
            st.stop()
    else:
        # Etapa 1: O usuário acedeu à página sem estar logado
        auth_url, _ = flow.authorization_url(prompt="select_account")

        # Lógica de login automático:
        # Verifica se já tentamos o login automático nesta sessão para evitar loops
        if not st.session_state.get("login_attempted", False):
            st.session_state.login_attempted = True
            # Usa um meta refresh para redirecionar o usuário para a URL de login do Google
            st.html(f'<meta http-equiv="refresh" content="0;URL=\'{auth_url}\'">')
            st.stop()
        else:
            # Se a tentativa automática falhou (usuário não estava logado no Google),
            # exibe o botão para login manual.
            st.link_button("Login com Google", auth_url, use_container_width=True, type="primary")
            st.info("ℹ️ Para aceder, por favor, faça o login com a sua conta Google.")
            st.stop()


# (A função get_google_auth_flow e a de logout permanecem as mesmas)
def logout_usuario():
    """Limpa todas as informações da sessão para deslogar o usuário."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()