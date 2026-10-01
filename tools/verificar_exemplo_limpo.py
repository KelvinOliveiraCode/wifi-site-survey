#!/usr/bin/env python
"""Confere que os exemplos versionados nao carregam caminho local.

Check that the committed examples carry no local filesystem paths.

Um relatorio que vai para commit e para issue de ticket nao pode conter o
caminho de quem o gerou: estraga a revisao do diff e ainda entrega informacao da
maquina de desenvolvimento de qualquer pessoa que clona o repositorio.

O HTML e gerado a partir de dados, entao um caminho so entraria por bug no
codigo - que e exatamente o que este script existe para pegar.

Exit code 0 = nenhum caminho local encontrado.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXEMPLOS = RAIZ / "exemplos"

# Caminho de usuario do Windows, home de Unix e a propria variavel de ambiente.
MARCAS = (
    "C:\\Users",
    "C:/Users",
    "D:\\Users",
    "/Users/",
    "/home/",
    "AppData",
    "%USERPROFILE%",
    "TEMP",
)

# Caminho absoluto de Windows solto, como C:\qualquer\coisa.
PADRAO_WINDOWS = re.compile(r"[A-Za-z]:\\\\?[A-Za-z0-9_.-]+[\\\\/]")


def auditar(caminho: Path) -> list[str]:
    """Lista os caminhos locais encontrados em um exemplo.

    List local paths found in one example.

    Args:
        caminho: Caminho do exemplo.

    Returns:
        Lista de descricoes, vazia se o arquivo estiver limpo.
    """
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    problemas: list[str] = []

    for marca in MARCAS:
        if marca in texto:
            numero = texto.count(marca)
            problemas.append(f"{marca!r} aparece {numero} vez(es)")

    achados = PADRAO_WINDOWS.findall(texto)
    if achados:
        problemas.append(f"caminho absoluto de Windows: {sorted(set(achados))}")

    return problemas


def main() -> int:
    """Percorre os exemplos do repositorio.

    Walk the repository examples.

    Returns:
        0 se todos estiverem limpos, 1 caso contrario.
    """
    if not EXEMPLOS.exists():
        print(f"erro: diretorio de exemplos ausente: {EXEMPLOS}")
        return 1

    arquivos = sorted(p for p in EXEMPLOS.iterdir() if p.is_file())
    if not arquivos:
        print(f"erro: nenhum exemplo em {EXEMPLOS}")
        return 1

    falhas: list[str] = []
    for caminho in arquivos:
        problemas = auditar(caminho)
        if problemas:
            falhas.append(f"{caminho.name}:")
            falhas.extend(f"    {p}" for p in problemas)

    if falhas:
        print("caminho local encontrado nos exemplos:")
        print("\n".join(falhas))
        return 1

    nomes = ", ".join(p.name for p in arquivos)
    print(f"exemplos limpos ({len(arquivos)} arquivo(s)): {nomes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
