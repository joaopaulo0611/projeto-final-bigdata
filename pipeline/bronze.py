
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    DoubleType,
    LongType,
    ArrayType,
    MapType,
)

from comum import (
    criar_sessao,
    exigir_camada,
    glob_eventos,
    ler_eventos,
    gravar_eventos,
    titulo,
)


# R4: schema explícito para os eventos da landing.
# Mantemos event_ts como string, pois a Bronze não deve
# descartar nem corrigir timestamps inválidos.
SCHEMA = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_name", StringType(), True),
    StructField("event_ts", StringType(), True),
    StructField("user_pseudo_id", StringType(), True),
    StructField("user_id", StringType(), True),
    StructField("session_hint", StringType(), True),

    StructField("page", StructType([
        StructField("location", StringType(), True),
        StructField("referrer", StringType(), True),
    ]), True),

    StructField("traffic", StructType([
        StructField("source", StringType(), True),
        StructField("medium", StringType(), True),
        StructField("campaign", StringType(), True),
    ]), True),

    StructField("device", StructType([
        StructField("category", StringType(), True),
        StructField("os", StringType(), True),
        StructField("browser", StringType(), True),
    ]), True),

    # Valores heterogêneos convertidos para texto.
    # A Silver será responsável pela tipagem.
    StructField(
        "params",
        MapType(StringType(), StringType()),
        True
    ),

    StructField("items", ArrayType(StructType([
        StructField("item_id", StringType(), True),
        StructField("item_name", StringType(), True),
        StructField("item_category", StringType(), True),
        StructField("price", DoubleType(), True),
        StructField("quantity", LongType(), True),
    ])), True),
])


def main():
    spark = criar_sessao("bronze")

    try:
        # R2: verificar a existência da camada anterior
        exigir_camada(
            spark,
            glob_eventos("landing"),
            "python gerador/gerar_eventos.py"
        )

        # R1 e R4: ler JSON pelo Spark com schema explícito
        landing = ler_eventos(
            spark,
            "landing",
            "json",
            schema=SCHEMA
        )

        # R4: adicionar proveniência.
        # As colunas de partição vêm do caminho da landing.
        bronze = (
            landing
            .withColumn(
                "arquivo_origem",
                F.input_file_name()
            )
            .withColumn(
                "ingestao_ts",
                F.current_timestamp()
            )
        )

        titulo("Bronze - Ingestão")

        # Contagem para conferir a leitura
        print(f"Eventos recebidos: {bronze.count()}")

        # R4: gravação append-only em Parquet
        gravar_eventos(bronze, "bronze", "append")

        print("Camada Bronze gravada com sucesso!")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
