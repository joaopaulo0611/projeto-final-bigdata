from datetime import datetime, timezone

import pytest

from gerador.gerar_eventos import gerar, main

DATA = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _gerar(seed):
    return gerar(seed=seed, dias=3, visitantes=200, sujeira=0.03, data_inicial=DATA)


def test_mesma_seed_gera_os_mesmos_arquivos():
    assert _gerar(5)[0] == _gerar(5)[0]


def test_seeds_diferentes_geram_conteudo_diferente():
    assert set(_gerar(5)[0].values()) != set(_gerar(6)[0].values())


def test_resumo_bate_com_as_linhas_gravadas():
    arquivos, r = _gerar(5)
    linhas = sum(len(v.splitlines()) for v in arquivos.values())
    inseridos = r["sujeira"]["refund_orfao"] + r["sujeira"]["evento_fora_catalogo"]
    assert linhas == r["linhas_gravadas"] == r["eventos_limpos"] + inseridos + r["duplicatas_reenvio"]
    assert r["visitantes"] == 200
    assert r["arquivos"] == len(arquivos)
    assert sum(r["por_evento"].values()) == r["eventos_limpos"]
    assert r["periodo"] == "2026-09-01 a 2026-09-03"


def test_main_grava_na_pasta_local_e_imprime_resumo(tmp_path, capsys):
    assert main(["--dias", "2", "--visitantes", "50", "--saida-local", str(tmp_path)]) == 0
    assert list(tmp_path.glob("landing/event_name=*/year=*/month=*/day=*/coletor-s42-*.jsonl"))
    saida = capsys.readouterr().out
    assert "eventos limpos" in saida
    assert str(tmp_path.resolve()) in saida


def test_main_recusa_fracao_de_sujeira_absurda(tmp_path):
    with pytest.raises(SystemExit):
        main(["--sujeira", "0.9", "--saida-local", str(tmp_path)])


def test_main_recusa_data_inicial_invalida(tmp_path):
    with pytest.raises(SystemExit):
        main(["--data-inicial", "2026-9-1x", "--saida-local", str(tmp_path)])
