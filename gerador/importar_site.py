"""Sobe para a landing do datalake o JSONL exportado pela página site/index.html.

    python gerador/importar_site.py eventos_2026-10-10.jsonl
    python gerador/importar_site.py eventos.jsonl --saida-local saida
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gerador.destinos import DestinoLocal, DestinoS3
from gerador.lotes import pasta


def validar(texto: str) -> list[dict]:
    return [evento for _, evento in _linhas_validas(texto)]


def _linhas_validas(texto: str) -> list[tuple[str, dict]]:
    """Devolve (linha original, evento) de cada linha não vazia, ou ValueError com o número da linha."""
    eventos = []
    for n, linha in enumerate(texto.split("\n"), start=1):
        linha = linha.removesuffix("\r")
        if not linha.strip():
            continue
        try:
            evento = json.loads(linha)
        except json.JSONDecodeError as erro:
            raise ValueError(f"linha {n}: JSON inválido ({erro.msg})") from None
        if not isinstance(evento, dict) or not isinstance(evento.get("event_id"), str) \
                or not isinstance(evento.get("event_ts"), str):
            raise ValueError(f"linha {n}: falta event_id ou event_ts")
        eventos.append((linha, evento))
    if not eventos:
        raise ValueError("arquivo sem eventos")
    return eventos


def arquivos(texto: str, agora: datetime) -> dict[str, str]:
    """{chave na landing: conteúdo}: um arquivo por event_name, todos na data do primeiro evento."""
    linhas = _linhas_validas(texto)
    data = linhas[0][1]["event_ts"]
    por_pasta: dict[str, list[str]] = {}
    for linha, evento in linhas:
        por_pasta.setdefault(pasta(evento.get("event_name"), data), []).append(linha)
    nome = f"site-{agora:%Y%m%dT%H%M%S%f}.jsonl"
    return {f"{p}/{nome}": "\n".join(ls) + "\n" for p, ls in sorted(por_pasta.items())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("arquivo", type=Path, help="JSONL exportado pelo botão 'Exportar JSONL' do site")
    ap.add_argument("--saida-local", type=Path, help="grava nesta pasta em vez do S3")
    a = ap.parse_args(argv)

    try:
        texto = a.arquivo.read_text(encoding="utf-8-sig")
        gerados = arquivos(texto, datetime.now(timezone.utc))
    except (OSError, UnicodeDecodeError, ValueError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1

    destino = DestinoLocal(a.saida_local) if a.saida_local else DestinoS3()
    for k, conteudo in gerados.items():
        destino.gravar(k, conteudo)
        print(f"{len(conteudo.splitlines()):>5} eventos enviados para {destino.descricao()} em {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
