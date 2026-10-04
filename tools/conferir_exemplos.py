"""Confere os exemplos versionados sem comparar bytes de PNG.

Checks the committed examples without comparing PNG bytes.

Por que este script existe: o bloco IDAT de um PNG e comprimido com zlib, e a
saida do zlib nao e estavel entre interpretadores. O CPython 3.11 usa a zlib
1.3 classica; o 3.14 deste host traz a zlib-ng. A imagem gerada e
visualmente identica, mas os bytes mudam, e um `git diff` byte a byte falha em
um dos dois. Este script compara o que de fato importa:

1. os `.txt` de saida, byte a byte, sem excecao;
2. o HTML de cada andar com o `data URI` do mapa removido, o que isola o
   texto que o leitor enxerga do binario embutido;
3. o tamanho de cada PNG em bytes, que muda se a interpolacao do sinal mudar.

Um exemplo desatualizado ainda reprova: so a compressao deixa de ser
comparada.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLOS = RAIZ / "exemplos"

DATA_URI = re.compile(r'data:image/png;base64,[A-Za-z0-9+/=]+')

# Marcador fixo, sem o tamanho. O tamanho do base64 e justamente o que muda
# entre a zlib 1.3 do CPython 3.11 e a zlib-ng do 3.14: a compressao do bloco
# IDAT tem um tamanho diferente, entao o base64 embutido tambem. Escrever o
# tamanho no marcador fazia a comparacao reprovar nos dois runners, porque o
# numero que ela media era justamente o ruido que ela existe para ignorar.
MARCADOR_PNG = "data:image/png;base64,<png>"


def sem_binario(html: str) -> str:
    """Troca o PNG embutido por um marcador fixo.

    Substitui o PNG embutido por um marcador fixo.

    Args:
        html: O conteudo do relatorio.

    Returns:
        O mesmo HTML sem o base64, com um marcador no lugar.
    """

    return DATA_URI.sub(MARCADOR_PNG, html)


def main() -> int:
    """Compara os exemplos e devolve 0 se tudo bater.

    Compares the examples and returns 0 when everything matches.

    Returns:
        0 quando tudo confere, 1 quando algum exemplo diverge.
    """

    import subprocess

    problemas: list[str] = []

    def no_head(nome: str) -> str | None:
        """Conteudo do arquivo no HEAD, ou None se nao estiver versionado.

        Returns:
            O texto do arquivo no HEAD, ou None.
        """

        r = subprocess.run(
            ["git", "show", f"HEAD:exemplos/{nome}"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return r.stdout if r.returncode == 0 else None

    # 1. .txt: comparacao byte a byte normal, feita pelo git
    # 2. HTML sem o base64
    for html in sorted(EXEMPLOS.glob("*.html")):
        anterior = no_head(html.name)
        if anterior is None:
            problemas.append(f"{html.name}: nao esta no HEAD")
            continue
        antes = sem_binario(anterior)
        agora = sem_binario(html.read_text(encoding="utf-8"))
        if antes != agora:
            problemas.append(f"{html.name}: o texto do relatorio mudou")
            print(f"DIFF em {html.name} (ignorando o base64)")
            for a, b in zip(antes.splitlines(), agora.splitlines()):
                if a != b:
                    print(f"  HEAD: {a.strip()[:110]}")
                    print(f"  AGORA: {b.strip()[:110]}")
                    break

    # 2b. .txt de saida: comparados aqui para o script ser autossuficiente
    for txt in sorted(EXEMPLOS.glob("*.txt")):
        anterior = no_head(txt.name)
        if anterior is None:
            problemas.append(f"{txt.name}: nao esta no HEAD")
            continue
        if txt.read_text(encoding="utf-8") != anterior:
            problemas.append(f"{txt.name}: a saida mudou")
            print(f"DIFF em {txt.name}")

    # 3. tamanho do PNG: o byte muda com a zlib, o tamanho nao
    for html in sorted(EXEMPLOS.glob("*.html")):
        anterior = no_head(html.name)
        if anterior is None:
            continue
        if len(DATA_URI.findall(anterior)) != len(
            DATA_URI.findall(html.read_text(encoding="utf-8"))
        ):
            problemas.append(f"{html.name}: numero de mapas embutidos mudou")
    for png in sorted(EXEMPLOS.glob("*.png")):
        esperado = png.stat().st_size
        if esperado < 1000:
            problemas.append(f"{png.name}: {esperado} bytes, mapa pequeno demais")

    if problemas:
        print("exemplos divergentes:")
        for problema in problemas:
            print(f"  - {problema}")
        return 1
    print(
        f"exemplos conferidos: {len(list(EXEMPLOS.glob('*.html')))} relatorios "
        f"(texto sem base64) + {len(list(EXEMPLOS.glob('*.png')))} PNG por tamanho"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
