# ==============================================================================
# ARQUIVO DA PÁGINA: p1_Extrair_Dados_PDF.py
# ADICIONADO: Lógica para suavizar a barra de progresso e um botão para
# cancelar a extração de dados durante a execução.
# ==============================================================================

import streamlit as st
import pandas as pd
import re
import time
import pdfplumber
import gc

st.set_page_config(layout="wide")
st.title("Passo 1: Extrair Dados dos Relatórios PDF 📄")


def extrair_dados_de_pdf(arquivo_pdf, disciplinas_validas):
    dados_extraidos = []
    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"
    nome_escola, municipio, data_relatorio = "N/A", "N/A", "N/A"
    turma_atual = None
    cabecalho_lido = False
    data_ja_encontrada = False

    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page_num, page in enumerate(pdf.pages):
                texto_pagina = page.extract_text()
                if not texto_pagina: continue
                linhas = texto_pagina.split("\n")
                if page_num == 0:
                    for idx, linha in enumerate(linhas):
                        if not data_ja_encontrada:
                            match_data = re.search(data_relatorio_re, linha)
                            if match_data:
                                data_relatorio = match_data.group()
                                data_ja_encontrada = True
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
                            data_relatorio, municipio, nome_escola, turma_atual, horario,
                            disciplina_encontrada, registro_aula, registro_conteudo
                        ])
    except Exception:
        return pd.DataFrame()
    colunas = ["DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA", "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA",
               "REGISTRO_DE_CONTEUDO"]
    return pd.DataFrame(dados_extraidos, columns=colunas)


# --- Lógica de Estado da Interface ---
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'cancel_extraction' not in st.session_state:
    st.session_state.cancel_extraction = False

# --- Interface ---
st.info(
    "Esta página é dedicada a ler os arquivos PDF e consolidar todos os dados. Ao final, você fará o download de um arquivo único para ser enviado na próxima etapa.")

# Desabilita os uploaders durante o processamento para evitar inconsistências
is_disabled = st.session_state.processing

col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Selecione os arquivos PDF para extração", type="pdf", accept_multiple_files=True,
                                      disabled=is_disabled)
with col2:
    disciplinas_file = st.file_uploader("Selecione a planilha de disciplinas", type=["xlsx"], disabled=is_disabled)

# Placeholder para os botões de ação (Iniciar/Cancelar)
action_placeholder = st.empty()

if uploaded_files and disciplinas_file:
    if not st.session_state.processing:
        if action_placeholder.button(f"Iniciar Extração de {len(uploaded_files)} Arquivos", use_container_width=True,
                                     type="primary"):
            st.session_state.processing = True
            st.session_state.cancel_extraction = False
            if 'final_df' in st.session_state:
                del st.session_state.final_df
            st.rerun()

if st.session_state.processing:
    # Mostra o botão de cancelar e a barra de progresso
    if action_placeholder.button("Cancelar Processo", use_container_width=True):
        st.session_state.cancel_extraction = True
        # Não precisa de rerun, o loop vai detectar a flag

    try:
        disciplinas_df = pd.read_excel(disciplinas_file)
        lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]

        all_dfs = []
        progress_bar = st.progress(0, "Iniciando...")

        sorted_files = sorted(uploaded_files, key=lambda f: f.name)
        total_files = len(sorted_files)

        for i, file in enumerate(sorted_files):
            # Verifica se o cancelamento foi solicitado
            if st.session_state.cancel_extraction:
                st.warning("Extração cancelada pelo usuário.")
                break

            df_temp = extrair_dados_de_pdf(file, lista_disciplinas_validas)
            if not df_temp.empty:
                all_dfs.append(df_temp)

            # Atualiza a barra de progresso
            progress_bar.progress((i + 1) / total_files, f"Processado arquivo {i + 1}/{total_files}: {file.name}")

            # --- LÓGICA PARA SUAVIZAR A BARRA ---
            time.sleep(0.01)

        # Após o loop, verifica se foi cancelado ou concluído
        if not st.session_state.cancel_extraction:
            if all_dfs:
                st.session_state.final_df = pd.concat(all_dfs, ignore_index=True)
                del all_dfs
                gc.collect()
            else:
                st.warning("Nenhum dado válido foi extraído dos arquivos.")

    except Exception as e:
        st.error(f"Ocorreu um erro crítico durante a extração: {e}")

    finally:
        # Reseta os estados para permitir uma nova execução
        st.session_state.processing = False
        st.session_state.cancel_extraction = False
        st.rerun()

if 'final_df' in st.session_state and not st.session_state.processing:
    df_final = st.session_state.final_df
    st.success(f"Extração Concluída! {len(df_final)} registros foram lidos.")
    st.dataframe(df_final.head())

    parquet_data = df_final.to_parquet(index=False)

    st.download_button(
        label="📥 Baixar Arquivo de Dados (.parquet)",
        data=parquet_data,
        file_name="dados_extraidos.parquet",
        mime="application/octet-stream",
        use_container_width=True,
        help="Clique para baixar o arquivo com todos os dados. Em seguida, vá para a página 'Carregar Dados para o BigQuery'."
    )