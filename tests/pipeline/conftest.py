import sys
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

# os jobs do aluno rodam como `python pipeline/<job>.py` e importam `comum` da própria pasta
PIPELINE = Path(__file__).resolve().parents[2] / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))


@pytest.fixture(scope="session")
def spark():
    sessao = (
        SparkSession.builder
        .master("local[2]")
        .appName("testes-comum")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.sources.partitionColumnTypeInference.enabled", "false")
        .getOrCreate()
    )
    sessao.sparkContext.setLogLevel("ERROR")
    yield sessao
    sessao.stop()
