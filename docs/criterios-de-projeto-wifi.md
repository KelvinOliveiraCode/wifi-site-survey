# Critérios de projeto Wi-Fi

Os números em `dados/capacidade.yaml` não são verdade universal: são
**configuração**. Este documento diz de onde vêm, o que cada um controla e o que
acontece quando você muda. Sem isso, o relatório vira uma caixa-preta que emite
números, e ninguém no cliente consegue dizer se estão certos.

Todos os valores são sobrescritos com `--parametros`:

```powershell
python -m wifisurvey relatorio --andar andar1 --parametros dados/meus.yaml --saida relatorio.html
```

## Canais

### Por que 2.4 GHz só aceita 1, 6 e 11

O espectro de 2.4 GHz tem cerca de 83 MHz utilizáveis. Um canal ocupa ~22 MHz.
Três cabem sem sobreposição; quatro não. A norma define 13 canais (1 a 13, ou
1 a 11 em parte do mundo), mas usar o canal 3 não é "uma variante do canal 1":
ele sobrepõe o canal 1 e o 6, e derruba o SNR dos dois. Três canais
inextricáveis, não uma escolha entre treze.

O mesmo número em bandas diferentes não é o mesmo canal: 6 em 2.4 GHz fica perto
de 2437 MHz e 36 em 5 GHz perto de 5180 MHz. Por isso a comparação de
sobreposição nunca cruza bandas.

### Por que 5 GHz usa blocos de quatro

5 GHz tem muito mais canais e menos vizinhos. O bloco `36-48` são quatro canais
de 20 MHz (36, 40, 44, 48) que não se sobrepõem. É por isso que **um** canal de
20 MHz no 36 e **outro** no 44 convivem, e por isso que a largura importa tanto:

| Largura | Ocupa | Consequência |
|---|---|---|
| 20 MHz | 1 canal | quatro APs por bloco |
| 40 MHz | 2 canais | dois APs por bloco |
| 80 MHz | 4 canais | **um** AP por bloco, e derruba quem estiver nos vizinhos |
| 160 MHz | 8 canais | dois blocos, e só se o AP não for legado |

A lacuna entre 64 e 100 é DFS: o emissor só entra ali depois de detectar radar,
e muda de canal sozinho. Um projeto que depende disso entrega um equipamento
que se reconfigura sem ninguém avisar.

### O erro do canal centrado

A faixa ocupada é **ancorada no canal primário**, não centrada nele. Um canal de
40 MHz com primário 56 ocupa 56 **e 60**, porque o bloco `52-64` é formado por
52/56/60/64. Um de 80 MHz com primário 36 ocupa 36, 40, 44 e 48.

Se a faixa fosse centrada, 56 ocuparia 55 e 57 — canais que **não existem** na
grade de 5 GHz — e um emissor de 40 MHz jamais colidiria com o vizinho de 20 MHz.
Era esse o bug que impedia o relatório de acusar sobreposição em 5 GHz: o
andar inteiro estava saturado e a ferramenta dizia que estava tudo bem.

## Capacidade por AP

```yaml
capacidade:
  "2.4":
    "20": 15
    "40": 10
  "5":
    "20": 25
    "40": 50
    "80": 100
    "160": 200
```

Dois padrões aqui, e a diferença entre eles é o ponto:

- **Em 5 GHz a capacidade cresce com a largura.** O canal largo é mais limpo, o
  AP usa mais espectro e cabe mais cliente. Dobrar a largura dobra a capacidade.
- **Em 2.4 GHz a capacidade *cai* com a largura.** Um canal de 40 MHz não dobra
  nada: rouba o tempo de ar dos vizinhos, e a mesma rádio carrega menos cliente
  próprio. Essa assimetria é real e é o motivo de a tabela não ser simétrica.

E o número em si não vem de lei nenhuma: muda com o número de antenas, com
MIMO, com o tipo de cliente e com o tráfego. O valor do repositório é um
orçamento de referência para um escritório com notebooks e celulares.

### A soma ignora SSID

`capacidade_do_ap` soma **banda e largura distintas**, nunca SSID. Cinco SSIDs no
mesmo BSSID continuam sendo uma antena. Somar por rede daria a um AP dual-band
cinco vezes a capacidade dele.

## Critérios de dimensionamento

| Critério | Padrão | O que controla |
|---|---|---|
| `area_por_cliente_m2` | 35,0 | quanto espaço cada pessoa ocupa |
| `distancia_max_entre_aps_m` | 15,0 | espaçamento de projeto entre APs |
| `rssi_minimo_dbm` | −67 | abaixo disso o sinal é rejeito |
| `aps_por_1000_m2` | 4 | densidade de cobertura |

O dimensionamento usa três critérios independentes e **o maior vence**:

- **cobertura** — `area / 1000 × aps_por_1000_m2`
- **população** — `clientes / capacidade_de_um_ap`
- **ocupação** — quantas "rodadas" de gente o espaço comporta, por
  `area_por_cliente_m2`

O terceiro é o que costuma ser ignorado e é o mais revelador. Com 35 m² por
cliente, um andar de 100 m² comporta 2 pessoas confortavelmente. Se o projeto
diz 200 pessoas ali dentro, são 100 rodadas: a **área** vira o gargalo antes de o
AP virar, e nenhumnenhum AP novo resolve isso resolve isso.

### Por que −67 dBm

É o limiar em que a taxa dede vazao cai mais rápido do que as barras de sinal
sugerem. Abaixo dele o cliente continua conectado — o que é pior, porque o
problema aparece como lentidão e ninguém sabe procurar a causa. Não é um número
bonito: é onde a curva dede vazao se separa da leitura de sinal.

### Por que o alerta de distância compara com a mediana

Este é o ponto que mais gera discussão, e o argumento é simples: **um andar
com quinze APs em 540 m² tem, obrigatoriamente, APs a menos de 15 m uns dos
outros.** Quinze APs com 15 m de separação ocupariam 3375 m². Um alerta que
comparasse a menor distância com o critério de projeto dispararia em todo andar
bem povoado, e um alerta que dispara sempre não é lido por ninguém.

O que separa um aglomerado de um andar bem projetado é a **irregularidade**. Se
um AP está a 0,9 m do seu vizinho enquanto os outros estão a 3,6 m dos seus
vizinhos, alguém prendeu dois aparelhos no mesmo ponto — e aí sobra sinal ali e
falta em volta.

Por isso o gatilho é `minimo < 0,35 × mediana`, e a estatística é a distância ao
**vizinho mais próximo** de cada AP, não a menor distância entre todos os pares.
Entre todos os pares, a menor distância é quase sempre pequena por acaso, mesmo
em planta regular: com quinze APs em 540 m², é matematicamente obrigatório que
dois estejam perto. A distância ao vizinho mais próximo é bem condicionada —
em planta uniforme todas se parecem, e só dispara quando existe aglomerado de
verdade.

## O que estes números não fazem

- **Não previsam throughput.** Capacidade é quantos clientes, não quão rápido.
  Um andar com 60 clientes a −55 dBm em 5 GHz a 80 MHz entrega talvez 40 Mbps
  para cada, e um com 25 clientes a −67 dBm entrega mais.
- **Não conhecem a planta.** Uma parede de drywall custa 3 dB; uma de concreto
  armoured custa 15. Dois andares com a mesma metragem e os mesmos números no
  YAML precisam de APs diferentes.
- **Não modelam espectro de vizinho.** O projeto olha só para dentro do prédio.
  Um AP num prédio comercial compete com as redes dos prédios ao lado, e isso
  não está em lugar nenhum do CSV.
- **Não säo medição.** São configuração. `[metodo-de-medicao.md](metodo-de-medicao.md)`
  separa o que é medido do que é estimado; este arquivo separa o que é fato do
  que é escolha.

## Ajustando para o seu caso

Copie o arquivo, mude os números, mantenha o nome das chaves e passe
`--parametros`. O programa **recusa** parâmetros absurdos em vez de emitir um
relatório bonito e falso:

| Valor recusado | Por quê |
|---|---|
| capacidade ≤ 0 | nenhum AP suporta nada |
| `rssi_minimo_dbm` acima de −30 | melhor que qualquer AP produz |
| `rssi_minimo_dbm` abaixo de −100 | o receptor não distingue mais ruído |
| `area_por_cliente_m2` ≤ 0 | divisão por zero no cálculo |
| `aps_por_1000_m2` ≤ 0 | divisão por zero no cálculo |
| banda diferente de 2.4 ou 5 | banda que não existe |
| largura diferente de 20/40/80/160 | largura que não existe |

A recusa é preferível ao relatório. Um relatório que afirma que 1000 clientes
cabem num AP porque alguém digitou `capacidade: 0` não é um bug de um caractere:
é uma decisão de negócio tomada com o número errado.
