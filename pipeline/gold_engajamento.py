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


MARCOS_VIDEO = [10, 25, 50, 75, 100]


def criar_sessoes(eventos):
    """Uma linha por sessão, com canal e dispositivo do primeiro evento."""

    ordem = Window.partitionBy("session_id").orderBy(
        F.col("event_timestamp").asc(),
        F.col("event_id").asc()
    )

    primeiros = (
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
            ).alias("canal"),
            F.col("device.category").alias("dispositivo")
        )
    )

    resumo = eventos.groupBy("session_id").agg(
        F.first("user_pseudo_id").alias("user_pseudo_id"),
        F.max("user_id").alias("user_id"),
        F.min("event_timestamp").alias("inicio"),
        F.max("event_timestamp").alias("fim"),
        F.count("*").alias("eventos"),
        F.coalesce(
            F.max("percent_scrolled"), F.lit(0)
        ).alias("scroll_maximo"),
        F.max("video_percent").alias("video_percent_maximo"),
        F.max(
            F.col("event_name") == "generate_lead"
        ).alias("fez_lead"),
        F.max(
            F.col("event_name") == "purchase"
        ).alias("comprou"),
    )

    return (
        resumo
        .withColumn(
            "duracao_segundos",
            F.unix_timestamp("fim") - F.unix_timestamp("inicio")
        )
        .join(primeiros, "session_id", "inner")
        .select(
            "session_id",
            "user_pseudo_id",
            "user_id",
            "inicio",
            "fim",
            "duracao_segundos",
            "eventos",
            "scroll_maximo",
            "video_percent_maximo",
            "fez_lead",
            "comprou",
            "canal",
            "dispositivo",
        )
    )


def criar_retencao_video(eventos):
    """Das sessões com video_start, quantas chegaram a cada marco."""

    por_sessao = (
        eventos
        .filter(F.col("event_name").startswith("video_"))
        .groupBy("session_id")
        .agg(
            F.max(
                F.col("event_name") == "video_start"
            ).alias("iniciou"),
            F.max("video_percent").alias("maior_percent")
        )
        .filter(F.col("iniciou"))
    )

    return por_sessao.agg(
        F.count("*").alias("sessoes_com_video_start"),
        *[
            F.sum(
                F.when(F.col("maior_percent") >= marco, 1)
                 .otherwise(0)
            ).alias(f"m{marco}")
            for marco in MARCOS_VIDEO
        ]
    ).select(
        F.explode(F.array(*[
            F.struct(
                F.lit(marco).alias("marco"),
                F.col("sessoes_com_video_start"),
                F.col(f"m{marco}").alias("sessoes_que_chegaram"),
            )
            for marco in MARCOS_VIDEO
        ])).alias("_linha")
    ).select(
        "_linha.*"
    ).withColumn(
        "pct_sessoes",
        F.round(
            F.try_divide(
                F.col("sessoes_que_chegaram"),
                F.col("sessoes_com_video_start")
            ),
            4
        )
    )


def criar_buscas_faq(eventos):
    """Termo, total de buscas e buscas sem resultado."""

    return (
        eventos
        .filter(F.col("event_name") == "site_search")
        .withColumn(
            "termo",
            F.lower(F.trim(F.col("search_term")))
        )
        .groupBy("termo")
        .agg(
            F.count("*").alias("total_buscas"),
            F.sum(
                F.when(F.col("search_results") == 0, 1)
                 .otherwise(0)
            ).alias("buscas_sem_resultado"),
        )
        .withColumn(
            "taxa_sem_resultado",
            F.round(
                F.try_divide(
                    F.col("buscas_sem_resultado"),
                    F.col("total_buscas")
                ),
                4
            )
        )
    )


def criar_saidas_downloads(eventos):
    """Cliques de saída por domínio e downloads por arquivo."""

    saidas = (
        eventos
        .filter(
            (F.col("event_name") == "click")
            & F.col("outbound")
        )
        .groupBy(F.col("link_domain").alias("destino"))
        .agg(
            F.count("*").alias("total"),
            F.countDistinct("session_id").alias("sessoes"),
        )
        .withColumn("tipo", F.lit("saida"))
    )

    downloads = (
        eventos
        .filter(F.col("event_name") == "file_download")
        .groupBy(F.col("file_name").alias("destino"))
        .agg(
            F.count("*").alias("total"),
            F.countDistinct("session_id").alias("sessoes"),
        )
        .withColumn("tipo", F.lit("download"))
    )

    return (
        saidas.unionByName(downloads)
        .select("tipo", "destino", "total", "sessoes")
    )


def main():
    spark = criar_sessao("gold_engajamento")

    try:
        # Verificar se a Silver existe
        exigir_camada(
            spark,
            glob_eventos("silver"),
            "python pipeline/silver.py"
        )

        eventos = ler_eventos(spark, "silver")

        titulo("Gold - Sessões")

        sessoes = criar_sessoes(eventos)

        sessoes.write.mode("overwrite").parquet(
            caminho("gold/sessoes")
        )

        print("Tabela sessoes gravada!")
        sessoes.show(10, truncate=False)

        titulo("Gold - Retenção do vídeo")

        retencao = criar_retencao_video(eventos)

        retencao.write.mode("overwrite").parquet(
            caminho("gold/retencao_video")
        )

        print("Tabela retencao_video gravada!")
        retencao.orderBy("marco").show(truncate=False)

        titulo("Gold - Buscas no FAQ")

        buscas = criar_buscas_faq(eventos)

        buscas.write.mode("overwrite").parquet(
            caminho("gold/buscas_faq")
        )

        print("Tabela buscas_faq gravada!")
        buscas.orderBy(
            F.desc("buscas_sem_resultado"),
            F.desc("total_buscas")
        ).show(truncate=False)

        titulo("Gold - Saídas e downloads")

        saidas = criar_saidas_downloads(eventos)

        saidas.write.mode("overwrite").parquet(
            caminho("gold/saidas_downloads")
        )

        print("Tabela saidas_downloads gravada!")
        saidas.orderBy("tipo", F.desc("total")).show(truncate=False)

        titulo("Gold - Finalizado")
        print("Gold Engajamento executada com sucesso!")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
