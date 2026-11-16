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


def canal_por_sessao(eventos):
    """Canal do primeiro evento de cada sessão."""

    ordem = Window.partitionBy("session_id").orderBy(
        F.col("event_timestamp").asc(),
        F.col("event_id").asc()
    )

    return (
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


def preparar_compras(eventos, canais):
    """Uma linha por compra, com plano, canal e o reembolso atribuído."""

    reembolsos = (
        eventos
        .filter(F.col("event_name") == "refund")
        .groupBy("transaction_id")
        .agg(F.sum("value").alias("valor_reembolsado"))
    )

    plano = F.filter(
        "items",
        lambda item: item.item_category == "plano"
    ).getItem(0).getField("item_id")

    tem_bump = F.exists(
        "items",
        lambda item: item.item_id == "BUMP-MENTORIA"
    )

    return (
        eventos
        .filter(F.col("event_name") == "purchase")
        .select(
            "transaction_id",
            "session_id",
            "user_pseudo_id",
            "user_id",
            "event_timestamp",
            # 5.4 (10): data da compra em UTC
            F.to_date("event_timestamp").alias("data_compra"),
            F.coalesce(plano, F.lit("(nenhum)")).alias("plano"),
            tem_bump.alias("tem_bump"),
            F.col("value").alias("valor_bruto"),
        )
        .join(canais, "session_id", "left")
        # O reembolso volta para a data, o plano e o canal da compra
        .join(reembolsos, "transaction_id", "left")
        .fillna({"valor_reembolsado": 0.0})
        .withColumn(
            "reembolsada",
            F.col("valor_reembolsado") > 0
        )
    )


def criar_receita_diaria(compras):
    """Receita bruta, reembolsada e líquida por data, plano e canal."""

    return (
        compras
        .groupBy("data_compra", "plano", "canal")
        .agg(
            F.round(F.sum("valor_bruto"), 2).alias("receita_bruta"),
            F.round(
                F.sum("valor_reembolsado"), 2
            ).alias("receita_reembolsada"),
            F.count("*").alias("pedidos"),
        )
        .withColumn(
            "receita_liquida",
            F.round(
                F.col("receita_bruta") - F.col("receita_reembolsada"),
                2
            )
        )
        .withColumn(
            "ticket_medio",
            F.round(
                F.try_divide(
                    F.col("receita_bruta"),
                    F.col("pedidos")
                ),
                2
            )
        )
        .select(
            "data_compra",
            "plano",
            "canal",
            "receita_bruta",
            "receita_reembolsada",
            "receita_liquida",
            "pedidos",
            "ticket_medio",
        )
    )


def criar_taxa_reembolso(compras):
    """Pedidos com reembolso ÷ pedidos, por plano e canal."""

    return (
        compras
        .groupBy("plano", "canal")
        .agg(
            F.count("*").alias("pedidos"),
            F.sum(
                F.when(F.col("reembolsada"), 1).otherwise(0)
            ).alias("pedidos_reembolsados"),
            F.round(F.sum("valor_bruto"), 2).alias("receita_bruta"),
            F.round(
                F.sum("valor_reembolsado"), 2
            ).alias("receita_reembolsada"),
        )
        .withColumn(
            "taxa_reembolso",
            F.round(
                F.try_divide(
                    F.col("pedidos_reembolsados"),
                    F.col("pedidos")
                ),
                4
            )
        )
    )


def criar_adesao_order_bump(compras):
    """Percentual de compras com BUMP-MENTORIA, total e por plano."""

    total = compras.withColumn("plano", F.lit("(todos)"))

    return (
        compras.unionByName(total)
        .groupBy("plano")
        .agg(
            F.count("*").alias("compras"),
            F.sum(
                F.when(F.col("tem_bump"), 1).otherwise(0)
            ).alias("compras_com_bump"),
        )
        .withColumn(
            "adesao_bump",
            F.round(
                F.try_divide(
                    F.col("compras_com_bump"),
                    F.col("compras")
                ),
                4
            )
        )
    )


def criar_lead_para_compra(eventos, canais, compras):
    """Primeiro lead da pessoa e a primeira compra estritamente depois dele."""

    # 5.4 (5): a pessoa é o user_id resolvido, ou o user_pseudo_id
    pessoa = F.coalesce(F.col("user_id"), F.col("user_pseudo_id"))

    ordem_lead = Window.partitionBy("pessoa").orderBy(
        F.col("event_timestamp").asc(),
        F.col("event_id").asc()
    )

    # 5.4 (9): o canal do lead é o da sessão do primeiro generate_lead
    leads = (
        eventos
        .filter(F.col("event_name") == "generate_lead")
        .withColumn("pessoa", pessoa)
        .withColumn("_ordem", F.row_number().over(ordem_lead))
        .filter(F.col("_ordem") == 1)
        .join(canais, "session_id", "left")
        .select(
            "pessoa",
            F.col("event_timestamp").alias("ts_lead"),
            "canal",
        )
    )

    primeira_compra = (
        compras
        .withColumn("pessoa", pessoa)
        .join(leads.select("pessoa", "ts_lead"), "pessoa", "inner")
        .filter(F.col("event_timestamp") > F.col("ts_lead"))
        .groupBy("pessoa")
        .agg(F.min("event_timestamp").alias("ts_compra"))
    )

    base = (
        leads
        .join(primeira_compra, "pessoa", "left")
        .withColumn(
            "dias",
            (
                F.unix_timestamp("ts_compra")
                - F.unix_timestamp("ts_lead")
            ) / 86400
        )
    )

    total = base.withColumn("canal", F.lit("(todos)"))

    return (
        base.unionByName(total)
        .groupBy("canal")
        .agg(
            F.count("*").alias("leads"),
            F.count("ts_compra").alias("compraram_depois"),
            # 5.4 (8): mediana com percentile_approx
            F.percentile_approx("dias", 0.5).alias("mediana_dias"),
        )
        .withColumn(
            "taxa_conversao",
            F.round(
                F.try_divide(
                    F.col("compraram_depois"),
                    F.col("leads")
                ),
                4
            )
        )
        .withColumn("mediana_dias", F.round("mediana_dias", 2))
    )


def main():
    spark = criar_sessao("gold_receita")

    try:
        # Verificar se a Silver existe
        exigir_camada(
            spark,
            glob_eventos("silver"),
            "python pipeline/silver.py"
        )

        eventos = ler_eventos(spark, "silver")
        canais = canal_por_sessao(eventos)
        compras = preparar_compras(eventos, canais).cache()

        titulo("Gold - Receita diária")

        receita = criar_receita_diaria(compras)

        receita.write.mode("overwrite").parquet(
            caminho("gold/receita_diaria")
        )

        print("Tabela receita_diaria gravada!")
        receita.orderBy("data_compra", "plano", "canal").show(
            10, truncate=False
        )
        receita.agg(
            F.round(F.sum("receita_bruta"), 2).alias("bruta"),
            F.round(F.sum("receita_reembolsada"), 2).alias("reembolsada"),
            F.round(F.sum("receita_liquida"), 2).alias("liquida"),
            F.sum("pedidos").alias("pedidos"),
        ).show(truncate=False)

        titulo("Gold - Taxa de reembolso")

        reembolso = criar_taxa_reembolso(compras)

        reembolso.write.mode("overwrite").parquet(
            caminho("gold/taxa_reembolso")
        )

        print("Tabela taxa_reembolso gravada!")
        reembolso.orderBy("plano", "canal").show(30, truncate=False)

        titulo("Gold - Adesão ao order bump")

        bump = criar_adesao_order_bump(compras)

        bump.write.mode("overwrite").parquet(
            caminho("gold/adesao_order_bump")
        )

        print("Tabela adesao_order_bump gravada!")
        bump.orderBy("plano").show(truncate=False)

        titulo("Gold - Lead para compra")

        lead = criar_lead_para_compra(eventos, canais, compras)

        lead.write.mode("overwrite").parquet(
            caminho("gold/lead_para_compra")
        )

        print("Tabela lead_para_compra gravada!")
        lead.orderBy("canal").show(truncate=False)

        titulo("Gold - Finalizado")
        print("Gold Receita e Aquisição executada com sucesso!")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
