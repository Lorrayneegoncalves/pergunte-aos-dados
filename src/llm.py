"""Única função que chama o modelo de linguagem.

Para trocar de provedor (por exemplo, para o Claude), só esta função precisa mudar.
A chave vem da variável de ambiente OPENAI_API_KEY e nunca fica no código.
"""
import os


def chamar_modelo(mensagens: list[dict], modelo: str | None = None) -> str:
    chave = os.environ.get("OPENAI_API_KEY")
    if not chave:
        raise RuntimeError("Chave da API não encontrada. Defina a variável OPENAI_API_KEY.")
    from openai import OpenAI  # importado aqui para os testes rodarem sem a biblioteca

    cliente = OpenAI(api_key=chave)
    resposta = cliente.chat.completions.create(
        model=modelo or os.environ.get("MODELO", "gpt-5-mini"),
        messages=mensagens,
    )
    return resposta.choices[0].message.content
