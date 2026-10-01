#!/usr/bin/env python
"""Confere o encoding dos arquivos de texto do repositorio.

Check the encoding of the repository's text files.

Motivo: neste host ja surgiram ideogramas CJK acidentais em arquivos escritos
com acento. Nao sao erro de logica: sao corrupcao de encoding, que passa
despercebida, muda o conteudo e contamina o repositorio. Um `dano` com acento
circonflexo vira outra palavra; um CJK num doc vira lixo que ninguem sabe de
onde veio.

Por isso o gate e por **tipo de arquivo**, com regra diferente para codigo e
para documentacao:

- ``.py``, ``.json``, ``.yaml``, ``.yml``, ``.toml``, ``.cfg``, ``.txt`` sao
  ASCII puro. Nao e purismo: sao arquivos que o CI le, que um diff mostra e
  que um terminal Windows em CP850 pode truncar. Um acento em ``.py`` e um
  risco operacional sem ganho nenhum - o codigo fala ingles e os comments
  ficam sem acento.
- ``.md`` aceita acento PT-BR e matematica (m2, sinal de menos, menor-igual),
  porque documentacao existe para ser lida em portugues. CJK continua proibido
  em qualquer arquivo.

Exit code 0 = tudo limpo.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Extensoes que precisam ser ASCII puro.
ASCII_PURO = {".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".txt"}

# Extensoes que aceitam PT-BR acentuado.
DOCUMENTACAO = {".md"}

# Caracteres nao-alfabeticos aceitos em Markdown: matematica, pontuacao e a
# tipografia que a documentacao em portugues usa.
PERMITIDOS_MD = set(
    "\u00b0\u00b2\u00b3\u00ba"       # grau, quadrado, cubico, ordinal (3o andar)
    "\u00d7\u2212\u2248"            # vezes, menos, aproximadamente
    "\u2264\u2265\u2260"            # menor-igual, maior-igual, diferente
    "\u2013\u2014"                  # travessao e meia-pontua
    "\u2018\u2019\u201c\u201d"      # aspas tipograficas
    "\u2026"                        # reticencias
)

# Desenho de caixas (U+2500 a U+257F): as arvores de diretorio dos README e os
# separadores de secao das docs usam estes caracteres, que renderizam em
# qualquer Markdown.
INICIO_CAIXAS = 0x2500
FIM_CAIXAS = 0x257F

IGNORADOS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "htmlcov"}


def _caminho_candidato(caminho: Path) -> bool:
    return not any(parte in IGNORADOS for parte in caminho.parts)


def classificar(caminho: Path) -> str:
    """Diz qual regra se aplica ao arquivo.

    Tell which rule applies to the file.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        ``ascii``, ``markdown``, ``ignorado`` ou ``sem_regra``.
    """
    ext = caminho.suffix.lower()
    if ext in ASCII_PURO:
        return "ascii"
    if ext in DOCUMENTACAO:
        return "markdown"
    if ext in {".png", ".ico", ".jpg", ".gif", ".html", ".svg"}:
        # HTML e SVG gerados: o conteudo vem do codigo, verificado la.
        return "ignorado"
    return "sem_regra"


def auditar(caminho: Path) -> list[str]:
    """Lista os problemas de encoding de um arquivo.

    List a file's encoding problems.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        Lista de descricoes dos problemas, vazia se o arquivo estiver limpo.
    """
    modo = classificar(caminho)
    if modo in ("ignorado", "sem_regra"):
        return []

    texto = caminho.read_text(encoding="utf-8", errors="replace")
    problemas: list[str] = []

    if "\ufffd" in texto:
        problemas.append("contem U+FFFD, o caractere de substituicao")

    for numero, linha in enumerate(texto.splitlines(), 1):
        for coluna, caractere in enumerate(linha, 1):
            ponto = ord(caractere)
            if ponto < 128:
                continue

            nome = unicodedata.name(caractere, "U+%04X" % ponto)

            if 0x3000 <= ponto <= 0x9FFF or 0xAC00 <= ponto <= 0xD7AF:
                problemas.append(
                    f"linha {numero}, coluna {coluna}: ideograma CJK U+{ponto:04X}"
                )
                continue

            if modo == "ascii":
                problemas.append(
                    f"linha {numero}, coluna {coluna}: {nome} em arquivo de codigo"
                )
                continue

            if caractere in PERMITIDOS_MD:
                continue

            if INICIO_CAIXAS <= ponto <= FIM_CAIXAS:
                continue

            if 0xC0 <= ponto <= 0x17F:
                continue

            problemas.append(
                f"linha {numero}, coluna {coluna}: {nome} nao permitido em Markdown"
            )

    return problemas


def main() -> int:
    """Percorre o repositorio e reporta.

    Walk the repository and report.

    Returns:
        0 se todos os arquivos estiverem limpos, 1 caso contrario.
    """
    problemas: list[str] = []
    auditados = 0

    for caminho in sorted(RAIZ.rglob("*")):
        if not caminho.is_file() or not _caminho_candidato(caminho):
            continue
        modo = classificar(caminho)
        if modo in ("ignorado", "sem_regra"):
            continue
        auditados += 1
        achados = auditar(caminho)
        if achados:
            problemas.append(
                f"{caminho.relative_to(RAIZ)}: {len(achados)} ocorrencia(s)"
            )
            problemas.extend(f"    {a}" for a in achados[:6])

    if problemas:
        print("encoding FALHOU:")
        print("\n".join(problemas))
        return 1

    print(
        f"encoding ok: {auditados} arquivo(s), nenhum U+FFFD, nenhum ideograma "
        "CJK, nenhum caractere nao-ASCII em codigo ou dado"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
