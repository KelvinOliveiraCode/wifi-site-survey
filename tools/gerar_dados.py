#!/usr/bin/env python
"""Gera os CSVs de varrimento e as plantas SVG dos tres andares.

Generate the survey CSVs and floor plan SVGs for all three floors.

Tudo aqui e ficticio e deterministico: a semente fixa garante que o mesmo
rodar gere os mesmos bytes, e o CI compara o resultado com o que esta no
repositorio. Um varrimento "realista" com valores aleatorios a cada execucao
nao serviria nem como dado nem como prova.

Cada AP fisico transmite **varios SSIDs no mesmo BSSID**, como acontece em
campo. E o que faz o agrupamento por BSSID importar: sem isso o relatorio
contaria cada SSID como um aparelho e mandaria comprar hardware que ja existe
na parede.

Os tres andares plantam problemas diferentes:

- **andar1** - 2.4 GHz saturado nos tres canais canonicos e um AP orfao no
  canto, com RSSI abaixo do limite. E o caso de refazer o projeto de canal.
- **andar2** - sinal bom, mas APs plantados perto demais uns dos outros. O
  problema e interferencia por sobreposicao, nao falta de capacidade.
- **andar3** - APs bem posicionados e sinal confortavel, porem uma populacao
  muito maior do que a capacidade instalada. O sinal esta bom e mesmo assim o
  andar nao aguenta: e o caso onde capacidade decide e RSSI nao.
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

# O modelo de perda vem do proprio pacote, nao de uma copia aqui.
# Se o dado e o mapa usassem curvas diferentes, o mapa estaria desenhando
# um sinal que o CSV nao produz.
from wifisurvey.mapa import perda_por_distancia  # noqa: E402

SEMENTE = 20260115

LARGURA_M = 30.0
ALTURA_M = 18.0
METROS_PX = 22.0




# Pontos de medicao por AP. A grade cobre o andar inteiro; um varrimento real
# andaria por ele, mas uma grade nao inventa pico de leitura onde ninguem foi.
# Lados da grade de medicao por AP. 5 x 5 = 25 pontos, como um varrimento
# real que percorre o andar. A densidade importa mais do que parece: a
# posicao estimada do AP e o centroide ponderado pela potencia, entao uma
# grade grossa puxa a estimativa para o ponto de grade mais proximo. Com
# 4 pontos, dois APs plantados a 7 m saiam estimados a 3 m - e o alerta de
# interferencia disparava em todos os andares, ate nos que estao bem
# projetados.
PONTOS_POR_AP = 5

# prefixo de MAC local (bit local unico ligado): nenhum destes enderecos
# pode existir na internet, por construcao.
PREFIXO_MAC = "02:00:00"

# SSIDs ficticios. Nenhum e rede real de operadora ou empresa.
SSIDS = (
    "CORP-TI",
    "CORP-VISITANTES",
    "CORP-IOT",
    "CORP-VOIP",
    "REDE-LAB",
    "GUEST-LAB",
    "CORP-CFTV",
    "LAB-SENSORNET",
)

# Canais 2.4 GHz canonicos: so estes tres nao se sobrepoem.
CANAIS_2G = (1, 6, 11)

# Blocos 5 GHz de 20 MHz. Andar1 usa os tres primeiros de proposito, para
# Produzir sobreposicao entre blocos vizinhos - 56 esta dentro do bloco
# 52-64 e nao em 52-60, entao ele invade 60.
BLOCOS_5G = (36, 52, 100, 149)

# RSSI a 1 metro do AP. -30 e um AP de teto em ambiente aberto; 5 GHz entrega
# cerca de 2 dB a mais que 2.4 GHz na mesma posicao, pela largura de banda
# maior. A perda extra de cada andar entra por cima.
RSSI_1M_2G = -30
RSSI_1M_5G = -28

# ANDAR, aps, ssids_por_ap, populacao, perda_extra, aps_proximos
#
# A perda extra e o que separa um andar do outro: parede extra, AP amurado,
# gente na frente do sinal. Com o modelo interno de perda ja dao ~24 dB entre o
# ponto mais proximo e o mais distante de um AP, a perda extra planta o que o
# projeto tem de mostrar - e o que separa o andar2, que tem sinal bom e APs
# mal distribuidos, do andar3, que tem sinal bom e capacidade curta.
ANDARES = (
    ("andar1", 10, 3, 60, -6, False),
    ("andar2", 9, 3, 45, 0, True),
    ("andar3", 5, 2, 90, -4, False),
)


def grade_medicao(lados: int = PONTOS_POR_AP) -> list[tuple[float, float]]:
    """Grade de pontos de medicao cobrindo o andar.

    Measurement grid covering the floor.

    Args:
        lados: Lados da grade. ``2`` da quatro pontos, ``3`` da nove.

    Returns:
        Coordenadas ``(x, y)`` em metros, ordenadas.
    """
    pontos: list[tuple[float, float]] = []
    for iy in range(lados):
        for ix in range(lados):
            pontos.append(
                (
                    round((ix + 0.5) * LARGURA_M / lados, 2),
                    round((iy + 0.5) * ALTURA_M / lados, 2),
                )
            )
    return pontos


def rssi_em(distancia_m: float, rssi_1m: float) -> int:
    """RSSI a uma distancia do AP.

    RSSI at a distance from the AP.

    Args:
        distancia_m: Distancia em metros.
        rssi_1m: RSSI a 1 metro.

    Returns:
        RSSI em dBm, limitado a -100 dBm (abaixo disso o receptor ja nao
        distingueruido de ruido, e o valor exato nao muda a decisao).
    """
    return max(-100, int(round(rssi_1m - perda_por_distancia(distancia_m))))


def posicoes_aps(quantidade: int, rng: random.Random) -> list[tuple[float, float]]:
    """Distribui APs pela area do andar, em grade com jitter.

    Spread APs across the floor area, on a jittered grid.

    A versao anterior sorteava posicoes e aceitava as que ficassem a 7 m ou
    mais da anterior. Funcionava ate a densidade pedida nao coubesse: com
    quinze APs em 540 m2 e 7 m de separacao minima, o sorteio rodava milhares
    de tentativas sem sucesso e caia num laco de preenchimento que empilhava
    os APs restantes no mesmo lugar. O andar inteiro disparava o alerta de
    aglomerado, e o alerta virou ruido.

    Uma grade com jitter resolve os dois problemas de uma vez: a separacao
    fica garantida pelo tamanho da celula, e o jitter evita que a planta pareca
    um tabuleiro de xadrez. Uma coluna de grade tem margem de 3 m da parede,
    porque AP rente a parede tem parte da antepara no caminho do sinal.

    Args:
        quantidade: Quantos APs.
        rng: Gerador com semente fixa.

    Returns:
        Coordenadas ``(x, y)`` em metros.
    """
    margem = 3.0
    util_x = LARGURA_M - 2 * margem
    util_y = ALTURA_M - 2 * margem

    # Proporcao de colunas e linhas que casa com o formato do andar, ajustada
    # para caber a quantidade pedida.
    cols = max(1, round((quantidade * util_x / util_y) ** 0.5))
    linhas = max(1, -(-quantidade // cols))
    cols = max(1, -(-quantidade // linhas))

    cel_x = util_x / cols
    cel_y = util_y / linhas
    jitter = 0.30

    pontos: list[tuple[float, float]] = []
    for i in range(quantidade):
        cx = i % cols
        cy = i // cols
        x = margem + (cx + 0.5) * cel_x + rng.uniform(-jitter, jitter) * cel_x
        y = margem + (cy + 0.5) * cel_y + rng.uniform(-jitter, jitter) * cel_y
        pontos.append(
            (
                round(min(max(x, margem), LARGURA_M - margem), 2),
                round(min(max(y, margem), ALTURA_M - margem), 2),
            )
        )

    return pontos


def gerar_andar(
    indice: int,
    definicao: tuple,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Gera as linhas de CSV de um andar.

    Generate one floor's CSV rows.

    Args:
        indice: Indice do andar, usado para o prefixo de MAC.
        definicao: ``(nome, n_aps, ssids_por_ap, populacao, rssi_extra, proximos)``.
        rng: Gerador com semente fixa.

    Returns:
        Linhas prontas para o CSV.
    """
    nome, n_aps, ssids_por_ap, _populacao, rssi_extra, proximos = definicao
    grid = grade_medicao()
    posicoes = posicoes_aps(n_aps, rng)

    # Andar2 planta APs proximos de proposito, para exercitar o alerta de
    # interferencia por distancia.
    if proximos:
        novas: list[tuple[float, float]] = []
        for i in range(n_aps):
            if i % 3 == 0 and i + 1 < len(posicoes):
                base = posicoes[i]
                novas.append(base)
                novas.append((round(base[0] + 0.5, 2), round(base[1] + 0.4, 2)))
            else:
                novas.append(posicoes[i])
        posicoes = novas[:n_aps]

    # Andar1 planta um AP orfao no canto, longe de tudo.
    if nome == "andar1":
        posicoes.append((LARGURA_M - 2.5, ALTURA_M - 2.5))

    linhas: list[dict[str, object]] = []
    n_ap = 0

    for pos in posicoes:
        n_ap += 1
        # Um MAC por radio: os cinco primeiros octetos identificam o aparelho,
        # o ultimo distingue o radio. E assim que um AP dual-band aparece num
        # varrimento de verdade.
        assinatura = f"{PREFIXO_MAC}:{indice:02x}:{n_ap:02x}:00"

        # Cada AP transmite nas duas bandas. Em 2.4 GHz o canal sai do trio
        # canonico; em 5 GHz, de um bloco de 20 MHz.
        canal_24 = CANAIS_2G[n_ap % 3]
        bloco = (n_ap // 2) % len(BLOCOS_5G)
        canal_5 = BLOCOS_5G[bloco]

        # No andar1 o projeto empilha canais largos de proposito: um AP de
        # 80 MHz no canal 36 ocupa 36, 40, 44 e 48, e um de 40 MHz no canal 56
        # ocupa 56 e 60. Como os blocos de 20 MHz vizinhos continuam em uso,
        # a faixa larga invade canal alheio - que e a forma mais comum de
        # sobreposicao em 5 GHz num andar que "parece" estar bem distribuido.
        largura_24 = 20
        largura_5 = 20
        if nome == "andar1":
            if n_ap == 1:
                largura_5 = 80       # 36 -> 36, 40, 44, 48
            elif n_ap == 3:
                largura_5 = 40       # 56 -> 56 e 60

        ref_24 = RSSI_1M_2G + rssi_extra
        ref_5 = RSSI_1M_5G + rssi_extra

        for k in range(ssids_por_ap):
            ssid = SSIDS[(n_ap * ssids_por_ap + k) % len(SSIDS)]
            for _idx, (sufixo, canal, banda, ref, largura) in enumerate(
                (
                    ("00", canal_24, "2.4", ref_24, largura_24),
                    ("01", canal_5, "5", ref_5, largura_5),
                )
            ):
                mac = f"{assinatura}:{sufixo}"
                for px, py in grid:
                    d = ((px - pos[0]) ** 2 + (py - pos[1]) ** 2) ** 0.5
                    linhas.append(
                        {
                            "bssid": mac,
                            "ssid": ssid,
                            "canal": canal,
                            "banda": banda,
                            "rssi": rssi_em(d, ref),
                            "x": px,
                            "y": py,
                            "largura_canal": largura,
                        }
                    )

    return linhas


def escrever_csv(destino: Path, linhas: list[dict[str, object]]) -> None:
    """Grava as linhas em um CSV de varrimento.

    Write the rows to a survey CSV.
    """
    with destino.open("w", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(
            fh,
            fieldnames=("bssid", "ssid", "canal", "banda", "rssi", "x", "y", "largura_canal"),
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def escrever_planta(destino: Path, nome: str) -> None:
    """Grava a planta do andar em SVG.

    Write the floor plan as SVG.

    A planta e um retangulo com grade de 5 m e tres salas. O mapa de calor
    desenha por cima dela, entao ela precisa estar em unidades de metro e
    ter a mesma origem.
    """
    w = LARGURA_M * METROS_PX
    h = ALTURA_M * METROS_PX

    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
            f'width="{w:.0f}" height="{h:.0f}">'
        ),
        f"<!-- planta ficticia do {nome}: {LARGURA_M:.0f} m x {ALTURA_M:.0f} m -->",
        (
            f'<rect x="0" y="0" width="{w:.0f}" height="{h:.0f}" '
            f'fill="#ffffff" stroke="#111111" stroke-width="2"/>'
        ),
    ]

    for metro in range(0, int(LARGURA_M) + 1, 5):
        x = metro * METROS_PX
        partes.append(
            f'<line x1="{x:.0f}" y1="0" x2="{x:.0f}" y2="{h:.0f}" stroke="#e2e2e2"/>'
        )
    for metro in range(0, int(ALTURA_M) + 1, 5):
        y = metro * METROS_PX
        partes.append(
            f'<line x1="0" y1="{y:.0f}" x2="{w:.0f}" y2="{y:.0f}" stroke="#e2e2e2"/>'
        )

    for i in (1, 2):
        x = w / 3 * i
        partes.append(
            f'<line x1="{x:.0f}" y1="0" x2="{x:.0f}" y2="{h:.0f}" '
            f'stroke="#9a9a9a" stroke-width="3"/>'
        )

    partes.append("</svg>")
    destino.write_text("\n".join(partes) + "\n", encoding="utf-8")


def main() -> int:
    """Gera os tres andares.

    Generate all three floors.

    Returns:
        0 em sucesso.
    """
    dados = RAIZ / "dados"
    dados.mkdir(parents=True, exist_ok=True)

    for indice, definicao in enumerate(ANDARES):
        nome = definicao[0]
        rng = random.Random(SEMENTE + indice)
        linhas = gerar_andar(indice, definicao, rng)
        escrever_csv(dados / f"varrimento-{nome}.csv", linhas)
        escrever_planta(dados / f"planta-{nome}.svg", nome)

        # O aparelho tem um MAC por radio, entao o total de BSSIDs e o dobro
        # do numero de APs. E o agrupamento por assinatura que junta os dois.
        from wifisurvey.plano import assinatura_do_equipamento

        bssids = {linha["bssid"] for linha in linhas}
        aps = {assinatura_do_equipamento(b) for b in bssids}
        ssids = {linha["ssid"] for linha in linhas}
        print(
            f"{nome}: {len(linhas)} medicoes, {len(bssids)} BSSIDs, "
            f"{len(aps)} APs fisicos, {len(ssids)} SSIDs  -> dados/varrimento-{nome}.csv"
        )

    print("plantas SVG em dados/planta-*.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
