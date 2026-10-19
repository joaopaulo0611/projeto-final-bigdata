from explorador import particoes
from explorador.particoes import (SEM_PARTICAO, Dataset, LinhaParticao, Objeto, datasets,
                                  formato_do_arquivo, navegar, particao_da_chave,
                                  tabela_particoes, tamanho_legivel)

CHAVES = [
    "landing/event_name=scroll/year=2026/month=09/day=01/coletor-s42-001.jsonl",
    "landing/event_name=scroll/year=2026/month=09/day=02/coletor-s42-001.jsonl",
    "silver/event_name=page_view/year=2026/month=09/day=01/part-0.snappy.parquet",
    "silver/_SUCCESS",
    "silver/eventos_rejeitados/part-0.snappy.parquet",
    "silver/itens/year=2026/month=09/day=01/part-0.snappy.parquet",
    "gold/funil_compra/part-0.snappy.parquet",
    "gold/funil_compra/_SUCCESS",
    "_verificacao/part-0.parquet",
    "bronze/_temporary/0/part-0.parquet",
    "solto.parquet",
    "silver/leia-me.txt",
]


def test_formato_do_arquivo():
    assert formato_do_arquivo("a/b.snappy.parquet") == "parquet"
    assert formato_do_arquivo("a/b.jsonl") == "jsonl"
    assert formato_do_arquivo("a/_SUCCESS") is None
    assert formato_do_arquivo("a/b.txt") is None


def test_particao_da_chave_mantem_o_mes_com_dois_digitos():
    assert particao_da_chave(CHAVES[0]) == {"event_name": "scroll", "year": "2026", "month": "09", "day": "01"}
    assert particao_da_chave("gold/funil_compra/part-0.parquet") is None
    assert particao_da_chave("x/year=2026/part-0.parquet") == {"year": "2026"}


def test_datasets_ignora_pastas_internas_arquivos_soltos_e_nao_dados():
    assert datasets(CHAVES) == [
        Dataset("gold/funil_compra", "parquet", "gold.funil_compra", False),
        Dataset("landing", "jsonl", "landing.eventos", True),
        Dataset("silver", "parquet", "silver.eventos", True),
        Dataset("silver/eventos_rejeitados", "parquet", "silver.eventos_rejeitados", False),
        Dataset("silver/itens", "parquet", "silver.itens", True),
    ]


def test_tabela_particoes_soma_arquivos_e_bytes_por_evento_e_dia():
    objetos = [
        Objeto(CHAVES[0], 100), Objeto(CHAVES[1], 50),
        Objeto("landing/event_name=scroll/year=2026/month=09/day=01/coletor-s42-002.jsonl", 10),
        Objeto("landing/event_name=click/year=2026/month=09/day=01/coletor-s42-001.jsonl", 3),
        Objeto("landing_outros/event_name=click/year=2026/month=09/day=01/x.jsonl", 999),
    ]
    assert tabela_particoes(objetos, "landing") == [
        LinhaParticao("click", "2026", "09", "01", 1, 3),
        LinhaParticao("scroll", "2026", "09", "01", 2, 110),
        LinhaParticao("scroll", "2026", "09", "02", 1, 50),
    ]


def test_tabela_particoes_da_raiz_da_silver_deixa_de_fora_as_pastas_vizinhas():
    objetos = [Objeto(c, 1) for c in CHAVES]
    assert tabela_particoes(objetos, "silver") == [LinhaParticao("page_view", "2026", "09", "01", 1, 1)]
    assert tabela_particoes(objetos, "silver/itens") == [LinhaParticao(SEM_PARTICAO, "2026", "09", "01", 1, 1)]


def test_tabela_particoes_de_dataset_sem_particao():
    objetos = [Objeto("gold/funil_compra/part-0.parquet", 7), Objeto("gold/funil_compra/_SUCCESS", 0)]
    assert tabela_particoes(objetos, "gold/funil_compra/") == [
        LinhaParticao(SEM_PARTICAO, SEM_PARTICAO, SEM_PARTICAO, SEM_PARTICAO, 1, 7)]


def test_navegar_devolve_subpastas_e_arquivos_diretos():
    objetos = [Objeto(c, 1) for c in CHAVES]
    pastas, arquivos = navegar(objetos, "")
    assert pastas == ["_verificacao", "bronze", "gold", "landing", "silver"]
    assert [o.chave for o in arquivos] == ["solto.parquet"]
    pastas, arquivos = navegar(objetos, "gold/funil_compra/")
    assert pastas == []
    assert [o.chave for o in arquivos] == ["gold/funil_compra/_SUCCESS", "gold/funil_compra/part-0.snappy.parquet"]


def test_tamanho_legivel():
    assert tamanho_legivel(0) == "0 B"
    assert tamanho_legivel(512) == "512 B"
    assert tamanho_legivel(1536) == "1,5 KB"
    assert tamanho_legivel(5 * 1024 * 1024) == "5,0 MB"


def test_pasta_com_dois_formatos_vira_um_dataset_por_formato():
    chaves = ["landing/mista/year=2026/month=09/day=01/a.jsonl",
              "landing/mista/year=2026/month=09/day=01/b.parquet"]
    assert datasets(chaves) == [Dataset("landing/mista", "jsonl", "landing.mista_jsonl", True),
                                Dataset("landing/mista", "parquet", "landing.mista_parquet", True)]
    objetos = [Objeto(chaves[0], 10), Objeto(chaves[1], 30)]
    assert tabela_particoes(objetos, "landing/mista", "parquet") == [LinhaParticao(SEM_PARTICAO, "2026", "09", "01", 1, 30)]
    assert tabela_particoes(objetos, "landing/mista") == [LinhaParticao(SEM_PARTICAO, "2026", "09", "01", 2, 40)]


def test_tabela_particoes_ignora_subpastas_que_nao_sao_particao():
    objetos = [Objeto("silver/eventos/year=2026/month=09/day=01/a.parquet", 5),
               Objeto("silver/eventos/_tmp/year=2026/b.parquet", 7),
               Objeto("silver/eventos/backup/c.parquet", 9)]
    assert tabela_particoes(objetos, "silver/eventos") == [LinhaParticao(SEM_PARTICAO, "2026", "09", "01", 1, 5)]


def test_tamanho_legivel_arredonda_para_a_unidade_seguinte():
    assert tamanho_legivel(1048575) == "1,0 MB"
    assert tamanho_legivel(1023) == "1023 B"


def test_migalhas_do_caminho_para_o_breadcrumb():
    from explorador.particoes import migalhas
    assert migalhas("") == []
    assert migalhas("silver/event_name=purchase/") == [("silver", "silver/"),
                                                      ("event_name=purchase", "silver/event_name=purchase/")]


# ------------------------------------------------------------ outros buckets ------------------------------------------------------------

def test_dataset_de_outro_bucket_vira_banco_com_o_nome_do_bucket():
    chaves = ["silver/event_name=x/year=2026/month=09/day=01/a.parquet",
              particoes.chave_virtual("rascunho-turma", "notas/a.jsonl"),
              particoes.chave_virtual("rascunho-turma", "vendas/year=2026/b.parquet"),
              particoes.chave_virtual("rascunho-turma", "solto.parquet")]
    por_nome = {d.nome_view: d for d in particoes.datasets(chaves)}
    assert set(por_nome) == {"silver.eventos", "rascunho_turma.notas", "rascunho_turma.vendas", "rascunho_turma.raiz"}
    notas = por_nome["rascunho_turma.notas"]
    assert (notas.bucket, notas.caminho) == ("rascunho-turma", "notas")
    assert por_nome["rascunho_turma.vendas"].particionado
    assert (por_nome["rascunho_turma.raiz"].bucket, por_nome["rascunho_turma.raiz"].caminho) == ("rascunho-turma", "")
    assert (por_nome["silver.eventos"].bucket, por_nome["silver.eventos"].caminho) == (None, "silver")


def test_bucket_com_nome_de_camada_nao_se_mistura_com_a_camada():
    chaves = ["gold/funil/a.parquet", particoes.chave_virtual("gold", "funil/a.parquet")]
    assert sorted(d.nome_view for d in particoes.datasets(chaves)) == ["gold.funil", "gold_bucket.funil"]


def test_particoes_de_outro_bucket_nao_misturam_com_o_datalake():
    objetos = [Objeto("notas/year=2026/a.parquet", 10),
               Objeto(particoes.chave_virtual("rascunho", "notas/year=2026/a.parquet"), 99)]
    dataset = next(d for d in particoes.datasets(o.chave for o in objetos) if d.bucket == "rascunho")
    assert [l.bytes for l in particoes.tabela_particoes(objetos, dataset.prefixo, dataset.formato)] == [99]
