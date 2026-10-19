"""Scripts e workflows dos jobs dentro do floci, como o bucket de "assets" do Glue.

Os recursos ficam num bucket próprio, separado do datalake (aparece na tela S3, mas não no
Data Catalog nem no Athena):

    s3://glue-assets/scripts/<job>.py        e scripts/comum.py, a biblioteca que os jobs importam
    s3://glue-assets/workflows/<nome>.json

O botão Sincronizar copia pipeline/*.py e pipeline/workflows/*.json para lá, como um espelho:
o que é novo ou mudou é enviado e o que sumiu da pasta local sai do bucket. Para rodar, o console
baixa os scripts do bucket numa pasta temporária e executa de lá, como o Glue faz.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from explorador import glue, s3, workflows

BUCKET = os.environ.get("EXPLORADOR_RECURSOS") or "glue-assets"
SCRIPTS, WORKFLOWS = "scripts/", "workflows/"
COMUM = "comum.py"


@dataclass
class Resumo:
    """O que o sincronizar fez (ou faria, em pendencias)."""
    enviados: list[str] = field(default_factory=list)   # novos ou alterados
    iguais: list[str] = field(default_factory=list)
    removidos: list[str] = field(default_factory=list)  # estavam no bucket e sumiram da pasta local

    @property
    def vazio(self) -> bool:
        return not self.enviados and not self.removidos


def _cliente():
    return s3._cliente()


def _sem_conexao(erro: Exception) -> bool:
    return s3._sem_conexao(erro)


@contextmanager
def _floci():
    """Falha de rede vira S3Indisponivel, com a mensagem que a tela mostra."""
    try:
        yield
    except s3.S3Indisponivel:
        raise
    except Exception as erro:
        if _sem_conexao(erro):
            raise s3._indisponivel() from None
        raise


def _listar(prefixo: str) -> dict[str, dict]:
    """{chave: item da listagem} do bucket de recursos; bucket ainda inexistente = vazio."""
    try:
        paginas = _cliente().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefixo)
        return {item["Key"]: item for pagina in paginas for item in pagina.get("Contents", [])}
    except Exception as erro:
        if getattr(erro, "response", {}).get("Error", {}).get("Code") in ("NoSuchBucket", "404"):
            return {}
        if _sem_conexao(erro):
            raise s3._indisponivel() from None
        raise


def _locais(pasta_jobs: Path, comum: Path) -> dict[str, bytes]:
    """O que deve existir no bucket: os .py da pasta de jobs, o comum.py de verdade e os workflows."""
    pasta_jobs = Path(pasta_jobs)
    arquivos = {f"{SCRIPTS}{p.name}": p.read_bytes() for p in sorted(pasta_jobs.glob("*.py")) if p.name != COMUM}
    if Path(comum).is_file():          # a pasta de jobs pode ter um comum.py que só carrega o outro: vai o de verdade
        arquivos[f"{SCRIPTS}{COMUM}"] = Path(comum).read_bytes()
    pasta_wf = workflows.pasta_definicoes(pasta_jobs)
    arquivos.update({f"{WORKFLOWS}{p.name}": p.read_bytes() for p in sorted(pasta_wf.glob("*.json"))}
                    if pasta_wf.is_dir() else {})
    return arquivos


def _md5(item: dict) -> str:
    return item.get("ETag", "").strip('"')


def pendencias(pasta_jobs: Path, comum: Path) -> Resumo:
    """O que o Sincronizar faria agora, sem mexer em nada."""
    locais = _locais(pasta_jobs, comum)
    remotos = {**_listar(SCRIPTS), **_listar(WORKFLOWS)}
    resumo = Resumo()
    for chave, conteudo in locais.items():
        remoto = remotos.get(chave)
        igual = remoto is not None and _md5(remoto) == hashlib.md5(conteudo).hexdigest()
        (resumo.iguais if igual else resumo.enviados).append(chave)
    resumo.removidos = sorted(set(remotos) - set(locais))
    return resumo


def _garantir_bucket(cliente) -> None:
    """Cria o bucket de recursos na primeira vez (como o Glue cria o bucket de assets)."""
    try:
        cliente.head_bucket(Bucket=BUCKET)
    except Exception as erro:
        if _sem_conexao(erro):
            raise s3._indisponivel() from None
        cliente.create_bucket(Bucket=BUCKET)


def sincronizar(pasta_jobs: Path, comum: Path) -> Resumo:
    """Espelha a pasta local no bucket de recursos (cria o bucket na primeira vez)."""
    cliente = _cliente()
    _garantir_bucket(cliente)
    resumo = pendencias(pasta_jobs, comum)
    locais = _locais(pasta_jobs, comum)
    with _floci():
        for chave in resumo.enviados:
            cliente.put_object(Bucket=BUCKET, Key=chave, Body=locais[chave])
        for chave in resumo.removidos:
            cliente.delete_object(Bucket=BUCKET, Key=chave)
    return resumo


def ler(chave: str) -> str:
    with _floci():
        return _cliente().get_object(Bucket=BUCKET, Key=chave)["Body"].read().decode("utf-8")


def caminho(chave: str) -> str:
    return f"s3://{BUCKET}/{chave}"


def listar_jobs() -> list[str]:
    """Os jobs que estão no floci: os scripts, menos o comum.py e os que começam com "_"."""
    nomes = (Path(chave).name for chave in _listar(SCRIPTS) if chave.endswith(".py"))
    return sorted(n[:-3] for n in nomes if n not in glue.IGNORADOS and not n.startswith("_"))


def baixar_scripts(destino: Path) -> Path:
    """Copia todos os scripts do bucket para `destino` (os jobs se importam entre si, como do comum)."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for chave in _listar(SCRIPTS):
        if chave.endswith(".py") and "/" not in chave[len(SCRIPTS):]:
            (destino / Path(chave).name).write_text(ler(chave), encoding="utf-8")
    return destino


def listar_workflows() -> tuple[list[workflows.Workflow], list[str]]:
    """(workflows, avisos): um arquivo estragado no bucket vira aviso em vez de derrubar a tela."""
    lidos, avisos = [], []
    for chave in sorted(_listar(WORKFLOWS)):
        if not chave.endswith(".json"):
            continue
        try:
            lidos.append(workflows.Workflow.de_dict(json.loads(ler(chave))))
        except (ValueError, KeyError, TypeError) as erro:
            avisos.append(f"{caminho(chave)}: não consegui ler ({type(erro).__name__}: {erro}).")
    return lidos, avisos


def salvar_workflow(wf: workflows.Workflow) -> str:
    chave = f"{WORKFLOWS}{wf.nome}.json"
    texto = json.dumps(wf.para_dict(), ensure_ascii=False, indent=2) + "\n"
    cliente = _cliente()
    _garantir_bucket(cliente)
    with _floci():
        cliente.put_object(Bucket=BUCKET, Key=chave, Body=texto.encode("utf-8"))
    return caminho(chave)


def excluir_workflow(nome: str) -> None:
    if workflows.NOME_VALIDO.match(nome):                # nunca apaga nada fora de workflows/
        with _floci():
            _cliente().delete_object(Bucket=BUCKET, Key=f"{WORKFLOWS}{nome}.json")
