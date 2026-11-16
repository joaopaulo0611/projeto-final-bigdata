
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from comum import (
    criar_sessao,
    exigir_camada,
    glob_eventos,
    ler_eventos,
    gravar_eventos,
    caminho,
    titulo,
)


# R7 - Eventos conhecidos do contrato
EVENTOS_VALIDOS = [
    "page_view",
    "scroll",
    "click",
    "site_search",
    "video_start",
    "video_progress",
    "video_complete",
    "file_download",
    "view_item_list",
    "select_item",
    "view_item",
    "add_to_cart",
    "remove_from_cart",
    "view_cart",
    "begin_checkout",
    "add_shipping_info",
    "add_payment_info",
    "purchase",
    "refund",
    "generate_lead",
    "sign_up",
    "login",
]


def extrair_parametros(df):
    """R6 - Extrai os params com tipos explícitos."""

    campos_texto = [
        "currency",
        "transaction_id",
        "payment_type",
        "coupon",
        "reason",
        "shipping_tier",
        "element_id",
        "page_title",
        "link_url",
        "link_domain",
        "link_text",
        "link_id",
        "search_term",
        "search_area",
        "video_title",
        "video_provider",
        "file_name",
        "file_extension",
        "item_list_id",
        "item_list_name",
        "lead_source",
        "method",
    ]

    campos_double = [
        "value",
        "tax",
        "shipping",
        "video_duration",
        "video_current_time",
    ]

    campos_int = [
        "percent_scrolled",
        "video_percent",
        "search_results",
    ]

    for nome in campos_texto:
        df = df.withColumn(
            nome,
            F.col("params").getItem(nome)
        )

    for nome in campos_double:
        df = df.withColumn(
            nome,
            F.expr(
                f"try_cast(params['{nome}'] AS DOUBLE)"
            )
        )

    for nome in campos_int:
        df = df.withColumn(
            nome,
            F.expr(
                f"try_cast(params['{nome}'] AS INT)"
            )
        )

    df = df.withColumn(
        "outbound",
        F.expr("try_cast(params['outbound'] AS BOOLEAN)")
    )

    return df


def validar_eventos(df):
    """R7 - Aplica regras e registra motivos de rejeição."""

    # Mantém o instante original de ingestão para validação
    df = df.withColumn(
        "event_timestamp",
        F.expr("try_cast(event_ts AS TIMESTAMP)")
    )

    motivos = [
        F.when(
            F.col("event_name").isNull()
            | (~F.col("event_name").isin(EVENTOS_VALIDOS)),
            F.lit("evento fora do catálogo")
        ),

        F.when(
            F.col("event_timestamp").isNull()
            | (F.col("event_timestamp") > F.col("ingestao_ts")),
            F.lit("timestamp ausente ou futuro")
        ),

        F.when(
            F.col("event_name").isin("purchase", "refund")
            & (
                F.col("transaction_id").isNull()
                | (F.trim(F.col("transaction_id")) == "")
            ),
            F.lit("transação sem id")
        ),

        F.when(
            (F.col("value") < 0)
            | (
                F.col("value").isNotNull()
                & (
                    F.col("currency").isNull()
                    | (F.col("currency") != "BRL")
                )
            ),
            F.lit("valor monetário inválido")
        ),

        F.when(
            (
                F.col("percent_scrolled").isNotNull()
                & (~F.col("percent_scrolled").isin(25, 50, 75, 90))
            )
            | (
                F.col("video_percent").isNotNull()
                & (~F.col("video_percent").isin(
                    0, 10, 25, 50, 75, 100
                ))
            ),
            F.lit("marco fora do padrão")
        ),
    ]

    df = df.withColumn(
        "_motivos",
        F.array(*motivos)
    ).withColumn(
        "_motivos",
        F.filter("_motivos", lambda x: x.isNotNull())
    )

    # Primeiro valida as regras independentes
    preliminarmente_validos = df.filter(
        F.size("_motivos") == 0
    )

    # Compras válidas para conferir os reembolsos
    compras = (
        preliminarmente_validos
        .filter(F.col("event_name") == "purchase")
        .select("transaction_id")
        .distinct()
        .withColumn("_compra_existe", F.lit(True))
    )

    df = df.join(
        compras,
        on="transaction_id",
        how="left"
    )

    # Reembolso sem compra válida
    df = df.withColumn(
        "_motivos",
        F.when(
            (F.col("event_name") == "refund")
            & F.col("_compra_existe").isNull(),
            F.concat(
                F.col("_motivos"),
                F.array(F.lit("reembolso sem compra"))
            )
        ).otherwise(F.col("_motivos"))
    ).drop("_compra_existe")

    validos = (
        df.filter(F.size("_motivos") == 0)
        .drop("_motivos")
    )

    # Uma linha por motivo de rejeição
    rejeitados = (
        df.filter(F.size("_motivos") > 0)
        .withColumn(
            "motivo_rejeicao",
            F.explode("_motivos")
        )
        .drop("_motivos")
    )

    return validos, rejeitados


def calcular_sessoes(df):
    """R8 - Nova sessão após mais de 30 minutos."""

    # Nunca utiliza session_hint.
    # IDs nulos recebem uma chave própria por evento.
    df = df.withColumn(
        "_chave_visitante",
        F.coalesce(
            F.col("user_pseudo_id"),
            F.concat(F.lit("sem-id-"), F.col("event_id"))
        )
    )

    janela = (
        Window
        .partitionBy("_chave_visitante")
        .orderBy("event_timestamp", "event_id")
    )

    df = df.withColumn(
        "_evento_anterior",
        F.lag("event_timestamp").over(janela)
    )

    df = df.withColumn(
        "_nova_sessao",
        F.when(
            F.col("_evento_anterior").isNull()
            | (
                F.unix_timestamp("event_timestamp")
                - F.unix_timestamp("_evento_anterior")
                > 1800
            ),
            1
        ).otherwise(0)
    )

    janela_acumulada = janela.rowsBetween(
        Window.unboundedPreceding,
        Window.currentRow
    )

    df = df.withColumn(
        "_numero_sessao",
        F.sum("_nova_sessao").over(janela_acumulada)
    )

    df = df.withColumn(
        "session_id",
        F.concat_ws(
            "-",
            F.col("_chave_visitante"),
            F.col("_numero_sessao").cast("string")
        )
    )

    return df.drop(
        "_chave_visitante",
        "_evento_anterior",
        "_nova_sessao",
        "_numero_sessao"
    )


def resolver_identidades(df):
    """R9 - Propaga o user_id aos eventos anônimos."""

    identificados = df.filter(
        F.col("user_pseudo_id").isNotNull()
        & F.col("user_id").isNotNull()
    )

    janela = (
        Window
        .partitionBy("user_pseudo_id")
        .orderBy("event_timestamp", "event_id")
    )

    identidades = (
        identificados
        .withColumn("_ordem_id", F.row_number().over(janela))
        .filter(F.col("_ordem_id") == 1)
        .select(
            "user_pseudo_id",
            F.col("user_id").alias("_user_id_resolvido")
        )
    )

    df = df.join(
        identidades,
        on="user_pseudo_id",
        how="left"
    )

    return (
        df.withColumn(
            "user_id",
            F.coalesce(
                F.col("_user_id_resolvido"),
                F.col("user_id")
            )
        )
        .drop("_user_id_resolvido")
    )


def criar_tabela_itens(df):
    """R10 - Uma linha por item de cada evento."""

    return (
        df.withColumn("_item", F.explode("items"))
        .select(
            "event_id",
            "event_name",
            "event_timestamp",
            "session_id",
            "user_pseudo_id",
            "user_id",
            "year",
            "month",
            "day",
            F.col("_item.item_id").alias("item_id"),
            F.col("_item.item_name").alias("item_name"),
            F.col("_item.item_category").alias("item_category"),
            F.col("_item.price").alias("price"),
            F.col("_item.quantity").alias("quantity"),
        )
    )


def main():
    spark = criar_sessao("silver")

    try:
        # R2 - Verificar a camada anterior
        exigir_camada(
            spark,
            glob_eventos("bronze"),
            "python pipeline/bronze.py"
        )

        # Ler os eventos Bronze
        bronze = ler_eventos(spark, "bronze")

        titulo("Silver - R5: Deduplicação")

        total = bronze.count()
        print(f"Eventos na Bronze: {total}")

        # Separa IDs nulos para não deduplicá-los juntos
        com_id = bronze.filter(F.col("event_id").isNotNull())
        sem_id = bronze.filter(F.col("event_id").isNull())

        janela = Window.partitionBy("event_id").orderBy(
            F.col("ingestao_ts").asc(),
            F.col("arquivo_origem").asc()
        )

        unicos = (
            com_id
            .withColumn("_ordem", F.row_number().over(janela))
            .filter(F.col("_ordem") == 1)
            .drop("_ordem")
        )

        unicos = unicos.unionByName(sem_id)

        quantidade_unicos = unicos.count()

        print(f"Eventos após deduplicação: {quantidade_unicos}")
        print(f"Duplicatas removidas: {total - quantidade_unicos}")

        # R6
        titulo("Silver - R6: Extração dos parâmetros")
        tipados = extrair_parametros(unicos)
        print("Parâmetros extraídos com sucesso!")

        # R7
        titulo("Silver - R7: Validação")
        validos, rejeitados = validar_eventos(tipados)

        print(f"Eventos válidos: {validos.count()}")
        print(f"Linhas de rejeição: {rejeitados.count()}")

        print("Rejeições por motivo:")
        rejeitados.groupBy("motivo_rejeicao").count().show(
            truncate=False
        )

        # R8
        titulo("Silver - R8: Sessionização")
        com_sessoes = calcular_sessoes(validos)

        # R9
        titulo("Silver - R9: Identity Stitching")
        silver = resolver_identidades(com_sessoes)

        print(
            "Sessões distintas:",
            silver.select("session_id").distinct().count()
        )

        # R10
        titulo("Silver - R10: Tabela de itens")
        itens = criar_tabela_itens(silver)

        print(f"Total de itens: {itens.count()}")

        # Gravar os eventos Silver
        titulo("Silver - Gravação")

        gravar_eventos(silver, "silver", "overwrite")

        # Gravar rejeitados separadamente
        (
            rejeitados.write
            .mode("overwrite")
            .parquet(caminho("silver/eventos_rejeitados"))
        )

        # Gravar itens por data
        (
            itens.write
            .mode("overwrite")
            .partitionBy("year", "month", "day")
            .parquet(caminho("silver/itens"))
        )

        print("Camada Silver gravada com sucesso!")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
