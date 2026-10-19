"""Defeitos injetados no dado, para a Silver encontrar.

Cada tipo recebe uma cota proporcional ao seu peso. Os defeitos que
alteram um evento existente atingem no máximo 5% dos candidatos daquele
tipo, para não destruir a receita (por exemplo, tirar o id de metade das
compras). Além disso, somando todos os tipos, no máximo 5% dos eventos de
cada nome são alterados, para os defeitos monetários não se acumularem nas
compras. Os reembolsos órfãos inseridos também ficam em 5% das compras,
para não superar os reembolsos reais. O que sobra das cotas vai para "ts_futuro", que tem candidatos
de sobra. Um evento recebe no máximo um defeito.
"""

from __future__ import annotations

import copy
import itertools
import math
import random
from collections import Counter
from datetime import timedelta

from gerador.eventos import hex8, iso, ler_iso, novo_uuid

PESOS = {
    "purchase_sem_id": 1,
    "valor_negativo": 2,
    "moeda_usd": 2,
    "scroll_33": 2,
    "ts_nulo": 2,
    "ts_futuro": 2,
    "refund_orfao": 1,
    "evento_fora_catalogo": 2,
}
TIPOS = tuple(PESOS)
TETO = 0.05


def _monetario_positivo(e: dict) -> bool:
    v = e["params"].get("value")
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


FILTROS = {
    "purchase_sem_id": lambda e: e["event_name"] == "purchase",
    "valor_negativo": _monetario_positivo,
    "moeda_usd": lambda e: "currency" in e["params"],
    "scroll_33": lambda e: e["event_name"] == "scroll",
    "ts_nulo": lambda e: e["event_ts"] is not None,
    "ts_futuro": lambda e: e["event_ts"] is not None,
}


def _sem_id(e: dict) -> None:
    e["params"]["transaction_id"] = None


def _negativo(e: dict) -> None:
    e["params"]["value"] = -float(e["params"]["value"])


def _usd(e: dict) -> None:
    e["params"]["currency"] = "USD"


def _scroll_33(e: dict) -> None:
    e["params"]["percent_scrolled"] = 33


def _ts_nulo(e: dict) -> None:
    e["event_ts"] = None


def _ts_futuro(e: dict) -> None:
    e["event_ts"] = iso(ler_iso(e["event_ts"]) + timedelta(days=3650))


# ts_futuro por último: absorve o que os outros tipos não conseguiram usar
MUTACOES = {
    "purchase_sem_id": _sem_id,
    "valor_negativo": _negativo,
    "moeda_usd": _usd,
    "scroll_33": _scroll_33,
    "ts_nulo": _ts_nulo,
    "ts_futuro": _ts_futuro,
}


def _clonar(rng: random.Random, base: dict, nome: str, params: dict) -> dict:
    novo = copy.deepcopy(base)
    novo.update(event_id=novo_uuid(rng), event_name=nome, params=params, items=[])
    return novo


def _refund_orfao(rng: random.Random, base: dict) -> dict:
    return _clonar(rng, base, "refund", {
        "transaction_id": "T-" + hex8(rng).upper(), "value": 597.0, "tax": 29.85,
        "shipping": 0.0, "currency": "BRL", "reason": "garantia_7_dias",
    })


def _fora_do_catalogo(rng: random.Random, base: dict) -> dict:
    return _clonar(rng, base, "add_to_wishlist", {})


INSERCOES = {"refund_orfao": _refund_orfao, "evento_fora_catalogo": _fora_do_catalogo}


def _cotas(alvo: int) -> dict[str, int]:
    total = sum(PESOS.values())
    cotas = {t: alvo * p // total for t, p in PESOS.items()}
    for t in itertools.islice(itertools.cycle(TIPOS), alvo - sum(cotas.values())):
        cotas[t] += 1
    return cotas


def _limitar_orfaos(cota: int, originais: list[dict]) -> tuple[int, int]:
    """Aplica o teto de 5% das compras aos reembolsos órfãos. Devolve (cota, sobra)."""
    n_compras = sum(1 for e in originais if e["event_name"] == "purchase")
    n = min(cota, math.ceil(n_compras * TETO))
    return n, cota - n


def aplicar_sujeira(rng: random.Random, eventos: list[dict], fracao: float) -> dict[str, int]:
    """Altera `eventos` no lugar e acrescenta os inseridos. Devolve a contagem por tipo."""
    originais = list(eventos)
    cotas = _cotas(round(len(originais) * fracao))
    cotas["refund_orfao"], sobra = _limitar_orfaos(cotas["refund_orfao"], originais)
    contagem = dict.fromkeys(TIPOS, 0)
    usados: set[int] = set()
    por_nome = Counter(e["event_name"] for e in originais)
    tetos = {nome: math.ceil(n * TETO) for nome, n in por_nome.items()}
    alterados: Counter = Counter()

    for tipo, mutar in MUTACOES.items():
        candidatos = [e for e in originais if id(e) not in usados and FILTROS[tipo](e)]
        rng.shuffle(candidatos)
        quero = cotas[tipo] + (sobra if tipo == "ts_futuro" else 0)
        teto = len(candidatos) if tipo == "ts_futuro" else math.ceil(len(candidatos) * TETO)
        n = min(quero, teto)
        if tipo != "ts_futuro":
            sobra += quero - n
        aplicados = 0
        for e in candidatos:
            if aplicados == n:
                break
            nome = e["event_name"]
            if alterados[nome] >= tetos[nome]:
                continue
            mutar(e)
            usados.add(id(e))
            alterados[nome] += 1
            aplicados += 1
        if tipo != "ts_futuro":
            sobra += n - aplicados
        contagem[tipo] = aplicados

    limpos = [e for e in originais if id(e) not in usados]
    for tipo, inserir in INSERCOES.items():
        for _ in range(cotas[tipo]):
            eventos.append(inserir(rng, rng.choice(limpos)))
        contagem[tipo] = cotas[tipo]
    return contagem
