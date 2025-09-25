# utils/config.py
import streamlit as st

try:
    # Configurações de Autenticação
    CLIENT_ID = st.secrets.google_oauth.client_id
    CLIENT_SECRET = st.secrets.google_oauth.client_secret
    PROJECT_ID = st.secrets.google_oauth.project_id
    REDIRECT_URI = st.secrets.google_oauth.redirect_uri
    SCOPES = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        "https://www.googleapis.com/auth/bigquery",
        "https://www.googleapis.com/auth/drive.file"
    ]

except (AttributeError, KeyError):
    st.error(
        "ERRO DE CONFIGURAÇÃO: A seção [google_oauth] não foi encontrada ou está incompleta nos Segredos do Streamlit."
    )
    st.stop()