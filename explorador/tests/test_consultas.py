import duckdb
import pytest

from explorador import consultas, particoes


@pytest.fixture
def lago(tmp_path):
    """Monta um mini-bucket local: Silver particionada por event_name com itens/ ao lado,
    landing JSONL e uma Gold."""
    con = duckdb.connect()
    for dia in ("01", "02"):
        pasta = tmp_path / "silver" / "event_name=page_view" / "year=2026" / "month=09" / f"day={dia}"
        pasta.mkdir(parents=True)
        con.sql(f"COPY (SELECT 'e{dia}-' || i AS event_id FROM range(3) t(i)) "
                f"TO '{pasta}/part-0.parquet' (FORMAT parquet)")
    itens = tmp_path / "silver" / "itens" / "year=2026" / "month=09" / "day=01"
    itens.mkdir(parents=True)
    con.sql(f"COPY (SELECT 'PLANO-PRO' AS item_id) TO '{itens}/part-0.parquet' (FORMAT parquet)")
    gold = tmp_path / "gold" / "funil_compra"
    gold.mkdir(parents=True)
    con.sql(f"COPY (SELECT 'purchase' AS etapa, 7 AS sessoes) TO '{gold}/part-0.parquet' (FORMAT parquet)")
    (gold / "_SUCCESS").write_text("")
    for nome, evento in (("scroll", "a"), ("click", "b")):
        landing = tmp_path / "landing" / f"event_name={nome}" / "year=2026" / "month=09" / "day=01"
        landing.mkdir(parents=True)
        (landing / "coletor-s42-001.jsonl").write_text(
            f'{{"event_id":"{evento}","event_name":"{nome}"}}\n', encoding="utf-8")
    chaves = [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()]
    conexao = consultas.conectar(s3=False)
    views = consultas.criar_views(conexao, str(tmp_path), particoes.datasets(chaves))
    consultas.travar(conexao, str(tmp_path))
    return conexao, views, tmp_path


def test_cria_uma_view_por_dataset(lago):
    _, views, _ = lago
    assert set(views) == {"gold.funil_compra", "landing.eventos", "silver.eventos", "silver.itens"}


def test_particoes_viram_colunas_de_texto(lago):
    con, _, _ = lago
    r = consultas.executar(con, "SELECT DISTINCT event_name, month, day, typeof(month) AS tipo "
                                "FROM silver.eventos ORDER BY day")
    assert r.tabela.to_dict("records") == [
        {"event_name": "page_view", "month": "09", "day": "01", "tipo": "VARCHAR"},
        {"event_name": "page_view", "month": "09", "day": "02", "tipo": "VARCHAR"},
    ]


def test_contagens_das_views(lago):
    con, _, _ = lago
    contar = lambda v: consultas.executar(con, f"SELECT count(*) AS n FROM {v}").tabela["n"][0]
    assert (contar("silver.eventos"), contar("silver.itens"), contar("landing.eventos"), contar("gold.funil_compra")) == (6, 1, 2, 1)

def test_executar_corta_no_limite_e_avisa(lago):
    con, _, _ = lago
    r = consultas.executar(con, "SELECT * FROM range(10)", limite=3)
    assert len(r.tabela) == 3 and r.cortado is True and r.colunas == ["range"]
    r = consultas.executar(con, "SELECT * FROM range(10)", limite=10)
    assert len(r.tabela) == 10 and r.cortado is False


def test_executar_nunca_passa_do_limite_maximo(lago):
    con, _, _ = lago
    r = consultas.executar(con, f"SELECT * FROM range({consultas.LIMITE_MAXIMO + 5})", limite=10**9)
    assert len(r.tabela) == consultas.LIMITE_MAXIMO and r.cortado is True


def test_executar_recusa_sql_proibido_sem_executar(lago):
    con, _, tmp_path = lago
    destino = tmp_path / "copia.csv"
    with pytest.raises(consultas.SqlNaoPermitido):
        consultas.executar(con, f"COPY silver.eventos TO '{destino}'")
    assert not destino.exists()


def test_executar_recusa_explain_analyze_com_copy_escondido(lago):
    con, _, tmp_path = lago
    destino = tmp_path / "pwn1.csv"
    sql = f"EXPLAIN ANALYZE /* /* */ ' */ COPY (SELECT 42) TO '{destino}' --'"
    with pytest.raises(consultas.SqlNaoPermitido):
        consultas.executar(con, sql)
    assert not destino.exists()


def test_previa_le_um_arquivo(lago):
    con, _, tmp_path = lago
    chave = "landing/event_name=scroll/year=2026/month=09/day=01/coletor-s42-001.jsonl"
    assert consultas.previa(con, str(tmp_path), chave)["event_id"].tolist() == ["a"]
    assert len(consultas.previa(con, str(tmp_path), "gold/funil_compra/part-0.parquet")) == 1
    with pytest.raises(ValueError, match="Prévia"):
        consultas.previa(con, str(tmp_path), "gold/funil_compra/_SUCCESS")


def test_conexao_travada_nao_le_fora_da_raiz(lago):
    con, _, _ = lago
    with pytest.raises(duckdb.Error):
        consultas.executar(con, "SELECT * FROM read_text('/etc/hostname')")
    with pytest.raises(duckdb.Error):
        con.sql("SET enable_external_access = true")


@pytest.mark.parametrize("sql, trecho", [
    ("SELECT * FROM nao_existe", "tabela ou view não existe"),
    ("SELECT coluna_inventada FROM silver.eventos", "coluna ou função não foi encontrada"),
    ("SELECT CAST('abc' AS INTEGER)", "não pôde ser convertido"),
])
def test_explicar_erro_traduz_erros_comuns(lago, sql, trecho):
    con, _, _ = lago
    with pytest.raises(duckdb.Error) as erro:
        consultas.executar(con, sql)
    assert trecho in consultas.explicar_erro(erro.value)


def test_explicar_erro_tem_frase_padrao():
    assert consultas.explicar_erro(duckdb.Error("x")) == "O DuckDB não conseguiu rodar a consulta."


def test_previa_recusa_caminho_com_ponto_ponto(lago):
    con, _, raiz = lago
    with pytest.raises(ValueError, match="dentro do bucket"):
        consultas.previa(con, str(raiz), "silver/../../etc/x.parquet")


def test_view_de_outro_bucket_le_do_bucket_certo_e_a_trava_cobre_os_dois(tmp_path):
    datalake, outro = tmp_path / "datalake", tmp_path / "outro"
    (datalake / "gold" / "funil").mkdir(parents=True)
    (outro / "notas").mkdir(parents=True)
    duckdb.sql(f"COPY (SELECT 1 AS etapa) TO '{datalake}/gold/funil/a.parquet' (FORMAT parquet)")
    duckdb.sql(f"COPY (SELECT 9 AS nota) TO '{outro}/notas/a.parquet' (FORMAT parquet)")
    (tmp_path / "fora").mkdir()
    duckdb.sql(f"COPY (SELECT 0 AS segredo) TO '{tmp_path}/fora/x.parquet' (FORMAT parquet)")
    chaves = ["gold/funil/a.parquet", particoes.chave_virtual("rascunho", "notas/a.parquet")]
    raiz_de = lambda bucket=None: str(outro) if bucket == "rascunho" else str(datalake)
    con = consultas.conectar(s3=False)
    consultas.criar_views(con, raiz_de, particoes.datasets(chaves))
    consultas.travar(con, [str(datalake), str(outro)])
    assert consultas.executar(con, "SELECT nota FROM rascunho.notas").tabela["nota"].tolist() == [9]
    assert consultas.executar(con, "SELECT etapa FROM gold.funil").tabela["etapa"].tolist() == [1]
    with pytest.raises(duckdb.Error):                                  # fora dos buckets: bloqueado
        consultas.executar(con, f"SELECT * FROM read_parquet('{tmp_path}/fora/x.parquet')")


def test_origem_com_raiz_em_texto_usa_s3_para_os_outros_buckets():
    dataset = next(d for d in particoes.datasets([particoes.chave_virtual("rascunho", "notas/a.parquet")]))
    assert "'s3://rascunho/notas/**/*.parquet'" in consultas.origem("s3://datalake", dataset)
