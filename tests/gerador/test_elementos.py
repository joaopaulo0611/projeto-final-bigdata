import copy
import json
from datetime import datetime, timezone

import pytest

from gerador.elementos import ELEMENTOS, elemento, marcar_elementos
from gerador.gerar_eventos import gerar

DATA = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEM_CLIQUE = {"page_view", "scroll", "video_progress", "video_complete", "view_item_list", "view_item", "view_cart"}


def _ev(nome, params=None, items=None):
    return {"event_name": nome, "params": params or {}, "items": items or []}


@pytest.mark.parametrize("evento, esperado", [
    (_ev("click", {"link_domain": "instagram.com", "outbound": True}), "social-instagram"),
    (_ev("click", {"link_domain": "wa.me", "outbound": True}), "social-whatsapp"),
    (_ev("click", {"link_id": "hero_ver_planos", "outbound": False}), "cta-hero-ver-planos"),
    (_ev("select_item", items=[{"item_id": "PLANO-PRO"}]), "plano-pro"),
    (_ev("add_to_cart", items=[{"item_id": "PLANO-BASICO"}]), "plano-basico"),   # sem contexto: botão do cartão
    (_ev("remove_from_cart", items=[{"item_id": "BUMP-MENTORIA"}]), "bump"),
    (_ev("add_shipping_info", {"shipping_tier": "SEDEX"}), "frete-sedex"),
    (_ev("add_payment_info", {"payment_type": "cartao_parcelado"}), "pagto-cartao-parcelado"),
    (_ev("video_start"), "btn-play"),
    (_ev("refund"), "btn-refund"),
    (_ev("sign_up"), "btn-signup"),
    (_ev("page_view"), None),
    (_ev("add_to_wishlist"), None),
])
def test_elemento_segue_a_tabela_da_spec(evento, esperado):
    assert elemento(evento) == esperado


def test_todo_id_produzido_esta_no_catalogo_de_elementos():
    assert len(ELEMENTOS) == 26
    assert all(i == i.lower() and " " not in i for i in ELEMENTOS)


def test_gerador_marca_so_eventos_de_clique_e_nao_muda_o_resto():
    arquivos, resumo = gerar(seed=5, dias=3, visitantes=300, sujeira=0.03, data_inicial=DATA)
    eventos = [json.loads(l) for v in arquivos.values() for l in v.splitlines()]
    for e in eventos:
        eid = (e.get("params") or {}).get("element_id")
        if e["event_name"] in SEM_CLIQUE or e["event_name"] == "add_to_wishlist":
            assert eid is None
        else:
            assert eid in ELEMENTOS, e
    assert resumo["linhas_gravadas"] == len(eventos)


def test_marcar_elementos_nao_consome_o_rng_nem_muda_outros_campos():
    eventos = [_ev("video_start", {"video_percent": 0}), _ev("page_view")]
    antes = copy.deepcopy(eventos)
    assert marcar_elementos(eventos) == 1
    assert eventos[0]["params"] == {"video_percent": 0, "element_id": "btn-play"}
    assert eventos[1] == antes[1]


def _do(usuario, nome, item=None):
    return {"event_name": nome, "user_pseudo_id": usuario, "params": {},
            "items": [{"item_id": item}] if item else []}


def test_compra_pelo_modal_ou_pelo_cartao_segue_o_site():
    eventos = [
        _do("a", "select_item", "PLANO-PRO"), _do("a", "view_item", "PLANO-PRO"), _do("a", "add_to_cart", "PLANO-PRO"),
        _do("b", "select_item", "PLANO-BASICO"), _do("b", "add_to_cart", "PLANO-BASICO"),
        _do("b", "remove_from_cart", "PLANO-BASICO"), _do("b", "add_to_cart", "PLANO-PREMIUM"),
    ]
    marcar_elementos(eventos)
    ids = [e["params"].get("element_id") for e in eventos]
    assert ids == ["plano-pro", None, "modal-comprar",            # detalhe aberto → botão do modal
                   "plano-basico", "plano-basico",                # direto do cartão
                   "plano-premium", "plano-premium"]              # troca: cartão do plano novo


def test_contexto_e_do_mesmo_visitante():
    eventos = [_do("a", "view_item", "PLANO-PRO"), _do("b", "add_to_cart", "PLANO-PRO")]
    marcar_elementos(eventos)
    assert eventos[1]["params"]["element_id"] == "plano-pro"


def test_plano_desconhecido_fica_sem_element_id():
    assert elemento(_ev("add_to_cart", items=[{"item_id": "PLANO-X"}])) is None
    assert elemento(_ev("add_to_cart")) is None
