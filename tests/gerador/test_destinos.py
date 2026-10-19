import pytest

from gerador.destinos import BUCKET, DestinoLocal, DestinoS3


def test_destino_local_espelha_a_chave_em_pastas(tmp_path):
    destino = DestinoLocal(tmp_path)
    destino.gravar("landing/eventos/year=2026/month=09/day=01/coletor-s42-001.jsonl", '{"a":"é"}\n')
    arquivo = tmp_path / "landing" / "eventos" / "year=2026" / "month=09" / "day=01" / "coletor-s42-001.jsonl"
    assert arquivo.read_bytes() == '{"a":"é"}\n'.encode("utf-8")
    assert str(tmp_path.resolve()) in destino.descricao()


class ErroS3(Exception):
    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


class EndpointConnectionError(Exception):
    pass


class S3Falso:
    def __init__(self):
        self.objetos = {}
        self.buckets = set()

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise ErroS3("404")

    def create_bucket(self, Bucket, **_):
        self.buckets.add(Bucket)

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objetos[(Bucket, Key)] = (Body, ContentType)


def test_destino_s3_cria_o_bucket_e_grava_utf8():
    s3 = S3Falso()
    destino = DestinoS3(cliente=s3)
    destino.gravar("landing/x.jsonl", "é\n")
    assert BUCKET in s3.buckets
    assert s3.objetos[(BUCKET, "landing/x.jsonl")] == ("é\n".encode("utf-8"), "application/x-ndjson")
    assert destino.descricao().startswith(f"s3://{BUCKET}")


def test_destino_s3_nao_recria_bucket_existente():
    s3 = S3Falso()
    s3.buckets.add(BUCKET)
    s3.create_bucket = lambda **_: pytest.fail("create_bucket nao deveria ser chamado")
    DestinoS3(cliente=s3)


def test_destino_s3_repropaga_erro_que_nao_e_404():
    s3 = S3Falso()

    def head_proibido(Bucket):
        raise ErroS3("403")

    s3.head_bucket = head_proibido
    with pytest.raises(ErroS3):
        DestinoS3(cliente=s3)
    assert not s3.buckets


def test_destino_s3_sem_conexao_manda_subir_o_floci():
    s3 = S3Falso()

    def head_sem_conexao(Bucket):
        raise EndpointConnectionError("sem rede")

    s3.head_bucket = head_sem_conexao
    with pytest.raises(SystemExit) as saida:
        DestinoS3(cliente=s3)
    assert "docker compose up" in str(saida.value)
