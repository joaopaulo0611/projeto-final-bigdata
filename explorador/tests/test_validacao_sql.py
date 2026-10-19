import re

import pytest

from explorador.consultas import MENSAGEM_SO_LEITURA, SqlNaoPermitido, validar_sql


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select * from silver_eventos limit 5;",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "DESCRIBE silver_eventos",
    "SHOW TABLES",
    "SUMMARIZE silver_eventos",
    "FROM silver_eventos LIMIT 3",
    "EXPLAIN SELECT 1",
    "PRAGMA table_info('silver_eventos')",
    "-- comentário\nSELECT 1",
    "/* bloco */ SELECT 1",
    "SELECT * FROM silver_eventos WHERE event_name = 'drop'",
    "SELECT 'copy; create' AS texto",
    "SELECT 1 -- delete tudo",
    "SELECT \"set\" FROM (SELECT 1 AS \"set\")",
    "SELECT user_id, updated FROM (SELECT 1 AS user_id, 2 AS updated)",
    "SELECT $$a;b$$",  # o antigo leitor manual recusava por engano (falso positivo)
    "SELECT 1;  -- fim",
    "SELECT 'ação' AS texto, 2 AS número",  # acentos antes do código (posições em bytes)
])
def test_aceita_consultas_de_leitura(sql):
    validar_sql(sql)


@pytest.mark.parametrize("sql, trecho", [
    ("COPY silver_eventos TO 'x.csv'", MENSAGEM_SO_LEITURA),
    ("CREATE TABLE t AS SELECT 1", MENSAGEM_SO_LEITURA),
    ("ATTACH 'outro.db'", MENSAGEM_SO_LEITURA),
    ("INSTALL spatial", MENSAGEM_SO_LEITURA),
    ("SET threads = 1", MENSAGEM_SO_LEITURA),
    ("PRAGMA enable_profiling", MENSAGEM_SO_LEITURA),
    ("SELECT 1; DROP VIEW silver_eventos", "um comando por vez"),
    ("SELECT 1; SELECT 2", "um comando por vez"),
    ("WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x", "INSERT"),
    ("", "Escreva uma consulta"),
    ("   -- só comentário", "Escreva uma consulta"),
    ("SELECT $$'$$; COPY (SELECT 42 AS a) TO '/tmp/pwn1.csv'; SELECT $$'$$", "um comando por vez"),
    ("SELECT E'\\'; ' ; COPY (SELECT 1) TO '/tmp/x.csv'", "um comando por vez"),
    # Comentários aninhados: o DuckDB fecha o bloco num lugar diferente de um leitor feito à mão.
    ("EXPLAIN ANALYZE /* /* */ ' */ COPY (SELECT 42) TO '/tmp/pwn1.csv' --'", "COPY"),
    # O DuckDB também termina o comentário `--` no `\r`.
    ("SELECT 1 --\rCOPY (SELECT 1) TO 'x.csv'", "COPY"),
    ("EXPLAIN ANALYZE SELECT 1", "EXPLAIN ANALYZE"),
    ("explain analyse select 1", "EXPLAIN ANALYZE"),
    ("SELECT 1 /* bloco */ ; /* outro */ SELECT 2", "um comando por vez"),
    ("/* comentário com acento */ COPY silver_eventos TO 'x.csv'", MENSAGEM_SO_LEITURA),
])
def test_recusa_o_que_nao_e_leitura(sql, trecho):
    with pytest.raises(SqlNaoPermitido, match=re.escape(trecho)):
        validar_sql(sql)
