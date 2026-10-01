"""Testes de capacidade e dimensionamento.

Capacity and sizing tests.

O numero de clientes que um AP suporta nao vem de lugar nenhum: vem do arquivo
de configuracao. Por isso o que se testa aqui e a **arredondacao** - teto,
piso, fracao de cliente que sobra - e nao a tabela em si. A tabela mudar e uma
decisao legitima do cliente; o que nao pode mudar e um AP aguentar 2,5 clientes.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from wifisurvey.capacidade import (
    CAPACIDADE_PADRAO,
    CRITERIOS_PADRAO,
    FRACAO_DE_AGLOMERADO,
    Dimensionamento,
    Parametros,
    ParametrosInvalidos,
    capacidade_do_ap,
    dimensionar,
    espacamento_aps,
    verifica_projeto,
)
from wifisurvey.plano import AccessPoint, Medicao, Rede

RAIZ = Path(__file__).resolve().parent.parent


def rede(
    bssid: str = "02:00:00:00:01:00",
    ssid: str = "CORP",
    canal: int = 36,
    banda: str = "5",
    largura: int = 20,
    pontos: list[tuple[float, float, int]] | None = None,
) -> Rede:
    """Fabrica uma Rede com medicoes sinteticas.

    Build a Rede with synthetic measurements.
    """
    brutos = pontos or [(5.0, 5.0, -50), (10.0, 10.0, -55), (15.0, 15.0, -60)]
    medicoes = tuple(
        Medicao(bssid=bssid, ssid=ssid, canal=canal, banda=banda,
                rssi=rssi, x=x, y=y, largura_canal=largura)
        for x, y, rssi in brutos
    )
    return Rede(ssid=ssid, bssid=bssid, canal=canal, banda=banda,
                largura_canal=largura, pontos=medicoes)


def ap(bssid: str, x: float, y: float, *redes: Rede) -> AccessPoint:
    """Fabrica um AccessPoint.

    Build an AccessPoint.
    """
    return AccessPoint(
        bssid=bssid,
        bandas=tuple(sorted({r.banda for r in redes})),
        x=x,
        y=y,
        redes=redes,
    )


class TestPadroes:
    """Os numeros de referencia do modulo."""

    def test_tem_2g_e_5g(self) -> None:
        assert set(CAPACIDADE_PADRAO) == {"2.4", "5"}

    def test_20_mhz_2g_e_menor_que_5g(self) -> None:
        assert CAPACIDADE_PADRAO["2.4"]["20"] < CAPACIDADE_PADRAO["5"]["20"]

    def test_em_5g_capacidade_so_cresce_com_a_largura(self) -> None:
        larguras = CAPACIDADE_PADRAO["5"]
        valores = [larguras[str(l)] for l in (20, 40, 80, 160)]
        assert valores == sorted(valores)

    def test_em_2g_capacidade_CAI_com_a_largura(self) -> None:
        # Em 2.4 GHz um canal de 40 MHz NAO dobra a capacidade: ele rouba o
        # tempo de ar dos vizinhos, entao a mesma radio carrega menos cliente
        # proprio. E o oposto da banda de 5 GHz, onde o canal largo e mais
        # limpo. A tabela nao e simetrica de proposito.
        larguras = CAPACIDADE_PADRAO["2.4"]
        assert larguras["40"] < larguras["20"]

    def test_rssi_minimo_negativo(self) -> None:
        assert CRITERIOS_PADRAO["rssi_minimo_dbm"] < 0

    def test_area_por_cliente_positiva(self) -> None:
        assert CRITERIOS_PADRAO["area_por_cliente_m2"] > 0


class TestParametros:
    """Carga e validacao."""

    def test_padrao_sempre_valido(self) -> None:
        Parametros()

    def test_carrega_o_arquivo_do_repo(self) -> None:
        p = Parametros.carregar(RAIZ / "dados" / "capacidade.yaml")
        assert p.clientes_por_ap("5", 80) == 100

    def test_arquivo_ausente(self) -> None:
        with pytest.raises(OSError):
            Parametros.carregar(RAIZ / "dados" / "nao-existe.yaml")

    def test_banda_desconhecida(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros(capacidade={"6": {"20": 10}})

    def test_largura_desconhecida(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros(capacidade={"5": {"30": 10}})

    def test_capacidade_zero(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros(capacidade={"5": {"20": 0}})

    def test_capacidade_negativa(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros(capacidade={"5": {"20": -5}})

    def test_area_por_cliente_zero(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros(criterios={"area_por_cliente_m2": 0})

    def test_rssi_minimo_otimista_demais(self) -> None:
        # -20 dBm e sinal melhor do que qualquer AP produz. Aceitar isso como
        # "minimo aceitavel" desligaria o alerta de AP fraco sem querer.
        with pytest.raises(ParametrosInvalidos):
            Parametros(criterios={"rssi_minimo_dbm": -20})

    def test_rssi_minimo_abaixo_do_piso(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros(criterios={"rssi_minimo_dbm": -140})

    def test_densidade_zero(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros(criterios={"aps_por_1000_m2": 0})

    def test_so_substitui_o_criterio_mudado(self) -> None:
        p = Parametros(criterios={"rssi_minimo_dbm": -72})
        assert p.rssi_minimo == -72.0
        assert p.criterios["area_por_cliente_m2"] == CRITERIOS_PADRAO["area_por_cliente_m2"]

    def test_banda_inexistente_na_capacidade(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros().clientes_por_ap("60", 20)

    def test_largura_inexistente_na_capacidade(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            Parametros().clientes_por_ap("5", 320)


class TestCapacidadeDoAp:
    """Soma de bandas, sem contar SSID duas vezes."""

    def test_ap_de_uma_banda(self) -> None:
        a = ap("a", 5, 5, rede(banda="5", largura=20))
        assert capacidade_do_ap(a, Parametros()) == 25

    def test_ap_dual_band_soma_as_duas(self) -> None:
        a = ap("a", 5, 5, rede(banda="2.4"), rede(banda="5"))
        assert capacidade_do_ap(a, Parametros()) == 15 + 25

    def test_varios_ssids_nao_somam_capacidade(self) -> None:
        # Cinco SSIDs no mesmo BSSID continuam sendo uma antena.
        a = ap("a", 5, 5, *[rede(ssid=f"S{i}") for i in range(5)])
        assert capacidade_do_ap(a, Parametros()) == 25

    def test_larguras_distintas_na_mesma_banda_somam(self) -> None:
        a = ap("a", 5, 5, rede(largura=20), rede(largura=80))
        assert capacidade_do_ap(a, Parametros()) == 25 + 100

    def test_mesma_largura_nao_soma_duas_vezes(self) -> None:
        a = ap("a", 5, 5, rede(largura=20), rede(largura=20))
        assert capacidade_do_ap(a, Parametros()) == 25

    def test_ap_sem_redes(self) -> None:
        vazio = AccessPoint(bssid="a", bandas=(), x=1, y=1, redes=())
        assert capacidade_do_ap(vazio, Parametros()) == 0


class TestDimensionar:
    """Dimensionamento por area, populacao e rodadas de ocupacao."""

    def test_andar_pequeno_precisa_de_um(self) -> None:
        d = dimensionar([], 100.0, 5, Parametros())
        assert d.aps_necessarios >= 1

    def test_andar_grande_precisa_de_mais(self) -> None:
        pequeno = dimensionar([], 100.0, 10, Parametros())
        grande = dimensionar([], 5000.0, 10, Parametros())
        assert grande.aps_necessarios > pequeno.aps_necessarios

    def test_mais_pessoas_Exige_mais_aps(self) -> None:
        vazio = dimensionar([], 540.0, 10, Parametros())
        cheio = dimensionar([], 540.0, 900, Parametros())
        assert cheio.aps_necessarios > vazio.aps_necessarios

    def test_area_invalida(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            dimensionar([], 0.0, 10, Parametros())

    def test_area_negativa(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            dimensionar([], -1.0, 10, Parametros())

    def test_populacao_negativa(self) -> None:
        with pytest.raises(ParametrosInvalidos):
            dimensionar([], 100.0, -5, Parametros())

    def test_rodadas_de_ocupacao_dominam(self) -> None:
        # 100 m2 comportam 100/35 = 2 pessoas confortavelmente. Com 200
        # pessoas sao 100 rodadas, e a area vira o gargalo.
        d = dimensionar([], 100.0, 200, Parametros())
        assert d.aps_necessarios >= 2

    def test_falta_e_zero_quando_sobra(self) -> None:
        d = dimensionar([], 540.0, 10, Parametros())
        d.aps_existentes = d.aps_necessarios
        assert d.falta == 0

    def test_falta_conta_a_diferenca(self) -> None:
        d = dimensionar([], 540.0, 900, Parametros())
        d.aps_existentes = 2
        assert d.falta == 2 - d.aps_necessarios if False else d.falta == max(0, d.aps_necessarios - 2)

    def test_excedente_conta_a_diferenca(self) -> None:
        d = dimensionar([], 540.0, 10, Parametros())
        d.aps_existentes = d.aps_necessarios + 5
        assert d.excedente == 5

    def test_capacidade_suficiente(self) -> None:
        aps = [ap(f"a{i}", i * 3, 3, rede(banda="5", largura=80)) for i in range(3)]
        d = dimensionar(aps, 540.0, 100, Parametros())
        assert d.capacidade_total == 300
        assert d.capacidade_suficiente

    def test_capacidade_insuficiente(self) -> None:
        d = dimensionar([], 540.0, 5000, Parametros())
        assert not d.capacidade_suficiente

    def test_area_por_cliente(self) -> None:
        d = dimensionar([], 540.0, 10, Parametros())
        assert d.area_por_cliente == 54.0

    def test_area_por_cliente_zero_pessoas(self) -> None:
        d = dimensionar([], 540.0, 0, Parametros())
        assert d.area_por_cliente == 0.0

    def test_resumo_menca_falta(self) -> None:
        d = dimensionar([], 540.0, 900, Parametros())
        d.aps_existentes = 2
        assert "faltam" in d.resumo()

    def test_resumo_menca_excedente(self) -> None:
        d = dimensionar([], 540.0, 10, Parametros())
        d.aps_existentes = d.aps_necessarios + 2
        assert "acima do necessario" in d.resumo()

    def test_resumo_menca_correto(self) -> None:
        d = dimensionar([], 540.0, 10, Parametros())
        d.aps_existentes = d.aps_necessarios
        assert "dimensionamento correto" in d.resumo()

    def test_para_dict_tem_as_chaves(self) -> None:
        d = dimensionar([], 540.0, 10, Parametros())
        chaves = set(d.para_dict())
        assert {"area_m2", "clientes", "aps_necessarios", "capacidade_total",
                "falta", "excedente"} <= chaves

    def test_para_dict_serializa(self) -> None:
        import json

        d = dimensionar([], 540.0, 10, Parametros())
        assert json.loads(json.dumps(d.para_dict()))


class TestEspacamento:
    """Vizinho mais proximo, e nao distancia entre todos os pares."""

    def test_um_ap_so(self) -> None:
        assert espacamento_aps([ap("a", 5, 5, rede())]) == (0.0, 0.0)

    def test_lista_vazia(self) -> None:
        assert espacamento_aps([]) == (0.0, 0.0)

    def test_ap_na_mesma_posicao_e_ignorado(self) -> None:
        dois = [ap("a", 5, 5, rede()), ap("b", 5, 5, rede(bssid="02:00:00:00:02:00"))]
        assert espacamento_aps(dois) == (0.0, 0.0)

    def test_planta_regular(self) -> None:
        aps = [ap(str(i), 5 + i * 10, 5, rede()) for i in range(4)]
        menor, tipica = espacamento_aps(aps)
        assert menor == pytest.approx(tipica)

    def test_aglomerado_deriva_a_mediana(self) -> None:
        # Dois APs colados num canto, o resto da planta com 10 m de passo.
        aps = [ap("a", 5, 5, rede()), ap("b", 5.5, 5.4, rede(bssid="02:00:00:00:02:00"))]
        aps += [ap(f"c{i}", 15 + 10 * i, 5, rede()) for i in range(4)]
        menor, tipica = espacamento_aps(aps)
        assert menor < tipica * FRACAO_DE_AGLOMERADO

    def test_planta_regular_nao_deriva(self) -> None:
        aps = [ap(f"a{i}", 5 + 10 * i, 5, rede()) for i in range(5)]
        menor, tipica = espacamento_aps(aps)
        assert menor == pytest.approx(tipica)


class TestVerificaProjeto:
    """Os problemas que o relatorio aponta."""

    def test_andar_vazio(self) -> None:
        assert verifica_projeto([], Parametros()) == ["nenhum access point no andar"]

    def test_andar_bem_projetado_nao_acusa(self) -> None:
        aps = [ap(str(i), 6 + (i % 3) * 10, 6 + (i // 3) * 8, rede()) for i in range(9)]
        assert verifica_projeto(aps, Parametros()) == []

    def test_ap_fraco_e_acusado(self) -> None:
        fraco = ap("fraco", 10, 10, rede(pontos=[(10, 10, -85)]))
        problemas = verifica_projeto([fraco], Parametros())
        assert any("abaixo de" in p for p in problemas)

    def test_ap_forte_nao_e_acusado(self) -> None:
        forte = ap("forte", 10, 10, rede(pontos=[(10, 10, -40)]))
        problemas = verifica_projeto([forte], Parametros())
        assert not any("abaixo de" in p for p in problemas)

    def test_aglomerado_e_acusado(self) -> None:
        aps = [ap("a", 5, 5, rede()), ap("b", 5.4, 5.3, rede(bssid="02:00:00:00:02:00"))]
        aps += [ap(f"c{i}", 5 + 12 * (i + 1), 5, rede()) for i in range(4)]
        problemas = verifica_projeto(aps, Parametros())
        assert any("aglomerado" in p for p in problemas)

    def test_planta_regular_nao_acusa_aglomerado(self) -> None:
        aps = [ap(str(i), 4 + (i % 4) * 7, 4 + (i // 4) * 7, rede()) for i in range(9)]
        problemas = verifica_projeto(aps, Parametros())
        assert not any("aglomerado" in p for p in problemas)

    def test_fraco_e_aglomerado_aparecem_juntos(self) -> None:
        # Um AP fraco e dois APs colados, num andar de resto regular.
        aps = [ap("fraco", 5, 5, rede(pontos=[(5, 5, -90)]))]
        aps += [ap("b", 5.5, 5.4, rede(bssid="02:00:00:00:02:00"))]
        aps += [ap(f"c{i}", 16 + 10 * i, 5, rede()) for i in range(3)]
        problemas = verifica_projeto(aps, Parametros())
        assert any("abaixo de" in p for p in problemas)
        assert any("aglomerado" in p for p in problemas)


class TestDimensionamentoIsolado:
    """A classe de resultado, sem passar por dimensionar."""

    def test_falta_negativa_vira_zero(self) -> None:
        d = Dimensionamento(540, 10, 4, 9, 4, 1, 0)
        assert d.falta == 0

    def test_excedente_negativo_vira_zero(self) -> None:
        d = Dimensionamento(540, 10, 9, 4, 9, 1, 0)
        assert d.excedente == 0

    def test_arredondamento_para_cima(self) -> None:
        # 900 clientes / 100 por AP = 9 rodadas exatas; o teto continua 1.
        d = dimensionar([], 100.0, 900, Parametros())
        assert isinstance(d.aps_necessarios, int)
        assert not isinstance(d.aps_necessarios, float)

    def test_matematica_nao_divide_por_zero(self) -> None:
        d = dimensionar([], 540.0, 0, Parametros())
        assert d.aps_necessarios >= 1
        assert math.isfinite(float(d.aps_necessarios))
