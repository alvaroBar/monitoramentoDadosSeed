# ==============================================================================
# ARQUIVO DA PÁGINA: p1_Processar_Relatorios_PDF.py
# Adicionado Modo de Depuração e tratamento de erros (try/except) para
# evitar que o programa trave durante o processamento de PDFs.
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


# A função de processamento agora aceita um parâmetro "debug_mode"
def processar_pdfs(lista_de_arquivos_pdf, disciplinas_validas, progress_bar, status_text, debug_mode=False):
    """
    Função principal que extrai os dados de uma lista de arquivos PDF,
    com modo de depuração opcional.
    """
    dados_extraidos = []
    total_arquivos = len(lista_de_arquivos_pdf)
    tempo_inicio = time.time()

    horario_re = r"\d{2}:\d{2}:\d{2}"
    registro_re = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}"
    data_relatorio_re = r"\b\d{2}/\d{2}/\d{4}\b"

    nome_escola = "ESCOLA NÃO IDENTIFICADA"
    municipio = "MUNICÍPIO NÃO IDENTIFICADO"
    data_relatorio = "DATA NÃO IDENTIFICADA"
    semana = 0

    for i, arquivo_pdf in enumerate(lista_de_arquivos_pdf):
        if debug_mode:
            st.write(f"---")
            st.write(f"**DEBUG: Iniciando processamento do arquivo `{arquivo_pdf.name}`**")

        progresso_atual = (i + 1) / total_arquivos
        tempo_decorrido = time.time() - tempo_inicio

        if i > 0:
            tempo_medio_por_arquivo = tempo_decorrido / (i + 1)
            arquivos_restantes = total_arquivos - (i + 1)
            tempo_restante_estimado = tempo_medio_por_arquivo * arquivos_restantes
            texto_progresso = f"Processando arquivo {i + 1} de {total_arquivos}... Tempo restante estimado: {formatar_tempo(tempo_restante_estimado)}"
        else:
            texto_progresso = f"Processando arquivo {i + 1} de {total_arquivos}..."

        progress_bar.progress(progresso_atual, text=texto_progresso)
        status_text.info(f"Lendo arquivo: `{arquivo_pdf.name}`")

        turma_atual = None

        with pdfplumber.open(arquivo_pdf) as pdf:
            for page_num, page in enumerate(pdf.pages):
                if debug_mode:
                    st.write(f"**DEBUG:** Lendo página `{page_num + 1}`...")

                texto_pagina = page.extract_text()
                if not texto_pagina:
                    if debug_mode:
                        st.warning(f"**DEBUG:** Página `{page_num + 1}` sem texto extraível.")
                    continue

                linhas = texto_pagina.split("\n")

                if page_num == 0:
                    for idx, linha in enumerate(linhas):
                        if "ESTADO DO PARANÁ" in linha:
                            match_data = re.search(data_relatorio_re, linha)
                            if match_data: data_relatorio = match_data.group()
                        if "SECRETARIA DE ESTADO DA EDUCAÇÃO" in linha:
                            municipio_temp = linha.split("SECRETARIA")[0].strip()
                            if municipio_temp: municipio = municipio_temp
                            if idx + 1 < len(linhas):
                                nome_escola_temp = linhas[idx + 1].strip()
                                if nome_escola_temp: nome_escola = nome_escola_temp

                for line_num, linha in enumerate(linhas):
                    # --- ADICIONADO PARA DEBUG: Bloco try/except ---
                    # Este bloco tenta processar cada linha. Se falhar, ele reporta o erro
                    # e continua, em vez de travar o programa.
                    try:
                        linha = linha.strip()
                        if " - " in linha and "TURMA" not in linha and "LANÇAMENTO" not in linha:
                            turma_atual = linha
                            if debug_mode:
                                st.info(f"**DEBUG:** Turma identificada: `{turma_atual}`")
                            continue

                        if not turma_atual: continue

                        horarios = re.findall(horario_re, linha)
                        if not horarios: continue

                        # Se a linha contém um horário, é uma linha de dados e deve ser processada
                        if debug_mode:
                            st.write(f"**DEBUG:** (Linha {line_num + 1}) Candidata: `{linha}`")

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
                            if debug_mode:
                                st.warning(f"**DEBUG:** Disciplina não encontrada na linha. Pulando.")
                            continue

                        dados_extraidos.append([
                            semana, data_relatorio, municipio, nome_escola,
                            turma_atual, horario, disciplina_encontrada,
                            registro_aula, registro_conteudo
                        ])
                        if debug_mode:
                            st.success(f"**DEBUG:** Linha processada com sucesso!")

                    except Exception as e:
                        if debug_mode:
                            st.error(
                                f"**DEBUG: ERRO ao processar a linha {line_num + 1} do arquivo `{arquivo_pdf.name}`!**")
                            st.error(f"**--> Linha com problema:** `{linha}`")
                            st.error(f"**--> Erro:** `{e}`")
                        # Continua para a próxima linha
                        continue

    status_text.empty()
    progress_bar.empty()

    colunas = [
        "SEMANA", "DATA_DO_RELATORIO", "MUNICIPIO", "ESCOLA", "TURMA",
        "HORARIO", "DISCIPLINA", "REGISTRO_DE_AULA", "REGISTRO_DE_CONTEUDO"
    ]
    df = pd.DataFrame(dados_extraidos, columns=colunas)
    return df


# --- Interface do Streamlit ---

st.set_page_config(layout="wide")
st.title("Processar Relatórios PDF 📄")

autenticar_usuario()

if 'user_info' not in st.session_state:
    st.info("Por favor, faça login com a sua conta Google para continuar.")
    st.stop()

# --- Lógica da Aplicação (Visível apenas após o login) ---
user_info = st.session_state.user_info
# ... (o resto da autenticação e mapeamento continua igual) ...
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

if 'etapa' not in st.session_state:
    st.session_state.etapa = "upload"

if st.session_state.etapa == "upload":
    st.header("Passo 1: Carregue os Arquivos")

    # --- ADICIONADO PARA DEBUG ---
    debug_mode = st.checkbox("Ativar Modo de Depuração",
                             help="Marque esta caixa para ver detalhes do processo e mensagens de erro específicas.")

    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Selecione os arquivos PDF", type="pdf", accept_multiple_files=True)
    with col2:
        disciplinas_file = st.file_uploader("Selecione a planilha de disciplinas", type=["xlsx"])

    if uploaded_files and disciplinas_file:
        if st.button("Processar Arquivos PDF", use_container_width=True):
            try:
                disciplinas_df = pd.read_excel(disciplinas_file)
                lista_disciplinas_validas = [str(d).strip().upper() for d in
                                             disciplinas_df.iloc[:, 0].dropna().unique()]

                progress_bar = st.progress(0, text="Iniciando processamento...")
                status_text = st.empty()

                # Passa o estado do checkbox para a função de processamento
                df_temp = processar_pdfs(uploaded_files, lista_disciplinas_validas, progress_bar, status_text,
                                         debug_mode)

                if not df_temp.empty:
                    st.session_state.df_processado = df_temp
                    st.session_state.etapa = "configurar_envio"
                    st.rerun()
                else:
                    st.warning(
                        "Nenhum registro válido foi encontrado nos PDFs. Verifique os arquivos e o output do modo de depuração (se ativo).")

            except Exception as e:
                st.error(f"Ocorreu um erro geral durante o processamento: {e}")

# O restante do arquivo (ETAPA 2 e ETAPA 3) permanece o mesmo.
# --- ETAPA 2: Configuração e Envio ---
elif st.session_state.etapa == "configurar_envio":
    df_processado = st.session_state.df_processado
    st.success(f"✅ {len(df_processado)} registros foram extraídos com sucesso.")

    st.header("Passo 2: Configure e Envie os Dados")

    # --- LÓGICA DE FILTRO AUTOMÁTICO ADICIONADA AQUI ---
    termos_para_excluir = ['aut', 'mec', 'eja', 'ali', 'gas', 'eletrom']
    regex_pattern = '|'.join(termos_para_excluir)

    mascara_exclusao = df_processado['TURMA'].str.contains(regex_pattern, case=False, na=False)
    turmas_excluidas_auto = sorted(df_processado[mascara_exclusao]['TURMA'].unique())

    df_filtrado_auto = df_processado[~mascara_exclusao]

    if turmas_excluidas_auto:
        st.info(
            f"**Filtro Automático:** As seguintes {len(turmas_excluidas_auto)} turmas foram removidas da seleção por conterem termos pré-definidos (como 'EJA', 'MEC', etc.):")
        num_cols = 3
        cols = st.columns(num_cols)
        for i, turma in enumerate(turmas_excluidas_auto):
            cols[i % num_cols].write(f"- {turma}")

    creds = st.session_state.credentials
    dataset_id = st.session_state.dataset_id
    ultima_semana = get_latest_week(creds, dataset_id)
    semana_sugerida = ultima_semana + 1

    col_info, col_input = st.columns(2)
    with col_info:
        st.metric("Última Semana no Banco de Dados", ultima_semana)
    with col_input:
        semana_para_envio = st.number_input(
            "Confirme ou altere o número da semana para estes novos registros:",
            min_value=1, value=semana_sugerida, step=1
        )

    st.markdown("#### Filtrar Turmas Manualmente (Opcional)")
    turmas_encontradas = sorted(df_filtrado_auto['TURMA'].unique())

    filtro_texto_turma = st.text_input(
        "Digite para filtrar a lista de turmas a excluir:",
        placeholder="Ex: 8º Ano - Manhã"
    )

    if filtro_texto_turma:
        opcoes_filtradas = [t for t in turmas_encontradas if filtro_texto_turma.lower() in t.lower()]
    else:
        opcoes_filtradas = turmas_encontradas

    turmas_para_excluir_manual = st.multiselect(
        "Selecione outras turmas que deseja EXCLUIR do envio:",
        options=opcoes_filtradas,
        default=[]
    )

    df_filtrado_manual = df_filtrado_auto[~df_filtrado_auto['TURMA'].isin(turmas_para_excluir_manual)]
    df_para_envio = df_filtrado_manual.copy()
    df_para_envio['SEMANA'] = semana_para_envio

    st.markdown("---")

    if not df_para_envio.empty:
        st.write(f"**{len(df_para_envio)}** registros prontos para serem enviados (após filtros).")

        with st.expander("Clique para visualizar todos os dados a serem enviados"):
            st.dataframe(df_para_envio)

        csv_data = df_para_envio.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="📥 Baixar dados selecionados como CSV",
            data=csv_data,
            file_name=f"dados_semana_{semana_para_envio}_para_envio.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.markdown("---")

        if st.button("Enviar para o BigQuery", use_container_width=True):
            with st.spinner("Conectando e carregando dados..."):
                sucesso = carregar_dados_no_bigquery(df_para_envio, creds, dataset_id, 'append')
                if sucesso:
                    st.session_state.etapa = "sucesso"
                    st.session_state.semana_enviada = semana_para_envio
                    st.rerun()
                else:
                    st.error("Falha no envio dos dados. Verifique a mensagem de erro acima.")
    else:
        st.warning("Nenhuma turma foi selecionada ou todas as turmas foram excluídas. Nenhum dado será enviado.")

# --- ETAPA 3: Sucesso e Recomeço ---
elif st.session_state.etapa == "sucesso":
    st.success(f"Dados da semana {st.session_state.semana_enviada} enviados para o BigQuery com sucesso!")
    st.balloons()

    if st.button("Iniciar Novo Lançamento", use_container_width=True):
        if 'df_processado' in st.session_state:
            del st.session_state['df_processado']
        st.session_state.etapa = "upload"
        st.rerun()