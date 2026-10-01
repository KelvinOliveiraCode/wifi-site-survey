#!/usr/bin/env python
"""Prova de aceite do wifisurvey.

Acceptance proof for wifisurvey.

A suite de testes prova que cada funcao funciona. Isso e diferente de provar que
os **arquivos que acompanham o repositorio** se comportam como o README promete.
Um varrimento com 3 APs passa em todos os testes e nao serve para uma
apresentacao; este script exige que os dados do repositorio acionem cada
detector de problema.

O que ele exige, andar por andar:

- andar1 - 2.4 GHz saturado nos tres canais, com um emissor de 80 MHz que
  invade canal alheio em 5 GHz. Precisa acusar conflito de canal.
- andar2 - APs plantados a menos de um metro uns dos outros. Precisa acusar
  aglomerado.
- andar3 - cinco APs para noventa pessoas. Precisa acusar falta de capacidade
  e dizer quantos faltam.

Nenhum andar pode acusar problema que o outro nao tenha: os tres nao podem dar
o mesmo resultado, porque um alerta que dispara em tudo nao diz nada.

Exit code 0 = os tres andares se comportam como o README promete.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from wifisurvey.capacidade import (  # noqa: E402
    Parametros,
    ParametrosInvalidos,
    dimensionar,
    espacamento_aps,
    verifica_projeto,
)
from wifisurvey.interferencia import (  # noqa: E402
    canais_validos,
    canal_recomendado,
    conflito_de_canal,
    indices_de_conflito,
)
from wifisurvey.leitor import CsvInvalido, carregar  # noqa: E402
from wifisurvey.mapa import (  # noqa: E402
    escala_dos_dados,
    escala_dos_dados as _escal,
    rssi_estimado,
)
from wifisurvey.mapa import grade_sinal  # noqa: E402

AREA_M2 = 540.0
POPULACAO = {"andar1": 60, "andar2": 45, "andar3": 90}

# Minimos que os dados do repositorio precisam superar.
MIN_APS = 5
MIN_REDES = 20

# Teto fisico de leitura. Um receptor nao le sinal mais forte do que o
# transmissor emite: um AP comum transmite entre 15 e 20 dBm. Acima de -20 dBm
# nao ha "AP muito bom", ha erro de leitura - sinal em dBm invertido, coluna
# trocada ou valor em mW rotulado como dBm.
MAX_RSSI = -20.0

# Piso de leitura. Abaixo de -95 dBm o receptor ja nao distingue sinal de
# ruido, e o valor exato deixa de ter significado.
MIN_RSSI = -95.0


class Falha(Exception):
    """Uma condicao de aceite nao foi satisfeita."""


def checar(condicao: bool, mensagem: str) -> None:
    """Falha se a condicao for falsa.

    Fail if the condition is false.
    """
    if not condicao:
        raise Falha(mensagem)


def carregar_andar(andar: str) -> tuple:
    """Carrega um andar com os parametros do repositorio.

    Load one floor with the repository's parameters.
    """
    try:
        aps = carregar(RAIZ / "dados" / f"varrimento-{andar}.csv")
    except CsvInvalido as exc:
        raise Falha(f"{andar}: CSV invalido ({exc})") from exc
    return aps, Parametros.carregar(RAIZ / "dados" / "capacidade.yaml")


def auditar_andar(andar: str) -> dict:
    """Roda todas as verificacoes de um andar.

    Run every check for one floor.

    Args:
        andar: Nome do andar.

    Returns:
        Dicionario com os indicadores do andar.

    Raises:
        Falha: Se algum minimo nao for atingido.
    """
    aps, params = carregar_andar(andar)
    checar(len(aps) >= MIN_APS, f"{andar}: so {len(aps)} APs, minimo {MIN_APS}")

    redes = [r for ap in aps for r in ap.redes]
    checar(
        len(redes) >= MIN_REDES,
        f"{andar}: so {len(redes)} redes, minimo {MIN_REDES}",
    )

    # Todo AP precisa estar nas duas bandas: um AP de uma banda so nao
    # exercita a soma de capacidade do AP dual-band.
    sem_dual = [a.bssid for a in aps if not (a.bandas_2g and a.bandas_5g)]
    checar(not sem_dual, f"{andar}: APs sem dual-band: {sem_dual}")

    # Nenhum AP pode ficar com sinal impossivel.
    for ap in aps:
        checar(ap.rssi_max <= MAX_RSSI, f"{andar}: {ap.bssid} com RSSI {ap.rssi_max}")
        pior_rede = min(r.rssi_min for r in ap.redes)
        checar(
            pior_rede >= MIN_RSSI,
            f"{andar}: {ap.bssid} com leitura de {pior_rede} dBm, "
            f"abaixo do piso de {MIN_RSSI}",
        )

    dim = dimensionar(aps, AREA_M2, POPULACAO[andar], params)
    problemas = verifica_projeto(aps, params)
    conflitos = indices_de_conflito(aps)
    disputados = conflito_de_canal(redes)

    grade = grade_sinal(aps, 30.0, 18.0, 1.0)
    pior, melhor = escala_dos_dados([v for _, _, v in grade])

    # O mapa tem de ter gradiente. Um heatmap de uma cor so nao informa nada.
    checar(
        melhor - pior >= 10.0,
        f"{andar}: mapa sem gradiente ({pior:.1f} a {melhor:.1f} dBm)",
    )

    # O canal recomendado tem de ser realmente valido para a banda.
    c24 = sorted({r.canal for r in redes if r.banda == "2.4"})
    c5 = sorted({r.canal for r in redes if r.banda == "5"})
    recomendado = canal_recomendado("5", 20, c5)
    checar(recomendado in canais_validos("5"), f"{andar}: canal {recomendado} invalido")

    return {
        "aps": aps,
        "redes": redes,
        "dim": dim,
        "problemas": problemas,
        "conflitos": conflitos,
        "disputados": disputados,
        "pior": pior,
        "melhor": melhor,
        "c24": c24,
        "c5": c5,
        "recomendado": recomendado,
    }


def principal() -> int:
    """Roda a prova de aceite dos tres andares.

    Run the acceptance proof for all three floors.

    Returns:
        0 se tudo se comportar como o README promete.
    """
    falhas: list[str] = []
    indicadores: dict[str, dict] = {}

    for andar in ("andar1", "andar2", "andar3"):
        try:
            indicadores[andar] = auditar_andar(andar)
        except Falha as exc:
            falhas.append(str(exc))

    if falhas:
        print("ACEITE FALHOU:")
        for f in falhas:
            print("  -", f)
        return 1

    for andar, dados in indicadores.items():
        dim = dados["dim"]
        print(f"{andar}: {len(dados['aps'])} APs, {len(dados['redes'])} redes")
        print(
            f"  sinal estimado: {dados['pior']:.1f} a {dados['melhor']:.1f} dBm "
            f"(gradiente de {dados['melhor'] - dados['pior']:.1f} dBm)"
        )
        print(
            f"  canais: 2.4 GHz {dados['c24']} | 5 GHz {dados['c5']} "
            f"-> recomendado {dados['recomendado']}"
        )
        print(f"  canais disputados: {len(dados['disputados'])}")
        print(f"  APs em conflito: {len(dados['conflitos'])}")
        print(f"  dimensionamento: {dim.resumo()}")
        print(f"  capacidade: {dim.capacidade_total} clientes para {dim.clientes}")
        for p in dados["problemas"]:
            print("  problema:", p)
        print()

    andar1 = indicadores["andar1"]
    andar2 = indicadores["andar2"]
    andar3 = indicadores["andar3"]

    # --- andar1: conflito de canal ---
    checar(
        len(andar1["disputados"]) >= 3,
        "andar1: 2.4 GHz deveria estar saturado, com conflito em varios canais",
    )
    checar(
        len(andar1["conflitos"]) >= 1,
        "andar1: o emissor de 80 MHz deveria invadir o canal de outro AP",
    )
    print(
        f"andar1: conflito de canal detectado em {len(andar1['disputados'])} "
        f"canais, {len(andar1['conflitos'])} APs em interferencia"
    )

    # --- andar2: aglomerado ---
    minimo, tipica = espacamento_aps(andar2["aps"])
    checar(
        any("aglomerado" in p for p in andar2["problemas"]),
        "andar2: os APs plantados a menos de um metro deveriam acusar aglomerado",
    )
    print(
        f"andar2: aglomerado detectado (vizinho mais proximo a {minimo:.1f} m, "
        f"contra {tipica:.1f} m tipicos)"
    )

    # --- andar3: falta de capacidade ---
    checar(
        andar3["dim"].falta > 0,
        "andar3: cinco APs para noventa pessoas deveriam faltar AP por cobertura",
    )
    checar(
        andar3["dim"].aps_existentes < andar3["dim"].aps_necessarios,
        "andar3: os APs instalados deveriam ser menos que os necessarios",
    )

    # O ponto incomodo deste andar: a capacidade de clientes sobra
    # (cinco APs duais comportam duzentas pessoas), e ainda assim o andar esta
    # subdimensionado. O gargalo nao e quantos clientes cada AP aguenta, e
    # quantos APs existem para cobrir a area. Um relatorio que so mostrasse a
    # capacidade diria que o andar esta otimo.
    capacidade_sobra = andar3["dim"].capacidade_total > andar3["dim"].clientes
    print(
        f"andar3: falta de cobertura - {andar3['dim'].falta} AP(s) para cobrir "
        f"540 m2 com 90 pessoas "
        f"({andar3['dim'].aps_existentes} instalados, "
        f"{andar3['dim'].aps_necessarios} necessarios). "
        f"A capacidade de clientes {'sobra' if capacidade_sobra else 'falta'}: "
        f"{andar3['dim'].capacidade_total} para {andar3['dim'].clientes}"
    )
    checar(
        capacidade_sobra,
        "andar3: este andar existe para mostrar que capacidade de cliente "
        "sobra e ainda assim falta AP - se o dado mudasse, o exemplo perderia "
        "a licao",
    )

    # --- os tres andares nao podem dar o mesmo resultado ---
    #
    # A assinatura de cada andar junta tudo o que o relatorio mostra: os
    # problemas de planta, quantos canais estao disputados, quantos APs estao
    # em interferencia e o veredito do dimensionamento. Comparar apenas a
    # lista de verifica_projeto seria insuficiente: andar1 e andar3 nao
    # acusam nenhum problema de planta e ainda assim contam historias
    # opostas - um tem o espectro saturado, o outro esta sem AP.
    def assinatura(dados: dict) -> tuple:
        dim = dados["dim"]
        return (
            tuple(sorted(dados["problemas"])),
            len(dados["disputados"]),
            len(dados["conflitos"]),
            dim.falta > 0,
            dim.capacidade_suficiente,
        )

    assinaturas = {andar: assinatura(d) for andar, d in indicadores.items()}
    for a in ("andar1", "andar2", "andar3"):
        for b in ("andar1", "andar2", "andar3"):
            if a < b:
                checar(
                    assinaturas[a] != assinaturas[b],
                    f"{a} e {b} produziram a mesma assinatura de relatorio: "
                    "tres andares com o mesmo resultado seriam uma tabela e "
                    "meio, nao um relatorio util",
                )

    checar(
        bool(andar1["disputados"]) and bool(andar2["problemas"]) and andar3["dim"].falta > 0,
        "cada andar devia ter uma historia propria: conflito de canal no "
        "andar1, aglomerado no andar2, falta de cobertura no andar3",
    )

    print()
    print(
        "ok: os tres andares se comportam como o README promete - "
        "conflito de canal no andar1, aglomerado no andar2, "
        "falta de capacidade no andar3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
