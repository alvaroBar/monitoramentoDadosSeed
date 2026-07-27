# ==============================================================================
# ARQUIVO DA PÁGINA: 3_Carga_Inicial.py
# VERSÃO REVISADA: Padronizada a inicialização do serviço.
# ==============================================================================

import streamlit as st
import pandas as pd
import time
from streamlit_autorefresh import st_autorefresh
from services import auth_service
from services.bigquery_service import BigQueryService
from utils.dataframe_utils import preparar_dataframe_para_bigquery
from utils import interface


def formatar_tempo(segundos):
    """Converte segundos em uma string formatada (minutos e segundos)."""
    mins, segs = divmod(segundos, 60)
    if mins > 0:
        return f"{int(mins)}m {int(segs)}s"
    return f"{int(segs)}s"


st.set_page_config(layout="wide")
st.title("Carga Inicial de Dados Históricos 🚚")
interface.exibir_cabecalho_ano()

# 1. Autenticação
auth_service.autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica Padrão de Sidebar, Mapeamento e Inicialização ---
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
st_autorefresh(interval=10 * 60 * 1000, key="session_refresher_carga")

# --- Lógica da Página ---
st.warning(
    "Use esta página apenas uma vez ou para substituir todos os dados. Esta operação apagará os dados existentes antes de carregar os novos.",
    icon="⚠️")

uploaded_file = st.file_uploader("Selecione o arquivo CSV completo com os dados históricos", type="csv")

if uploaded_file is not None:
    # MUDANÇA: Colunas para alinhar o botão à direita
    _, col_btn_carga = st.columns([3, 1])
    with col_btn_carga:
        # MUDANÇA: Removido `use_container_width=True`
        if st.button("Iniciar Carga e Substituir", type="primary"):
            try:
                with st.spinner("Lendo arquivo CSV..."):
                    df = pd.read_csv(uploaded_file)
                st.success(f"Arquivo lido com sucesso! {len(df)} linhas encontradas.")

                # Padroniza e ordena os dados antes de enviar
                df.columns = [col.upper().replace(' ', '_') for col in df.columns]
                df['SEMANA'] = pd.to_numeric(df['SEMANA'], errors='coerce').fillna(0).astype(int)
                df = df.sort_values(by='SEMANA').reset_index(drop=True)

                st.info("Iniciando o envio dos dados para o BigQuery em lotes...")
                progress_bar = st.progress(0, text="Preparando para o envio...")
                status_text = st.empty()

                chunk_size = 50000
                chunks = [df[i:i + chunk_size] for i in range(0, len(df), chunk_size)]
                total_chunks = len(chunks)
                sucesso_geral = True
                tempo_inicio = time.time()

                for i, chunk in enumerate(chunks):
                    modo_de_carga = 'replace' if i == 0 else 'append'

                    progresso_atual = (i + 1) / total_chunks
                    tempo_decorrido = time.time() - tempo_inicio
                    tempo_medio_por_chunk = tempo_decorrido / (i + 1)
                    chunks_restantes = total_chunks - (i + 1)
                    tempo_restante_estimado = tempo_medio_por_chunk * chunks_restantes
                    texto_progresso = (f"Enviando lote {i + 1}/{total_chunks} | "
                                       f"Tempo decorrido: {formatar_tempo(tempo_decorrido)} | "
                                       f"Restante est.: {formatar_tempo(tempo_restante_estimado)}")

                    progress_bar.progress(progresso_atual, text=texto_progresso)
                    status_text.write(f"Enviando {len(chunk):,} linhas...".replace(",", "."))

                    chunk_preparado = preparar_dataframe_para_bigquery(chunk)
                    sucesso_chunk = bq_service.carregar_dados(chunk_preparado, mode=modo_de_carga)

                    if not sucesso_chunk:
                        sucesso_geral = False
                        st.error(f"Falha ao enviar o lote {i + 1}. A operação foi interrompida.")
                        break
                    time.sleep(0.01)  # Pequena pausa para a UI atualizar suavemente

                progress_bar.empty()
                status_text.empty()

                if sucesso_geral:
                    st.success("Carga inicial concluída com sucesso! Todos os dados foram substituídos no BigQuery.")
                    st.balloons()
                else:
                    st.error("A carga inicial falhou. Verifique as mensagens de erro acima.")

            except Exception as e:
                st.error(f"Ocorreu um erro durante a carga inicial: {e}")
