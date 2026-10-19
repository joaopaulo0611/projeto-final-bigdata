"""Lista os buckets do floci com boto3. Este módulo só lê; quem grava (no bucket de recursos) é o recursos.py.

O bucket do datalake (AWS_S3_BUCKET) é o que alimenta o Data Catalog e o Athena; a tela S3
mostra todos os buckets que existirem no floci.
"""

from __future__ import annotations

import os

from explorador.particoes import Objeto

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL") or "http://floci:4566"
BUCKET = os.environ.get("AWS_S3_BUCKET") or "datalake-tracking"
CHAVE = os.environ.get("AWS_ACCESS_KEY_ID") or "test"
SEGREDO = os.environ.get("AWS_SECRET_ACCESS_KEY") or "test"
REGIAO = os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
# Classes-base do botocore (e do Python) para falhas de rede; as filhas, como SSLError,
# ProxyConnectionError e EndpointConnectionError, são reconhecidas pela herança.
ERROS_DE_CONEXAO = {"ConnectionError", "HTTPClientError", "EndpointConnectionError", "ConnectTimeoutError",
                    "ConnectionClosedError", "ReadTimeoutError", "TimeoutError"}


class S3Indisponivel(RuntimeError):
    """O floci não respondeu; a mensagem vai direto para o usuário."""


def raiz(bucket: str | None = None) -> str:
    return f"s3://{bucket or BUCKET}"


def _cliente():
    import boto3
    from botocore.config import Config

    return boto3.client("s3", endpoint_url=ENDPOINT, aws_access_key_id=CHAVE,
                        aws_secret_access_key=SEGREDO, region_name=REGIAO,
                        config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 1}))


def _sem_conexao(erro: Exception) -> bool:
    return any(c.__name__ in ERROS_DE_CONEXAO for c in type(erro).__mro__)


def _indisponivel() -> S3Indisponivel:
    return S3Indisponivel(f"Não consegui falar com o S3 em {ENDPOINT}. Rode `docker compose up -d floci`.")


def listar_buckets(cliente=None) -> list[str]:
    """Nomes de todos os buckets do floci, com o do datalake primeiro."""
    s3 = cliente if cliente is not None else _cliente()
    try:
        nomes = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    except Exception as erro:
        if _sem_conexao(erro):
            raise _indisponivel() from None
        raise
    return sorted(nomes, key=lambda nome: (nome != BUCKET, nome))


def listar(prefixo: str = "", cliente=None, bucket: str | None = None) -> list[Objeto]:
    s3 = cliente if cliente is not None else _cliente()
    try:
        objetos = []
        for pagina in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket or BUCKET, Prefix=prefixo):
            for item in pagina.get("Contents", []):
                objetos.append(Objeto(item["Key"], item["Size"], item.get("LastModified")))
        return objetos
    except Exception as erro:
        codigo = getattr(erro, "response", {}).get("Error", {}).get("Code")
        if codigo in ("NoSuchBucket", "404"):
            return []
        if _sem_conexao(erro):
            raise _indisponivel() from None
        raise
