import json
from datetime import datetime, timezone

import pytest

from gerador.importar_site import arquivos, main, validar

UM = '{"event_id":"a","event_ts":"2026-10-10T12:00:00.000Z"}'


def test_validar_aceita_o_jsonl_do_site_e_ignora_linhas_vazias():
    eventos = validar(UM + '\n\n{"event_id":"b","event_ts":"2026-10-10T12:00:01.000Z"}\n')
    assert [e["event_id"] for e in eventos] == ["a", "b"]


@pytest.mark.parametrize("texto, mensagem", [
    ("isto não é json\n", "linha 1: JSON inválido"),
    ('{"event_id":"a"}\n', "linha 1: falta event_id ou event_ts"),
    (UM + "\n[1, 2]\n", "linha 2: falta event_id ou event_ts"),
    ("\n\n", "arquivo sem eventos"),
])
def test_validar_rejeita_com_a_linha_do_problema(texto, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        validar(texto)


def test_um_arquivo_por_event_name_na_data_do_primeiro_evento():
    agora = datetime(2026, 10, 11, 8, 30, 0, tzinfo=timezone.utc)
    texto = (
        '{"event_id":"a","event_ts":"2026-10-10T23:59:00.000Z","event_name":"page_view"}\n'
        '{"event_id":"b","event_ts":"2026-10-11T00:01:00.000Z","event_name":"scroll"}\n'
        '{"event_id":"c","event_ts":"2026-10-11T00:02:00.000Z","event_name":"page_view"}\n'
        '{"event_id":"d","event_ts":"2026-10-11T00:03:00.000Z"}\n'
    )
    gerados = arquivos(texto, agora)
    nome = "year=2026/month=10/day=10/site-20261011T083000000000.jsonl"
    assert sorted(gerados) == [
        f"landing/event_name=__HIVE_DEFAULT_PARTITION__/{nome}",
        f"landing/event_name=page_view/{nome}",
        f"landing/event_name=scroll/{nome}",
    ]
    assert [json.loads(l)["event_id"] for l in gerados[f"landing/event_name=page_view/{nome}"].splitlines()] == ["a", "c"]


def test_main_grava_o_arquivo_na_landing(tmp_path):
    origem = tmp_path / "eventos.jsonl"
    origem.write_text(UM + "\n", encoding="utf-8")
    assert main([str(origem), "--saida-local", str(tmp_path / "s3")]) == 0
    gravados = list((tmp_path / "s3").glob("landing/event_name=*/year=2026/month=10/day=10/site-*.jsonl"))
    assert len(gravados) == 1
    assert gravados[0].read_text(encoding="utf-8") == UM + "\n"


def test_main_devolve_1_e_explica_quando_o_arquivo_e_invalido(tmp_path, capsys):
    origem = tmp_path / "ruim.jsonl"
    origem.write_text("{quebrado\n", encoding="utf-8")
    assert main([str(origem), "--saida-local", str(tmp_path / "s3")]) == 1
    assert "linha 1" in capsys.readouterr().err
    assert not (tmp_path / "s3").exists()


def test_validar_aceita_texto_com_crlf():
    assert len(validar(UM + "\r\n" + UM.replace('"a"', '"b"') + "\r\n")) == 2


def test_validar_aceita_u2028_cru_dentro_de_string():
    linha = '{"event_id":"a","event_ts":"2026-10-10T12:00:00.000Z","params":{"search_term":"x y"}}'
    assert len(validar(linha + "\n")) == 1


def test_main_aceita_arquivo_com_bom_e_grava_sem_bom(tmp_path):
    origem = tmp_path / "eventos.jsonl"
    origem.write_bytes(("﻿" + UM + "\n").encode("utf-8"))
    assert main([str(origem), "--saida-local", str(tmp_path / "s3")]) == 0
    gravados = list((tmp_path / "s3").glob("landing/event_name=*/year=2026/month=10/day=10/site-*.jsonl"))
    assert len(gravados) == 1
    assert gravados[0].read_text(encoding="utf-8") == UM + "\n"


def test_main_devolve_1_quando_o_arquivo_nao_existe(tmp_path, capsys):
    assert main([str(tmp_path / "nao_existe.jsonl"), "--saida-local", str(tmp_path / "s3")]) == 1
    assert "erro" in capsys.readouterr().err
