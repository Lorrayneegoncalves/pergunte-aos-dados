"""Validação de consultas SQL geradas pelo modelo.

Esta é a primeira camada de segurança. A segunda está em db.py: a conexão é aberta
somente para leitura e usa um "authorizer" do SQLite que nega qualquer operação
diferente de leitura.

Regras aplicadas:
- um único comando, começando com SELECT ou WITH;
- sem comentários;
- nenhuma palavra de escrita ou administração (INSERT, DROP, PRAGMA etc.);
- só tabelas permitidas depois de FROM e JOIN;
- LIMIT obrigatório (acrescentado se faltar, reduzido se for maior que o máximo).
"""
import re

PALAVRAS_PROIBIDAS = {
    "insert", "update", "delete", "drop", "alter", "create", "attach", "detach",
    "pragma", "replace", "vacuum", "reindex", "analyze", "truncate", "begin",
    "commit", "rollback", "savepoint", "load_extension", "writefile", "readfile",
}


def _mascarar_literais(sql: str) -> str:
    """Troca o conteúdo de textos entre aspas simples, para não confundir a análise."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validar(sql: str, tabelas_permitidas: set[str], limite: int = 200) -> tuple[bool, str]:
    """Retorna (True, sql_final) se aprovada, ou (False, motivo) se reprovada."""
    if not sql or not sql.strip():
        return False, "Consulta vazia."

    sql = sql.strip()
    while sql.endswith(";"):
        sql = sql[:-1].rstrip()

    mascarado = _mascarar_literais(sql)
    baixo = mascarado.lower()

    if ";" in mascarado:
        return False, "Só é permitido um comando por vez."
    if "--" in mascarado or "/*" in mascarado:
        return False, "Comentários não são permitidos na consulta."

    primeira = re.match(r"\s*([a-z_]+)", baixo)
    if not primeira or primeira.group(1) not in {"select", "with"}:
        return False, "Só são permitidas consultas de leitura (SELECT)."

    palavras = set(re.findall(r"[a-z_][a-z0-9_]*", baixo))
    proibidas = sorted(palavras & PALAVRAS_PROIBIDAS)
    if proibidas:
        return False, f"Palavra não permitida na consulta: {proibidas[0].upper()}."

    ctes = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(", baixo))
    referencias = re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", baixo)
    permitidas = {t.lower() for t in tabelas_permitidas}
    for ref in referencias:
        if ref not in permitidas and ref not in ctes:
            return False, f"Tabela não permitida: {ref}."

    m = re.search(r"\blimit\s+(\d+)", baixo)
    if m is None:
        sql = f"{sql} LIMIT {limite}"
    elif int(m.group(1)) > limite:
        sql = re.sub(r"(?i)\blimit\s+\d+", f"LIMIT {limite}", sql)

    return True, sql
