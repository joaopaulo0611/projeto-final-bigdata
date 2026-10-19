"""Tipos das colunas, do jeito que o DuckDB descreve (DESCRIBE), resumidos para caber na tela.

Uma coluna STRUCT pode ter um tipo enorme: STRUCT(page VARCHAR, "user" STRUCT(id BIGINT, …), …).
Na tabela aparece só `struct`; a tipagem interna vira uma árvore, mostrada num overlay.
"""

from __future__ import annotations

Campo = tuple[str, str, list]          # (nome, tipo resumido, campos internos)


def _partes(texto: str) -> list[str]:
    """Divide pelas vírgulas que estão fora de parênteses e de aspas."""
    partes, atual, nivel, aspas = [], "", 0, False
    for c in texto:
        if c == '"':
            aspas = not aspas
        elif not aspas and c == "(":
            nivel += 1
        elif not aspas and c == ")":
            nivel -= 1
        elif not aspas and nivel == 0 and c == ",":
            partes.append(atual.strip())
            atual = ""
            continue
        atual += c
    if atual.strip():
        partes.append(atual.strip())
    return partes


def _fecha(texto: str, abre: int) -> int:
    """Posição do ")" que fecha o "(" em `abre` (ignorando o que está entre aspas)."""
    nivel, aspas = 0, False
    for i in range(abre, len(texto)):
        c = texto[i]
        if c == '"':
            aspas = not aspas
        elif not aspas and c == "(":
            nivel += 1
        elif not aspas and c == ")":
            nivel -= 1
            if nivel == 0:
                return i
    return len(texto) - 1


def _structs(tipo: str) -> list[tuple[int, int]]:
    """(início, fim) de cada STRUCT(...) do primeiro nível dentro do tipo."""
    achados, i, alto = [], 0, tipo.upper()
    while (i := alto.find("STRUCT(", i)) != -1:
        fim = _fecha(tipo, i + len("STRUCT"))
        achados.append((i, fim))
        i = fim + 1
    return achados


def tem_struct(tipo: str) -> bool:
    return bool(_structs(tipo))


def curto(tipo: str) -> str:
    """O tipo com cada STRUCT(...) trocado pela palavra `struct`, em minúsculas."""
    resumo, ultimo = "", 0
    for inicio, fim in _structs(tipo):
        resumo += tipo[ultimo:inicio] + "struct"
        ultimo = fim + 1
    return (resumo + tipo[ultimo:]).lower()


def _nome_e_tipo(campo: str) -> tuple[str, str]:
    if campo.startswith('"'):
        fim = campo.index('"', 1)
        return campo[1:fim], campo[fim + 1:].strip()
    nome, _, tipo = campo.partition(" ")
    return nome, tipo.strip()


def campos(tipo: str) -> list[Campo]:
    """Campos internos do primeiro STRUCT do tipo (também dentro de lista ou map), em árvore."""
    achados = _structs(tipo)
    if not achados:
        return []
    inicio, fim = achados[0]
    corpo = tipo[inicio + len("STRUCT("):fim]
    saida = []
    for campo in _partes(corpo):
        nome, tipo_campo = _nome_e_tipo(campo)
        saida.append((nome, curto(tipo_campo), campos(tipo_campo)))
    return saida


def arvore_markdown(tipo: str) -> str:
    """Lista em markdown, um nível de recuo por struct, para o overlay da tipagem interna."""
    def linhas(itens: list[Campo], nivel: int):
        for nome, tipo_campo, internos in itens:
            yield f"{'    ' * nivel}- `{nome}` {tipo_campo}"
            yield from linhas(internos, nivel + 1)
    return "\n".join(linhas(campos(tipo), 0))
