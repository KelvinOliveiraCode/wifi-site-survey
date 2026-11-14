# wifi-site-survey

[English](README.en.md) · **Português (Brasil)**

[![Python 3](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](#) [![PyYAML](https://img.shields.io/badge/PyYAML-%C3%BAnica%20dep-3776AB?style=flat-square)](#) [![pytest](https://img.shields.io/badge/pytest-266%20testes-0A9EDC?style=flat-square&logo=pytest)](#) [![MIT License](https://img.shields.io/badge/License-MIT-f4c430?style=flat-square)](LICENSE)

## O que é

**Survey de Wi-Fi**: lê medições site-survey (CSV por andar), calcula densidade de APs, interferência de canal (2,4/5 GHz), capacidade por AP, gera mapa de calor RSSI em HTML (cores por posição) e detecta conflitos de canal entre andares. É um laboratório educacional de redes sem fio.

## Status

Laboratório educacional funcional e testado (266 testes — o maior do portfólio).

## Funcionalidades

- **Leitura** (`leitor.py`): `ler_csv`, `agregar` (medicoes → redes), `carregar` (APs) e `carregar_andares`.
- **Plano** (`plano.py`): `Medicao`, `Rede`, `AccessPoint`, `agrupar_aps`, `assinatura_do_equipamento`.
- **Capacidade** (`capacidade.py`): `capacidade_do_ap`, `Dimensionamento`, `verifica_projeto`.
- **Interferência** (`interferencia.py`): `canais_validos` (2,4 e 5 GHz), `sobrepoe`, `nivel_interferencia`, `indices_de_conflito`.
- **Mapa** (`mapa.py`): `perda_por_distancia`, `rssi_estimado`, `melhor_leitura`, `cor_para_rssi` → heatmap.
- **Relatório** (`cli.py`): `_cmd_relatorio` (HTML), `_cmd_comparar` (entre andares).
- **CLI** (`wifisurvey`): relatório HTML e comparação entre andares.

## Arquitetura

Pacote `wifisurvey` com `leitor` (CSV), `plano` (modelo de rede), `capacidade` (dimensionamento), `interferencia` (conflitos), `mapa` (RSSI/cores) e `cli` (HTML).

## Stack

- Python ≥ 3.10, PyYAML ≥ 6.0
- pytest (dev)

## Estrutura

```
wifi-site-survey/
├── src/wifisurvey/  # leitor · plano · capacidade · interferencia · mapa · cli
├── dados/           # CSVs de medição por andar
├── tests/           # 266 testes
└── LICENSE          # MIT
```

## Pré-requisitos e instalação

```bash
pip install -e .
```

## Como executar

```bash
wifisurvey relatorio dados/ --html saida.html
wifisurvey comparar dados/{andar1,andar2}
```

## Testes e qualidade

```bash
PYTHONPATH=src python -m pytest tests/   # 266 passed
```

## Decisões técnicas

- Heatmap RSSI por interpolação de pontos de medição; sem modelo de propagação Ray-Tracing.
- Conflitos de canal por sobreposição de banda.

## Limitações

- Sem exportação para Ekahau/Eagle; import só CSV manual.
- Modelo de perda de percurso simplificado.

## Processo de desenvolvimento

Projeto individual de Kelvin Oliveira, construído com agentes de IA orquestrados e revisado pelo autor.

## Licença e autor

MIT — Copyright (c) 2026 Kelvin Rebelo de Oliveira. Autor: [Kelvin Oliveira](https://github.com/KelvinOliveiraCode) · [Portfólio](https://kelvinoliveiracode.github.io/portfolio/)
