"""Consultas SQL no bucket com DuckDB — somente leitura.

A validação lê o SQL com o tokenizer do próprio DuckDB e confirma com o parser dele
(1 comando, só SELECT/EXPLAIN)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import duckdb
import pandas as pd

from explorador.particoes import Dataset, banco_e_tabela, formato_do_arquivo, sql_nome

MENSAGEM_SO_LEITURA = "O explorador só faz consultas de leitura (SELECT, WITH, DESCRIBE…)."
MENSAGEM_UM_COMANDO = "Rode um comando por vez (sem `;` no meio)."
MENSAGEM_EXPLAIN_ANALYZE = "`EXPLAIN ANALYZE` não é aceito: ele executa o comando de verdade. Use só `EXPLAIN`."
INICIOS_PERMITIDOS = ("select", "with", "describe", "show", "summarize", "from", "explain", "pragma")
PROIBIDAS = ("copy", "attach", "detach", "install", "load", "create", "drop", "insert", "update",
             "delete", "alter", "export", "import", "set", "call", "checkpoint", "vacuum", "use")
TIPOS_DE_PALAVRA = ("keyword", "identifier")


class SqlNaoPermitido(ValueError):
    """SQL que o explorador não executa; a mensagem vai direto para o usuário."""


def _tokens(sql: str) -> list[tuple[str, str]]:
    """Separa o SQL com o leitor (tokenizer) do próprio DuckDB: devolve pares (tipo, texto).

    Comentários não viram token e o texto de cada token vai até o início do próximo,
    então o que importa é só a primeira palavra de cada um."""
    try:
        brutos = duckdb.tokenize(sql)
    except Exception as erro:  # noqa: BLE001 — qualquer falha do leitor vira recusa amigável
        raise SqlNaoPermitido("Não consegui ler esse SQL. Confira a escrita e tente de novo.") from erro
    # As posições vêm em bytes (UTF-8), não em caracteres: "comentário" ocupa 11 bytes.
    dados = sql.encode("utf-8")
    tokens = []
    for i, (inicio, tipo) in enumerate(brutos):
        fim = brutos[i + 1][0] if i + 1 < len(brutos) else len(dados)
        tokens.append((getattr(tipo, "name", str(tipo)), dados[inicio:fim].decode("utf-8", "replace")))
    return tokens


def validar_sql(sql: str) -> None:
    """Recusa o que não é uma única consulta de leitura; o último passo confirma com o parser do DuckDB."""
    tokens = _tokens(sql)
    # Palavras de código (palavras-chave e nomes sem aspas); strings e comentários ficam de fora.
    palavras = []
    for tipo, texto in tokens:
        palavra = re.match(r"[a-z_][a-z0-9_]*", texto.lower())
        if tipo in TIPOS_DE_PALAVRA and palavra:
            palavras.append(palavra.group())
    pontos_e_virgula = [i for i, (tipo, texto) in enumerate(tokens)
                        if tipo == "operator" and texto.lstrip().startswith(";")]
    ultimo_codigo = max((i for i in range(len(tokens)) if i not in pontos_e_virgula), default=-1)
    if ultimo_codigo < 0:
        raise SqlNaoPermitido("Escreva uma consulta SQL.")
    if any(i < ultimo_codigo for i in pontos_e_virgula):
        raise SqlNaoPermitido(MENSAGEM_UM_COMANDO)
    primeira = palavras[0] if palavras else ""
    if primeira not in INICIOS_PERMITIDOS:
        raise SqlNaoPermitido(MENSAGEM_SO_LEITURA)
    if primeira == "pragma" and palavras[1:2] != ["table_info"]:
        raise SqlNaoPermitido(MENSAGEM_SO_LEITURA)
    proibida = next((p for p in palavras if p in PROIBIDAS), None)
    if proibida:
        raise SqlNaoPermitido(f"{MENSAGEM_SO_LEITURA} O comando `{proibida.upper()}` não é permitido.")
    if primeira == "explain" and ("analyze" in palavras or "analyse" in palavras):
        raise SqlNaoPermitido(MENSAGEM_EXPLAIN_ANALYZE)
    # Confirmação autoritativa com o parser do DuckDB.
    try:
        comandos = duckdb.extract_statements(sql)
    except duckdb.Error:
        return  # erro de sintaxe: deixa o DuckDB explicar na execução
    if len(comandos) != 1:
        raise SqlNaoPermitido(MENSAGEM_UM_COMANDO)
    tipo = comandos[0].type.name
    if tipo not in ("SELECT", "EXPLAIN"):
        raise SqlNaoPermitido(f"{MENSAGEM_SO_LEITURA} O comando `{tipo}` não é permitido.")


LIMITE_PADRAO = 1000
LIMITE_MAXIMO = 50_000
LINHAS_PREVIA = 100
OPCOES_LEITURA = "hive_partitioning=true, hive_types_autocast=false, union_by_name=true"


@dataclass
class Resultado:
    tabela: pd.DataFrame
    cortado: bool
    colunas: list[str]


EXPLICACOES_DE_ERRO = (
    ("CatalogException", "Essa tabela ou view não existe. Confira o nome na lista de tabelas, à esquerda do editor."),
    ("BinderException", "Alguma coluna ou função não foi encontrada. Confira os nomes das colunas da view."),
    ("ParserException", "O SQL tem um erro de escrita (vírgula, parêntese ou palavra fora do lugar)."),
    ("ConversionException", "Um valor não pôde ser convertido para o tipo pedido (ex.: texto para número)."),
    ("PermissionException", "Esse acesso é bloqueado: o explorador só lê os arquivos do bucket."),
    ("HTTPException", "O S3 recusou ou não respondeu à leitura. Confira se o floci está ligado."),
    ("IOException", "Não consegui ler os arquivos. Talvez a pasta tenha mudado: clique em Recarregar."),
    ("OutOfMemoryException", "A consulta precisou de memória demais. Filtre mais ou agrupe os dados."),
    ("InvalidInputException", "Algum valor ou argumento da consulta é inválido."),
)


def explicar_erro(erro: Exception) -> str:
    """Traduz o tipo de erro do DuckDB numa frase em português (a mensagem original fica à parte)."""
    nomes = {c.__name__ for c in type(erro).__mro__}
    return next((texto for nome, texto in EXPLICACOES_DE_ERRO if nome in nomes),
                "O DuckDB não conseguiu rodar a consulta.")


def _texto_sql(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def conectar(s3: bool = True, endpoint: str = "http://floci:4566", chave: str = "test",
             segredo: str = "test", regiao: str = "us-east-1") -> duckdb.DuckDBPyConnection:
    """Conexão DuckDB em memória. Com s3=True, aponta o S3 do DuckDB para o floci."""
    con = duckdb.connect()
    # Se precisar gravar temporários, o DuckDB usa /tmp do contêiner, nunca a pasta do projeto.
    con.sql("SET temp_directory = '/tmp/duckdb'")
    if s3:
        con.sql("LOAD httpfs")
        ssl = endpoint.startswith("https://")
        host = endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
        con.sql(
            "CREATE OR REPLACE SECRET floci (TYPE s3, "
            f"KEY_ID {_texto_sql(chave)}, SECRET {_texto_sql(segredo)}, REGION {_texto_sql(regiao)}, "
            f"ENDPOINT {_texto_sql(host)}, URL_STYLE 'path', USE_SSL {'true' if ssl else 'false'})"
        )
    return con


def _raiz_do_dataset(raiz, dataset: Dataset) -> str:
    """`raiz` é a do bucket do datalake (texto) ou uma função bucket -> raiz (None = datalake)."""
    if callable(raiz):
        return raiz(dataset.bucket)
    return raiz if dataset.bucket is None else f"s3://{dataset.bucket}"


def origem(raiz, dataset: Dataset) -> str:
    """A leitura de um dataset (read_parquet ou read_json_auto), usada nas views e na contagem por partição."""
    extensao = "parquet" if dataset.formato == "parquet" else "jsonl"
    funcao = "read_parquet" if dataset.formato == "parquet" else "read_json_auto"
    # Particionado: só as pastas k=v, para não misturar as vizinhas (silver/itens ao lado de silver/event_name=…).
    pastas = "*=*/**" if dataset.particionado else "**"
    base = _raiz_do_dataset(raiz, dataset).rstrip("/")
    if dataset.caminho:
        base = f"{base}/{dataset.caminho}"
    padrao = f"{base}/{pastas}/*.{extensao}"
    return f"{funcao}({_texto_sql(padrao)}, {OPCOES_LEITURA})"


def criar_views(con: duckdb.DuckDBPyConnection, raiz, datasets: list[Dataset]) -> dict[str, str]:
    """Uma view por dataset, num schema por banco (como os bancos do Glue): silver.eventos, gold.funil_compra…

    `raiz`: a do bucket do datalake, ou uma função bucket -> raiz para os datasets de outros buckets."""
    views = {}
    for dataset in datasets:
        leitura = origem(raiz, dataset)
        banco, _ = banco_e_tabela(dataset.nome_view)
        con.sql(f'CREATE SCHEMA IF NOT EXISTS "{banco}"')
        con.sql(f"CREATE OR REPLACE VIEW {sql_nome(dataset.nome_view)} AS SELECT * FROM {leitura}")
        views[dataset.nome_view] = leitura
    return views


def travar(con: duckdb.DuckDBPyConnection, raizes: str | Iterable[str]) -> None:
    """Depois das views: só deixa ler dentro das raízes dos buckets e congela a configuração."""
    pastas = [raizes] if isinstance(raizes, str) else list(raizes)
    lista = ", ".join(_texto_sql(p.rstrip("/") + "/") for p in pastas)
    con.sql(f"SET allowed_directories = [{lista}]")
    con.sql("SET enable_external_access = false")
    con.sql("SET lock_configuration = true")


def executar(con: duckdb.DuckDBPyConnection, sql: str, limite: int = LIMITE_PADRAO) -> Resultado:
    validar_sql(sql)
    limite = max(1, min(int(limite), LIMITE_MAXIMO))
    relacao = con.sql(sql)
    if relacao is None:
        return Resultado(pd.DataFrame(), False, [])
    tabela = relacao.limit(limite + 1).df()
    cortado = len(tabela) > limite
    tabela = tabela.head(limite)
    return Resultado(tabela, cortado, list(tabela.columns))


def previa(con: duckdb.DuckDBPyConnection, raiz: str, chave: str, linhas: int = LINHAS_PREVIA) -> pd.DataFrame:
    formato = formato_do_arquivo(chave)
    if formato is None:
        raise ValueError("Prévia só para arquivos .parquet e .jsonl.")
    if ".." in chave.split("/"):
        raise ValueError("Prévia só para arquivos dentro do bucket.")
    funcao = "read_parquet" if formato == "parquet" else "read_json_auto"
    caminho = f"{raiz.rstrip('/')}/{chave}"
    return con.sql(f"SELECT * FROM {funcao}({_texto_sql(caminho)}) LIMIT {int(linhas)}").df()
