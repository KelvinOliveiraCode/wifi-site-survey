"""Canais validos e deteccao de sobreposicao de canal.

Valid channels and channel-overlap detection. A regra de separacao de canal e
a base do projeto de Wi-Fi: dois emissores no mesmo canal se somam e nao se
somam em canal - o resultado e ruido, nao capacidade.

Duas bandas, duas situacoes diferentes:

- **2.4 GHz** tem apenas tres canais nao sobrepostos (1, 6 e 11). Cada canal
  ocupa cerca de 22 MHz e o espectro tem cerca de 83 MHz utilizaveis, entao a
  matematica deixa tres. Usar canal 3 nao e "um canal um pouco diferente do 1":
  e sobreposicao parcial, que derruba o SNR dos dois.
- **5 GHz** tem muito mais canais e canais de 20 MHz, 40, 80 e 160 MHz. Blocos
  de quatro canais de 20 MHz nao se sobrepoem entre si; um canal de 80 MHz usa
  quatro blocos, entao ocupa quatro vezes mais espaco.
"""

from __future__ import annotations

from .plano import AccessPoint, Rede, assinatura_do_equipamento


# Os tres canais 2.4 GHz validos para projeto. Nao e a lista completa do
# padrao: sao os tres que nao se sobrepoem, e so eles funcionam em uso real.
CANAIS_2G = (1, 6, 11)

# Faixas 5 GHz utilisaveis em dentro/fora do pais. Cada faixa e um bloco de
# quatro canais de 20 MHz que nao se sobrepoem aos vizinhos. A lacuna entre
# 64 e 100 e DFS: emissor so pode ali depois de detectar radar, e um projeto
# que depende disso entrega um equipamento que muda de canal sozinho.
FAIXAS_5G = ((36, 48), (52, 64), (100, 112), (149, 161))

# Larguras de canal aceitas, em MHz. 160 so existe em 5 GHz.
LARGURAS_ACEITAS = (20, 40, 80, 160)

# Quanto cada canal de 20 MHz ocupa, em MHz. 2.4 GHz tem espacamento de 5 MHz
# entre centros e usa 22 MHz util; 5 GHz tem espacamento de 20 MHz e usa 20.
LARGURA_UTIL_2G = 22
LARGURA_UTIL_5G = 20

# Em 5 GHz os canais sao numerados de 4 em 4 dentro do bloco, entao um avanco
# de um bloco de 20 MHz vale 4 no numero do canal.
PASSO_5G = 4

FAIXA_2G_HZ = (2401, 2472)
FAIXA_5G_HZ = (5150, 5875)


class CanalInvalido(ValueError):
    """O canal nao existe na banda informada."""

    def __init__(self, canal: int, banda: str) -> None:
        super().__init__(
            f"canal {canal} invalido em {banda} GHz"
        )
        self.canal = canal
        self.banda = banda


def canais_validos(banda: str) -> tuple[int, ...]:
    """Lista os canais validos de uma banda.

    List the valid channels of a band.

    Args:
        banda: ``2.4`` ou ``5``.

    Returns:
        Os canais aceitos, em ordem crescente.

    Raises:
        ValueError: Se a banda nao for ``2.4`` nem ``5``.
    """
    if banda == "2.4":
        return CANAIS_2G
    if banda == "5":
        return canais_5g_utilizaveis()
    raise ValueError(f"banda desconhecida: {banda!r} (use '2.4' ou '5')")


def canais_5g_utilizaveis() -> tuple[int, ...]:
    """Todos os canais de 20 MHz das faixas 5 GHz.

    All 20 MHz channels of the 5 GHz bands.
    """
    canais: list[int] = []
    for inicio, fim in FAIXAS_5G:
        canais.extend(range(inicio, fim + 1, 4))
    return tuple(canais)


def canal_valido(canal: int, banda: str) -> bool:
    """Diz se um canal de 20 MHz e valido na banda.

    Whether a 20 MHz channel is valid in the band.
    """
    try:
        return canal in canais_validos(banda)
    except ValueError:
        return False


def faixa_ocupada(canal: int, largura: int, banda: str) -> tuple[int, int]:
    """Calcula os canais que um emissor ocupa, do mais baixo ao mais alto.

    Compute which channels a transmitter occupies, lowest to highest.

    A faixa e **ancorada no canal primario**, e nao centrada nele, porque e
    assim que a especificacao escreve os canais.

    Em 5 GHz os canais sao numerados de 4 em 4 dentro de cada bloco, entao a
    largura avanca em passos de 4: um canal de 40 MHz com primario 56 ocupa
    56 **e 60**, e um de 80 MHz com primario 36 ocupa 36, 40, 44 e 48. Usar
    passos de 1 - a conta ingenua de "80 MHz sao quatro canais de 20" - daria
    36 ate 39, canais que nem existem na grade, e nenhum emissor largo jamais
    colidiria com o vizinho.

    Em 2.4 GHz o espacamento e de 5 MHz, entao um canal de 40 MHz com primario
    1 ocupa os canais 1 a 4. E o de 20 MHz ocupa so o primario: os 22 MHz uteis
    nao chegam a cobrir o centro do canal vizinho.

    Dois bugs efetivo a primeira versao: passos de 1 em 5 GHz (que nunca
    acusava sobreposicao) e ``(20 - 22) // 5`` em 2.4 GHz, que com divisao
    inteira arredondando para baixo dava -1, e a faixa do canal 1 voltava
    ``(1, 0)`` - um intervalo invertido, que nenhuma sobreposicao casava.

    Args:
        canal: Canal principal.
        largura: Largura em MHz (20, 40, 80 ou 160).
        banda: ``2.4`` ou ``5``.

    Returns:
        Tupla ``(canal_mais_baixo, canal_mais_alto)``, em numeros de canal.

    Raises:
        CanalInvalido: Se a largura nao for aceita ou nao existir na banda.
    """
    if largura not in LARGURAS_ACEITAS:
        raise CanalInvalido(canal, f"{banda} GHz largura {largura} MHz")

    if banda == "2.4":
        if largura not in (20, 40):
            raise CanalInvalido(canal, f"2.4 GHz largura {largura} MHz")
        return (canal, canal + max(0, largura // 10 - 1))

    if banda != "5":
        raise CanalInvalido(canal, f"banda desconhecida: {banda!r}")

    # Um passo de 4 em numeros de canal equivale a um bloco de 20 MHz.
    return (canal, canal + PASSO_5G * (largura // LARGURA_UTIL_5G - 1))


def sobrepoe(
    canal_a: int,
    largura_a: int,
    banda_a: str,
    canal_b: int,
    largura_b: int,
    banda_b: str,
) -> bool:
    """Diz se duas emissoes ocupam o mesmo espectro.

    Whether two transmissions occupy the same spectrum.

    Canais de bandas diferentes nunca se sobrepoem: 36 em 5 GHz e 6 em 2.4 GHz
    estao em frequencias diferentes, mesmo que o numero seja parecido. Por isso
    a comparacao so acontece dentro da mesma banda.

    Args:
        canal_a: Canal principal da primeira emissao.
        largura_a: Largura da primeira emissao em MHz.
        banda_a: Banda da primeira emissao.
        canal_b: Canal principal da segunda emissao.
        largura_b: Largura da segunda emissao em MHz.
        banda_b: Banda da segunda emissao.

    Returns:
        Verdadeiro se as faixas ocupadas se intersectarem.
    """
    if banda_a != banda_b:
        return False

    inicio_a, fim_a = faixa_ocupada(canal_a, largura_a, banda_a)
    inicio_b, fim_b = faixa_ocupada(canal_b, largura_b, banda_b)
    return inicio_a <= fim_b and inicio_b <= fim_a


def nivel_interferencia(rede: Rede, vizinhas: list[Rede]) -> list[Rede]:
    """Lista as redes que interferem na rede dada.

    List the networks that interfere with the given one.

    Args:
        rede: Rede avaliada.
        vizinhas: Redes candidatas a interferir.

    Returns:
        As redes cuja faixa se sobrepoe a da rede avaliada, ordenadas por BSSID.
    """
    batidas = [
        v
        for v in vizinhas
        if v.bssid != rede.bssid
        and sobrepoe(
            rede.canal, rede.largura_canal, rede.banda,
            v.canal, v.largura_canal, v.banda,
        )
    ]
    return sorted(batidas, key=lambda v: (v.banda, v.canal, v.bssid))


def indices_de_conflito(aps: list[AccessPoint]) -> dict[str, list[str]]:
    """Aponta os APs que disputam o mesmo espectro entre si.

    Point out the APs that contend for the same spectrum.

    A comparacao e feita entre **todos** os APs do andar, nao so dentro de cada
    um. Interferencia entre radios do mesmo aparelho nao existe - eles
    transmitem em bandas diferentes por construcao, e o radio sabe disso. O
    que atrapalha o cliente e o radio do vizinho. A primeira versao comparava
    cada rede apenas com as demais redes do seu proprio AP, e por isso nunca
    acusava conflito nenhum: o conjunto de dois APs devolvia dicionario vazio
    mesmo com um deles em canal de 80 MHz invadindo o canal do outro.

    Args:
        aps: APs do andar.

    Returns:
        Dicionario ``assinatura_do_ap -> lista de assinaturas em conflito``.
    """
    todas = [r for ap in aps for r in ap.redes]
    conflitos: dict[str, set[str]] = {}

    for ap in aps:
        batidas = [
            r
            for rede in ap.redes
            for r in nivel_interferencia(rede, todas)
            if assinatura_do_equipamento(r.bssid) != ap.bssid
        ]
        if batidas:
            conflitos[ap.bssid] = {assinatura_do_equipamento(r.bssid) for r in batidas}

    return {k: sorted(v) for k, v in sorted(conflitos.items())}


def canal_recomendado(
    banda: str,
   largura: int,
    ocupados: list[int],
) -> int:
    """Escolhe o canal menos perturbado para um novo AP.

    Pick the least-perturbed channel for a new AP.

    Escolhe o canal cuja faixa ocupada tem menos vizinho. Empate resolve no
    canal mais baixo, para o resultado ser estavel entre execucoes.

    Args:
        banda: ``2.4`` ou ``5``.
        largura: Largura do canal novo em MHz.
        ocupados: Canais ja em uso no andar.

    Returns:
        O canal recomendado.

    Raises:
        CanalInvalido: Se a largura nao for aceita na banda.
    """
    candidatos = canais_validos(banda)

    # A largura e validada uma vez, aqui. Se a validacao ficasse dentro do
    # laco, um canal invalido seria apenas "pulado" e a funcao devolveria o
    # primeiro canal da lista como se nada estivesse errado - o chamador
    # receberia uma recomendacao para 80 MHz em 2.4 GHz, que nao existe.
    faixa_ocupada(candidatos[0], largura, banda)

    melhor = candidatos[0]
    menor_perturbacao: int | None = None

    for canal in candidatos:
        inicio, fim = faixa_ocupada(canal, largura, banda)

        perturbacao = 0
        for usado in ocupados:
            try:
                inicio_u, fim_u = faixa_ocupada(usado, 20, banda)
            except CanalInvalido:
                # Dado sujo: um canal de outra banda na lista. Ignorar em vez
                # de quebrar e o comportamento certo para um relatorio.
                continue
            if inicio <= fim_u and inicio_u <= fim:
                perturbacao += 1

        if menor_perturbacao is None or perturbacao < menor_perturbacao:
            menor_perturbacao = perturbacao
            melhor = canal

    return melhor


def conflito_de_canal(redes: list[Rede]) -> dict[int, list[str]]:
    """Agrupa as redes que disputam o mesmo canal.

    Group networks contending for the same channel.

    Cada SSID entra uma vez so na exibicao. Numa instalacao de verdade o mesmo
    SSID aparece em varios BSSIDs, e o relatorio que contasse cada ocorrencia
    mostraria "CORP-TI" tres vezes na mesma linha do canal.

    A contagem, essa sim, e por **BSSID**: tres APs transmitindo "CORP-TI" no
    canal 36 sao tres radios disputando o mesmo espectro, mesmo que o nome seja
    um so. Agrupar por SSID faria o canal parecer limpo - que e exatamente o
    caso em que o alerta precisa disparar.

    Args:
        redes: Redes do andar.

    Returns:
        Dicionario ``canal -> lista de SSIDs unicos`` somente para canais com
        mais de um BSSID.
    """
    por_canal: dict[int, dict[str, str]] = {}
    for rede in redes:
        por_canal.setdefault(rede.canal, {}).setdefault(rede.bssid, rede.ssid)

    return dict(
        sorted(
            (canal, sorted(set(ssids.values())))
            for canal, ssids in por_canal.items()
            if len(ssids) > 1
        )
    )
