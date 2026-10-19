"""Confere que o Spark lê e grava no floci por s3a:// (rode dentro do contêiner app).

    docker compose run --rm app python infra/verificar_ambiente.py

Usa a mesma sessão que os seus jobs: criar_sessao() de pipeline/comum.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from comum import apagar_camada, caminho, criar_sessao, ler_eventos  # noqa: E402


def main() -> int:
    spark = criar_sessao("verificar-ambiente")
    teste = "_verificacao"
    try:
        eventos = ler_eventos(spark, "landing", "json")
        print(f"[ok] landing lida por s3a: {eventos.count()} linhas em {caminho('landing/')}")
        eventos.groupBy("event_name").count().orderBy(F.desc("count")).show(25, truncate=False)

        spark.range(5).write.mode("overwrite").parquet(caminho(teste))
        lidos = spark.read.parquet(caminho(teste)).count()
        print(f"[ok] escrita e leitura de Parquet por s3a: {lidos} linhas em {caminho(teste + '/')}")

        apagar_camada(spark, teste)
        print("[ok] pasta de verificação removida")
    except Exception as erro:  # diagnóstico para o aluno
        print(f"[erro] {type(erro).__name__}: {str(erro).splitlines()[0]}", file=sys.stderr)
        print("Confira: docker compose up -d floci, e rode o gerador antes.", file=sys.stderr)
        return 1
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
