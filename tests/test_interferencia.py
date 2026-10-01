"""Testes de canal e sobreposicao.

Channel and overlap tests.

O teste mais importante deste arquivo nao verifica que dois canais se
sobrepoem - verifica que dois canais **nao** se sobrepoem quando nao devem.
Um detector de interferencia que accuse tudo parece cheio de problemas e nao
encontra nenhum: e o tipo de ferramenta que o cliente desliga na primeira
semana.
"""

from __future__ import annotations

import pytest

from wifisurvey.interferencia import (
    CANAIS_2G,
    FAIXAS_5G,
    CanalInvalido,
    canal_recomendado,
    canais_5g_utilizaveis,
    canais_validos,
    canal_valido,
    conflito_de_canal,
    faixa_ocupada,
    indices_de_conflito,
    nivel_interferencia,
    sobrepoe,
)
from wifisurvey.plano import Medicao, Rede, agrupar_aps


def rede(
    bssid: str = "02:00:00:00:01:00",
    ssid: str = "CORP",
    canal: int = 36,
    banda: str = "5",
    largura: int = 20,
) -> Rede:
    """Fabrica uma Rede com uma unica medicao.

    Build a Rede with a single measurement.
    """
    medicao = Medicao(bssid=bssid, ssid=ssid, canal=canal, banda=banda,
                      rssi=-50, x=5, y=5, largura_canal=largura)
    return Rede(ssid=ssid, bssid=bssid, canal=canal, banda=banda,
                largura_canal=largura, pontos=(medicao,))


class TestCanaisValidos:
    """A lista de canais que o projeto aceita."""

    def test_2g_sao_tres(self) -> None:
        assert canais_validos("2.4") == CANAIS_2G == (1, 6, 11)

    def test_2g_nao_tem_canal_3(self) -> None:
        # O canal 3 existe na norma e se sobrepoe ao 1. Ele nao entra na lista
        # porque lista de canal aceito para projeto nao e "canal existente".
        assert 3 not in canais_validos("2.4")

    def test_2g_nao_tem_canal_2_nem_12(self) -> None:
        for canal in (2, 12):
            assert canal not in canais_validos("2.4")

    def test_5g_tem_bloques_de_quatro(self) -> None:
        canais = canais_5g_utilizaveis()
        for inicio, fim in FAIXAS_5G:
            bloco = [c for c in canais if inicio <= c <= fim]
            assert len(bloco) == (fim - inicio) // 4 + 1

    def test_5g_nao_usa_a_lacuna_dfs(self) -> None:
        canais = canais_5g_utilizaveis()
        assert not any(64 < c < 100 for c in canais)

    def test_banda_desconhecida(self) -> None:
        with pytest.raises(ValueError):
            canais_validos("6")

    @pytest.mark.parametrize("canal,banda,esperado", [
        (1, "2.4", True), (6, "2.4", True), (11, "2.4", True),
        (3, "2.4", False), (2, "2.4", False),
        (36, "5", True), (149, "5", True), (70, "5", False),
    ])
    def test_canal_valido(self, canal: int, banda: str, esperado: bool) -> None:
        assert canal_valido(canal, banda) is esperado

    def test_canal_valido_nao_levanta(self) -> None:
        assert canal_valido(1, "900") is False


class TestFaixaOcupada:
    """Qual canal um emissor ocupa de fato."""

    @pytest.mark.parametrize("canal,largura,banda,esperado", [
        (1, 20, "2.4", (1, 2)),
        (6, 20, "2.4", (6, 7)),
        (1, 40, "2.4", (1, 4)),
        (36, 20, "5", (36, 36)),
        (36, 40, "5", (36, 40)),
        (36, 80, "5", (36, 48)),
        (52, 40, "5", (52, 56)),
        (56, 40, "5", (56, 60)),
        (149, 20, "5", (149, 149)),
    ])
    def test_faixa(self, canal: int, largura: int, banda: str,
                   esperado: tuple[int, int]) -> None:
        assert faixa_ocupada(canal, largura, banda) == esperado

    def test_faixa_2g_de_20_mhz_nao_e_invertida(self) -> None:
        # (20 - 22) // 5 e -1 em divisao inteira, e a faixa saia (1, 0):
        # intervalo invertido, com o primeiro maior que o segundo.
        inicio, fim = faixa_ocupada(1, 20, "2.4")
        assert inicio <= fim

    def test_faixa_cresce_com_a_largura(self) -> None:
        for canal in (36, 52, 100, 149):
            faixas = [faixa_ocupada(canal, w, "5")[1] for w in (20, 40, 80)]
            assert faixas == sorted(faixas), canal

    def test_largura_desconhecida(self) -> None:
        with pytest.raises(CanalInvalido):
            faixa_ocupada(36, 30, "5")

    def test_160_mhz_em_2g_nao_existe(self) -> None:
        with pytest.raises(CanalInvalido):
            faixa_ocupada(6, 160, "2.4")

    def test_80_mhz_em_2g_nao_existe(self) -> None:
        with pytest.raises(CanalInvalido):
            faixa_ocupada(6, 80, "2.4")

    def test_banda_desconhecida(self) -> None:
        with pytest.raises(CanalInvalido):
            faixa_ocupada(36, 20, "900")

    def test_excecao_guarda_os_campos(self) -> None:
        with pytest.raises(CanalInvalido) as exc:
            faixa_ocupada(36, 30, "5")
        assert exc.value.canal == 36


class TestSobreposicao:
    """O detector de sobreposicao, incluindo os falsos negativos que importam."""

    @pytest.mark.parametrize("a,b", [
        ((1, 20, "2.4"), (6, 20, "2.4")),
        ((6, 20, "2.4"), (11, 20, "2.4")),
        ((1, 20, "2.4"), (11, 20, "2.4")),
        ((36, 20, "5"), (40, 20, "5")),
        ((36, 20, "5"), (56, 20, "5")),
        ((52, 20, "5"), (100, 20, "5")),
        ((149, 20, "5"), (36, 20, "5")),
    ])
    def test_nao_sobrepoe(self, a: tuple, b: tuple) -> None:
        assert sobrepoe(*a, *b) is False

    @pytest.mark.parametrize("a,b", [
        ((1, 20, "2.4"), (1, 20, "2.4")),
        ((36, 20, "5"), (36, 20, "5")),
        ((56, 40, "5"), (60, 20, "5")),
        ((36, 80, "5"), (44, 20, "5")),
        ((36, 80, "5"), (48, 20, "5")),
        ((1, 40, "2.4"), (4, 20, "2.4")),
    ])
    def test_sobrepoe(self, a: tuple, b: tuple) -> None:
        assert sobrepoe(*a, *b) is True

    def test_56_a_40_nao_atinge_o_64(self) -> None:
        # 56 a 40 MHz ocupa 56 e 60. O canal 64 e do bloco seguinte e fica
        # livre, e o 52 e do bloco anterior: e isso que permite usar os blocos
        # 36-48 e 52-64 ao mesmo tempo sem interferir.
        assert sobrepoe(56, 40, "5", 52, 20, "5") is False
        assert sobrepoe(56, 40, "5", 64, 20, "5") is False

    def test_bandas_diferentes_nunca_sobrepoem(self) -> None:
        # Mesmo numero de canal, bandas distintas: frequencias diferentes.
        assert sobrepoe(6, 20, "2.4", 6, 20, "5") is False

    def test_160_mhz_engloba_o_bloco_inteiro(self) -> None:
        assert sobrepoe(36, 160, "5", 64, 20, "5") is True

    def test_80_mhz_NAO_engloba_o_bloco_vizinho(self) -> None:
        # 36 a 80 MHz termina no canal 48. O canal 52 e do bloco seguinte e
        # fica livre - e o que permite usar blocos 36-48 e 52-64 juntos.
        assert sobrepoe(36, 80, "5", 52, 20, "5") is False


class TestNivelInterferencia:
    """Redes que interferem numa rede dada."""

    def test_rede_isolada(self) -> None:
        alvo = rede(bssid="02:00:00:00:01:00", canal=36)
        vizinha = rede(bssid="02:00:00:00:02:00", canal=149)
        assert nivel_interferencia(alvo, [alvo, vizinha]) == []

    def test_encontra_a_vizinha(self) -> None:
        alvo = rede(bssid="02:00:00:00:01:00", canal=36)
        vizinha = rede(bssid="02:00:00:00:02:00", canal=36)
        assert nivel_interferencia(alvo, [alvo, vizinha]) == [vizinha]

    def test_nao_conta_a_si_mesma(self) -> None:
        alvo = rede(bssid="02:00:00:00:01:00", canal=36, largura=80)
        assert nivel_interferencia(alvo, [alvo]) == []

    def test_outra_banda_nao_interfere(self) -> None:
        alvo = rede(bssid="02:00:00:00:01:00", canal=6, banda="2.4")
        vizinha = rede(bssid="02:00:00:00:02:00", canal=11, banda="2.4")
        longe = rede(bssid="02:00:00:00:03:00", canal=36, banda="5")
        assert nivel_interferencia(alvo, [alvo, vizinha, longe]) == []

    def test_largura_alarga_atropela_a_vizinha(self) -> None:
        alvo = rede(bssid="02:00:00:00:01:00", canal=36, largura=80)
        vizinha = rede(bssid="02:00:00:00:02:00", canal=44)
        assert vizinha in nivel_interferencia(alvo, [alvo, vizinha])

    def test_ordem_deterministica(self) -> None:
        alvo = rede(bssid="02:00:00:00:01:00", canal=36, largura=80)
        vizinhas = [
            rede(bssid="02:00:00:00:05:00", canal=36),
            rede(bssid="02:00:00:00:02:00", canal=36),
            rede(bssid="02:00:00:00:03:00", canal=40),
        ]
        resultado = nivel_interferencia(alvo, [alvo] + vizinhas)
        # Ordenado por banda, canal e BSSID: os dois canais 36 primeiro, em
        # ordem de BSSID, e so entao o canal 40.
        assert [r.canal for r in resultado] == [36, 36, 40]
        assert [r.bssid for r in resultado[:2]] == sorted(r.bssid for r in resultado[:2])

    def test_lista_vazia_de_vizinhas(self) -> None:
        alvo = rede()
        assert nivel_interferencia(alvo, []) == []


class TestConflitoDeCanal:
    """Redes que dividem o mesmo numero de canal."""

    def test_sem_conflito(self) -> None:
        redes = [rede(bssid=f"02:00:00:00:0{i}:00", canal=c) for i, c in
                 enumerate((36, 40, 44, 149))]
        assert conflito_de_canal(redes) == {}

    def test_detecta_o_canal_repetido(self) -> None:
        redes = [rede(bssid=f"02:00:00:00:0{i}:00", canal=36) for i in range(3)]
        assert list(conflito_de_canal(redes)) == [36]

    def test_nao_repete_o_mesmo_ssid(self) -> None:
        # O mesmo SSID em tres BSSIDs conta como conflito - sao tres radios
        # disputando o mesmo espectro - mas o nome aparece uma vez so na tela.
        redes = [rede(bssid=f"02:00:00:00:0{i}:00", ssid="CORP", canal=36)
                 for i in range(3)]
        assert conflito_de_canal(redes)[36] == ["CORP"]

    def test_um_so_bssid_nao_conflita_consigo_mesmo(self) -> None:
        # Uma rede lida em varios pontos continua sendo uma rede.
        med = Medicao(bssid="02:00:00:00:01:00", ssid="CORP", canal=36,
                      banda="5", rssi=-50, x=5, y=5)
        redes = [Rede(ssid="CORP", bssid="02:00:00:00:01:00", canal=36, banda="5",
                      largura_canal=20, pontos=(med, med))]
        assert conflito_de_canal(redes) == {}

    def test_ignora_banda_diferente(self) -> None:
        redes = [
            rede(bssid="02:00:00:00:01:00", canal=6, banda="2.4"),
            rede(bssid="02:00:00:00:02:00", canal=36, banda="5"),
        ]
        assert conflito_de_canal(redes) == {}

    def test_lista_vazia(self) -> None:
        assert conflito_de_canal([]) == {}

    def test_saida_ordenada(self) -> None:
        redes = [rede(bssid=f"02:00:00:00:0{i}:00", canal=c, ssid=f"S{i}")
                 for i, c in enumerate((149, 36, 40))]
        assert list(conflito_de_canal(redes)) == sorted(conflito_de_canal(redes))


class TestIndicesDeConflito:
    """APs que disputam espectro entre si."""

    def test_andar_sem_conflito(self) -> None:
        aps = agrupar_aps([
            rede(bssid="02:00:00:00:01:00", canal=36),
            rede(bssid="02:00:00:00:02:00", canal=100),
            rede(bssid="02:00:00:00:03:00", canal=149),
        ])
        assert indices_de_conflito(aps) == {}

    def test_detecta_o_par(self) -> None:
        aps = agrupar_aps([
            rede(bssid="02:00:00:00:01:00", canal=36, largura=80),
            rede(bssid="02:00:00:00:02:00", canal=44),
        ])
        conflitos = indices_de_conflito(aps)
        assert "02:00:00:00:01" in conflitos
        assert "02:00:00:00:02" in conflitos["02:00:00:00:01"]

    def test_ap_sem_conflito_nao_aparece(self) -> None:
        aps = agrupar_aps([
            rede(bssid="02:00:00:00:01:00", canal=36, largura=80),
            rede(bssid="02:00:00:00:02:00", canal=44),
            rede(bssid="02:00:00:00:03:00", canal=149),
        ])
        conflitos = indices_de_conflito(aps)
        assert "02:00:00:00:03" not in conflitos

    def test_nao_repete_o_conflito(self) -> None:
        aps = agrupar_aps([
            rede(bssid="02:00:00:00:01:00", canal=36, largura=80),
            rede(bssid="02:00:00:00:02:00", canal=44),
        ])
        lista = indices_de_conflito(aps)["02:00:00:00:01"]
        assert len(lista) == len(set(lista))

    def test_andar_vazio(self) -> None:
        assert indices_de_conflito([]) == {}


class TestCanalRecomendado:
    """Escolha do canal para um AP novo."""

    def test_andar_vazio_escolhe_o_primeiro(self) -> None:
        assert canal_recomendado("2.4", 20, []) == 1

    def test_2g_escolhe_um_dos_tres(self) -> None:
        assert canal_recomendado("2.4", 20, [1, 6]) in CANAIS_2G

    def test_5g_escolhe_dos_validos(self) -> None:
        assert canal_recomendado("5", 20, [36]) in canais_validos("5")

    def test_empate_resolve_no_mais_baixo(self) -> None:
        # Dois canais disputados: o terceiro e Recommended, nao qualquer um.
        assert canal_recomendado("2.4", 20, [1, 6]) == 11

    def test_evita_canal_ocupado(self) -> None:
        recomendacao = canal_recomendado("5", 20, [36, 52, 100, 149])
        assert recomendacao not in (36, 52, 100, 149)

    def test_resultado_deterministico(self) -> None:
        ocupados = [1, 6, 36, 40, 52, 100]
        primeiro = canal_recomendado("5", 20, ocupados)
        assert all(canal_recomendado("5", 20, ocupados) == primeiro for _ in range(5))

    def test_largura_80_leva_em_conta(self) -> None:
        # Um canal de 80 ms ocupa quatro blocos, entao o recomendado nao pode
        # ser vizinho de um ja ocupado por um emissor largo.
        assert canal_recomendado("5", 80, [36]) in canais_validos("5")

    def test_largura_invalida(self) -> None:
        with pytest.raises(CanalInvalido):
            canal_recomendado("2.4", 80, [])

    def test_ignora_canal_fora_da_banda_dos_dados(self) -> None:
        # Dado sujo com canal de 2.4 GHz na lista de 5 GHz nao pode quebrar.
        assert canal_recomendado("5", 20, [1, 6, 11, 36]) in canais_validos("5")
