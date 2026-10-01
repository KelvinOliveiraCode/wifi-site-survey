"""Modelo de uma medicao de Wi-Fi.

Wi-Fi measurement model. One row of a site survey is one network heard on one
channel at one physical spot, with a signal strength.

A distincao que organiza este modulo e entre **rede logica** e **AP fisico**.
Um access point quase sempre transmite varios SSIDs - rede de visitante,
corporativa, IoT,VoIP - e todos aparecem no varrimento com o mesmo BSSID. Sao
cinco redes no papel e um unico aparelho na parede. Somar capacidade por SSID
contaria o mesmo antena cinco vezes e o relatorio mandaria o cliente comprar
hardware que ele ja tem.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Medicao:
    """Uma leitura de rede em um ponto do varrimento.

    A single network reading at one survey point.

    Attributes:
        bssid: Endereco MAC do AP fisico. E o que agrupa os SSIDs.
        ssid: Nome da rede logica, o que o usuario ve.
        canal: Canal principal, em GHz.
        banda: ``2.4`` ou ``5``.
        rssi: Forca do sinal em dBm. Valores negativos; -30 e excelente,
            -67 e o limite de aceitabilidade em projeto.
        x: Coordenada horizontal do ponto medido, em metros.
        y: Coordenada vertical do ponto medido, em metros.
    """

    bssid: str
    ssid: str
    canal: int
    banda: str
    rssi: int
    x: float
    y: float
    largura_canal: int = 20

    @property
    def chave_ap(self) -> str:
        """Identidade do AP fisico, independente do SSID.

        The physical AP identity, regardless of SSID.
        """
        return self.bssid


@dataclass(frozen=True)
class Rede:
    """Uma rede logica, agregada sobre todas as suas medicoes.

    A logical network, aggregated over every measurement of it.
    """

    ssid: str
    bssid: str
    canal: int
    banda: str
    largura_canal: int
    pontos: tuple[Medicao, ...]

    @property
    def rssi_medio(self) -> float:
        """RSSI medio das medicoes.

        Mean RSSI across measurements.
        """
        if not self.pontos:
            return 0.0
        return sum(p.rssi for p in self.pontos) / len(self.pontos)

    @property
    def rssi_max(self) -> int:
        """Melhor RSSI medido.

        Strongest RSSI measured.
        """
        return max((p.rssi for p in self.pontos), default=0)

    @property
    def rssi_min(self) -> int:
        """Pior RSSI medido.

        Weakest RSSI measured.
        """
        return min((p.rssi for p in self.pontos), default=0)

    @property
    def posicao(self) -> tuple[float, float]:
        """Posicao estimada do AP, pela potencia recebida em cada ponto.

        Estimated AP position, by received power at each point.

        O ponto medio simples erra: o varrimento so conhece os pontos onde
        alguem andou, e eles nao ficam em torno do AP de forma uniforme. A
        media ponderada pela potencia recebida (10^(RSSI/10), a lei de
        Friis) puxa a posicao para perto do AP, porque o sinal mais forte foi
        medido mais perto dele.

        O detalhe que custa um bug: o peso tem de ser a **potencia**, nao o
        valor absoluto do RSSI. Como o RSSI ja e negativo, ``abs(rssi)`` da
        peso maior para a leitura **mais fraca**, que e a mais distante - e a
        media cai no centro da planta, onde ficam os quatro cantos longe. Todos
        os AP pareciam estar no mesmo ponto.

        Args:
            Nenhum.

        Returns:
            Coordenada ``(x, y)`` estimada, arredondada a 2 casas.
        """
        if not self.pontos:
            return (0.0, 0.0)
        pesos = [10 ** (p.rssi / 10.0) for p in self.pontos]
        total = sum(pesos) or 1.0
        px = sum(p.x * w for p, w in zip(self.pontos, pesos)) / total
        py = sum(p.y * w for p, w in zip(self.pontos, pesos)) / total
        return (round(px, 2), round(py, 2))

    @property
    def canais_ocupados(self) -> tuple[int, ...]:
        """Canais distintos onde a rede foi ouvida.

        Distinct channels where the network was heard.
        """
        return tuple(sorted({p.canal for p in self.pontos}))

    def cobre_todo(self, largura: float, altura: float) -> bool:
        """Diz se algum ponto medido esta dentro da area.

        Whether any measured point falls inside the area.

        Args:
            largura: Largura da area em metros.
            altura: Altura da area em metros.

        Returns:
            Verdadeiro se ao menos um ponto estiver dentro dos limites.
        """
        return any(0 <= p.x <= largura and 0 <= p.y <= altura for p in self.pontos)


@dataclass(frozen=True)
class AccessPoint:
    """Um AP fisico e as redes logicas que ele transmite.

    A physical AP and the logical networks it broadcasts.

    Agrupar por BSSID e o que impede o relatorio de contar cinco antenas onde
    existe uma. Varios SSIDs no mesmo BSSID compartilham canal, consomem o
    mesmo espectro e ocupam o mesmo ponto da planta.
    """

    bssid: str
    bandas: tuple[str, ...]
    x: float
    y: float
    redes: tuple[Rede, ...]

    @property
    def canais(self) -> tuple[int, ...]:
        """Canais usados pelo AP, em qualquer banda.

        Channels used by the AP, across all bands.
        """
        return tuple(sorted({r.canal for r in self.redes}))

    @property
    def bandas_2g(self) -> tuple[str, ...]:
        """Redes em 2.4 GHz.

        Networks in 2.4 GHz.
        """
        return tuple(b for b in self.bandas if b == "2.4")

    @property
    def bandas_5g(self) -> tuple[str, ...]:
        """Redes em 5 GHz.

        Networks in 5 GHz.
        """
        return tuple(b for b in self.bandas if b == "5")

    @property
    def rssi_medio(self) -> float:
        """RSSI medio de todas as redes do AP.

        Mean RSSI across every network the AP broadcasts.
        """
        if not self.redes:
            return 0.0
        return sum(r.rssi_medio for r in self.redes) / len(self.redes)

    @property
    def rssi_max(self) -> int:
        """Melhor RSSI entre as redes do AP.

        Strongest RSSI across the AP's networks.
        """
        return max((r.rssi_max for r in self.redes), default=0)

    @property
    def n_redes(self) -> int:
        """Quantas redes logicas o AP transmite.

        How many logical networks the AP broadcasts.
        """
        return len(self.redes)


def assinatura_do_equipamento(bssid: str) -> str:
    """Os cinco primeiros octetos do MAC, que identificam o aparelho.

    The first five MAC octets, which identify the device.

    Um AP dual-band tem **um MAC por radio**: o 2.4 GHz e o 5 GHz sao radios
    diferentes, entao aparecem com BSSIDs diferentes, mesmo sendo o mesmo
    aparelho na mesma parede. Os cinco primeiros octetos sao iguais; so o
    ultimo muda. Sem essa distincao, um AP dual-band vira dois APs no
    relatorio - e o dimensionamento conta capacidade dobrada e ponto de
    cobertura repetido.

    Args:
        bssid: Endereco MAC do radio.

    Returns:
        A assinatura do equipamento, em minusculas. Um BSSID com menos de seis
        octetos e devolvido como veio, para nao perder informacao.
    """
    partes = [p for p in bssid.lower().replace("-", ":").split(":") if p]
    if len(partes) < 6:
        return bssid.lower()
    return ":".join(partes[:5])


def agrupar_aps(redes: list[Rede], por_radio: bool = False) -> list[AccessPoint]:
    """Agrupa redes logicas em APs fisicos.

    Group logical networks into physical APs.

    Args:
        redes: Redes logicas agregadas.
        por_radio: Quando verdadeiro, agrupa por BSSID exato e cada radio vira
            um AP. O padrao e ``False``, que une os radios do mesmo aparelho.

    Returns:
        APs fisicos, ordenados por BSSID para saida deterministica.
    """
    por_chave: dict[str, list[Rede]] = {}
    for rede in redes:
        chave = rede.bssid if por_radio else assinatura_do_equipamento(rede.bssid)
        por_chave.setdefault(chave, []).append(rede)

    aps: list[AccessPoint] = []
    for chave, grupo in por_chave.items():
        xs = [r.posicao[0] for r in grupo]
        ys = [r.posicao[1] for r in grupo]
        aps.append(
            AccessPoint(
                bssid=chave,
                bandas=tuple(sorted({r.banda for r in grupo})),
                x=round(sum(xs) / len(xs), 2),
                y=round(sum(ys) / len(ys), 2),
                redes=tuple(sorted(grupo, key=lambda r: (r.banda, r.ssid, r.bssid))),
            )
        )
    return sorted(aps, key=lambda a: a.bssid)
