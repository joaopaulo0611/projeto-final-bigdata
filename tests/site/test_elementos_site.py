import re
from pathlib import Path

from gerador.elementos import ELEMENTOS

HTML = (Path(__file__).resolve().parents[2] / "site" / "index.html").read_text(encoding="utf-8")


def _ids_no_site() -> set[str]:
    literais = set(re.findall(r'data-heat="([^"]+)"', HTML))
    planos = set(re.findall(r'heat: "([^"]+)"', HTML))      # cartões gerados por JS (PLANOS)
    return literais | planos


def test_todo_elemento_do_contrato_existe_no_site_e_vice_versa():
    assert _ids_no_site() == set(ELEMENTOS)


def test_eventos_de_clique_passam_por_comElemento():
    for nome in ("click", "file_download", "video_start", "select_item", "begin_checkout",
                 "add_shipping_info", "add_payment_info", "purchase", "refund", "generate_lead", "site_search"):
        trecho = re.search(r'track\("' + nome + r'", comElemento\(', HTML)
        assert trecho, f"track(\"{nome}\", ...) sem comElemento"


def test_site_carrega_o_mapa_antes_do_script_principal_e_tem_o_botao():
    pos_mapa = HTML.index('<script src="mapa_calor.js"></script>')
    pos_principal = HTML.index("<script>\n(function () {")
    assert pos_mapa < pos_principal
    assert 'id="mapa-calor"' in HTML


def test_camadas_do_overlay_nao_recebem_clique():
    assert re.search(r"\.calor-canvas\s*\{[^}]*pointer-events:\s*none", HTML)
    assert re.search(r"\.calor-etiqueta\s*\{[^}]*pointer-events:\s*none", HTML)
    assert re.search(r"\.calor-faixa\s*\{[^}]*pointer-events:\s*none", HTML)


def test_mapa_e_desenhado_em_canvas_com_manchas_coloridas():
    assert 'document.createElement("canvas")' in HTML
    assert "createRadialGradient" in HTML          # cada ponto de calor é uma mancha difusa
    assert "getImageData" in HTML                  # o calor acumulado é pintado com a paleta
    assert "PALETA_CALOR" in HTML
    assert ".calor-camada" not in HTML             # os retângulos antigos saíram


def test_overlay_nao_aumenta_a_pagina_nem_cria_contexto_abaixo_do_modal():
    regra = re.search(r"#calor-raiz\s*\{([^}]*)\}", HTML).group(1)
    assert "overflow: hidden" in regra
    assert "z-index" not in regra          # sem contexto próprio: a camada do modal pode ficar acima dele


def test_overlay_redesenha_quando_o_conteudo_muda_de_tamanho():
    assert "new ResizeObserver(redesenharCalorDepois)" in HTML
    assert re.search(r'observar\(document\.querySelector\("main"\)\)', HTML)
    assert re.search(r'observar\(document\.querySelector\("#modal \.modal"\)\)', HTML)


def test_overlay_redesenha_a_cada_interacao_mesmo_sem_resizeobserver():
    assert '["click", "input", "change"].forEach' in HTML
    assert "if (calor.ligado) redesenharCalorDepois();" in HTML


def test_avisos_do_site_falam_a_lingua_do_aluno():
    assert "jobs 07 e 08" not in HTML
    assert "job de exportação do mapa de calor (R11)" in HTML
    assert "O mapa não tem cliques" in HTML        # landing antiga, sem element_id


def test_elementos_fixos_tem_calor_em_camada_fixa_na_tela():
    assert re.search(r"\.calor-fixo\s*\{[^}]*position:\s*fixed[^}]*pointer-events:\s*none", HTML)
    assert 'el.closest(".topo")' in HTML           # cabeçalho grudado no topo (sticky)
    assert 'el.closest("#modal")' in HTML          # modal (position: fixed)


def test_cada_canvas_respeita_a_intensidade_da_gold_e_mapa_vazio_nao_tem_veu():
    assert "teto" in HTML                          # o vermelho de cada canvas vem da intensidade, não do próprio máximo
    assert "if (!pontos.length) return;" in HTML
