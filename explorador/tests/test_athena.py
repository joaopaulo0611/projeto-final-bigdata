from explorador import athena
from explorador.particoes import Dataset, Objeto


def test_nova_aba_numera_em_sequencia_e_comeca_vazia():
    abas = athena.nova_aba([])
    abas = athena.nova_aba(abas)
    assert [a.nome for a in abas] == ["Consulta 1", "Consulta 2"]
    assert abas[0].sql == "" and abas[0].execucao is None


def test_nova_aba_nao_repete_nome_depois_de_fechar():
    abas = athena.nova_aba(athena.nova_aba([]))
    abas, _ = athena.fechar_aba(abas, 0)
    assert [a.nome for a in athena.nova_aba(abas)] == ["Consulta 2", "Consulta 3"]


def test_fechar_aba_mantem_pelo_menos_uma_e_ajusta_a_selecao():
    abas = athena.nova_aba(athena.nova_aba(athena.nova_aba([])))
    abas, ativa = athena.fechar_aba(abas, 2)
    assert [a.nome for a in abas] == ["Consulta 1", "Consulta 2"] and ativa == 1
    abas, ativa = athena.fechar_aba(abas, 0)
    abas, ativa = athena.fechar_aba(abas, 0)
    assert [a.nome for a in abas] == ["Consulta 2"] and ativa == 0     # a última nunca fecha


def test_inserir_acrescenta_com_espaco():
    assert athena.inserir("", "silver") == "silver"
    assert athena.inserir("SELECT * FROM", "silver") == "SELECT * FROM silver"
    assert athena.inserir("SELECT * FROM ", "silver") == "SELECT * FROM silver"
    assert athena.inserir("SELECT\n", "event_name") == "SELECT\nevent_name"


def test_views_usadas_acha_os_nomes_no_sql_sem_contar_strings_e_comentarios():
    nomes = ["landing.eventos", "silver.eventos", "silver.itens", "gold.funil_compra"]
    sql = "-- silver.itens\nSELECT * FROM silver.eventos s JOIN \"gold\".\"funil_compra\" g ON 1=1 WHERE x = 'landing.eventos'"
    assert athena.views_usadas(sql, nomes) == ["gold.funil_compra", "silver.eventos"]
    assert athena.views_usadas("SELECT 1", nomes) == []
    assert athena.views_usadas("isto não é sql (", nomes) == []


def test_bytes_lidos_soma_os_arquivos_das_views_usadas():
    datasets = [Dataset("silver", "parquet", "silver.eventos", True), Dataset("silver/itens", "parquet", "silver.itens", True)]
    objetos = [
        Objeto("silver/event_name=scroll/year=2026/month=09/day=01/a.parquet", 100),
        Objeto("silver/event_name=click/year=2026/month=09/day=01/b.parquet", 50),
        Objeto("silver/itens/year=2026/month=09/day=01/c.parquet", 7),
    ]
    assert athena.bytes_lidos(["silver.eventos"], datasets, objetos) == 150
    assert athena.bytes_lidos(["silver.eventos", "silver.itens"], datasets, objetos) == 157
    assert athena.bytes_lidos([], datasets, objetos) == 0


def test_registrar_poe_a_mais_recente_primeiro_e_limita_o_tamanho():
    historico = []
    for i in range(5):
        historico = athena.registrar(historico, athena.Execucao(f"SELECT {i}", "Concluída", "10:00:0" + str(i),
                                                                0.1, 1, 0), maximo=3)
    assert [e.sql for e in historico] == ["SELECT 4", "SELECT 3", "SELECT 2"]


def test_resumo_da_execucao_em_portugues():
    ok = athena.Execucao("SELECT 1", "Concluída", "10:00:00", 0.4213, 1000, 1536)
    assert athena.resumo(ok) == "Concluída · tempo de execução 0,42 s · 1000 linhas · dados lidos (estimado) 1,5 KB"
    falhou = athena.Execucao("SELEC 1", "Falhou", "10:00:00", 0.01, 0, 0, erro="erro de escrita")
    assert athena.resumo(falhou) == "Falhou · tempo de execução 0,01 s · erro de escrita"


def test_bytes_lidos_respeita_filtro_de_particao_por_event_name():
    datasets = [Dataset("landing", "jsonl", "landing.eventos", True)]
    objetos = [
        Objeto("landing/event_name=purchase/year=2026/month=09/day=01/a.jsonl", 10),
        Objeto("landing/event_name=refund/year=2026/month=09/day=01/b.jsonl", 5),
        Objeto("landing/event_name=scroll/year=2026/month=09/day=01/c.jsonl", 1000),
    ]
    tudo = "SELECT count(*) FROM landing.eventos"
    um = "SELECT count(*) FROM landing.eventos WHERE event_name = 'purchase'"
    dois = "SELECT count(*) FROM landing.eventos WHERE event_name IN ('purchase', 'refund')"
    assert athena.bytes_lidos(["landing.eventos"], datasets, objetos, tudo) == 1015
    assert athena.bytes_lidos(["landing.eventos"], datasets, objetos, um) == 10
    assert athena.bytes_lidos(["landing.eventos"], datasets, objetos, dois) == 15
    assert athena.particoes_filtradas("SELECT 1 -- event_name = 'x'") is None    # comentário não conta
