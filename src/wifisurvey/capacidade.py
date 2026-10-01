"""Capacidade por access point e dimensionamento por andar.

Capacity per access point and per-floor sizing. How many clients one AP holds,
and how many APs a floor needs to cover its area and its expected population.

Os numeros de capacidade sao configuraveis em ``dados/capacidade.yaml`` porque
nao sao lei da fabricante: mudam com a banda, a largura de canal, o numero de
antenas e o trafego. O que esta no repositorio e um orcamento de referencia,
documentado, e nao uma promessa.
"""

from __future__ import annotations

import math
from pathlib import Path

from .plano import AccessPoint


# Orcamento de referencia quando nao ha arquivo de configuracao.
# 2.4 GHz carrega menos cliente por AP: a banda tem menos espectro e mais
# interferencia de vizinho. 5 GHz dobra, e quadruplica ao quadruplicar a
# largura de canal, porque ai o canal passou a ser o gargalo e nao o radio.
CAPACIDADE_PADRAO = {
    "2.4": {"20": 15, "40": 10},
    "5": {"20": 25, "40": 50, "80": 100, "160": 200},
}

# Criterios de projeto por andar, tambem configuraveis.
CRITERIOS_PADRAO = {
    "area_por_cliente_m2": 35.0,
    "distancia_max_entre_aps_m": 15.0,
    "rssi_minimo_dbm": -67,
    "aps_por_1000_m2": 4,
}

# Fracao da distancia tipica abaixo da qual um par de APs conta como
# agglomerado. Configuravel junto com os criterios, porque o que e aceitavel
# depende do tipo de ambiente.
FRACAO_DE_AGLOMERADO = 0.35


class ParametrosInvalidos(ValueError):
    """Um parametro de projeto esta fora do intervalo fazivel."""

    def __init__(self, campo: str, valor: object) -> None:
        super().__init__(f"parametro invalido {campo}={valor!r}")
        self.campo = campo
        self.valor = valor


class Parametros:
    """Parametros de capacidade e projeto, validados na carga.

    Capacity and design parameters, validated on load.

    A validacao aqui nao e vaidade. Capacidade zero, area por cliente negativa
    ou RSSI minimo positivo sao exatamente os valores que fariam o relatorio
    afirmar que um AP suporta um numero impossivel, ou que -40 dBm esta fraco.
    Recusar o arquivo e melhor do que emitir um relatorio bonito e falso.
    """

    def __init__(
        self,
        capacidade: dict[str, dict[str, int]] | None = None,
        criterios: dict[str, float] | None = None,
    ) -> None:
        cap = capacidade if capacidade is not None else CAPACIDADE_PADRAO
        crit = {**CRITERIOS_PADRAO, **(criterios or {})}

        for banda, larguras in cap.items():
            if banda not in ("2.4", "5"):
                raise ParametrosInvalidos("banda", banda)
            for largura, n in larguras.items():
                if int(largura) not in (20, 40, 80, 160):
                    raise ParametrosInvalidos("largura", largura)
                if n <= 0:
                    raise ParametrosInvalidos("capacidade", n)

        if crit["area_por_cliente_m2"] <= 0:
            raise ParametrosInvalidos("area_por_cliente_m2", crit["area_por_cliente_m2"])
        if crit["distancia_max_entre_aps_m"] <= 0:
            raise ParametrosInvalidos(
                "distancia_max_entre_aps_m", crit["distancia_max_entre_aps_m"]
            )
        if not -100 <= crit["rssi_minimo_dbm"] <= -30:
            raise ParametrosInvalidos("rssi_minimo_dbm", crit["rssi_minimo_dbm"])
        if crit["aps_por_1000_m2"] <= 0:
            raise ParametrosInvalidos("aps_por_1000_m2", crit["aps_por_1000_m2"])

        self.capacidade = cap
        self.criterios = crit

    @classmethod
    def carregar(cls, caminho: str | Path) -> "Parametros":
        """Le parametros de um YAML.

        Load parameters from a YAML file.

        Args:
            caminho: Caminho do arquivo.

        Returns:
            Os parametros validados.

        Raises:
            ParametrosInvalidos: Se algum valor estiver fora do intervalo.
        """
        import yaml

        bruto = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
        return cls(capacidade=bruto.get("capacidade"), criterios=bruto.get("criterios"))

    def clientes_por_ap(self, banda: str, largura: int = 20) -> int:
        """Quantos clientes um AP suporta naquela banda e largura.

        How many clients one AP supports at that band and width.

        Args:
            banda: ``2.4`` ou ``5``.
            largura: Largura de canal em MHz.

        Returns:
            O numero de clientes simultaneos.

        Raises:
            ParametrosInvalidos: Se a combinacao banda/largura nao existir.
        """
        por_largura = self.capacidade.get(banda)
        if por_largura is None:
            raise ParametrosInvalidos("banda", banda)
        clientes = por_largura.get(str(largura))
        if clientes is None:
            raise ParametrosInvalidos("largura", largura)
        return clientes

    @property
    def rssi_minimo(self) -> float:
        """RSSI minimo aceitavel, em dBm.

        Minimum acceptable RSSI, in dBm.
        """
        return float(self.criterios["rssi_minimo_dbm"])


def capacidade_do_ap(ap: AccessPoint, params: Parametros) -> int:
    """Soma a capacidade das bandas que o AP transmite.

    Sum the capacity of the bands the AP broadcasts.

    Um AP dual-band que transmite em 2.4 e em 5 carrega os dois.Orcamento e a
    soma de **banda e largura distintas**, nao a soma das redes: cinco SSIDs no
    mesmo BSSID continuam sendo uma antena. Contar por rede daria a um AP
    dual-band cinco vezes a capacidade dele.

    Args:
        ap: Access point fisico.
        params: Parametros de capacidade.

    Returns:
        Total de clientes simultaneos suportados.
    """
    total = 0
    vistas: set[tuple[str, int]] = set()

    for rede in ap.redes:
        chave = (rede.banda, rede.largura_canal)
        if chave in vistas:
            continue
        vistas.add(chave)
        total += params.clientes_por_ap(rede.banda, rede.largura_canal)

    return total


class Dimensionamento:
    """Resultado do dimensionamento de um andar.

    One floor's sizing result.

    Attributes:
        area_m2: Area do andar.
        clientes: Populacao prevista.
        aps_necessarios: Quantos APs o criterio exige.
        aps_existentes: Quantos APs o varrimento encontrou.
        aps_por_cobertura: Quantos APs a area exige.
        aps_por_populacao: Quantos APs a populacao exige.
        capacidade_total: Clientes que os APs existentes suportam.
    """

    def __init__(
        self,
        area_m2: float,
        clientes: int,
        aps_necessarios: int,
        aps_existentes: int,
        aps_por_cobertura: int,
        aps_por_populacao: int,
        capacidade_total: int,
    ) -> None:
        self.area_m2 = area_m2
        self.clientes = clientes
        self.aps_necessarios = aps_necessarios
        self.aps_existentes = aps_existentes
        self.aps_por_cobertura = aps_por_cobertura
        self.aps_por_populacao = aps_por_populacao
        self.capacidade_total = capacidade_total

    @property
    def falta(self) -> int:
        """Quantos APs faltam, zero quando ha cobertura.

        How many APs are missing, zero when covered.
        """
        return max(0, self.aps_necessarios - self.aps_existentes)

    @property
    def excedente(self) -> int:
        """Quantos APs sobram, zero quando a area esta apenas coberta.

        How many APs are surplus, zero when the area is just covered.
        """
        return max(0, self.aps_existentes - self.aps_necessarios)

    @property
    def capacidade_suficiente(self) -> bool:
        """A capacidade dos APs existentes cobre a populacao?

        Whether the existing AP capacity covers the population.
        """
        return self.capacidade_total >= self.clientes

    @property
    def area_por_cliente(self) -> float:
        """Area disponivel por cliente, em m2.

        Available area per client, in m2.
        """
        if self.clientes <= 0:
            return 0.0
        return round(self.area_m2 / self.clientes, 2)

    def resumo(self) -> str:
        """Uma frase explicando o veredito do dimensionamento.

        One sentence stating the sizing verdict.
        """
        if self.falta:
            return (
                f"faltam {self.falta} AP(s): {self.aps_existentes} instalado(s) "
                f"para {self.aps_necessarios} necessario(s)"
            )
        if self.excedente:
            return (
                f"{self.excedente} AP(s) acima do necessario: "
                f"{self.aps_existentes} instalado(s) para "
                f"{self.aps_necessarios} necessario(s)"
            )
        return f"dimensionamento correto: {self.aps_existentes} AP(s)"

    def para_dict(self) -> dict[str, object]:
        """Serializa o resultado.

        Serialize the result.
        """
        return {
            "area_m2": self.area_m2,
            "clientes": self.clientes,
            "aps_necessarios": self.aps_necessarios,
            "aps_existentes": self.aps_existentes,
            "aps_por_cobertura": self.aps_por_cobertura,
            "aps_por_populacao": self.aps_por_populacao,
            "capacidade_total": self.capacidade_total,
            "falta": self.falta,
            "excedente": self.excedente,
            "capacidade_suficiente": self.capacidade_suficiente,
        }


def dimensionar(
    aps: list[AccessPoint],
    area_m2: float,
    clientes: int,
    params: Parametros,
) -> Dimensionamento:
    """Calcula quantos APs o andar precisa, com tres criterios independentes.

    Compute how many APs a floor needs, using three independent criteria.

    Os tres medem limites diferentes, e por isso nenhum decide sozinho:

    - **cobertura** - quantos APs a area exige, pela densidade de projeto de
      4 APs por 1000 m2. Um andar de 540 m2 pede 3.
    - **populacao** - quantos APs a populacao exige, dividindo pela capacidade
      de um AP em 5 GHz a 80 MHz (100 clientes). Noventa pessoas pedem 1.
    - **ocupacao** - o criterio de area por cliente, que e o unico que
     cresce. Com 35 m2 por cliente, 540 m2 comportam 15 pessoas confortavelmente.
      Noventa pessoas num andar que comporta quinze sao seis rodadas.

    O criterio de ocupacao entra **somando**, nao multiplicando. Multiplicar
    cobertura por rodadas foi a primeira versao, e ela e errada por um motivo
    que so aparece quando os numeros ficam grandes: `por_cobertura *
    rodadas` trata "seis rodadas de gente" como "seis vezes mais AP de
    cobertura", o que nao tem lectura fisica. Um andar de 100 m2 com 200
    pessoas dava 70 APs - e a area nem e o problema, o problema sao as 200
    pessoas. O resultado correto e `por_cobertura + rodadas - 1`: a cobertura
    de base, mais uma unidade de capacidade para cada rodada alem da primeira.

    Com essa soma, 540 m2 e 90 pessoas dao 3 + 6 - 1 = 8 APs. E um numero que
    alguem consegue defender em reuniao: tres para cobrir o espaco, cinco para
    dar conta da gente.

    Args:
        aps: APs encontrados no varrimento.
        area_m2: Area do andar em metros quadrados.
        clientes: Populacao prevista.
        params: Parametros de projeto.

    Returns:
        O resultado do dimensionamento.

    Raises:
        ParametrosInvalidos: Se a area for nao positiva.
    """
    if area_m2 <= 0:
        raise ParametrosInvalidos("area_m2", area_m2)
    if clientes < 0:
        raise ParametrosInvalidos("clientes", clientes)

    por_cobertura = max(1, math.ceil(area_m2 / 1000.0 * params.criterios["aps_por_1000_m2"]))

    capacidade_unitaria = params.clientes_por_ap("5", 80)
    por_populacao = max(1, math.ceil(clientes / capacidade_unitaria)) if clientes else 1

    capacidade_espacial = area_m2 / params.criterios["area_por_cliente_m2"]
    rodadas = max(1, math.ceil(clientes / capacidade_espacial)) if capacidade_espacial > 0 else 1

    # A cobertura de base, mais uma unidade para cada rodada alem da primeira.
    # Subtrair 1 evita contar a primeira rodada duas vezes: com uma unica
    # rodada, o resultado e so a cobertura.
    por_ocupacao = por_cobertura + rodadas - 1

    necessarios = max(por_cobertura, por_populacao, por_ocupacao)

    return Dimensionamento(
        area_m2=area_m2,
        clientes=clientes,
        aps_necessarios=necessarios,
        aps_existentes=len(aps),
        aps_por_cobertura=por_cobertura,
        aps_por_populacao=por_populacao,
        capacidade_total=sum(capacidade_do_ap(ap, params) for ap in aps),
    )


def distancia_entre_aps(aps: list[AccessPoint]) -> float:
    """A menor distancia entre dois APs em posicoes distintas.

    The smallest distance between two APs at distinct positions.

    Dois APs muito perto nao e excesso de capacidade: e interferencia, porque
    o cliente nao consegue escolher qual sinal seguir. APs na mesma posicao nao
    contam como par - e o caso normal de um AP dual-band, que e um aparelho so.

    Args:
        aps: APs do andar.

    Returns:
        A menor distancia em metros, ou 0.0 se houver menos de dois APs em
        posicoes distintas.
    """
    if len(aps) < 2:
        return 0.0

    menor = float("inf")
    for i, a in enumerate(aps):
        for b in aps[i + 1:]:
            if (a.x, a.y) == (b.x, b.y):
                continue
            menor = min(menor, ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5)

    return round(menor, 2) if menor != float("inf") else 0.0


def espacamento_aps(aps: list[AccessPoint]) -> tuple[float, float]:
    """A menor e a distancia tipica ate o vizinho mais proximo.

    The smallest and the typical distance to the nearest neighbour.

    A estatistica e a distancia de cada AP ate o seu vizinho mais proximo, e
    nao a distancia entre todos os pares. A distincao importa: num
    Em uma distribuicao qualquer, a menor distancia entre *algum par* e quase
    sempre pequena - com quinze APs em 540 m2 e matematicamente obrigatorio haver
    dois deles perto, e a razao menor/mediana fica baixa mesmo com a planta
    perfeitamente regular. Ate o alerta viraria ruido.

    Olhando o vizinho mais proximo de cada AP, a comparacao fica bem
    condicionada: em uma planta uniforme todas as distancias se parecem, e
    so dispara quando existe mesmo um aglomerado - dois aparelhos colados
    num canto enquanto o resto da planta esta regular.

    Args:
        aps: APs do andar.

    Returns:
        Tupla ``(menor_vizinho_proximo, mediana_dos_vizinhos_proximos)``, em
        metros. Com menos de dois APs em posicoes distintas, devolve
        ``(0.0, 0.0)``.
    """
    if len(aps) < 2:
        return (0.0, 0.0)

    vizinhos: list[float] = []
    for i, a in enumerate(aps):
        mais_proximo = None
        for j, b in enumerate(aps):
            if i == j or (a.x, a.y) == (b.x, b.y):
                continue
            d = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
            if mais_proximo is None or d < mais_proximo:
                mais_proximo = d
        if mais_proximo is not None:
            vizinhos.append(mais_proximo)

    if not vizinhos:
        return (0.0, 0.0)

    ordenadas = sorted(vizinhos)
    meio = len(ordenadas) // 2
    mediana = (
        ordenadas[meio]
        if len(ordenadas) % 2
        else (ordenadas[meio - 1] + ordenadas[meio]) / 2
    )
    return (round(ordenadas[0], 2), round(mediana, 2))


def verifica_projeto(aps: list[AccessPoint], params: Parametros) -> list[str]:
    """Aponta os problemas de projeto do andar.

    Point out the floor's design problems.

    O alerta de distancia **nao** compara a menor separacao com o criterio
    de projeto de 15 m. Um andar com quinze APs em 540 m2 tem,
    obrigatoriamente, APs a menos de 15 m uns dos outros: quinze APs com
    15 m de separacao ocupariam 3375 m2. Um alerta assim dispararia em todo
    andar bem povoado, e um alerta que dispara sempre nao e lido por ninguem.

    O que separa um aglomerado de um andar bem projetado e a
    **irregularidade**: se um AP esta muito mais perto do seu vizinho do que
    os outros APs estao dos seus, alguem prendeu dois aparelhos no mesmo
    ponto - e ai sobra sinal ali e falta em volta.
    Args:
        aps: APs do andar.
        params: Parametros de projeto.

    Returns:
        Lista de problemas em texto, vazia se o projeto estiver coerente.
    """
    problemas: list[str] = []

    if not aps:
        return ["nenhum access point no andar"]

    minimo = params.rssi_minimo
    fracos = [ap for ap in aps if ap.rssi_max < minimo]
    if fracos:
        problemas.append(
            f"{len(fracos)} AP(s) com sinal maximo abaixo de {minimo:.0f} dBm: "
            + ", ".join(sorted(a.bssid for a in fracos))
        )

    menor, tipica = espacamento_aps(aps)
    if tipica > 0 and menor < tipica * FRACAO_DE_AGLOMERADO:
        problemas.append(
            f"aglomerado: APs a {menor:.1f} m uns dos outros, contra uma "
            f"distancia tipica de {tipica:.1f} m. Dois aparelhos no mesmo ponto "
            "somam sinal em vez de somar cobertura"
        )

    return problemas
