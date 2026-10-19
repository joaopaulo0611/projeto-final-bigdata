import random
from datetime import datetime, timezone

from gerador import catalogo as cat
from gerador.eventos import Contexto, criar_evento, iso, item, novo_uuid


def _ctx():
    return Contexto("anon-1", cat.CANAIS[1], cat.DISPOSITIVOS[0], "s-1", pagina="landing")


def test_iso_tem_milissegundos_e_z():
    ts = datetime(2026, 9, 1, 14, 22, 5, 123456, tzinfo=timezone.utc)
    assert iso(ts) == "2026-09-01T14:22:05.123Z"


def test_uuid_e_deterministico_pela_seed():
    assert novo_uuid(random.Random(1)) == novo_uuid(random.Random(1))
    assert len(novo_uuid(random.Random(1))) == 36


def test_criar_evento_segue_o_contrato():
    ts = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ev = criar_evento(random.Random(1), "purchase", ts, _ctx(), {"value": 1.0}, [item(cat.PLANOS[0])])
    assert set(ev) == {
        "event_id", "event_name", "event_ts", "user_pseudo_id", "user_id", "session_hint",
        "page", "traffic", "device", "params", "items",
    }
    assert ev["event_ts"] == "2026-09-01T00:00:00.000Z"
    assert ev["user_id"] is None
    assert ev["page"] == {"location": "https://loja.exemplo/", "referrer": None}
    assert ev["traffic"] == {"source": "google", "medium": "cpc", "campaign": "formacao_dados"}
    assert ev["device"] == {"category": "mobile", "os": "Android", "browser": "Chrome"}
    assert ev["items"] == [{
        "item_id": "PLANO-BASICO", "item_name": "Plano Básico", "item_category": "plano",
        "price": 297.0, "quantity": 1,
    }]


def test_item_aceita_campos_da_lista():
    it = item(cat.PLANOS[1], index=1, **cat.LISTA)
    assert it["index"] == 1
    assert it["item_list_id"] == "tabela_planos"


def test_catalogo_tem_os_22_nomes_de_evento():
    assert len(cat.EVENTOS) == 22
    assert len(set(cat.EVENTOS)) == 22
