<div align="center">

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/tests-262%20passing-brightgreen?style=flat-square" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-95%25-brightgreen-brightgreen?style=flat-square" alt="Coverage">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square" alt="Windows">
</p>

# wifi-site-survey

**Le a varredura de Wi-Fi, monta o mapa de calor de RSSI por andar, dimensiona AP e acusa sobreposicao de canal.**

</div>

---

## PT-BR

### O que e

Analisa o CSV que sai de um analisador de Wi-Fi, monta mapa de calor de RSSI por
andar, dimensiona quantos access points o andar precisa e aponta onde os canais
estao se sobrepondo. A saida e um relatorio HTML autocontido e um PNG, sem
servidor e sem internet.

### Por que foi feito

A conversa com cliente sobre Wi-Fi quase nunca e "coloque este SSID". E "por que
o corredor do terceiro andar cai", e essa resposta exige dado medido, nao
opiniao. A ferramenta pega a varredura e responde tres perguntas: onde o sinal
esta ruim, falta access point, e onde os canais estao brigando.

### Como rodar

```powershell
# 1. Instalar
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

# 2. Validar
python -m pytest tests/ -v

# 3. Executar
python -m wifisurvey relatorio dados/varrimento-andar1.csv --planta dados/planta-andar1.svg --saida exemplos/relatorio-andar1.html --png exemplos/mapa-andar1.png
```

Saida real:

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

O relatorio abre com duplo clique: o mapa vai embutido como *data URI*, entao
nao existe pasta de imagens ao lado para quebrar quando o arquivo e mandado por
e-mail.

### Os tres andares do exemplo

Cada andar existe para demonstrar um problema diferente. O `verificar_aceite.py`
exige que os tres acionem o detector correspondente.

| | andar1 | andar2 | andar3 |
|---|---|---|---|
| APs fisicos | 11 | 9 | 5 |
| Populacao | 60 | 45 | 90 |
| RSSI medio | -68,4 dBm | -62,3 dBm | -65,2 dBm |
| Canais 2.4 GHz | 1, 6, 11 | 1, 6, 11 | 1, 6, 11 |
| Canais 5 GHz | 36, 52, 100, 149 | 36, 52, 100, 149 | 36, 52, 100 |
| Canais disputados | 7 | 7 | 4 |
| Dimensionamento | 5 APs acima do necessario | 4 APs acima do necessario | falta 3 APs |
| **O que ensina** | conflito de canal | aglomerado | falta de cobertura |

**andar1 - o espectro esta saturado.** Os tres canais de 2.4 GHz canonicos estao
em uso por varios APs, e um emissor de 80 MHz no canal 36 ocupa 36, 40, 44 e 48
enquanto um de 40 MHz no 56 pega 56 e 60. Sete canais em disputa, onze APs em
interferencia. O sinal e aceitavel, a capacidade sobra (11 APs para o necessario
de 6) e a rede e ruim: o problema aqui nao e falta de AP, e canal mal escolhido.

**andar2 - dois aparelhos no mesmo lugar.** Nove APs, capacidade de sobra, sinal
bom, e mesmo assim ha um aglomerado: dois APs a 0,9 m um do outro contra 3,6 m
de distancia tipica dos demais. E o erro de instalacao mais comum que nao
aparece em nenhuma ferramenta que so olha RSSI.

**andar3 - e aqui esta a licao.** Cinco APs duais comportam 200 clientes para 90
pessoas. A capacidade sobra, e ainda assim o andar esta subdimensionado: sao
6 m2 por pessoa contra os 35 m2 de projeto, e e a **area** que vira o gargalo,
nao o AP. Sao 8 APs necessarios contra os 5 instalados, por causa do criterio
de ocupacao: 540 m2 comportam 15 pessoas confortavelmente, e ha 90.

Um relatorio que mostrasse so capacidade diria que esse andar esta otimo, com
folga de 110 clientes.

### Como funciona

| Modulo | Responsabilidade |
|---|---|
| `leitor.py` | Le o CSV: banda em seis grafias, largura, coordenadas |
| `plano.py` | Modelo de rede e de AP, e o agrupamento por BSSID |
| `interferencia.py` | Canais validos, faixa ocupada e sobreposicao |
| `capacidade.py` | Capacidade por AP, dimensionamento e problemas |
| `mapa.py` | Mapa de calor: estimativa de RSSI, cor, HTML e PNG |
| `cli.py` | A linha de comando |

**Agrupar por BSSID: o porque dos cinco octetos.** Um AP de teto dual-band com
tres SSIDs aparece no varrimento como seis redes logicas, seis BSSIDs e um access
point. Os cinco primeiros octetos do MAC sao iguais entre os radios; so o sexto
muda. Contar por SSID daria seis antenas onde existe uma, e o relatorio mandaria
comprar seis APs para um andar ja servido. Contar por BSSID exato daria dois APs
onde existe um. Por isso `assinatura_do_equipamento` corta em cinco octetos.

**Sobreposicao ancorada no canal primario.** Um canal de 40 MHz com primario 56
ocupa 56 e 60, porque o bloco `52-64` e formado por 52/56/60/64. Um de 80 MHz
com primario 36 ocupa 36, 40, 44 e 48. O detalhe custou um bug real: com a faixa
**centrada** no primario, 56 ocuparia 55 e 57, canais que nao existem na grade de
5 GHz, e um emissor largo jamais colidiria com o vizinho. O andar 1 estava
saturado e a ferramenta dizia que estava tudo bem.

**Capacidade nao e cobertura.** `capacidade_do_ap` soma banda e largura distintas,
nunca SSID: cinco SSIDs no mesmo BSSID continuam sendo uma antena. O
dimensionamento usa tres criterios independentes - cobertura, populacao e
ocupacao - e o maior vence. Em 2.4 GHz a capacidade **cai** com a largura de
canal (20 MHz: 15 clientes; 40 MHz: 10), porque o canal largo rouba tempo de ar
dos vizinhos. Em 5 GHz ela sobe (20 MHz: 25; 80 MHz: 100). A assimetria e real,
e e o motivo de a tabela nao ser simetrica.

**O mapa e estimativa, e diz isso.** Entre dois pontos visitados, o valor
desenhado e interpolado por perda de caminho com expoente 3,0 (tipico de
interior), mais 4 dB por parede a cada 6 m extras. O relatorio marca isso
explicitamente na legenda. A escala de cor acompanha a faixa medida naquele
andar, e nao uma escala fixa: num andar denso com quinze APs o melhor sinal esta
sempre perto, todo ponto cai entre -61 e -36 dBm, e uma escala fixa empurra
tudo para o mesmo azul.

**O PNG sem Pillow.** O mapa de calor sai em PNG escrito com `zlib` e `struct`,
da biblioteca padrao: cabecalho, chunks `IHDR`/`IDAT`/`IEND` e os dados
comprimidos. Sao quarenta linhas, e elas nao vao sumir em tres anos como
dependencia abandonada. Pillow continua sendo bom para isso, mas nao e
necessario para um heatmap de um andar.

### Formato dos dados

**`dados/varrimento-andar1.csv`** - uma linha por rede vista em um ponto:

```
bssid,ssid,canal,banda,rssi,x,y,largura_canal
02:00:00:00:01:00,CORP-TI,1,2.4,-44,5.0,6.0,20
02:00:00:00:01:01,CORP-TI,36,5,-42,5.0,6.0,80
```

`banda` aceita `2.4`, `2.4G`, `2,4`, `2400MHz`, `5`, `5G`, `5000MHz`.
`largura_canal` e opcional e assume 20 quando vazio.

**`dados/capacidade.yaml`** - capacidade por banda e largura, e os criterios de
projeto. E configuracao, nao verdade:

```yaml
capacidade:
  "5":
    "20": 25
    "80": 100
criterios:
  area_por_cliente_m2: 35.0
  rssi_minimo_dbm: -67
  aps_por_1000_m2: 4
```

O programa **recusa** parametros absurdos em vez de emitir relatorio bonito e
falso. Capacidade menor ou igual a zero, `rssi_minimo_dbm` acima de -30 (melhor
que qualquer AP produz) e area por cliente menor ou igual a zero: todos recusados
na carga. A lista esta em
[`docs/criterios-de-projeto-wifi.md`](docs/criterios-de-projeto-wifi.md).

### Uso como biblioteca

```python
from wifisurvey.capacidade import Parametros, dimensionar, verifica_projeto
from wifisurvey.leitor import carregar

aps = carregar("dados/varrimento-andar3.csv")
params = Parametros.carregar("dados/capacidade.yaml")

dim = dimensionar(aps, area_m2=540.0, clientes=90, params=params)
print(dim.resumo())
print(f"{dim.falta} AP(s) faltando, capacidade de {dim.capacidade_total}")

for problema in verifica_projeto(aps, params):
    print(problema)
```

Saida real do snippet acima:

```
faltam 3 AP(s): 5 instalado(s) para 8 necessario(s)
3 AP(s) faltando, capacidade de 200
```

### O que aprendi

- **Contar AP por SSID manda comprar AP que ja existe.** O andar 1 tem 11 APs
  fisicos e 66 redes logicas; por SSID o relatorio pediria 66 antenas. O corte
  em cinco octetos do MAC e o que separa as duas coisas.
- **A faixa do canal e ancorada no primario, e errar isso esconde o
  problema.** Com a faixa centrada, um emissor de 40 MHz no 56 ocuparia 55 e 57,
  que nao existem na grade: nenhum colidia, e o andar saturado passava como
  limpo. O bug nao era do detector, era do modelo de canal.
- **Capacidade sobrando nao significa rede boa.** O andar 3 tem 200 clientes de
  capacidade para 90 pessoas e ainda assim precisa de 3 APs a mais, porque o
  criterio que aperta e area por pessoa. Quem olha so capacidade recomenda
  guardar dinheiro num andar que vai continuar caindo.
- **RSSI nao ve erro de instalacao.** Dois APs a 0,9 m um do outro somam sinal
  em vez de cobertura, e o mapa de calor mostra exatamente o esperado. So a
  distancia entre vizinhos denuncia.
- **O mapa precisa dizer que e estimativa.** Entre dois pontos visitados o valor
  e desenhado, nao observado; sem isso na legenda, o relatorio vira prova de
  algo que ninguem mediu.

### Limitacoes

- **O mapa e interpolacao.** Entre dois pontos visitados o valor e desenhado, nao
  observado. A legenda do relatorio avisa.
- **A posicao do AP e estimada** pelo centroide ponderado das amostras. Com
  pouca densidade de pontos, ela desloca alguns metros.
- **A perda de caminho e um modelo**, com expoente 3,0 e 4 dB por parede a cada
  6 m. Prediz para predio com layout parecido; nao para um bloco inteiro com
  varios andares e armarios no caminho.
- **A capacidade por AP e configuracao.** Nao sai de catalogo de fabricante.
- **Nao existe previsao de throughput.** Capacidade e quantos clientes, nao qua
  rapido: 60 clientes a -55 dBm em 80 MHz podem render menos que 25 a -67 dBm em
  20 MHz.
- **Um unico modelo de perda de caminho para 2.4 e 5 GHz**, o que nao e verdade
  fisica. A diferenca real e pequena neste contexto.

### Licenca

MIT. Ver [LICENSE](LICENSE).

---

## EN

### What it is

It reads the CSV produced by a Wi-Fi analyser, builds a per-floor RSSI heatmap,
sizes how many access points the floor needs and flags where channels overlap.
The output is a self-contained HTML report and a PNG, with no server and no
internet.

### Why it was built

The conversation with a customer about Wi-Fi is rarely "put this SSID up". It is
"why does the third floor corridor drop", and that answer needs measured data,
not opinion. The tool takes the survey and answers three questions: where the
signal is bad, whether an access point is missing, and where channels are
fighting each other.

### How to run

```powershell
# 1. Install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

# 2. Validate
python -m pytest tests/ -v

# 3. Run
python -m wifisurvey relatorio dados/varrimento-andar1.csv --planta dados/planta-andar1.svg --saida exemplos/relatorio-andar1.html --png exemplos/mapa-andar1.png
```

Real output:

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

The other subcommands:

```powershell
# the three floors side by side
python -m wifisurvey comparar

# the valid channels of each band, and the validation of one channel
python -m wifisurvey canais --banda 5 --canal 70
```

Without installing anything, from the repository root:

```powershell
$env:PYTHONPATH="$PWD\src"; python -m wifisurvey relatorio dados/varrimento-andar1.csv --planta dados/planta-andar1.svg --saida exemplos/relatorio-andar1.html --png exemplos/mapa-andar1.png
```

The report opens with a double click: the map is embedded as a *data URI*, so
there is no image folder next to it to break when the file is emailed.

### The three example floors

Each floor exists to demonstrate a different problem. `verificar_aceite.py`
requires all three to trigger their own detector.

| | andar1 | andar2 | andar3 |
|---|---|---|---|
| Physical APs | 11 | 9 | 5 |
| Population | 60 | 45 | 90 |
| Average RSSI | -68,4 dBm | -62,3 dBm | -65,2 dBm |
| 2.4 GHz channels | 1, 6, 11 | 1, 6, 11 | 1, 6, 11 |
| 5 GHz channels | 36, 52, 100, 149 | 36, 52, 100, 149 | 36, 52, 100 |
| Contested channels | 7 | 7 | 4 |
| Sizing | 5 APs above what is needed | 4 APs above what is needed | 3 APs missing |
| **What it teaches** | channel conflict | cluster | coverage gap |

**Floor 1 - the spectrum is saturated.** The three canonical 2.4 GHz channels
are all in use by several APs, an 80 MHz emitter on channel 36 occupies 36, 40,
44 and 48 while a 40 MHz one on 56 takes 56 and 60. Seven contested channels,
eleven APs in interference. The signal is acceptable, capacity is in surplus (11
APs for the 6 needed), and the network is bad: the problem is not a missing AP,
it is badly chosen channels.

**Floor 2 - two devices in the same place.** Nine APs, capacity in surplus, good
signal, and still a cluster: two APs 0,9 m apart against a 3,6 m typical
distance. It is the most common installation error that no RSSI-only tool shows.

**Floor 3 - and this is the lesson.** Five dual-band APs support 200 clients for
90 people. Capacity is in surplus, and the floor is still undersized: it is 6 m2
per person against the 35 m2 design figure, and **area** is the bottleneck, not
the AP. It takes 8 APs against the 5 installed, because of the occupancy
criterion: 540 m2 comfortably hold 15 people, and there are 90.

A report that only showed capacity would call this floor perfect, with 110
clients to spare.

### How it works

| Module | Responsibility |
|---|---|
| `leitor.py` | Reads the CSV: band in six spellings, width, coordinates |
| `plano.py` | Network and AP model, and the grouping by BSSID |
| `interferencia.py` | Valid channels, occupied span and overlap |
| `capacidade.py` | Capacity per AP, sizing and problems |
| `mapa.py` | Heatmap: RSSI estimate, colour, HTML and PNG |
| `cli.py` | The command line |

**Grouping by BSSID: why five octets.** A ceiling dual-band AP with three SSIDs
shows up in the survey as six logical networks, six BSSIDs and one access point.
The first five octets of the MAC are equal across the radios; only the sixth
changes. Counting per SSID would report six antennas where one exists, and the
report would tell you to buy six APs for a floor already covered. Counting per
exact BSSID would report two APs where one exists. That is why
`assinatura_do_equipamento` cuts at five octets.

**Overlap is anchored on the primary channel.** A 40 MHz channel with primary 56
occupies 56 and 60, because the `52-64` block is made of 52/56/60/64. An 80 MHz
one with primary 36 occupies 36, 40, 44 and 48. Getting this detail wrong cost a
real bug: with the span **centred** on the primary, 56 would occupy 55 and 57,
channels that do not exist on the 5 GHz grid, and a wide emitter would never
collide with its neighbour. Floor 1 was saturated and the tool said everything
was fine.

**Capacity is not coverage.** `capacidade_do_ap` sums distinct band and width,
never SSID: five SSIDs on the same BSSID are still one antenna. Sizing uses three
independent criteria - coverage, population and occupancy - and the largest one
wins. In 2.4 GHz capacity **drops** as the channel widens (20 MHz: 15 clients;
40 MHz: 10), because the wide channel steals airtime from its neighbours. In
5 GHz it rises (20 MHz: 25; 80 MHz: 100). The asymmetry is real, and it is why
the table is not symmetric.

**The map is an estimate, and says so.** Between two visited points the drawn
value is interpolated with a path-loss exponent of 3.0 (typical indoors), plus
4 dB per wall for every extra 6 m. The report states this explicitly in the
legend. The colour scale follows the range measured on that floor rather than a
fixed scale: on a dense floor with fifteen APs the best signal is always close
by, every point falls between -61 and -36 dBm, and a fixed scale pushes
everything into the same blue.

**The PNG without Pillow.** The heatmap is written as a PNG built with `zlib`
and `struct` from the standard library: header, `IHDR`/`IDAT`/`IEND` chunks and
the compressed data. It is forty lines long, and they will not disappear in
three years as an abandoned dependency. Pillow remains a good tool for this,
but it is not required for a one-floor heatmap.

### Data format

**`dados/varrimento-andar1.csv`** - one row per network seen at a point:

```
bssid,ssid,canal,banda,rssi,x,y,largura_canal
02:00:00:00:01:00,CORP-TI,1,2.4,-44,5.0,6.0,20
02:00:00:00:01:01,CORP-TI,36,5,-42,5.0,6.0,80
```

`banda` accepts `2.4`, `2.4G`, `2,4`, `2400MHz`, `5`, `5G`, `5000MHz`.
`largura_canal` is optional and defaults to 20 when empty.

**`dados/capacidade.yaml`** - capacity per band and width, plus the design
criteria. It is configuration, not truth:

```yaml
capacidade:
  "5":
    "20": 25
    "80": 100
criterios:
  area_por_cliente_m2: 35.0
  rssi_minimo_dbm: -67
  aps_por_1000_m2: 4
```

The program **rejects** absurd parameters instead of emitting a pretty and false
report. Capacity at or below zero, `rssi_minimo_dbm` above -30 (better than any
AP produces) and area per client at or below zero: all rejected at load time. The
list is in [`docs/criterios-de-projeto-wifi.md`](docs/criterios-de-projeto-wifi.md).

### Library use

```python
from wifisurvey.capacidade import Parametros, dimensionar, verifica_projeto
from wifisurvey.leitor import carregar

aps = carregar("dados/varrimento-andar3.csv")
params = Parametros.carregar("dados/capacidade.yaml")

dim = dimensionar(aps, area_m2=540.0, clientes=90, params=params)
print(dim.resumo())
print(f"{dim.falta} AP(s) faltando, capacidade de {dim.capacidade_total}")

for problema in verifica_projeto(aps, params):
    print(problema)
```

Real output of the snippet above:

```
faltam 3 AP(s): 5 instalado(s) para 8 necessario(s)
3 AP(s) faltando, capacidade de 200
```

### What I learned

- **Counting APs per SSID tells you to buy APs you already have.** Floor 1 has
  11 physical APs and 66 logical networks; counting per SSID would ask for 66
  antennas. Cutting the MAC at five octets is what tells the two apart.
- **A channel span is anchored on the primary, and getting that wrong hides the
  problem.** With a centred span, a 40 MHz emitter on 56 would occupy 55 and 57,
  which do not exist on the grid: nothing collided and a saturated floor passed
  as clean. The bug was not in the detector, it was in the channel model.
- **Surplus capacity does not mean a good network.** Floor 3 has capacity for 200
  clients and 90 people, and still needs 3 more APs, because the criterion that
  bites is area per person. Anyone looking only at capacity saves money on a
  floor that keeps dropping.
- **RSSI cannot see an installation error.** Two APs 0,9 m apart add signal
  instead of coverage, and the heatmap shows exactly what you would hope for.
  Only the neighbour distance gives it away.
- **The map has to say it is an estimate.** Between two visited points the value
  is drawn, not measured; without that in the legend, the report becomes proof of
  something nobody measured.

### Limitations

- **The map is interpolation.** Between two visited points the value is drawn,
  not observed. The report legend says so.
- **The AP position is estimated** from the weighted centroid of the samples.
  With a low sample density it shifts by a few metres.
- **Path loss is a model**, with exponent 3.0 and 4 dB per wall every 6 m. It
  predicts for a building with a similar layout; not for a whole block with
  several floors and cabinets in the way.
- **AP capacity is configuration.** It does not come from a vendor catalogue.
- **There is no throughput forecast.** Capacity is how many clients, not how
  fast: 60 clients at -55 dBm on 80 MHz can deliver less than 25 at -67 dBm on
  20 MHz.
- **A single path-loss model for 2.4 and 5 GHz**, which is not physical truth.
  The real difference is small in this context.

### License

MIT. See [LICENSE](LICENSE).

---

<div align="center">
  <sub>Por <a href="https://github.com/KelvinOliveiraCode">Kelvin Oliveira</a> &middot;
  <a href="https://kelvinoliveiracode.github.io/portfolio/">portfolio</a></sub>
</div>
