"""Narzędzia do naturalnego sortowania numerów działek.

Numery działek często zawierają część główną i część po ukośniku, np.
``12/3`` albo ``12/10``. Zwykłe sortowanie tekstowe ustawia wtedy ``12/10``
przed ``12/3``. Funkcje z tego modułu porównują kolejne fragmenty liczbowe
jako liczby, zachowując przy tym oryginalny zapis na wyjściu.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"\d+|\D+")
_LIST_SEPARATOR_RE = re.compile(r"[\r\n,;\t]+")
_SLASH_SPACES_RE = re.compile(r"\s*/\s*")


def normalize_parcel_number(value: object) -> str:
    """Zwraca czytelny zapis numeru działki bez zbędnych odstępów.

    Nie zmienia samego numeru ani literowego dopisku. Usuwa wyłącznie spacje
    na początku i końcu oraz spacje wokół ukośnika, które często trafiają do
    list po wklejeniu danych z arkusza.
    """

    text = " ".join(str("" if value is None else value).strip().split())
    return _SLASH_SPACES_RE.sub("/", text)


def parcel_sort_key(value: object) -> tuple[tuple[object, ...], ...]:
    """Tworzy bezpieczny klucz naturalnego sortowania dla numeru działki.

    Każdy element klucza ma znacznik typu, dzięki czemu sortowanie nie próbuje
    porównać bezpośrednio liczby z tekstem dla nietypowych wpisów. Porównanie
    nie zależy od wielkości liter ani od wariantu Unicode znaków.
    """

    normalized = unicodedata.normalize("NFKC", normalize_parcel_number(value))
    folded = normalized.casefold()
    tokens: list[tuple[object, ...]] = []

    for token in _TOKEN_RE.findall(folded):
        if token.isdigit():
            tokens.append((0, int(token)))
        else:
            tokens.append((1, token))

    # Terminator musi sortować się przed kolejnym fragmentem numeru. Dzięki
    # temu działka 1 trafia przed 1/1, a nie po jej poddziałkach.
    tokens.append((-1,))
    return tuple(tokens)


def parse_parcel_list(text: object) -> list[str]:
    """Odczytuje numery działek rozdzielone wierszem, tabulatorem, przecinkiem
    lub średnikiem.
    """

    return [
        number
        for raw_value in _LIST_SEPARATOR_RE.split(str("" if text is None else text))
        if (number := normalize_parcel_number(raw_value))
    ]


def sort_parcel_numbers(
    values: Iterable[object], *, unique: bool = False, reverse: bool = False
) -> list[str]:
    """Sortuje numery działek naturalnie.

    Parametr ``unique`` usuwa powtarzające się wpisy bez rozróżniania wielkości
    liter, zachowując pierwszą wersję zapisu podaną przez użytkownika.
    """

    normalized_values = [
        normalized
        for value in values
        if (normalized := normalize_parcel_number(value))
    ]

    if unique:
        seen: set[str] = set()
        unique_values: list[str] = []
        for value in normalized_values:
            key = unicodedata.normalize("NFKC", value).casefold()
            if key not in seen:
                seen.add(key)
                unique_values.append(value)
        normalized_values = unique_values

    return sorted(normalized_values, key=parcel_sort_key, reverse=reverse)
