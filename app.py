"""Tela do app (Streamlit): pergunte aos dados de preços de combustíveis da ANP."""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.agente import perguntar
from src.db import abrir_somente_leitura, esquema_texto
from src.llm import chamar_modelo

BANCO = Path(__file__).parent / "data" / "precos.db"
MAX_PERGUNTAS_POR_SESSAO = 20

st.set_page_config(page_title="Pergunte aos dados", page_icon="📊", layout="wide")

# A chave e a senha ficam em "Secrets" (no Streamlit Cloud) ou em variáveis de ambiente, nunca no código.
try:
    if "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
    senha_app = st.secrets.get("APP_SENHA")
except Exception:
    senha_app = os.environ.get("APP_SENHA")


@st.cache_resource
def conexao():
    return abrir_somente_leitura(BANCO)


if not BANCO.exists():
    st.error("Banco de dados não encontrado. Rode `python data/construir_base.py` (veja o README).")
    st.stop()

con = conexao()
esquema = esquema_texto(con)

st.title("Pergunte aos dados")
st.caption("Preços de combustíveis (dados abertos da ANP). Faça uma pergunta em português e veja a consulta, o resultado e a explicação.")

with st.sidebar:
    st.subheader("Sobre a base")
    st.code(esquema, language="text")
    st.caption(
        "O modelo recebe esta estrutura e os valores de produto e estado, nunca as linhas de dados. "
        "Só são executadas consultas de leitura (SELECT), validadas antes de rodar."
    )

if senha_app:
    if st.session_state.get("liberado") is not True:
        digitada = st.text_input("Senha de acesso", type="password")
        if digitada and digitada == senha_app:
            st.session_state["liberado"] = True
            st.rerun()
        st.stop()

st.session_state.setdefault("n_perguntas", 0)

pergunta = st.text_input("Sua pergunta", placeholder="Ex.: Qual o preço médio do etanol hidratado por estado no último ano?")
if st.button("Perguntar", type="primary") and pergunta.strip():
    if st.session_state["n_perguntas"] >= MAX_PERGUNTAS_POR_SESSAO:
        st.warning("Limite de perguntas desta sessão atingido.")
        st.stop()
    st.session_state["n_perguntas"] += 1

    with st.spinner("Consultando..."):
        r = perguntar(pergunta.strip(), con, esquema, chamar_modelo)

    if r.erro and r.df is None:
        st.error(r.erro)
    elif r.bloqueada:
        st.warning(f"Consulta bloqueada pelo validador: {r.motivo}")
        if r.sql:
            st.code(r.sql, language="sql", wrap_lines=True)
    elif r.sql is None:
        st.info(r.motivo)
    else:
        st.subheader("Consulta gerada")
        st.code(r.sql, language="sql")
        st.caption("✓ Consulta validada: somente leitura" + (" · corrigida após 1 erro" if r.tentativas == 2 else ""))

        st.subheader("Resultado")
        st.dataframe(r.df, width="stretch")
        df = r.df
        if (
            df.shape[1] == 2 and 1 < len(df) <= 40
            and not pd.api.types.is_numeric_dtype(df.iloc[:, 0])
            and pd.api.types.is_numeric_dtype(df.iloc[:, 1])
        ):
            st.bar_chart(df.set_index(df.columns[0]))

        if r.explicacao:
            st.subheader("Explicação")
            st.write(r.explicacao.replace("$", "\\$"))
        st.caption("A consulta e a explicação são geradas por IA e podem conter erros. Confira a consulta antes de usar o resultado.")
