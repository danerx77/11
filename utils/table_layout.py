"""Pomocniki utrzymujące kolumny tabel widoczne dla użytkownika.

Program zapisuje układ nagłówków (szerokości i kolejność kolumn) w
konfiguracji. Gdy w nowszej wersji dochodzi kolumna — jak „Identyfikator
działki” w Wypisach — stary zapis nie pasuje do nowej tabeli i potrafi
zostawić kolumnę ukrytą albo o zerowej szerokości. Poniższe funkcje
wykrywają taką sytuację i przywracają dostęp do wszystkich kolumn.

Funkcje operują na dowolnym obiekcie z interfejsem QTableWidget
(``columnCount``/``isColumnHidden``/``setColumnHidden``/``columnWidth``/
``setColumnWidth``), dzięki czemu można je testować bez uruchamiania Qt.
"""

from __future__ import annotations

from typing import Any, MutableMapping

# Poniżej tej szerokości kolumna jest praktycznie niewidoczna.
MIN_COLUMN_WIDTH = 40
# Szerokość nadawana kolumnie, którą trzeba było przywrócić.
FALLBACK_COLUMN_WIDTH = 120

COLUMN_COUNT_SUFFIX = "_columns"


def column_count_key(state_key: str) -> str:
    """Klucz konfiguracji z liczbą kolumn zapisanego układu."""

    return f"{state_key}{COLUMN_COUNT_SUFFIX}"


def state_matches_columns(
    config: MutableMapping[str, Any] | None,
    state_key: str,
    column_count: int,
) -> bool:
    """Czy zapisany układ nagłówka pasuje do dzisiejszej liczby kolumn.

    Brak zapisanej liczby kolumn oznacza stary zapis sprzed dodania tej
    informacji — traktujemy go jako niepasujący, żeby nie odtwarzać układu,
    w którym nowe kolumny są niewidoczne.
    """

    if not isinstance(config, MutableMapping):
        return False
    raw = config.get(column_count_key(state_key))
    try:
        return int(raw) == int(column_count)
    except (TypeError, ValueError):
        return False


def remember_column_count(
    config: MutableMapping[str, Any] | None,
    state_key: str,
    column_count: int,
) -> None:
    """Zapamiętuje, dla ilu kolumn zapisano układ nagłówka."""

    if isinstance(config, MutableMapping):
        config[column_count_key(state_key)] = int(column_count)


def ensure_columns_visible(
    table: Any,
    *,
    minimum_width: int = MIN_COLUMN_WIDTH,
    fallback_width: int = FALLBACK_COLUMN_WIDTH,
    wide_columns: dict[int, int] | None = None,
) -> list[int]:
    """Odkrywa ukryte kolumny i nadaje zbyt wąskim sensowną szerokość.

    ``wide_columns`` pozwala wskazać kolumny z długą treścią (np. lista
    działek albo identyfikatorów), którym należy się większa szerokość.
    Zwraca posortowaną listę indeksów kolumn, które wymagały naprawy.
    """

    repaired: list[int] = []
    wide = wide_columns or {}

    for column in range(int(table.columnCount())):
        needs_fix = False

        if table.isColumnHidden(column):
            table.setColumnHidden(column, False)
            needs_fix = True

        if int(table.columnWidth(column)) < minimum_width:
            table.setColumnWidth(column, max(fallback_width, wide.get(column, 0)))
            needs_fix = True

        # Kolumna, którą trzeba było ratować, dostaje też właściwą szerokość
        # — inaczej „odkryta” kolumna z długą treścią nadal jest nieczytelna.
        if needs_fix and column in wide:
            if int(table.columnWidth(column)) < wide[column]:
                table.setColumnWidth(column, wide[column])

        if needs_fix:
            repaired.append(column)

    return repaired


def apply_minimum_widths(table: Any, widths: dict[int, int]) -> list[int]:
    """Poszerza wskazane kolumny, jeśli są węższe niż podane minimum."""

    widened: list[int] = []
    count = int(table.columnCount())
    for column, wanted in sorted(widths.items()):
        if not (0 <= column < count):
            continue
        if int(table.columnWidth(column)) < wanted:
            table.setColumnWidth(column, wanted)
            widened.append(column)
    return widened
