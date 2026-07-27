# ==============================================================================
# ARQUIVO DA PÁGINA: 1_Extrair_Dados_PDF.py
# VERSÃO FINAL: Excel formatado (Auto-ajuste e Alerta de Pendências)
# ==============================================================================

import streamlit as st
import pandas as pd
import re
import time
import pdfplumber
import gc
import io  # Necessário para criar os arquivos Excel/CSV em memória
from services import auth_service
from streamlit_autorefresh import st_autorefresh
from utils import interface
from services.backup_service import verificar_e_executar_backup_semanal

# Configuração da página
st.set_page_config(
    page_title="1. Extrair Dados (PDF)",
    page_icon="📄",
    layout="wide"
)

st.title("📄 1. Extrair Dados (PDF)")
interface.exibir_cabecalho_ano()

# --- Autenticação e Sidebar ---
auth_service.autenticar_usuario()

if 'user_info' in st.session_state:
    user_info = st.session_state.user_info
    user_name = user_info.get("name", "Usuário")

    with st.sidebar:
        st.subheader(f"Olá, {user_name}!")
        if st.button("Logout"):
            auth_service.logout_usuario()
else:
    pass

# Auto-refresh para manter a sessão ativa
st_autorefresh(interval=10 * 60 * 1000, key="refresher_extração_dados")

verificar_e_executar_backup_semanal(forcar_teste=True)


def extrair_dados_de_pdf(arquivo_pdf, disciplinas_validas):
    """Extrai dados de um arquivo PDF e retorna um DataFrame."""
    dados_extraidos = []
    # Regex padrões
    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"

    nome_escola, municipio, data_relatorio = "N/A", "N/A", "N/A"
    turma_atual = None
    data_ja_encontrada = False

    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page_num, page in enumerate(pdf.pages):
                texto_pagina = page.extract_text()
                if not texto_pagina: continue
                linhas = texto_pagina.split("\n")

                # Cabeçalho (apenas na primeira página)
                if page_num == 0:
                    for idx, linha in enumerate(linhas):
                        if not data_ja_encontrada and (match_data := re.search(data_relatorio_re, linha)):
                            data_relatorio = match_data.group()
                            data_ja_encontrada = True
                        if "SECRETARIA DE ESTADO DA EDUCAÇÃO" in linha.upper():
                            if municipio_temp := linha.split("SECRETARIA")[0].strip():
                                municipio = municipio_temp
                            if idx + 1 < len(linhas) and (nome_escola_temp := linhas[idx + 1].strip()):
                                nome_escola = nome_escola_temp

                # Processamento das linhas
                for linha in linhas:
                    linha = linha.strip()
                    # Identifica a Turma
                    if " - " in linha and "TURMA" not in linha.upper() and "LANÇAMENTO" not in linha.upper():
                        turma_atual = linha
                        continue
                    if not turma_atual: continue

                    # Identifica Horários
                    if not (horarios := re.findall(horario_re, linha)): continue

                    registros = re.findall(registro_re, linha)
                    horario = horarios[0]
                    pos_horario = linha.find(horario)
                    pos_fim_horario = pos_horario + len(horario)

                    registro_aula = registros[0] if len(registros) >= 1 else "Sem registro"
                    registro_conteudo = registros[1] if len(registros) >= 2 else "Sem registro"

                    pos_registro = linha.find(registros[0]) if registros else len(linha)
                    disciplina_raw = linha[pos_fim_horario:pos_registro].strip()

                    # Validação de Disciplina
                    matches = [d for d in disciplinas_validas if d in disciplina_raw.upper()]

                    if matches:
                        disciplina_encontrada = max(matches, key=len)
                        dados_extraidos.append([
                            data_relatorio, municipio, nome_escola, turma_atual, horario,
                            disciplina_encontrada, registro_aula, registro_conteudo
                        ])
    except Exception as e:
        st.warning(
            f"Atenção: Ocorreu um erro ao processar o arquivo '{arquivo_pdf.name}'. Este arquivo será ignorado. (Erro: {e})")
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
    "Esta página lê os arquivos PDF e consolida os dados. Ao final, baixe o arquivo PARQUET para o sistema, ou Excel/CSV para análise manual.")

is_disabled = st.session_state.processing
col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Selecione os arquivos PDF para extração", type="pdf", accept_multiple_files=True,
                                      disabled=is_disabled)
with col2:
    disciplinas_file = st.file_uploader("Selecione a planilha de disciplinas", type=["xlsx"], disabled=is_disabled)

_, col_btn = st.columns([3, 1])
action_placeholder = col_btn.empty()

# Botão Iniciar
if uploaded_files and disciplinas_file and not st.session_state.processing:
    if action_placeholder.button(f"Iniciar Extração de {len(uploaded_files)} Arquivos", type="secondary"):
        st.session_state.processing = True
        st.session_state.cancel_extraction = False
        if 'final_df' in st.session_state:
            del st.session_state.final_df
        st.rerun()

# Processamento
if st.session_state.processing:
    if action_placeholder.button("Cancelar Processo", type="primary"):
        st.session_state.cancel_extraction = True

    try:
        disciplinas_df = pd.read_excel(disciplinas_file)
        lista_disciplinas_validas = [str(d).strip().upper() for d in disciplinas_df.iloc[:, 0].dropna().unique()]
        all_dfs = []
        progress_bar = st.progress(0, "Iniciando...")
        sorted_files = sorted(uploaded_files, key=lambda f: f.name)
        total_files = len(sorted_files)

        for i, file in enumerate(sorted_files):
            if st.session_state.cancel_extraction:
                st.warning("Extração cancelada pelo usuário.")
                break
            df_temp = extrair_dados_de_pdf(file, lista_disciplinas_validas)
            if not df_temp.empty:
                all_dfs.append(df_temp)
            progress_bar.progress((i + 1) / total_files, f"Processado arquivo {i + 1}/{total_files}: {file.name}")
            time.sleep(0.01)

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
        st.session_state.processing = False
        st.session_state.cancel_extraction = False
        st.rerun()

# --- Área de Sucesso e Downloads ---
if 'final_df' in st.session_state and not st.session_state.processing:
    df_final = st.session_state.final_df
    st.success(f"Extração Concluída! {len(df_final)} registros foram lidos.")
    st.dataframe(df_final.head())

    # 1. Preparar PARQUET (Para o Sistema)
    parquet_data = df_final.to_parquet(index=False)

    # 2. Preparar EXCEL (Para o Usuário) - COM FORMATAÇÃO AVANÇADA
    excel_buffer = io.BytesIO()

    # Usamos o 'xlsxwriter' como engine para ter controle visual
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Dados Extraídos')

        # Acessar os objetos do xlsxwriter para aplicar estilos
        workbook = writer.book
        worksheet = writer.sheets['Dados Extraídos']

        # Formato para destaque (Fundo Vermelho Claro, Texto Vermelho Escuro)
        formato_alerta = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})

        # Dimensões do DataFrame
        (max_row, max_col) = df_final.shape

        # APLICAÇÃO 1: Ajuste Automático de Largura das Colunas
        for i, col in enumerate(df_final.columns):
            # Calcula o tamanho máximo do conteúdo na coluna ou o tamanho do cabeçalho
            # Adiciona um pouco de margem (+2)
            max_len = max(
                df_final[col].astype(str).map(len).max(),
                len(str(col))
            ) + 2
            worksheet.set_column(i, i, max_len)

        # APLICAÇÃO 2: Formatação Condicional para "Sem registro"
        # Aplica em todas as células de dados
        worksheet.conditional_format(1, 0, max_row, max_col - 1, {
            'type': 'text',
            'criteria': 'containing',
            'value': 'Sem registro',
            'format': formato_alerta
        })

    excel_data = excel_buffer.getvalue()

    # 3. Preparar CSV (Para o Usuário)
    csv_data = df_final.to_csv(index=False).encode('utf-8')

    st.divider()
    st.write("### 📥 Opções de Download")

    col_sis, col_analise1, col_analise2 = st.columns([1.5, 1, 1])

    with col_sis:
        st.info("Para continuar no sistema:")
        st.download_button(
            label="📥 Baixar .parquet (Obrigatório)",
            data=parquet_data,
            file_name="dados_extraidos.parquet",
            mime="application/octet-stream",
            type="primary",
            help="Este é o arquivo que você deve carregar na próxima página do sistema."
        )

    with col_analise1:
        st.warning("Para análise manual:")
        st.download_button(
            label="📊 Baixar Excel (.xlsx)",
            data=excel_data,
            file_name="analise_manual_formatada.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Baixe este arquivo para ver os dados com formatação de pendências e colunas ajustadas."
        )

    with col_analise2:
        st.write("")  # Espaçamento
        st.write("")  # Espaçamento
        st.download_button(
            label="📝 Baixar CSV",
            data=csv_data,
            file_name="analise_manual.csv",
            mime="text/csv",
            help="Arquivo de texto simples separado por vírgulas."
        )