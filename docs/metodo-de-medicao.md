# Método de medição

Um mapa de calor bonito e um número inventado tem o mesmo valor. Este documento
explica o que o `wifisurvey` mede, o que ele **estima**, e onde está a diferença
— porque a diferença é exatamente o que faz um relatório servir para conversar
com o cliente ou servir só para impressionar em reunião.

## O que um varrimento realmente é

Um varrimento de Wi-Fi sai do analisador como uma linha por **rede vista em um
ponto**. Não é uma fotografia do andar: é uma lista de amostras, e o número de
amostras é limitado por quantas vezes alguém andou com o adaptador.

O CSV do projeto tem essa forma:

```
bssid,ssid,canal,banda,rssi,x,y,largura_canal
02:00:00:00:01:00,CORP-TI,1,2.4,-47,5.0,6.0,20
02:00:00:00:01:00,CORP-TI,1,2.4,-58,15.0,6.0,20
```

Duas linhas do mesmo `bssid` com coordenadas diferentes são a mesma rede medida
em dois lugares. Isso importa mais do que parece, e o motivo está na seção
seguinte.

## Rede lógica, AP físico e o porquê do BSSID

Um access point de teto transmite vários SSIDs ao mesmo tempo — corporativo,
visitantes, IoT, VoIP — e em dual-band transmite em **dois rádios**, cada um com
o seu endereço MAC. Um único aparelho pode aparecer no varrimento como:

- 6 redes lógicas (3 SSIDs × 2 rádios)
- 6 BSSIDs diferentes
- **1 access point**

Os cinco primeiros octetos do MAC são iguais entre os rádios; só o sexto muda.
É por isso que `assinatura_do_equipamento` corta em cinco octetos, e não em
seis.

Contar por SSID daria seis antenas onde existe uma. O dimensionamento somaria
seis vezes a capacidade, e o relatório recomendaria seis APs novos para um andar
que já está servido. Contar por BSSID exato daria o erro oposto: dois APs onde
existe um. Nenhum dos dois funciona, e os dois são erros que aparecem em campo.

> O SSID é o que o usuário vê; o BSSID é o que o rádio é. Uma rede lógica é o
> par dos dois.

## De onde vem o RSSI

RSSI é a potência recebida, em dBm. Pérdida de caminho em espaço livre é
20 dB por década: dobrar a distância custa 6 dB.

Dentro de um prédio isso não basta, e é o motivo de o modelo do projeto usar
expoente 3 em vez de 2:

```python
perda = 30 * log10(distancia)      # expoente 3.0, típico de interior
if distancia > 6:
    perda += 4 * (distancia - 6) / 6   # uma parede a cada 6 m extras
```

O sinal não viaja em linha reta: ele contorna moveis, atravessa corredores e
passa por portas. Com um AP de teto a −30 dBm a 1 m, o modelo entrega:

| Distância | RSSI | Leitura |
|---|---|---|
| 3 m | −44 dBm | confortável |
| 10 m | −60 dBm | no limite do confortável |
| 20 m | −76 dBm | sinal fraco de verdade |

O modelo de espaço livre daria −53 dBm a 20 m, otimista demais, e o mapa sairia
quase todo azul. Esse é o tipo de erro que faz um relatório dizer que o sinal
está bom quando o usuário, no lugar, está reclamando da queda.

**O gerador dos CSVs importa esta mesma função** de `wifisurvey.mapa`. Não por
economia de linhas: se o dado e o mapa usassem curvas diferentes, o mapa estaria
desenhando um sinal que o CSV não produz, e a diferença seria um bug invisível
que ninguém encontraria — porque cada metade estaria internamente correta.

## A posição estimada do AP

O varrimento não diz onde o AP está: diz onde alguém estava quando o leu. A
posição é estimada pelo centroide das amostras, ponderado pela potência
recebida (10^(RSSI/10), a lei de Friis) — o sinal mais forte foi medido mais
perto do AP, então ele puxa o centroide para o lugar certo.

O detalhe que custa um bug: **o peso tem de ser a potência, não o módulo do
RSSI**. Como o RSSI já é negativo, `abs(rssi)` dá peso *maior* à leitura mais
fraca, que é a mais distante. O centroide migrava para o centro da planta, onde
ficam os cantos longes, e todos os APs do andar apareciam empilhados no mesmo
ponto. O mapa ficava bonito e completamente errado.

## O mapa é estimativa, não medição

Entre dois pontos visitados, o valor desenhado é **interpolado**. O relatório
diz isso explicitamente, e não é mods: é a diferença entre um cliente aceitar o
mapa e o cliente achar que o técnico mediu o corredor inteiro.

Por isso a escala de cor acompanha a faixa medida no andar, e não uma escala
fixa de −80 a −35 dBm. Num andar denso, com quinze APs, o melhor sinal está
sempre perto e todo ponto cai entre −61 e −36 dBm: uma escala fixa empurra
tudo para o mesmo tom de azul e o mapa não informa nada. Escalando pela faixa
real, o gradiente mostra a **distribuição**, que é o que interessa.

## Medido contra estimado

| | Origem | Confiabilidade |
|---|---|---|
| RSSI nas amostras do CSV | medida | alta, é leitura do receptor |
| Posição do AP | estimada | média, depende da densidade de pontos |
| RSSI entre dois pontos | estimado | baixa, é interpolação |
| Capacidade por AP | configuração | depende do fabricante |
| Número de APs necessário | cálculo | depende dos critérios escolhidos |

A última linha é a mais importante: **ninguuma delas é medição**. Todas são
decisão. O relatório mostra a decisão e os critérios que a produziram, para
que o cliente possa discordar da decisão.

## Como reproduzir uma medição de verdade

1. Defina a grade de pontos. O projeto usa uma grade de 5×5 por AP, o que dá
   posições estimadas boas. Com quatro pontos, dois APs plantados a 7 m saíam
   estimados a 3 m, e o alerta de interferência disparava em todo andar.
2. Fique parado **três segundos** em cada ponto, com o adaptador no lugar que o
   cliente vai usar. RSSI medido no chão não descreve quem segura o celular.
3. Registre o `canal` e a `largura_canal` de cada rede. O varrimento de canal
   automático mostra o canal atual, não a largura configurada, e é a largura que
   determina a sobreposição.
4. Meça no horário de pico. Um andar vazio às 11h da manhã tem menos
   interferência e mais RSSI que o mesmo andar cheio às 18h.
5. Repita em 5 GHz e em 2.4 GHz. São dois problemas diferentes, e medir um só dá
   metade do diagnóstico.
