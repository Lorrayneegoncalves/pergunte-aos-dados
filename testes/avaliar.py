"""Avalia o agente com perguntas de resposta conhecida.

Para cada pergunta do tipo "consulta", executa o SQL esperado (escrito à mão em perguntas.csv)
e compara o RESULTADO com o da consulta gerada pelo modelo, e não o texto do SQL, porque
consultas diferentes podem estar corretas.
Para o tipo "recusa", o agente acerta se o modelo se recusa ou se o validador bloqueia.

Uso:
    python testes/avaliar.py                      # usa o modelo real (precisa de OPENAI_API_KEY)
    python testes/avaliar.py --banco data/precos.db
    python testes/avaliar.py --simulado           # só para testar o script; NÃO mede o modelo

Os placeholders {ANO} e {ANO_ANT} são trocados pelo último ano disponível na base e pelo anterior.
Revise o sql_esperado de cada pergunta (e os nomes de produto) antes de confiar no resultado.
"""
import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.agente import perguntar  # noqa: E402
from src.db import abrir_somente_leitura, esquema_texto, executar  # noqa: E402


def _valor(v):
    if isinstance(v, (int, float)) and v == v:  # números (e não NaN): comparar com 2 casas decimais
        return round(float(v), 2)
    return str(v)


def colunas_normalizadas(df: pd.DataFrame) -> list:
    """Cada coluna vira uma lista ordenada de valores arredondados (ignora nome da coluna e ordem das linhas)."""
    return [sorted((_valor(v) for v in df[c].tolist()), key=str) for c in df.columns]


def resultado_equivalente(obtido: pd.DataFrame, esperado: pd.DataFrame) -> bool:
    """Acerta se tem o mesmo número de linhas e se toda coluna do esperado aparece no obtido.

    Colunas a mais no resultado do modelo não são consideradas erro.
    """
    if len(obtido) != len(esperado):
        return False
    cols_obtidas = colunas_normalizadas(obtido)
    return all(col in cols_obtidas for col in colunas_normalizadas(esperado))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default=str(RAIZ / "data" / "precos.db"))
    ap.add_argument("--perguntas", default=str(RAIZ / "testes" / "perguntas.csv"))
    ap.add_argument("--simulado", action="store_true", help="usa um modelo falso que devolve o SQL esperado")
    args = ap.parse_args()

    con = abrir_somente_leitura(args.banco)
    esquema = esquema_texto(con)
    ano = con.execute("SELECT MAX(ano) FROM precos_mensais").fetchone()[0]
    subst = {"{ANO}": str(ano), "{ANO_ANT}": str(ano - 1)}

    def aplicar(txt):
        for k, v in subst.items():
            txt = txt.replace(k, v)
        return txt

    with open(args.perguntas, encoding="utf-8", newline="") as f:
        itens = list(csv.DictReader(f))

    if args.simulado:
        gabarito = {aplicar(i["pergunta"]): i for i in itens}

        def llm(mensagens):
            if mensagens[0]["content"].startswith("Você converte"):
                item = gabarito[mensagens[1]["content"]]
                sql = aplicar(item["sql_esperado"]) if item["tipo"] == "consulta" else None
                return json.dumps({"sql": sql or None, "motivo": None if sql else "fora do escopo"})
            return "Resposta simulada."
    else:
        from src.llm import chamar_modelo as llm

    linhas = []
    for item in itens:
        pergunta = aplicar(item["pergunta"])
        r = perguntar(pergunta, con, esquema, llm)
        if item["tipo"] == "recusa":
            if r.erro and not r.bloqueada:  # falha do provedor ou formato inválido não é recusa
                acertou, detalhe = False, r.erro
            else:
                acertou = r.sql is None or r.bloqueada
                detalhe = "recusou" if r.sql is None and not r.bloqueada else ("bloqueada pelo validador" if r.bloqueada else "executou")
        else:
            esperado = executar(con, aplicar(item["sql_esperado"]))
            acertou = r.df is not None and resultado_equivalente(r.df, esperado)
            detalhe = "ok" if acertou else (r.erro or r.motivo or "resultado diferente do esperado")
        linhas.append({"id": item["id"], "tipo": item["tipo"], "pergunta": pergunta, "acertou": acertou,
                       "detalhe": detalhe, "tentativas": r.tentativas, "sql_gerado": r.sql})
        print(f"[{'OK ' if acertou else 'ERRO'}] {item['id']:>2} {pergunta}  ->  {detalhe}")

    total = len(linhas)
    acertos = sum(l["acertou"] for l in linhas)
    print(f"\nAcertos: {acertos} de {total}" + ("   (MODO SIMULADO: não mede o modelo)" if args.simulado else ""))

    saida = RAIZ / "testes" / f"resultados-{dt.date.today().isoformat()}{'-simulado' if args.simulado else ''}.csv"
    pd.DataFrame(linhas).to_csv(saida, index=False, encoding="utf-8")
    print(f"Detalhes salvos em {saida}")


if __name__ == "__main__":
    main()
