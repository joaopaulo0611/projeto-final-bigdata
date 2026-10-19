import time

from explorador import glue
from explorador.particoes import Dataset, Objeto

DATASETS = [
    Dataset("gold/funil_compra", "parquet", "gold.funil_compra", False),
    Dataset("landing", "jsonl", "landing.eventos", True),
    Dataset("silver", "parquet", "silver.eventos", True),
    Dataset("silver/itens", "parquet", "silver.itens", True),
    Dataset("bronze", "parquet", "bronze.eventos", True),
]


def test_bancos_seguem_a_ordem_das_camadas():
    bancos = glue.bancos(DATASETS)
    assert list(bancos) == ["landing", "bronze", "silver", "gold"]
    assert [d.nome_view for d in bancos["silver"]] == ["silver.eventos", "silver.itens"]


def test_localizacao_e_chaves_de_particao():
    objetos = [Objeto("silver/event_name=scroll/year=2026/month=09/day=01/a.parquet", 1),
               Objeto("silver/itens/year=2026/month=09/day=01/b.parquet", 1),
               Objeto("gold/funil_compra/part-0.parquet", 1)]
    assert glue.localizacao(DATASETS[2], "datalake-tracking") == "s3://datalake-tracking/silver/"
    assert glue.chaves_particao(DATASETS[2], objetos) == ["event_name", "year", "month", "day"]
    assert glue.chaves_particao(DATASETS[3], objetos) == ["year", "month", "day"]
    assert glue.chaves_particao(DATASETS[0], objetos) == []


def test_listar_jobs_pega_os_scripts_e_ignora_o_comum(tmp_path):
    for nome in ("bronze.py", "silver.py", "comum.py", "__init__.py", "_rascunho.py", "notas.txt"):
        (tmp_path / nome).write_text("print('oi')\n")
    assert [j.nome for j in glue.listar_jobs(tmp_path)] == ["bronze", "silver"]
    assert glue.listar_jobs(tmp_path / "nao_existe") == []


def _esperar(pasta, id_execucao, segundos=20):
    for _ in range(segundos * 10):
        execucao = glue.execucao(pasta, id_execucao)
        if execucao.status != glue.EM_EXECUCAO:
            return execucao
        time.sleep(0.1)
    raise AssertionError("a execução não terminou")


def test_executar_um_job_que_termina_bem(tmp_path):
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "bronze.py").write_text("print('linhas gravadas: 10')\n")
    job = glue.listar_jobs(tmp_path / "jobs")[0]
    pasta = tmp_path / "execucoes"
    id_execucao = glue.iniciar(job, pasta, raiz=tmp_path)
    assert glue.em_execucao(pasta, "bronze") in (True, False)
    execucao = _esperar(pasta, id_execucao)
    assert execucao.status == glue.SUCESSO and execucao.codigo == 0
    assert "linhas gravadas: 10" in glue.log(pasta, id_execucao)
    assert execucao.duracao >= 0
    assert [e.id for e in glue.execucoes(pasta, "bronze")] == [id_execucao]


def test_executar_um_job_que_falha_guarda_o_codigo_e_o_erro(tmp_path):
    (tmp_path / "ruim.py").write_text("import sys\nprint('camada anterior não existe', file=sys.stderr)\nsys.exit(3)\n")
    job = glue.listar_jobs(tmp_path)[0]
    pasta = tmp_path / "execucoes"
    execucao = _esperar(pasta, glue.iniciar(job, pasta, raiz=tmp_path))
    assert execucao.status == glue.FALHOU and execucao.codigo == 3
    assert "camada anterior não existe" in glue.log(pasta, execucao.id)


def test_execucoes_mais_recentes_primeiro_e_so_do_job_pedido(tmp_path):
    (tmp_path / "a.py").write_text("pass\n")
    (tmp_path / "b.py").write_text("pass\n")
    a, b = glue.listar_jobs(tmp_path)
    pasta = tmp_path / "execucoes"
    primeira = _esperar(pasta, glue.iniciar(a, pasta, raiz=tmp_path)).id
    time.sleep(0.01)
    segunda = _esperar(pasta, glue.iniciar(a, pasta, raiz=tmp_path)).id
    _esperar(pasta, glue.iniciar(b, pasta, raiz=tmp_path))
    assert [e.id for e in glue.execucoes(pasta, "a")] == [segunda, primeira]
    assert glue.em_execucao(pasta, "a") is False


def test_banco_de_outro_bucket_vem_depois_das_camadas_e_aponta_para_o_bucket_dele():
    from explorador import particoes
    outros = particoes.datasets([particoes.chave_virtual("rascunho-turma", "notas/a.parquet")])
    bancos = glue.bancos(DATASETS + outros)
    assert list(bancos) == ["landing", "bronze", "silver", "gold", "rascunho_turma"]
    assert glue.local_do_banco(bancos["rascunho_turma"], "datalake-tracking") == "s3://rascunho-turma/"
    assert glue.local_do_banco(bancos["silver"], "datalake-tracking") == "s3://datalake-tracking/silver/"
    assert glue.localizacao(outros[0], "datalake-tracking") == "s3://rascunho-turma/notas/"


def test_arquivo_de_execucao_estragado_e_pulado_sem_derrubar_a_lista(tmp_path):
    (tmp_path / "a.py").write_text("pass\n")
    pasta = tmp_path / "execucoes"
    boa = _esperar(pasta, glue.iniciar(glue.listar_jobs(tmp_path)[0], pasta, raiz=tmp_path)).id
    (pasta / "a-quebrada.json").write_text('{"job": "a", "ini')          # o contêiner caiu no meio da gravação
    assert [e.id for e in glue.execucoes(pasta, "a")] == [boa]


def test_execucao_apaga_a_copia_dos_scripts_ao_terminar(tmp_path):
    copia = tmp_path / "copia"
    copia.mkdir()
    (copia / "a.py").write_text("print('ok')\n")
    pasta = tmp_path / "execucoes"
    execucao = _esperar(pasta, glue.iniciar(glue.Job("a", copia / "a.py"), pasta, raiz=tmp_path, descartar=copia))
    assert execucao.status == glue.SUCESSO and "ok" in glue.log(pasta, execucao.id)
    for _ in range(50):                                   # o .fim sai um instante antes da cópia ser apagada
        if not copia.exists():
            break
        time.sleep(0.05)
    assert not copia.exists()


def test_historico_guarda_so_as_execucoes_mais_recentes(tmp_path):
    (tmp_path / "a.py").write_text("pass\n")
    job = glue.listar_jobs(tmp_path)[0]
    pasta = tmp_path / "execucoes"
    ids = []
    for _ in range(4):
        ids.append(_esperar(pasta, glue.iniciar(job, pasta, raiz=tmp_path)).id)
        time.sleep(0.01)
    glue.podar(pasta, "a", manter=2)
    assert [e.id for e in glue.execucoes(pasta, "a")] == ids[:1:-1]          # as duas últimas, mais recente primeiro
    assert not list(pasta.glob(f"{ids[0]}.*"))                              # .json, .log e .fim saíram


def test_limpar_copias_apaga_so_as_esquecidas(tmp_path):
    import os
    velha, nova = tmp_path / "bronze-1", tmp_path / "bronze-2"
    velha.mkdir()
    nova.mkdir()
    os.utime(velha, (time.time() - 2 * 24 * 3600,) * 2)
    glue.limpar_copias(tmp_path)
    assert not velha.exists() and nova.exists()
