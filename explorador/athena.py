"""Lógica da tela "Editor de consultas" (no estilo do Athena), sem Streamlit: abas, histórico e
a estimativa de dados lidos. Tudo puro, para ser testado sem abrir o site."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from explorador import consultas
from explorador.particoes import SEM_PARTICAO, Dataset, Objeto, tabela_particoes, tamanho_legivel


@dataclass
class Execucao:
    sql: str
    status: str               # "Concluída" ou "Falhou"
    quando: str               # hora local, "HH:MM:SS"
    segundos: float
    linhas: int
    bytes: int                # dados lidos (estimado)
    erro: str | None = None


@dataclass
class Aba:
    nome: str
    sql: str = ""
    resultado: object = None                  # consultas.Resultado da última execução bem-sucedida
    execucao: Execucao | None = None
    limite: int = field(default=consultas.LIMITE_PADRAO)
    erro_original: str | None = None          # mensagem do DuckDB (em inglês) da última falha


def nova_aba(abas: list[Aba]) -> list[Aba]:
    """Acrescenta "Consulta N", com N sempre maior que o de qualquer aba existente."""
    numeros = [int(m.group(1)) for a in abas if (m := re.fullmatch(r"Consulta (\d+)", a.nome))]
    return abas + [Aba(f"Consulta {max(numeros, default=0) + 1}")]


def fechar_aba(abas: list[Aba], indice: int) -> tuple[list[Aba], int]:
    """Fecha a aba `indice` (a última aba nunca fecha). Devolve (abas, índice da aba ativa)."""
    if len(abas) <= 1:
        return abas, 0
    restantes = abas[:indice] + abas[indice + 1:]
    return restantes, min(indice, len(restantes) - 1)


def inserir(sql: str, texto: str) -> str:
    """Põe `texto` no fim do SQL, com um espaço se precisar (botão "Inserir" da árvore de tabelas)."""
    if not sql or sql[-1].isspace():
        return sql + texto
    return f"{sql} {texto}"


def views_usadas(sql: str, nomes_views: list[str]) -> list[str]:
    """Views citadas no SQL, lidas com o tokenizer do DuckDB (strings e comentários não contam)."""
    try:
        tokens = consultas._tokens(sql)
    except consultas.SqlNaoPermitido:
        return []
    conhecidas = {n.lower(): n for n in nomes_views}

    def palavra(i: int) -> str | None:
        if i >= len(tokens) or tokens[i][0] not in ("identifier", "keyword"):
            return None
        achada = re.match(r'\s*"?([A-Za-z_][A-Za-z0-9_]*)"?', tokens[i][1])
        return achada.group(1).lower() if achada else None

    achadas, i = set(), 0
    while i < len(tokens):
        banco = palavra(i)
        ponto = i + 1 < len(tokens) and tokens[i + 1][1].strip() == "."
        tabela = palavra(i + 2) if ponto else None
        if banco and tabela and f"{banco}.{tabela}" in conhecidas:     # banco.tabela, com ou sem aspas
            achadas.add(conhecidas[f"{banco}.{tabela}"])
            i += 3
            continue
        i += 1
    return sorted(achadas)


def particoes_filtradas(sql: str) -> set[str] | None:
    """Valores de event_name fixados no WHERE (`= 'x'` ou `IN ('x', 'y')`); None se não houver filtro.

    É o que o Athena usa para pular partições inteiras ("partition pruning")."""
    sem_comentarios = re.sub(r"/\*.*?\*/", " ", re.sub(r"--[^\n\r]*", " ", sql), flags=re.S)
    valores = set(re.findall(r"\bevent_name\s*=\s*'([^']*)'", sem_comentarios, flags=re.I))
    for lista in re.findall(r"\bevent_name\s+in\s*\(([^)]*)\)", sem_comentarios, flags=re.I):
        valores |= set(re.findall(r"'([^']*)'", lista))
    return valores or None


def bytes_lidos(views: list[str], datasets: list[Dataset], objetos: list[Objeto], sql: str = "") -> int:
    """Estimativa do "Dados verificados" do Athena: soma dos arquivos das views usadas.

    Se o SQL filtra event_name por valores fixos, só contam as partições desses eventos."""
    filtro = particoes_filtradas(sql)
    total = 0
    for d in datasets:
        if d.nome_view not in views:
            continue
        for linha in tabela_particoes(objetos, d.prefixo, d.formato):
            if filtro is None or linha.event_name == SEM_PARTICAO or linha.event_name in filtro:
                total += linha.bytes
    return total


def registrar(historico: list[Execucao], execucao: Execucao, maximo: int = 50) -> list[Execucao]:
    """Consultas recentes: a mais nova primeiro, no máximo `maximo`."""
    return ([execucao] + historico)[:maximo]


def resumo(e: Execucao) -> str:
    tempo = f"tempo de execução {e.segundos:.2f} s".replace(".", ",")
    if e.status != "Concluída":
        return f"{e.status} · {tempo} · {e.erro}"
    return f"{e.status} · {tempo} · {e.linhas} linhas · dados lidos (estimado) {tamanho_legivel(e.bytes)}"
