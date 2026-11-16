"""R3 - Roda os jobs do pipeline em sequência, a partir da landing.

Não gera dados: a landing precisa existir (python gerador/gerar_eventos.py).

    docker compose run --rm app python pipeline/rodar_pipeline.py
"""

import subprocess
import sys
import time

from comum import arquivo_do_projeto, titulo


# O job de ML foi dispensado pelo professor
JOBS = [
    "bronze",
    "silver",
    "gold_funil",
    "gold_engajamento",
    "gold_receita",
    "gold_mapa_calor",
    "exportar_mapa_calor",
]


def main():
    inicio_total = time.time()

    for numero, job in enumerate(JOBS, start=1):
        titulo(f"[{numero}/{len(JOBS)}] {job}")

        inicio = time.time()
        script = arquivo_do_projeto(f"pipeline/{job}.py")
        codigo = subprocess.run([sys.executable, str(script)]).returncode

        if codigo != 0:
            raise SystemExit(
                f"O job {job} falhou (código {codigo}). "
                "Os jobs seguintes não foram executados."
            )

        print(f"{job} terminou em {time.time() - inicio:.0f}s")

    titulo("Pipeline completo")
    print(f"{len(JOBS)} jobs em {time.time() - inicio_total:.0f}s")


if __name__ == "__main__":
    main()
