from datetime import datetime, timezone

import pytest

from gerador.jornadas import simular

DATA_INICIAL = datetime(2026, 9, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def simulacao():
    """1500 visitantes em 14 dias, sem sujeira. Devolve (eventos, sessoes)."""
    eventos, sessoes, _ = simular(seed=7, dias=14, visitantes=1500, data_inicial=DATA_INICIAL)
    return eventos, sessoes
