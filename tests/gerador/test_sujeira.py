import copy
import math
import random
from collections import Counter

from gerador.sujeira import TIPOS, aplicar_sujeira


def test_total_de_defeitos_respeita_a_fracao_e_todos_os_tipos_aparecem(simulacao):
    eventos = copy.deepcopy(simulacao[0])
    n = len(eventos)
    contagem = aplicar_sujeira(random.Random(1), eventos, 0.03)
    assert set(contagem) == set(TIPOS)
    assert sum(contagem.values()) == round(n * 0.03)
    assert all(contagem[t] > 0 for t in TIPOS)
    assert len(eventos) == n + contagem["refund_orfao"] + contagem["evento_fora_catalogo"]


def test_compras_sem_id_ficam_limitadas_a_5_por_cento(simulacao):
    eventos = copy.deepcopy(simulacao[0])
    compras = sum(1 for e in eventos if e["event_name"] == "purchase")
    contagem = aplicar_sujeira(random.Random(1), eventos, 0.03)
    assert contagem["purchase_sem_id"] <= -(-compras * 5 // 100)


def test_reembolsos_orfaos_ficam_limitados_a_5_por_cento_das_compras(simulacao):
    eventos = copy.deepcopy(simulacao[0])
    compras = sum(1 for e in eventos if e["event_name"] == "purchase")
    contagem = aplicar_sujeira(random.Random(1), eventos, 0.03)
    assert contagem["refund_orfao"] <= -(-compras * 5 // 100)
    assert contagem["refund_orfao"] > 0


def test_cada_defeito_e_visivel_no_dado(simulacao):
    eventos = copy.deepcopy(simulacao[0])
    ids_compra = {e["params"]["transaction_id"] for e in eventos if e["event_name"] == "purchase"}
    aplicar_sujeira(random.Random(1), eventos, 0.03)
    assert any(e["event_ts"] is None for e in eventos)
    assert any(e["event_ts"] is not None and e["event_ts"] > "2030" for e in eventos)
    assert any(e["event_name"] == "purchase" and e["params"]["transaction_id"] is None for e in eventos)
    assert any(isinstance(e["params"].get("value"), float) and e["params"]["value"] < 0 for e in eventos)
    assert any(e["params"].get("currency") == "USD" for e in eventos)
    assert any(e["event_name"] == "scroll" and e["params"]["percent_scrolled"] == 33 for e in eventos)
    assert any(e["event_name"] == "add_to_wishlist" for e in eventos)
    assert any(e["event_name"] == "refund" and e["params"]["transaction_id"] not in ids_compra for e in eventos)


def test_um_evento_recebe_no_maximo_um_defeito(simulacao):
    eventos = copy.deepcopy(simulacao[0])
    aplicar_sujeira(random.Random(1), eventos, 0.03)
    for e in eventos:
        defeitos = [
            e["event_ts"] is None,
            e["event_ts"] is not None and e["event_ts"] > "2030",
            e["params"].get("currency") == "USD",
            isinstance(e["params"].get("value"), float) and e["params"]["value"] < 0,
        ]
        assert sum(defeitos) <= 1


def test_fracao_zero_nao_altera_nada(simulacao):
    eventos = copy.deepcopy(simulacao[0])
    contagem = aplicar_sujeira(random.Random(1), eventos, 0.0)
    assert sum(contagem.values()) == 0
    assert eventos == simulacao[0]


def test_cada_nome_de_evento_recebe_no_maximo_5_por_cento_de_mutacoes(simulacao):
    eventos = copy.deepcopy(simulacao[0])
    antes = {e["event_id"]: copy.deepcopy(e) for e in eventos}
    total = Counter(e["event_name"] for e in eventos)
    aplicar_sujeira(random.Random(1), eventos, 0.03)
    mutados = Counter(e["event_name"] for e in eventos
                      if e["event_id"] in antes and e != antes[e["event_id"]])
    assert mutados
    for nome, n in mutados.items():
        assert n <= math.ceil(total[nome] * 0.05), nome
