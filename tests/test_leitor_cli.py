"""Testes do leitor de CSV, do modelo de planta e da CLI.

CSV reader, floor model and CLI tests.

O CSV vem de equipamento, entao os testes cobrem exportacao real: banda escrita
de seis maneiras diferentes, larguras de canal que nao existem, cabecalho
incompleto e numero que nao convergiu. Um leitor que so funciona com o CSV
limpo que o proprio codigo gerou nao serve para nada em campo.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from wifisurvey.cli import construir_parser, main
from wifisurvey.leitor import (
    COLUNAS_OBRIGATORIAS,
    CsvInvalido,
    _normalizar_banda,
    agregar,
    carregar,
    carregar_andares,
    ler_csv,
)
from wifisurvey.plano import (
    AccessPoint,
    Medicao,
    Rede,
    assinatura_do_equipamento,
    agrupar_aps,
)

RAIZ = Path(__file__).resolve().parent.parent

CABECALHO = "bssid,ssid,canal,banda,rssi,x,y,largura_canal"


def escrever(tmp_path: Path, linhas: list[str], cabecalho: str = CABECALHO) -> Path:
    """Grava um CSV de teste.

    Write a test CSV.
    """
    destino = tmp_path / "varrimento-teste.csv"
    destino.write_text("\n".join([cabecalho] + linhas) + "\n", encoding="utf-8")
    return destino


class TestNormalizarBanda:
    """As grafias de banda que aparecem em exportacao real."""

    @pytest.mark.parametrize("bruto,esperado", [
        ("2.4", "2.4"), ("2.4G", "2.4"), ("2,4", "2.4"), ("2.4GHz", "2.4"),
        ("2.4 ghz", "2.4"), ("2400", "2.4"), ("2400MHz", "2.4"),
        ("5", "5"), ("5G", "5"), ("5g", "5"), ("5GHz", "5"),
        ("5000", "5"), ("5000MHz", "5"), ("  5  ", "5"),
    ])
    def test_reconhece(self, bruto: str, esperado: str) -> None:
        assert _normalizar_banda(bruto) == esperado

    def test_nao_reconhece(self) -> None:
        with pytest.raises(CsvInvalido):
            _normalizar_banda("6")

    def test_texto_vazio(self) -> None:
        with pytest.raises(CsvInvalido):
            _normalizar_banda("")


class TestLerCsv:
    """A leitura do arquivo."""

    def test_linha_completa(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,5,-50,5,5,20"])
        medicoes = ler_csv(c)
        assert len(medicoes) == 1
        assert medicoes[0].ssid == "CORP"
        assert medicoes[0].canal == 36
        assert medicoes[0].rssi == -50

    def test_arquivo_inexistente(self, tmp_path: Path) -> None:
        with pytest.raises(CsvInvalido):
            ler_csv(tmp_path / "nao-existe.csv")

    def test_arquivo_vazio(self, tmp_path: Path) -> None:
        c = tmp_path / "vazio.csv"
        c.write_text("", encoding="utf-8")
        with pytest.raises(CsvInvalido):
            ler_csv(c)

    def test_cabecalho_incompleto(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["1,CORP,36,5,-50,5,5"], "bssid,ssid,canal,banda,rssi")
        with pytest.raises(CsvInvalido) as exc:
            ler_csv(c)
        assert "x" in str(exc.value) or "y" in str(exc.value)

    def test_canal_nao_numerico(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,abc,5,-50,5,5,20"])
        with pytest.raises(CsvInvalido) as exc:
            ler_csv(c)
        assert exc.value.linha == 2

    def test_rssi_nao_numerico(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,5,fraco,5,5,20"])
        with pytest.raises(CsvInvalido):
            ler_csv(c)

    def test_coordenada_nao_numerica(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,5,-50,meio,5,20"])
        with pytest.raises(CsvInvalido):
            ler_csv(c)

    def test_banda_desconhecida(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,6,-50,5,5,20"])
        with pytest.raises(CsvInvalido):
            ler_csv(c)

    def test_largura_vazia_usa_20(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,5,-50,5,5,"])
        assert ler_csv(c)[0].largura_canal == 20

    def test_sem_coluna_de_largura(self, tmp_path: Path) -> None:
        c = escrever(
            tmp_path, ["02:00:00:00:01:00,CORP,36,5,-50,5,5"],
            "bssid,ssid,canal,banda,rssi,x,y",
        )
        assert ler_csv(c)[0].largura_canal == 20

    def test_largura_nao_numerica(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,5,-50,5,5,larga"])
        with pytest.raises(CsvInvalido):
            ler_csv(c)

    def test_bssid_vazio_e_pulado(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, [
            ",CORP,36,5,-50,5,5,20",
            "02:00:00:00:01:00,CORP,36,5,-50,5,5,20",
        ])
        assert len(ler_csv(c)) == 1

    def test_ssid_vazio_vira_oculto(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,,36,5,-50,5,5,20"])
        assert ler_csv(c)[0].ssid == "<oculto>"

    def test_bssid_e_normalizado(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,5,-50,5,5,20"])
        assert ler_csv(c)[0].bssid == "02:00:00:00:01:00"

    def test_espaco_em_branco_no_bssid(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["  02:00:00:00:01:00 ,CORP,36,5,-50,5,5,20"])
        assert ler_csv(c)[0].bssid == "02:00:00:00:01:00"

    def test_coordenada_decimal(self, tmp_path: Path) -> None:
        c = escrever(tmp_path, ["02:00:00:00:01:00,CORP,36,5,-50,5.25,5.5,20"])
        assert ler_csv(c)[0].x == 5.25

    def test_le_o_csv_do_repositorio(self) -> None:
        for andar in ("andar1", "andar2", "andar3"):
            assert len(ler_csv(RAIZ / "dados" / f"varrimento-{andar}.csv")) > 0


class TestAgregar:
    """Agrupamento de medicoes em redes."""

    def test_agrupa_por_ssid_e_bssid(self) -> None:
        medicoes = [
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -50, 5, 5),
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -55, 10, 10),
        ]
        redes = agregar(medicoes)
        assert len(redes) == 1
        assert redes[0].rssi_medio == -52.5

    def test_ssids_diferentes_viram_redes(self) -> None:
        medicoes = [
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -50, 5, 5),
            Medicao("02:00:00:00:01:00", "GUEST", 36, "5", -50, 5, 5),
        ]
        assert len(agregar(medicoes)) == 2

    def test_ap_migrado_de_canal_preserva_os_dois(self) -> None:
        medicoes = [
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -50, 5, 5),
            Medicao("02:00:00:00:01:00", "CORP", 149, "5", -52, 10, 10),
        ]
        assert agregar(medicoes)[0].canais_ocupados == (36, 149)

    def test_vazio(self) -> None:
        assert agregar([]) == []

    def test_ordem_deterministica(self) -> None:
        medicoes = [
            Medicao("02:00:00:00:03:00", "C", 149, "5", -50, 5, 5),
            Medicao("02:00:00:00:01:00", "A", 36, "5", -50, 5, 5),
        ]
        assert [r.bssid for r in agregar(medicoes)] == [
            "02:00:00:00:01:00", "02:00:00:00:03:00"
        ]

    def test_rssi_max_e_min(self) -> None:
        redes = agregar([
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -40, 5, 5),
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -70, 10, 10),
        ])
        assert (redes[0].rssi_max, redes[0].rssi_min) == (-40, -70)

    def test_cobre_todo_a_area(self) -> None:
        rede = agregar([Medicao("02:00:00:00:01:00", "CORP", 36, "5", -50, 5, 5)])[0]
        assert rede.cobre_todo(30, 18)
        assert not rede.cobre_todo(3, 3)


class TestAssinatura:
    """A identidade do aparelho, em vez do radio."""

    def test_ignora_o_sextimo_octeto(self) -> None:
        assert (assinatura_do_equipamento("02:00:00:00:01:00")
                == assinatura_do_equipamento("02:00:00:00:01:01"))

    def test_distingue_aparelhos(self) -> None:
        assert (assinatura_do_equipamento("02:00:00:00:01:00")
                != assinatura_do_equipamento("02:00:00:00:02:00"))

    def test_aceita_guioes(self) -> None:
        assert assinatura_do_equipamento("02-00-00-00-01-00") == "02:00:00:00:01"

    def test_normaliza_maiusculas(self) -> None:
        assert assinatura_do_equipamento("02:00:00:00:0A:00") == "02:00:00:00:0a"

    def test_bssid_curto_nao_perde_info(self) -> None:
        assert assinatura_do_equipamento("02:00:00") == "02:00:00"


class TestAgruparAps:
    """Varios SSIDs e radios no mesmo aparelho."""

    def _rede(self, bssid: str, ssid: str, canal: int, banda: str) -> Rede:
        m = Medicao(bssid, ssid, canal, banda, -50, 5, 5)
        return Rede(ssid, bssid, canal, banda, 20, (m,))

    def test_une_os_radios_do_mesmo_ap(self) -> None:
        redes = [
            self._rede("02:00:00:00:01:00", "CORP", 1, "2.4"),
            self._rede("02:00:00:00:01:01", "CORP", 36, "5"),
        ]
        aps = agrupar_aps(redes)
        assert len(aps) == 1
        assert set(aps[0].bandas) == {"2.4", "5"}

    def test_une_varios_ssids_do_mesmo_radio(self) -> None:
        redes = [
            self._rede("02:00:00:00:01:00", "CORP", 36, "5"),
            self._rede("02:00:00:00:01:00", "GUEST", 36, "5"),
        ]
        assert len(agrupar_aps(redes)) == 1

    def test_por_radio_separa(self) -> None:
        redes = [
            self._rede("02:00:00:00:01:00", "CORP", 1, "2.4"),
            self._rede("02:00:00:00:01:01", "CORP", 36, "5"),
        ]
        assert len(agrupar_aps(redes, por_radio=True)) == 2

    def test_ap_separado_continua_separado(self) -> None:
        redes = [
            self._rede("02:00:00:00:01:00", "CORP", 36, "5"),
            self._rede("02:00:00:00:02:00", "CORP", 36, "5"),
        ]
        assert len(agrupar_aps(redes)) == 2

    def test_contagem_de_redes(self) -> None:
        redes = [self._rede("02:00:00:00:01:00", f"S{i}", 36, "5") for i in range(4)]
        assert agrupar_aps(redes)[0].n_redes == 4

    def test_canais_do_ap(self) -> None:
        redes = [
            self._rede("02:00:00:00:01:00", "CORP", 1, "2.4"),
            self._rede("02:00:00:00:01:01", "CORP", 36, "5"),
        ]
        assert agrupar_aps(redes)[0].canais == (1, 36)

    def test_ordem_deterministica(self) -> None:
        redes = [
            self._rede("02:00:00:00:02:00", "B", 36, "5"),
            self._rede("02:00:00:00:01:00", "A", 36, "5"),
        ]
        assert [a.bssid for a in agrupar_aps(redes)] == [
            "02:00:00:00:01", "02:00:00:00:02"
        ]

    def test_rssi_medio_do_ap(self) -> None:
        redes = [self._rede("02:00:00:00:01:00", "A", 36, "5"),
                 self._rede("02:00:00:00:01:00", "B", 36, "5")]
        assert agrupar_aps(redes)[0].rssi_medio == -50.0

    def test_lista_vazia(self) -> None:
        assert agrupar_aps([]) == []


class TestPosicao:
    """A posicao estimada do AP."""

    def test_ap_central(self) -> None:
        rede = agregar([
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -40, 12, 9),
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -40, 12, 9),
        ])[0]
        assert rede.posicao == (12.0, 9.0)

    def test_sinal_forte_puxa_a_posicao(self) -> None:
        # A leitura mais forte foi colada num canto; e para la que a posicao
        # estimada deve ir. Com o peso pelo valor absoluto do RSSI - que e
        # negativo - o resultado seria o oposto.
        rede = agregar([
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -30, 2, 2),
            Medicao("02:00:00:00:01:00", "CORP", 36, "5", -80, 20, 20),
        ])[0]
        x, y = rede.posicao
        assert x < 11 and y < 11

    def test_rede_sem_pontos(self) -> None:
        vazia = Rede("CORP", "02:00:00:00:01:00", 36, "5", 20, ())
        assert vazia.posicao == (0.0, 0.0)
        assert vazia.rssi_medio == 0.0
        assert vazia.rssi_max == 0
        assert vazia.canais_ocupados == ()


class TestCarregar:
    """A leitura de ponta a ponta."""

    def test_carrega_o_andar1(self) -> None:
        aps = carregar(RAIZ / "dados" / "varrimento-andar1.csv")
        assert len(aps) > 0
        assert all(isinstance(a, AccessPoint) for a in aps)

    def test_todos_os_apis_dual_band(self) -> None:
        for andar in ("andar1", "andar2", "andar3"):
            aps = carregar(RAIZ / "dados" / f"varrimento-{andar}.csv")
            assert all(a.bandas_2g and a.bandas_5g for a in aps), andar

    def test_saida_deterministica(self) -> None:
        a = carregar(RAIZ / "dados" / "varrimento-andar1.csv")
        b = carregar(RAIZ / "dados" / "varrimento-andar1.csv")
        assert [x.bssid for x in a] == [x.bssid for x in b]

    def test_carregar_andares_mensagem(self) -> None:
        with pytest.raises(CsvInvalido) as exc:
            carregar_andares(RAIZ / "dados" / "nao-existe.csv", "andar9")
        assert "andar9" in str(exc.value)

    def test_carregar_andares_ok(self) -> None:
        aps = carregar_andares(RAIZ / "dados" / "varrimento-andar1.csv", "andar1")
        assert len(aps) > 0


class TestCli:
    """A linha de comando."""

    def test_relatorio_do_andar1(self, tmp_path: Path, capsys) -> None:
        saida = tmp_path / "r.html"
        codigo = main([
            "relatorio", str(RAIZ / "dados" / "varrimento-andar1.csv"),
            "--dados", str(RAIZ / "dados"),
            "--parametros", str(RAIZ / "dados" / "capacidade.yaml"),
            "--planta", str(RAIZ / "dados" / "planta-andar1.svg"),
            "--saida", str(saida),
        ])
        assert codigo == 0
        assert saida.exists()
        assert "APs fisicos" in capsys.readouterr().out

    def test_relatorio_gera_png(self, tmp_path: Path) -> None:
        png = tmp_path / "m.png"
        codigo = main([
            "relatorio", str(RAIZ / "dados" / "varrimento-andar1.csv"),
            "--dados", str(RAIZ / "dados"),
            "--saida", str(tmp_path / "r.html"),
            "--png", str(png),
        ])
        assert codigo == 0
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_andar_inferido_do_nome(self, tmp_path: Path) -> None:
        codigo = main([
            "relatorio", str(RAIZ / "dados" / "varrimento-andar2.csv"),
            "--dados", str(RAIZ / "dados"),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 0

    def test_andar_explicito(self, tmp_path: Path) -> None:
        codigo = main([
            "relatorio", "--andar", "andar3",
            "--dados", str(RAIZ / "dados"),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 0

    def test_andar_inexistente(self, tmp_path: Path) -> None:
        codigo = main([
            "relatorio", "--andar", "andar99",
            "--dados", str(RAIZ / "dados"),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 2

    def test_planta_de_outro_andar(self, tmp_path: Path, capsys) -> None:
        codigo = main([
            "relatorio", "--andar", "andar1",
            "--dados", str(RAIZ / "dados"),
            "--planta", str(RAIZ / "dados" / "planta-andar2.svg"),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 2
        assert "andar1" in capsys.readouterr().err

    def test_planta_inexistente(self, tmp_path: Path) -> None:
        codigo = main([
            "relatorio", "--andar", "andar1",
            "--dados", str(RAIZ / "dados"),
            "--planta", str(tmp_path / "nao-existe.svg"),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 2

    def test_planta_sem_viewbox(self, tmp_path: Path) -> None:
        planta = tmp_path / "planta-andar1.svg"
        planta.write_text("<svg></svg>", encoding="utf-8")
        codigo = main([
            "relatorio", "--andar", "andar1",
            "--dados", str(RAIZ / "dados"),
            "--planta", str(planta),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 2

    def test_csv_com_cabecalho_ruim(self, tmp_path: Path, capsys) -> None:
        c = escrever(tmp_path, ["lixo,nao,e,csv,mas,sim,6,7"])
        codigo = main([
            "relatorio", str(c), "--dados", str(RAIZ / "dados"),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 2
        assert "Erro" in capsys.readouterr().err

    def test_cria_diretorio_de_saida(self, tmp_path: Path) -> None:
        destino = tmp_path / "a" / "b" / "r.html"
        codigo = main([
            "relatorio", "--andar", "andar1",
            "--dados", str(RAIZ / "dados"), "--saida", str(destino),
        ])
        assert codigo == 0
        assert destino.exists()

    def test_saida_e_utf8_valida(self, tmp_path: Path) -> None:
        saida = tmp_path / "r.html"
        main([
            "relatorio", "--andar", "andar1",
            "--dados", str(RAIZ / "dados"), "--saida", str(saida),
        ])
        saida.read_bytes().decode("utf-8")

    def test_relatorio_e_deterministico(self, tmp_path: Path) -> None:
        primeira, segunda = tmp_path / "a.html", tmp_path / "b.html"
        for destino in (primeira, segunda):
            main([
                "relatorio", "--andar", "andar1",
                "--dados", str(RAIZ / "dados"), "--saida", str(destino),
            ])
        assert primeira.read_bytes() == segunda.read_bytes()

    def test_comparar(self, capsys) -> None:
        codigo = main(["comparar", "--dados", str(RAIZ / "dados")])
        assert codigo == 0
        saida = capsys.readouterr().out
        for andar in ("andar1", "andar2", "andar3"):
            assert andar in saida

    def test_comparar_andares_especificos(self, capsys) -> None:
        main(["comparar", "--dados", str(RAIZ / "dados"), "--andares", "andar3"])
        saida = capsys.readouterr().out
        assert "andar3" in saida
        assert "andar1" not in saida

    def test_comparar_andar_inexistente(self) -> None:
        assert main([
            "comparar", "--dados", str(RAIZ / "dados"), "--andares", "andar99"
        ]) == 2

    def test_canais(self, capsys) -> None:
        assert main(["canais"]) == 0
        saida = capsys.readouterr().out
        assert "1, 6, 11" in saida
        assert "149" in saida

    def test_canais_valida_um_valido(self, capsys) -> None:
        assert main(["canais", "--banda", "5", "--canal", "149"]) == 0
        assert "valido" in capsys.readouterr().out

    def test_canais_reprova_um_invalido(self, capsys) -> None:
        assert main(["canais", "--banda", "5", "--canal", "70"]) == 1
        assert "INVALIDO" in capsys.readouterr().out

    def test_ajuda(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_ajuda_do_subcomando(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["relatorio", "--help"])
        assert exc.value.code == 0

    def test_sem_subcomando(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code != 0

    def test_subcomando_desconhecido(self) -> None:
        with pytest.raises(SystemExit):
            main(["inventado"])

    def test_parser_tem_os_tres_subcomandos(self) -> None:
        parser = construir_parser()
        for sub in ("relatorio", "comparar", "canais"):
            args = parser.parse_args([sub] if sub == "canais" else [sub, "--saida", "x"]
                                     if sub == "relatorio" else [sub])
            assert args.func is not None

    def test_parametros_invalidos(self, tmp_path: Path) -> None:
        ruim = tmp_path / "ruim.yaml"
        ruim.write_text("capacidade:\n  '5':\n    '20': 0\n", encoding="utf-8")
        codigo = main([
            "relatorio", "--andar", "andar1",
            "--dados", str(RAIZ / "dados"),
            "--parametros", str(ruim),
            "--saida", str(tmp_path / "r.html"),
        ])
        assert codigo == 2
