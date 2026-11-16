"""Peças prontas para os seus jobs: use em vez de reescrever.

    from comum import criar_sessao, caminho, exigir_camada, glob_eventos, ler_eventos, gravar_eventos, titulo

Este arquivo vem pronto no pacote do projeto. Ele cuida da parte repetitiva
(configurar o Spark para o floci, montar caminhos s3a://, conferir se uma camada
existe, ler e gravar as partições event_name=…) para você gastar o tempo no que
o enunciado avalia: as transformações de cada camada.

Tudo aqui fala com o S3 só pelo Spark (requisito R1). Para saber se uma pasta
existe, ou para apagá-la, usa o FileSystem do Hadoop pela JVM do próprio Spark,
sem boto3.
"""

from __future__ import annotations

import os
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL") or "http://floci:4566"
BUCKET = os.environ.get("AWS_S3_BUCKET", "datalake-tracking")


def criar_sessao(nome: str) -> SparkSession:
    """A SparkSession pronta para o floci. `nome` aparece nos logs do Spark (ex.: "bronze")."""
    spark = (
        SparkSession.builder
        .appName(nome)
        .master("local[4]")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.session.timeZone", "UTC")
        # year=2026/month=09/day=01: sem inferência, month continua "09" (e não 9) ao regravar
        .config("spark.sql.sources.partitionColumnTypeInference.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.endpoint", ENDPOINT)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
        .config("spark.hadoop.fs.s3a.access.key", os.environ.get("AWS_ACCESS_KEY_ID", "test"))
        .config("spark.hadoop.fs.s3a.secret.key", os.environ.get("AWS_SECRET_ACCESS_KEY", "test"))
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def arquivo_do_projeto(relativo: str) -> Path:
    """Um arquivo do repositório, fora do S3: arquivo_do_projeto("site/mapa_calor.js") -> /projeto/site/mapa_calor.js.

    Os jobs rodam sempre com a pasta do projeto como diretório atual: no terminal (docker compose run)
    e no explorador, mesmo quando o script vem do floci e roda de uma pasta temporária. Por isso
    não use Path(__file__) para achar o projeto."""
    return Path.cwd() / relativo


def caminho(camada: str, bucket: str | None = None) -> str:
    """'silver/itens' -> 's3a://datalake-tracking/silver/itens'.

    Para ler ou gravar em outro bucket do floci, passe o nome dele:
    caminho("notas", bucket="rascunho-turma") -> 's3a://rascunho-turma/notas'."""
    return f"s3a://{bucket or BUCKET}/{camada}"


# Os eventos de cada camada ficam em <camada>/event_name=<nome>/year=…/month=…/day=…
# (sem pasta "eventos"). Na Silver, itens/ e eventos_rejeitados/ ficam ao lado das partições.
PARTICAO_EVENTOS = "event_name=*"
COLUNAS_PARTICAO = ["event_name", "year", "month", "day"]


def glob_eventos(camada: str) -> str:
    """'silver' -> 'silver/event_name=*': o glob (curinga) que pega só as pastas de eventos."""
    return f"{camada}/{PARTICAO_EVENTOS}"


def ler_eventos(spark, camada: str, formato: str = "parquet", schema=None) -> DataFrame:
    """Lê só as pastas event_name=… da camada.

        ler_eventos(spark, "landing", "json", schema=SCHEMA)   # landing: JSON com schema explícito (R4)
        ler_eventos(spark, "bronze")                           # Bronze e Silver: Parquet

    O basePath faz o Spark devolver event_name, year, month e day como colunas e
    ignorar as pastas vizinhas (silver/itens, silver/eventos_rejeitados)."""
    leitor = spark.read.option("basePath", caminho(camada))
    if schema is not None:
        leitor = leitor.schema(schema)
    return leitor.format(formato).load(caminho(glob_eventos(camada)))


def gravar_eventos(df: DataFrame, camada: str, modo: str) -> None:
    """Grava particionado por event_name/year/month/day direto na raiz da camada.

    `modo` é "append" (Bronze) ou "overwrite" (Silver). Com "overwrite", o modo
    dinâmico troca só as partições presentes no DataFrame: sem ele, o Spark
    apagaria a pasta inteira da camada (e, na Silver, itens/ e eventos_rejeitados/ junto).
    As colunas event_name, year, month e day precisam existir no DataFrame, como texto."""
    (df.write.mode(modo).option("partitionOverwriteMode", "dynamic")
       .partitionBy(*COLUNAS_PARTICAO).parquet(caminho(camada)))


def _sistema_de_arquivos(spark, uri: str):
    path = spark._jvm.org.apache.hadoop.fs.Path(uri)
    return path.getFileSystem(spark._jsc.hadoopConfiguration()), path


def existe(spark, uri: str) -> bool:
    """True se a pasta existe. Aceita glob (ex.: .../silver/event_name=*): basta alguma pasta casar."""
    fs, path = _sistema_de_arquivos(spark, uri)
    if "*" in uri:
        return bool(fs.globStatus(path))
    return bool(fs.exists(path))


def camada_existe(spark, camada: str) -> bool:
    return existe(spark, caminho(camada))


def exigir_camada(spark, camada: str, comando: str) -> None:
    """Para o job com uma mensagem clara se a camada anterior não existe (requisito R2).

        exigir_camada(spark, glob_eventos("bronze"), "python pipeline/bronze.py")
    """
    if not camada_existe(spark, camada):
        spark.stop()
        raise SystemExit(f"{caminho(camada)} não existe. Rode antes: {comando}")


def apagar_camada(spark, camada: str) -> bool:
    """Apaga a pasta da camada inteira (para recomeçar do zero). Devolve True se havia algo."""
    fs, path = _sistema_de_arquivos(spark, caminho(camada))
    return bool(fs.exists(path) and fs.delete(path, True))


def titulo(texto: str) -> None:
    """Imprime um título destacado no terminal, para separar a saída de cada job."""
    print(f"\n{'=' * 70}\n{texto}\n{'=' * 70}")
