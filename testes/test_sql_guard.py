import pytest

from src.sql_guard import validar

TAB = {"precos_mensais"}


def aprovada(sql, **kw):
    ok, resp = validar(sql, TAB, **kw)
    assert ok, resp
    return resp


def reprovada(sql):
    ok, resp = validar(sql, TAB)
    assert not ok
    return resp


def test_select_simples_ganha_limit():
    assert aprovada("SELECT uf FROM precos_mensais;").endswith("LIMIT 200")


def test_limit_existente_e_mantido():
    assert aprovada("SELECT uf FROM precos_mensais LIMIT 5").endswith("LIMIT 5")


def test_limit_grande_e_reduzido():
    assert aprovada("SELECT uf FROM precos_mensais LIMIT 99999").endswith("LIMIT 200")


def test_with_aprovado():
    aprovada("WITH x AS (SELECT uf, AVG(valor_venda) m FROM precos_mensais GROUP BY uf) SELECT * FROM x")


def test_subconsulta_aprovada():
    aprovada("SELECT (SELECT AVG(valor_venda) FROM precos_mensais) / 2 AS metade")


@pytest.mark.parametrize("sql", [
    "DROP TABLE precos_mensais",
    "DELETE FROM precos_mensais",
    "UPDATE precos_mensais SET valor_venda = 0",
    "INSERT INTO precos_mensais VALUES (1)",
    "PRAGMA table_info(precos_mensais)",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT 1; DROP TABLE precos_mensais",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM outra_tabela",
    "SELECT * FROM precos_mensais -- comentário",
    "SELECT * FROM precos_mensais /* x */",
    "SELECT load_extension('x')",
    "",
])
def test_reprovadas(sql):
    reprovada(sql)


def test_palavra_proibida_dentro_de_texto_nao_bloqueia():
    aprovada("SELECT * FROM precos_mensais WHERE bandeira = 'DROP TABLE'")


def test_join_com_tabela_nao_permitida():
    reprovada("SELECT * FROM precos_mensais p JOIN usuarios u ON 1=1")
