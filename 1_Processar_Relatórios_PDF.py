# ==============================================================================
# ARQUIVO COMPLETO: 1_Processar_Relatórios_PDF.py (Versão Multilocatário)
# Página principal para o processamento diário de relatórios PDF.
# ==============================================================================

import streamlit as st
import pandas as pd
import re
import pdfplumber
from io import BytesIO

# Importa as funções do nosso módulo loader
from bigquery_loader import (
    autenticar_usuario,
    get_latest_week,
    carregar_dados_no_bigquery
)


# --- Funções de Apoio ---

def processar_pdfs(lista_de_arquivos_pdf, disciplinas_validas, numero_da_semana):
    """
    Função principal que extrai os dados de uma lista de arquivos PDF,
    mantendo o contexto (escola, município) entre os arquivos.
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
                            if municipio_temp: municipio = municipio_temp
                            if i + 1 < len(linhas):
                                nome_escola_temp = linhas[i + 1].strip()
                                if nome_escola_temp: nome_escola = nome_escola_temp

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
                        numero_da_semana, data_relatorio, municipio, nome_escola,
                        turma_atual, horario, disciplina_encontrada,
                        registro_aula, registro_conteudo
                    ])

    colunas = [
        "SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA",
        "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"
    ]
    return pd.DataFrame(dados_extraidos, columns=colunas)


# --- Interface do Streamlit ---

st.set_page_config(layout="wide")
st.title("Conversor LRCO: PDF ➡️ BigQuery 📄➡️☁️")

# --- Lógica de Autenticação e Mapeamento ---
autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com sua conta Google para continuar.")
    st.stop()

user_email = st.session_state.user_info['email']
creds = st.session_state.credentials

try:
    dataset_id = st.secrets.office_mapping[user_email]
except KeyError:
    st.error(f"O e-mail **{user_email}** não está autorizado a usar este sistema.")
    st.error("Por favor, contate o administrador para solicitar acesso.")
    st.stop()

st.sidebar.success(f"Logado como: **{user_email}**")
st.sidebar.info(f"Escritório (Dataset): **{dataset_id}**")
if st.sidebar.button("Logout"):
    del st.session_state.credentials
    if 'user_info' in st.session_state: del st.session_state.user_info
    st.rerun()

# --- Lógica Principal da Aplicação ---
if 'df_processado' not in st.session_state: st.session_state.df_processado = pd.DataFrame()
if 'upload_success' not in st.session_state: st.session_state.upload_success = False
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0


def reset_workflow():
    st.session_state.df_processado = pd.DataFrame()
    st.session_state.upload_success = False
    st.session_state.uploader_key += 1


st.info("Passo 1: Carregue os arquivos PDF e a planilha de disciplinas.")
col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Selecione os arquivos PDF", type="pdf", accept_multiple_files=True,
                                      key=f"pdf_uploader_{st.session_state.uploader_key}")
    if uploaded_files: st.button("Remover Todos os Arquivos", on_click=reset_workflow)
with col2:
    disciplinas_file = st.file_uploader("Selecione a planilha de disciplinas", type=["xlsx"])

if uploaded_files and disciplinas_file:
    if st.button("Processar Arquivos PDF"):
        st.session_state.upload_success = False
        try:
            disciplinas_df = pd.read_excel(disciplinas_file)
            lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]

            with st.spinner("Buscando última semana registrada..."):
                st.session_state.ultima_semana = get_latest_week(creds, dataset_id)
                st.session_state.semana_sugerida = st.session_state.ultima_semana + 1

            with st.spinner("Processando PDFs..."):
                st.session_state.df_processado = processar_pdfs(uploaded_files, lista_disciplinas_validas, 0)
        except Exception as e:
            st.error(f"Ocorreu um erro no processamento: {e}")

if not st.session_state.df_processado.empty:
    if st.session_state.upload_success:
        st.success(
            f"Dados da semana {st.session_state.get('semana_enviada', '')} enviados para o BigQuery com sucesso!")
        st.balloons()
        st.button("🎉 Iniciar Novo Lançamento", on_click=reset_workflow)
    else:
        st.success(f"✅ Conversão concluída! {len(st.session_state.df_processado)} registros extraídos.")
        st.markdown("---")
        st.subheader("Passo 2: Configure os dados para envio")

        col_info, col_input = st.columns(2)
        with col_info:
            st.metric("Última Semana no Banco de Dados", st.session_state.get('ultima_semana', 'N/A'))
        with col_input:
            semana_para_envio = st.number_input("Confirme o número da semana para estes registros:", min_value=1,
                                                value=st.session_state.get('semana_sugerida', 1), step=1)

        st.markdown("#### Filtrar Disciplinas")
        disciplinas_encontradas = sorted(st.session_state.df_processado['DISCIPLINA'].unique())
        disciplinas_selecionadas = st.multiselect("Selecione as disciplinas que deseja enviar:",
                                                  options=disciplinas_encontradas, default=disciplinas_encontradas)

        df_filtrado = st.session_state.df_processado[
            st.session_state.df_processado['DISCIPLINA'].isin(disciplinas_selecionadas)]
        df_para_envio = df_filtrado.copy()
        df_para_envio['SEMANA'] = semana_para_envio

        st.markdown("---")
        st.subheader("Passo 3: Envie os Dados")

        if not df_para_envio.empty:
            st.write(f"**{len(df_para_envio)}** registros prontos para serem enviados. Pré-visualização:")
            st.dataframe(df_para_envio.head())
            if st.button("Enviar para o BigQuery"):
                with st.spinner("Conectando e carregando dados..."):
                    sucesso = carregar_dados_no_bigquery(df_para_envio, creds, dataset_id, 'append')
                    if sucesso:
                        st.session_state.semana_enviada = semana_para_envio
                        st.session_state.upload_success = True
                        st.rerun()
                    else:
                        st.error("Falha no envio dos dados.")
        else:
            st.warning("Nenhuma disciplina selecionada.")