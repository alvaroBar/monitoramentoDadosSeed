# ==============================================================================
# ARQUIVO DA PÁGINA: 2_Carga_Inicial.py
# Melhorada a lógica de exibição do tempo estimado na barra de progresso.
# ==============================================================================

import streamlit as st
import pandas as pd
import time
from streamlit_autorefresh import st_autorefresh

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import autenticar_usuario, carregar_dados_no_bigquery


def formatar_tempo(segundos):
    """Converte segundos em uma string formatada (minutos e segundos)."""
    mins, segs = divmod(segundos, 60)
    if mins > 0:
        return f"{int(mins)}m {int(segs)}s"
    return f"{int(segs)}s"


st.set_page_config(layout="wide")
st.title("Carga Inicial de Dados Históricos 🚚")

autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica da Aplicação (Visível apenas após o login) ---
user_info = st.session_state.user_info
user_email = user_info.get("email")
user_name = user_info.get("name", "Usuário")

try:
    office_mapping = st.secrets.office_mapping
    if user_email in office_mapping:
        st.session_state.dataset_id = office_mapping[user_email]
    else:
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador.")
        st.stop()
except (AttributeError, KeyError):
    st.error(
        "ERRO DE CONFIGURAÇÃO: O mapeamento de escritórios [office_mapping] não foi encontrado nos Segredos do Streamlit.")
    st.stop()

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- Keep-alive da sessão ---
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_carga")

st.warning(
    "Use esta página apenas uma vez ou quando precisar substituir todos os dados no banco de dados. Esta operação apagará os dados existentes antes de carregar os novos.",
    icon="⚠️")

uploaded_file = st.file_uploader("Selecione o arquivo CSV completo com os dados históricos", type="csv")

if uploaded_file is not None:
    if st.button("Iniciar Carga Inicial e Substituir Dados", use_container_width=True, type="primary"):
        try:
            with st.spinner("Lendo arquivo CSV..."):
                df = pd.read_csv(uploaded_file)
            st.success(f"Arquivo lido com sucesso! {len(df)} linhas encontradas.")

            # Padroniza e ordena os dados antes de enviar
            df.columns = [col.upper().replace(' ', '_') for col in df.columns]
            df['SEMANA'] = pd.to_numeric(df['SEMANA'], errors='coerce').fillna(0).astype(int)
            df = df.sort_values(by='SEMANA').reset_index(drop=True)

            # --- LÓGICA DE UPLOAD EM PEDAÇOS COM BARRA DE PROGRESSO MELHORADA ---
            st.info("Iniciando o envio dos dados para o BigQuery em lotes...")
            progress_bar = st.progress(0, text="Preparando para o envio...")
            status_text = st.empty()

            total_rows = len(df)
            chunk_size = 50000
            chunks = [df[i:i + chunk_size] for i in range(0, total_rows, chunk_size)]
            total_chunks = len(chunks)

            creds = st.session_state.credentials
            dataset_id = st.session_state.dataset_id
            sucesso_geral = True
            tempo_inicio = time.time()

            for i, chunk in enumerate(chunks):
                modo_de_carga = 'replace' if i == 0 else 'append'

                # --- ALTERAÇÃO APLICADA AQUI: Lógica de cálculo de tempo restante ---
                progresso_atual = (i + 1) / total_chunks
                tempo_decorrido = time.time() - tempo_inicio

                # Calcula o tempo restante com base na média atual
                tempo_medio_por_chunk = tempo_decorrido / (i + 1)
                chunks_restantes = total_chunks - (i + 1)
                tempo_restante_estimado = tempo_medio_por_chunk * chunks_restantes

                # Monta o texto para a barra de progresso, mostrando o tempo restante
                texto_progresso = f"Enviando lote {i + 1} de {total_chunks}... Tempo restante estimado: {formatar_tempo(tempo_restante_estimado)}"

                progress_bar.progress(progresso_atual, text=texto_progresso)
                status_text.write(f"Enviando {len(chunk):,} linhas...".replace(",", "."))

                sucesso_chunk = carregar_dados_no_bigquery(chunk, creds, dataset_id, modo_de_carga)

                if not sucesso_chunk:
                    sucesso_geral = False
                    st.error(f"Falha ao enviar o lote {i + 1}. A operação foi interrompida.")
                    break

                time.sleep(0.01)

            progress_bar.empty()
            status_text.empty()

            if sucesso_geral:
                st.success("Carga inicial concluída com sucesso! Todos os dados foram substituídos no BigQuery.")
                st.balloons()
            else:
                st.error("A carga inicial falhou. Verifique as mensagens de erro acima.")

        except Exception as e:
            st.error(f"Ocorreu um erro durante a carga inicial: {e}")

