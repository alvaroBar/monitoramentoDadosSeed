# ==============================================================================
# ARQUIVO COMPLETO: 1_Processar_Relatórios_PDF.py (Versão Multilocatário)
# Página principal para a operação diária de processamento de PDFs.
# ==============================================================================

import streamlit as st
import pandas as pd
import pdfplumber
import re

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import autenticar_usuario, get_latest_week, carregar_dados_no_bigquery


def processar_pdfs(lista_de_arquivos_pdf, disciplinas_validas):
    """
    Função principal que extrai os dados de uma lista de arquivos PDF.
    """
    dados_extraidos = []

    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"

    nome_escola = "ESCOLA NÃO IDENTIFICADA"
    municipio = "MUNICÍPIO NÃO IDENTIFICADO"
    data_relatorio = "DATA NÃO IDENTIFICADA"

    for arquivo_pdf in lista_de_arquivos_pdf:
        turma_atual = None

        with pdfplumber.open(arquivo_pdf) as pdf:
            for page_num, page in enumerate(pdf.pages):
                texto_pagina = page.extract_text()
                if not texto_pagina: continue
                linhas = texto_pagina.split("\n")

                if page_num == 0:
                    for i, linha in enumerate(linhas):
                        if "ESTADO DO PARANÁ" in linha:
                            match_data = re.search(data_relatorio_re, linha)
                            if match_data: data_relatorio = match_data.group()
                        if "SECRETARIA DE ESTADO DA EDUCAÇÃO" in linha:
                            municipio_temp = linha.split("SECRETARIA")[0].strip()
                            if municipio_temp:
                                municipio = municipio_temp
                            if i + 1 < len(linhas):
                                nome_escola_temp = linhas[i + 1].strip()
                                if nome_escola_temp:
                                    nome_escola = nome_escola_temp

                for linha in linhas:
                    linha = linha.strip()
                    if " - " in linha and "TURMA" not in linha and "LANÇAMENTO" not in linha:
                        turma_atual = linha
                        continue
                    if not turma_atual: continue
                    horarios = re.findall(horario_re, linha)
                    registros = re.findall(registro_re, linha)
                    if not horarios: continue
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
                    if not disciplina_encontrada: continue

                    dados_extraidos.append([
                        0,  # Semana será definida pelo usuário
                        data_relatorio,
                        municipio,
                        nome_escola,
                        turma_atual,
                        horario,
                        disciplina_encontrada,
                        registro_aula,
                        registro_conteudo
                    ])

    colunas = [
        "SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA",
        "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"
    ]
    df = pd.DataFrame(dados_extraidos, columns=colunas)
    return df


# --- Configuração da Página ---
st.set_page_config(layout="wide")
st.title("Conversor LRCO: PDF ➡️ BigQuery 📄➡️☁️")

# --- Lógica de Autenticação e Mapeamento ---
autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

user_email = st.session_state.user_info.get("email", "Email não encontrado")
user_name = st.session_state.user_info.get("name", "Usuário")

OFFICE_MAPPING = st.secrets.get("office_mapping", {})
if user_email not in OFFICE_MAPPING:
    st.error(f"ERRO: O e-mail '{user_email}' não está autorizado. Contate o administrador para obter acesso.")
    st.stop()

dataset_id = OFFICE_MAPPING[user_email]

# --- Interface Principal Após Login ---
st.sidebar.success(f"Olá, {user_name}!")
if st.sidebar.button("Logout"):
    del st.session_state.credentials
    if 'user_info' in st.session_state:
        del st.session_state.user_info
    st.rerun()

# --- Lógica de Estado para o fluxo do aplicativo ---
if 'upload_key' not in st.session_state:
    st.session_state.upload_key = 0
if 'df_processado' not in st.session_state:
    st.session_state.df_processado = pd.DataFrame()
if 'processamento_concluido' not in st.session_state:
    st.session_state.processamento_concluido = False

# --- Passo 1: Upload e Processamento ---
st.info("Passo 1: Carregue os arquivos PDF e a planilha de disciplinas.")
col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Selecione os arquivos PDF", type="pdf", accept_multiple_files=True,
                                      key=f"pdf_uploader_{st.session_state.upload_key}")
with col2:
    disciplinas_file = st.file_uploader("Selecione a planilha de disciplinas", type=["xlsx"],
                                        key=f"disciplinas_uploader_{st.session_state.upload_key}")

if uploaded_files:
    if st.button("Remover Arquivos PDF"):
        st.session_state.upload_key += 1
        st.rerun()

if uploaded_files and disciplinas_file:
    if st.button("Processar Arquivos PDF"):
        try:
            disciplinas_df = pd.read_excel(disciplinas_file)
            lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]

            with st.spinner("Processando PDFs..."):
                df_temp = processar_pdfs(uploaded_files, lista_disciplinas_validas)
                st.session_state.df_processado = df_temp
                st.session_state.processamento_concluido = True
                st.rerun()

        except Exception as e:
            st.error(f"Ocorreu um erro durante o processamento: {e}")

# --- Passo 2 e 3: Configuração e Envio ---
if st.session_state.processamento_concluido and not st.session_state.df_processado.empty:
    st.success(f"✅ {len(st.session_state.df_processado)} registos foram extraídos com sucesso.")
    st.markdown("---")
    st.subheader("Passo 2: Configure os dados para envio")

    with st.spinner("A procurar a última semana registada..."):
        ultima_semana = get_latest_week(st.session_state.credentials, dataset_id)

    col_info, col_input = st.columns(2)
    with col_info:
        st.metric("Última Semana no Banco de Dados", ultima_semana)
    with col_input:
        semana_para_envio = st.number_input(
            "Confirme ou altere o número da semana para estes novos registos:",
            min_value=1, value=ultima_semana + 1, step=1
        )

    st.markdown("#### Filtrar Disciplinas")
    disciplinas_encontradas = sorted(st.session_state.df_processado['DISCIPLINA'].unique())
    disciplinas_selecionadas = st.multiselect(
        "Selecione as disciplinas que deseja enviar:",
        options=disciplinas_encontradas, default=disciplinas_encontradas
    )

    df_filtrado = st.session_state.df_processado[
        st.session_state.df_processado['DISCIPLINA'].isin(disciplinas_selecionadas)]
    df_para_envio = df_filtrado.copy()
    df_para_envio['SEMANA'] = semana_para_envio

    st.markdown("---")
    st.subheader("Passo 3: Envie os Dados")

    if not df_para_envio.empty:
        st.write(f"**{len(df_para_envio)}** registos prontos para serem enviados. Pré-visualização:")
        st.dataframe(df_para_envio.head())

        if st.button("Enviar para o BigQuery"):
            with st.spinner("A conectar e a carregar os dados..."):
                sucesso = carregar_dados_no_bigquery(df_para_envio, st.session_state.credentials, dataset_id, 'append')
                if sucesso:
                    st.session_state.envio_sucesso = True
                    st.session_state.semana_enviada = semana_para_envio
                    st.rerun()
                else:
                    st.error("Falha no envio dos dados. Verifique a mensagem de erro acima.")
    else:
        st.warning("Nenhuma disciplina foi selecionada. Nenhum dado será enviado.")

elif st.session_state.get('envio_sucesso', False):
    st.success(f"Dados da semana {st.session_state.semana_enviada} enviados para o BigQuery com sucesso!")
    st.balloons()
    if st.button("Iniciar Novo Lançamento"):
        # Limpa o estado para um novo ciclo
        st.session_state.processamento_concluido = False
        st.session_state.df_processado = pd.DataFrame()
        st.session_state.envio_sucesso = False
        st.session_state.upload_key += 1
        st.rerun()