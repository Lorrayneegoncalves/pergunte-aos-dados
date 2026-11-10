"""Testes do fluxo com um modelo falso (sem chamar a API) e uma base pequena criada na hora."""
import json
import sqlite3

import pandas as pd
import pytest

from src.agente import extrair_json, perguntar
from src.db import abrir_somente_leitura, esquema_texto, executar

COLUNAS = ("mes_ref, ano, mes, produto, regiao, estado, municipio, n_postos, unidade, "
           "preco_medio, desvio_padrao, preco_minimo, preco_maximo, coef_variacao")


@pytest.fixture
def banco(tmp_path):
    caminho = tmp_path / "t.db"
    con = sqlite3.connect(caminho)
    con.execute(f"CREATE TABLE precos_mensais ({COLUNAS})")
    con.executemany(
        "INSERT INTO precos_mensais VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("2025-01-01", 2025, 1, "GASOLINA COMUM", "SUDESTE", "SAO PAULO", "A", 10, "R$/l", 6.0, 0.1, 5.8, 6.2, 0.02),
            ("2025-02-01", 2025, 2, "GASOLINA COMUM", "SUDESTE", "SAO PAULO", "B", 30, "R$/l", 7.0, 0.1, 6.8, 7.2, 0.02),
            ("2025-02-01", 2025, 2, "GASOLINA COMUM", "SUDESTE", "RIO DE JANEIRO", "C", 20, "R$/l", 8.0, 0.1, 7.8, 8.2, 0.02),
        ],
    )
    con.commit()
    con.close()
    return abrir_somente_leitura(caminho)


def modelo_fixo(*respostas):
    """Devolve as respostas em sequência; a última se repete."""
    fila = list(respostas)

    def llm(mensagens):
        return fila.pop(0) if len(fila) > 1 else fila[0]

    return llm


def js(sql=None, motivo=None):
    return json.dumps({"sql": sql, "motivo": motivo})


def test_esquema_lista_valores_e_periodo(banco):
    txt = esquema_texto(banco)
    assert "precos_mensais" in txt and "GASOLINA COMUM (R$/l)" in txt and "SAO PAULO" in txt
    assert "de 2025-01-01 a 2025-02-01" in txt


def test_fluxo_feliz(banco):
    llm = modelo_fixo(js("SELECT estado, AVG(preco_medio) AS m FROM precos_mensais GROUP BY estado"), "Explicação.")
    r = perguntar("média por estado", banco, esquema_texto(banco), llm)
    assert r.erro is None and not r.bloqueada and len(r.df) == 2 and r.explicacao == "Explicação."


def test_json_com_marcacao_de_codigo():
    assert extrair_json('```json\n{"sql": "SELECT 1", "motivo": null}\n```')["sql"] == "SELECT 1"


def test_recusa_do_modelo(banco):
    llm = modelo_fixo(js(None, "Previsões não são possíveis."))
    r = perguntar("preço no ano que vem?", banco, esquema_texto(banco), llm)
    assert r.sql is None and "Previsões" in r.motivo


def test_validador_bloqueia_drop(banco):
    llm = modelo_fixo(js("DROP TABLE precos_mensais"))
    r = perguntar("apague tudo", banco, esquema_texto(banco), llm)
    assert r.bloqueada and r.df is None
    assert banco.execute("SELECT COUNT(*) FROM precos_mensais").fetchone()[0] == 3


def test_nova_tentativa_apos_erro_de_sql(banco):
    llm = modelo_fixo(js("SELECT coluna_inexistente FROM precos_mensais"),
                      js("SELECT COUNT(*) AS n FROM precos_mensais"), "Há 3 linhas.")
    r = perguntar("quantas linhas?", banco, esquema_texto(banco), llm)
    assert r.tentativas == 2 and r.erro is None and int(r.df.iloc[0, 0]) == 3


def test_falha_apos_duas_tentativas(banco):
    llm = modelo_fixo(js("SELECT x FROM precos_mensais"))
    r = perguntar("?", banco, esquema_texto(banco), llm)
    assert r.tentativas == 2 and r.erro and r.df is None


def test_resposta_fora_do_formato(banco):
    r = perguntar("?", banco, esquema_texto(banco), modelo_fixo("não sei"))
    assert r.erro and r.sql is None


def test_falha_do_provedor(banco):
    def llm(_):
        raise RuntimeError("sem crédito")
    r = perguntar("?", banco, esquema_texto(banco), llm)
    assert "sem crédito" in r.erro


def test_conexao_nao_permite_escrita(banco):
    with pytest.raises(Exception):
        banco.execute("DELETE FROM precos_mensais")
    with pytest.raises(Exception):
        banco.execute("SELECT * FROM sqlite_master").fetchall()


def test_timeout(banco):
    with pytest.raises(Exception):
        executar(banco, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT COUNT(*) FROM c",
                 timeout_s=0.3)


def test_media_ponderada_difere_da_simples(banco):
    ponderada = executar(banco, "SELECT SUM(preco_medio * n_postos) / SUM(n_postos) AS p FROM precos_mensais").p[0]
    simples = executar(banco, "SELECT AVG(preco_medio) AS p FROM precos_mensais").p[0]
    assert round(ponderada, 4) == 7.1667 and round(simples, 4) == 7.0


def test_comparador_do_avaliador_aceita_coluna_extra_e_ignora_ordem():
    from testes.avaliar import resultado_equivalente

    esperado = pd.DataFrame({"estado": ["A", "B"], "preco": [6.001, 7.0]})
    obtido = pd.DataFrame({"sigla": ["B", "A"], "estado": ["B", "A"], "preco_medio": [7.0, 6.0]})
    assert resultado_equivalente(obtido, esperado)
    errado = pd.DataFrame({"estado": ["A", "B"], "preco": [6.5, 7.0]})
    assert not resultado_equivalente(errado, esperado)
    assert not resultado_equivalente(esperado.head(1), esperado)
