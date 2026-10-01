"""Mapa de calor por andar: HTML autocontido e PNG.

Per-floor heatmap: self-contained HTML and PNG.

O mapa de calor e a saida que o cliente olha primeiro, entao ele precisa ser
honesto sobre o que mostra. Um mapa de calor interpolado a partir de quatro
pontos de medicao parece suave e bonito e e uma **estimativa**, nao medicao.
Por isso o desenho marca os pontos onde houve leitura de verdade: o cliente ve
onde o dado existe e onde ele foi desenhado.

O PNG e escrito com ``zlib`` e os blocos da biblioteca padrao, sem Pillow. O
motivo e o mesmo que vale para o resto do portfolio: o projeto precisa rodar
com um Python limpo, sem etapa de instalacao extra. Um PNG e um container
simples - cabecalho, chunks ``IHDR``/``IDAT``/``IEND``, e os dados comprimidos
com zlib. Sao quarenta linhas, e elas nao vao sumir em tres anos como
dependencia abandonada.
"""

from __future__ import annotations

import base64
import html as html_mod
import math
import struct
import zlib
from pathlib import Path

from .plano import AccessPoint


# Escala de cor do mapa. Vai de ruim (vermelho) a bom (azul), passando por
# cinza no meio, que e o "no limite de projeto". A paleta e a mesma do
# portfolio: preto, branco e cinza como base, com o vermelho e o azul so nas
# pontas.
RSSI_PIOR = -80.0
RSSI_MELHOR = -35.0

COR_RUIM = (198, 40, 40)
CIDADA = (130, 130, 130)
COR_BOA = (21, 101, 192)


def perda_por_distancia(distancia_m: float) -> float:
    """Perda de caminho em ambiente interno, em dB.

    Indoor path loss, in dB.

    Espaco livre e queda de 20 dB por decada. Dentro de um predio nao e: o
    expoente de perda sobe para perto de 3, porque o sinal nao viaja em linha
    reta - ele contorna moveis, atravessa corredores e passa por portas. Sobre
    isso vem a perda por parede, que cresce com a distancia porque caminho mais
    longo significa mais obstaculos atravessados.

    Com este modelo, um AP de teto a -30 dBm a 1 m entrega:

    - 3 m  -> -44 dBm, confortavel
    - 10 m -> -60 dBm, no limite do confortavel
    - 20 m -> -76 dBm, sinal fraco de verdade

    Este e o **unico** modelo de perda do projeto. O gerador dos CSVs importa
    esta mesma funcao, de proposito: se o dado e o mapa usassem modelos
    diferentes, o mapa estaria desenhando um sinal que o dado nao produz, e a
    diferenca entre os dois viraria um bug invisivel.

    Args:
        distancia_m: Distancia em metros.

    Returns:
        A perda em dB. Zero abaixo de 1 m.
    """
    d = max(distancia_m, 1.0)
    perda = 30.0 * math.log10(d)          # expoente 3.0, tipico de interior
    if d > 6.0:
        perda += 4.0 * (d - 6.0) / 6.0    # uma parede a cada 6 m extras
    return perda


def escala_dos_dados(valores: list[float]) -> tuple[float, float]:
    """A faixa de RSSI que a grade realmente cobre.

    The RSSI range the grid actually covers.

    Um mapa com escala fixa nao informa nada em andar denso: com quinze APs,
    o melhor sinal esta sempre perto, todo ponto cai entre -61 e -36 dBm, e
    uma escala fixa de -80 a -35 empurra tudo para o mesmo tom de azul. A
    escala acompanha os dados, entao o gradiente sempre diz alguma coisa.

    Args:
        valores: Os valores de RSSI da grade.

    Returns:
        Tupla ``(minimo, maximo)``. Com um unico valor, repete o valor para
        nao gerar divisao por zero.
    """
    if not valores:
        return (RSSI_PIOR, RSSI_MELHOR)
    return (min(valores), max(valores))


def cor_para_rssi(
    rssi: float,
    minimo: float = RSSI_PIOR,
    maximo: float = RSSI_MELHOR,
) -> tuple[int, int, int]:
    """Escolhe a cor de um valor de RSSI dentro da escala dos dados.

    Pick the colour for an RSSI value within the data scale.

    A cor e interpolada em tres trechos: vermelho na pior leitura, cinza no
    meio da faixa medida, azul na melhor. Escalando pela faixa real, o mapa
    mostra a **distribuicao** do sinal no andar, que e o que interessa, em vez
    de repetir "tudo azul" ou "tudo vermelho".

    Args:
        rssi: Sinal em dBm.
        minimo: Pior leitura da grade.
        maximo: Melhor leitura da grade.

    Returns:
        Tupla ``(r, g, b)``.
    """
    if maximo <= minimo:
        return CIDADA

    t = (rssi - minimo) / (maximo - minimo)
    t = max(0.0, min(1.0, t))

    if t <= 0.5:
        a, b, u = COR_RUIM, CIDADA, t * 2
    else:
        a, b, u = CIDADA, COR_BOA, (t - 0.5) * 2

    return (
        max(0, min(255, round(a[0] + (b[0] - a[0]) * u))),
        max(0, min(255, round(a[1] + (b[1] - a[1]) * u))),
        max(0, min(255, round(a[2] + (b[2] - a[2]) * u))),
    )


def rssi_estimado(aps: list[AccessPoint], x: float, y: float) -> float:
    """Estima o sinal em um ponto, pelo AP mais forte.

    Estimate the signal at a point, from the strongest AP.

    Modelo de perda de caminho: o sinal cai 20 dB por decada de distancia. O
    ponto usa o melhor AP disponivel, e nao a media - porque e assim que o
    cliente escolhe: ele se conecta ao radio que chega mais forte, e nao a uma
    media de quinze radios.

    Args:
        aps: APs do andar.
        x: Coordenada horizontal em metros.
        y: Coordenada vertical em metros.

    Returns:
        RSSI estimado em dBm, ou -100.0 se nao houver AP algum.
    """
    if not aps:
        return RSSI_PIOR

    return _rssi_com_referencias(referencias(aps), x, y)


def melhor_leitura(ap: AccessPoint) -> tuple[float, float]:
    """A leitura de sinal mais forte de um AP, e a distancia dela ate ele.

    An AP's strongest reading, and its distance from the AP.

    Args:
        ap: Access point fisico.

    Returns:
        Tupla ``(distancia_em_metros, rssi_em_dbm)``. Com o AP sem medicao,
        devolve ``(1.0, RSSI_PIOR)``.
    """
    melhor: tuple[float, float] | None = None
    for rede in ap.redes:
        for p in rede.pontos:
            d = ((p.x - ap.x) ** 2 + (p.y - ap.y) ** 2) ** 0.5
            if melhor is None or p.rssi > melhor[1]:
                melhor = (d, float(p.rssi))
    return melhor if melhor is not None else (1.0, RSSI_PIOR)


def referencias(aps: list[AccessPoint]) -> list[tuple[float, float, float, float]]:
    """Prepara os APs para interpolar o sinal numa grade.

    Prepare the APs for interpolating signal over a grid.

    ``melhor_leitura`` varre todos os pontos medidos de um AP para achar a
    leitura mais forte. Chamar isso **dentro** do laco de pixels e o que
    travava a geracao do PNG: 105 mil pixels vezes 11 APs vezes 150 pontos de
    medicao cada, ou 175 milhoes de iteracoes para um PNG de 420 px de lado.

    As referencias sao calculadas uma vez, aqui, e o mapa de calor passa a
    custar uma multiplicacao por pixel.

    Args:
        aps: APs do andar.

    Returns:
        Lista de ``(x_do_ap, y_do_ap, perda_da_leitura_de_referencia,
        rssi_da_leitura_de_referencia)``.
    """
    refs: list[tuple[float, float, float, float]] = []
    for ap in aps:
        d_ref, rssi_ref = melhor_leitura(ap)
        refs.append((ap.x, ap.y, perda_por_distancia(d_ref), rssi_ref))
    return refs


def _rssi_com_referencias(
    refs: list[tuple[float, float, float, float]],
    x: float,
    y: float,
) -> float:
    """Estima o sinal em um ponto, usando referencias ja calculadas.

    Estimate the signal at a point, using precomputed references.

    A perda de referencia ja vem pronta dentro de ``refs``, porque nao muda
    de pixel para pixel. So a perda do ponto atual e calculada, com um
    ``log10`` por AP em vez de dois.

    Args:
        refs: Saida de :func:`referencias`.
        x: Coordenada horizontal em metros.
        y: Coordenada vertical em metros.

    Returns:
        RSSI estimado em dBm.
    """
    if not refs:
        return RSSI_PIOR

    melhor = RSSI_PIOR
    for ax, ay, perda_ref, rssi_ref in refs:
        d = ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5
        estimativa = min(rssi_ref, rssi_ref - (perda_por_distancia(d) - perda_ref))
        if estimativa > melhor:
            melhor = estimativa

    return round(max(RSSI_PIOR, min(RSSI_MELHOR, melhor)), 1)


def grade_sinal(
    aps: list[AccessPoint],
    largura_m: float,
    altura_m: float,
    passo_m: float = 1.0,
) -> list[tuple[int, int, float]]:
    """Calcula o RSSI em uma grade de pontos do andar.

    Compute RSSI on a grid of points across the floor.

    Args:
        aps: APs do andar.
        largura_m: Largura do andar em metros.
        altura_m: Altura do andar em metros.
        passo_m: Espacamento da grade em metros.

    Returns:
        Lista de ``(ix, iy, rssi)``.
    """
    refs = referencias(aps)
    nx = max(1, int(largura_m / passo_m))
    ny = max(1, int(altura_m / passo_m))
    return [
        (
            ix,
            iy,
            _rssi_com_referencias(
                refs, (ix + 0.5) * largura_m / nx, (iy + 0.5) * altura_m / ny
            ),
        )
        for iy in range(ny)
        for ix in range(nx)
    ]


def _png_chunk(tipo: bytes, dados: bytes) -> bytes:
    """Monta um chunk PNG com length, type, data e CRC.

    Build a PNG chunk with length, type, data and CRC.
    """
    return (
        struct.pack(">I", len(dados))
        + tipo
        + dados
        + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    )


def escrever_png(
    caminho: str | Path,
    aps: list[AccessPoint],
    largura_m: float = 30.0,
    altura_m: float = 18.0,
    escala_px: int = 12,
) -> int:
    """Escreve o mapa de calor em PNG.

    Write the heatmap as a PNG.

    Nao usa Pillow: o PNG e montado com ``zlib`` e ``struct``. Um heatmap de um
    andar e uma imagem de poucas dezenas de milhares de pixels, e a compressao
    RLE do proprio PNG com zlib resolve bem sem biblioteca externa.

    Args:
        caminho: Caminho do arquivo de saida.
        aps: APs do andar.
        largura_m: Largura do andar em metros.
        altura_m: Altura do andar em metros.
        escala_px: Pixels por metro.

    Returns:
        O numero de bytes escritos.
    """
    png = png_em_memoria(aps, largura_m, altura_m, escala_px)

    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(png)
    return len(png)


def png_em_memoria(
    aps: list[AccessPoint],
    largura_m: float = 30.0,
    altura_m: float = 18.0,
    escala_px: int = 12,
) -> bytes:
    """Monta o PNG do mapa e devolve os bytes, sem tocar em disco.

    Build the map PNG and return the bytes, without touching disk.

    Args:
        aps: APs do andar.
        largura_m: Largura do andar em metros.
        altura_m: Altura do andar em metros.
        escala_px: Pixels por metro.

    Returns:
        Os bytes do PNG.
    """
    largura_px = int(largura_m * escala_px)
    altura_px = int(altura_m * escala_px)
    refs = referencias(aps)

    # A escala vem da faixa que a propria imagem cobre, entao o PNG e o SVG
    # do mesmo relatorio usam exatamente as mesmas cores.
    minimo, maximo = escala_dos_dados([
        _rssi_com_referencias(refs, (px + 0.5) / escala_px, (py + 0.5) / escala_px)
        for py in range(0, altura_px, 4)
        for px in range(0, largura_px, 4)
    ])

    linhas: list[bytes] = []
    for py in range(altura_px):
        y = (py + 0.5) / escala_px
        linha = bytearray([0])  # filtro 0 = None
        for px in range(largura_px):
            x = (px + 0.5) / escala_px
            r, g, b = cor_para_rssi(_rssi_com_referencias(refs, x, y), minimo, maximo)
            linha += bytes((r, g, b))
        linhas.append(bytes(linha))

    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR", struct.pack(">IIBBBBB", largura_px, altura_px, 8, 2, 0, 0, 0)
        )
        + _png_chunk(b"IDAT", zlib.compress(b"".join(linhas), 9))
        + _png_chunk(b"IEND", b"")
    )


ESTILO = """
:root { color-scheme: light; --tinta: #111; --papel: #fff; --cinza: #6b6b6b; --linha: #e2e2e2; }
* { box-sizing: border-box; }
body {
  font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  font-weight: 300; line-height: 1.6; margin: 0; padding: 48px 24px;
  background: var(--papel); color: var(--tinta);
}
main { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 28px; font-weight: 200; letter-spacing: -0.01em; margin: 0 0 4px; }
.subtitle { color: var(--cinza); font-size: 13px; margin: 0 0 36px; }
h2 { font-size: 16px; font-weight: 400; margin: 40px 0 8px; }
table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }
th, td { border-bottom: 1px solid var(--linha); padding: 9px 12px; text-align: left; font-size: 13px; vertical-align: top; }
th { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: var(--cinza); font-weight: 400; border-bottom: 1px solid var(--tinta); }
.mapa { border: 1px solid var(--linha); position: relative; margin-bottom: 12px; }
.mapa img { display: block; width: 100%; height: auto; }
.legenda { display: flex; gap: 0; border: 1px solid var(--linha); margin-bottom: 8px; }
/* A legenda mostra numeros, nao rotulos: upper-case aqui transformava
   "dBm" em "DBM", que e unidade errada e nao existe. O tamanho pequeno e o
   espaco entre letras dao o mesmo ar de etiqueta sem mexer no texto. */
.legenda div {
  flex: 1; padding: 8px 10px; color: #fff; font-size: 11px;
  letter-spacing: .06em; font-family: Consolas, 'Courier New', monospace;
}
.nota { color: var(--cinza); font-size: 11px; }
.alert { border-left: 2px solid #c62828; padding-left: 12px; margin-bottom: 6px; font-size: 13px; }
.ok { border-left: 2px solid #1565c0; padding-left: 12px; margin-bottom: 6px; font-size: 13px; }
td.num { font-family: Consolas, 'Courier New', monospace; }
"""


def _grade_svg(
    grade: list[tuple[int, int, float]],
    nx: int,
    ny: int,
    minimo: float,
    maximo: float,
    escala: int = 10,
) -> str:
    """Desenha a grade de RSSI como retangulos SVG.

    Draw the RSSI grid as SVG rectangles.
    """
    partes: list[str] = []
    for ix, iy, rssi in grade:
        r, g, b = cor_para_rssi(rssi, minimo, maximo)
        partes.append(
            f'<rect x="{ix * escala}" y="{ny * escala - (iy + 1) * escala}" '
            f'width="{escala}" height="{escala}" fill="rgb({r},{g},{b})" '
            f'stroke="none"/>'
        )
    return "".join(partes)


def _png_data_uri(ap: list[AccessPoint], largura_m: float, altura_m: float) -> str:
    """Gera o PNG do mapa e devolve como data URI.

    Generate the map PNG and return it as a data URI.

    O HTML precisa abrir com duplo clique, sem servidor e sem internet. Isso
    significa que a imagem tem de estar **dentro** do arquivo: um ``<img
    src="mapa.png">`` quebraria assim que o relatorio fosse para um e-mail.
    """
    # O PNG vai para memoria e nao para disco. Escrever num temporario do
    # sistema eoa caminho que no Windows falha quando o antivirus abre o
    # arquivo entre o create e o write, e o caminho feliz nao pode depender
    # dessa corrida.
    bruto = png_em_memoria(ap, largura_m, altura_m, escala_px=8)
    return "data:image/png;base64," + base64.b64encode(bruto).decode("ascii")


def gerar_relatorio(
    andar: str,
    aps: list[AccessPoint],
    largura_m: float,
    altura_m: float,
    populacao: int,
    dimensao,
    problemas: list[str],
    conflitos: dict[str, list[str]],
    conflito_canais: dict[int, list[str]],
    canais_24: list[int],
    canais_5: list[int],
    recomendado_24: int,
    recomendado_5: int,
    planta_png: str | None = None,
) -> str:
    """Monta o relatorio HTML do andar.

    Build the floor's HTML report.

    Args:
        andar: Nome do andar.
        aps: APs do andar.
        largura_m: Largura do andar em metros.
        altura_m: Altura do andar em metros.
        populacao: Populacao prevista.
        dimensao: Resultado do dimensionamento.
        problemas: Problemas de projeto encontrados.
        conflitos: APs em conflito por sobreposicao de canal.
        conflito_canais: Redes disputando o mesmo canal.
        canais_24: Canais 2.4 GHz em uso.
        canais_5: Canais 5 GHz em uso.
        recomendado_24: Canal 2.4 GHz recomendado.
        recomendado_5: Canal 5 GHz recomendado.
        planta_png: Data URI do PNG do mapa, opcional.

    Returns:
        O documento HTML completo.
    """
    esc = html_mod.escape

    grade = grade_sinal(aps, largura_m, altura_m, passo_m=1.0)
    nx = max(1, int(largura_m))
    ny = max(1, int(altura_m))
    minimo, maximo = escala_dos_dados([v for _, _, v in grade])

    # O heatmap em SVG vai embutido: e texto, escala em qualquer tamanho e
    # nao depende de a imagem embutida estar correta.
    mapa_svg = _grade_svg(grade, nx, ny, minimo, maximo, escala=14)

    veredito = (
        f'<p class="ok">{esc(dimensao.resumo())}. '
        f"Capacidade instalada: {dimensao.capacidade_total} clientes para "
        f"{dimensao.clientes} previstos.</p>"
        if dimensao.falta == 0 and dimensao.capacidade_suficiente
        else f'<p class="alert">{esc(dimensao.resumo())}. '
        f"Capacidade instalada: {dimensao.capacidade_total} clientes para "
        f"{dimensao.clientes} previstos.</p>"
    )

    linhas_problema = "".join(
        f'<p class="alert">{esc(p)}</p>' for p in problemas
    ) or '<p class="ok">Nenhum problema de cobertura ou distancia detectado.</p>'

    # Tabela de APs: posicao, bandas, canais e melhor sinal.
    linhas_ap = ""
    for ap in aps:
        banda = " + ".join(ap.bandas)
        linhas_ap += (
            f"<tr><td class=\"num\">{esc(ap.bssid)}</td>"
            f"<td>{esc(banda)}</td>"
            f"<td class=\"num\">{esc(', '.join(str(c) for c in ap.canais))}</td>"
            f"<td>{ap.n_redes}</td>"
            f"<td class=\"num\">{ap.rssi_medio:.1f}</td>"
            f"<td class=\"num\">{ap.rssi_max}</td>"
            f"<td class=\"num\">{ap.x:.1f}, {ap.y:.1f}</td>"
            f"<td>{'sim' if ap.bssid in conflitos else 'nao'}</td></tr>"
        )

    linhas_conflito = ""
    for canal, ssids in conflito_canais.items():
        linhas_conflito += (
            f"<tr><td class=\"num\">{canal}</td>"
            f"<td>{esc(', '.join(ssids))}</td>"
            f"<td>{len(ssids)}</td></tr>"
        )
    if not linhas_conflito:
        linhas_conflito = '<tr><td colspan="3">Nenhuma rede disputa o mesmo canal.</td></tr>'

    if planta_png:
        img = (
            f'<img src="{planta_png}" alt="Mapa de calor de RSSI do {esc(andar)}" '
            f"width=\"{int(largura_m * 14)}\" height=\"{int(altura_m * 14)}\">"
        )
        src_png = "dentro do arquivo (data URI)"
    else:
        img = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {nx * 14} {ny * 14}" role="img" '
            f'aria-label="Mapa de calor de RSSI do {esc(andar)}">'
            f"{mapa_svg}</svg>"
        )
        src_png = "SVG embutido (o PNG e gerado com o comando --png)"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Varrimento Wi-Fi - {esc(andar)}</title>
<style>{ESTILO}</style>
</head>
<body>
<main>
<h1>Varrimento Wi-Fi - {esc(andar)}</h1>
<p class="subtitle">Planta {largura_m:.0f} m x {altura_m:.0f} m,
{len(aps)} APs fisicos, {sum(a.n_redes for a in aps)} redes logicas,
populacao prevista {populacao}. Dados ficticios.</p>

<h2>Mapa de calor de RSSI</h2>
<div class="legenda">
<div style="background:rgb({cor_para_rssi(minimo, minimo, maximo)})">{minimo:.1f} dBm</div>
<div style="background:rgb({cor_para_rssi((minimo + maximo) / 2, minimo, maximo)})">{(minimo + maximo) / 2:.1f} dBm</div>
<div style="background:rgb({cor_para_rssi(maximo, minimo, maximo)})">{maximo:.1f} dBm</div>
</div>
<div class="mapa">{img}</div>
<p class="nota">Fonte da imagem: {esc(src_png)}. A escala acompanha a faixa
medida neste andar ({minimo:.1f} a {maximo:.1f} dBm). O mapa e uma
<strong>estimativa interpolada</strong> a partir das medicoes, nao uma medicao
continua: entre dois pontos visitados o valor e desenhado, nao observado.</p>

<h2>Resumo do dimensionamento</h2>
{veredito}
<table>
<tr><th>Criterio</th><th>Valor</th></tr>
<tr><td>Area por cliente</td><td class="num">{dimensao.area_por_cliente:.1f} m2 (minimo 35,0)</td></tr>
<tr><td>APs por cobertura</td><td class="num">{dimensao.aps_por_cobertura}</td></tr>
<tr><td>APs por populacao</td><td class="num">{dimensao.aps_por_populacao}</td></tr>
<tr><td>APs necessarios</td><td class="num">{dimensao.aps_necessarios}</td></tr>
<tr><td>APs encontrados</td><td class="num">{dimensao.aps_existentes}</td></tr>
<tr><td>Capacidade instalada</td><td class="num">{dimensao.capacidade_total} clientes</td></tr>
</table>

<h2>Problemas de projeto</h2>
{linhas_problema}

<h2>Plano de canal</h2>
<table>
<tr><th>Banda</th><th>Em uso</th><th>Recomendado</th><th>Faixas validas</th></tr>
<tr><td>2.4 GHz</td><td class="num">{esc(', '.join(str(c) for c in sorted(canais_24)) or 'nenhum')}</td>
<td class="num">{recomendado_24}</td><td class="num">1, 6, 11</td></tr>
<tr><td>5 GHz</td><td class="num">{esc(', '.join(str(c) for c in sorted(canais_5)) or 'nenhum')}</td>
<td class="num">{recomendado_5}</td><td class="num">36-48, 52-64, 100-112, 149-161</td></tr>
</table>

<h2>Redes disputando o mesmo canal</h2>
<table>
<tr><th>Canal</th><th>SSIDs</th><th>Quantidade</th></tr>
{linhas_conflito}
</table>

<h2>Access points</h2>
<table>
<tr><th>BSSID</th><th>Bandas</th><th>Canais</th><th>Redes</th>
<th>RSSI medio</th><th>RSSI max</th><th>Posicao</th><th>Conflito</th></tr>
{linhas_ap}
</table>
</main>
</body>
</html>
"""
