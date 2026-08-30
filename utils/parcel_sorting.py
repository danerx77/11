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
# Po znormalizowaniu spacji wokół ukośnika można bezpiecznie traktować każdą
# pozostałą spację jako separator kolejnego numeru działki.
_LIST_SEPARATOR_RE = re.compile(r"[\s,;]+")
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
    """Odczytuje numery działek rozdzielone spacją, wierszem, tabulatorem,
    przecinkiem lub średnikiem.

    Spacje wokół ukośnika są najpierw usuwane, dlatego zapis ``1 / 2`` nadal
    oznacza jeden numer działki, a ``1/2 1/3`` oznacza dwa kolejne numery.
    """

    # Najpierw zabezpieczamy poprawny zapis numeru ze spacjami wokół ukośnika,
    # dopiero potem rozdzielamy pozostałe białe znaki na kolejne wpisy.
    source = _SLASH_SPACES_RE.sub("/", str("" if text is None else text))
    return [
        number
        for raw_value in _LIST_SEPARATOR_RE.split(source)
        if (number := normalize_parcel_number(raw_value))
    ]


def format_parcel_list(values: Iterable[object]) -> str:
    """Zapisuje numery działek w jednym wierszu, rozdzielając je przecinkiem.

    Ten format jest używany zarówno w widoku sortera, jak i w zapamiętanych
    ustawieniach. ``parse_parcel_list`` nadal rozumie także starszy zapis w
    wielu wierszach, więc wcześniej zapisane listy pozostają kompatybilne.
    """

    return ", ".join(
        normalized
        for value in values
        if (normalized := normalize_parcel_number(value))
    )


def _duplicate_key(value: str) -> str:
    """Buduje klucz porównania dla wykrywania identycznych działek."""

    return unicodedata.normalize("NFKC", value).casefold()


def remove_duplicate_parcel_numbers(values: Iterable[object]) -> list[str]:
    """Usuwa powtórzone numery działek, zachowując pierwszy zapis i kolejność.

    W przeciwieństwie do ``sort_parcel_numbers(..., unique=True)`` funkcja nie
    sortuje wyniku. Dzięki temu lista ``1/2, 1/3, 1/2, 1/4`` zwróci dokładnie
    ``1/2, 1/3, 1/4``.
    """

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_parcel_number(value)
        if not normalized:
            continue
        key = _duplicate_key(normalized)
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def find_duplicate_parcel_numbers(values: Iterable[object]) -> list[tuple[str, int]]:
    """Zwraca powielone działki jako ``(pierwszy_zapis, liczba_wystąpień)``.

    Wynik zachowuje kolejność, w której duplikaty po raz pierwszy pojawiły się
    na wejściu. Spacje wokół ukośnika są ignorowane, np. ``1 / 2`` i ``1/2``
    są tym samym numerem.
    """

    counts: dict[str, int] = {}
    first_values: dict[str, str] = {}
    order: list[str] = []
    for value in values:
        normalized = normalize_parcel_number(value)
        if not normalized:
            continue
        key = _duplicate_key(normalized)
        if key not in counts:
            counts[key] = 0
            first_values[key] = normalized
            order.append(key)
        counts[key] += 1
    return [
        (first_values[key], counts[key])
        for key in order
        if counts[key] > 1
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
        normalized_values = remove_duplicate_parcel_numbers(normalized_values)

    return sorted(normalized_values, key=parcel_sort_key, reverse=reverse)
