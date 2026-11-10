"""Montagem dos prompts. O texto de cada versão fica em prompts/ (histórico no GitHub)."""
from pathlib import Path

VERSAO = "v2"
_PASTA = Path(__file__).resolve().parent.parent / "prompts"


def prompt_sql(esquema: str, versao: str = VERSAO) -> str:
    base = (_PASTA / f"sql_{versao}.txt").read_text(encoding="utf-8")
    return f"{base}\n\n{esquema}"


def prompt_explicacao() -> str:
    return (_PASTA / "explicacao_v1.txt").read_text(encoding="utf-8")
