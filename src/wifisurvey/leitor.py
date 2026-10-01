"""Leitura do CSV de varrimento de Wi-Fi.

Reading a Wi-Fi site survey CSV. Uma varredura real sai do analisador como uma
linha por rede vista por ponto de medicao. Este modulo transforma essas linhas
em objetos ``Rede`` agregados e ``AccessPoint`` agrupados por BSSID.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .plano import AccessPoint, Medicao, Rede, agrupar_aps


# Cabecalho exigido. As colunas sao as mesmas que um analisador exporta, com
# nomes em ingles porque o formato vem do equipamento.
COLUNAS = ("bssid", "ssid", "canal", "banda", "rssi", "x", "y", "largura_canal")
COLUNAS_OBRIGATORIAS = ("bssid", "ssid", "canal", "banda", "rssi", "x", "y")


class CsvInvalido(ValueError):
    """O CSV nao tem o formato de varredura esperado."""

    def __init__(self, mensagem: str, linha: int | None = None) -> None:
        super().__init__(mensagem if linha is None else f"linha {linha}: {mensagem}")
        self.linha = linha


def _normalizar_banda(bruto: str) -> str:
    """Converte a banda escrita no CSV para ``2.4`` ou ``5``.

    Convert the band written in the CSV to ``2.4`` or ``5``.

    Aceita as grafias que aparecem em exportacao real: ``2.4``, ``2.4G``,
    ``2,4`` e ``2400MHz`` sao a mesma banda; ``5G`` e ``5000MHz`` tambem.

    Args:
        bruto: Texto como veio do CSV.

    Returns:
        ``2.4`` ou ``5``.

    Raises:
        CsvInvalido: Se a banda nao for reconhecida.
    """
    t = bruto.strip().lower().replace(",", ".").replace("ghz", "").replace("g", "")
    t = t.replace("mhz", "").strip()

    if t.startswith("2.4") or t in ("24", "2400"):
        return "2.4"
    if t.startswith("5") or t in ("50", "5000"):
        return "5"
    raise CsvInvalido(f"banda nao reconhecida: {bruto!r}")


def ler_csv(caminho: str | Path) -> list[Medicao]:
    """Le um CSV de varrimento e devolve as medicoes.

    Read a survey CSV and return the measurements.

    Args:
        caminho: Caminho do arquivo CSV.

    Returns:
        Uma medicao por linha de dados.

    Raises:
        CsvInvalido: Se faltar coluna obrigatoria, se um numero nao
            convergir ou se o arquivo estiver sem cabecalho.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise CsvInvalido(f"arquivo nao encontrado: {caminho}")

    with caminho.open(newline="", encoding="utf-8") as fh:
        leitor = csv.DictReader(fh)

        if leitor.fieldnames is None:
            raise CsvInvalido("arquivo sem cabecalho")

        faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in leitor.fieldnames]
        if faltando:
            raise CsvInvalido(f"colunas obrigatorias faltando: {', '.join(faltando)}")

        medicoes: list[Medicao] = []
        for numero, linha in enumerate(leitor, start=2):
            if not (linha.get("bssid") or "").strip():
                continue

            try:
                canal = int(linha["canal"])
                rssi = int(linha["rssi"])
                x = float(linha["x"])
                y = float(linha["y"])
            except (TypeError, ValueError) as exc:
                raise CsvInvalido(f"valor nao numerico ({exc})", numero) from exc

            largura = 20
            if (linha.get("largura_canal") or "").strip():
                try:
                    largura = int(linha["largura_canal"])
                except (TypeError, ValueError) as exc:
                    raise CsvInvalido("largura_canal nao numerica", numero) from exc

            try:
                banda = _normalizar_banda(linha["banda"])
            except CsvInvalido as exc:
                raise CsvInvalido(str(exc), numero) from exc

            medicoes.append(
                Medicao(
                    bssid=linha["bssid"].strip().lower(),
                    ssid=(linha.get("ssid") or "").strip() or "<oculto>",
                    canal=canal,
                    banda=banda,
                    rssi=rssi,
                    x=x,
                    y=y,
                    largura_canal=largura,
                )
            )

    return medicoes


def agregar(medicoes: list[Medicao]) -> list[Rede]:
    """Agrega medicoes em redes logicas, por BSSID e SSID.

    Aggregate measurements into logical networks, by BSSID and SSID.

    Uma rede pode ser medida em varios pontos e em varios canais - um AP que
    migra de canal durante a varredura aparece com dois. Agregar por SSID
    separado mantem essa migracao visivel em ``canais_ocupados``, em vez de
    escolher um canal e esconder o outro.

    Args:
        medicoes: Medicoes vindas do CSV.

    Returns:
        Redes agregadas, ordenadas por BSSID e SSID.
    """
    grupos: dict[tuple[str, str], list[Medicao]] = {}
    for med in medicoes:
        grupos.setdefault((med.bssid, med.ssid), []).append(med)

    redes: list[Rede] = []
    for (bssid, ssid), pontos in grupos.items():
        principal = pontos[0]
        redes.append(
            Rede(
                ssid=ssid,
                bssid=bssid,
                canal=principal.canal,
                banda=principal.banda,
                largura_canal=principal.largura_canal,
                pontos=tuple(sorted(pontos, key=lambda p: (p.x, p.y))),
            )
        )

    return sorted(redes, key=lambda r: (r.banda, r.canal, r.bssid, r.ssid))


def carregar(caminho: str | Path) -> list[AccessPoint]:
    """Le um CSV e devolve os APs fisicos agrupados por BSSID.

    Read a CSV and return the physical APs grouped by BSSID.

    Args:
        caminho: Caminho do arquivo CSV.

    Returns:
        APs fisicos ordenados por BSSID.
    """
    return agrupar_aps(agregar(ler_csv(caminho)))


def carregar_andares(
    caminho: str | Path,
    andar: str,
) -> list[AccessPoint]:
    """Le o CSV de um andar especifico.

    Read the CSV of one floor.

    Args:
        caminho: Caminho do arquivo CSV.
        andar: Identificador do andar, para mensagens.

    Returns:
        APs do andar.

    Raises:
        CsvInvalido: Se o arquivo nao existir.
    """
    try:
        return carregar(caminho)
    except CsvInvalido as exc:
        raise CsvInvalido(f"andar {andar}: {exc}", getattr(exc, "linha", None)) from exc
