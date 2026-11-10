"""Orquestração: pergunta -> SQL (modelo) -> validação -> execução -> explicação (modelo)."""
import json
import re
from dataclasses import dataclass

import pandas as pd

from .db import executar
from .prompt import prompt_explicacao, prompt_sql
from .sql_guard import validar

TABELAS_PERMITIDAS = {"precos_mensais"}


@dataclass
class Resultado:
    pergunta: str
    sql: str | None = None
    df: pd.DataFrame | None = None
    explicacao: str | None = None
    motivo: str | None = None  # recusa do modelo ou motivo do bloqueio
    erro: str | None = None
    bloqueada: bool = False
    tentativas: int = 0


def extrair_json(texto: str) -> dict:
    """Lê o JSON da resposta, mesmo que o modelo tenha colocado marcações de código."""
    limpo = re.sub(r"```(?:json)?", "", texto or "").strip()
    ini, fim = limpo.find("{"), limpo.rfind("}")
    if ini == -1 or fim == -1:
        raise ValueError("Resposta sem JSON")
    return json.loads(limpo[ini : fim + 1])


def perguntar(pergunta: str, con, esquema: str, llm, max_linhas: int = 200) -> Resultado:
    """llm é uma função que recebe a lista de mensagens e devolve texto (ver src/llm.py)."""
    r = Resultado(pergunta=pergunta)
    mensagens = [
        {"role": "system", "content": prompt_sql(esquema)},
        {"role": "user", "content": pergunta},
    ]

    for tentativa in (1, 2):
        r.tentativas = tentativa
        try:
            bruto = llm(mensagens)
        except Exception as e:  # falha de rede, chave inválida, crédito etc.
            r.erro = f"Falha ao chamar o modelo: {e}"
            return r
        try:
            dados = extrair_json(bruto)
        except ValueError:
            r.erro = "A resposta do modelo não veio no formato esperado."
            return r

        sql = dados.get("sql")
        if not sql:
            r.motivo = dados.get("motivo") or "Não foi possível responder com os dados disponíveis."
            return r

        r.sql = sql
        aprovada, resposta = validar(sql, TABELAS_PERMITIDAS, max_linhas)
        if not aprovada:
            r.bloqueada = True
            r.motivo = resposta
            return r
        r.sql = resposta

        try:
            r.df = executar(con, resposta)
            r.erro = None
            break
        except Exception as e:
            r.erro = f"Erro ao executar a consulta: {e}"
            if tentativa == 1:  # uma nova tentativa, devolvendo o erro ao modelo
                mensagens += [
                    {"role": "assistant", "content": bruto},
                    {
                        "role": "user",
                        "content": f"A consulta gerou este erro no SQLite: {e}\n"
                        "Corrija e responda no mesmo formato JSON.",
                    },
                ]
                continue
            return r

    if r.df is None:
        return r
    if r.df.empty:
        r.explicacao = "A consulta não retornou nenhuma linha."
        return r

    try:
        r.explicacao = llm(
            [
                {"role": "system", "content": prompt_explicacao()},
                {
                    "role": "user",
                    "content": f"Pergunta: {pergunta}\nConsulta: {r.sql}\n"
                    f"Resultado (CSV):\n{r.df.head(20).to_csv(index=False)}",
                },
            ]
        ).strip()
    except Exception:
        r.explicacao = None  # a tabela já responde; a explicação é um extra
    return r
