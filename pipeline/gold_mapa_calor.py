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


MARCOS_ROLAGEM = [0, 25, 50, 75, 90]


def com_pagina(eventos):
    """5.4 (12): caminho de page_location sem domínio, # e ?. A raiz vira /."""

    caminho_pagina = F.regexp_replace(
        F.regexp_replace(
            F.col("page.location"),
            r"^https?://[^/]+",
            ""
        ),
        r"[?#].*$",
        ""
    )

    return eventos.withColumn(
        "pagina",
        F.when(
            F.col("page.location").isNull(),
            F.lit(None)
        ).when(
            caminho_pagina == "",
            F.lit("/")
        ).otherwise(caminho_pagina)
    )


def sessoes_com_page_view(eventos):
    """Sessões distintas com page_view em cada página."""

    return (
        eventos
        .filter(
            (F.col("event_name") == "page_view")
            & F.col("pagina").isNotNull()
        )
        .select("pagina", "session_id")
        .distinct()
    )


def criar_mapa_calor_cliques(eventos, page_views):
    """Uma linha por página e element_id."""

    sessoes_na_pagina = page_views.groupBy("pagina").agg(
        F.count("*").alias("sessoes_na_pagina")
    )

    por_pagina = Window.partitionBy("pagina")

    return (
        eventos
        .filter(
            F.col("element_id").isNotNull()
            & F.col("pagina").isNotNull()
        )
        .groupBy("pagina", "element_id")
        .agg(
            F.count("*").alias("cliques"),
            F.countDistinct("session_id").alias("sessoes"),
        )
        .join(sessoes_na_pagina, "pagina", "left")
        .fillna({"sessoes_na_pagina": 0})
        .withColumn(
            "taxa_clique",
            # try_divide devolve nulo quando o divisor é 0
            F.round(
                F.try_divide(
                    F.col("sessoes"),
                    F.col("sessoes_na_pagina")
                ),
                4
            )
        )
        .withColumn(
            "intensidade",
            F.round(
                F.col("cliques") / F.max("cliques").over(por_pagina),
                4
            )
        )
        .select(
            "pagina",
            "element_id",
            "cliques",
            "sessoes",
            "sessoes_na_pagina",
            "taxa_clique",
            "intensidade",
        )
    )


def criar_mapa_calor_rolagem(eventos, page_views):
    """Sessões com page_view na landing que chegaram a cada marco."""

    base = (
        page_views
        .filter(F.col("pagina") == "/")
        .select("session_id")
    )

    maior_rolagem = (
        eventos
        .filter(
            (F.col("event_name") == "scroll")
            & (F.col("pagina") == "/")
        )
        .groupBy("session_id")
        .agg(F.max("percent_scrolled").alias("maior_percent"))
    )

    por_sessao = base.join(maior_rolagem, "session_id", "left")

    contagens = por_sessao.agg(*[
        (
            F.count("*")
            if marco == 0
            else F.sum(
                F.when(F.col("maior_percent") >= marco, 1)
                 .otherwise(0)
            )
        ).alias(f"m{marco}")
        for marco in MARCOS_ROLAGEM
    ])

    return contagens.select(
        F.explode(F.array(*[
            F.struct(
                F.lit("/").alias("pagina"),
                F.lit(marco).alias("marco"),
                F.col(f"m{marco}").cast("long").alias("sessoes_que_chegaram"),
                F.round(
                    F.try_divide(F.col(f"m{marco}"), F.col("m0")),
                    4
                ).alias("pct_sessoes"),
            )
            for marco in MARCOS_ROLAGEM
        ])).alias("_linha")
    ).select("_linha.*")


def main():
    spark = criar_sessao("gold_mapa_calor")

    try:
        # Verificar se a Silver existe
        exigir_camada(
            spark,
            glob_eventos("silver"),
            "python pipeline/silver.py"
        )

        eventos = com_pagina(ler_eventos(spark, "silver"))
        page_views = sessoes_com_page_view(eventos).cache()

        titulo("Gold - Mapa de calor: cliques")

        cliques = criar_mapa_calor_cliques(eventos, page_views)

        cliques.write.mode("overwrite").parquet(
            caminho("gold/mapa_calor_cliques")
        )

        print("Tabela mapa_calor_cliques gravada!")
        cliques.orderBy("pagina", F.desc("cliques")).show(
            40, truncate=False
        )

        titulo("Gold - Mapa de calor: rolagem")

        rolagem = criar_mapa_calor_rolagem(eventos, page_views)

        rolagem.write.mode("overwrite").parquet(
            caminho("gold/mapa_calor_rolagem")
        )

        print("Tabela mapa_calor_rolagem gravada!")
        rolagem.orderBy("marco").show(truncate=False)

        titulo("Gold - Finalizado")
        print("Gold Mapa de Calor executada com sucesso!")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
