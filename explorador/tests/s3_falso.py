"""Um S3 em memória com o pouco que o explorador usa do boto3 (buckets, put/get/delete, listagem paginada)."""

import hashlib
import io
from datetime import datetime, timezone


class ErroS3(Exception):
    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


class _Paginador:
    def __init__(self, s3):
        self.s3 = s3

    def paginate(self, Bucket, Prefix=""):
        if Bucket not in self.s3.buckets:
            raise ErroS3("NoSuchBucket")
        conteudo = [{"Key": k, "Size": len(v), "ETag": f'"{hashlib.md5(v).hexdigest()}"',
                     "LastModified": self.s3.datas[(Bucket, k)]}
                    for k, v in sorted(self.s3.buckets[Bucket].items()) if k.startswith(Prefix)]
        yield {"Contents": conteudo} if conteudo else {}


class S3Falso:
    def __init__(self):
        self.buckets: dict[str, dict[str, bytes]] = {}
        self.datas = {}

    def list_buckets(self):
        return {"Buckets": [{"Name": n} for n in sorted(self.buckets)]}

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise ErroS3("404")

    def create_bucket(self, Bucket, **_):
        self.buckets.setdefault(Bucket, {})

    def put_object(self, Bucket, Key, Body, **_):
        self.buckets[Bucket][Key] = Body if isinstance(Body, bytes) else Body.encode("utf-8")
        self.datas[(Bucket, Key)] = datetime.now(timezone.utc)

    def get_object(self, Bucket, Key):
        if Key not in self.buckets.get(Bucket, {}):
            raise ErroS3("NoSuchKey")
        return {"Body": io.BytesIO(self.buckets[Bucket][Key])}

    def delete_object(self, Bucket, Key):
        self.buckets.get(Bucket, {}).pop(Key, None)

    def get_paginator(self, nome):
        assert nome == "list_objects_v2"
        return _Paginador(self)
