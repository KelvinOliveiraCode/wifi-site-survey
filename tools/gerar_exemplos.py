#!/usr/bin/env python
"""Regera os exemplos versionados de forma deterministica.

Regenerate the committed examples deterministically.

O relatorio HTML nao pode ser gerado pelo comando da CLI, porque a CLI nao
carimba data nenhuma - nao ha "gerado em" no relatorio do wifisurvey. Ele
poderia ser. Aqui a geracao vai pela biblioteca mesmo assim, para que o
exemplo versionado e o comando do README sao o mesmo caminho de codigo.

O que precisa ser deterministico e o **PNG**. Ele depende da interpolacao do
sinal, que depende da posicao estimada dos APs, que depende do CSV. Como o CSV
e gerado com semente fixa, o PNG sai identico. O CI compara os bytes.

Exit code 0 = os exemplos foram regerados.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from wifisurvey.capacidade import Parametros, dimensionar, verifica_projeto  # noqa: E402
from wifisurvey.interferencia import (  # noqa: E402
    canal_recomendado,
    conflito_de_canal,
    indices_de_conflito,
)
from wifisurvey.leitor import carregar  # noqa: E402
from wifisurvey.mapa import _png_data_uri, escrever_png, gerar_relatorio  # noqa: E402

ANDARES = {
    "andar1": (540.0, 60),
    "andar2": (540.0, 45),
    "andar3": (540.0, 90),
}

LARGURA_M = 30.0
ALTURA_M = 18.0


def gerar_andar(andar: str, pop: int, params: Parametros) -> None:
    """Regera o HTML e o PNG de um andar.

    Regenerate one floor's HTML and PNG.

    Args:
        andar: Nome do andar.
        pop: Populacao prevista.
        params: Parametros de projeto.
    """
    aps = carregar(RAIZ / "dados" / f"varrimento-{andar}.csv")
    dim = dimensionar(aps, LARGURA_M * ALTURA_M, pop, params)
    c24 = sorted({r.canal for a in aps for r in a.redes if r.banda == "2.4"})
    c5 = sorted({r.canal for a in aps for r in a.redes if r.banda == "5"})

    html = gerar_relatorio(
        andar=andar,
        aps=aps,
        largura_m=LARGURA_M,
        altura_m=ALTURA_M,
        populacao=pop,
        dimensao=dim,
        problemas=verifica_projeto(aps, params),
        conflitos=indices_de_conflito(aps),
        conflito_canais=conflito_de_canal([r for a in aps for r in a.redes]),
        canais_24=c24,
        canais_5=c5,
        recomendado_24=canal_recomendado("2.4", 20, c24),
        recomendado_5=canal_recomendado("5", 20, c5),
        planta_png=_png_data_uri(aps, LARGURA_M, ALTURA_M),
    )

    exemplos = RAIZ / "exemplos"
    html_path = exemplos / f"relatorio-{andar}.html"
    png_path = exemplos / f"mapa-{andar}.png"
    html_path.write_text(html, encoding="utf-8")
    escrever_png(png_path, aps, LARGURA_M, ALTURA_M, escala_px=14)

    print(
        f"{andar}: {html_path.relative_to(RAIZ)} ({len(html)} bytes), "
        f"{png_path.relative_to(RAIZ)} ({png_path.stat().st_size} bytes)"
    )


def main() -> int:
    """Regera os tres andares.

    Regenerate all three floors.

    Returns:
        0 em sucesso.
    """
    params = Parametros.carregar(RAIZ / "dados" / "capacidade.yaml")
    for andar, (area, pop) in ANDARES.items():
        gerar_andar(andar, pop, params)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
