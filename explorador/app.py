"""Console do datalake: telas no estilo do S3, do Glue (Data Catalog e Jobs ETL) e do Athena.

    docker compose up -d explorador      # e abra http://localhost:8501

S3, Data Catalog e Athena só leem. Jobs ETL e Workflows rodam os scripts guardados no bucket
glue-assets do floci (o botão Sincronizar envia para lá o que está em pipeline/). É uma ferramenta
de estudo que imita o fluxo de um console de nuvem; não usa nenhuma marca nem serviço de nuvem.
"""

from __future__ import annotations

import html
import json
import os
import shutil
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
import pandas as pd
import streamlit as st

from streamlit.runtime.scriptrunner_utils.exceptions import RerunException, StopException

from explorador import athena, consultas, glue, particoes, preferencias, recursos, s3, tutorial, ui, workflows
from explorador.tutorial import TELA_ATHENA, TELA_CATALOGO, TELA_JOBS, TELA_S3, TELA_WORKFLOWS

RAIZ = Path(__file__).resolve().parents[1]
ICONES = {TELA_S3: "🪣  Buckets", TELA_CATALOGO: "🗂  Data Catalog", TELA_JOBS: "⚙  Jobs ETL",
          TELA_WORKFLOWS: "🔀  Workflows",
          TELA_ATHENA: "🔎  Editor de consultas"}

EXEMPLOS = {
    "Eventos por nome (landing)": (
        "SELECT event_name, count(*) AS eventos\nFROM landing.eventos\n"
        "GROUP BY event_name\nORDER BY eventos DESC"
    ),
    "Linhas por dia (Silver)": (
        "SELECT year, month, day, count(*) AS linhas\nFROM silver.eventos\nGROUP BY ALL\nORDER BY ALL"
    ),
    "Colunas de uma tabela": "DESCRIBE silver.eventos",
}


@st.cache_data(ttl=30, show_spinner="Listando o bucket…")
def _listar(bucket: str | None = None) -> list[particoes.Objeto]:
    return s3.listar(bucket=bucket or s3.BUCKET)


def _fechar(valor) -> None:
    """Fecha a conexão DuckDB quando ela sai do cache (Recarregar ou datasets novos)."""
    valor[0].close()


def _mostrar_erro(titulo: str, erro: Exception) -> None:
    st.error(f"{titulo} {consultas.explicar_erro(erro)}")
    st.caption(f"Mensagem original do DuckDB: {erro}")


@st.cache_resource(max_entries=2, on_release=_fechar, show_spinner="Conectando ao S3 e criando as tabelas…")
def _conexao(datasets: tuple[particoes.Dataset, ...], raizes: tuple[str, ...]):
    """Uma view por tabela de todos os buckets; a conexão fica trancada nesses buckets.

    Uma tabela que o DuckDB não consegue ler (arquivo estragado num bucket qualquer) vira aviso, não derruba o resto."""
    con = consultas.conectar(endpoint=s3.ENDPOINT, chave=s3.CHAVE, segredo=s3.SEGREDO, regiao=s3.REGIAO)
    colunas, falhas = {}, {}
    for dataset in datasets:
        try:
            consultas.criar_views(con, s3.raiz, [dataset])
            descricao = con.sql(f"DESCRIBE {particoes.sql_nome(dataset.nome_view)}").df()
            colunas[dataset.nome_view] = list(zip(descricao["column_name"], descricao["column_type"]))
        except duckdb.Error as erro:
            falhas[dataset.nome_view] = f"{consultas.explicar_erro(erro)} ({str(erro).splitlines()[0][:160]})"
    consultas.travar(con, raizes)
    return con, colunas, falhas


def _escolher(**valores) -> None:
    for chave, valor in valores.items():
        st.session_state[chave] = valor


# ------------------------------------------------------------------ S3 ------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner="Listando os buckets…")
def _buckets() -> list[str]:
    return s3.listar_buckets()


@st.cache_resource(max_entries=4, on_release=lambda con: con.close(), show_spinner=False)
def _conexao_bucket(bucket: str):
    """Conexão só para a prévia e a contagem da tela S3, trancada no bucket aberto (cada bucket tem a sua)."""
    con = consultas.conectar(endpoint=s3.ENDPOINT, chave=s3.CHAVE, segredo=s3.SEGREDO, regiao=s3.REGIAO)
    consultas.travar(con, s3.raiz(bucket))
    return con


def _uso_do_bucket(bucket: str) -> str:
    if bucket == s3.BUCKET:
        return "datalake: Data Catalog e Athena"
    if bucket == recursos.BUCKET:
        return "scripts e workflows (Jobs ETL e Workflows)"
    return "Data Catalog e Athena"


def _ir_para(pasta: str | None, bucket: str | None = None) -> None:
    """pasta None = lista de buckets; "" = raiz do bucket; "silver/…/" = uma pasta."""
    if bucket is not None:
        st.session_state["bucket_sel"] = bucket
    st.session_state["bucket_aberto"] = pasta is not None
    st.session_state["pasta"] = pasta or ""
    st.session_state.pop("arquivo", None)


def _lista_de_buckets(buckets: list[str]) -> None:
    _contexto("s3-buckets")
    ui.trilha([("Buckets", None, None, {})], "s3")
    ui.titulo("Buckets", len(buckets), "Os buckets são contêineres de objetos armazenados no S3, aqui emulado pelo "
              f"floci. Todos aparecem aqui, só para leitura: o <code>{s3.BUCKET}</code> é o do datalake, o "
              f"<code>{recursos.BUCKET}</code> guarda os scripts e workflows dos jobs, e os demais também viram "
              "bancos no Data Catalog.")
    linhas, vazio_datalake = [], s3.BUCKET not in buckets
    for nome in buckets:
        objetos = _listar(nome)
        vazio_datalake = vazio_datalake or (nome == s3.BUCKET and not objetos)
        linhas.append([ui.Link(nome, f"bucket:{nome}", _ir_para, ("", nome)), s3.REGIAO, str(len(objetos)),
                       particoes.tamanho_legivel(sum(o.tamanho for o in objetos)),
                       _uso_do_bucket(nome)])
    if vazio_datalake:
        st.info(f"O bucket {s3.BUCKET} está vazio (ou ainda não existe). Gere os eventos com "
                "`docker compose run --rm app python gerador/gerar_eventos.py` e clique em Recarregar.")
    with ui.painel("buckets", "Buckets", len(buckets)):
        ui.tabela("buckets", [("Nome", 3), ("Região", 1.5), ("Objetos", 1), ("Tamanho", 1), ("Usado por", 1.8)], linhas,
                  localizar=len(linhas) > 8, vazio="Nenhum bucket no floci ainda.")


def _tipo(chave: str) -> str:
    nome = chave.rsplit("/", 1)[-1]
    return particoes.formato_do_arquivo(chave) or (nome.rsplit(".", 1)[-1] if "." in nome else "—")


def _aba_objetos(objetos, con, bucket: str, pasta: str) -> None:
    subpastas, arquivos = particoes.navegar(objetos, pasta)
    linhas = [[ui.Link(f"📁 {sub}/", f"obj:{pasta}{sub}/", _ir_para, (f"{pasta}{sub}/",)), "Pasta", "—", "—"]
              for sub in subpastas]
    linhas += [[ui.Link(f"📄 {o.chave[len(pasta):]}", f"obj:{o.chave}", _escolher, kwargs={"arquivo": o.chave}),
                _tipo(o.chave), o.modificado.strftime("%d/%m/%Y %H:%M:%S") if o.modificado else "—",
                particoes.tamanho_legivel(o.tamanho)] for o in arquivos]
    with ui.painel("objetos", "Objetos", len(linhas),
                   "Objetos são as entidades fundamentais guardadas no S3. Clique numa pasta para entrar ou num arquivo para ver a prévia."):
        ui.tabela("objetos", [("Nome", 5), ("Tipo", 1), ("Última modificação", 2), ("Tamanho", 1)], linhas,
                  localizar=len(linhas) > 8, vazio="Nenhum objeto nesta pasta.")

    arquivo = st.session_state.get("arquivo")
    if arquivo and arquivo.startswith(pasta):
        with ui.painel("previa", f"Prévia: {arquivo.rsplit('/', 1)[-1]}", descricao=f"s3://{bucket}/{arquivo}"):
            if particoes.formato_do_arquivo(arquivo) is None:
                st.info("Prévia só para arquivos .parquet e .jsonl.")
                return
            try:
                st.dataframe(consultas.previa(con.cursor(), s3.raiz(bucket), arquivo), hide_index=True)
                st.caption(f"Primeiras {consultas.LINHAS_PREVIA} linhas, no máximo.")
            except ValueError as erro:
                st.warning(str(erro))
            except duckdb.Error as erro:
                _mostrar_erro("Não consegui ler o arquivo.", erro)


def _aba_particoes(objetos, datasets, con, bucket: str) -> None:
    with ui.painel("particoes", "Partições", descricao="Uma linha por partição: quantos arquivos e quantos bytes ela tem."):
        if not datasets:
            st.info("Ainda não há datasets (pastas com .parquet ou .jsonl) neste bucket.")
            return
        repetidos = {d.prefixo for d in datasets if sum(o.prefixo == d.prefixo for o in datasets) > 1}
        rotulos = {d.nome_view: d.prefixo + (f" ({d.formato})" if d.prefixo in repetidos else "") for d in datasets}
        if st.session_state.get("dataset") not in rotulos:
            st.session_state.pop("dataset", None)        # trocou de bucket: o dataset escolhido antes não existe aqui
        nome = st.selectbox("Dataset", list(rotulos), format_func=rotulos.get, key="dataset")
        dataset = next(d for d in datasets if d.nome_view == nome)
        linhas = particoes.tabela_particoes(objetos, dataset.prefixo, dataset.formato)
        if not linhas:
            st.info("Nenhum arquivo de dados neste dataset.")
            return
        tabela = pd.DataFrame([asdict(l) for l in linhas])
        tabela["tamanho"] = tabela["bytes"].map(particoes.tamanho_legivel)
        st.dataframe(tabela, hide_index=True)
        st.caption(f"{len(linhas)} partição(ões) · {int(tabela['arquivos'].sum())} arquivo(s) · "
                   f"{particoes.tamanho_legivel(int(tabela['bytes'].sum()))}")
        if st.button("Contar linhas por partição", key="contar"):
            campos = [c for c in particoes.CAMPOS if any(getattr(l, c) != particoes.SEM_PARTICAO for l in linhas)]
            leitura = consultas.origem(s3.raiz(bucket), dataset)
            sql = (f'SELECT {", ".join(campos)}, count(*) AS linhas FROM {leitura} GROUP BY ALL ORDER BY ALL'
                   if campos else f'SELECT count(*) AS linhas FROM {leitura}')
            try:
                with st.spinner("Contando linhas… (lê todos os arquivos do dataset)"):
                    contagem = consultas.executar(con.cursor(), sql, consultas.LIMITE_MAXIMO).tabela
                st.dataframe(contagem, hide_index=True)
            except duckdb.Error as erro:
                _mostrar_erro("Não consegui contar.", erro)


def _aba_propriedades(objetos, datasets, bucket: str) -> None:
    with ui.painel("bucket-visao", "Visão geral do bucket"):
        ui.pares({
            "Nome": bucket, "Região": s3.REGIAO, "Endpoint": s3.ENDPOINT, "Objetos": str(len(objetos)),
            "Tamanho total": particoes.tamanho_legivel(sum(o.tamanho for o in objetos)),
            "Datasets (pastas com dados)": str(len(datasets)),
            "Usado por": _uso_do_bucket(bucket),
            "Acesso": "somente leitura",
        })


def _tela_s3() -> None:
    try:
        buckets = _buckets()
        if not st.session_state.get("bucket_aberto"):
            _lista_de_buckets(buckets)
            return
        bucket = st.session_state.get("bucket_sel") or s3.BUCKET
        objetos = _listar(bucket)
    except s3.S3Indisponivel as erro:
        st.error(str(erro))
        return
    _contexto("s3-bucket")
    datasets = particoes.datasets(o.chave for o in objetos)
    con = _conexao_bucket(bucket)
    pasta = st.session_state.get("pasta", "")
    trilha = [("Buckets", "migalha:buckets", _ir_para, {"pasta": None}),
              (bucket, "migalha:", _ir_para, {"pasta": ""})]
    trilha += [(rotulo, f"migalha:{caminho}", _ir_para, {"pasta": caminho}) for rotulo, caminho in particoes.migalhas(pasta)]
    ui.trilha(trilha, "s3")
    ui.titulo(bucket)
    aba_objetos, aba_particoes, aba_propriedades = st.tabs(["Objetos", "Partições", "Propriedades"])
    with aba_objetos:
        _aba_objetos(objetos, con, bucket, pasta)
    with aba_particoes:
        _aba_particoes(objetos, datasets, con, bucket)
    with aba_propriedades:
        _aba_propriedades(objetos, datasets, bucket)


# ---------------------------------------------------------------- Athena ----------------------------------------------------------------

def _abas() -> list[athena.Aba]:
    if "abas" not in st.session_state:
        st.session_state["abas"] = athena.nova_aba([])
        st.session_state["indice_aba"] = 0
    return st.session_state["abas"]


def _aba_ativa() -> athena.Aba:
    return _abas()[st.session_state.get("indice_aba", 0)]


def _chave_sql(aba: athena.Aba) -> str:
    return f"sql:{aba.nome}"


def _por_no_editor(texto: str, substituir: bool = False) -> None:
    aba = _aba_ativa()
    atual = st.session_state.get(_chave_sql(aba), aba.sql)
    aba.sql = texto if substituir else athena.inserir(atual, texto)
    st.session_state[_chave_sql(aba)] = aba.sql


def _nova_aba() -> None:
    st.session_state["abas"] = athena.nova_aba(_abas())
    st.session_state["indice_aba"] = len(st.session_state["abas"]) - 1


def _fechar_aba() -> None:
    abas, indice = athena.fechar_aba(_abas(), st.session_state.get("indice_aba", 0))
    st.session_state["abas"], st.session_state["indice_aba"] = abas, indice


def _trocar_aba() -> None:
    nomes = [a.nome for a in _abas()]
    st.session_state["indice_aba"] = nomes.index(st.session_state["aba_ativa"])


def _abrir_no_athena(sql: str) -> None:
    """Abre uma aba nova no editor com esta SQL e troca para a tela do Athena."""
    _nova_aba()
    _por_no_editor(sql, substituir=True)
    st.session_state["tela"] = TELA_ATHENA


def _arvore(datasets, colunas) -> None:
    with ui.painel("athena-dados", "Dados"):
        st.caption("Fonte de dados: Data Catalog de estudo · floci (S3 local)")
        bancos = glue.bancos(datasets)
        banco = st.selectbox("Banco de dados", list(bancos), key="athena_banco")
        nomes = [d.nome_view for d in bancos.get(banco, []) if d.nome_view in colunas]
        st.markdown(f'<div class="painel-titulo" style="font-size:.9375rem">Tabelas <span class="contador">({len(nomes)})</span></div>',
                    unsafe_allow_html=True)
        for nome in nomes:
            with st.expander(f"▦ {particoes.banco_e_tabela(nome)[1]}"):
                st.button("Inserir no editor", key=f"inserir:{nome}", type="tertiary", on_click=_por_no_editor, args=(nome,))
                for c, t in colunas[nome]:
                    # struct aparece curto; o clique no tipo abre a tipagem interna num overlay
                    with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"arvcol-{nome}-{c}"):
                        st.markdown(f"`{c}`", width="content")
                        ui.tipo(st, c, t, f"arvore-{nome}-{c}")
    with ui.painel("athena-exemplos", "Consultas de exemplo"):
        for titulo, sql in EXEMPLOS.items():
            st.button(titulo, key=f"exemplo:{titulo}", type="tertiary", on_click=_por_no_editor, args=(sql, True))


def _executar(con, aba: athena.Aba, objetos, datasets, limite: int) -> None:
    sql = st.session_state.get(_chave_sql(aba), "")
    aba.sql, aba.limite, aba.erro_original = sql, limite, None
    inicio, quando = time.perf_counter(), datetime.now().strftime("%H:%M:%S")
    try:
        with st.spinner("Executando a consulta…"):
            resultado = consultas.executar(con.cursor(), sql, limite)
        lidos = athena.bytes_lidos(athena.views_usadas(sql, [d.nome_view for d in datasets]), datasets, objetos, sql)
        aba.resultado = resultado
        aba.execucao = athena.Execucao(sql, "Concluída", quando, time.perf_counter() - inicio,
                                       len(resultado.tabela), lidos)
    except consultas.SqlNaoPermitido as erro:
        aba.resultado = None
        aba.execucao = athena.Execucao(sql, "Falhou", quando, time.perf_counter() - inicio, 0, 0, str(erro))
    except duckdb.Error as erro:
        aba.resultado = None
        aba.execucao = athena.Execucao(sql, "Falhou", quando, time.perf_counter() - inicio, 0, 0,
                                       consultas.explicar_erro(erro))
        aba.erro_original = str(erro)
    st.session_state["historico"] = athena.registrar(st.session_state.get("historico", []), aba.execucao)


def _resultados(aba: athena.Aba) -> None:
    if aba.execucao is None:
        st.markdown('<div class="tab-vazio">Execute uma consulta para ver os resultados aqui.</div>', unsafe_allow_html=True)
        return
    if aba.execucao.status == "Concluída":
        st.success(athena.resumo(aba.execucao))
    else:
        st.error(athena.resumo(aba.execucao))
        if aba.erro_original:
            st.caption(f"Mensagem original do DuckDB: {aba.erro_original}")
        return
    resultado = aba.resultado
    if resultado.cortado:
        st.warning(f"Resultado cortado em {int(aba.limite)} linhas. Aumente o limite ou filtre a consulta.")
    st.dataframe(resultado.tabela, hide_index=True)
    st.download_button("Baixar resultados (CSV)", resultado.tabela.to_csv(index=False).encode("utf-8"),
                       file_name="resultado.csv", mime="text/csv", key="baixar", on_click="ignore")


def _recentes() -> None:
    historico = st.session_state.get("historico", [])
    if not historico:
        st.markdown('<div class="tab-vazio">Nenhuma consulta executada nesta sessão do navegador.</div>',
                    unsafe_allow_html=True)
        return
    st.dataframe(pd.DataFrame([{
        "Hora": e.quando, "Status": e.status, "Tempo (s)": round(e.segundos, 2), "Linhas": e.linhas,
        "Dados lidos (estimado)": particoes.tamanho_legivel(e.bytes), "Consulta": " ".join(e.sql.split())[:120],
    } for e in historico]), hide_index=True)
    st.caption("Abrir uma consulta no editor:")
    for i, e in enumerate(historico):
        st.button(f"{e.quando} · {' '.join(e.sql.split())[:80]}", key=f"abrir_hist:{i}", type="tertiary",
                  on_click=_por_no_editor, args=(e.sql, True))
    st.caption("O histórico vale enquanto esta aba do navegador estiver aberta; recarregar a página zera.")


def _tela_athena(objetos, datasets, con, colunas) -> None:
    _contexto("athena")
    ui.trilha([("Athena", None, None, {}), ("Editor de consultas", None, None, {})], "athena")
    ui.titulo("Editor de consultas")
    esquerda, direita = st.columns([1, 3], gap="medium")
    with esquerda:
        _arvore(datasets, colunas)
    with direita:
        abas = _abas()
        nomes = [a.nome for a in abas]
        aba = _aba_ativa()
        st.session_state["aba_ativa"] = aba.nome
        with ui.painel("athena-editor"):
            seletor, mais, fechar = st.columns([10, 1, 1], vertical_alignment="center")
            seletor.radio("Consultas abertas", nomes, key="aba_ativa", horizontal=True,
                          label_visibility="collapsed", on_change=_trocar_aba)
            mais.button("＋", key="nova_aba", help="Nova consulta", on_click=_nova_aba)
            fechar.button("✕", key="fechar_aba", help="Fechar esta consulta", on_click=_fechar_aba,
                          disabled=len(abas) == 1)
            if _chave_sql(aba) not in st.session_state:
                st.session_state[_chave_sql(aba)] = aba.sql
            st.text_area("Consulta", key=_chave_sql(aba), height=220, label_visibility="collapsed",
                         placeholder="SELECT * FROM silver.eventos LIMIT 10")
            executar, limite_col, _ = st.columns([1, 2, 3], vertical_alignment="bottom")
            limite = limite_col.number_input("Limite de linhas", min_value=1, max_value=consultas.LIMITE_MAXIMO,
                                             value=aba.limite, step=100, key=f"limite:{aba.nome}")
            if executar.button("Executar", key="executar", type="primary"):
                _executar(con, aba, objetos, datasets, limite)
        with ui.painel("athena-resultados"):
            aba_resultados, aba_recentes = st.tabs(["Resultados", "Consultas recentes"])
            with aba_resultados:
                _resultados(aba)
            with aba_recentes:
                _recentes()


# ------------------------------------------------------------ Glue · Data Catalog ------------------------------------------------------------

def _tela_catalogo(objetos, datasets, colunas) -> None:
    bancos = glue.bancos(datasets)
    banco = st.session_state.get("cat_banco")
    tabela = st.session_state.get("cat_tabela")
    if banco not in bancos:
        banco, tabela = None, None
    elif tabela not in {d.nome_view for d in bancos[banco]}:
        tabela = None                               # sumiu ou ficou ilegível depois do Recarregar: volta ao banco
    trilha = [("Glue", None, None, {}), ("Data Catalog", "cat:inicio", _escolher, {"cat_banco": None, "cat_tabela": None})]
    if banco:
        trilha.append((banco, "cat:banco", _escolher, {"cat_tabela": None}))
    if tabela:
        trilha.append((particoes.banco_e_tabela(tabela)[1], None, None, {}))
    ui.trilha(trilha if banco else trilha[:1] + [("Data Catalog", None, None, {})], "catalogo")

    if not banco:
        _contexto("catalogo-bancos")
        ui.titulo("Bancos de dados", len(bancos), "No Glue, um banco de dados agrupa tabelas. Aqui há um por camada do "
                  f"medalhão, no bucket <code>{s3.BUCKET}</code>, e um para cada outro bucket do floci, com o nome dele.")
        with ui.painel("bancos", "Bancos de dados", len(bancos)):
            ui.tabela("bancos", [("Nome", 2), ("Tabelas", 1), ("Localização", 3), ("Bucket", 2)], [
                [ui.Link(nome, f"banco:{nome}", _escolher, kwargs={"cat_banco": nome, "cat_tabela": None}),
                 str(len(tabelas)), glue.local_do_banco(tabelas, s3.BUCKET), tabelas[0].bucket or s3.BUCKET]
                for nome, tabelas in bancos.items()], localizar=len(bancos) > 8)
        return

    if not tabela:
        _contexto("catalogo-tabelas")
        ui.titulo(banco, descricao=f"Banco de dados · {glue.local_do_banco(bancos[banco], s3.BUCKET)}")
        linhas = [[ui.Link(particoes.banco_e_tabela(d.nome_view)[1], f"tabela:{d.nome_view}", _escolher,
                           kwargs={"cat_tabela": d.nome_view}),
                   "Parquet" if d.formato == "parquet" else "JSON", glue.localizacao(d, s3.BUCKET),
                   str(len(particoes.tabela_particoes(objetos, d.prefixo, d.formato))),
                   str(len(colunas.get(d.nome_view, [])))] for d in bancos[banco]]
        with ui.painel("tabelas", "Tabelas", len(linhas)):
            ui.tabela("tabelas", [("Nome", 3), ("Formato", 1), ("Localização", 4), ("Partições", 1), ("Colunas", 1)],
                      linhas, localizar=len(linhas) > 8)
        return

    _contexto("catalogo-tabela")
    dataset = next(d for d in datasets if d.nome_view == tabela)
    chaves = glue.chaves_particao(dataset, objetos)
    linhas_part = particoes.tabela_particoes(objetos, dataset.prefixo, dataset.formato)
    titulo, botao = st.columns([4, 1], vertical_alignment="center")
    with titulo:
        ui.titulo(tabela)
    botao.button("Consultar no Athena", key="consultar_athena", type="primary",
                 on_click=_abrir_no_athena, args=(f"SELECT * FROM {tabela} LIMIT 10",))
    with ui.painel("tabela-visao", "Visão geral da tabela"):
        ui.pares({"Banco de dados": banco, "Localização": glue.localizacao(dataset, s3.BUCKET),
                  "Classificação": "parquet" if dataset.formato == "parquet" else "json",
                  "Chaves de partição": ", ".join(chaves) or "—", "Arquivos": str(sum(l.arquivos for l in linhas_part)),
                  "Nome no Athena": tabela})
    aba_esquema, aba_particoes = st.tabs(["Esquema", "Partições"])
    with aba_esquema:
        # struct aparece curto; o clique no tipo abre a tipagem interna num overlay
        ui.tabela("esquema", [("Coluna", 2), ("Tipo", 2), ("Chave de partição", 1)],
                  [[c, ui.Tipo(c, t, f"esquema-{tabela}-{c}"), "sim" if c in chaves else ""]
                   for c, t in colunas.get(tabela, [])], localizar=len(colunas.get(tabela, [])) > 8)
    with aba_particoes:
        if chaves:
            st.caption(f"Chaves de partição: {', '.join(chaves)}")
            st.dataframe(pd.DataFrame([{**{c: getattr(l, c) for c in chaves}, "arquivos": l.arquivos,
                                        "tamanho": particoes.tamanho_legivel(l.bytes)} for l in linhas_part]),
                         hide_index=True)
        else:
            st.info("Tabela sem partições: todos os arquivos ficam direto na pasta.")


# -------------------------------------------------------------- Glue · Jobs ETL --------------------------------------------------------------

def _pastas_jobs() -> tuple[Path, Path]:
    """(pasta local dos jobs, a que o Sincronizar envia ao floci; pasta das execuções)."""
    jobs = Path(os.environ.get("EXPLORADOR_JOBS", "pipeline"))
    execucoes = Path(os.environ.get("EXPLORADOR_EXECUCOES", "/tmp/explorador-execucoes"))
    return (jobs if jobs.is_absolute() else RAIZ / jobs), execucoes


def _comum() -> Path:
    """A biblioteca dos jobs: sempre a do pipeline/ (a solução do professor só carrega esta)."""
    return RAIZ / "pipeline" / "comum.py"


def _quando(instante: float) -> str:
    return datetime.fromtimestamp(instante).strftime("%d/%m/%Y %H:%M:%S")


def _relativo(caminho: Path) -> str:
    return str(caminho.relative_to(RAIZ)) if caminho.is_relative_to(RAIZ) else str(caminho)


def _copia_dos_scripts(pasta_exec: Path, nome: str) -> Path:
    """Baixa os scripts do floci para uma pasta só desta execução, como o Glue faz antes de rodar.

    A execução apaga a cópia ao terminar; as esquecidas (processo morto no meio) saem depois de um dia."""
    glue.limpar_copias(pasta_exec / "scripts")
    return recursos.baixar_scripts(pasta_exec / "scripts" / f"{nome}-{time.time_ns()}")


def _sincronizar(pasta_jobs: Path) -> None:
    try:
        resumo = recursos.sincronizar(pasta_jobs, _comum())
    except s3.S3Indisponivel as erro:
        st.session_state["sync_aviso"] = ("⚠️", str(erro))
        return
    st.cache_data.clear()                           # a tela S3 passa a ver o bucket de recursos atualizado
    if resumo.vazio:
        st.session_state["sync_aviso"] = ("✅", "Já estava tudo sincronizado com o floci.")
    else:
        st.session_state["sync_aviso"] = ("✅", f"Sincronizado: {len(resumo.enviados)} enviado(s) e "
                                               f"{len(resumo.removidos)} removido(s) do floci.")


def _botao_sync(alvo, pasta_jobs: Path, chave: str) -> None:
    """Só o botão; a explicação e o que está pendente ficam no overlay (passe o mouse ou foque com o Tab)."""
    try:
        plano = recursos.pendencias(pasta_jobs, _comum())
        pendente = (f"Agora: {len(plano.enviados)} arquivo(s) para enviar e {len(plano.removidos)} para remover."
                    if not plano.vazio else "Agora: tudo sincronizado.")
    except s3.S3Indisponivel as erro:
        plano, pendente = None, str(erro)
    explicacao = (f"Como no Glue, os jobs e workflows rodam a partir do S3: aqui, do bucket {recursos.BUCKET} do floci. "
                  f"Este botão envia para lá os scripts .py de {_relativo(pasta_jobs)}/ e os workflows de "
                  f"{_relativo(pasta_jobs)}/workflows/: o que é novo ou mudou vai, e o que você apagou sai. "
                  f"Clique depois de criar ou editar um arquivo.\n\n{pendente}")
    alvo.button("⟳ Sincronizar", key=f"sincronizar-{chave}", on_click=_sincronizar, args=(pasta_jobs,),
                type="primary" if plano is not None and not plano.vazio else "secondary",
                disabled=plano is None, help=explicacao)
    if aviso := st.session_state.pop("sync_aviso", None):
        st.toast(aviso[1], icon=aviso[0])


def _executar_job(nome: str, pasta: Path) -> None:
    if glue.em_execucao(pasta, nome):
        return
    copia = _copia_dos_scripts(pasta, nome)
    script = copia / f"{nome}.py"
    if not script.exists():
        shutil.rmtree(copia, ignore_errors=True)
        st.session_state["job_erro"] = f"O script {nome}.py não está mais no floci. Clique em Sincronizar."
        return
    st.session_state["execucao_sel"] = glue.iniciar(glue.Job(nome, script), pasta, RAIZ, descartar=copia)


def _painel_execucoes(nome: str, pasta: Path, rodando_antes: bool = False) -> None:
    if rodando_antes and not glue.em_execucao(pasta, nome):
        st.rerun()                                  # terminou: redesenha a página toda (reativa o botão Executar)
    execucoes = glue.execucoes(pasta, nome)
    with ui.painel("execucoes", "Execuções", len(execucoes)):
        ui.tabela("execucoes", [("Execução", 2.6), ("Status", 1.3), ("Início", 1.8), ("Duração", 1), ("Código de saída", 1.1),
                                ("Origem", 2)],
                  [[e.id, ui.selo(e.status), _quando(e.inicio), _duracao(e.duracao),
                    "—" if e.codigo is None else str(e.codigo), e.origem] for e in execucoes],
                  vazio="Nenhuma execução ainda. Clique em Executar.")
    if not execucoes:
        return
    ids = [e.id for e in execucoes]
    if st.session_state.get("execucao_sel") not in ids:
        st.session_state["execucao_sel"] = ids[0]
    with ui.painel("log", "Log"):
        escolhida = st.selectbox("Execução", ids, key="execucao_sel")
        st.code(glue.log(pasta, escolhida, ultimas=300) or "(sem saída ainda)", language="text")


def _tela_jobs() -> None:
    pasta_jobs, pasta_exec = _pastas_jobs()
    try:
        jobs = recursos.listar_jobs()
    except s3.S3Indisponivel as erro:
        st.error(str(erro))
        return
    nome = st.session_state.get("job_sel") if st.session_state.get("job_sel") in jobs else None

    if nome is None:
        _contexto("jobs-lista")
        ui.trilha([("Glue", None, None, {}), ("Jobs ETL", None, None, {})], "jobs")
        titulo, botao = st.columns([4, 1], vertical_alignment="center")
        with titulo:
            ui.titulo("Jobs", len(jobs), f"Os scripts guardados no floci, em <code>s3://{recursos.BUCKET}/scripts/</code>, "
                      "como no Glue. Executar aqui é como rodar <code>docker compose run --rm app python "
                      "&lt;script&gt;</code>, mas com a cópia que está no floci.")
        _botao_sync(botao, pasta_jobs, "jobs")
        linhas = []
        for j in jobs:
            ultima = next(iter(glue.execucoes(pasta_exec, j)), None)
            linhas.append([ui.Link(j, f"job:{j}", _escolher, kwargs={"job_sel": j}), "Spark",
                           recursos.caminho(f"{recursos.SCRIPTS}{j}.py"), ui.selo(ultima.status) if ultima else "—",
                           _quando(ultima.inicio) if ultima else "—"])
        with ui.painel("jobs", "Jobs", len(jobs)):
            ui.tabela("jobs", [("Nome do job", 2.6), ("Tipo", 0.6), ("Script", 3.6), ("Última execução", 1.4), ("Início", 1.6)],
                      linhas, localizar=len(linhas) > 8,
                      vazio=f"Nenhum job no floci ainda. Crie os scripts em {_relativo(pasta_jobs)}/ "
                            "(por exemplo bronze.py) e clique em Sincronizar.")
        return

    _contexto("jobs-detalhe")
    ui.trilha([("Glue", None, None, {}), ("Jobs ETL", "jobs:inicio", _escolher, {"job_sel": None}),
               (nome, None, None, {})], "jobs")
    rodando = glue.em_execucao(pasta_exec, nome)
    titulo, botao = st.columns([4, 1], vertical_alignment="center")
    with titulo:
        ui.titulo(nome, descricao="Tipo: Spark (PySpark 4.2.0, local) · o script vem do floci e roda no contêiner "
                  "do explorador · um job por vez")
    botao.button("Executar", key="executar_job", type="primary", disabled=rodando,
                 on_click=_executar_job, args=(nome, pasta_exec))
    if mensagem := st.session_state.pop("job_erro", None):
        st.error(mensagem)
    aba_exec, aba_script = st.tabs(["Execuções", "Script"])
    with aba_exec:
        # enquanto há execução em andamento, o painel se atualiza sozinho a cada 3 s
        st.fragment(run_every=3 if rodando else None)(_painel_execucoes)(nome, pasta_exec, rodando)
    with aba_script:
        chave = f"{recursos.SCRIPTS}{nome}.py"
        with ui.painel("script", recursos.caminho(chave),
                       descricao="A cópia que está no floci, que é a que roda. Edite o arquivo local no seu editor "
                                 "e clique em Sincronizar."):
            st.code(recursos.ler(chave), language="python")


# ------------------------------------------------------------- Glue · Workflows -------------------------------------------------------------

NOVO = "__novo__"


def _abrir_form(wf: workflows.Workflow | None, disponiveis: list[str]) -> None:
    """Prepara o formulário: os widgets leem estes valores quando a página redesenhar."""
    for chave in [k for k in st.session_state if str(k).startswith("wf_form_")]:
        del st.session_state[chave]
    st.session_state["wf_editar"] = wf.nome if wf else NOVO
    st.session_state["wf_form_nome"] = wf.nome if wf else ""
    st.session_state["wf_form_descricao"] = wf.descricao if wf else ""
    st.session_state["wf_form_paralelo"] = wf.paralelo if wf else 2
    jobs = [e.job for e in wf.etapas if e.job in disponiveis] if wf else []
    st.session_state["wf_form_jobs"] = jobs
    for e in (wf.etapas if wf else ()):
        if e.job in jobs:
            st.session_state[f"wf_form_dep:{e.job}"] = [d for d in e.depende_de if d in jobs]


def _workflow_do_form() -> workflows.Workflow:
    escolhidos = list(st.session_state.get("wf_form_jobs", []))
    etapas = tuple(workflows.Etapa(j, tuple(d for d in st.session_state.get(f"wf_form_dep:{j}", []) if d in escolhidos))
                   for j in escolhidos)
    return workflows.Workflow(st.session_state.get("wf_form_nome", "").strip(),
                              st.session_state.get("wf_form_descricao", "").strip(),
                              int(st.session_state.get("wf_form_paralelo", 2)), etapas)


def _encadear() -> None:
    """Atalho: cada job depende do anterior, em sequência, na ordem em que foram escolhidos."""
    escolhidos = list(st.session_state.get("wf_form_jobs", []))
    for anterior, job in zip([None] + escolhidos, escolhidos):
        st.session_state[f"wf_form_dep:{job}"] = [anterior] if anterior else []


def _salvar_form(pasta_jobs: Path, disponiveis: set[str], editando: bool) -> None:
    wf = _workflow_do_form()
    try:
        workflows.validar(wf, disponiveis)
        if not editando and wf.nome in {w.nome for w in recursos.listar_workflows()[0]}:
            raise workflows.WorkflowInvalido(f"Já existe um workflow chamado {wf.nome}. Escolha outro nome.")
        no_floci = recursos.salvar_workflow(wf)
    except workflows.WorkflowInvalido as erro:
        st.session_state["wf_form_erro"] = str(erro)
        return
    except s3.S3Indisponivel as erro:
        st.session_state["wf_form_erro"] = str(erro)
        return
    # a cópia local mantém o workflow no git e faz o próximo Sincronizar não apagá-lo do floci
    local = workflows.salvar(pasta_jobs, wf)
    st.session_state.update(wf_editar=None, wf_sel=wf.nome, wf_exec_sel=None,
                            wf_flash=f"Workflow {wf.nome} salvo no floci ({no_floci}) e na pasta local ({_relativo(local)}).")


def _excluir_workflow(pasta_jobs: Path, nome: str) -> None:
    try:
        recursos.excluir_workflow(nome)
    except s3.S3Indisponivel as erro:
        st.session_state["wf_flash_erro"] = f"Não excluí o workflow {nome}: {erro}"
        return
    workflows.excluir(pasta_jobs, nome)
    st.session_state.update(wf_sel=None, wf_flash=f"Workflow {nome} excluído do floci e da pasta local. "
                                                  "O histórico de execuções continua guardado.")


def _executar_workflow(wf: workflows.Workflow, pasta_exec: Path, disponiveis: set[str]) -> None:
    try:
        workflows.validar(wf, disponiveis)
    except workflows.WorkflowInvalido as erro:
        st.session_state["wf_flash_erro"] = f"Não dá para executar: {erro}"
        return
    if not workflows.em_execucao(pasta_exec, wf.nome):
        copia = _copia_dos_scripts(pasta_exec, f"workflow-{wf.nome}")   # os jobs rodam com a cópia do floci
        st.session_state["wf_exec_sel"] = workflows.iniciar(wf, copia, pasta_exec, RAIZ, descartar=True)


def _parar_workflow(pasta_exec: Path, nome: str) -> None:
    for e in workflows.execucoes(pasta_exec, nome):
        if e.status == workflows.EM_EXECUCAO:
            workflows.parar(pasta_exec, e.id)


def _avisos_workflow() -> None:
    if mensagem := st.session_state.pop("wf_flash", None):
        st.success(mensagem)
    if mensagem := st.session_state.pop("wf_flash_erro", None):
        st.error(mensagem)


def _duracao(segundos: float | None) -> str:
    return "—" if segundos is None else f"{segundos:.1f} s".replace(".", ",")


def _painel_execucao_workflow(wf: workflows.Workflow, pasta_exec: Path, rodando_antes: bool = False) -> None:
    execucoes = workflows.execucoes(pasta_exec, wf.nome)
    if rodando_antes and not any(e.status == workflows.EM_EXECUCAO for e in execucoes):
        st.rerun()                                  # terminou: redesenha a página toda (reativa o botão Executar)
    ids = [e.id for e in execucoes]
    if ids and st.session_state.get("wf_exec_sel") not in ids:
        st.session_state["wf_exec_sel"] = ids[0]
    escolhida = next((e for e in execucoes if e.id == st.session_state.get("wf_exec_sel")), None)
    grafo = escolhida.workflow if escolhida else wf     # a execução guarda o workflow do jeito que ele estava
    status = {j: s.status for j, s in escolhida.etapas.items()} if escolhida else {}

    with ui.painel("grafo", "Grafo", descricao="Cada seta quer dizer \"roda depois de\". As cores mostram o status "
                   "de cada job na execução escolhida."):
        if escolhida:
            por_id = {e.id: e for e in execucoes}
            st.selectbox("Execução", ids, key="wf_exec_sel", format_func=lambda i: f"{i} · {por_id[i].status}")
            st.markdown(f"{ui.selo(escolhida.status).conteudo} · início {_quando(escolhida.inicio)} · "
                        f"duração {_duracao(escolhida.duracao)}", unsafe_allow_html=True)
        else:
            st.caption("Nenhuma execução ainda: o grafo aparece sem cores. Clique em Executar.")
        st.graphviz_chart(workflows.dot(grafo, status), width="stretch")

    linhas = []
    for etapa in grafo.etapas:
        s = escolhida.etapas.get(etapa.job) if escolhida else None
        linhas.append([etapa.job, ", ".join(etapa.depende_de) or "—", ui.selo(s.status) if s else "—",
                       _quando(s.inicio) if s and s.inicio else "—", _duracao(s.duracao) if s else "—"])
    with ui.painel("etapas", "Etapas", len(linhas)):
        ui.tabela("etapas", [("Job", 2.2), ("Depende de", 2.4), ("Status", 1.4), ("Início", 1.8), ("Duração", 1)], linhas)
        if not escolhida:
            return
        for nome, s in escolhida.etapas.items():
            if s.erro:
                st.error(f"{nome}: {s.erro}")
        com_log = [j for j, s in escolhida.etapas.items() if s.execucao]
        if com_log:
            if st.session_state.get("wf_log_sel") not in com_log:
                falhou = [j for j in com_log if escolhida.etapas[j].status == workflows.FALHOU]
                st.session_state["wf_log_sel"] = (falhou or com_log)[-1]
            etapa = st.selectbox("Log da etapa", com_log, key="wf_log_sel")
            st.code(glue.log(pasta_exec, escolhida.etapas[etapa].execucao, ultimas=200) or "(sem saída ainda)",
                    language="text")


def _form_workflow(pasta_jobs: Path, disponiveis: list[str]) -> None:
    _contexto("workflows-form")
    editando = st.session_state["wf_editar"] != NOVO
    acao = "Editar workflow" if editando else "Criar workflow"
    ui.trilha([("Glue", None, None, {}), ("Workflows", "wf:voltar", _escolher, {"wf_editar": None}),
               (acao, None, None, {})], "workflows")
    ui.titulo(acao, descricao="Escolha os jobs e diga de quem cada um depende. Jobs sem dependência entre si "
              "podem rodar ao mesmo tempo.")
    if not disponiveis:
        st.info(f"Ainda não há jobs no floci. Crie os scripts em {_relativo(pasta_jobs)}/ e clique em Sincronizar, "
                "na lista de Jobs ETL ou de Workflows.")
    esquerda, direita = st.columns([1, 1], gap="large")
    with esquerda:
        with ui.painel("propriedades", "Propriedades"):
            st.text_input("Nome", key="wf_form_nome", disabled=editando, placeholder="medalhao",
                          help="Letras minúsculas, números, _ ou -. Vira o arquivo workflows/<nome>.json.")
            st.text_input("Descrição", key="wf_form_descricao", placeholder="Para que serve este workflow")
            st.number_input("Jobs ao mesmo tempo", min_value=1, max_value=workflows.PARALELO_MAX, key="wf_form_paralelo",
                            help="Cada job abre um Spark. Mais de 2 ao mesmo tempo pode faltar memória no contêiner.")
            st.multiselect("Jobs do workflow", disponiveis, key="wf_form_jobs", placeholder="Escolha os jobs")
        escolhidos = list(st.session_state.get("wf_form_jobs", []))
        with ui.painel("dependencias", "Dependências", descricao="Para cada job, de quais outros ele depende."):
            if not escolhidos:
                st.caption("Escolha os jobs acima.")
            for job in escolhidos:
                outros = [o for o in escolhidos if o != job]
                chave = f"wf_form_dep:{job}"
                if chave in st.session_state:
                    st.session_state[chave] = [d for d in st.session_state[chave] if d in outros]
                st.multiselect(f"{job} depende de", outros, key=chave, placeholder="nenhum: começa logo")
            if len(escolhidos) > 1:
                st.button("Encadear em sequência (cada job depende do anterior)", key="wf_encadear", type="tertiary",
                          on_click=_encadear)
    with direita:
        with ui.painel("previa", "Prévia"):
            wf = _workflow_do_form()
            if wf.etapas:
                try:                                # sem nome ainda: valida o resto com um nome provisório
                    workflows.validar(replace(wf, nome=wf.nome or "rascunho"), set(disponiveis))
                    st.caption(" → ".join(" + ".join(c) for c in workflows.niveis(wf)))
                except workflows.WorkflowInvalido as erro:
                    st.warning(str(erro))
                st.graphviz_chart(workflows.dot(wf), width="stretch")
            else:
                st.caption("O grafo aparece aqui quando você escolher os jobs.")
    if erro := st.session_state.pop("wf_form_erro", None):
        st.error(erro)
    with st.container(horizontal=True):
        st.button("Cancelar", key="wf_cancelar", on_click=_escolher, kwargs={"wf_editar": None})
        st.button("Salvar workflow", key="wf_salvar", type="primary", on_click=_salvar_form,
                  args=(pasta_jobs, set(disponiveis), editando))


def _tela_workflows() -> None:
    pasta_jobs, pasta_exec = _pastas_jobs()
    try:
        disponiveis = recursos.listar_jobs()       # só os jobs que estão no floci entram num workflow
        lista, avisos = recursos.listar_workflows()
    except s3.S3Indisponivel as erro:
        st.error(str(erro))
        return
    if st.session_state.get("wf_editar"):
        _form_workflow(pasta_jobs, disponiveis)
        return
    wf = next((w for w in lista if w.nome == st.session_state.get("wf_sel")), None)

    if wf is None:
        _contexto("workflows-lista")
        ui.trilha([("Glue", None, None, {}), ("Workflows", None, None, {})], "workflows")
        titulo, botao = st.columns([3, 2], vertical_alignment="center")
        with titulo:
            ui.titulo("Workflows", len(lista), "Grafos de jobs guardados no floci, em "
                      f"<code>s3://{recursos.BUCKET}/workflows/</code>. Executar um workflow é como rodar os jobs um "
                      "depois do outro no terminal, mas seguindo as dependências do grafo.")
        with botao, st.container(horizontal=True, horizontal_alignment="right"):
            _botao_sync(st, pasta_jobs, "workflows")
            st.button("Criar workflow", key="criar_workflow", type="primary", on_click=_abrir_form,
                      args=(None, disponiveis))
        _avisos_workflow()
        for aviso in avisos:
            st.warning(aviso)
        linhas = []
        for w in lista:
            ultima = next(iter(workflows.execucoes(pasta_exec, w.nome)), None)
            linhas.append([ui.Link(w.nome, f"wf:{w.nome}", _escolher, kwargs={"wf_sel": w.nome, "wf_exec_sel": None}),
                           w.descricao or "—", str(len(w.etapas)), ui.selo(ultima.status) if ultima else "—",
                           _quando(ultima.inicio) if ultima else "—"])
        with ui.painel("workflows", "Workflows", len(lista)):
            ui.tabela("workflows", [("Nome", 2), ("Descrição", 3.2), ("Jobs", 0.6), ("Última execução", 1.4),
                                    ("Início", 1.6)], linhas, localizar=len(linhas) > 8,
                      vazio="Nenhum workflow ainda. Clique em Criar workflow.")
        return

    _contexto("workflows-detalhe")
    ui.trilha([("Glue", None, None, {}), ("Workflows", "wf:inicio", _escolher, {"wf_sel": None}),
               (wf.nome, None, None, {})], "workflows")
    rodando = workflows.em_execucao(pasta_exec, wf.nome)
    titulo, acoes = st.columns([3, 2], vertical_alignment="center")
    with titulo:
        ui.titulo(wf.nome, descricao=f"{html.escape(wf.descricao) + ' · ' if wf.descricao else ''}"
                  f"{len(wf.etapas)} jobs · até {wf.paralelo} ao mesmo tempo")
    with acoes, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center"):
        st.button("Editar", key="editar_workflow", disabled=rodando, on_click=_abrir_form, args=(wf, disponiveis))
        with st.popover("Excluir", disabled=rodando, key="excluir_menu"):
            st.markdown(f"Excluir o workflow **{wf.nome}**? O arquivo .json é apagado; os jobs e o histórico de "
                        "execuções continuam.")
            st.button("Excluir de vez", key="excluir_workflow", type="primary", on_click=_excluir_workflow,
                      args=(pasta_jobs, wf.nome))
        if rodando:
            st.button("Parar", key="parar_workflow", on_click=_parar_workflow, args=(pasta_exec, wf.nome),
                      help="Não começa jobs novos; os que já rodam terminam.")
        st.button("Executar", key="executar_workflow", type="primary", disabled=rodando, on_click=_executar_workflow,
                  args=(wf, pasta_exec, set(disponiveis)))
    _avisos_workflow()
    aba_execucao, aba_historico, aba_definicao = st.tabs(["Execução", "Histórico", "Definição"])
    with aba_execucao:
        # enquanto o workflow roda, o grafo e as etapas se atualizam sozinhos a cada 2 s
        st.fragment(run_every=2 if rodando else None)(_painel_execucao_workflow)(wf, pasta_exec, rodando)
    with aba_historico:
        execucoes = workflows.execucoes(pasta_exec, wf.nome)
        with ui.painel("historico", "Execuções", len(execucoes),
                       "Clique numa execução para vê-la no grafo da aba Execução."):
            ui.tabela("historico", [("Execução", 3), ("Status", 1.4), ("Início", 1.8), ("Duração", 1),
                                    ("Jobs com sucesso", 1.2)],
                      [[ui.Link(e.id, f"wfexec:{e.id}", _escolher, kwargs={"wf_exec_sel": e.id}), ui.selo(e.status),
                        _quando(e.inicio), _duracao(e.duracao),
                        f"{sum(s.status == workflows.SUCESSO for s in e.etapas.values())} de {len(e.etapas)}"]
                       for e in execucoes], vazio="Nenhuma execução ainda. Clique em Executar.")
    with aba_definicao:
        arquivo = workflows.pasta_definicoes(pasta_jobs) / f"{wf.nome}.json"
        with ui.painel("definicao", recursos.caminho(f"{recursos.WORKFLOWS}{wf.nome}.json"),
                       descricao=f"A definição que está no floci. A cópia local fica em <code>{_relativo(arquivo)}</code>."):
            st.code(json.dumps(wf.para_dict(), ensure_ascii=False, indent=2), language="json")
            st.caption("Para rodar a cópia local pelo terminal, sem o explorador:")
            st.code(f"docker compose run --rm app python -m explorador.workflows {_relativo(arquivo)}", language="bash")


# --------------------------------------------------------------- Tutorial ---------------------------------------------------------------

def _arquivo_preferencias() -> Path:
    return Path(os.environ.get("EXPLORADOR_PREFERENCIAS", RAIZ / ".explorador" / "preferencias.json"))


def _salvas() -> dict:
    return preferencias.carregar(_arquivo_preferencias())


def _atuais() -> dict:
    """O que está valendo nesta sessão: o valor dos widgets `pref_*`, ou o salvo para os que ainda não existem."""
    return {k: st.session_state.get(f"pref_{k}", v) for k, v in _salvas().items()}


def _salvar_preferencia() -> None:
    atuais = _atuais()
    if atuais != _salvas():                                                  # só grava quando muda
        preferencias.salvar(_arquivo_preferencias(), atuais)


def _desligar_tutorial() -> None:
    st.session_state["pref_tutorial"] = False
    _salvar_preferencia()


def _restaurar_acessibilidade() -> None:
    for chave, valor in preferencias.PADRAO.items():
        if chave != "tutorial":
            st.session_state[f"pref_{chave}"] = valor
    _salvar_preferencia()


def _inicial(chave: str, salvas: dict, parametro: str = "value") -> dict:
    # o valor inicial vem do arquivo; depois, o próprio widget guarda o estado da sessão
    if f"pref_{chave}" in st.session_state:
        return {}
    valor = salvas[chave]
    return {parametro: preferencias.TAMANHOS.index(valor) if parametro == "index" else valor}


def _abrir_tour() -> None:
    # um número novo a cada clique, único também entre sessões: o navegador guarda o último que já abriu
    # (tour-forca) e um contador que recomeça em 1 depois de recarregar a página seria confundido com ele
    st.session_state["tour_forcar"] = time.time_ns()


def _contexto(nome: str) -> None:
    """Cada tela diz qual roteiro do tutorial vale para ela."""
    st.session_state["contexto_tour"] = nome


def _mostrar_tour() -> None:
    contexto = st.session_state.get("contexto_tour")
    if not contexto:
        return
    ligado = bool(st.session_state.get("pref_tutorial"))
    forcar = st.session_state.get("tour_forcar", 0)
    if ligado or forcar:
        ui.tour(contexto, tutorial.roteiro(contexto), auto=ligado, forcar=forcar)


# ---------------------------------------------------------------- página ----------------------------------------------------------------

TAMANHO_ROTULO = {100: "A", 115: "A+", 130: "A++"}


def _barra_flutuante(salvas: dict) -> None:
    """Três botões redondos no canto inferior direito: ⬆ topo (só depois de rolar), 🎓 tutorial desta tela
    e ♿, um menu com a chave do tutorial e as opções de acessibilidade."""
    with st.container(key="dock"):
        st.button("⬆", key="topo", help="Voltar ao topo da página")
        st.button("🎓", key="tour-abrir", on_click=_abrir_tour,
                  help="Abrir o tutorial desta tela: mostra, num modal, para que serve cada parte.")
        with st.popover("♿", help="Tutorial e acessibilidade"):
            st.markdown("**Tutorial**")
            st.toggle("Mostrar tutorial", key="pref_tutorial", on_change=_salvar_preferencia, **_inicial("tutorial", salvas),
                      help="Ligado, o tutorial abre sozinho na primeira visita a cada tela. Desligado, só pelo botão 🎓.")
            st.markdown("**Acessibilidade**")
            st.radio("Tamanho do texto", preferencias.TAMANHOS, key="pref_texto", horizontal=True,
                     format_func=TAMANHO_ROTULO.get, on_change=_salvar_preferencia,
                     **_inicial("texto", salvas, "index"))
            st.toggle("Alto contraste", key="pref_contraste", on_change=_salvar_preferencia,
                      **_inicial("contraste", salvas), help="Textos e bordas mais escuros.")
            st.toggle("Sublinhar links", key="pref_sublinhar", on_change=_salvar_preferencia,
                      **_inicial("sublinhar", salvas), help="Deixa claro o que é clicável sem depender da cor.")
            st.toggle("Mais espaço entre letras e linhas", key="pref_espacamento", on_change=_salvar_preferencia,
                      **_inicial("espacamento", salvas), help="Facilita a leitura, por exemplo para quem tem dislexia.")
            st.toggle("Reduzir movimento", key="pref_movimento", on_change=_salvar_preferencia,
                      **_inicial("movimento", salvas), help="Tira animações e a rolagem suave.")
            st.button("Voltar ao padrão", key="a11y-padrao", type="tertiary", on_click=_restaurar_acessibilidade)
        # botão invisível: o "Não mostrar mais o tutorial" do modal clica nele para gravar a preferência
        st.button("desligar tutorial", key="tour-desligar", on_click=_desligar_tutorial)


def _menu() -> str:
    opcoes = [TELA_S3, TELA_CATALOGO, TELA_JOBS, TELA_WORKFLOWS, TELA_ATHENA]
    if st.session_state.get("tela") not in opcoes:
        st.session_state["tela"] = TELA_S3
    with st.sidebar:
        st.markdown('<div class="menu-titulo">Console do datalake</div>', unsafe_allow_html=True)
        tela = st.radio("Serviço", opcoes, key="tela", format_func=ICONES.get, label_visibility="collapsed")
        st.divider()
        if st.button("Recarregar", key="recarregar", help="Lê o bucket de novo e recria as tabelas"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()
        st.caption("Ferramenta de estudo inspirada nos consoles do S3, do Glue e do Athena. Roda no seu computador.")
    return tela


def _pagina() -> None:
    st.set_page_config(page_title="Console do datalake", layout="wide", initial_sidebar_state="expanded")
    st.markdown(ui.CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="barra-console">'
                f'<span class="marca"><span aria-hidden="true">☁ </span>Console do datalake</span>'
                f'<span class="servicos">S3 · Glue · Athena</span>'
                f'<span class="detalhe">s3://{s3.BUCKET} · {s3.ENDPOINT} · Athena só lê · jobs rodam de s3://{recursos.BUCKET}/</span>'
                f'<span class="regiao">{s3.REGIAO}</span></div>', unsafe_allow_html=True)
    tela = _menu()
    salvas = _salvas()
    _barra_flutuante(salvas)
    escolhas = _atuais()
    st.markdown(ui.css_acessibilidade(escolhas), unsafe_allow_html=True)
    ui.apoio_acessibilidade(reduzir_movimento=escolhas["movimento"])
    st.session_state.pop("contexto_tour", None)
    try:
        _conteudo(tela)
    finally:
        _mostrar_tour()


def _objetos_de_todos_os_buckets() -> tuple[list[particoes.Objeto], list[str]]:
    """Objetos do datalake com a chave de sempre e os dos outros buckets como "@<bucket>/<chave>"."""
    buckets = [b for b in _buckets() if b not in (s3.BUCKET, recursos.BUCKET)]   # scripts não viram tabelas
    objetos = list(_listar())
    for bucket in buckets:
        objetos += [replace(o, chave=particoes.chave_virtual(bucket, o.chave)) for o in _listar(bucket)]
    return objetos, [s3.BUCKET] + buckets


def _conteudo(tela: str) -> None:
    if tela == TELA_S3:                        # S3, jobs e workflows não dependem do bucket do datalake ter dados
        _tela_s3()
        return
    if tela == TELA_WORKFLOWS:
        _tela_workflows()
        return
    if tela == TELA_JOBS:
        _tela_jobs()
        return

    try:
        objetos, buckets = _objetos_de_todos_os_buckets()
    except s3.S3Indisponivel as erro:
        st.error(str(erro))
        st.stop()
    aviso_vazio = (f"O bucket {s3.BUCKET} está vazio. Gere os eventos com "
                   "`docker compose run --rm app python gerador/gerar_eventos.py` e clique em Recarregar.")
    if not objetos:
        st.info(aviso_vazio)
        st.stop()
    if all(o.chave.startswith(particoes.MARCA_BUCKET) for o in objetos):     # só há dados nos outros buckets
        st.info(aviso_vazio + " Por enquanto, aparecem só as tabelas dos outros buckets.")

    datasets = particoes.datasets(o.chave for o in objetos)
    try:
        con, colunas, falhas = _conexao(tuple(datasets), tuple(s3.raiz(b) for b in buckets))
    except duckdb.Error as erro:
        _mostrar_erro("Não consegui preparar as tabelas no DuckDB.", erro)
        st.stop()
    if falhas:
        with st.expander(f"⚠ {len(falhas)} tabela(s) que o DuckDB não conseguiu ler ficaram de fora"):
            for nome, motivo in falhas.items():
                st.markdown(f"- `{nome}`: {motivo}")
        datasets = [d for d in datasets if d.nome_view not in falhas]

    if tela == TELA_CATALOGO:
        _tela_catalogo(objetos, datasets, colunas)
    else:
        _tela_athena(objetos, datasets, con, colunas)


def main() -> None:
    try:
        _pagina()
    except (StopException, RerunException):
        raise
    except Exception as erro:
        st.error("Algo deu errado no explorador. Clique em Recarregar; se continuar, veja `docker compose logs explorador`.")
        st.caption(f"Detalhe técnico: {type(erro).__name__}: {erro}")


main()
