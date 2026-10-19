"""Divide os eventos em lotes por dia, como um coletor que descarrega em intervalos.

Cada arquivo vai para a pasta `event_name=<nome>/year=AAAA/month=MM/day=DD`:
um lote do coletor vira um arquivo por nome de evento. O dia do lote
(`_dt`) é o dia de coleta, gravado antes da sujeira, por isso
um evento com timestamp nulo ou no futuro ainda tem uma partição. Cerca de
1% dos eventos é reenviado no lote vizinho com o mesmo event_id; é a
duplicata que a Silver precisa remover.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict

PREFIXO = "landing"
# Mesmas regras do Spark para valores de partição: vazio/nulo vira esta pasta,
# e caracteres que confundem o caminho viram %XX.
SEM_NOME = "__HIVE_DEFAULT_PARTITION__"
_ESCAPAR = set('"#%\'*/:=?\\{[]^\x7f')  # \\ é a barra invertida


def particao(data_iso: str) -> str:
    """'2026-09-01' -> 'year=2026/month=09/day=01'."""
    ano, mes, dia = data_iso[:10].split("-")
    return f"year={ano}/month={mes}/day={dia}"


def valor_de_particao(valor) -> str:
    """'page_view' -> 'page_view'; None ou '' -> SEM_NOME; 'a/b' -> 'a%2Fb'."""
    if not isinstance(valor, str) or not valor:
        return SEM_NOME
    return "".join(f"%{ord(c):02X}" if c in _ESCAPAR or ord(c) < 0x20 else c for c in valor)


def pasta(event_name, data_iso: str) -> str:
    """Pasta da landing de um evento: 'landing/event_name=scroll/year=2026/month=09/day=01'."""
    return f"{PREFIXO}/event_name={valor_de_particao(event_name)}/{particao(data_iso)}"


def serializar(eventos: list[dict]) -> str:
    return "".join(
        json.dumps({k: v for k, v in e.items() if not k.startswith("_")},
                   ensure_ascii=False, separators=(",", ":")) + "\n"
        for e in eventos
    )


def montar_lotes(rng: random.Random, eventos: list[dict], origem: str, seed: int,
                 fracao_reenvio: float = 0.01) -> tuple[dict[str, str], int]:
    """Devolve ({chave S3: conteúdo JSONL}, número de duplicatas por reenvio)."""
    por_dia: dict[str, list[dict]] = defaultdict(list)
    for e in eventos:
        por_dia[e["_dt"]].append(e)

    arquivos: dict[str, str] = {}
    duplicatas = 0
    for dt in sorted(por_dia):
        do_dia = sorted(por_dia[dt], key=lambda e: e["event_ts"] or "")
        n = min(rng.randint(3, 6), len(do_dia))
        lotes = [do_dia[i * len(do_dia) // n:(i + 1) * len(do_dia) // n] for i in range(n)]
        reenvios: list[list[dict]] = [[] for _ in lotes]
        if len(lotes) > 1:
            for i, lote in enumerate(lotes):
                destino = i + 1 if i + 1 < len(lotes) else i - 1
                for e in lote:
                    if rng.random() < fracao_reenvio:
                        reenvios[destino].append(e)
                        duplicatas += 1
        for i, (lote, extra) in enumerate(zip(lotes, reenvios), start=1):
            por_nome: dict[str, list[dict]] = defaultdict(list)
            for e in lote + extra:
                por_nome[pasta(e["event_name"], dt)].append(e)
            for destino_pasta, do_nome in sorted(por_nome.items()):
                arquivos[f"{destino_pasta}/{origem}-s{seed}-{i:03d}.jsonl"] = serializar(do_nome)
    return arquivos, duplicatas
