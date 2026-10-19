from explorador import tipos

EVENTO = 'STRUCT(page VARCHAR, "user" STRUCT(id BIGINT, plano VARCHAR), itens STRUCT(sku VARCHAR, preco DOUBLE)[])'


def test_tipo_simples_fica_como_esta_em_minusculas():
    assert tipos.curto("VARCHAR") == "varchar"
    assert tipos.curto("DECIMAL(10,2)") == "decimal(10,2)"
    assert not tipos.tem_struct("BIGINT[]")


def test_struct_vira_so_a_palavra_struct():
    assert tipos.curto(EVENTO) == "struct"
    assert tipos.curto("STRUCT(a INTEGER)[]") == "struct[]"
    assert tipos.curto("MAP(VARCHAR, STRUCT(a INTEGER))") == "map(varchar, struct)"
    assert tipos.tem_struct(EVENTO) and tipos.tem_struct("MAP(VARCHAR, STRUCT(a INTEGER))")


def test_campos_mostra_a_tipagem_interna_em_arvore():
    assert tipos.campos(EVENTO) == [
        ("page", "varchar", []),
        ("user", "struct", [("id", "bigint", []), ("plano", "varchar", [])]),
        ("itens", "struct[]", [("sku", "varchar", []), ("preco", "double", [])]),
    ]


def test_campos_de_struct_dentro_de_map_e_lista():
    assert tipos.campos("STRUCT(a INTEGER)[]") == [("a", "integer", [])]
    assert tipos.campos("MAP(VARCHAR, STRUCT(b DATE))") == [("b", "date", [])]
    assert tipos.campos("VARCHAR") == []


def test_markdown_da_arvore_com_recuo_por_nivel():
    md = tipos.arvore_markdown(EVENTO)
    linhas = md.splitlines()
    assert linhas[0] == "- `page` varchar"
    assert linhas[1] == "- `user` struct"
    assert linhas[2] == "    - `id` bigint"
    assert "    - `preco` double" in linhas


def test_nome_com_virgula_ou_parenteses_entre_aspas():
    assert tipos.campos('STRUCT("a,b" INTEGER, "c(d)" VARCHAR)') == [("a,b", "integer", []), ("c(d)", "varchar", [])]
