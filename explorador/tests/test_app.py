import functools
import json
import time
from pathlib import Path

import duckdb
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from explorador import consultas, recursos, s3, workflows
from explorador.particoes import Objeto
from explorador.tests.s3_falso import S3Falso

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def limpar_cache():
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture(autouse=True)
def so_o_bucket_do_datalake(monkeypatch):
    """Sem isto a tela S3 perguntaria ao floci de verdade quais buckets existem."""
    monkeypatch.setattr(s3, "listar_buckets", lambda *_, **__: [s3.BUCKET])


@pytest.fixture(autouse=True)
def floci_falso(monkeypatch):
    """Os scripts e workflows dos jobs vão para um S3 em memória, nunca para o floci de verdade."""
    falso = S3Falso()
    monkeypatch.setattr(recursos, "_cliente", lambda: falso)
    return falso


def _rodar():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_floci_desligado_mostra_mensagem_amigavel(monkeypatch):
    def desligado(*_, **__):
        raise s3.S3Indisponivel("Não consegui falar com o S3 em http://floci:4566. Rode `docker compose up -d floci`.")
    monkeypatch.setattr(s3, "listar", desligado)
    at = _rodar()
    assert not at.exception
    assert "docker compose up -d floci" in at.error[0].value


def test_bucket_vazio_orienta_a_rodar_o_gerador(monkeypatch):
    monkeypatch.setattr(s3, "listar", lambda *_, **__: [])
    at = _rodar()
    assert not at.exception
    assert "gerar_eventos.py" in at.info[0].value


@pytest.fixture
def bucket_local(tmp_path, monkeypatch):
    pasta = tmp_path / "silver" / "event_name=page_view" / "year=2026" / "month=09" / "day=01"
    pasta.mkdir(parents=True)
    duckdb.sql("COPY (SELECT 'e' || i AS event_id, {'page': 'home', 'user': {'id': i}} AS props "
               f"FROM range(4) t(i)) TO '{pasta}/part-0.parquet' (FORMAT parquet)")
    objetos = [Objeto(p.relative_to(tmp_path).as_posix(), p.stat().st_size)
               for p in tmp_path.rglob("*") if p.is_file()]
    monkeypatch.setattr(s3, "listar", lambda *_, **__: objetos)
    monkeypatch.setattr(s3, "raiz", lambda *_: str(tmp_path))
    monkeypatch.setattr(consultas, "conectar", functools.partial(consultas.conectar, s3=False))
    return tmp_path

ATHENA = "Athena · Editor de consultas"
SQL = "sql:Consulta 1"


def _athena(at):
    return at.radio(key="tela").set_value(ATHENA).run()


def _executar(at, sql, aba="Consulta 1"):
    at.text_area(key=f"sql:{aba}").input(sql).run()
    return at.button(key="executar").click().run()


def test_abre_no_s3_com_a_lista_de_buckets_e_entra_no_bucket(bucket_local):
    at = _rodar()
    assert not at.exception
    assert at.radio(key="tela").options == ["🪣  Buckets", "🗂  Data Catalog", "⚙  Jobs ETL", "🔀  Workflows",
                                             "🔎  Editor de consultas"]
    assert at.button(key=f"bucket:{s3.BUCKET}").label.endswith(s3.BUCKET)
    at.button(key=f"bucket:{s3.BUCKET}").click().run()
    assert [t.label for t in at.tabs] == ["Objetos", "Partições", "Propriedades"]


def test_navega_pelo_breadcrumb_e_mostra_a_previa_do_arquivo(bucket_local):
    at = _rodar()
    at.button(key=f"bucket:{s3.BUCKET}").click().run()
    caminho = ""
    for pasta in ("silver", "event_name=page_view", "year=2026", "month=09", "day=01"):
        caminho += pasta + "/"
        at.button(key=f"obj:{caminho}").click().run()
    assert at.session_state["pasta"] == "silver/event_name=page_view/year=2026/month=09/day=01/"
    at.button(key=f"obj:{caminho}part-0.parquet").click().run()
    assert not at.exception
    previa = next(d.value for d in at.dataframe if "event_id" in d.value.columns)
    assert previa["event_id"].tolist() == ["e0", "e1", "e2", "e3"]
    at.button(key="migalha:silver/event_name=page_view/").click().run()
    assert at.session_state["pasta"] == "silver/event_name=page_view/"
    at.button(key="migalha:buckets").click().run()
    assert at.button(key=f"bucket:{s3.BUCKET}")


def test_aba_particoes_lista_os_dias_e_conta_linhas(bucket_local):
    at = _rodar()
    at.button(key=f"bucket:{s3.BUCKET}").click().run()
    assert at.selectbox(key="dataset").value == "silver.eventos"
    at.button(key="contar").click().run()
    assert not at.exception
    contagens = [d.value for d in at.dataframe if "linhas" in d.value.columns]
    assert contagens[-1]["linhas"].tolist() == [4]


def test_athena_executa_e_mostra_detalhes_da_execucao(bucket_local):
    at = _executar(_athena(_rodar()), "SELECT count(*) AS n FROM silver.eventos")
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Resultados", "Consultas recentes"]
    assert at.dataframe[0].value["n"].tolist() == [4]
    resumo = next(s.value for s in at.success)
    assert resumo.startswith("Concluída · tempo de execução") and "dados lidos (estimado)" in resumo
    assert "0 B" not in resumo                       # a view silver tem arquivos: a estimativa não é zero


def test_athena_recusa_sql_de_escrita(bucket_local):
    at = _executar(_athena(_rodar()), "DROP VIEW silver")
    assert any("só faz consultas de leitura" in e.value for e in at.error)


def test_athena_avisa_quando_corta_o_resultado(bucket_local):
    at = _athena(_rodar())
    at.text_area(key=SQL).input("SELECT * FROM range(20)").run()
    at.number_input(key="limite:Consulta 1").set_value(5).run()
    at.button(key="executar").click().run()
    assert len(at.dataframe[0].value) == 5
    assert any("cortado em 5 linhas" in w.value for w in at.warning)


def test_athena_erro_de_sql_vem_explicado_em_portugues(bucket_local):
    at = _executar(_athena(_rodar()), "SELECT * FROM view_que_nao_existe")
    assert not at.exception
    assert any("não existe" in e.value for e in at.error)
    assert any("Mensagem original do DuckDB" in c.value for c in at.caption)


def test_athena_abas_guardam_cada_uma_a_sua_consulta(bucket_local):
    at = _executar(_athena(_rodar()), "SELECT 1 AS um")
    at.button(key="nova_aba").click().run()
    assert at.text_area(key="sql:Consulta 2").value == ""
    at = _executar(at, "SELECT 2 AS dois", aba="Consulta 2")
    assert at.dataframe[0].value.columns.tolist() == ["dois"]
    at.radio(key="aba_ativa").set_value("Consulta 1").run()
    assert at.text_area(key=SQL).value == "SELECT 1 AS um"
    assert at.dataframe[0].value.columns.tolist() == ["um"]
    at.button(key="fechar_aba").click().run()
    assert at.radio(key="aba_ativa").options == ["Consulta 2"]


def test_athena_arvore_insere_o_nome_da_tabela_no_editor(bucket_local):
    at = _athena(_rodar())
    at.text_area(key=SQL).input("SELECT * FROM").run()
    at.button(key="inserir:silver.eventos").click().run()
    assert at.text_area(key=SQL).value == "SELECT * FROM silver.eventos"


def test_athena_historico_guarda_as_consultas_e_reabre_no_editor(bucket_local):
    at = _executar(_athena(_rodar()), "SELECT 1 AS um")
    at = _executar(at, "SELECT * FROM nao_existe")
    tabela = at.dataframe[-1].value
    assert tabela["Status"].tolist() == ["Falhou", "Concluída"]
    at.button(key="abrir_hist:1").click().run()
    assert at.text_area(key=SQL).value == "SELECT 1 AS um"


def test_erro_inesperado_vira_mensagem_sem_stack_trace(monkeypatch):
    def negado(*_, **__):
        raise RuntimeError("AccessDenied")
    monkeypatch.setattr(s3, "listar", negado)
    at = _rodar()
    assert not at.exception
    assert "Algo deu errado" in at.error[0].value


CATALOGO = "Glue · Data Catalog"
JOBS = "Glue · Jobs ETL"


def test_catalogo_navega_banco_tabela_e_abre_no_athena(bucket_local):
    at = _rodar()
    at.radio(key="tela").set_value(CATALOGO).run()
    assert not at.exception
    at.button(key="banco:silver").click().run()
    at.button(key="tabela:silver.eventos").click().run()
    assert [t.label for t in at.tabs] == ["Esquema", "Partições"]     # propriedades viraram o painel "Visão geral"
    textos = [str(m.value) for m in at.markdown]
    assert any(">event_id<" in t for t in textos) and any(">sim<" in t for t in textos)   # event_name é a chave
    at.button(key="consultar_athena").click().run()
    assert at.radio(key="tela").value == ATHENA
    assert at.text_area(key="sql:Consulta 2").value == "SELECT * FROM silver.eventos LIMIT 10"


def test_catalogo_com_tabela_que_sumiu_volta_para_o_banco_sem_erro(bucket_local):
    at = _rodar()
    at.radio(key="tela").set_value(CATALOGO).run()
    at.session_state["cat_banco"] = "silver"
    at.session_state["cat_tabela"] = "silver.nao_existe_mais"          # escolhida antes do Recarregar
    at.run()
    assert not at.exception and not at.error
    assert any(b.key == "tabela:silver.eventos" for b in at.button)    # mostra as tabelas do banco


def test_jobs_lista_executa_e_mostra_o_log(bucket_local, tmp_path, monkeypatch):
    jobs = tmp_path / "meus_jobs"
    jobs.mkdir()
    (jobs / "bronze.py").write_text("print('bronze gravada')\n")
    (jobs / "comum.py").write_text("")
    monkeypatch.setenv("EXPLORADOR_JOBS", str(jobs))
    monkeypatch.setenv("EXPLORADOR_EXECUCOES", str(tmp_path / "execucoes"))
    at = _rodar()
    at.radio(key="tela").set_value(JOBS).run()
    assert not at.exception
    assert not [b for b in at.button if b.key and b.key.startswith("job:")]   # nada no floci antes do sync
    at.button(key="sincronizar-jobs").click().run()
    assert any("Sincronizado" in t.value for t in at.toast)                # aviso rápido, que some sozinho
    assert [b.key for b in at.button if b.key and b.key.startswith("job:")] == ["job:bronze"]
    at.button(key="job:bronze").click().run()
    assert [t.label for t in at.tabs] == ["Execuções", "Script"]
    assert any("bronze gravada" in c.value for c in at.code)           # o script mostrado é o do floci
    at.button(key="executar_job").click().run()
    for _ in range(100):
        at.run()
        if any("Sucesso" in str(m.value) for m in at.markdown):
            break
        time.sleep(0.2)
    assert any("selo-ok" in str(m.value) and "Sucesso" in str(m.value) for m in at.markdown)
    assert any("bronze gravada" in c.value for c in at.code)


@pytest.fixture(autouse=True)
def preferencias_isoladas(tmp_path, monkeypatch):
    arquivo = tmp_path / "prefs" / "preferencias.json"
    monkeypatch.setenv("EXPLORADOR_PREFERENCIAS", str(arquivo))
    return arquivo


def test_cada_tela_escolhe_o_seu_roteiro_do_tutorial(bucket_local):
    at = _rodar()
    assert at.session_state["contexto_tour"] == "s3-buckets"
    at.button(key=f"bucket:{s3.BUCKET}").click().run()
    assert at.session_state["contexto_tour"] == "s3-bucket"
    at.radio(key="tela").set_value(ATHENA).run()
    assert at.session_state["contexto_tour"] == "athena"
    at.radio(key="tela").set_value(CATALOGO).run()
    assert at.session_state["contexto_tour"] == "catalogo-bancos"


def test_botao_abre_o_tutorial_mesmo_desligado(bucket_local):
    at = _rodar()
    at.toggle(key="pref_tutorial").set_value(False).run()
    at.button(key="tour-abrir").click().run()
    assert not at.exception
    primeiro = at.session_state["tour_forcar"]
    assert primeiro
    at.button(key="tour-abrir").click().run()
    assert at.session_state["tour_forcar"] != primeiro                # cada clique gera um pedido novo


def test_desligar_o_tutorial_lembra_a_escolha(bucket_local, preferencias_isoladas):
    at = _rodar()
    assert at.toggle(key="pref_tutorial").value is True
    at.toggle(key="pref_tutorial").set_value(False).run()
    assert '"tutorial": false' in preferencias_isoladas.read_text(encoding="utf-8")
    st.cache_data.clear()
    st.cache_resource.clear()
    assert _rodar().toggle(key="pref_tutorial").value is False        # nova sessão: continua desligado


def test_nao_mostrar_mais_do_modal_grava_a_preferencia(bucket_local, preferencias_isoladas):
    at = _rodar()
    at.button(key="tour-desligar").click().run()                      # é o botão que o modal clica
    assert at.toggle(key="pref_tutorial").value is False
    assert '"tutorial": false' in preferencias_isoladas.read_text(encoding="utf-8")


def test_abrir_o_console_nao_grava_preferencias(bucket_local, preferencias_isoladas):
    at = _rodar()
    at.radio(key="tela").set_value(ATHENA).run()
    assert not at.exception
    assert not preferencias_isoladas.exists()           # só grava quando a pessoa muda a chave


def test_botoes_flutuantes_e_menu_de_acessibilidade(bucket_local):
    at = _rodar()
    assert not at.exception
    assert at.button(key="topo").label == "⬆"
    assert at.button(key="tour-abrir").label == "🎓"
    assert at.radio(key="pref_texto").value == 100
    assert at.toggle(key="pref_contraste").value is False


def test_acessibilidade_e_gravada_e_aplicada(bucket_local, preferencias_isoladas):
    at = _rodar()
    at.radio(key="pref_texto").set_value(130).run()
    at.toggle(key="pref_contraste").set_value(True).run()
    salvo = preferencias_isoladas.read_text(encoding="utf-8")
    assert '"texto": 130' in salvo and '"contraste": true' in salvo
    estilos = " ".join(str(m.value) for m in at.markdown)
    assert "font-size: 130%" in estilos and "#000" in estilos
    st.cache_data.clear()
    st.cache_resource.clear()
    nova = _rodar()                                                   # nova sessão: continua valendo
    assert nova.radio(key="pref_texto").value == 130
    assert nova.toggle(key="pref_contraste").value is True


def test_voltar_ao_padrao_desfaz_a_acessibilidade_e_mantem_o_tutorial(bucket_local, preferencias_isoladas):
    at = _rodar()
    at.toggle(key="pref_tutorial").set_value(False).run()
    at.toggle(key="pref_movimento").set_value(True).run()
    at.button(key="a11y-padrao").click().run()
    assert at.toggle(key="pref_movimento").value is False
    assert at.toggle(key="pref_tutorial").value is False
    assert '"movimento": false' in preferencias_isoladas.read_text(encoding="utf-8")


def test_titulos_e_tabelas_marcados_para_leitor_de_tela(bucket_local):
    at = _rodar()
    textos = " ".join(str(m.value) for m in at.markdown)
    assert 'role="heading" aria-level="1"' in textos and 'role="heading" aria-level="2"' in textos


def _struct_na_tela(at):
    textos = [str(m.value) for m in at.markdown]
    assert not any("STRUCT(" in t.upper() for t in textos)            # o tipo completo não aparece na tela
    popovers = [p for p in at.get("popover") if p.proto.popover.label == "struct"]
    assert popovers, "o tipo struct vira um botão que abre o overlay"
    arvore = next(t for t in textos if t.startswith("- `page` varchar"))
    assert "- `user` struct\n    - `id` bigint" in arvore              # um recuo por nível


def test_esquema_mostra_struct_curto_e_a_tipagem_interna_no_overlay(bucket_local):
    at = _rodar()
    at.radio(key="tela").set_value(CATALOGO).run()
    at.button(key="banco:silver").click().run()
    at.button(key="tabela:silver.eventos").click().run()
    assert not at.exception
    _struct_na_tela(at)


def test_arvore_do_athena_mostra_struct_curto_e_a_tipagem_interna_no_overlay(bucket_local):
    at = _athena(_rodar())
    assert not at.exception
    _struct_na_tela(at)


WORKFLOWS = "Glue · Workflows"


@pytest.fixture
def pasta_workflows(tmp_path, monkeypatch):
    jobs = tmp_path / "meus_jobs"
    jobs.mkdir()
    for nome in ("bronze", "silver", "gold"):
        (jobs / f"{nome}.py").write_text(f"print('{nome} gravada')\n")
    monkeypatch.setenv("EXPLORADOR_JOBS", str(jobs))
    monkeypatch.setenv("EXPLORADOR_EXECUCOES", str(tmp_path / "execucoes"))
    return jobs


def _workflows(at, sincronizar=True):
    at = at.radio(key="tela").set_value(WORKFLOWS).run()
    return at.button(key="sincronizar-workflows").click().run() if sincronizar else at


def test_cria_workflow_pelo_console_e_salva_o_json(pasta_workflows, floci_falso):
    at = _workflows(_rodar())
    assert not at.exception
    at.button(key="criar_workflow").click().run()
    at.text_input(key="wf_form_nome").input("medalhao").run()
    at.multiselect(key="wf_form_jobs").select("bronze").select("silver").select("gold").run()
    at.button(key="wf_encadear").click().run()                       # cada job depende do anterior
    assert at.multiselect(key="wf_form_dep:gold").value == ["silver"]
    at.button(key="wf_salvar").click().run()
    assert not at.exception
    salvo = json.loads((pasta_workflows / "workflows" / "medalhao.json").read_text(encoding="utf-8"))
    assert salvo["etapas"] == [{"job": "bronze", "depende_de": []}, {"job": "silver", "depende_de": ["bronze"]},
                               {"job": "gold", "depende_de": ["silver"]}]
    assert at.session_state["wf_sel"] == "medalhao"                  # abre o workflow recém-criado
    no_floci = json.loads(floci_falso.buckets[recursos.BUCKET]["workflows/medalhao.json"])
    assert no_floci["etapas"] == salvo["etapas"]                      # salvo no floci e na pasta local
    assert [t.label for t in at.tabs] == ["Execução", "Histórico", "Definição"]


def test_formulario_recusa_ciclo_e_explica(pasta_workflows):
    at = _workflows(_rodar())
    at.button(key="criar_workflow").click().run()
    at.text_input(key="wf_form_nome").input("circular").run()
    at.multiselect(key="wf_form_jobs").select("bronze").select("silver").run()
    at.multiselect(key="wf_form_dep:bronze").select("silver").run()
    at.multiselect(key="wf_form_dep:silver").select("bronze").run()
    assert any("ciclo" in w.value for w in at.warning)               # a prévia já avisa
    at.button(key="wf_salvar").click().run()
    assert any("ciclo" in e.value for e in at.error)
    assert not (pasta_workflows / "workflows" / "circular.json").exists()


def test_executa_workflow_e_mostra_o_status_de_cada_etapa(pasta_workflows):
    wf = workflows.Workflow("medalhao", "", 2, (workflows.Etapa("bronze"), workflows.Etapa("silver", ("bronze",)),
                                               workflows.Etapa("gold", ("bronze",))))
    workflows.salvar(pasta_workflows, wf)
    at = _workflows(_rodar())
    at.button(key="wf:medalhao").click().run()
    at.button(key="executar_workflow").click().run()
    for _ in range(150):
        at.run()
        if any("Sucesso" in str(m.value) and "duração" in str(m.value) for m in at.markdown):
            break
        time.sleep(0.2)
    assert not at.exception
    resumo = next(str(m.value) for m in at.markdown if "duração" in str(m.value))
    assert "Sucesso" in resumo
    at.selectbox(key="wf_log_sel").set_value("gold").run()
    assert any("gold gravada" in c.value for c in at.code)            # log da etapa escolhida
    # cada etapa também aparece no histórico do job, marcada com a origem
    at.radio(key="tela").set_value(JOBS).run()
    at.button(key="job:silver").click().run()
    assert any(">workflow medalhao<" in str(m.value) for m in at.markdown)


def test_tela_s3_mostra_todos_os_buckets_e_abre_outro(bucket_local, monkeypatch):
    outro = bucket_local / "outro-bucket"
    (outro / "brutos").mkdir(parents=True)
    duckdb.sql(f"COPY (SELECT 7 AS numero) TO '{outro}/brutos/a.parquet' (FORMAT parquet)")
    por_bucket = {s3.BUCKET: s3.listar(), "rascunho": [Objeto("brutos/a.parquet", (outro / "brutos/a.parquet").stat().st_size)]}
    monkeypatch.setattr(s3, "listar_buckets", lambda *_, **__: [s3.BUCKET, "rascunho"])
    monkeypatch.setattr(s3, "listar", lambda prefixo="", cliente=None, bucket=None: por_bucket[bucket or s3.BUCKET])
    monkeypatch.setattr(s3, "raiz", lambda bucket=None: str(outro) if bucket == "rascunho" else str(bucket_local))
    at = _rodar()
    assert not at.exception
    assert at.button(key="bucket:rascunho") and at.button(key=f"bucket:{s3.BUCKET}")
    textos = " ".join(str(m.value) for m in at.markdown)
    assert "datalake: Data Catalog e Athena" in textos and textos.count("Data Catalog e Athena") >= 2
    at.button(key="bucket:rascunho").click().run()
    at.button(key="obj:brutos/").click().run()
    at.button(key="obj:brutos/a.parquet").click().run()
    assert not at.exception
    previa = next(d.value for d in at.dataframe if "numero" in d.value.columns)
    assert previa["numero"].tolist() == [7]
    at.button(key="migalha:buckets").click().run()
    at.button(key=f"bucket:{s3.BUCKET}").click().run()                # volta para o datalake sem erro
    assert not at.exception and at.session_state["bucket_sel"] == s3.BUCKET


@pytest.fixture
def dois_buckets(bucket_local, monkeypatch):
    outro = bucket_local / "outro-bucket"
    (outro / "notas").mkdir(parents=True)
    duckdb.sql(f"COPY (SELECT 'ana' AS aluno, 9 AS nota UNION ALL SELECT 'bia', 8) TO '{outro}/notas/a.parquet' (FORMAT parquet)")
    por_bucket = {s3.BUCKET: s3.listar(),
                  "rascunho-turma": [Objeto("notas/a.parquet", (outro / "notas/a.parquet").stat().st_size)]}
    monkeypatch.setattr(s3, "listar_buckets", lambda *_, **__: [s3.BUCKET, "rascunho-turma"])
    monkeypatch.setattr(s3, "listar", lambda prefixo="", cliente=None, bucket=None: por_bucket[bucket or s3.BUCKET])
    monkeypatch.setattr(s3, "raiz", lambda bucket=None: str(outro) if bucket == "rascunho-turma" else str(bucket_local))
    return outro


def test_catalogo_tem_um_banco_para_cada_outro_bucket(dois_buckets):
    at = _rodar()
    at.radio(key="tela").set_value(CATALOGO).run()
    assert not at.exception
    assert at.button(key="banco:silver") and at.button(key="banco:rascunho_turma")
    at.button(key="banco:rascunho_turma").click().run()
    at.button(key="tabela:rascunho_turma.notas").click().run()
    textos = " ".join(str(m.value) for m in at.markdown)
    assert "s3://rascunho-turma/notas/" in textos and ">nota<" in textos
    at.button(key="consultar_athena").click().run()
    at.button(key="executar").click().run()
    assert not at.exception
    assert sorted(at.dataframe[0].value["aluno"].tolist()) == ["ana", "bia"]


def test_athena_junta_tabelas_de_buckets_diferentes(dois_buckets):
    at = _executar(_athena(_rodar()), "SELECT (SELECT count(*) FROM silver.eventos) AS eventos, "
                                      "(SELECT max(nota) FROM rascunho_turma.notas) AS maior_nota")
    assert not at.exception
    assert at.dataframe[0].value.to_dict("records") == [{"eventos": 4, "maior_nota": 9}]
    resumo = next(s.value for s in at.success)
    assert "0 B" not in resumo                                         # a estimativa conta os dois buckets


def test_tabela_ilegivel_de_um_bucket_vira_aviso_sem_derrubar_o_catalogo(dois_buckets, monkeypatch):
    (dois_buckets / "quebrado").mkdir()
    (dois_buckets / "quebrado" / "x.parquet").write_text("isto não é parquet")
    por_bucket = {s3.BUCKET: s3.listar(), "rascunho-turma": s3.listar(bucket="rascunho-turma")
                  + [Objeto("quebrado/x.parquet", 18)]}
    monkeypatch.setattr(s3, "listar", lambda prefixo="", cliente=None, bucket=None: por_bucket[bucket or s3.BUCKET])
    at = _rodar()
    at.radio(key="tela").set_value(CATALOGO).run()
    assert not at.exception
    assert any("rascunho_turma.quebrado" in str(m.value) for m in at.markdown)   # o aviso cita a tabela
    assert at.button(key="banco:silver")                                         # o resto continua


def test_bucket_de_recursos_aparece_no_s3_mas_nao_vira_banco(bucket_local, monkeypatch):
    por_bucket = {s3.BUCKET: s3.listar(),
                  recursos.BUCKET: [Objeto("scripts/bronze.py", 10), Objeto("workflows/medalhao.json", 10),
                                    Objeto("scripts/sobra.parquet", 10)]}
    monkeypatch.setattr(s3, "listar_buckets", lambda *_, **__: [s3.BUCKET, recursos.BUCKET])
    monkeypatch.setattr(s3, "listar", lambda prefixo="", cliente=None, bucket=None: por_bucket[bucket or s3.BUCKET])
    at = _rodar()
    assert at.button(key=f"bucket:{recursos.BUCKET}")
    assert any("scripts e workflows" in str(m.value) for m in at.markdown)
    at.radio(key="tela").set_value(CATALOGO).run()
    assert not at.exception
    assert not [b for b in at.button if b.key and b.key.startswith("banco:glue")]   # nem com um .parquet perdido lá
