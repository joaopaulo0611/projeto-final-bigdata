"""Workflows (no estilo do Glue Workflows): um grafo de jobs com dependências, montado no console.

Cada workflow é um arquivo JSON na pasta de jobs, versionado junto com os scripts:

    pipeline/workflows/medalhao.json
    {"nome": "medalhao", "descricao": "…", "paralelo": 2,
     "etapas": [{"job": "bronze", "depende_de": []}, {"job": "silver", "depende_de": ["bronze"]}, …]}

Para rodar, um orquestrador libera cada job quando todas as dependências dele terminaram com sucesso,
até `paralelo` jobs ao mesmo tempo. Se um job falha (ou alguém clica em Parar), nenhum job novo começa:
os que já rodam terminam e o resto fica "Não executado". Cada etapa é uma execução de job comum
(glue.iniciar), então aparece também na tela Jobs ETL, marcada com a origem.

Também roda pelo terminal:

    docker compose run --rm app python -m explorador.workflows pipeline/workflows/medalhao.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from explorador import glue

AGUARDANDO, NAO_EXECUTADO, PARADO = "Aguardando", "Não executado", "Parado"
EM_EXECUCAO, SUCESSO, FALHOU = glue.EM_EXECUCAO, glue.SUCESSO, glue.FALHOU
NOME_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
PARALELO_MAX = 4
PASTA = "workflows"


class WorkflowInvalido(ValueError):
    """O workflow não pode ser salvo nem executado; a mensagem explica o motivo."""


@dataclass(frozen=True)
class Etapa:
    job: str
    depende_de: tuple[str, ...] = ()


@dataclass(frozen=True)
class Workflow:
    nome: str
    descricao: str
    paralelo: int
    etapas: tuple[Etapa, ...]

    def para_dict(self) -> dict:
        return {"nome": self.nome, "descricao": self.descricao, "paralelo": self.paralelo,
                "etapas": [{"job": e.job, "depende_de": list(e.depende_de)} for e in self.etapas]}

    @classmethod
    def de_dict(cls, dados: dict) -> "Workflow":
        etapas = tuple(Etapa(str(e["job"]), tuple(str(d) for d in e.get("depende_de", []))) for e in dados["etapas"])
        return cls(str(dados["nome"]), str(dados.get("descricao", "")), int(dados.get("paralelo", 1)), etapas)


# ------------------------------------------------------------- definição -------------------------------------------------------------

def niveis(wf: Workflow) -> list[list[str]]:
    """Os jobs em camadas: cada camada só depende das anteriores (ordem topológica)."""
    faltam = {e.job: set(e.depende_de) for e in wf.etapas}
    ordem = [e.job for e in wf.etapas]
    camadas, feitos = [], set()
    while faltam:
        prontos = [j for j in ordem if j in faltam and faltam[j] <= feitos]
        if not prontos:
            raise WorkflowInvalido(f"As dependências formam um ciclo entre: {', '.join(sorted(faltam))}. "
                                   "Um job não pode esperar por outro que espera por ele.")
        camadas.append(prontos)
        feitos.update(prontos)
        for j in prontos:
            del faltam[j]
    return camadas


def validar(wf: Workflow, jobs_disponiveis: set[str]) -> None:
    if not NOME_VALIDO.match(wf.nome):
        raise WorkflowInvalido("Use um nome com letras minúsculas, números, _ ou - (sem espaços nem acentos), "
                               "por exemplo medalhao_diario.")
    if not wf.etapas:
        raise WorkflowInvalido("Escolha pelo menos um job para o workflow.")
    if not 1 <= wf.paralelo <= PARALELO_MAX:
        raise WorkflowInvalido(f"Rode de 1 a {PARALELO_MAX} jobs ao mesmo tempo.")
    vistos: set[str] = set()
    for e in wf.etapas:
        if e.job in vistos:
            raise WorkflowInvalido(f"O job {e.job} aparece duas vezes no workflow.")
        vistos.add(e.job)
        if e.job not in jobs_disponiveis:
            raise WorkflowInvalido(f"O job {e.job} não existe na pasta de jobs (o script {e.job}.py sumiu?).")
    for e in wf.etapas:
        for d in e.depende_de:
            if d == e.job:
                raise WorkflowInvalido(f"O job {e.job} não pode depender de si mesmo.")
            if d not in vistos:
                raise WorkflowInvalido(f"O job {e.job} depende de {d}, que não está no workflow.")
    niveis(wf)                                          # acusa ciclo


def pasta_definicoes(pasta_jobs: Path) -> Path:
    return Path(pasta_jobs) / PASTA


def salvar(pasta_jobs: Path, wf: Workflow) -> Path:
    pasta = pasta_definicoes(pasta_jobs)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{wf.nome}.json"
    arquivo.write_text(json.dumps(wf.para_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return arquivo


def excluir(pasta_jobs: Path, nome: str) -> None:
    if NOME_VALIDO.match(nome):                         # nunca apaga nada fora da pasta de workflows
        (pasta_definicoes(pasta_jobs) / f"{nome}.json").unlink(missing_ok=True)


def carregar(arquivo: Path) -> Workflow:
    return Workflow.de_dict(json.loads(Path(arquivo).read_text(encoding="utf-8")))


def listar(pasta_jobs: Path) -> tuple[list[Workflow], list[str]]:
    """(workflows, avisos): um arquivo estragado vira aviso em vez de derrubar a tela."""
    pasta = pasta_definicoes(pasta_jobs)
    if not pasta.is_dir():
        return [], []
    lidos, avisos = [], []
    for arquivo in sorted(pasta.glob("*.json")):
        try:
            lidos.append(carregar(arquivo))
        except (OSError, ValueError, KeyError, TypeError) as erro:
            avisos.append(f"{arquivo.name}: não consegui ler ({type(erro).__name__}: {erro}).")
    return lidos, avisos


CORES = {AGUARDANDO: ("#ffffff", "#8c8c94"), EM_EXECUCAO: ("#d1f1ff", "#006ce0"), SUCESSO: ("#e9fbe5", "#00802f"),
         FALHOU: ("#fff5f5", "#db0000"), NAO_EXECUTADO: ("#f6f6f9", "#b4b4bb"), PARADO: ("#f6f6f9", "#656871")}


def dot(wf: Workflow, status: dict[str, str] | None = None) -> str:
    """O grafo em DOT (Graphviz), da esquerda para a direita, com a cor do status de cada job."""
    status = status or {}
    linhas = ['digraph workflow {', '  rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.6;',
              '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12, penwidth=1.6, margin="0.2,0.1"];',
              '  edge [color="#8c8c94", arrowsize=0.7];']
    for e in wf.etapas:
        situacao = status.get(e.job)
        fundo, borda = CORES.get(situacao, CORES[AGUARDANDO])
        rotulo = e.job + (f"\\n{situacao}" if situacao else "")
        tracejado = ', style="rounded,filled,dashed"' if situacao == NAO_EXECUTADO else ""
        linhas.append(f'  "{e.job}" [label="{rotulo}", fillcolor="{fundo}", color="{borda}"{tracejado}];')
    for e in wf.etapas:
        for d in e.depende_de:
            linhas.append(f'  "{d}" -> "{e.job}";')
    linhas.append("}")
    return "\n".join(linhas)


# ------------------------------------------------------------- execução -------------------------------------------------------------

@dataclass
class EstadoEtapa:
    status: str = AGUARDANDO
    execucao: str | None = None                         # id da execução do job (tela Jobs ETL)
    inicio: float | None = None
    duracao: float | None = None
    erro: str = ""


@dataclass
class ExecucaoWorkflow:
    id: str
    workflow: Workflow
    inicio: float
    status: str
    duracao: float
    etapas: dict[str, EstadoEtapa] = field(default_factory=dict)


def _pasta_execucoes(pasta_exec: Path) -> Path:
    return Path(pasta_exec) / PASTA


def _gravar(arquivo: Path, dados: dict) -> None:
    temporario = arquivo.with_name(arquivo.name + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(temporario, arquivo)                     # quem lê nunca pega o arquivo pela metade


def preparar(wf: Workflow, pasta_exec: Path) -> str:
    """Registra uma execução nova (com uma cópia do workflow: editar depois não muda a que já começou)."""
    pasta = _pasta_execucoes(pasta_exec)
    pasta.mkdir(parents=True, exist_ok=True)
    id_execucao = glue.novo_id(wf.nome)
    _gravar(pasta / f"{id_execucao}.json", {"workflow": wf.para_dict(), "inicio": time.time(), "pid": None})
    podar(pasta_exec, wf.nome)
    return id_execucao


def podar(pasta_exec: Path, workflow: str, manter: int = glue.HISTORICO) -> None:
    """Apaga as execuções terminadas mais antigas do workflow, deixando as `manter` mais recentes."""
    pasta = _pasta_execucoes(pasta_exec)
    for antiga in execucoes(pasta_exec, workflow)[manter:]:
        if antiga.status != EM_EXECUCAO:
            for sufixo in (".json", ".estado.json", ".fim", ".parar"):
                (pasta / f"{antiga.id}{sufixo}").unlink(missing_ok=True)


def iniciar(wf: Workflow, pasta_jobs: Path, pasta_exec: Path, raiz: Path, descartar: bool = False) -> str:
    """Começa a execução em segundo plano (um processo orquestrador) e devolve o id dela.

    `descartar`: apaga `pasta_jobs` no fim (a cópia dos scripts baixada do floci só para esta execução)."""
    id_execucao = preparar(wf, pasta_exec)
    ambiente = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(Path(__file__).resolve().parents[1]),
                                                                           os.environ.get("PYTHONPATH")]))}
    processo = subprocess.Popen(
        [sys.executable, "-m", "explorador.workflows", "--execucao", id_execucao, str(pasta_jobs), str(pasta_exec),
         str(raiz)] + (["--descartar"] if descartar else []), cwd=str(raiz), env=ambiente, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    arquivo = _pasta_execucoes(pasta_exec) / f"{id_execucao}.json"
    _gravar(arquivo, {**json.loads(arquivo.read_text(encoding="utf-8")), "pid": processo.pid})
    return id_execucao


def parar(pasta_exec: Path, id_execucao: str) -> None:
    """Pede para parar: nenhum job novo começa; os que já rodam terminam."""
    (_pasta_execucoes(pasta_exec) / f"{id_execucao}.parar").touch()


def orquestrar(pasta_exec: Path, id_execucao: str, pasta_jobs: Path, raiz: Path, intervalo: float = 1.0,
               avisar=lambda texto: None) -> int:
    """Roda o grafo até o fim; grava o estado de cada etapa em <id>.estado.json e o resultado em <id>.fim."""
    pasta = _pasta_execucoes(pasta_exec)
    wf = Workflow.de_dict(json.loads((pasta / f"{id_execucao}.json").read_text(encoding="utf-8"))["workflow"])
    jobs = {j.nome: j for j in glue.listar_jobs(pasta_jobs)}
    estado = {e.job: EstadoEtapa() for e in wf.etapas}
    dependencias = {e.job: e.depende_de for e in wf.etapas}
    ordem = [j for camada in niveis(wf) for j in camada]
    interromper, parado = False, False

    def gravar_estado():
        _gravar(pasta / f"{id_execucao}.estado.json", {j: vars(s) for j, s in estado.items()})

    while True:
        for nome, s in estado.items():                  # quem terminou?
            if s.status == EM_EXECUCAO:
                job = glue.execucao(pasta_exec, s.execucao)
                if job.status != glue.EM_EXECUCAO:
                    s.status, s.duracao = job.status, job.duracao
                    avisar(f"<<< {nome}: {job.status} em {job.duracao:.0f} s")
                    interromper = interromper or job.status == FALHOU
        if not parado and (pasta / f"{id_execucao}.parar").exists():
            interromper = parado = True
            avisar("--- pedido para parar: nenhum job novo vai começar")
        rodando = sum(s.status == EM_EXECUCAO for s in estado.values())
        if not interromper:
            for nome in ordem:                          # libera quem já pode rodar, até o limite
                s = estado[nome]
                if rodando >= wf.paralelo:
                    break
                if s.status != AGUARDANDO or any(estado[d].status != SUCESSO for d in dependencias[nome]):
                    continue
                if nome not in jobs:
                    s.status, s.erro, interromper = FALHOU, f"O script {nome}.py não existe mais na pasta de jobs.", True
                    avisar(f"!!! {nome}: {s.erro}")
                    break
                if glue.em_execucao(pasta_exec, nome):  # alguém já rodou este job pelo console: espera terminar
                    continue
                s.execucao = glue.iniciar(jobs[nome], pasta_exec, raiz, origem=f"workflow {wf.nome}")
                s.status, s.inicio = EM_EXECUCAO, time.time()
                rodando += 1
                avisar(f">>> {nome}")
        aguardando = any(s.status == AGUARDANDO for s in estado.values())
        if rodando == 0 and (interromper or not aguardando):
            break
        gravar_estado()
        time.sleep(intervalo)

    for s in estado.values():
        if s.status == AGUARDANDO:
            s.status = NAO_EXECUTADO
    gravar_estado()
    sucesso = all(s.status == SUCESSO for s in estado.values())
    resultado = SUCESSO if sucesso else (PARADO if parado else FALHOU)
    _gravar(pasta / f"{id_execucao}.fim", {"status": resultado, "fim": time.time()})
    return 0 if sucesso else 1


def _vivo(pid: int | None) -> bool:
    return pid is None or glue._vivo(pid)               # sem pid: rodando no próprio processo (terminal, testes)


def execucao(pasta_exec: Path, id_execucao: str) -> ExecucaoWorkflow:
    pasta = _pasta_execucoes(pasta_exec)
    dados = json.loads((pasta / f"{id_execucao}.json").read_text(encoding="utf-8"))
    wf = Workflow.de_dict(dados["workflow"])
    arquivo_estado = pasta / f"{id_execucao}.estado.json"
    etapas = {e.job: EstadoEtapa() for e in wf.etapas}
    if arquivo_estado.exists():
        etapas.update({j: EstadoEtapa(**s) for j, s in json.loads(arquivo_estado.read_text(encoding="utf-8")).items()})
    agora = time.time()
    fim = pasta / f"{id_execucao}.fim"
    if fim.exists():
        final = json.loads(fim.read_text(encoding="utf-8"))
        return ExecucaoWorkflow(id_execucao, wf, dados["inicio"], final["status"], final["fim"] - dados["inicio"], etapas)
    vivo = _vivo(dados.get("pid"))
    for s in etapas.values():
        if vivo:
            if s.status == EM_EXECUCAO and s.inicio:    # duração das etapas que ainda rodam
                s.duracao = agora - s.inicio
            continue
        # orquestrador morreu (contêiner reiniciado, kill…): o status de cada job vem da execução dele,
        # que pode ter terminado (ou seguir rodando) sozinha; quem nem começou não vai mais rodar
        if s.status == EM_EXECUCAO and s.execucao:
            try:
                job = glue.execucao(pasta_exec, s.execucao)
                s.status, s.duracao = job.status, job.duracao
            except (OSError, ValueError, KeyError, TypeError):
                s.status = FALHOU
        elif s.status == AGUARDANDO:
            s.status = NAO_EXECUTADO
    status = EM_EXECUCAO if vivo else FALHOU
    return ExecucaoWorkflow(id_execucao, wf, dados["inicio"], status, agora - dados["inicio"], etapas)


def execucoes(pasta_exec: Path, workflow: str | None = None) -> list[ExecucaoWorkflow]:
    """Execuções (de um workflow, se pedido), a mais recente primeiro."""
    pasta = _pasta_execucoes(pasta_exec)
    if not pasta.is_dir():
        return []
    todas = []
    for arquivo in pasta.glob("*.json"):
        if arquivo.name.endswith(".estado.json"):
            continue
        try:
            todas.append(execucao(pasta_exec, arquivo.name[:-len(".json")]))
        except (OSError, ValueError, KeyError, TypeError):
            continue                                # arquivo estragado (contêiner caiu no meio da gravação): pula
    return sorted((e for e in todas if workflow is None or e.workflow.nome == workflow), key=lambda e: e.inicio,
                  reverse=True)


def em_execucao(pasta_exec: Path, workflow: str) -> bool:
    return any(e.status == EM_EXECUCAO for e in execucoes(pasta_exec, workflow))


# --------------------------------------------------------------- terminal ---------------------------------------------------------------

def main(argumentos: list[str]) -> int:
    if argumentos[:1] == ["--execucao"]:                # chamado pelo console (iniciar)
        id_execucao, pasta_jobs, pasta_exec, raiz = argumentos[1:5]
        try:
            return orquestrar(Path(pasta_exec), id_execucao, Path(pasta_jobs), Path(raiz))
        finally:
            if "--descartar" in argumentos[5:]:          # a cópia dos scripts era só desta execução
                shutil.rmtree(pasta_jobs, ignore_errors=True)
    if len(argumentos) != 1:
        print("uso: python -m explorador.workflows <pasta de jobs>/workflows/<nome>.json")
        return 2
    arquivo = Path(argumentos[0]).resolve()
    raiz = Path.cwd()
    pasta_jobs = arquivo.parent.parent                  # <pasta de jobs>/workflows/<nome>.json
    pasta_exec = Path(os.environ.get("EXPLORADOR_EXECUCOES", "/tmp/explorador-execucoes"))
    wf = carregar(arquivo)
    validar(wf, {j.nome for j in glue.listar_jobs(pasta_jobs)})
    print(f"workflow {wf.nome}: {' → '.join(' + '.join(c) for c in niveis(wf))} (até {wf.paralelo} ao mesmo tempo)",
          flush=True)
    id_execucao = preparar(wf, pasta_exec)
    codigo = orquestrar(pasta_exec, id_execucao, pasta_jobs, raiz, avisar=lambda t: print(t, flush=True))
    ex = execucao(pasta_exec, id_execucao)
    for nome, s in ex.etapas.items():
        if s.status == FALHOU and s.execucao:
            print(f"\n--- últimas linhas de {nome}:\n{glue.log(pasta_exec, s.execucao, ultimas=20)}", flush=True)
    print(f"\nworkflow {wf.nome}: {ex.status} em {ex.duracao:.0f} s", flush=True)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
