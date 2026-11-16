
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from comum import (
    criar_sessao,
    exigir_camada,
    glob_eventos,
    ler_eventos,
    caminho,
    titulo,
)


ETAPAS_COMPRA = [
    "view_item_list",
    "select_item",
    "add_to_cart",
    "view_cart",
    "begin_checkout",
    "add_payment_info",
    "purchase",
]


def preparar_sessoes(eventos):
    """Define canal e plano de cada sessão."""

    ordem = Window.partitionBy("session_id").orderBy(
        F.col("event_timestamp").asc(),
        F.col("event_id").asc()
    )

    # Canal do primeiro evento da sessão
    canais = (
        eventos
        .withColumn("_ordem", F.row_number().over(ordem))
        .filter(F.col("_ordem") == 1)
        .select(
            "session_id",
            F.concat(
                F.coalesce(
                    F.col("traffic.source"),
                    F.lit("(unknown)")
                ),
                F.lit(" / "),
                F.coalesce(
                    F.col("traffic.medium"),
                    F.lit("(unknown)")
                )
            ).alias("canal")
        )
    )

    # Plano do primeiro select_item da sessão
    planos = (
        eventos
        .filter(F.col("event_name") == "select_item")
        .withColumn("_ordem", F.row_number().over(ordem))
        .filter(F.col("_ordem") == 1)
        .select(
            "session_id",
            F.col("items").getItem(0)
                .getField("item_id").alias("plano")
        )
    )

    return (
        canais.join(planos, "session_id", "left")
        .fillna({"plano": "(nenhum)"})
    )


def criar_funil_compra(eventos, sessoes):
    """Funil completo, total e por plano e canal."""

    nomes = ETAPAS_COMPRA + ["view_item"]

    marcadores = eventos.groupBy("session_id").agg(
        *[
            F.max(
                F.when(F.col("event_name") == nome, 1)
                 .otherwise(0)
            ).alias(nome)
            for nome in nomes
        ]
    )

    base = sessoes.join(
        marcadores, "session_id", "inner"
    )

    # Total geral e detalhamento por plano/canal
    total = (
        base.withColumn("plano", F.lit("(todos)"))
            .withColumn("canal", F.lit("(todos)"))
    )

    base = base.unionByName(total)

    agregacoes = base.groupBy("plano", "canal").agg(
        *[
            F.sum(F.col(nome)).alias(nome)
            for nome in nomes
        ]
    )

    # Uma linha por etapa do funil
    resultado = None

    for indice, etapa in enumerate(ETAPAS_COMPRA):

        anterior = (
            ETAPAS_COMPRA[indice - 1]
            if indice > 0
            else None
        )

        etapa_df = agregacoes.select(
            "plano",
            "canal",
            F.lit(indice + 1).alias("ordem_etapa"),
            F.lit(etapa).alias("etapa"),
            F.col(etapa).alias("sessoes"),

            (
                F.lit(1.0)
                if anterior is None
                else F.try_divide(
                    F.col(etapa),
                    F.col(anterior)
                )
            ).alias("conversao_anterior"),

            F.try_divide(
                F.col(etapa),
                F.col("view_item_list")
            ).alias("conversao_topo"),

            F.try_divide(
                F.col("view_item"),
                F.col("select_item")
            ).alias("taxa_view_item")
        )

        resultado = (
            etapa_df if resultado is None
            else resultado.unionByName(etapa_df)
        )

    return resultado


def criar_funil_lead(eventos, sessoes):
    """Page view da landing -> scroll >= 50 -> lead."""

    # Extrair apenas o caminho da URL
    caminho_pagina = F.regexp_replace(
        F.regexp_replace(
            F.col("page.location"),
            r"^https?://[^/]+",
            ""
        ),
        r"[?#].*$",
        ""
    )

    eventos = eventos.withColumn(
        "_pagina",
        F.when(
            caminho_pagina.isNull()
            | (caminho_pagina == ""),
            F.lit("/")
        ).otherwise(caminho_pagina)
    )

    marcadores = eventos.groupBy("session_id").agg(
        F.max(
            F.when(
                (F.col("event_name") == "page_view")
                & (F.col("_pagina") == "/"),
                1
            ).otherwise(0)
        ).alias("page_view"),

        F.max(
            F.when(
                (F.col("event_name") == "scroll")
                & (F.col("_pagina") == "/")
                & (F.col("percent_scrolled") >= 50),
                1
            ).otherwise(0)
        ).alias("scroll_50"),

        F.max(
            F.when(
                F.col("event_name") == "generate_lead",
                1
            ).otherwise(0)
        ).alias("generate_lead")
    )

    base = sessoes.join(
        marcadores, "session_id", "inner"
    )

    return base.groupBy("canal").agg(
        F.sum("page_view").alias("sessoes_landing"),
        F.sum("scroll_50").alias("sessoes_scroll_50"),
        F.sum("generate_lead").alias("sessoes_lead")
    ).withColumn(
        "taxa_scroll",
        F.try_divide(
            F.col("sessoes_scroll_50"),
            F.col("sessoes_landing")
        )
    ).withColumn(
        "taxa_lead",
        F.try_divide(
            F.col("sessoes_lead"),
            F.col("sessoes_landing")
        )
    )


def main():
    spark = criar_sessao("gold_funil")

    try:
        # Verificar se a Silver existe
        exigir_camada(
            spark,
            glob_eventos("silver"),
            "python pipeline/silver.py"
        )

        titulo("Gold - Funil de compra")

        eventos = ler_eventos(spark, "silver")
        sessoes = preparar_sessoes(eventos)

        funil_compra = criar_funil_compra(
            eventos, sessoes
        )

        funil_compra.write.mode("overwrite").parquet(
            caminho("gold/funil_compra")
        )

        print("Tabela funil_compra gravada!")
        funil_compra.orderBy(
            "plano", "canal", "ordem_etapa"
        ).show(15, truncate=False)

        titulo("Gold - Funil de leads")

        funil_lead = criar_funil_lead(
            eventos, sessoes
        )

        funil_lead.write.mode("overwrite").parquet(
            caminho("gold/funil_lead")
        )

        print("Tabela funil_lead gravada!")
        funil_lead.show(15, truncate=False)

        titulo("Gold - Finalizado")
        print("Gold Funil executada com sucesso!")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()