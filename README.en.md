# wifi-site-survey

**English** · [Português (Brasil)](README.md)

[![Python 3](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](#) [![PyYAML](https://img.shields.io/badge/PyYAML-only%20dep-3776AB?style=flat-square)](#) [![pytest](https://img.shields.io/badge/pytest-266%20tests-0A9EDC?style=flat-square&logo=pytest)](#) [![MIT License](https://img.shields.io/badge/License-MIT-f4c430?style=flat-square)](LICENSE)

## What it is

**A WiFi site survey tool**: it reads site-survey measurements (CSV per floor), calculates AP density, channel interference (2.4/5 GHz), per-AP capacity, generates an RSSI heatmap in HTML (colours by position) and detects channel conflicts across floors. It is an educational wireless-networking lab.

## Status

An educational lab, working and tested (266 tests — the largest in the portfolio).

## Features

- **Reader** (`leitor.py`): `ler_csv`, `agregar` (measurements → networks), `carregar` (APs), `carregar_andares`.
- **Plan** (`plano.py`): `Medicao`, `Rede`, `AccessPoint`, `agrupar_aps`, `assinatura_do_equipamento`.
- **Capacity** (`capacidade.py`): `capacidade_do_ap`, `Dimensionamento`, `verifica_projeto`.
- **Interference** (`interferencia.py`): `canais_validos` (2.4 and 5 GHz), `sobrepoe`, `nivel_interferencia`, `indices_de_conflito`.
- **Map** (`mapa.py`): `perda_por_distancia`, `rssi_estimado`, `melhor_leitura`, `cor_para_rssi` → heatmap.
- **Report** (`cli.py`): `_cmd_relatorio` (HTML), `_cmd_comparar` (between floors).
- **CLI** (`wifisurvey`): HTML report and floor comparison.

## Architecture

A `wifisurvey` package with `leitor` (CSV), `plano` (network model), `capacidade` (sizing), `interferencia` (conflicts), `mapa` (RSSI/colours) and `cli` (HTML).

## Stack

- Python ≥ 3.10, PyYAML ≥ 6.0
- pytest (dev)

## Repository layout

```
wifi-site-survey/
├── src/wifisurvey/  # leitor · plano · capacidade · interferencia · mapa · cli
├── dados/           # measurement CSVs per floor
├── tests/           # 266 tests
└── LICENSE          # MIT
```

## Prerequisites and installation

```bash
pip install -e .
```

## How to run

```bash
wifisurvey relatorio dados/ --html saida.html
wifisurvey comparar dados/{floor1,floor2}
```

## Tests and quality

```bash
PYTHONPATH=src python -m pytest tests/   # 266 passed
```

## Technical decisions

- RSSI heatmap by measurement-point interpolation; no ray-tracing propagation model.
- Channel conflict by band overlap.

## Known limitations

- No Ekahau/Eagle export; manual CSV import only.
- Simplified path-loss model.

## Development process

An individual project by Kelvin Oliveira, built with orchestrated AI agents and reviewed by the author.

## License and author

MIT — Copyright (c) 2026 Kelvin Rebelo de Oliveira. Author: [Kelvin Oliveira](https://github.com/KelvinOliveiraCode) · [Portfolio](https://kelvinoliveiracode.github.io/portfolio/)
