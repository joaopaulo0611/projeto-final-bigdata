"""Funções puras sobre as chaves do bucket: datasets, partições e navegação.

Uma chave é o "caminho" de um arquivo no S3, por exemplo
landing/eventos/year=2026/month=09/day=01/coletor-s42-001.jsonl.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable

CAMPOS = ("event_name", "year", "month", "day")
SEM_PARTICAO = "—"
EXTENSOES = {".parquet": "parquet", ".jsonl": "jsonl"}


@dataclass(frozen=True)
class Objeto:
    chave: str
    tamanho: int
    modificado: datetime | None = None


# Os arquivos dos outros buckets entram no catálogo com a chave "@<bucket>/<chave>": assim eles nunca se
# misturam com as pastas do bucket do datalake, e o Dataset sabe de que bucket veio.
MARCA_BUCKET = "@"


def chave_virtual(bucket: str, chave: str) -> str:
    return f"{MARCA_BUCKET}{bucket}/{chave}"


def separar_bucket(prefixo: str) -> tuple[str | None, str]:
    """'@rascunho/notas' -> ('rascunho', 'notas'); 'silver/itens' -> (None, 'silver/itens')."""
    if not prefixo.startswith(MARCA_BUCKET):
        return None, prefixo
    bucket, _, caminho = prefixo[len(MARCA_BUCKET):].partition("/")
    return bucket, caminho


@dataclass(frozen=True)
class Dataset:
    prefixo: str
    formato: str
    nome_view: str
    particionado: bool = False   # arquivos em pastas k=v logo abaixo do prefixo

    @property
    def bucket(self) -> str | None:
        """None: o bucket do datalake; senão, o nome do outro bucket."""
        return separar_bucket(self.prefixo)[0]

    @property
    def caminho(self) -> str:
        """A pasta de verdade dentro do bucket (sem a marca @<bucket>/)."""
        return separar_bucket(self.prefixo)[1]


@dataclass(frozen=True)
class LinhaParticao:
    event_name: str
    year: str
    month: str
    day: str
    arquivos: int
    bytes: int


def _interno(segmento: str) -> bool:
    return segmento.startswith(("_", "."))


def formato_do_arquivo(chave: str) -> str | None:
    nome = chave.rsplit("/", 1)[-1]
    if _interno(nome):
        return None
    return next((f for ext, f in EXTENSOES.items() if nome.endswith(ext)), None)


def particao_da_chave(chave: str) -> dict[str, str] | None:
    valores = {}
    for segmento in chave.split("/")[:-1]:
        campo, igual, valor = segmento.partition("=")
        if igual and campo in CAMPOS:
            valores[campo] = valor
    return valores or None


def _prefixo_do_dataset(chave: str) -> str:
    base = []
    for segmento in chave.split("/")[:-1]:
        if "=" in segmento:
            break
        base.append(segmento)
    return "/".join(base)


def _limpo(texto: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", texto).strip("_").lower()


def _nome_view(prefixo: str) -> str:
    """Nome no catálogo, como no Glue: 'banco.tabela'. O banco é a camada (a 1ª pasta).

    'silver' -> 'silver.eventos' (partições event_name= na raiz da camada);
    'silver/itens' -> 'silver.itens'; 'gold/funil_compra' -> 'gold.funil_compra'.
    Outro bucket: o banco é o nome do bucket e a tabela é a pasta ('@rascunho/notas' -> 'rascunho.notas';
    arquivos soltos na raiz do bucket -> 'rascunho.raiz')."""
    bucket, caminho = separar_bucket(prefixo)
    if bucket is not None:
        return f"{_limpo(bucket)}.{_limpo(caminho) or 'raiz'}"
    banco, _, resto = prefixo.partition("/")
    return f"{_limpo(banco)}.{_limpo(resto) or 'eventos'}"


def banco_e_tabela(nome_view: str) -> tuple[str, str]:
    banco, _, tabela = nome_view.partition(".")
    return banco, tabela


def sql_nome(nome_view: str) -> str:
    """'silver.eventos' -> '"silver"."eventos"' (pronto para usar no SQL)."""
    return ".".join(f'"{parte}"' for parte in banco_e_tabela(nome_view))


def datasets(chaves: Iterable[str]) -> list[Dataset]:
    """Uma pasta com arquivos .parquet ou .jsonl vira um dataset (e uma view).

    Se a mesma pasta tiver os dois formatos, vira um dataset por formato, com o
    formato no fim do nome da view (ex.: landing_eventos_jsonl)."""
    formatos: dict[str, set[str]] = defaultdict(set)
    particionados: set[str] = set()
    for chave in chaves:
        formato = formato_do_arquivo(chave)
        if formato is None or any(_interno(s) for s in chave.split("/")[:-1]):
            continue
        prefixo = _prefixo_do_dataset(chave)
        if prefixo:
            formatos[prefixo].add(formato)
            if prefixo != chave.rsplit("/", 1)[0]:   # há pastas k=v entre o prefixo e o arquivo
                particionados.add(prefixo)
    resultado = []
    for prefixo, achados in sorted(formatos.items()):
        for formato in sorted(achados):
            nome = _nome_view(prefixo) + (f"_{formato}" if len(achados) > 1 else "")
            resultado.append(Dataset(prefixo, formato, nome, prefixo in particionados))
    # um bucket chamado "gold" não pode cair no mesmo banco da camada gold do datalake
    bancos_do_datalake = {banco_e_tabela(d.nome_view)[0] for d in resultado if d.bucket is None}
    for i, d in enumerate(resultado):
        banco, tabela = banco_e_tabela(d.nome_view)
        if d.bucket is not None and banco in bancos_do_datalake:
            resultado[i] = replace(d, nome_view=f"{banco}_bucket.{tabela}")
    return resultado


def _pertence_ao_dataset(resto: str) -> bool:
    """`resto` é a chave sem o prefixo do dataset. O arquivo conta se estiver direto na
    pasta do dataset ou dentro de pastas de partição (k=v), sem pastas internas (_x, .x)."""
    pastas = resto.split("/")[:-1]
    if any(_interno(p) for p in pastas):
        return False
    return not pastas or "=" in pastas[0]


def tabela_particoes(objetos: Iterable[Objeto], prefixo: str, formato: str | None = None) -> list[LinhaParticao]:
    """Uma linha por partição year/month/day; com `formato`, conta só arquivos daquele formato."""
    base = prefixo.rstrip("/") + "/"
    grupos: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
    for o in objetos:
        formato_do_objeto = formato_do_arquivo(o.chave)
        if not o.chave.startswith(base) or formato_do_objeto is None:
            continue
        if formato is not None and formato_do_objeto != formato:
            continue
        if not _pertence_ao_dataset(o.chave[len(base):]):
            continue
        particao = particao_da_chave(o.chave) or {}
        chave = tuple(particao.get(c, SEM_PARTICAO) for c in CAMPOS)
        grupos[chave][0] += 1
        grupos[chave][1] += o.tamanho
    return [LinhaParticao(*k, arquivos=a, bytes=b) for k, (a, b) in sorted(grupos.items())]


def navegar(objetos: Iterable[Objeto], pasta: str) -> tuple[list[str], list[Objeto]]:
    subpastas: set[str] = set()
    arquivos: list[Objeto] = []
    for o in objetos:
        if not o.chave.startswith(pasta):
            continue
        resto = o.chave[len(pasta):]
        if "/" in resto:
            subpastas.add(resto.split("/", 1)[0])
        elif resto:
            arquivos.append(o)
    return sorted(subpastas), sorted(arquivos, key=lambda o: o.chave)


def migalhas(pasta: str) -> list[tuple[str, str]]:
    """Breadcrumb do console: 'silver/event_name=x/' -> [('silver', 'silver/'), ('event_name=x', 'silver/event_name=x/')]."""
    partes = [p for p in pasta.split("/") if p]
    return [(p, "/".join(partes[:i + 1]) + "/") for i, p in enumerate(partes)]


def tamanho_legivel(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    valor = float(n)
    for unidade in ("KB", "MB", "GB", "TB"):
        valor /= 1024
        # Compara já arredondado: 1048575 B é "1,0 MB", não "1024,0 KB".
        if round(valor, 1) < 1024 or unidade == "TB":
            return f"{valor:.1f} {unidade}".replace(".", ",")
    return f"{n} B"
