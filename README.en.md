# wifisurvey (English)

Analyses a Wi-Fi survey, builds a per-floor RSSI heatmap, sizes access points
and flags channel overlap. Output is self-contained HTML and PNG.

Versão em português: [`README.md`](README.md)

> **All data in this repository is fictional.** The three floor plans are
> 30 m × 18 m, the BSSIDs use the locally-administered `02:00:00` prefix, and
> the SSIDs (`CORP-TI`, `GUEST-LAB`…) do not exist. The device models quoted are
> real, but no manufacturer/model/channel combination here describes a real
> environment.

## The problem it solves

Wi-Fi design is rare in university and common in an infrastructure team's first
job. And the conversation with the client is rarely "deploy this SSID": it is
"why does the third floor corridor drop", and that answer needs measured data,
not opinion.

`wifisurvey` takes the CSV an analyser exports and answers three questions:

1. **Where is the signal weak?** The heatmap, with the gradient scaled to the
   range actually measured on that floor.
2. **Is an access point missing?** By coverage, by population and by
   occupancy — the largest of the three wins.
3. **Where are channels colliding?** Who overruns whom, counting channel width
   and not just the channel number.

## Install

One dependency: PyYAML, to read the parameters file. The project runs without
it, using the defaults embedded in `capacidade.py`.

```powershell
git clone <repository-url>
cd wifi-site-survey
pip install -e ".[dev]"
```

## Usage

```powershell
python -m wifisurvey relatorio dados/varrimento-andar1.csv --planta dados/planta-andar1.svg --saida exemplos/relatorio-andar1.html --png exemplos/mapa-andar1.png
```

Actual output:

```
Andar: andar1
  APs fisicos: 11 (66 redes logicas agrupadas por BSSID)
  RSSI medio: -68.4 dBm
  Canais 2.4 GHz em uso: 1, 6, 11 -> recomendado 1
  Canais 5 GHz em uso: 36, 52, 100, 149 -> recomendado 40
  Dimensionamento: faltam 1 AP(s): 11 instalado(s) para 12 necessario(s)
  Problemas: 0
  PNG do mapa: exemplos\mapa-andar1.png (36567 bytes)
  Relatorio: exemplos\relatorio-andar1.html
  Planta conferida: dados\planta-andar1.svg
```

The other two subcommands:

```powershell
# All three floors side by side
python -m wifisurvey comparar

# The valid channels of each band, plus validation of one channel
python -m wifisurvey canais --banda 5 --canal 70
```

The report opens on double-click, with no server and no internet: the map is
embedded as a *data URI*, so there is no sibling image folder to break when the
file is emailed.

## The three example floors

Each floor exists to demonstrate a different problem, and
`verificar_aceite.py` requires all three to trigger their detector.

| | andar1 | andar2 | andar3 |
|---|---|---|---|
| Physical APs | 11 | 9 | 5 |
| Population | 60 | 45 | 90 |
| Mean RSSI | −68.4 dBm | −62.3 dBm | −65.2 dBm |
| 2.4 GHz channels | 1, 6, 11 | 1, 6, 11 | 1, 6, 11 |
| 5 GHz channels | 36, 52, 100, 149 | 36, 52, 100, 149 | 36, 52, 100 |
| Contested channels | 7 | 7 | 4 |
| Sizing | 1 AP short | correct | 13 APs short |
| **What it teaches** | channel conflict | clustering | coverage shortfall |

**andar1 — the spectrum is saturated.** All three canonical 2.4 GHz channels
are in use by several APs, and an 80 MHz transmitter on channel 36 occupies 36,
40, 44 and 48 while a 40 MHz one on 56 takes 56 and 60. Seven contested
channels, eleven APs in interference. The signal is acceptable and the network
is bad.

**andar2 — two devices in the same spot.** Nine APs, spare capacity, good
signal, and still a cluster: two APs 0.9 m apart against 3.6 m of typical
spacing for the rest. It is the most common installation mistake that no
RSSI-only tool will ever report.

**andar3 — and here is the lesson.** Five dual-band APs support 200 clients for
90 people. Client capacity **is not short**. The floor is still undersized: it
is 6 m² per person against the 35 m² design guideline, so **area** is the
bottleneck, not the AP. A report showing capacity alone would call this floor
fine.

## How it works

| Module | Responsibility |
|---|---|
| `leitor.py` | Reads the CSV: six band spellings, width, coordinates |
| `plano.py` | Network and AP model, and the BSSID grouping |
| `interferencia.py` | Valid channels, occupied range, overlap |
| `capacidade.py` | Per-AP capacity, sizing, design problems |
| `mapa.py` | Heatmap: RSSI estimate, colour, HTML and PNG |
| `cli.py` | The command line |

### Grouping by BSSID: why five octets

A ceiling dual-band AP with three SSIDs shows up in a survey as **six logical
networks, six BSSIDs, and one access point**. The first five MAC octets are
identical across radios; only the sixth changes.

Counting by SSID would report six antennas where there is one, and the report
would tell the client to buy six APs for a floor already covered. Counting by
exact BSSID would report two APs where there is one. That is why
`assinatura_do_equipamento` cuts at five octets.

### Overlap anchored on the primary channel

A 40 MHz channel with primary **56** occupies 56 **and 60**, because block
`52-64` is made of 52/56/60/64. An 80 MHz channel with primary 36 occupies 36,
40, 44 and 48.

This detail costs a real bug: with the range *centred* on the primary, 56 would
occupy 55 and 57 — channels that do not exist on the 5 GHz grid — and a wide
transmitter would never collide with its neighbour. Floor 1 was saturated and
the tool reported everything fine.

### Capacity is not coverage

`capacidade_do_ap` sums **distinct band and width combinations**, never SSID:
five SSIDs on one BSSID are still one antenna. Sizing then uses three
independent criteria — coverage, population and occupancy — and the largest
wins.

In 2.4 GHz capacity **falls** as channel width grows (20 MHz: 15 clients;
40 MHz: 10), because the wide channel steals airtime from neighbours. In 5 GHz
it rises (20 MHz: 25; 80 MHz: 100). The asymmetry is real, and it is why the
table is not symmetric.

### The map is an estimate, and says so

Between two visited points, the drawn value is interpolated using path loss with
an exponent of 3.0 (typical indoors), plus 4 dB per wall for every extra 6 m.
The report states this explicitly in the legend.

The colour scale follows the range measured on that floor rather than a fixed
scale. On a dense floor with fifteen APs the strongest signal is always nearby,
every point falls between −61 and −36 dBm, and a fixed scale pushes everything
into the same shade of blue.

### The PNG without Pillow

The heatmap is written as a PNG using `zlib` and `struct` from the standard
library: header, `IHDR`/`IDAT`/`IEND` chunks and compressed data. That is forty
lines, and it will not disappear in three years the way an abandoned dependency
does. Pillow is still good at this — but it is not required for a one-floor
heatmap.

## Data formats

**`dados/varrimento-andar1.csv`** — one row per network seen at one point:

```
bssid,ssid,canal,banda,rssi,x,y,largura_canal
02:00:00:00:01:00,CORP-TI,1,2.4,-44,5.0,6.0,20
02:00:00:00:01:01,CORP-TI,36,5,-42,5.0,6.0,80
```

`banda` accepts `2.4`, `2.4G`, `2,4`, `2400MHz`, `5`, `5G`, `5000MHz`.
`largura_canal` is optional and defaults to 20 when empty.

**`dados/capacidade.yaml`** — capacity per band and width, plus the design
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

The tool **refuses** absurd parameters rather than emitting a pretty, false
report. Capacity ≤ 0, `rssi_minimo_dbm` above −30 (better than any AP
produces), area per client ≤ 0: all rejected on load. The full list is in
[`docs/criterios-de-projeto-wifi.md`](docs/criterios-de-projeto-wifi.md)
(Portuguese).

## Library use

```python
from wifisurvey.capacidade import Parametros, dimensionar, verifica_projeto
from wifisurvey.leitor import carregar

aps = carregar("dados/varrimento-andar3.csv")
params = Parametros.carregar("dados/capacidade.yaml")

dim = dimensionar(aps, area_m2=540.0, clientes=90, params=params)
print(dim.resumo())
print(f"{dim.falta} AP(s) short, capacity {dim.capacidade_total}")

for problem in verifica_projeto(aps, params):
    print(problem)
```

```
faltam 13 AP(s): 5 instalado(s) para 18 necessario(s)
13 AP(s) short, capacity 200
```

Module, function and field names stay in Portuguese to match the portfolio and
the CSV data; `verificar_*` is the tool naming convention. The domain
vocabulary maps as: `fabricante`/vendor, `modelo`/`model`, `firmware`,
`criticidade`/criticality, `exposicao_red`/network exposure.

## Tests

```powershell
python -m pytest tests/ -v
```

224 tests, 95% coverage. They cover the occupied channel range in both
directions — what **must** and what **must not** overlap, because a detector
that flags everything looks full of problems and finds none —, the capacity
clamp at both ends, MAC-signature grouping, the map's colour scale, parameter
validation, and the whole CLI.

Checks the suite alone does not cover:

```powershell
python tools/verificar_aceite.py         # all three floors trigger their detector
python tools/verificar_encoding.py       # no corrupted characters
python tools/verificar_exemplo_limpo.py  # no local paths in the examples
python tools/gerar_exemplos.py           # regenerates examples deterministically
```

`verificar_aceite.py` is the important one: it proves the repository CSVs
exercise every detector. A test suite built on five synthetic APs passes
everything and is useless in a presentation.

## Structure

```
wifi-site-survey/
├── src/wifisurvey/       # the package
├── dados/                # three CSVs, three floor-plan SVGs, parameters YAML
├── docs/                 # measurement method and design criteria (Portuguese)
├── exemplos/             # three HTML reports and three PNGs
├── tests/                # 224 tests
└── tools/                # generators and verification scripts
```

## Limitations

Stated up front, because a report that hides its own reach is worth nothing:

- **The map is interpolation.** Between two visited points the value is drawn,
  not observed. The report's legend says so.
- **AP position is estimated** from the power-weighted centroid of samples. With
  sparse points it drifts by a few metres.
- **Path loss is a model**, with exponent 3.0 and 4 dB per wall every 6 m. It
  predicts reasonably for a similar layout; not for every multi-floor building.
- **Per-AP capacity is configuration.** It does not come from a vendor sheet.
- **There is no throughput prediction.** Capacity is how many clients, not how
  fast. 60 clients at −55 dBm on 80 MHz may deliver less than 25 clients at
  −67 dBm on 20 MHz.
- **One path-loss model covers both 2.4 and 5 GHz**, which is not physically
  true. The real difference is small in this context.

## License

MIT.
