"""CLI do wifisurvey - relatorio de varredura Wi-Fi por andar.

CLI for wifisurvey - per-floor Wi-Fi survey report.

Um subcomando por andar, e um ``comparar`` para ver os tres de uma vez, porque
e assim que o cliente pergunta: "os tres andares estao bons?".

O relatorio e HTML autocontido: o mapa vai embutido como data URI, entao o
arquivo abre com duplo clique, sem servidor, sem pasta de imagens ao lado e
sem internet. Um relatorio que depende de ``mapa.png`` na mesma pasta quebre
na hora em que alguem manda por e-mail.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .capacidade import (
    Parametros,
    ParametrosInvalidos,
    dimensionar,
    verifica_projeto,
)
from .interferencia import (
    canais_validos,
    canal_recomendado,
    conflito_de_canal,
    indices_de_conflito,
)
from .leitor import CsvInvalido, carregar
from .mapa import _png_data_uri, escrever_png, gerar_relatorio
from .plano import AccessPoint


# Andares que o comando ``comparar`` cobre por padrao.
ANDARES_PADRAO = ("andar1", "andar2", "andar3")

# Area e populacao de cada andar do projeto de exemplo. Ficticias.
METRAGEM = {
    "andar1": (540.0, 60),
    "andar2": (540.0, 45),
    "andar3": (540.0, 90),
}


class DadosInvalidos(ValueError):
    """Os dados de entrada do comando nao servem para o calculo."""


def _carga_do_andar(
    andar: str,
    dados: Path,
    params: Parametros,
) -> tuple[list[AccessPoint], object, list[str]]:
    """Carrega um andar e calcula dimensionamento e problemas.

    Load one floor and compute sizing and problems.

    Args:
        andar: Nome do andar.
        dados: Diretorio de dados.
        params: Parametros de projeto.

    Returns:
        Tupla ``(aps, dimensionamento, problemas)``.

    Raises:
        DadosInvalidos: Se o CSV do andar nao existir.
    """
    csv = dados / f"varrimento-{andar}.csv"
    if not csv.exists():
        raise DadosInvalidos(f"CSV do {andar} nao encontrado: {csv}")

    aps = carregar(csv)
    largura_m, altura_m = 30.0, 18.0
    area = largura_m * altura_m
    populacao = METRAGEM.get(andar, (0, 0))[1]

    dim = dimensionar(aps, area, populacao, params)
    return aps, dim, verifica_projeto(aps, params)


def _canais(aps: list[AccessPoint]) -> tuple[list[int], list[int]]:
    """Separa os canais em uso por banda.

    Split the channels in use by band.
    """
    c24 = sorted({r.canal for a in aps for r in a.redes if r.banda == "2.4"})
    c5 = sorted({r.canal for a in aps for r in a.redes if r.banda == "5"})
    return c24, c5


def _html_do_andar(andar: str, dados: Path, params: Parametros) -> str:
    """Monta o HTML de um andar.

    Build one floor's HTML.
    """
    aps, dim, problemas = _carga_do_andar(andar, dados, params)
    c24, c5 = _canais(aps)

    return gerar_relatorio(
        andar=andar,
        aps=aps,
        largura_m=30.0,
        altura_m=18.0,
        populacao=dim.clientes,
        dimensao=dim,
        problemas=problemas,
        conflitos=indices_de_conflito(aps),
        conflito_canais=conflito_de_canal([r for a in aps for r in a.redes]),
        canais_24=c24,
        canais_5=c5,
        recomendado_24=canal_recomendado("2.4", 20, c24),
        recomendado_5=canal_recomendado("5", 20, c5),
        planta_png=_png_data_uri(aps, 30.0, 18.0),
    )


def _cmd_relatorio(args: argparse.Namespace) -> int:
    """Gera o relatorio de um andar.

    Generate one floor's report.

    Returns:
        0 em sucesso.
    """
    params = Parametros.carregar(args.parametros) if args.parametros else Parametros()
    andar = args.andar or _andar_do_csv(args.csv)

    planta = _conferir_planta(args.planta, andar)

    html = _html_do_andar(andar, Path(args.dados), params)

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")

    aps, dim, problemas = _carga_do_andar(andar, Path(args.dados), params)
    c24, c5 = _canais(aps)

    print(
        f"Andar: {andar}\n"
        f"  APs fisicos: {len(aps)} "
        f"({sum(a.n_redes for a in aps)} redes logicas agrupadas por BSSID)\n"
        f"  RSSI medio: {sum(a.rssi_medio for a in aps) / max(1, len(aps)):.1f} dBm\n"
        f"  Canais 2.4 GHz em uso: {', '.join(str(c) for c in c24) or 'nenhum'}"
        f" -> recomendado {canal_recomendado('2.4', 20, c24)}\n"
        f"  Canais 5 GHz em uso: {', '.join(str(c) for c in c5) or 'nenhum'}"
        f" -> recomendado {canal_recomendado('5', 20, c5)}\n"
        f"  Dimensionamento: {dim.resumo()}\n"
        f"  Problemas: {len(problemas)}"
    )
    for p in problemas:
        print(f"    - {p}")

    if args.png:
        bytes_escritos = escrever_png(args.png, aps, 30.0, 18.0, escala_px=14)
        print(f"  PNG do mapa: {args.png} ({bytes_escritos} bytes)")

    print(f"  Relatorio: {destino}")
    if planta:
        print(f"  Planta conferida: {planta}")
    return 0


def _conferir_planta(planta: str | None, andar: str) -> str | None:
    """Confere se a planta pertence ao andar do CSV.

    Check that the floor plan belongs to the floor of the CSV.

    Passar a planta de outro andar e o erro mais facil de cometer na hora de
    montar o relatorio: o mapa sai bonito e os APs aparecem fora do lugar. A
    checagem e pelo nome do arquivo, que precisa conter o andar.

    Args:
        planta: Caminho da planta, opcional.
        andar: Andar esperado.

    Returns:
        O caminho conferido, ou ``None`` se nada foi passado.

    Raises:
        DadosInvalidos: Se a planta nao existir, se for de outro andar, ou se
            nao tiver viewBox de onde ler as dimensoes.
    """
    if not planta:
        return None

    caminho = Path(planta)
    if not caminho.exists():
        raise DadosInvalidos(f"planta nao encontrada: {caminho}")

    if andar not in caminho.stem:
        raise DadosInvalidos(
            f"planta {caminho.name} nao e do {andar}: "
            "o nome do arquivo nao bate com o andar do CSV"
        )

    if "viewBox" not in caminho.read_text(encoding="utf-8"):
        raise DadosInvalidos(
            f"planta {caminho.name} sem viewBox: nao da para ler as dimensoes"
        )

    return str(caminho)


def _andar_do_csv(caminho: str) -> str:
    """Deduz o nome do andar a partir do nome do arquivo.

    Infer the floor name from the file name.
    """
    nome = Path(caminho).stem
    if nome.startswith("varrimento-"):
        return nome[len("varrimento-"):]
    return nome


def _cmd_comparar(args: argparse.Namespace) -> int:
    """Compara os andares em uma tabela.

    Compare the floors in one table.
    """
    params = Parametros.carregar(args.parametros) if args.parametros else Parametros()
    dados = Path(args.dados)

    print(f"{'andar':<9}{'APs':>5}{'redes':>7}{'RSSI medio':>12}"
          f"{'necessarios':>13}{'capacidade':>12}  veredito")

    for andar in args.andares:
        aps, dim, _problemas = _carga_do_andar(andar, dados, params)
        medio = sum(a.rssi_medio for a in aps) / max(1, len(aps))
        print(
            f"{andar:<9}{len(aps):>5}{sum(a.n_redes for a in aps):>7}"
            f"{medio:>10.1f} dBm{dim.aps_necessarios:>13}"
            f"{dim.capacidade_total:>12}  {dim.resumo()}"
        )
    return 0


def _cmd_canais(args: argparse.Namespace) -> int:
    """Lista os canais validos e valida um canal escolhido.

    List valid channels and validate a chosen one.
    """
    for banda in ("2.4", "5"):
        c = canais_validos(banda)
        print(f"{banda:>4} GHz: {', '.join(str(x) for x in c)}")
        print(f"        {len(c)} canais de 20 MHz sem sobreposicao entre si")

    if args.canal is not None:
        ok = args.canal in canais_validos(args.banda)
        print(
            f"\ncanal {args.canal} em {args.banda} GHz: "
            f"{'valido' if ok else 'INVALIDO para projeto'}"
        )
        return 0 if ok else 1
    return 0


def construir_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos.

    Build the argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="wifisurvey",
        description=(
            "Analisa varredura de Wi-Fi, monta mapa de calor por andar, "
            "dimensiona access points e aponta conflito de canal. "
            "Analyses a Wi-Fi survey, builds a per-floor heatmap, sizes access "
            "points and flags channel conflicts."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_rel = sub.add_parser("relatorio", help="Gera o relatorio HTML de um andar.")
    p_rel.add_argument("csv", nargs="?", help="CSV do andar. Opcional: infere do nome.")
    p_rel.add_argument("--andar", help="Nome do andar. Ex.: andar1")
    p_rel.add_argument("--dados", default="dados", help="Diretorio de dados.")
    p_rel.add_argument("--parametros", help="YAML de capacidade e criterios.")
    p_rel.add_argument("--planta", help=(
        "Planta SVG do andar. Conferida contra as medicoes do CSV: se a "
        "planta for de outro andar, os APs medidos nao batem com as "
        "dimensoes e o mapa sai errado."
    ))
    p_rel.add_argument("--saida", default="exemplos/relatorio-andar1.html",
                       help="Caminho do HTML de saida.")
    p_rel.add_argument("--png", help="Caminho de um PNG do mapa de calor.")
    p_rel.set_defaults(func=_cmd_relatorio)

    p_cmp = sub.add_parser("comparar", help="Compara os andares em uma tabela.")
    p_cmp.add_argument("--dados", default="dados", help="Diretorio de dados.")
    p_cmp.add_argument("--parametros", help="YAML de capacidade e criterios.")
    p_cmp.add_argument("--andares", nargs="+", default=list(ANDARES_PADRAO),
                       help="Andares a comparar.")
    p_cmp.set_defaults(func=_cmd_comparar)

    p_can = sub.add_parser("canais", help="Lista os canais validos por banda.")
    p_can.add_argument("--banda", default="5", choices=["2.4", "5"], help="Banda.")
    p_can.add_argument("--canal", type=int, help="Valida este canal na banda.")
    p_can.set_defaults(func=_cmd_canais)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    CLI entry point.
    """
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (CsvInvalido, DadosInvalidos, ParametrosInvalidos, OSError) as exc:
        print(f"Erro / error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
