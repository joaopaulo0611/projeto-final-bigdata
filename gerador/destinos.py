"""Para onde o gerador grava: o S3 (floci, por padrão) ou uma pasta local.

Variáveis de ambiente, iguais às do pipeline:
  AWS_ENDPOINT_URL não definida -> floci em http://127.0.0.1:4566
  AWS_ENDPOINT_URL="" (vazia)   -> resolução padrão do boto3 (AWS real)
  AWS_S3_BUCKET                 -> bucket do datalake (padrão: datalake-tracking)
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

FLOCI_ENDPOINT = "http://127.0.0.1:4566"
_endpoint_env = os.environ.get("AWS_ENDPOINT_URL")
ENDPOINT = FLOCI_ENDPOINT if _endpoint_env is None else (_endpoint_env or None)
BUCKET = os.environ.get("AWS_S3_BUCKET", "datalake-tracking")


class DestinoLocal:
    def __init__(self, pasta: Path | str):
        self.pasta = Path(pasta)

    def gravar(self, chave: str, conteudo: str) -> None:
        caminho = self.pasta / chave
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo.encode("utf-8"))

    def descricao(self) -> str:
        return str(self.pasta.resolve())


def _cliente_boto3():
    try:
        import boto3
    except ImportError:
        raise SystemExit("boto3 não está instalado: pip install -r requirements.txt") from None
    return boto3.client("s3", endpoint_url=ENDPOINT)


CODIGOS_BUCKET_AUSENTE = {"404", "NoSuchBucket", "NotFound"}


class DestinoS3:
    def __init__(self, cliente=None):
        self.s3 = cliente if cliente is not None else _cliente_boto3()
        self._garantir_bucket()

    def _garantir_bucket(self) -> None:
        try:
            self.s3.head_bucket(Bucket=BUCKET)
            return
        except Exception as erro:
            if type(erro).__name__ == "EndpointConnectionError":
                raise SystemExit(
                    f"Não consegui falar com o S3 em {ENDPOINT}. "
                    "O floci está rodando? docker compose up -d floci"
                ) from None
            codigo = getattr(erro, "response", {}).get("Error", {}).get("Code")
            if codigo not in CODIGOS_BUCKET_AUSENTE:  # 403, timeout etc.: a causa real, sem mascarar
                raise
        argumentos = {"Bucket": BUCKET}
        regiao = os.environ["AWS_DEFAULT_REGION"]
        if regiao != "us-east-1":
            argumentos["CreateBucketConfiguration"] = {"LocationConstraint": regiao}
        self.s3.create_bucket(**argumentos)

    def gravar(self, chave: str, conteudo: str) -> None:
        self.s3.put_object(Bucket=BUCKET, Key=chave, Body=conteudo.encode("utf-8"),
                           ContentType="application/x-ndjson")

    def descricao(self) -> str:
        return f"s3://{BUCKET} ({ENDPOINT or 'AWS'})"
