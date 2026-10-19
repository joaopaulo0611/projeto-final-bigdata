"""O contrato do evento (spec, seção 5) e utilitários deterministas."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from gerador.catalogo import PAGINAS


@dataclass
class Contexto:
    """Estado do navegador do visitante no instante em que um evento é emitido."""

    user_pseudo_id: str
    canal: dict
    dispositivo: dict
    session_hint: str
    user_id: str | None = None
    pagina: str | None = None      # None antes do primeiro page_view da sessão
    referrer: str | None = None


def hex8(rng: random.Random) -> str:
    return f"{rng.getrandbits(32):08x}"


def novo_uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def iso(ts: datetime) -> str:
    ts = ts.astimezone(timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def ler_iso(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def item(produto: dict, **extra) -> dict:
    return {
        "item_id": produto["item_id"],
        "item_name": produto["item_name"],
        "item_category": produto["item_category"],
        "price": produto["price"],
        "quantity": 1,
        **extra,
    }


def criar_evento(rng: random.Random, nome: str, ts: datetime, ctx: Contexto,
                 params: dict | None = None, items: list | None = None) -> dict:
    return {
        "event_id": novo_uuid(rng),
        "event_name": nome,
        "event_ts": iso(ts),
        "user_pseudo_id": ctx.user_pseudo_id,
        "user_id": ctx.user_id,
        "session_hint": ctx.session_hint,
        "page": {"location": PAGINAS[ctx.pagina], "referrer": ctx.referrer},
        "traffic": {
            "source": ctx.canal["source"],
            "medium": ctx.canal["medium"],
            "campaign": ctx.canal["campaign"],
        },
        "device": {
            "category": ctx.dispositivo["category"],
            "os": ctx.dispositivo["os"],
            "browser": ctx.dispositivo["browser"],
        },
        "params": dict(params or {}),
        "items": [dict(i) for i in (items or [])],
    }
