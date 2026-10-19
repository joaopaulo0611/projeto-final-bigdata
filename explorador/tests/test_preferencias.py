from explorador import preferencias
from explorador.preferencias import PADRAO


def test_sem_arquivo_vale_o_padrao(tmp_path):
    assert preferencias.carregar(tmp_path / "nao_existe.json") == PADRAO
    assert PADRAO["tutorial"] is True and PADRAO["texto"] == 100


def test_salvar_e_carregar_preferencias(tmp_path):
    arquivo = tmp_path / "pasta" / "preferencias.json"
    escolhas = {**PADRAO, "tutorial": False, "texto": 130, "contraste": True, "movimento": True}
    preferencias.salvar(arquivo, escolhas)
    assert preferencias.carregar(arquivo) == escolhas


def test_salvar_grava_so_as_chaves_conhecidas(tmp_path):
    arquivo = tmp_path / "preferencias.json"
    preferencias.salvar(arquivo, {"tutorial": False, "outra": 1})
    assert preferencias.carregar(arquivo) == {**PADRAO, "tutorial": False}
    assert "outra" not in arquivo.read_text(encoding="utf-8")


def test_arquivo_estragado_volta_ao_padrao(tmp_path):
    arquivo = tmp_path / "preferencias.json"
    arquivo.write_text("{isto não é json", encoding="utf-8")
    assert preferencias.carregar(arquivo) == PADRAO


def test_valores_invalidos_voltam_ao_padrao(tmp_path):
    arquivo = tmp_path / "preferencias.json"
    arquivo.write_text('{"texto": 999, "contraste": "sim", "sublinhar": 1, "tutorial": false}', encoding="utf-8")
    assert preferencias.carregar(arquivo) == {**PADRAO, "tutorial": False}


def test_arquivo_antigo_so_com_tutorial_continua_valendo(tmp_path):
    arquivo = tmp_path / "preferencias.json"
    arquivo.write_text('{"tutorial": false}', encoding="utf-8")
    assert preferencias.carregar(arquivo) == {**PADRAO, "tutorial": False}
