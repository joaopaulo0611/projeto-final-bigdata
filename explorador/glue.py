"""Lógica das telas "Data Catalog" e "Jobs ETL" (no estilo do Glue), sem Streamlit.

Catálogo: os datasets do bucket viram bancos (um por camada) e tabelas.
Jobs: cada script roda como `python <script>` num processo separado (o console usa a cópia
baixada do floci; o workflow pelo terminal, a pasta local); cada execução deixa na pasta de execuções um .json (início), um .log (saída) e,
ao terminar, um .fim (código de saída).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from explorador.particoes import CAMPOS, SEM_PARTICAO, Dataset, Objeto, banco_e_tabela, tabela_particoes

ORDEM_CAMADAS = ["landing", "bronze", "silver", "gold"]
IGNORADOS = {"comum.py", "__init__.py"}
EM_EXECUCAO, SUCESSO, FALHOU = "Em execução", "Sucesso", "Falhou"
HISTORICO = 30                                      # execuções guardadas por job; as mais antigas saem


# ------------------------------------------------------------- catálogo -------------------------------------------------------------

def bancos(datasets: list[Dataset]) -> dict[str, list[Dataset]]:
    """{banco: [tabelas]}, com as camadas na ordem do medalhão e o resto em ordem alfabética."""
    por_banco: dict[str, list[Dataset]] = {}
    for d in sorted(datasets, key=lambda d: d.nome_view):
        por_banco.setdefault(banco_e_tabela(d.nome_view)[0], []).append(d)
    ordem = lambda b: (ORDEM_CAMADAS.index(b) if b in ORDEM_CAMADAS else len(ORDEM_CAMADAS), b)
    return {b: por_banco[b] for b in sorted(por_banco, key=ordem)}


def localizacao(dataset: Dataset, bucket: str) -> str:
    """`bucket` é o do datalake; um dataset de outro bucket mostra o bucket dele."""
    caminho = f"{dataset.caminho}/" if dataset.caminho else ""
    return f"s3://{dataset.bucket or bucket}/{caminho}"


def local_do_banco(tabelas: list[Dataset], bucket: str) -> str:
    """Banco do datalake: s3://<bucket>/<camada>/; banco de outro bucket: s3://<esse bucket>/."""
    primeira = tabelas[0]
    if primeira.bucket:
        return f"s3://{primeira.bucket}/"
    return f"s3://{bucket}/{primeira.prefixo.split('/')[0]}/"


def chaves_particao(dataset: Dataset, objetos: list[Objeto]) -> list[str]:
    linhas = tabela_particoes(objetos, dataset.prefixo, dataset.formato)
    return [c for c in CAMPOS if any(getattr(l, c) != SEM_PARTICAO for l in linhas)]


# --------------------------------------------------------------- jobs ---------------------------------------------------------------

@dataclass(frozen=True)
class Job:
    nome: str
    script: Path


@dataclass
class Execucao:
    id: str
    job: str
    inicio: float
    status: str
    codigo: int | None
    duracao: float
    origem: str = "console"                         # "console" ou "workflow <nome>"


def listar_jobs(pasta: Path) -> list[Job]:
    """Os scripts .py da pasta, menos o comum.py e os que começam com "_"."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    return [Job(p.stem, p) for p in sorted(pasta.glob("*.py"))
            if p.name not in IGNORADOS and not p.name.startswith("_")]


# Roda o script, grava stdout+stderr no .log e, no fim, o código de saída no .fim. Com um 5º argumento,
# apaga essa pasta ao terminar (a cópia dos scripts baixada do floci só para esta execução).
_EXECUTOR = """
import json, os, shutil, subprocess, sys, time
script, log, fim, raiz = sys.argv[1:5]
try:
    with open(log, "w", encoding="utf-8") as saida:
        codigo = subprocess.run([sys.executable, "-u", script], stdout=saida, stderr=subprocess.STDOUT, cwd=raiz).returncode
    with open(fim + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"codigo": codigo, "fim": time.time()}, f)
    os.replace(fim + ".tmp", fim)
finally:
    if len(sys.argv) > 5:
        shutil.rmtree(sys.argv[5], ignore_errors=True)
"""


def novo_id(nome: str) -> str:
    """<nome>-AAAAMMDD-HHMMSS-mmm, com a hora de agora."""
    agora = time.time()
    return f"{nome}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(agora))}-{int(agora * 1000) % 1000:03d}"


def iniciar(job: Job, pasta: Path, raiz: Path, origem: str = "console", descartar: Path | None = None) -> str:
    """Começa uma execução em segundo plano e devolve o id dela.

    `descartar`: pasta apagada quando a execução termina (a cópia dos scripts feita só para ela)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    agora = time.time()
    id_execucao = novo_id(job.nome)
    base = pasta / id_execucao
    argumentos = [str(job.script), f"{base}.log", f"{base}.fim", str(raiz)] + ([str(descartar)] if descartar else [])
    processo = subprocess.Popen(
        [sys.executable, "-c", _EXECUTOR, *argumentos],
        cwd=str(raiz), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (pasta / f"{id_execucao}.json").write_text(
        json.dumps({"job": job.nome, "script": str(job.script), "inicio": agora, "pid": processo.pid, "origem": origem}),
        encoding="utf-8")
    podar(pasta, job.nome)
    return id_execucao


def podar(pasta: Path, job: str, manter: int = HISTORICO) -> None:
    """Apaga as execuções terminadas mais antigas do job, deixando as `manter` mais recentes."""
    for antiga in execucoes(pasta, job)[manter:]:
        if antiga.status != EM_EXECUCAO:
            for sufixo in (".json", ".log", ".fim"):
                (Path(pasta) / f"{antiga.id}{sufixo}").unlink(missing_ok=True)


def limpar_copias(pasta: Path, idade: float = 24 * 3600) -> None:
    """Apaga as cópias de scripts esquecidas (o processo morreu antes de apagar a sua) com mais de `idade` segundos."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return
    limite = time.time() - idade
    for copia in pasta.iterdir():
        if copia.is_dir() and copia.stat().st_mtime < limite:
            shutil.rmtree(copia, ignore_errors=True)


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                            # processo filho já terminado vira zumbi até ser recolhido
        return os.waitpid(pid, os.WNOHANG) == (0, 0)
    except ChildProcessError:
        return True


def execucao(pasta: Path, id_execucao: str) -> Execucao:
    pasta = Path(pasta)
    dados = json.loads((pasta / f"{id_execucao}.json").read_text(encoding="utf-8"))
    fim = pasta / f"{id_execucao}.fim"
    origem = dados.get("origem", "console")
    if fim.exists():
        final = json.loads(fim.read_text(encoding="utf-8"))
        status = SUCESSO if final["codigo"] == 0 else FALHOU
        return Execucao(id_execucao, dados["job"], dados["inicio"], status, final["codigo"], final["fim"] - dados["inicio"],
                        origem)
    if not _vivo(dados["pid"]):                     # o processo morreu sem gravar o .fim (contêiner reiniciado, kill…)
        return Execucao(id_execucao, dados["job"], dados["inicio"], FALHOU, None, time.time() - dados["inicio"], origem)
    return Execucao(id_execucao, dados["job"], dados["inicio"], EM_EXECUCAO, None, time.time() - dados["inicio"], origem)


def execucoes(pasta: Path, job: str | None = None) -> list[Execucao]:
    """Execuções da pasta (de um job, se pedido), a mais recente primeiro."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    todas = []
    for arquivo in pasta.glob("*.json"):
        try:
            todas.append(execucao(pasta, arquivo.stem))
        except (OSError, ValueError, KeyError, TypeError):
            continue                                # arquivo estragado (contêiner caiu no meio da gravação): pula
    return sorted((e for e in todas if job is None or e.job == job), key=lambda e: e.inicio, reverse=True)


def em_execucao(pasta: Path, job: str) -> bool:
    return any(e.status == EM_EXECUCAO for e in execucoes(pasta, job))


def log(pasta: Path, id_execucao: str, ultimas: int | None = None) -> str:
    arquivo = Path(pasta) / f"{id_execucao}.log"
    if not arquivo.exists():
        return ""
    texto = arquivo.read_text(encoding="utf-8", errors="replace").replace("\r", "\n")
    linhas = [l for l in texto.split("\n") if l.strip() and "Stage " not in l]   # tira a barra de progresso do Spark
    return "\n".join(linhas[-ultimas:] if ultimas else linhas)
