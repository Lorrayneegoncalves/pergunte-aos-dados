"""Transforma o arquivo mensal por município da ANP (xlsx) em um banco SQLite.

Fonte: série histórica mensal do levantamento de preços da ANP, relatório "Municípios".
Cada linha do arquivo resume UM produto em UM município em UM mês (preço médio, mínimo,
máximo e número de postos pesquisados). Não são coletas individuais de cada posto.

Uso:
    python data/construir_base.py --entrada data/raw --saida data/precos.db
    python data/construir_base.py --entrada data/raw --anos 2024 2025

Coloque o(s) arquivo(s) .xlsx baixados da ANP em data/raw/.
As colunas de margem e de preço de distribuição vêm vazias nesse relatório e são descartadas.
"""
import argparse
import re
import sqlite3
import unicodedata
from pathlib import Path

import openpyxl
import pandas as pd

TABELA = "precos_mensais"

MAPA = {
    "mes": "mes_ref",
    "produto": "produto",
    "regiao": "regiao",
    "estado": "estado",
    "municipio": "municipio",
    "numero_de_postos_pesquisados": "n_postos",
    "unidade_de_medida": "unidade",
    "preco_medio_revenda": "preco_medio",
    "desvio_padrao_revenda": "desvio_padrao",
    "preco_minimo_revenda": "preco_minimo",
    "preco_maximo_revenda": "preco_maximo",
    "coef_de_variacao_revenda": "coef_variacao",
}
NUMERICAS = ["n_postos", "preco_medio", "desvio_padrao", "preco_minimo", "preco_maximo", "coef_variacao"]


def normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def achar_cabecalho(caminho: Path) -> int:
    """O arquivo da ANP tem um bloco de texto no topo; o cabeçalho real começa com a coluna MÊS."""
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        for i, linha in enumerate(wb.worksheets[0].iter_rows(values_only=True, max_row=80)):
            if linha and linha[0] and normalizar(linha[0]) == "mes":
                return i
    finally:
        wb.close()
    raise SystemExit(f"{caminho.name}: não encontrei a linha de cabeçalho (coluna 'MÊS').")


def ler_arquivo(caminho: Path) -> pd.DataFrame:
    df = pd.read_excel(caminho, header=achar_cabecalho(caminho), dtype=object)
    df.columns = [normalizar(c) for c in df.columns]
    faltando = [c for c in MAPA if c not in df.columns]
    if faltando:
        raise SystemExit(
            f"{caminho.name}: colunas esperadas não encontradas: {faltando}\n"
            f"Colunas do arquivo: {list(df.columns)}\n"
            "Ajuste o dicionário MAPA em construir_base.py para os nomes do seu arquivo."
        )
    return df[list(MAPA)].rename(columns=MAPA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="data/raw", help="pasta com os arquivos .xlsx da ANP")
    ap.add_argument("--saida", default="data/precos.db")
    ap.add_argument("--anos", nargs="*", type=int, help="manter só estes anos")
    args = ap.parse_args()

    arquivos = [a for a in sorted(Path(args.entrada).glob("*.xlsx")) if not a.name.startswith("~$")]
    if not arquivos:
        raise SystemExit(f"Nenhum arquivo .xlsx encontrado em {args.entrada}")

    partes = []
    for arq in arquivos:
        print(f"Lendo {arq.name} (pode levar 1 a 2 minutos)...")
        df = ler_arquivo(arq)
        partes.append(df)
        print(f"  {len(df)} linhas")

    base = pd.concat(partes, ignore_index=True)
    for col in ("produto", "regiao", "estado", "municipio", "unidade"):
        base[col] = base[col].astype(str).str.strip()
    for col in NUMERICAS:
        base[col] = pd.to_numeric(base[col], errors="coerce")  # "-" vira vazio
    base["mes_ref"] = pd.to_datetime(base["mes_ref"], errors="coerce")

    antes = len(base)
    base = base.dropna(subset=["mes_ref", "preco_medio", "n_postos"])
    if antes - len(base):
        print(f"Removidas {antes - len(base)} linhas sem mês, preço médio ou número de postos")

    base["ano"] = base["mes_ref"].dt.year.astype(int)
    base["mes"] = base["mes_ref"].dt.month.astype(int)
    base["n_postos"] = base["n_postos"].astype(int)
    base["mes_ref"] = base["mes_ref"].dt.strftime("%Y-%m-%d")
    base = base.drop_duplicates(subset=["mes_ref", "produto", "estado", "municipio"])

    if args.anos:
        base = base[base["ano"].isin(args.anos)]

    colunas = ["mes_ref", "ano", "mes", "produto", "regiao", "estado", "municipio", "n_postos", "unidade",
               "preco_medio", "desvio_padrao", "preco_minimo", "preco_maximo", "coef_variacao"]
    base = base[colunas]

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    if saida.exists():
        saida.unlink()
    con = sqlite3.connect(saida)
    base.to_sql(TABELA, con, index=False)
    con.execute(f"CREATE INDEX idx_prod_ano ON {TABELA}(produto, ano)")
    con.execute(f"CREATE INDEX idx_estado ON {TABELA}(estado)")
    con.commit()
    con.execute("VACUUM")
    con.close()

    print("\n--- Resumo da base ---")
    print(f"Linhas: {len(base)}  |  Período: {base['mes_ref'].min()} a {base['mes_ref'].max()}")
    print("Produtos e unidades:")
    for (p, u), n in base.groupby(["produto", "unidade"]).size().items():
        print(f"  {p} ({u}): {n} linhas")
    print(f"Estados: {base['estado'].nunique()}  |  Municípios (nome + estado): {base[['estado', 'municipio']].drop_duplicates().shape[0]}")
    print(f"Tamanho do arquivo: {saida.stat().st_size / 1e6:.1f} MB (limite de upload pelo navegador no GitHub: 25 MB)")


if __name__ == "__main__":
    main()
