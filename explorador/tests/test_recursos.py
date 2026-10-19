import pytest

from explorador import recursos, s3, workflows
from explorador.tests.s3_falso import S3Falso


@pytest.fixture
def floci(monkeypatch):
    falso = S3Falso()
    monkeypatch.setattr(recursos, "_cliente", lambda: falso)
    return falso


@pytest.fixture
def projeto(tmp_path):
    """pipeline/ com dois jobs, o comum.py e um workflow; a pasta de jobs pode ter um comum.py que só carrega o outro."""
    pipeline = tmp_path / "pipeline"
    (pipeline / "workflows").mkdir(parents=True)
    (pipeline / "bronze.py").write_text("print('bronze')\n")
    (pipeline / "silver.py").write_text("from comum import X\n")
    (pipeline / "comum.py").write_text("X = 1\n")
    (pipeline / "README.md").write_text("não vai para o floci")
    wf = workflows.Workflow("medalhao", "", 1, (workflows.Etapa("bronze"), workflows.Etapa("silver", ("bronze",))))
    workflows.salvar(pipeline, wf)
    return pipeline


def _sync(pasta, comum=None):
    return recursos.sincronizar(pasta, comum or pasta / "comum.py")


def test_primeiro_sync_cria_o_bucket_e_envia_scripts_e_workflows(floci, projeto):
    resumo = _sync(projeto)
    assert sorted(resumo.enviados) == ["scripts/bronze.py", "scripts/comum.py", "scripts/silver.py",
                                       "workflows/medalhao.json"]
    assert resumo.removidos == [] and resumo.iguais == []
    assert set(floci.buckets[recursos.BUCKET]) == set(resumo.enviados)      # README não vai


def test_sync_de_novo_sem_mudancas_nao_envia_nada(floci, projeto):
    _sync(projeto)
    assert recursos.pendencias(projeto, projeto / "comum.py").vazio
    resumo = _sync(projeto)
    assert resumo.enviados == [] and len(resumo.iguais) == 4


def test_sync_espelha_alterados_novos_e_removidos(floci, projeto):
    _sync(projeto)
    (projeto / "bronze.py").write_text("print('bronze v2')\n")
    (projeto / "gold.py").write_text("print('gold')\n")
    (projeto / "silver.py").unlink()
    plano = recursos.pendencias(projeto, projeto / "comum.py")
    assert (sorted(plano.enviados), plano.removidos) == (["scripts/bronze.py", "scripts/gold.py"], ["scripts/silver.py"])
    _sync(projeto)
    assert recursos.ler("scripts/bronze.py") == "print('bronze v2')\n"
    assert recursos.listar_jobs() == ["bronze", "gold"]                     # o comum.py não é job


def test_o_comum_enviado_e_o_de_verdade_e_nao_o_da_pasta_de_jobs(floci, projeto, tmp_path):
    verdadeiro = tmp_path / "comum_verdadeiro.py"
    verdadeiro.write_text("X = 'fonte única'\n")
    _sync(projeto, comum=verdadeiro)
    assert recursos.ler("scripts/comum.py") == "X = 'fonte única'\n"


def test_baixar_scripts_monta_a_pasta_para_rodar(floci, projeto, tmp_path):
    _sync(projeto)
    pasta = recursos.baixar_scripts(tmp_path / "copia")
    assert sorted(p.name for p in pasta.glob("*.py")) == ["bronze.py", "comum.py", "silver.py"]


def test_workflows_no_floci_listar_salvar_e_excluir(floci, projeto):
    _sync(projeto)
    lidos, avisos = recursos.listar_workflows()
    assert [w.nome for w in lidos] == ["medalhao"] and avisos == []
    novo = workflows.Workflow("so_bronze", "", 1, (workflows.Etapa("bronze"),))
    recursos.salvar_workflow(novo)
    assert [w.nome for w in recursos.listar_workflows()[0]] == ["medalhao", "so_bronze"]
    recursos.excluir_workflow("so_bronze")
    assert [w.nome for w in recursos.listar_workflows()[0]] == ["medalhao"]


def test_workflow_estragado_no_bucket_vira_aviso(floci, projeto):
    _sync(projeto)
    floci.put_object(Bucket=recursos.BUCKET, Key="workflows/quebrado.json", Body=b"{nao")
    lidos, avisos = recursos.listar_workflows()
    assert [w.nome for w in lidos] == ["medalhao"] and "quebrado.json" in avisos[0]


def test_bucket_ainda_nao_existe_e_tudo_vazio(floci):
    assert recursos.listar_jobs() == [] and recursos.listar_workflows() == ([], [])


class EndpointConnectionError(Exception):
    """Mesmo nome da falha de rede do botocore: é pelo nome que o explorador a reconhece."""


def test_floci_fora_do_ar_ao_excluir_ou_ler_vira_mensagem_amigavel(floci, monkeypatch):
    def sem_rede(*args, **kwargs):
        raise EndpointConnectionError("floci desligado")
    monkeypatch.setattr(floci, "delete_object", sem_rede, raising=False)
    monkeypatch.setattr(floci, "get_object", sem_rede, raising=False)
    with pytest.raises(s3.S3Indisponivel):
        recursos.excluir_workflow("medalhao")
    with pytest.raises(s3.S3Indisponivel):
        recursos.ler("scripts/bronze.py")
