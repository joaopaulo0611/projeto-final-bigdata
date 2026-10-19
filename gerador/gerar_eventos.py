"""Simula o coletor de tracking da landing DadosPro e grava na landing do datalake.

    python gerador/gerar_eventos.py                       # 6000 visitantes, 14 dias, no S3 (floci)
    python gerador/gerar_eventos.py --seed 7 --sujeira 0.05
    python gerador/gerar_eventos.py --saida-local saida   # numa pasta, sem S3

Não depende do pipeline nem do Spark. A mesma seed gera exatamente os mesmos arquivos.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gerador import catalogo as cat
from gerador.destinos import DestinoLocal, DestinoS3
from gerador.elementos import marcar_elementos
from gerador.jornadas import simular
from gerador.lotes import montar_lotes
from gerador.sujeira import aplicar_sujeira

DATA_PADRAO = "2026-09-01"


def gerar(seed: int = 42, dias: int = 14, visitantes: int = 6000, sujeira: float = 0.03,
          data_inicial: datetime = datetime(2026, 9, 1, tzinfo=timezone.utc)) -> tuple[dict[str, str], dict]:
    """Devolve ({chave: conteúdo JSONL}, resumo)."""
    eventos, sessoes, rng = simular(seed, dias, visitantes, data_inicial)
    for e in eventos:
        e["_dt"] = e["event_ts"][:10]           # dia de coleta, antes de a sujeira mexer no timestamp
    por_evento = Counter(e["event_name"] for e in eventos)
    eventos_limpos = len(eventos)
    defeitos = aplicar_sujeira(rng, eventos, sujeira)
    marcar_elementos(eventos)                 # determinístico: não mexe no rng
    arquivos, duplicatas = montar_lotes(rng, eventos, origem="coletor", seed=seed)

    ultimo_dia = data_inicial + timedelta(days=dias - 1)
    resumo = {
        "seed": seed,
        "periodo": f"{data_inicial:%Y-%m-%d} a {ultimo_dia:%Y-%m-%d}",
        "visitantes": visitantes,
        "sessoes_simuladas": sessoes,
        "eventos_limpos": eventos_limpos,
        "por_evento": {nome: por_evento.get(nome, 0) for nome in cat.EVENTOS},
        "sujeira": defeitos,
        "duplicatas_reenvio": duplicatas,
        "linhas_gravadas": sum(len(v.splitlines()) for v in arquivos.values()),
        "arquivos": len(arquivos),
    }
    return arquivos, resumo


def imprimir_resumo(r: dict, destino: str) -> None:
    print(f"Destino:            {destino}")
    print(f"Período:            {r['periodo']}   seed: {r['seed']}")
    print(f"visitantes          {r['visitantes']:>8}")
    print(f"sessões simuladas   {r['sessoes_simuladas']:>8}")
    print(f"eventos limpos      {r['eventos_limpos']:>8}")
    print(f"duplicatas (lote)   {r['duplicatas_reenvio']:>8}")
    print(f"linhas gravadas     {r['linhas_gravadas']:>8}   em {r['arquivos']} arquivos")
    print("\nEventos por nome (antes da sujeira):")
    for nome, n in r["por_evento"].items():
        print(f"  {nome:<20}{n:>8}")
    print("\nDefeitos injetados:")
    for tipo, n in r["sujeira"].items():
        print(f"  {tipo:<20}{n:>8}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--visitantes", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sujeira", type=float, default=0.03, help="fração de eventos com defeito (0 a 0.5)")
    ap.add_argument("--data-inicial", default=DATA_PADRAO, help="AAAA-MM-DD, em UTC")
    ap.add_argument("--saida-local", type=Path, help="grava nesta pasta em vez do S3")
    a = ap.parse_args(argv)
    if not 0 <= a.sujeira <= 0.5:
        ap.error("--sujeira precisa estar entre 0 e 0.5")
    if a.dias < 1 or a.visitantes < 1:
        ap.error("--dias e --visitantes precisam ser positivos")
    try:
        data = datetime.strptime(a.data_inicial, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        ap.error("--data-inicial precisa estar no formato AAAA-MM-DD")

    arquivos, resumo = gerar(a.seed, a.dias, a.visitantes, a.sujeira, data)
    destino = DestinoLocal(a.saida_local) if a.saida_local else DestinoS3()
    for chave, conteudo in arquivos.items():
        destino.gravar(chave, conteudo)
    imprimir_resumo(resumo, destino.descricao())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
