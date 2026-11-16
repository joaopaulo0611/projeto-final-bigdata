import json
from datetime import datetime, timezone

from comum import (
    criar_sessao,
    exigir_camada,
    arquivo_do_projeto,
    caminho,
    titulo,
)


# R11 - nomes de coluna exatos que o site lê
COLUNAS_CLIQUES = [
    "pagina",
    "element_id",
    "cliques",
    "sessoes",
    "sessoes_na_pagina",
    "taxa_clique",
    "intensidade",
]

COLUNAS_ROLAGEM = [
    "pagina",
    "marco",
    "sessoes_que_chegaram",
    "pct_sessoes",
]


def main():
    spark = criar_sessao("exportar_mapa_calor")

    try:
        # Verificar se as duas tabelas Gold existem
        for tabela in ["mapa_calor_cliques", "mapa_calor_rolagem"]:
            exigir_camada(
                spark,
                f"gold/{tabela}",
                "python pipeline/gold_mapa_calor.py"
            )

        titulo("Exportação do mapa de calor")

        # Tabelas pequenas: dá para trazer com collect()
        cliques = [
            linha.asDict()
            for linha in spark.read.parquet(
                caminho("gold/mapa_calor_cliques")
            ).select(*COLUNAS_CLIQUES)
             .orderBy("pagina", "element_id")
             .collect()
        ]

        rolagem = [
            linha.asDict()
            for linha in spark.read.parquet(
                caminho("gold/mapa_calor_rolagem")
            ).select(*COLUNAS_ROLAGEM)
             .orderBy("marco")
             .collect()
        ]

        agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dados = {
            "gerado_em": agora,
            "cliques": cliques,
            "rolagem": rolagem,
        }

        destino = arquivo_do_projeto("site/mapa_calor.js")
        texto = json.dumps(dados, ensure_ascii=False, default=float)
        destino.write_text(
            "window.MAPA_CALOR = " + texto + ";\n",
            encoding="utf-8"
        )

        print(f"{len(cliques)} linhas de cliques e "
              f"{len(rolagem)} de rolagem gravadas em {destino}")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
