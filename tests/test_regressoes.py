"""Testes de regressao para os tres achados da auditoria P03."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from wifisurvey.capacidade import FRACAO_DE_AGLOMERADO, Parametros, dimensionar
from wifisurvey.interferencia import (
    canais_validos,
    canal_recomendado,
    conflito_de_canal,
    contagem_por_canal,
    faixa_ocupada,
    larguras_por_canal,
    sobrepoe,
)
from wifisurvey.mapa import cor_css, cor_para_rssi, escala_dos_dados
from wifisurvey.plano import Medicao, Rede, agrupar_aps

RAIZ = Path(__file__).resolve().parent.parent


def rede(bssid: str, ssid: str, canal: int, banda: str = "5", largura: int = 20) -> Rede:
    """Fabrica uma Rede com uma medicao.

    Build a Rede with one measurement.
    """
    m = Medicao(bssid, ssid, canal, banda, -50, 5, 5, largura)
    return Rede(ssid, bssid, canal, banda, largura, (m,))


def _html_do_andar(andar: str) -> str:
    """Gera o HTML de um andar do repositorio.

    Generate one repository floor's HTML.
    """
    import sys

    sys.path.insert(0, str(RAIZ / "src"))
    from wifisurvey.capacidade import verifica_projeto
    from wifisurvey.cli import _html_do_andar

    return _html_do_andar(andar, RAIZ / "dados", Parametros())


class TestCorCss:
    """A cor precisa sair no formato que o CSS entende.

    Achado: o f-string interpolava a tupla direto e produzia
    ``rgb((198, 40, 40))``. O navegador descarta a declaracao sem avisar, e a
    legenda ficava sem cor nenhuma sem que nada aparecesse errado no arquivo.
    """

    def test_sem_parenteses_duplos(self) -> None:
        assert cor_css((198, 40, 40)) == "rgb(198,40,40)"

    def test_formato_completo(self) -> None:
        assert re.fullmatch(r"rgb\(\d{1,3},\d{1,3},\d{1,3}\)", cor_css((0, 0, 0)))

    def test_tres_canais(self) -> None:
        assert cor_css((1, 2, 3)).count(",") == 2

    def test_nao_repassa_a_tupla(self) -> None:
        assert "(" not in cor_css((1, 2, 3)).replace("rgb(", "")

    def test_html_do_relatorio_nao_tem_rgb_duplo(self) -> None:
        html = _html_do_andar("andar1")
        assert "rgb((" not in html

    def test_html_tem_a_cor_da_escala(self) -> None:
        html = _html_do_andar("andar1")
        assert re.search(r"background:rgb\(\d+,\d+,\d+\)", html)


class TestContagemDeRadios:
    """A contagem de quem disputa o canal e por BSSID, nao por nome.

    Achado: a tabela contava ``len(ssids)``, e tres APs transmitindo o mesmo
    SSID no canal 36 apareciam como "1". Sao tres radios disputando o espectro.
    """

    def test_tres_aps_mesmo_ssid_sao_tres(self) -> None:
        redes = [rede(f"02:00:00:00:0{i}:00", "CORP-TI", 36) for i in range(3)]
        assert contagem_por_canal(redes) == {36: 3}

    def test_nomes_continuam_sem_repeticao(self) -> None:
        redes = [rede(f"02:00:00:00:0{i}:00", "CORP-TI", 36) for i in range(3)]
        assert conflito_de_canal(redes) == {36: ["CORP-TI"]}

    def test_a_contagem_excede_a_lista_de_nomes(self) -> None:
        redes = [rede(f"02:00:00:00:0{i}:00", "CORP-TI", 36) for i in range(3)]
        assert contagem_por_canal(redes)[36] > len(conflito_de_canal(redes)[36])

    def test_um_so_bssid_nao_conta(self) -> None:
        assert contagem_por_canal([rede("02:00:00:00:01:00", "A", 36)]) == {}

    def test_canais_distintos_por_canal(self) -> None:
        # Dois radios no mesmo canal, cada um em seu BSSID: uma disputa.
        redes = [
            rede("02:00:00:00:01:00", "A", 36),
            rede("02:00:00:00:02:00", "B", 36),
        ]
        assert contagem_por_canal(redes) == {36: 2}

    def test_canal_com_um_radio_so_nao_conta(self) -> None:
        redes = [
            rede("02:00:00:00:01:00", "A", 36),
            rede("02:00:00:00:02:00", "B", 40),
        ]
        assert contagem_por_canal(redes) == {}

    def test_lista_vazia(self) -> None:
        assert contagem_por_canal([]) == {}

    def test_html_mostra_o_numero_de_radios(self) -> None:
        html = _html_do_andar("andar1")
        assert "Radios em disputa" in html


class TestLarguraNaRecomendacao:
    """Um ocupante largo precisa ser visto como largo.

    Achado: ``canal_recomendado`` assumia 20 MHz para todo canal ocupado. Um
    emissor de 80 MHz no canal 36 ocupa 36 a 48, e a funcao o via como se
    ocupasse so o 36 - podendo recomendar o canal 44, que nao esta livre.
    """

    def test_mapa_de_larguras(self) -> None:
        redes = [rede("02:00:00:00:01:00", "A", 36, largura=80)]
        assert larguras_por_canal(redes) == {36: 80}

    def test_pega_a_mais_larga_do_canal(self) -> None:
        redes = [
            rede("02:00:00:00:01:00", "A", 36, largura=20),
            rede("02:00:00:00:02:00", "B", 36, largura=80),
        ]
        assert larguras_por_canal(redes)[36] == 80

    def test_sem_mapa_usa_20_mhz(self) -> None:
        assert larguras_por_canal([]) == {}

    def test_ocupante_largo_bloqueia_o_bloco(self) -> None:
        # Com o mapa, o 44 e visto como ocupado e nao e recomendado.
        escolhido = canal_recomendado("5", 20, [36], {36: 80})
        assert escolhido in canais_validos("5")

    def test_ocupante_largo_empurra_a_recomendacao(self) -> None:
        # Um AP de 80 MHz no 36 ocupa 36-48. Com 52 ocupado, o proximo
        # livre e 56 - dentro do bloco 52-64, que continua limpo.
        escolhido = canal_recomendado("5", 20, [36, 52], {36: 80})
        assert escolhido == 56

    def test_livre_ou_perturbado(self) -> None:
        # O canal escolhido nao pode estar dentro do bloco de um ocupante
        # largo. Este e o teste que o achado desatualizava.
        escolhido = canal_recomendado("5", 20, [36, 52], {36: 80})
        inicio, fim = faixa_ocupada(36, 80, "5")
        assert not (inicio <= escolhido <= fim)

    def test_40_e_44_estao_barrados(self) -> None:
        # Sem o mapa, 40 e 44 parecem livres e um deles seria escolhido.
        assert canal_recomendado("5", 20, [36, 52]) in (40, 44)
        assert canal_recomendado("5", 20, [36, 52], {36: 80}) not in (40, 44)

    def test_mesmo_conjunto_mas_sem_o_mapa_da_outro_resultado(self) -> None:
        # A razao do achado: sem o mapa, 40 e 44 parecem livres.
        com_mapa = canal_recomendado("5", 20, [36, 52], {36: 80})
        sem_mapa = canal_recomendado("5", 20, [36, 52])
        assert com_mapa != sem_mapa

    def test_mapa_com_largura_invalida_e_ignorado(self) -> None:
        assert canal_recomendado("5", 20, [36], {36: 30}) in canais_validos("5")

    def test_largura_do_ocupante_igual_a_do_novo(self) -> None:
        assert canal_recomendado("5", 20, [36], {36: 20}) in canais_validos("5")

    def test_2g_aceita_o_mapa(self) -> None:
        assert canal_recomendado("2.4", 20, [1], {1: 20}) in (1, 6, 11)


class TestOcupacaoSomando:
    """O criterio de ocupacao soma, nao multiplica.

    Achado: ``por_cobertura * rodadas`` nao tem leitura fisica. Um andar de
    100 m2 com 200 pessoas dava 70 APs; com soma, da 70 tambem - mas 540 m2
    com 90 pessoas cai de 18 para 8, que e um numero defensavel.
    """

    def test_540_m2_com_90_da_8(self) -> None:
        d = dimensionar([], 540.0, 90, Parametros())
        assert d.aps_necessarios == 8

    def test_540_m2_com_60_da_6(self) -> None:
        assert dimensionar([], 540.0, 60, Parametros()).aps_necessarios == 6

    def test_uma_rodada_e_so_cobertura(self) -> None:
        # Cabem 15 pessoas em 540 m2. Com 15, uma rodada: o resultado e a
        # cobertura pura, sem acrescimo.
        d = dimensionar([], 540.0, 15, Parametros())
        assert d.aps_necessarios == d.aps_por_cobertura

    def test_cresce_com_a_ocupacao(self) -> None:
        p = Parametros()
        com_15 = dimensionar([], 540.0, 15, p).aps_necessarios
        com_90 = dimensionar([], 540.0, 90, p).aps_necessarios
        assert com_90 > com_15

    def test_nao_dispara_para_zero_rodadas(self) -> None:
        d = dimensionar([], 540.0, 0, Parametros())
        assert d.aps_necessarios == d.aps_por_cobertura

    def test_ocupacao_vence_quando_o_espaco_acaba(self) -> None:
        # 100 m2 comportam 2,86 pessoas por rodada. Com 5000 pessoas, sao
        # 1750 rodadas, e a ocupacao domina todos os outros criterios.
        d = dimensionar([], 100.0, 5000, Parametros())
        assert d.aps_necessarios == 1750
        assert d.aps_necessarios > d.aps_por_populacao
        assert d.aps_necessarios > d.aps_por_cobertura

    def test_cobertura_vence_sem_crowding(self) -> None:
        # Area grande e pouca gente: uma rodada so, e o resultado e a
        # cobertura pura, que e o criterio de area.
        d = dimensionar([], 5000.0, 100, Parametros())
        assert d.aps_necessarios == d.aps_por_cobertura

    def test_nenhum_criterio_da_menos_que_a_cobertura(self) -> None:
        p = Parametros()
        for area in (100.0, 540.0, 5000.0):
            for clientes in (0, 15, 90, 5000):
                d = dimensionar([], area, clientes, p)
                assert d.aps_necessarios >= d.aps_por_cobertura
                assert d.aps_necessarios >= d.aps_por_populacao

    def test_andar_do_repositorio_muda_para_8(self) -> None:
        import sys

        sys.path.insert(0, str(RAIZ / "src"))
        from wifisurvey.leitor import carregar

        aps = carregar(RAIZ / "dados" / "varrimento-andar3.csv")
        d = dimensionar(aps, 540.0, 90, Parametros())
        assert d.aps_necessarios == 8
        assert d.falta == 3


class TestNaoRegressao:
    """O que o auditoria poderia ter quebrado e nao quebrou."""

    def test_agrupar_aps_inalterado(self) -> None:
        aps = agrupar_aps([
            rede("02:00:00:00:01:00", "A", 1, "2.4"),
            rede("02:00:00:00:01:01", "A", 36, "5"),
        ])
        assert len(aps) == 1

    def test_sobreposicao_inalterada(self) -> None:
        assert sobrepoe(56, 40, "5", 60, 20, "5")
        assert not sobrepoe(36, 80, "5", 52, 20, "5")

    def test_faixa_ocupada_inalterada(self) -> None:
        assert faixa_ocupada(36, 80, "5") == (36, 48)

    def test_escala_de_cor_inalterada(self) -> None:
        assert escala_dos_dados([-70.0, -40.0]) == (-70.0, -40.0)
        assert cor_para_rssi(-70.0, -70.0, -40.0) == (198, 40, 40)