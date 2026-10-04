"""Testa o marcador que o conferir_exemplos.py usa para comparar relatorios.

Por que este teste existe

O `conferir_exemplos.py` compara o relatorio de cada andar com a versao no
HEAD, para reprovar quando o exemplo versionado deixa de bater com o codigo.
O problema: o mapa de calor esta embutido no HTML como `data URI`, e o bloco
IDAT do PNG e comprimido com zlib. A zlib 1.3 do CPython 3.11 e a zlib-ng do
CPython 3.14 comprimem o mesmo PNG para tamanhos diferentes, entao o base64
embutido tem comprimento diferente em cada uma.

A primeira versao do comparador trocava o base64 por um marcador que carregava
o **tamanho** dele. O resultado era que a comparacao media justamente o ruido
que existe para descartar, e reprovava nos dois runners com o exemplo correto.

O marcador agora e fixo. Este teste trava o contrato nos dois sentidos:

1. dois relatorios com binarios de tamanhos diferentes tem que ser iguais
   depois do marcador, porque a diferenca e so do compressor;
2. dois relatorios cujo texto difere tem que continuar diferentes, senao a
   verificacao de exemplo desatualizado deixa de funcionar.

O segundo teste e o que impede que o conserto vire uma tolerancia que engole
erro de verdade.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# carrega o modulo do tools/, que nao e pacote
_esp = importlib.util.spec_from_file_location(
    "conferir_exemplos", RAIZ / "tools" / "conferir_exemplos.py")
assert _esp and _esp.loader, "tools/conferir_exemplos.py nao encontrado"
ce = importlib.util.module_from_spec(_esp)
_esp.loader.exec_module(ce)

MODELO = (
    '<div class="mapa"><img src="data:image/png;base64,{b64}" '
    'alt="Mapa de calor de RSSI do andar1" width="640"></div>'
    '<h1>andar1</h1><p>1650 medicoes, 11 APs fisicos.</p>'
)

# os dois comprimentos que a zlib 1.3 e a zlib-ng produzem para o mesmo mapa
B64_ZLIB_CLASSICA = "A" * 24714
B64_ZLIB_NG = "B" * 24774


def test_binario_diferente_nao_reprova() -> None:
    """Mesmo relatorio, PNG comprimido diferente: tem que passar."""
    a = ce.sem_binario(MODELO.format(b64=B64_ZLIB_CLASSICA))
    b = ce.sem_binario(MODELO.format(b64=B64_ZLIB_NG))
    assert a == b, "a diferenca de tamanho do base64 esta reprovando a comparacao"
    assert ce.MARCADOR_PNG in a, "o marcador fixo nao entrou no relatorio"


def test_texto_diferente_reprova() -> None:
    """Relatorio com texto diferente: tem que reprovar, mesmo com PNG igual."""
    antes = ce.sem_binario(MODELO.format(b64=B64_ZLIB_CLASSICA))
    depois = ce.sem_binario(
        MODELO.format(b64=B64_ZLIB_NG).replace(
            "1650 medicoes", "9999 medicoes"))
    assert antes != depois, "texto diferente passou, e o exemplo desatualizado nao reprova"


def test_marcador_nao_carrega_tamanho() -> None:
    """A parte do marcador depois da virgula nao pode ter digito.

    O prefixo `data:image/png;base64,` tem digito por definicao do formato.
    O que nao pode ter e numero no lugar do conteudo: e o tamanho do PNG que
    difere entre a zlib 1.3 e a zlib-ng.
    """
    cauda = ce.MARCADOR_PNG.split(",", 1)[-1]
    assert not any(c.isdigit() for c in cauda), (
        f"o marcador carrega numero no conteudo: {cauda!r}")
    assert "bytes" not in cauda, (
        f"o marcador ainda escreve o tamanho em bytes: {cauda!r}")


def test_data_uri_completa_e_removida() -> None:
    """Nada do base64 pode sobrar no relatorio comparado."""
    saida = ce.sem_binario(MODELO.format(b64=B64_ZLIB_NG))
    assert "A" * 50 not in saida and "B" * 50 not in saida, "base64 sobrou no texto"
    assert ce.DATA_URI.search(saida) is None, "a data URI nao foi substituida"