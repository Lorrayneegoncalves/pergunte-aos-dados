"""Acesso ao banco SQLite, sempre em modo somente leitura."""
import sqlite3
import time
from pathlib import Path

import pandas as pd

TABELA = "precos_mensais"

DESCRICAO_COLUNAS = {
    "mes_ref": "primeiro dia do mês de referência, texto AAAA-MM-DD",
    "ano": "ano de referência (número inteiro)",
    "mes": "mês de referência (1 a 12)",
    "produto": "tipo de combustível",
    "regiao": "região do Brasil, em maiúsculas",
    "estado": "nome do estado, em maiúsculas e sem acento (ex.: SAO PAULO)",
    "municipio": "nome do município, em maiúsculas e sem acento (ex.: MACAE)",
    "n_postos": "número de postos pesquisados naquele município, produto e mês",
    "unidade": "unidade de medida dos preços (R$/l, R$/13kg para GLP, R$/m³ para GNV)",
    "preco_medio": "preço médio de revenda (ao consumidor) naquele município, produto e mês",
    "desvio_padrao": "desvio padrão do preço de revenda entre os postos pesquisados",
    "preco_minimo": "menor preço de revenda entre os postos pesquisados",
    "preco_maximo": "maior preço de revenda entre os postos pesquisados",
    "coef_variacao": "coeficiente de variação do preço de revenda",
}

_PERMITIDAS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


def _autorizador(acao, arg1, arg2, banco, origem):
    """Nega qualquer operação que não seja leitura, e também a leitura do catálogo interno."""
    if acao == sqlite3.SQLITE_READ and arg1 in {"sqlite_master", "sqlite_schema", "sqlite_temp_master"}:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if acao in _PERMITIDAS else sqlite3.SQLITE_DENY


def abrir_somente_leitura(caminho) -> sqlite3.Connection:
    caminho = Path(caminho).resolve()
    if not caminho.exists():
        raise FileNotFoundError(f"Banco não encontrado: {caminho}")
    con = sqlite3.connect(f"{caminho.as_uri()}?mode=ro", uri=True, check_same_thread=False)
    con.set_authorizer(_autorizador)
    return con


def executar(con: sqlite3.Connection, sql: str, timeout_s: float = 5.0) -> pd.DataFrame:
    """Executa a consulta com tempo máximo de execução."""
    limite = time.monotonic() + timeout_s
    con.set_progress_handler(lambda: 1 if time.monotonic() > limite else 0, 10000)
    try:
        return pd.read_sql_query(sql, con)
    finally:
        con.set_progress_handler(None, 0)


def esquema_texto(con: sqlite3.Connection) -> str:
    """Texto com a estrutura da tabela e os valores categóricos (produto, unidade, estado, região).

    Não são enviadas linhas de dados, só os nomes das colunas, os valores distintos dessas
    colunas categóricas e o intervalo de meses.
    """
    # Código nosso (não vem do modelo): libera o PRAGMA só durante esta leitura e reativa o bloqueio.
    con.set_authorizer(None)
    try:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({TABELA})")]
        produtos = con.execute(f"SELECT DISTINCT produto, unidade FROM {TABELA} ORDER BY 1").fetchall()
        estados = [r[0] for r in con.execute(f"SELECT DISTINCT estado FROM {TABELA} ORDER BY 1")]
        regioes = [r[0] for r in con.execute(f"SELECT DISTINCT regiao FROM {TABELA} ORDER BY 1")]
        ini, fim = con.execute(f"SELECT MIN(mes_ref), MAX(mes_ref) FROM {TABELA}").fetchone()
    finally:
        con.set_authorizer(_autorizador)
    linhas = [
        f"Tabela: {TABELA}",
        "Cada linha resume UM produto em UM município em UM mês (não é a coleta de um posto individual).",
        "Colunas:",
    ]
    for c in cols:
        linhas.append(f"- {c}: {DESCRICAO_COLUNAS.get(c, '')}".rstrip(": "))
    linhas += [
        "",
        "Valores existentes em produto (unidade): " + "; ".join(f"{p} ({u})" for p, u in produtos),
        "Valores existentes em regiao: " + ", ".join(regioes),
        "Valores existentes em estado: " + ", ".join(estados),
        f"Período dos dados: de {ini} a {fim}",
    ]
    return "\n".join(linhas)
