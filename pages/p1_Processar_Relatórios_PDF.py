# ==============================================================================
# ARQUIVO DA PÁGINA: p1_Processar_Relatorios_PDF.py
# Reestruturado para processamento em lotes (arquivo por arquivo) para
# resolver o problema de esgotamento de memória.
# ==============================================================================

import streamlit as st
import pdfplumber
import pandas as pd
import re
import time
from streamlit_autorefresh import st_autorefresh

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import autenticar_usuario, get_latest_week, carregar_dados_no_bigquery


# --- Funções de Apoio ---
def formatar_tempo(segundos):
    """Converte segundos em uma string formatada (minutos e segundos)."""
    mins, segs = divmod(segundos, 60)
    if mins > 0:
        return f"{int(mins)}m {int(segs)}s"
    return f"{int(segs)}s"


# A função de processamento agora só precisa do arquivo e das disciplinas
def extrair_dados_de_pdf(arquivo_pdf, disciplinas_validas):
    """Extrai dados de um único arquivo PDF."""
    dados_extraidos = []
    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"

    nome_escola = "ESCOLA NÃO IDENTIFICADA"
    municipio = "MUNICÍPIO NÃO IDENTIFICADO"
    data_relatorio = "DATA NÃO IDENTIFICADA"

    turma_atual = None

    with pdfplumber.open(arquivo_pdf) as pdf:
        for page_num, page in enumerate(pdf.pages):
            texto_pagina = page.extract_text()
            if not texto_pagina:
                continue

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

            for line_num, linha in enumerate(linhas):
                try:
                    linha = linha.strip()
                    if " - " in linha and "TURMA" not in linha.upper() and "LANÇAMENTO" not in linha.upper():
                        turma_atual = linha
                        continue

                    if not turma_atual:
                        continue

                    horarios = re.findall(horario_re, linha)
                    if not horarios:
                        continue

                    registros = re.findall(registro_re, linha)
                    horario = horarios[0]
                    pos_horario = linha.find(horario)
                    pos_fim_horario = pos_horario + len(horario)
                    registro_aula = registros[0] if len(registros) >= 1 else "Sem registro"
                    registro_conteudo = registros[1] if len(registros) >= 2 else "Sem registro"
                    pos_registro = linha.find(registros[0]) if registros else len(linha)
                    disciplina_raw = linha[pos_fim_horario:pos_registro].strip()
                    disciplina_encontrada = None

                    for nome_disciplina in disciplinas_validas:
                        if nome_disciplina in disciplina_raw.upper():
                            disciplina_encontrada = nome_disciplina
                            break

                    if not disciplina_encontrada:
                        continue

                    dados_extraidos.append([
                        0, data_relatorio, municipio, nome_escola,
                        turma_atual, horario, disciplina_encontrada,
                        registro_aula, registro_conteudo
                    ])
                except Exception:
                    # Ignora erros de linha para não interromper o lote
                    continue

    colunas = [
        "SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA",
        "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"
    ]
    return pd.DataFrame(dados_extraidos, columns=colunas)


# --- Interface do Streamlit ---

st.set_page_config(layout="wide")
st.title("Processar e Enviar Relatórios PDF 📄")

autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

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
    st.error("ERRO DE CONFIGURAÇÃO: O mapeamento [office_mapping] não foi encontrado nos Segredos do Streamlit.")
    st.stop()

with st.sidebar:
    st.subheader(f"Olá, {user_name}!")
    if st.button("Logout", key="logout_processar"):
        st.session_state.clear()
        st.rerun()

st_autorefresh(interval=5 * 60 * 1000, key="session_refresher_processar")

st.header("Passo 1: Carregue os Arquivos")

col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Selecione os arquivos PDF", type="pdf", accept_multiple_files=True)
with col2:
    disciplinas_file = st.file_uploader("Selecione a planilha de disciplinas", type=["xlsx"])

st.markdown("---")
st.header("Passo 2: Configure o Envio")

creds = st.session_state.credentials
dataset_id = st.session_state.dataset_id
ultima_semana = get_latest_week(creds, dataset_id)
semana_sugerida = ultima_semana + 1

semana_para_envio = st.number_input(
    "Digite o número da semana para os registros que serão enviados:",
    min_value=1, value=semana_sugerida, step=1
)

st.markdown("---")

if uploaded_files and disciplinas_file:
    if st.button(f"Processar e Enviar {len(uploaded_files)} Arquivos para a Semana {semana_para_envio}",
                 use_container_width=True, type="primary"):
        try:
            # Carrega a lista de disciplinas uma única vez
            disciplinas_df = pd.read_excel(disciplinas_file)
            lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]

            termos_para_excluir = ['aut', 'mec', 'eja', 'ali', 'gas', 'eletrom']
            regex_pattern = '|'.join(termos_para_excluir)

            total_files = len(uploaded_files)
            progress_bar = st.progress(0, text="Iniciando processamento em lotes...")
            status_text = st.empty()
            total_registros_enviados = 0

            for i, file in enumerate(uploaded_files):
                progress_text = f"Processando arquivo {i + 1}/{total_files}: {file.name}"
                progress_bar.progress((i + 1) / total_files, text=progress_text)
                status_text.info(progress_text)

                # 1. Extrai dados de um único PDF
                df_temp = extrair_dados_de_pdf(file, lista_disciplinas_validas)

                if df_temp.empty:
                    continue

                # 2. Aplica filtro automático
                mascara_exclusao = df_temp['TURMA'].str.contains(regex_pattern, case=False, na=False)
                df_filtrado = df_temp[~mascara_exclusao]

                if df_filtrado.empty:
                    continue

                # 3. Prepara e envia para o BigQuery
                df_para_envio = df_filtrado.copy()
                df_para_envio['SEMANA'] = semana_para_envio

                sucesso = carregar_dados_no_bigquery(df_para_envio, creds, dataset_id, mode='append')

                if sucesso:
                    total_registros_enviados += len(df_para_envio)
                else:
                    st.error(f"Falha ao enviar dados do arquivo: {file.name}. Continuando para o próximo...")

            progress_bar.empty()
            status_text.empty()
            st.success(
                f"Processamento concluído! {total_registros_enviados} registros foram enviados com sucesso para a semana {semana_para_envio}.")
            st.balloons()

        except Exception as e:
            st.error(f"Ocorreu um erro crítico durante o processamento em lote: {e}")