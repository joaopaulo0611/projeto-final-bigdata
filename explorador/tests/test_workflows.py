import json
import subprocess
import sys
import time

import pytest

from explorador import glue, workflows
from explorador.workflows import Etapa, Workflow, WorkflowInvalido

JOBS = {"bronze", "silver", "gold_a", "gold_b", "exportar"}


def _wf(*etapas, paralelo=2, nome="medalhao"):
    return Workflow(nome, "teste", paralelo, tuple(Etapa(j, tuple(d)) for j, d in etapas))


MEDALHAO = _wf(("bronze", []), ("silver", ["bronze"]), ("gold_a", ["silver"]), ("gold_b", ["silver"]),
               ("exportar", ["gold_a"]))


# ------------------------------------------------------------- definição -------------------------------------------------------------

def test_niveis_do_grafo_em_ordem_de_dependencia():
    assert workflows.niveis(MEDALHAO) == [["bronze"], ["silver"], ["gold_a", "gold_b"], ["exportar"]]


def test_workflow_valido_passa():
    workflows.validar(MEDALHAO, JOBS)


@pytest.mark.parametrize("wf, trecho", [
    (_wf(("bronze", []), nome="Meu Workflow"), "nome"),
    (_wf(), "pelo menos um job"),
    (_wf(("bronze", []), ("bronze", [])), "aparece duas vezes"),
    (_wf(("nao_existe", [])), "nao_existe"),
    (_wf(("bronze", ["silver"])), "não está no workflow"),
    (_wf(("bronze", ["bronze"])), "depender de si mesmo"),
    (_wf(("bronze", ["silver"]), ("silver", ["bronze"])), "ciclo"),
    (_wf(("bronze", []), paralelo=9), "ao mesmo tempo"),
])
def test_validar_explica_o_problema_em_portugues(wf, trecho):
    with pytest.raises(WorkflowInvalido, match=trecho):
        workflows.validar(wf, JOBS)


def test_salvar_listar_e_excluir(tmp_path):
    workflows.salvar(tmp_path, MEDALHAO)
    arquivo = tmp_path / "workflows" / "medalhao.json"
    assert json.loads(arquivo.read_text(encoding="utf-8"))["etapas"][1] == {"job": "silver", "depende_de": ["bronze"]}
    lidos, erros = workflows.listar(tmp_path)
    assert lidos == [MEDALHAO] and erros == []
    workflows.excluir(tmp_path, "medalhao")
    assert workflows.listar(tmp_path) == ([], [])


def test_arquivo_estragado_vira_aviso_sem_derrubar_a_lista(tmp_path):
    workflows.salvar(tmp_path, MEDALHAO)
    (tmp_path / "workflows" / "quebrado.json").write_text("{nao é json", encoding="utf-8")
    lidos, erros = workflows.listar(tmp_path)
    assert [w.nome for w in lidos] == ["medalhao"]
    assert len(erros) == 1 and "quebrado.json" in erros[0]


def test_dot_do_grafo_tem_os_nos_e_as_setas():
    dot = workflows.dot(MEDALHAO, {"bronze": workflows.SUCESSO, "silver": workflows.FALHOU})
    assert '"bronze" -> "silver"' in dot and '"gold_a" -> "exportar"' in dot
    assert "Sucesso" in dot and "Falhou" in dot


# ------------------------------------------------------------- execução -------------------------------------------------------------

@pytest.fixture
def pastas(tmp_path):
    jobs, execucoes = tmp_path / "jobs", tmp_path / "execucoes"
    jobs.mkdir()
    return jobs, execucoes, tmp_path


def _job(pasta, nome, codigo=0, espera=0.0, marca=None):
    corpo = f"import time, pathlib\ntime.sleep({espera})\n"
    if marca:
        corpo += f"pathlib.Path({str(marca)!r}).joinpath({nome!r}).write_text(str(time.time()))\n"
    corpo += f"print('{nome} rodou')\nraise SystemExit({codigo})\n"
    (pasta / f"{nome}.py").write_text(corpo, encoding="utf-8")


def _rodar(wf, pastas):
    jobs, execucoes, raiz = pastas
    id_execucao = workflows.preparar(wf, execucoes)
    codigo = workflows.orquestrar(execucoes, id_execucao, jobs, raiz, intervalo=0.05)
    return codigo, workflows.execucao(execucoes, id_execucao)


def test_roda_na_ordem_das_dependencias_e_termina_com_sucesso(pastas):
    jobs, execucoes, raiz = pastas
    marcas = raiz / "marcas"
    marcas.mkdir()
    for nome in JOBS:
        _job(jobs, nome, marca=marcas)
    codigo, ex = _rodar(MEDALHAO, pastas)
    assert codigo == 0 and ex.status == workflows.SUCESSO
    assert {n: e.status for n, e in ex.etapas.items()} == {n: workflows.SUCESSO for n in JOBS}
    hora = {n: float((marcas / n).read_text()) for n in JOBS}
    assert hora["bronze"] < hora["silver"] < min(hora["gold_a"], hora["gold_b"])
    assert hora["gold_a"] < hora["exportar"]
    # cada etapa é uma execução de job comum: aparece na tela Jobs ETL, marcada com a origem
    silver = glue.execucao(execucoes, ex.etapas["silver"].execucao)
    assert silver.status == glue.SUCESSO and silver.origem == "workflow medalhao"
    assert "silver rodou" in glue.log(execucoes, ex.etapas["silver"].execucao)


def test_falha_para_o_workflow_e_quem_depende_nao_executa(pastas):
    jobs, _, _ = pastas
    for nome in JOBS:
        _job(jobs, nome, codigo=1 if nome == "silver" else 0)
    codigo, ex = _rodar(MEDALHAO, pastas)
    assert codigo == 1 and ex.status == workflows.FALHOU
    status = {n: e.status for n, e in ex.etapas.items()}
    assert status == {"bronze": workflows.SUCESSO, "silver": workflows.FALHOU, "gold_a": workflows.NAO_EXECUTADO,
                      "gold_b": workflows.NAO_EXECUTADO, "exportar": workflows.NAO_EXECUTADO}


def test_jobs_independentes_rodam_ao_mesmo_tempo_respeitando_o_limite(pastas):
    jobs, _, raiz = pastas
    marcas = raiz / "marcas"
    marcas.mkdir()
    for nome in ("a", "b", "c"):
        _job(jobs, nome, espera=1.0, marca=marcas)
    codigo, ex = _rodar(_wf(("a", []), ("b", []), ("c", []), paralelo=2), pastas)
    assert codigo == 0
    # 3 jobs de 1 s, 2 por vez: os dois primeiros começam juntos e o terceiro só depois que um deles termina.
    # Compara os instantes de início com o fim real dos jobs (e não o relógio do teste todo): a máquina
    # lenta atrasa tudo junto e o teste não fica instável.
    _, execucoes, _ = pastas
    jobs = sorted((glue.execucao(execucoes, e.execucao) for e in ex.etapas.values()), key=lambda j: j.inicio)
    fim = [j.inicio + j.duracao for j in jobs]
    assert jobs[1].inicio < fim[0]                                           # os dois primeiros se sobrepõem
    assert jobs[2].inicio >= min(fim[0], fim[1])                             # o 3º espera uma vaga


def test_job_que_sumiu_falha_a_etapa_com_explicacao(pastas):
    jobs, _, _ = pastas
    _job(jobs, "bronze")
    codigo, ex = _rodar(_wf(("bronze", []), ("silver", ["bronze"])), pastas)
    assert codigo == 1
    assert ex.etapas["silver"].status == workflows.FALHOU and "não existe" in ex.etapas["silver"].erro


def test_parar_nao_comeca_jobs_novos(pastas):
    jobs, execucoes, raiz = pastas
    _job(jobs, "bronze", espera=0.6)
    _job(jobs, "silver")
    wf = _wf(("bronze", []), ("silver", ["bronze"]))
    id_execucao = workflows.preparar(wf, execucoes)
    workflows.parar(execucoes, id_execucao)
    codigo = workflows.orquestrar(execucoes, id_execucao, jobs, raiz, intervalo=0.05)
    ex = workflows.execucao(execucoes, id_execucao)
    assert codigo == 1 and ex.status == workflows.PARADO
    assert ex.etapas["silver"].status == workflows.NAO_EXECUTADO


def test_iniciar_em_segundo_plano_e_acompanhar(pastas):
    jobs, execucoes, raiz = pastas
    for nome in ("bronze", "silver"):
        _job(jobs, nome)
    wf = _wf(("bronze", []), ("silver", ["bronze"]))
    id_execucao = workflows.iniciar(wf, jobs, execucoes, raiz)
    assert workflows.em_execucao(execucoes, "medalhao")
    for _ in range(200):
        if workflows.execucao(execucoes, id_execucao).status != workflows.EM_EXECUCAO:
            break
        time.sleep(0.1)
    ex = workflows.execucao(execucoes, id_execucao)
    assert ex.status == workflows.SUCESSO
    assert [e.id for e in workflows.execucoes(execucoes, "medalhao")] == [id_execucao]
    assert not workflows.em_execucao(execucoes, "medalhao")


def test_arquivo_de_execucao_estragado_e_pulado(pastas):
    jobs, execucoes, _ = pastas
    _job(jobs, "bronze")
    _, ex = _rodar(_wf(("bronze", [])), pastas)
    (execucoes / workflows.PASTA / "medalhao-quebrada.json").write_text("{")
    assert [e.id for e in workflows.execucoes(execucoes, "medalhao")] == [ex.id]


def test_orquestrador_morto_mostra_o_status_real_de_cada_job(pastas):
    jobs, execucoes, raiz = pastas
    _job(jobs, "bronze")
    bronze = glue.iniciar(glue.listar_jobs(jobs)[0], execucoes, raiz, origem="workflow medalhao")
    for _ in range(100):                                  # o job termina sozinho, sem o orquestrador
        if glue.execucao(execucoes, bronze).status != glue.EM_EXECUCAO:
            break
        time.sleep(0.1)
    morto = subprocess.Popen([sys.executable, "-c", "pass"])
    morto.wait()                                          # um pid que já não existe
    wf = _wf(("bronze", []), ("silver", ["bronze"]))
    id_execucao = workflows.preparar(wf, execucoes)
    pasta = execucoes / workflows.PASTA
    dados = json.loads((pasta / f"{id_execucao}.json").read_text(encoding="utf-8"))
    (pasta / f"{id_execucao}.json").write_text(json.dumps({**dados, "pid": morto.pid}), encoding="utf-8")
    (pasta / f"{id_execucao}.estado.json").write_text(json.dumps({
        "bronze": {"status": workflows.EM_EXECUCAO, "execucao": bronze, "inicio": time.time(), "duracao": None, "erro": ""},
        "silver": {"status": workflows.AGUARDANDO, "execucao": None, "inicio": None, "duracao": None, "erro": ""}}),
        encoding="utf-8")
    ex = workflows.execucao(execucoes, id_execucao)
    assert ex.status == workflows.FALHOU
    assert {n: e.status for n, e in ex.etapas.items()} == {"bronze": workflows.SUCESSO,
                                                           "silver": workflows.NAO_EXECUTADO}


def test_historico_do_workflow_guarda_so_as_execucoes_mais_recentes(pastas):
    jobs, execucoes, _ = pastas
    _job(jobs, "bronze")
    ids = []
    for _ in range(3):
        ids.append(_rodar(_wf(("bronze", [])), pastas)[1].id)
        time.sleep(0.01)
    workflows.podar(execucoes, "medalhao", manter=1)
    assert [e.id for e in workflows.execucoes(execucoes, "medalhao")] == [ids[-1]]


def test_orquestrador_do_console_apaga_a_copia_dos_scripts_no_fim(pastas):
    _, execucoes, raiz = pastas
    copia = raiz / "copia"
    copia.mkdir()
    _job(copia, "bronze")
    id_execucao = workflows.preparar(_wf(("bronze", [])), execucoes)
    assert workflows.main(["--execucao", id_execucao, str(copia), str(execucoes), str(raiz), "--descartar"]) == 0
    assert not copia.exists()
