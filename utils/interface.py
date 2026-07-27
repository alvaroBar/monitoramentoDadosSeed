# utils/interface.py
import streamlit as st
import datetime

def exibir_cabecalho_ano():
    """
    Exibe um banner visual no topo da página indicando o ano letivo ativo.
    Diferencia visualmente o ano corrente de anos históricos (alerta).
    """
    if 'ano_letivo' not in st.session_state:
        # Se por acaso não tiver ano definido, define o atual para evitar erro
        st.session_state['ano_letivo'] = datetime.datetime.now().year

    ano_selecionado = st.session_state['ano_letivo']
    ano_atual = datetime.datetime.now().year

    # Estilo CSS para o Badge
    if ano_selecionado == ano_atual:
        # Estilo para Ano Corrente (Azul/Discreto)
        cor_fundo = "#e3f2fd"
        cor_texto = "#0d47a1"
        icone = "📅"
        texto_extra = "Vigente"
        borda = "1px solid #90caf9"
    else:
        # Estilo para Anos Anteriores (Amarelo/Alerta)
        cor_fundo = "#fff3cd"
        cor_texto = "#856404"
        icone = "⚠️"
        texto_extra = "HISTÓRICO - Cuidado ao editar"
        borda = "1px solid #ffeeba"

    # Renderiza o Banner HTML
    st.markdown(f"""
        <div style="
            background-color: {cor_fundo};
            color: {cor_texto};
            padding: 10px 15px;
            border-radius: 8px;
            border: {borda};
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-family: sans-serif;
        ">
            <span style="font-size: 1.1em; font-weight: bold;">
                {icone} Ano Letivo Ativo: {ano_selecionado}
            </span>
            <span style="font-size: 0.9em; opacity: 0.8;">
                {texto_extra}
            </span>
        </div>
    """, unsafe_allow_html=True)

    # (Opcional) Força o ano na sidebar também para garantir que está visível
    with st.sidebar:
        st.caption(f"📌 Base de Dados: `relatorios_lrco_{ano_selecionado}`")