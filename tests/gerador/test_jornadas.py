from collections import defaultdict
from datetime import timedelta

from gerador import catalogo as cat
from gerador.eventos import ler_iso


def _por_pseudo(eventos):
    grupos = defaultdict(list)
    for e in eventos:
        grupos[e["user_pseudo_id"]].append(e)
    for evs in grupos.values():
        evs.sort(key=lambda e: e["event_ts"])
    return grupos


def test_todos_os_eventos_do_catalogo_aparecem(simulacao):
    eventos, _ = simulacao
    assert {e["event_name"] for e in eventos} == set(cat.EVENTOS)


def test_toda_jornada_comeca_com_page_view(simulacao):
    for evs in _por_pseudo(simulacao[0]).values():
        assert evs[0]["event_name"] == "page_view"


def test_frete_so_em_carrinho_premium(simulacao):
    eventos, _ = simulacao
    fretes = [e for e in eventos if e["event_name"] == "add_shipping_info"]
    assert fretes
    for e in fretes:
        assert any(i["item_id"] == cat.PREMIUM for i in e["items"])
    for e in eventos:
        if e["event_name"] == "purchase" and e["params"]["shipping"] > 0:
            assert any(i["item_id"] == cat.PREMIUM for i in e["items"])


def test_compra_tem_id_valor_e_imposto_coerentes(simulacao):
    compras = [e for e in simulacao[0] if e["event_name"] == "purchase"]
    assert compras
    for e in compras:
        p = e["params"]
        assert p["transaction_id"].startswith("T-")
        bruto = round(sum(i["price"] * i["quantity"] for i in e["items"]), 2)
        esperado = round(bruto - round(bruto * 0.05, 2), 2) if p["payment_type"] == "pix" else bruto
        assert p["value"] == esperado
        assert p["tax"] == round(p["value"] * 0.05, 2)
        assert p["currency"] == "BRL"
        assert p["coupon"] == ("PIX5" if p["payment_type"] == "pix" else None)


def test_reembolso_referencia_compra_de_1_a_7_dias_antes(simulacao):
    eventos, _ = simulacao
    compras = {e["params"]["transaction_id"]: e for e in eventos if e["event_name"] == "purchase"}
    reembolsos = [e for e in eventos if e["event_name"] == "refund"]
    assert reembolsos
    for r in reembolsos:
        c = compras[r["params"]["transaction_id"]]
        assert timedelta(days=1) <= ler_iso(r["event_ts"]) - ler_iso(c["event_ts"]) <= timedelta(days=7)
        assert r["params"]["value"] == c["params"]["value"]
        assert r["items"] == c["items"]


def test_session_hint_muda_mais_vezes_que_as_sessoes(simulacao):
    eventos, sessoes = simulacao
    assert len({e["session_hint"] for e in eventos}) > sessoes


def test_session_hint_distintos_passam_de_1_2_vezes_as_sessoes(simulacao):
    eventos, sessoes = simulacao
    assert len({e["session_hint"] for e in eventos}) >= 1.2 * sessoes


def test_reembolso_e_mais_frequente_no_instagram_que_no_organico(simulacao):
    eventos, _ = simulacao
    compras = {e["params"]["transaction_id"]: e for e in eventos if e["event_name"] == "purchase"}
    reembolsados = {e["params"]["transaction_id"] for e in eventos if e["event_name"] == "refund"}
    n, r = defaultdict(int), defaultdict(int)
    for tid, c in compras.items():
        canal = (c["traffic"]["source"], c["traffic"]["medium"])
        n[canal] += 1
        r[canal] += tid in reembolsados
    insta, organico = ("instagram", "paid_social"), ("google", "organic")
    assert n[insta] and n[organico]
    assert r[insta] / n[insta] > r[organico] / n[organico]
    outros = [c for c in n if c != insta]
    assert r[insta] / n[insta] > sum(r[c] for c in outros) / sum(n[c] for c in outros)


def test_user_id_so_aparece_a_partir_do_sign_up(simulacao):
    casos = 0
    for evs in _por_pseudo(simulacao[0]).values():
        logados = [i for i, e in enumerate(evs) if e["user_id"]]
        if not logados:
            continue
        casos += 1
        primeiro = logados[0]
        assert evs[primeiro]["event_name"] == "sign_up"
        assert all(e["user_id"] is None for e in evs[:primeiro])
    assert casos > 0


def test_login_so_depois_de_sign_up_do_mesmo_user_id(simulacao):
    logins = 0
    for evs in _por_pseudo(simulacao[0]).values():
        for i, e in enumerate(evs):
            if e["event_name"] == "login":
                logins += 1
                assert any(a["event_name"] == "sign_up" and a["user_id"] == e["user_id"] for a in evs[:i])
    assert logins > 0


def test_existe_lead_que_volta_outro_dia_e_compra(simulacao):
    achou = False
    for evs in _por_pseudo(simulacao[0]).values():
        leads = [e for e in evs if e["event_name"] == "generate_lead"]
        compras = [e for e in evs if e["event_name"] == "purchase"]
        if leads and compras and compras[0]["event_ts"][:10] > leads[0]["event_ts"][:10]:
            achou = True
            break
    assert achou


def test_order_bump_e_troca_de_plano_geram_remove_from_cart(simulacao):
    removidos = {e["items"][0]["item_category"] for e in simulacao[0] if e["event_name"] == "remove_from_cart"}
    assert removidos == {"plano", "order_bump"}


def test_marcos_de_scroll_e_video_sao_os_do_contrato(simulacao):
    for e in simulacao[0]:
        if e["event_name"] == "scroll":
            assert e["params"]["percent_scrolled"] in (25, 50, 75, 90)
        elif e["event_name"] == "video_start":
            assert e["params"]["video_percent"] == 0
        elif e["event_name"] == "video_progress":
            assert e["params"]["video_percent"] in (10, 25, 50, 75)
        elif e["event_name"] == "video_complete":
            assert e["params"]["video_percent"] == 100


def test_busca_sem_resultado_existe(simulacao):
    buscas = [e for e in simulacao[0] if e["event_name"] == "site_search"]
    assert any(e["params"]["search_results"] == 0 for e in buscas)
    assert any(e["params"]["search_results"] > 0 for e in buscas)


def test_simular_e_deterministico():
    from datetime import datetime, timezone

    from gerador.jornadas import simular

    data = datetime(2026, 9, 1, tzinfo=timezone.utc)
    a, _, _ = simular(seed=3, dias=3, visitantes=50, data_inicial=data)
    b, _, _ = simular(seed=3, dias=3, visitantes=50, data_inicial=data)
    assert a == b
