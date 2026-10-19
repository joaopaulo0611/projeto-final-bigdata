"""Preferências de quem usa o console: tutorial e acessibilidade.

Ficam num JSON local fora do git (.explorador/preferencias.json) e valem também depois de reiniciar o
explorador. Sem Streamlit aqui: só ler, validar e gravar.
"""

from __future__ import annotations

import json
from pathlib import Path

TAMANHOS = (100, 115, 130)            # tamanho do texto, em % do normal

PADRAO = {
    "tutorial": True,                 # abre o tour na primeira visita a cada tela
    "texto": 100,                     # um dos TAMANHOS
    "contraste": False,               # alto contraste: textos e bordas mais escuros
    "sublinhar": False,               # sublinha links e botões de link
    "espacamento": False,             # mais espaço entre letras, palavras e linhas (ajuda na dislexia)
    "movimento": False,               # reduzir movimento: sem animações nem rolagem suave
}


def _valido(chave: str, valor) -> bool:
    if type(valor) is not type(PADRAO[chave]):                 # bool não passa por int e vice-versa
        return False
    return chave != "texto" or valor in TAMANHOS


def carregar(arquivo: Path) -> dict:
    """Preferências salvas; o que faltar, estiver estragado ou fora do esperado volta ao padrão."""
    try:
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        return {**PADRAO, **{k: v for k, v in dados.items() if k in PADRAO and _valido(k, v)}}
    except (OSError, ValueError, AttributeError):
        return dict(PADRAO)


def salvar(arquivo: Path, preferencias: dict) -> None:
    arquivo = Path(arquivo)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    dados = {k: preferencias.get(k, v) for k, v in PADRAO.items()}
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
