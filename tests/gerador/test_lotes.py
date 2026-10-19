import json
import random

from gerador.lotes import SEM_NOME, montar_lotes, particao, pasta, serializar, valor_de_particao


def _ev(i, dt="2026-09-01"):
    return {"event_id": f"id-{i}", "event_ts": f"{dt}T10:{i // 60 % 60:02d}:{i % 60:02d}.000Z",
            "event_name": "page_view", "_dt": dt}


def test_serializar_remove_campos_internos_e_gera_uma_linha_por_evento():
    texto = serializar([_ev(1), _ev(2)])
    linhas = texto.splitlines()
    assert len(linhas) == 2
    assert texto.endswith("\n")
    assert json.loads(linhas[0]) == {"event_id": "id-1", "event_ts": "2026-09-01T10:00:01.000Z",
                                     "event_name": "page_view"}


def test_serializar_mantem_acentos():
    assert "Básico" in serializar([{"event_id": "x", "nome": "Plano Básico"}])


def test_cada_dia_vira_de_3_a_6_lotes_com_a_chave_do_contrato():
    eventos = [_ev(i) for i in range(300)] + [_ev(i, "2026-09-02") for i in range(300, 600)]
    arquivos, duplicatas = montar_lotes(random.Random(3), eventos, origem="coletor", seed=42, fracao_reenvio=0.0)
    assert duplicatas == 0
    for dt in ("2026-09-01", "2026-09-02"):
        chaves = [k for k in arquivos if k.startswith(f"{pasta('page_view', dt)}/coletor-s42-")]
        assert 3 <= len(chaves) <= 6
        assert all(k.endswith(".jsonl") for k in chaves)
    assert sum(len(v.splitlines()) for v in arquivos.values()) == 600


def test_reenvio_repete_event_id_em_outro_lote_nunca_no_mesmo():
    eventos = [_ev(i) for i in range(1000)]
    arquivos, duplicatas = montar_lotes(random.Random(3), eventos, "coletor", 42, fracao_reenvio=0.05)
    assert duplicatas > 0
    ids = [json.loads(linha)["event_id"] for v in arquivos.values() for linha in v.splitlines()]
    assert len(ids) == 1000 + duplicatas
    assert len(set(ids)) == 1000
    for v in arquivos.values():
        do_lote = [json.loads(linha)["event_id"] for linha in v.splitlines()]
        assert len(do_lote) == len(set(do_lote))


def test_evento_sem_timestamp_vai_para_o_dia_de_coleta():
    sem_ts = {"event_id": "nulo", "event_ts": None, "event_name": "scroll", "_dt": "2026-09-01"}
    arquivos, _ = montar_lotes(random.Random(3), [_ev(1), _ev(2), _ev(3), sem_ts], "coletor", 42, 0.0)
    conteudo = "".join(v for k, v in arquivos.items() if "year=2026/month=09/day=01" in k)
    assert '"event_id":"nulo"' in conteudo


def test_particao_usa_year_month_day_com_zeros():
    assert particao("2026-09-01") == "year=2026/month=09/day=01"
    assert particao("2026-12-31") == "year=2026/month=12/day=31"


def test_cada_lote_vira_um_arquivo_por_event_name():
    eventos = [dict(_ev(i), event_name=("scroll" if i % 3 else "page_view")) for i in range(90)]
    arquivos, _ = montar_lotes(random.Random(3), eventos, "coletor", 42, 0.0)
    pastas = {k.rsplit("/", 1)[0] for k in arquivos}
    assert pastas == {"landing/event_name=page_view/year=2026/month=09/day=01",
                      "landing/event_name=scroll/year=2026/month=09/day=01"}
    for chave, conteudo in arquivos.items():
        nome = chave.split("event_name=")[1].split("/")[0]
        assert {json.loads(linha)["event_name"] for linha in conteudo.splitlines()} == {nome}
    assert sum(len(v.splitlines()) for v in arquivos.values()) == 90


def test_valor_de_particao_segue_as_regras_do_spark():
    assert valor_de_particao("page_view") == "page_view"
    assert valor_de_particao(None) == valor_de_particao("") == SEM_NOME
    assert valor_de_particao("a/b=c") == "a%2Fb%3Dc"
    assert pasta("scroll", "2026-09-01T10:00:00Z") == "landing/event_name=scroll/year=2026/month=09/day=01"
