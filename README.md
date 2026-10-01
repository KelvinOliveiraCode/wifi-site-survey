# wifisurvey

Analisa uma varredura de Wi-Fi, monta mapa de calor de RSSI por andar,
dimensiona quantos access points o andar precisa e aponta onde há sobreposição
de canal. Saída em HTML autocontido e PNG.

Analyses a Wi-Fi survey, builds a per-floor RSSI heatmap, sizes access points
and flags channel overlap. Output is self-contained HTML and PNG.

> **Os dados deste repositório são fictícios.** As três plantas são de 30 m ×
> 18 m, os BSSIDs usam o prefixo local `02:00:00` e os SSIDs (`CORP-TI`,
> `GUEST-LAB`…) não existem. Os modelos de equipamento citados são reais, mas
> nenhuma combinação de fabricante, modelo, canal e firmware aqui descreve um
> ambiente real.

## O problema que ele resolve

Projeto de Wi-Fi é raro na faculdade e comum no primeiro emprego de
infraestrutura. E a conversa com o cliente quase nunca é "coloque este SSID": é
"por que o corredor do 3º andar cai", e essa resposta exige dado medido, não
opinião.

O `wifisurvey` pega o CSV que sai do analisador e responde três coisas:

1. **Onde o sinal está ruim** — o mapa de calor, com o gradiente ajustado à
   faixa realmente medida no andar.
2. **Falta access point?** — por cobertura, por população e por ocupação, e o
   maior dos três vence.
3. **Onde os canais estão brigando** — quem invade quem, contando largura de
   canal e não só o número.

## Instalação

Uma dependência: PyYAML, para ler o arquivo de parâmetros. O projeto roda sem
ela, usando os valores embutidos em `capacidade.py`.

```powershell
git clone <url-do-repositorio>
cd wifi-site-survey
pip install -e ".[dev]"
```

## Uso

```powershell
python -m wifisurvey relatorio dados/varrimento-andar1.csv --planta dados/planta-andar1.svg --saida exemplos/relatorio-andar1.html --png exemplos/mapa-andar1.png
```

Saída real:

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

Os outros dois subcomandos:

```powershell
# Os três andares lado a lado
python -m wifisurvey comparar

# Os canais válidos de cada banda, e a validação de um canal
python -m wifisurvey canais --banda 5 --canal 70
```

O relatório abre com duplo clique, sem servidor e sem internet: o mapa vai
embutido como *data URI*, então não há pasta de imagens ao lado para quebrar
quando o arquivo é mandado por e-mail.

## Os três andares do exemplo

Cada andar existe para demonstrar um problema diferente. O `verificar_aceite.py`
exige que os três acionem o detector correspondente.

| | andar1 | andar2 | andar3 |
|---|---|---|---|
| APs físicos | 11 | 9 | 5 |
| População | 60 | 45 | 90 |
| RSSI médio | −68,4 dBm | −62,3 dBm | −65,2 dBm |
| Canais 2.4 GHz | 1, 6, 11 | 1, 6, 11 | 1, 6, 11 |
| Canais 5 GHz | 36, 52, 100, 149 | 36, 52, 100, 149 | 36, 52, 100 |
| Canais disputados | 7 | 7 | 4 |
| Dimensionamento | falta 1 AP | correto | falta 3 AP |
| **O que ensina** | conflito de canal | aglomerado | falta de cobertura |

**andar1 — o espectro está saturado.** Os três canais de 2.4 GHz canônicos estão
em uso por vários APs, e um emissor de 80 MHz no canal 36 ocupa 36, 40, 44 e 48
enquanto um de 40 MHz no 56 pega 56 e 60. Sete canais em disputa, onze APs em
interferência. O sinal está aceitável e a rede está ruim.

**andar2 — dois aparelhos no mesmo lugar.** Nove APs, capacidade de sobra,
sinal bom, e mesmo assim há um aglomerado: dois APs a 0,9 m um do outro contra
3,6 m de distância típica dos demais. É o erro de instalação mais comum que não
aparece em nenhuma ferramenta que só olha RSSI.

**andar3 - e aqui está a lição.** Cinco APs duais comportam 200
clientes, para 90 pessoas. A capacidade de clientes **sobra**: sobram 110. E
ainda assim o andar está subdimensionado — são 6 m² por pessoa contra os
35 m² de projeto, e é a **área** que vira o gargalo, não o AP. São 8
APs necessários contra os 5 instalados, por causa do critério de
ocupação: 540 m² comportam 15 pessoas confortavelmente, e há 90.

Um relatório que mostrasse só capacidade diria que esse andar está ótimo,
com folga de 110 clientes.

## Como funciona

| Módulo | Responsabilidade |
|---|---|
| `leitor.py` | Lê o CSV: banda em seis grafias, largura, coordenadas |
| `plano.py` | Modelo de rede e de AP, e o agrupamento por BSSID |
| `interferencia.py` | Canais válidos, faixa ocupada e sobreposição |
| `capacidade.py` | Capacidade por AP, dimensionamento e problemas |
| `mapa.py` | Mapa de calor: estimativa de RSSI, cor, HTML e PNG |
| `cli.py` | A linha de comando |

### Agrupar por BSSID: o porquê dos cinco octetos

Um AP de teto dual-band com três SSIDs aparece no varrimento como **seis redes
lógicas, seis BSSIDs, e um access point**. Os cinco primeiros octetos do MAC são
iguais entre os rádios; só o sexto muda.

Contar por SSID daria seis antenas onde existe uma, e o relatório mandaria
comprar seis APs para um andar já servido. Contar por BSSID exato daria dois APs
onde existe um. Por isso `assinatura_do_equipamento` corta em cinco octetos.

### Sobreposição ancorada no canal primário

Um canal de 40 MHz com primário **56** ocupa 56 **e 60**, porque o bloco
`52-64` é formado por 52/56/60/64. Um de 80 MHz com primário 36 ocupa 36, 40, 44
e 48.

O detalhe custa um bug real: com a faixa **centrada** no primário, 56 ocuparia
55 e 57 — canais que não existem na grade de 5 GHz — e um emissor largo jamais
colidiria com o vizinho. O andar 1 estava saturado e a ferramenta dizia que
estava tudo bem.

### Capacidade não é cobertura

`capacidade_do_ap` soma **banda e largura distintas**, nunca SSID: cinco SSIDs no
mesmo BSSID continuam sendo uma antena. O dimensionamento, então, usa três
critérios independentes — cobertura, população e ocupação — e o maior vence.

Em 2.4 GHz a capacidade **cai** com a largura de canal (20 MHz: 15 clientes;
40 MHz: 10), porque o canal largo rouba tempo de ar dos vizinhos. Em 5 GHz ela
sobe (20 MHz: 25; 80 MHz: 100). A assimetria é real, e é o motivo de a tabela
não ser simétrica.

### O mapa é estimativa, e diz isso

Entre dois pontos visitados, o valor desenhado é interpolado por perda de
caminho com expoente 3,0 (típico de interior), mais 4 dB por parede a cada
6 m extras. O relatório marca isso explicitamente na legenda.

A escala de cor acompanha a faixa medida naquele andar, não uma escala fixa.
Num andar denso com quinze APs o melhor sinal está sempre perto, todo ponto cai
entre −61 e −36 dBm, e uma escala fixa empurra tudo para o mesmo azul.

### O PNG sem Pillow

O mapa de calor sai em PNG escrito com `zlib` e `struct`, da biblioteca padrão:
cabeçalho, chunks `IHDR`/`IDAT`/`IEND` e os dados comprimidos. São quarenta
linhas, e elas não vão sumir em três anos como dependência abandonada. Pillow
continua sendo bom para isso — mas não é necessário para um heatmap de um andar.

## Formato dos dados

**`dados/varrimento-andar1.csv`** — uma linha por rede vista em um ponto:

```
bssid,ssid,canal,banda,rssi,x,y,largura_canal
02:00:00:00:01:00,CORP-TI,1,2.4,-44,5.0,6.0,20
02:00:00:00:01:01,CORP-TI,36,5,-42,5.0,6.0,80
```

`banda` aceita `2.4`, `2.4G`, `2,4`, `2400MHz`, `5`, `5G`, `5000MHz`.
`largura_canal` é opcional e assume 20 quando vazio.

**`dados/capacidade.yaml`** — capacidade por banda e largura, e os critérios de
projeto. É configuração, não verdade:

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

O programa **recusa** parâmetros absurdos em vez de emitir relatório bonito e
falso. Capacidade ≤ 0, `rssi_minimo_dbm` acima de −30 (melhor que qualquer AP
produz), área por cliente ≤ 0: todos recusados na carga. A lista está em
[`docs/criterios-de-projeto-wifi.md`](docs/criterios-de-projeto-wifi.md).

## Uso como biblioteca

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

```
faltam 13 AP(s): 5 instalado(s) para 18 necessario(s)
13 AP(s) faltando, capacidade de 200
```

## Testes

```powershell
python -m pytest tests/ -v
```

224 testes, 95% de cobertura. Cobrem a faixa de canal ocupada nos dois sentidos
— o que **deve** e o que **não deve** se sobrepor, porque um detector que acusa
tudo parece cheio de problemas e não encontra nenhum —, o teto e o piso da
capacidade, o agrupamento por assinatura de MAC, a escala de cor do mapa, a
validação dos parâmetros e a CLI inteira.

Verificações que a suíte não cobre sozinha:

```powershell
python tools/verificar_aceite.py      # os três andares acionam seu detector
python tools/verificar_encoding.py    # nenhum caractere corrompido
python tools/verificar_exemplo_limpo.py  # nenhum caminho de máquina no exemplo
python tools/gerar_exemplos.py        # regera os exemplos de forma determinística
```

O `verificar_aceite.py` é o mais importante: ele prova que os CSVs do
repositório exercitam cada detector. Uma suíte com cinco APs de teste passa em
tudo e não serve para uma apresentação.

## Estrutura

```
wifi-site-survey/
├── src/wifisurvey/       # o pacote
├── dados/                # três CSVs, três plantas SVG, parâmetros YAML
├── docs/                 # método de medição e critérios de projeto
├── exemplos/             # três relatórios HTML e três PNGs
├── tests/                # 224 testes
└── tools/                # geradores e verificações
```

## Limitações

Ditas de frente, porque um relatório que esconde o próprio alcance não serve
para nada:

- **O mapa é interpolação.** Entre dois pontos visitados, o valor é desenhado,
  não observado. A legenda do relatório avisa.
- **A posição do AP é estimada** pelo centroide ponderado das amostras. Com
  pouca densidade de pontos, ela desloca alguns metros.
- **A perda de caminho é um modelo**, com expoente 3,0 e 4 dB por parede a cada
  6 m. Preddz para prédio com layout parecido; não parautto com vários andares.
- **A capacidade por AP é configuração.** Não sai de catálogo de fabricante.
- **Não existe previsão de throughput.** Capacidade é quantos clientes, não
  quão rápido. 60 clientes a −55 dBm a 80 MHz podem render menos que 25 a
  −67 dBm a 20 MHz.
- **A perda de caminho é um único modelo para 2.4 e 5 GHz**, o que não é
  verdade física. A diferença real é pequena neste contexto.

## Licença

MIT.
