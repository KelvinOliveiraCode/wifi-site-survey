# wifi-site-survey

<img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/testes-266%20passando-brightgreen?style=flat-square" alt="Testes">
<img src="https://img.shields.io/badge/cobertura-95%25-brightgreen?style=flat-square" alt="Cobertura">
<img src="https://img.shields.io/badge/deps-PyYAML%20opcional-blue?style=flat-square" alt="Dependencias">
<img src="https://img.shields.io/badge/licenca-MIT-yellow?style=flat-square" alt="Licenca">
<img src="https://img.shields.io/badge/plataforma-Windows-blue?style=flat-square" alt="Windows">

Le a varredura de Wi-Fi, monta o mapa de calor de RSSI por andar, dimensiona quantos access points o andar precisa e aponta onde os canais se sobrepoem. A saida e um relatorio HTML autocontido e um PNG, sem servidor e sem internet.

## Problema / Por que existe

A conversa com o cliente sobre Wi-Fi quase nunca e "coloque este SSID". E "por que o corredor do terceiro andar cai", e essa resposta exige dado medido, nao opiniao. O wifisurvey pega o CSV que sai de um analisador de Wi-Fi e responde tres perguntas: onde o sinal esta ruim, falta access point, e onde os canais estao brigando.

Sem dado medido o relatorio vira palpite. Sem um mapa honesto sobre o que e estimado, o cliente nao pode discordar da conclusao. O projeto existe para trocar opiniao por medida em projeto de rede sem fio.

## O que faz

Lê um CSV de varredura (uma linha por rede vista em um ponto de medida) e produz, para cada andar:

- Agrupamento de redes logicas por BSSID: os cinco primeiros octetos do MAC identificam o aparelho, para nao contar um AP de teto com tres SSIDs como seis antenas e nao dobrar a capacidade de um AP dual-band.
- Modelo de canais ancorado no canal primario: um canal de 40 MHz com primario 56 ocupa 56 e 60; um de 80 MHz com primario 36 ocupa 36, 40, 44 e 48. Canais de bandas diferentes nunca se sobrepoem.
- Detecção de sobreposicao entre APs distintos do andar, comparando a faixa ocupada de cada emissor e nao apenas o numero do canal.
- Dimensionamento por tres criterios independentes — cobertura (area), populacao e ocupacao (area por cliente) — e o maior vence.
- Relatorio HTML de um andar com mapa de calor de RSSI, plano de canal, redes em disputa, problemas de plantao e tabela de APs. O mapa vai embutido como data URI: o arquivo abre com duplo clique, sem pasta de imagens ao lado e sem internet.
- PNG do mapa de calor gravado com zlib e struct da biblioteca padrao, sem Pillow.
- Subcomando comparar para ver os andares lado a lado, e canais para listar canais validos por banda e validar um escolhido.

## Stack

- Python 3.10+. Sem dependencia de runtime obrigatoria: o projeto roda com Python limpo. PyYAML e usado somente para ler o arquivo de parametros opcional (`--parametros`); sem ele, os valores padroes em `capacidade.py` sao usados.
- Biblioteca padrao apenas: csv, zlib, struct, math, html, argparse, dataclasses, pathlib, base64.
- Testes: pytest e pytest-cov (apenas desenvolvimento).
- Saida: HTML e PNG, sem servidor, sem navegador de build e sem internet.

## Como funciona

| Modulo | Responsabilidade |
|---|---|
| `leitor.py` | Lê o CSV: banda em seis grafias (`2.4`, `2.4G`, `2,4`, `2400MHz`, `5`, `5G`, `5000MHz`), largura de canal opcional (padrao 20) e coordenadas. |
| `plano.py` | Modelo de medida, rede logica e AP fisico; `assinatura_do_equipamento` corta o MAC em cinco octetos. |
| `interferencia.py` | Canais validos por banda, faixa ocupada, sobreposicao entre emissores, canal recomendado e contagem de radios por canal. |
| `capacidade.py` | Capacidade por AP (soma de banda e largura distintas, nunca SSID), dimensionamento por tres criterios e detecção de aglomerado de APs. |
| `mapa.py` | Mapa de calor: estimativa de RSSI por perda de caminho (expoente 3.0, mais 4 dB por parede a cada 6 m), escala de cor que segue a faixa medida no andar, HTML e PNG. |
| `cli.py` | Linha de comando com os subcomandos `relatorio`, `comparar` e `canais`. |

**Agrupar por BSSID: o porquê dos cinco octetos.** Um AP de teto dual-band com tres SSIDs aparece no varrimento como seis redes logicas, seis BSSIDs e um access point. Os cinco primeiros octetos do MAC sao iguais entre os radios; so o sexto muda. Contar por SSID daria seis antenas onde existe uma, e o relatorio mandaria comprar seis APs para um andar ja servido. Contar por BSSID exato daria dois APs onde existe um. Por isso `assinatura_do_equipamento` corta em cinco octetos.

**Sobreposicao ancorada no canal primario.** Um canal de 40 MHz com primario 56 ocupa 56 e 60, porque o bloco `52-64` e formado por 52/56/60/64. Um de 80 MHz com primario 36 ocupa 36, 40, 44 e 48. O detalhe custou um bug real: com a faixa centrada no primario, 56 ocuparia 55 e 57, canais que nao existem na grade de 5 GHz, e um emissor largo jamais colidiria com o vizinho. O andar 1 estava saturado e a ferramenta dizia que estava tudo bem.

**Capacidade nao e cobertura.** `capacidade_do_ap` soma banda e largura distintas, nunca SSID: cinco SSIDs no mesmo BSSID continuam sendo uma antena. O dimensionamento usa tres criterios independentes - cobertura, populacao e ocupacao - e o maior vence. Em 2.4 GHz a capacidade cai com a largura de canal (20 MHz: 15 clientes; 40 MHz: 10), porque o canal largo rouba tempo de ar dos vizinhos. Em 5 GHz ela sobe (20 MHz: 25; 80 MHz: 100). A assimetria e real, e e o motivo de a tabela nao ser simetrica.

**O mapa e estimativa, e diz isso.** Entre dois pontos visitados, o valor desenhado e interpolado por perda de caminho com expoente 3,0 (tipico de interior), mais 4 dB por parede a cada 6 m extras. O relatorio marca isso explicitamente na legenda. A escala de cor acompanha a faixa medida naquele andar, e nao uma escala fixa: num andar denso com quinze APs o melhor sinal esta sempre perto, todo ponto cai entre -61 e -36 dBm, e uma escala fixa empurra tudo para o mesmo azul.

**O PNG sem Pillow.** O mapa de calor sai em PNG escrito com `zlib` e `struct`, da biblioteca padrao: cabecalho, chunks `IHDR`/`IDAT`/`IEND` e os dados comprimidos. Sao quarenta linhas, e elas nao vao sumir em tres anos como dependencia abandonada. Pillow continua sendo bom para isso, mas nao e necessario para um heatmap de um andar.

## Como rodar

```powershell
# 1. Instalar
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

# 2. Validar
python -m pytest tests/ -q

# 3. Executar
python -m wifisurvey relatorio dados/varrimento-andar1.csv --planta dados/planta-andar1.svg --saida exemplos/relatorio-andar1.html --png exemplos/mapa-andar1.png
```

Saida real do exemplo acima:

```
Andar: andar1
  APs fisicos: 11 (66 redes logicas agrupadas por BSSID)
  RSSI medio: -68.4 dBm
  Canais 2.4 GHz em uso: 1, 6, 11 -> recomendado 1
  Canais 5 GHz em uso: 36, 52, 100, 149 -> recomendado 40
  Dimensionamento: 5 AP(s) acima do necessario: 11 instalado(s) para 6 necessario(s)
  Problemas: 0
  PNG do mapa: exemplos\mapa-andar1.png (36567 bytes)
  Relatorio: exemplos\relatorio-andar1.html
  Planta conferida: dados\planta-andar1.svg
```

Os outros subcomandos:

```powershell
# os tres andares lado a lado
python -m wifisurvey comparar

# os canais validos de cada banda, e a validacao de um canal
python -m wifisurvey canais --banda 5 --canal 70
```

Sem instalar nada, da raiz do repositorio:

```powershell
$env:PYTHONPATH="$PWD\src"; python -m wifisurvey relatorio dados/varrimento-andar1.csv --planta dados/planta-andar1.svg --saida exemplos/relatorio-andar1.html --png exemplos/mapa-andar1.png
```

O relatorio abre com duplo clique: o mapa vai embutido como data URI, entao nao existe pasta de imagens ao lado para quebrar quando o arquivo e mandado por e-mail.

Os tres andares do exemplo existem para demonstrar um problema diferente cada um; o script `tools/verificar_aceite.py` exige que os tres acionem o detector correspondente:

| | andar1 | andar2 | andar3 |
|---|---|---|---|
| APs fisicos | 11 | 9 | 5 |
| Populacao | 60 | 45 | 90 |
| RSSI medio | -68,4 dBm | -62,3 dBm | -65,2 dBm |
| Canais 2.4 GHz | 1, 6, 11 | 1, 6, 11 | 1, 6, 11 |
| Canais 5 GHz | 36, 52, 100, 149 | 36, 52, 100, 149 | 36, 52, 100 |
| Canais disputados | 7 | 7 | 4 |
| Dimensionamento | 5 APs acima do necessario | 4 APs acima do necessario | falta 3 APs |
| O que ensina | conflito de canal | aglomerado | falta de cobertura |

**andar1 - o espectro esta saturado.** Os tres canais de 2.4 GHz canonicos estao em uso por varios APs, e um emissor de 80 MHz no canal 36 ocupa 36, 40, 44 e 48 enquanto um de 40 MHz no 56 pega 56 e 60. Sete canais em disputa, onze APs em interferencia. O sinal e aceitavel, a capacidade sobra (11 APs para o necessario de 6) e a rede e ruim: o problema aqui nao e falta de AP, e canal mal escolhido.

**andar2 - dois aparelhos no mesmo lugar.** Nove APs, capacidade de sobra, sinal bom, e mesmo assim ha um aglomerado: dois APs a 0,9 m um do outro contra 3,6 m de distancia tipica dos demais. E o erro de instalacao mais comum que nao aparece em nenhuma ferramenta que so olha RSSI.

**andar3 - e aqui esta a licao.** Cinco APs duais comportam 200 clientes para 90 pessoas. A capacidade sobra, e ainda assim o andar esta subdimensionado: sao 6 m2 por pessoa contra os 35 m2 de projeto, e e a area que vira o gargalo, nao o AP. Sao 8 APs necessarios contra os 5 instalados, por causa do criterio de ocupacao: 540 m2 comportam 15 pessoas confortavelmente, e ha 90. Um relatorio que mostrasse so capacidade diria que esse andar esta otimo, com folga de 110 clientes.

## Estrutura do projeto

```
wifi-site-survey/
├── src/wifisurvey/       # pacote: cli, leitor, plano, interferencia, capacidade, mapa
├── dados/                # 3 CSVs de varredura, 3 plantas SVG, capacidade.yaml
├── docs/                 # metodo-de-medicao.md e criterios-de-projeto-wifi.md
├── exemplos/             # 3 relatorios HTML e 3 PNGs de exemplo
├── tests/                # 266 testes
└── tools/                # geradores e scripts de verificacao (aceite, encoding, exemplos)
```

## Trade-offs e decisões

- **BSSID em cinco octetos, nunca por SSID e nunca por BSSID exato.** Por SSID o relatorio pedia seis APs para um ja servido; por BSSID exato contava dois onde existe um. Cinco octetos une os radios de um mesmo aparelho sem multiplicar capacidade.
- **Faixa ancorada no canal primario, nao centrada.** Corrigiu o bug em que um emissor largo nunca colidia com o vizinho (canais 55 e 57 nao existem na grade de 5 GHz).
- **Capacidade e configuracao, nao catalogo de fabricante.** Os numeros em `dados/capacidade.yaml` sao um orcamento de referencia documentado, transparente e substituivel com `--parametros`, mas nao sao verdade universal.
- **Três criterios somando, nao multiplicando.** O criterio de ocupacao entra como `por_cobertura + rodadas - 1`. Multiplicar cobertura por rodadas gerou 70 APs em 100 m2 com 200 pessoas — sem fundamento fisico.
- **PNG com zlib e struct, sem Pillow.** Um heatmap de um andar e poucas dezenas de milhares de pixels; 40 linhas de biblioteca padrao nao dependem de um pacote externo que pode ser abandonado.
- **O mapa afirma que e estimativa.** Entre dois pontos visitados o valor e desenhado, nao observado; a legenda do relatorio avisa explicitamente.
- **Escala de cor segue o piso e o teto medidos no andar.** Uma escala fixa de -80 a -35 dBm empurra um andar denso para o mesmo tom de azul e nao informa nada.

## Limitações conhecidas

- **O mapa e interpolacao.** Entre dois pontos visitados o valor e desenhado, nao observado. A legenda do relatorio avisa.
- **A posicao do AP e estimada** pelo centroide ponderado das amostras (potencia recebida, lei de Friis). Com pouca densidade de pontos, ela desloca alguns metros.
- **A perda de caminho e um modelo**, com expoente 3.0 e 4 dB por parede a cada 6 m. Prediz para predio com layout parecido; nao para um bloco inteiro com varios andares e armarios no caminho.
- **Um unico modelo de perda de caminho para 2.4 e 5 GHz**, o que nao e verdade fisica. A diferenca real e pequena neste contexto.
- **A capacidade por AP e configuracao.** Nao sai de catalogo de fabricante.
- **Nao existe previsao de throughput.** Capacidade e quantos clientes, nao quao rapido: 60 clientes a -55 dBm em 80 MHz podem render menos que 25 a -67 dBm em 20 MHz.
- **Nao modela espectro de vizinho** fora do predio; redes de predios ao lado nao estao no CSV.
- **Os dados de exemplo sao ficticios:** planta de 30 m x 18 m, BSSIDs com prefixo de administracao local `02:00:00` e SSIDs que nao existem (`CORP-TI`, `GUEST-LAB`).

## Licença

MIT. Ver [LICENSE](LICENSE).

## Autor

Kelvin Oliveira — https://github.com/KelvinOliveiraCode — https://kelvinoliveiracode.github.io/portfolio/
