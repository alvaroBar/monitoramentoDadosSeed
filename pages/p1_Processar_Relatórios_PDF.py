# ==============================================================================
# ARQUIVO DA PÁGINA: p1_Processar_Relatorios_PDF.py
# Implementado gerenciamento de memória explícito (gc.collect) e logging 
# persistente em arquivo para diagnosticar crashes silenciosos.
# ==============================================================================

import streamlit as st
import pandas as pd
import re
import time
import pdfplumber
import os
import gc  # Garbage Collector
import logging
from streamlit_autorefresh import st_autorefresh

# Importa as funções necessárias
from bigquery_loader import autenticar_usuario, get_latest_week, carregar_dados_no_bigquery

# --- Configuração do Log em Arquivo ---
LOG_FILENAME = "processing_log.txt"
logging.basicConfig(
    filename=LOG_FILENAME,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'  # 'w' para sobrescrever o log a cada nova execução
)


# --- Funções de Apoio ---
def formatar_tempo(segundos):
    mins, segs = divmod(int(segundos), 60)
    return f"{mins}m {segs}s" if mins > 0 else f"{segs}s"


def extrair_dados_de_pdf(arquivo_pdf, disciplinas_validas):
    dados_extraidos = []
    # ... (resto da função permanece igual)
    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"
    nome_escola, municipio, data_relatorio = "N/A", "N/A", "N/A"
    turma_atual = None
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page_num, page in enumerate(pdf.pages):
                texto_pagina = page.extract_text()
                if not texto_pagina: continue
                linhas = texto_pagina.split("\n")
                if page_num == 0:
                    for idx, linha in enumerate(linhas):
                        if "ESTADO DO PARANá" in linha.upper():
                            match_data = re.search(data_relatorio_re, linha)
                            if match_data: data_relatorio = match_data.group()
                        if "SECRETARIA DE ESTADO DA EDUCAÇÃO" in linha.upper():
                            municipio_temp = linha.split("SECRETARIA")[0].strip()
                            if municipio_temp: municipio = municipio_temp
                            if idx + 1 < len(linhas):
                                nome_escola_temp = linhas[idx + 1].strip()
                                if nome_escola_temp: nome_escola = nome_escola_temp
                for linha in linhas:
                    linha = linha.strip()
                    if " - " in linha and "TURMA" not in linha.upper() and "LANÇAMENTO" not in linha.upper():
                        turma_atual = linha
                        continue
                    if not turma_atual: continue
                    horarios = re.findall(horario_re, linha)
                    if not horarios: continue
                    registros = re.findall(registro_re, linha)
                    horario = horarios[0]
                    pos_horario = linha.find(horario)
                    pos_fim_horario = pos_horario + len(horario)
                    registro_aula = registros[0] if len(registros) >= 1 else "Sem registro"
                    registro_conteudo = registros[1] if len(registros) >= 2 else "Sem registro"
                    pos_registro = linha.find(registros[0]) if registros else len(linha)
                    disciplina_raw = linha[pos_fim_horario:pos_registro].strip()
                    disciplina_encontrada = next((d for d in disciplinas_validas if d in disciplina_raw.upper()), None)
                    if disciplina_encontrada:
                        dados_extraidos.append([
                            0, data_relatorio, municipio, nome_escola, turma_atual, horario,
                            disciplina_encontrada, registro_aula, registro_conteudo
                        ])
    except Exception as e:
        logging.error(f"Falha ao processar o PDF {arquivo_pdf.name}. Erro: {e}", exc_info=True)
        return pd.DataFrame()
    colunas = ["SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA", "HORARIO", "DISCIPLINA",
               "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"]
    return pd.DataFrame(dados_extraidos, columns=colunas)


# --- Interface do Streamlit ---
st.set_page_config(layout="wide")
st.title("Processar e Enviar Relatórios PDF em Lotes 📄")
autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# ... (Lógica de Autenticação e Mapeamento)
user_info = st.session_state.user_info
user_email = user_info.get("email")
user_name = user_info.get("name", "Usuário")
try:
    office_mapping = st.secrets.office_mapping
    if user_email in office_mapping:
        st.session_state.dataset_id = office_mapping[user_email]
    else:
        st.error(f"ERRO: O e-mail '{user_email}' não está autorizado."); st.stop()
except (AttributeError, KeyError):
    st.error("ERRO DE CONFIGURAÇÃO: O mapeamento [office_mapping] não foi encontrado."); st.stop()

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout", key="logout_processar"): st.session_state.clear(); st.rerun()
st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_processar")

# --- Interface de Upload e Configuração ---
st.header("Passo 1: Carregue os Arquivos")
col1, col2 = st.columns(2)
with col1: uploaded_files = st.file_uploader("Selecione os arquivos PDF", type="pdf", accept_multiple_files=True)
with col2: disciplinas_file = st.file_uploader("Selecione a planilha de disciplinas", type=["xlsx"])
st.markdown("---")
st.header("Passo 2: Configure o Envio")
creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id
ultima_semana = get_latest_week(creds, dataset_id)
semana_sugerida = ultima_semana + 1
semana_para_envio = st.number_input("Digite o número da semana para os registros:", min_value=1, value=semana_sugerida,
                                    step=1)
st.markdown("---")

# --- Lógica de Processamento em Lotes ---
if uploaded_files and disciplinas_file:
    if st.button(f"Processar e Enviar {len(uploaded_files)} Arquivos para a Semana {semana_para_envio}",
                 use_container_width=True, type="primary"):
        CHUNK_SIZE = 20
        try:
            logging.info("--- INICIANDO NOVO PROCESSAMENTO ---")
            disciplinas_df = pd.read_excel(disciplinas_file)
            lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]
            termos_para_excluir = ['aut', 'mec', 'eja', 'ali', 'gas', 'eletrom']
            regex_pattern = '|'.join(termos_para_excluir)
            all_files = sorted(uploaded_files, key=lambda f: f.name)
            chunks = [all_files[i:i + CHUNK_SIZE] for i in range(0, len(all_files), CHUNK_SIZE)]
            total_chunks, total_registros_enviados = len(chunks), 0
            tempo_inicio_total = time.time()
            st.info(f"Iniciando processamento de {len(all_files)} arquivos em {total_chunks} lotes...")
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, chunk in enumerate(chunks):
                chunk_start_time = time.time()
                msg = f"Lote {i + 1}/{total_chunks}: Processando {len(chunk)} arquivos..."
                status_text.write(msg);
                logging.info(msg)
                list_of_dfs = [extrair_dados_de_pdf(file, lista_disciplinas_validas) for file in chunk]
                df_chunk = pd.concat(list_of_dfs, ignore_index=True)
                if df_chunk.empty: continue
                mascara_exclusao = df_chunk['TURMA'].str.contains(regex_pattern, case=False, na=False)
                df_filtrado = df_chunk[~mascara_exclusao]
                if df_filtrado.empty: continue
                df_para_envio = df_filtrado.copy()
                df_para_envio['SEMANA'] = semana_para_envio
                msg = f"Lote {i + 1}/{total_chunks}: Enviando {len(df_para_envio)} registros para o BigQuery..."
                status_text.write(msg);
                logging.info(msg)
                sucesso = carregar_dados_no_bigquery(df_para_envio, creds, dataset_id, mode='append')
                if sucesso:
                    total_registros_enviados += len(df_para_envio)
                else:
                    logging.error(f"Falha ao enviar dados do lote {i + 1}.")

                # --- Gerenciamento de Memória Explícito ---
                del list_of_dfs, df_chunk, df_filtrado, df_para_envio
                gc.collect()

                tempo_lote = time.time() - chunk_start_time
                logging.info(f"Lote {i + 1} concluído em {formatar_tempo(tempo_lote)}.")
                progress_bar.progress((i + 1) / total_chunks)

            tempo_total = time.time() - tempo_inicio_total
            msg = f"Processamento Concluído! {total_registros_enviados} registros enviados em {formatar_tempo(tempo_total)}."
            st.success(msg);
            logging.info(msg)
            logging.info("--- PROCESSAMENTO FINALIZADO COM SUCESSO ---")
            st.balloons()
        except Exception as e:
            st.error(f"Ocorreu um erro crítico: {e}")
            logging.error("ERRO CRÍTICO NO PROCESSAMENTO", exc_info=True)

# --- Seção de Download do Log ---
st.markdown("---")
st.header("Relatório de Processamento (Logs)")

if os.path.exists(LOG_FILENAME):
    with open(LOG_FILENAME, "r") as f:
        log_content = f.read()

    st.text_area("Conteúdo do Log", log_content, height=300, key="log_area")

    st.download_button(
        label="📥 Baixar Arquivo de Log Completo",
        data=log_content,
        file_name="processing_log.txt",
        mime="text/plain",
    )
else:
    st.info("Nenhum processamento foi executado ainda. O arquivo de log será criado quando você iniciar o processo.")