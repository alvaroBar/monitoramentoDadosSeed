# ==============================================================================
# ARQUIVO ATUALIZADO: converttoledo.py
# Agora busca a última semana do BigQuery e permite que o usuário defina
# a semana para os novos registros.
# ==============================================================================

import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

# Importa as funções necessárias do nosso módulo loader
from bigquery_loader import autenticar_com_service_account, get_latest_week, autenticar_e_carregar


# --- Funções de Apoio ---

def processar_pdfs(lista_de_arquivos_pdf, disciplinas_validas, numero_da_semana):
    """
    Função principal que extrai os dados de uma lista de arquivos PDF.
    Agora recebe o número da semana como parâmetro.
    """
    dados_extraidos = []

    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"

    for arquivo_pdf in lista_de_arquivos_pdf:
        turma_atual = None
        nome_escola = "ESCOLA NÃO IDENTIFICADA"
        municipio = "MUNICÍPIO NÃO IDENTIFICADO"
        data_relatorio = "DATA NÃO IDENTIFICADA"

        with pdfplumber.open(arquivo_pdf) as pdf:
            # ... (O restante desta função de extração continua exatamente o mesmo)
            # A única mudança é na linha final, onde usamos o parâmetro 'numero_da_semana'
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
                            municipio = linha.split("SECRETARIA")[0].strip()
                            if i + 1 < len(linhas): nome_escola = linhas[i + 1].strip()
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
                        numero_da_semana,  # <-- MUDANÇA IMPORTANTE AQUI
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


# --- Interface do Streamlit ---

st.set_page_config(layout="wide")
st.title("Conversor LRCO: PDF ➡️ BigQuery 📄➡️☁️")

# --- Lógica de Estado para o DataFrame ---
if 'df_processado' not in st.session_state:
    st.session_state.df_processado = pd.DataFrame()

# --- Seção de Upload e Configuração ---
st.info("Passo 1: Carregue os arquivos PDF e a planilha de disciplinas.")
col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Selecione os arquivos PDF do relatório LRCO", type="pdf",
                                      accept_multiple_files=True)
with col2:
    disciplinas_file = st.file_uploader("Selecione a planilha com a lista oficial de disciplinas", type=["xlsx"])

if uploaded_files and disciplinas_file:
    if st.button("Processar Arquivos PDF"):
        try:
            disciplinas_df = pd.read_excel(disciplinas_file)
            lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]

            # Busca a última semana no BigQuery ANTES de processar os PDFs
            creds = autenticar_com_service_account()
            if creds:
                with st.spinner("Buscando última semana registrada no BigQuery..."):
                    ultima_semana = get_latest_week(creds)

                # Armazena a semana sugerida no estado da sessão
                st.session_state.ultima_semana = ultima_semana
                st.session_state.semana_sugerida = ultima_semana + 1

                with st.spinner("Processando PDFs... Isso pode levar alguns momentos."):
                    # Processa os PDFs com um número de semana temporário (0)
                    df_temp = processar_pdfs(uploaded_files, lista_disciplinas_validas, 0)
                    st.session_state.df_processado = df_temp  # Armazena no estado da sessão
            else:
                st.error("Não foi possível autenticar para buscar a última semana.")

        except Exception as e:
            st.error(f"Ocorreu um erro inesperado durante o processamento: {e}")

# --- Seção de Visualização e Envio ---
if not st.session_state.df_processado.empty:
    st.success(f"✅ Conversão concluída! {len(st.session_state.df_processado)} registros foram extraídos com sucesso.")

    st.markdown("---")
    st.subheader("Passo 2: Defina a Semana e Envie os Dados")

    col_info, col_input = st.columns(2)
    with col_info:
        st.metric("Última Semana no Banco de Dados", st.session_state.get('ultima_semana', 'N/A'))

    with col_input:
        semana_para_envio = st.number_input(
            "Confirme ou altere o número da semana para estes novos registros:",
            min_value=1,
            value=st.session_state.get('semana_sugerida', 1),
            step=1
        )

    # Atualiza a coluna 'SEMANA' no DataFrame com o valor escolhido pelo usuário
    df_para_envio = st.session_state.df_processado.copy()
    df_para_envio['SEMANA'] = semana_para_envio

    st.write("Pré-visualização dos dados a serem enviados:")
    st.dataframe(df_para_envio.head())

    if st.button("Enviar para o BigQuery"):
        with st.spinner("Conectando e carregando dados..."):
            sucesso = autenticar_e_carregar(df_para_envio)
            if sucesso:
                st.success(f"Dados da semana {semana_para_envio} enviados para o BigQuery com sucesso!")
                st.balloons()
                # Limpa o estado para um novo processamento
                st.session_state.df_processado = pd.DataFrame()
            else:
                st.error("Falha no envio dos dados. Verifique a mensagem de erro acima.")
