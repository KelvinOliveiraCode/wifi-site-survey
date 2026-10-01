"""wifisurvey - analise de varredura de Wi-Fi por andar.

wifisurvey - per-floor Wi-Fi survey analysis.

Cruza um CSV de varredura com a planta do andar, monta mapa de calor de RSSI,
dimensiona quantos access points o andar precisa, e aponta onde ha sobreposicao
de canal. Os dados de exemplo sao ficticios.
"""

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "capacidade",
    "interferencia",
    "leitor",
    "mapa",
    "plano",
]
