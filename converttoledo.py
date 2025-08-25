# ==============================================================================
# ARQUIVO FINAL: converttoledo.py
# Este aplicativo Streamlit processa relatórios LRCO de PDFs, valida as
# disciplinas, e envia os dados limpos para uma tabela no Google BigQuery.
# ==============================================================================

import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

# Importa as funções de autenticação e carregamento do BigQuery
# (O arquivo bigquery_loader.py deve estar na mesma pasta)
from bigquery_loader import autenticar_e_obter_credenciais, carregar_dados_no_bigquery


# --- Funções de Apoio ---

def processar_pdfs(lista_de_arquivos_pdf, disciplinas_validas):
    """
    Função principal que extrai os dados de uma lista de arquivos PDF.

    Args:
        lista_de_arquivos_pdf: Uma lista de arquivos PDF carregados pelo Streamlit.
        disciplinas_validas: Uma lista de nomes de disciplinas para validação.

    Returns:
        Um DataFrame do Pandas com os dados extraídos e limpos.
    """
    dados_extraidos = []

    # Expressões Regulares para encontrar os padrões de dados nos PDFs
    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"

    for arquivo_pdf in lista_de_arquivos_pdf:
        turma_atual = None
        # Valores padrão caso a extração falhe
        nome_escola = "ESCOLA NÃO IDENTIFICADA"
        municipio = "MUNICÍPIO NÃO IDENTIFICADO"
        data_relatorio = "DATA NÃO IDENTIFICADA"
        semana = 0  # Valor padrão para a semana

        with pdfplumber.open(arquivo_pdf) as pdf:
            for page_num, page in enumerate(pdf.pages):
                texto_pagina = page.extract_text()
                if not texto_pagina:
                    continue

                linhas = texto_pagina.split("\n")

                # Tenta extrair informações do cabeçalho, geralmente na primeira página
                if page_num == 0:
                    for i, linha in enumerate(linhas):
                        if "ESTADO DO PARANÁ" in linha:
                            match_data = re.search(data_relatorio_re, linha)
                            if match_data:
                                data_relatorio = match_data.group()
                        if "SECRETARIA DE ESTADO DA EDUCAÇÃO" in linha:
                            municipio = linha.split("SECRETARIA")[0].strip()
                            if i + 1 < len(linhas):
                                nome_escola = linhas[i + 1].strip()

                # Processa cada linha da página
                for linha in linhas:
                    linha = linha.strip()
                    # Lógica para identificar a linha que contém a "Turma"
                    if " - " in linha and "TURMA" not in linha and "LANÇAMENTO" not in linha:
                        turma_atual = linha
                        continue
                    if not turma_atual:
                        continue

                    horarios = re.findall(horario_re, linha)
                    registros = re.findall(registro_re, linha)

                    if not horarios:
                        continue

                    horario = horarios[0]
                    pos_horario = linha.find(horario)
                    pos_fim_horario = pos_horario + len(horario)

                    # Atribui os registros de aula e conteúdo, com "Sem registro" como padrão
                    registro_aula = registros[0] if len(registros) >= 1 else "Sem registro"
                    registro_conteudo = registros[1] if len(registros) >= 2 else "Sem registro"

                    pos_registro = linha.find(registros[0]) if registros else len(linha)
                    disciplina_raw = linha[pos_fim_horario:pos_registro].strip()

                    # Valida a disciplina contra a lista oficial
                    disciplina_encontrada = None
                    for nome_disciplina in disciplinas_validas:
                        if nome_disciplina in disciplina_raw.upper():
                            disciplina_encontrada = nome_disciplina
                            break

                    if not disciplina_encontrada:
                        continue  # Pula a linha se a disciplina não for reconhecida

                    dados_extraidos.append([
                        semana,  # Adicionado aqui
                        data_relatorio,
                        municipio,
                        nome_escola,
                        turma_atual,
                        horario,
                        disciplina_encontrada,
                        registro_aula,
                        registro_conteudo
                    ])

    # Define as colunas do DataFrame final
    colunas = [
        "SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA",
        "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"
    ]
    df = pd.DataFrame(dados_extraidos, columns=colunas)
    return df


# --- Interface do Streamlit ---

st.set_page_config(layout="wide")
st.title("Conversor LRCO: PDF ➡️ BigQuery 📄➡️☁️")

st.info(
    "Esta aplicação extrai dados de relatórios LRCO em formato PDF, valida as informações e as envia para o banco de dados central no BigQuery.")

# --- Seção de Upload de Arquivos ---
col1, col2 = st.columns(2)

with col1:
    uploaded_files = st.file_uploader("1. Selecione os arquivos PDF do relatório LRCO", type="pdf",
                                      accept_multiple_files=True)

with col2:
    disciplinas_file = st.file_uploader("2. Envie a planilha com a lista oficial de disciplinas", type=["xlsx"])

# --- Lógica Principal da Aplicação ---
if uploaded_files and disciplinas_file:
    try:
        # Carrega a lista de disciplinas e prepara para validação
        disciplinas_df = pd.read_excel(disciplinas_file)
        lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]

        with st.spinner("Processando PDFs... Isso pode levar alguns momentos."):
            # Chama a função para processar todos os arquivos de uma vez
            df_processado = processar_pdfs(uploaded_files, lista_disciplinas_validas)

        if not df_processado.empty:
            st.success(f"✅ Conversão concluída! {len(df_processado)} registros foram extraídos com sucesso.")
            st.dataframe(df_processado)

            # --- Seção de Upload para o BigQuery ---
            st.markdown("---")
            st.subheader("🚀 3. Enviar Dados para o Banco de Dados")

            if st.button("Enviar para o BigQuery"):
                with st.spinner(
                        "Conectando e carregando dados... Por favor, verifique o navegador para login, se necessário."):
                    creds = autenticar_e_obter_credenciais()

                    if creds:
                        sucesso = carregar_dados_no_bigquery(df_processado, creds)

                        if sucesso:
                            st.success("Dados enviados para o BigQuery com sucesso!")
                            st.balloons()
                        else:
                            st.error(
                                "Falha no envio dos dados. Verifique o console ou terminal para mais detalhes do erro.")
                    else:
                        st.error("Não foi possível obter as credenciais de autenticação.")
        else:
            st.warning(
                "Nenhum registro válido foi encontrado nos PDFs processados. Verifique se os arquivos estão corretos e se as disciplinas correspondem à lista.")

    except Exception as e:
        st.error(f"Ocorreu um erro inesperado durante o processamento: {e}")
        st.error("Por favor, verifique se os arquivos enviados são válidos e tente novamente.")

else:
    st.markdown("---")
    st.write("Aguardando o envio dos arquivos PDF e da planilha de disciplinas para iniciar...")