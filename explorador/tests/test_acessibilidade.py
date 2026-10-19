from explorador import ui
from explorador.preferencias import PADRAO


def test_padrao_so_define_o_tamanho_do_texto():
    css = ui.css_acessibilidade(PADRAO)
    assert "font-size: 100%" in css
    assert "#000" not in css and "underline" not in css and "letter-spacing" not in css and "transition" not in css


def test_cada_opcao_acrescenta_a_sua_regra():
    assert "font-size: 115%" in ui.css_acessibilidade({**PADRAO, "texto": 115})
    assert "color: #000" in ui.css_acessibilidade({**PADRAO, "contraste": True})
    assert "text-decoration: underline" in ui.css_acessibilidade({**PADRAO, "sublinhar": True})
    espaco = ui.css_acessibilidade({**PADRAO, "espacamento": True})
    assert "letter-spacing: .12em" in espaco and "word-spacing: .16em" in espaco      # valores da WCAG 1.4.12
    assert "transition: none" in ui.css_acessibilidade({**PADRAO, "movimento": True})


def test_alto_contraste_nao_pinta_de_preto_o_texto_dos_botoes():
    # links e botões continuam azuis no alto contraste: a cor é a pista de que dá para clicar
    css = ui.css_acessibilidade({**PADRAO, "contraste": True})
    assert ":not(button *, .barra-console *)" in css               # nem o da barra escura do topo


def test_selo_tem_texto_e_o_icone_fica_escondido_do_leitor_de_tela():
    selo = ui.selo("Falhou").conteudo
    assert 'aria-hidden="true">✖</span>' in selo and "Falhou" in selo


def test_script_de_apoio_cria_o_pular_para_o_conteudo_e_as_regioes():
    js = ui._APOIO_JS
    assert "Pular para o conteúdo" in js and 'role: "main"' in js and 'role: "navigation"' in js
    assert 'role: "table"' in js and '"columnheader"' in js and '"cell"' in js
