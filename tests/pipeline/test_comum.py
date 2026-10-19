import comum


def test_caminho_em_outro_bucket():
    assert comum.caminho("notas", bucket="rascunho-turma") == "s3a://rascunho-turma/notas"


def test_caminho_aponta_para_o_bucket_por_s3a():
    assert comum.caminho("silver/itens") == f"s3a://{comum.BUCKET}/silver/itens"
    assert comum.glob_eventos("silver") == "silver/event_name=*"


def test_existe_usa_o_filesystem_do_hadoop(spark, tmp_path):
    (tmp_path / "camada").mkdir()
    assert comum.existe(spark, (tmp_path / "camada").as_uri()) is True
    assert comum.existe(spark, (tmp_path / "nada").as_uri()) is False


def test_gravar_eventos_preserva_as_pastas_vizinhas_e_ler_eventos_as_ignora(spark, tmp_path, monkeypatch):
    monkeypatch.setattr(comum, "caminho", lambda camada: f"file://{tmp_path}/{camada}")
    spark.createDataFrame([("i1",)], ["item_id"]).write.parquet(comum.caminho("silver/itens"))
    linhas = [("e1", "page_view", "2026", "09", "01"), ("e2", "scroll", "2026", "09", "01")]
    df = spark.createDataFrame(linhas, ["event_id", "event_name", "year", "month", "day"])

    comum.gravar_eventos(df, "silver", "overwrite")
    comum.gravar_eventos(df.filter("event_name = 'scroll'"), "silver", "overwrite")

    assert (tmp_path / "silver" / "itens").is_dir()
    assert (tmp_path / "silver" / "event_name=page_view" / "year=2026" / "month=09" / "day=01").is_dir()
    lidos = comum.ler_eventos(spark, "silver")
    assert sorted((r.event_id, r.event_name, r.month) for r in lidos.collect()) == [
        ("e1", "page_view", "09"), ("e2", "scroll", "09")]
    assert comum.existe(spark, comum.caminho(comum.glob_eventos("silver"))) is True
    assert comum.existe(spark, comum.caminho(comum.glob_eventos("bronze"))) is False


def test_exigir_camada_para_com_a_mensagem_do_que_rodar(spark, tmp_path, monkeypatch):
    monkeypatch.setattr(comum, "caminho", lambda camada: f"file://{tmp_path}/{camada}")
    monkeypatch.setattr(spark, "stop", lambda: None)       # a sessão é compartilhada pelos testes
    try:
        comum.exigir_camada(spark, comum.glob_eventos("bronze"), "python pipeline/bronze.py")
    except SystemExit as erro:
        assert "Rode antes: python pipeline/bronze.py" in str(erro)
    else:
        raise AssertionError("exigir_camada deveria parar")


def test_ler_eventos_aceita_schema_explicito_para_a_landing(spark, tmp_path, monkeypatch):
    from pyspark.sql.types import StringType, StructField, StructType
    monkeypatch.setattr(comum, "caminho", lambda camada: f"file://{tmp_path}/{camada}")
    pasta = tmp_path / "landing" / "event_name=scroll" / "year=2026" / "month=09" / "day=01"
    pasta.mkdir(parents=True)
    (pasta / "coletor-s42-001.jsonl").write_text('{"event_id":"a","event_name":"scroll","extra":1}\n')
    schema = StructType([StructField("event_id", StringType()), StructField("event_name", StringType())])
    df = comum.ler_eventos(spark, "landing", "json", schema=schema)
    assert "extra" not in df.columns
    assert [(r.event_id, r.event_name, r.month) for r in df.collect()] == [("a", "scroll", "09")]


def test_arquivo_do_projeto_parte_da_pasta_atual(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert comum.arquivo_do_projeto("site/mapa_calor.js") == tmp_path / "site" / "mapa_calor.js"
