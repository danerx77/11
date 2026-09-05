"""Czysta logika modułu Wskaźnik: działki i ich identyfikatory ewidencyjne.

Moduł nie zależy od Qt, dzięki czemu odczyt plików TXT/CSV, filtrowanie listą
działek oraz scalanie danych z wypisów można w całości pokryć testami.

Identyfikator działki ewidencyjnej ma postać ``WWPPGG_R.XXXX.NDZ``, np.
``221001_1.0001.123/4``. Program nigdy nie zmienia jego treści — normalizuje
wyłącznie białe znaki, aby ten sam identyfikator nie trafił na listę dwa razy.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

from utils.wypis_fields import normalize_parcel_identifier

from utils.parcel_sorting import (
    normalize_parcel_number,
    parcel_sort_key,
    parse_parcel_list,
)

# Kolumny zapisywane w pliku projektu i eksportach.
INDICATOR_FIELDS = (
    "number",
    "identifier",
    "precinct",
    "precinct_number",
    "municipality",
    "county",
    "voivodeship",
    "note",
)

# Pełny identyfikator działki: TERYT gminy, rodzaj, numer obrębu i numer działki.
FULL_IDENTIFIER_RE = re.compile(
    r"\b(\d{6}_\d(?:\.\d{4})?\.[0-9A-Za-z]+(?:/[0-9A-Za-z]+)*)\b"
)
# Zapis spotykany w niektórych wypisach: 221001_1.0001.123/4 bez podkreślenia.
LOOSE_IDENTIFIER_RE = re.compile(
    r"\b(\d{6}[_\s.]\d[.\s]\d{4}[.\s][0-9A-Za-z]+(?:/[0-9A-Za-z]+)*)\b"
)

_SEPARATOR_RE = re.compile(r"[\t;|]+|\s{2,}|\s*=>\s*|\s*=\s*")


def normalize_identifier(value: object) -> str:
    """Zwraca identyfikator w zapisie z podkreślnikiem i kropkami.

    ``110101 2 0010 202`` → ``110101_2.0010.202``. Wartości, których nie da
    się rozpoznać, zostają bez zmian (bez nadmiarowych spacji).
    """

    text = " ".join(str("" if value is None else value).split())
    text = text.strip(" ,;")
    return normalize_parcel_identifier(text) or text


def _clean_text(value: object) -> str:
    return " ".join(str("" if value is None else value).split()).strip()


def parcel_number_from_identifier(identifier: object) -> str:
    """Odczytuje numer działki z końcówki identyfikatora ewidencyjnego."""

    text = normalize_identifier(identifier)
    if not text:
        return ""
    tail = text.rsplit(".", 1)[-1]
    if re.fullmatch(r"[0-9A-Za-z]+(?:/[0-9A-Za-z]+)*", tail) and any(
        char.isdigit() for char in tail
    ):
        return normalize_parcel_number(tail)
    return ""


def precinct_number_from_identifier(identifier: object) -> str:
    """Odczytuje numer obrębu (czwarty człon identyfikatora), jeśli istnieje."""

    text = normalize_identifier(identifier)
    parts = text.split(".")
    if len(parts) >= 3 and re.fullmatch(r"\d{4}", parts[1]):
        return parts[1]
    return ""


def make_indicator_row(data: Mapping[str, Any] | None = None, **overrides: Any) -> dict:
    """Tworzy pojedynczy wiersz modułu Wskaźnik z pełnym zestawem pól."""

    source: dict[str, Any] = dict(data or {})
    source.update(overrides)

    row = {field: "" for field in INDICATOR_FIELDS}
    row["number"] = normalize_parcel_number(source.get("number"))
    row["identifier"] = normalize_identifier(source.get("identifier"))
    for field in ("precinct", "precinct_number", "municipality", "county", "voivodeship", "note"):
        row[field] = _clean_text(source.get(field))

    # Identyfikator jest wiarygodnym źródłem numeru działki i numeru obrębu.
    if not row["number"]:
        row["number"] = parcel_number_from_identifier(row["identifier"])
    if not row["precinct_number"]:
        row["precinct_number"] = precinct_number_from_identifier(row["identifier"])
    return row


def parse_indicator_line(line: object) -> dict | None:
    """Odczytuje jedną linię pliku TXT/CSV z działką i jej identyfikatorem.

    Obsługiwane zapisy w jednej linii:

    * ``123/4;221001_1.0001.123/4``
    * ``123/4 -> 221001_1.0001.123/4``
    * ``221001_1.0001.123/4`` (sam identyfikator, numer działki z końcówki)
    * ``123/4`` (sama działka, identyfikator do uzupełnienia)
    * ``123/4 | 221001_1.0001.123/4 | Obręb Polki``
    """

    text = _clean_text(line)
    if not text or text.startswith("#"):
        return None

    identifier = ""
    match = FULL_IDENTIFIER_RE.search(text) or LOOSE_IDENTIFIER_RE.search(text)
    if match:
        identifier = normalize_identifier(match.group(1))
        # Ujednolicamy zapis z przypadkowymi spacjami wewnątrz identyfikatora.
        identifier = re.sub(r"\s+", "", identifier)
        text = (text[: match.start()] + " " + text[match.end() :]).strip()

    fields = [
        field.strip(" ,;:-")
        for field in _SEPARATOR_RE.split(text)
        if field.strip(" ,;:-")
    ]

    number = ""
    remaining: list[str] = []
    for field in fields:
        candidate = normalize_parcel_number(field)
        if not number and re.fullmatch(r"\d+(?:/[0-9A-Za-z]+)*", candidate):
            number = candidate
            continue
        remaining.append(field)

    if not number and not identifier:
        # Ostatnia szansa: numer działki może stać w linii razem z opisem.
        loose = re.search(r"\b(\d+(?:/[0-9A-Za-z]+)+|\d{1,6})\b", text)
        if not loose:
            return None
        number = normalize_parcel_number(loose.group(1))
        remaining = [text.replace(loose.group(1), " ").strip(" ,;:-")]
        remaining = [value for value in remaining if value]

    note = ", ".join(remaining)
    row = make_indicator_row(number=number, identifier=identifier, note=note)
    return row if row["number"] or row["identifier"] else None


def parse_indicator_text(text: object) -> list[dict]:
    """Odczytuje cały plik/wklejony tekst z działkami i identyfikatorami.

    Gdy w jednej linii jest wiele numerów działek bez identyfikatorów (np.
    ``1/1, 1/2, 1/3``), każdy z nich staje się osobnym wierszem.
    """

    rows: list[dict] = []
    for raw_line in str("" if text is None else text).splitlines():
        line = _clean_text(raw_line)
        if not line or line.startswith("#"):
            continue

        has_identifier = bool(
            FULL_IDENTIFIER_RE.search(line) or LOOSE_IDENTIFIER_RE.search(line)
        )
        if not has_identifier and ("," in line or re.search(r"\d\s+\d", line)):
            numbers = parse_parcel_list(line)
            if len(numbers) > 1:
                rows.extend(make_indicator_row(number=number) for number in numbers)
                continue

        row = parse_indicator_line(line)
        if row is not None:
            rows.append(row)
    return rows


def merge_indicator_rows(
    existing: Iterable[Mapping[str, Any]],
    incoming: Iterable[Mapping[str, Any]],
    *,
    overwrite: bool = False,
) -> tuple[list[dict], int, int]:
    """Scala nowe wiersze z już wczytanymi, bez gubienia opisów.

    Zwraca ``(wiersze, liczba_dodanych, liczba_uzupełnionych)``. Domyślnie nie
    nadpisujemy istniejącego identyfikatora — uzupełniamy wyłącznie puste pola,
    aby import z pliku nie skasował ręcznych poprawek użytkownika.
    """

    rows = [make_indicator_row(row) for row in existing]
    index = {row["number"].casefold(): position for position, row in enumerate(rows) if row["number"]}

    added = 0
    updated = 0
    for source in incoming:
        candidate = make_indicator_row(source)
        if not candidate["number"] and not candidate["identifier"]:
            continue

        key = candidate["number"].casefold()
        if not key or key not in index:
            rows.append(candidate)
            if key:
                index[key] = len(rows) - 1
            added += 1
            continue

        target = rows[index[key]]
        changed = False
        for field in INDICATOR_FIELDS:
            if field == "number":
                continue
            new_value = candidate.get(field, "")
            if not new_value:
                continue
            if overwrite or not target.get(field):
                if target.get(field) != new_value:
                    target[field] = new_value
                    changed = True
        if changed:
            updated += 1
    return rows, added, updated


def indicator_rows_from_owners(owners: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Buduje listę działek z identyfikatorami na podstawie danych z Wypisów."""

    rows: list[dict] = []
    seen: set[str] = set()
    for owner in owners:
        for parcel in owner.get("parcels", []) or []:
            if isinstance(parcel, Mapping):
                row = make_indicator_row(
                    number=parcel.get("number"),
                    identifier=parcel.get("identifier"),
                    precinct=parcel.get("precinct") or owner.get("precinct"),
                    precinct_number=(
                        parcel.get("precinct_number") or owner.get("precinct_number")
                    ),
                    municipality=parcel.get("municipality") or owner.get("municipality"),
                    county=parcel.get("county") or owner.get("county"),
                    voivodeship=parcel.get("voivodeship") or owner.get("voivodeship"),
                )
            else:
                row = make_indicator_row(number=parcel)
            if not row["number"] and not row["identifier"]:
                continue
            key = row["number"].casefold() or row["identifier"].casefold()
            if key in seen:
                # Ta sama działka u kilku współwłaścicieli — scalamy dane.
                for existing_row in rows:
                    existing_key = (
                        existing_row["number"].casefold()
                        or existing_row["identifier"].casefold()
                    )
                    if existing_key != key:
                        continue
                    for field in INDICATOR_FIELDS:
                        if row.get(field) and not existing_row.get(field):
                            existing_row[field] = row[field]
                    break
                continue
            seen.add(key)
            rows.append(row)
    return rows


def indicator_rows_from_parcels(parcels: Iterable[Mapping[str, Any] | str]) -> list[dict]:
    """Buduje listę wierszy z zakładki Lista Działek."""

    rows: list[dict] = []
    seen: set[str] = set()
    for parcel in parcels:
        if isinstance(parcel, Mapping):
            row = make_indicator_row(
                number=parcel.get("number"),
                identifier=parcel.get("identifier"),
                precinct=parcel.get("precinct"),
                precinct_number=parcel.get("precinct_number"),
            )
        else:
            row = make_indicator_row(number=parcel)
        key = row["number"].casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def indicator_rows_from_project(
    parcels: Iterable[Mapping[str, Any] | str],
    owners: Iterable[Mapping[str, Any]] = (),
) -> list[dict]:
    """Łączy listę działek projektu z danymi z Wypisów.

    Lista działek decyduje o tym, które działki mają się pojawić, a wypisy
    uzupełniają identyfikator, obręb, gminę, powiat i województwo. Działki
    znane tylko z wypisów też trafiają na listę, żeby nic nie zginęło.
    """

    rows = indicator_rows_from_parcels(parcels)
    owner_rows = indicator_rows_from_owners(owners or [])
    if not owner_rows:
        return rows
    merged, _added, _updated = merge_indicator_rows(rows, owner_rows)
    return merged


def sort_indicator_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    key: str = "number",
    reverse: bool = False,
) -> list[dict]:
    """Sortuje wiersze naturalnie po numerze działki albo tekstowo po polu."""

    materialized = [make_indicator_row(row) for row in rows]
    if key == "number":
        return sorted(materialized, key=lambda row: parcel_sort_key(row["number"]), reverse=reverse)
    return sorted(
        materialized,
        key=lambda row: (str(row.get(key, "")).casefold(), parcel_sort_key(row["number"])),
        reverse=reverse,
    )


def filter_indicator_rows(
    rows: Iterable[Mapping[str, Any]],
    filter_text: object,
    *,
    search_text: object = "",
) -> tuple[list[dict], list[str]]:
    """Zwraca wiersze wskazane listą działek oraz działki nieodnalezione.

    ``filter_text`` może być listą działek rozdzieloną przecinkami, spacjami,
    średnikami, tabulatorami lub nowymi wierszami — dokładnie tak, jak działa
    zakładka Sortowanie działek. Pusty filtr oznacza „pokaż wszystko”.

    ``search_text`` dodatkowo zawęża wynik do wierszy zawierających podany
    fragment w dowolnej kolumnie (numer, identyfikator, obręb, notatka).
    """

    materialized = [make_indicator_row(row) for row in rows]
    wanted = parse_parcel_list(filter_text)

    if wanted:
        by_number: dict[str, list[dict]] = {}
        for row in materialized:
            by_number.setdefault(row["number"].casefold(), []).append(row)

        selected: list[dict] = []
        missing: list[str] = []
        used: set[int] = set()
        for number in wanted:
            matches = by_number.get(number.casefold())
            if not matches:
                if number not in missing:
                    missing.append(number)
                continue
            for row in matches:
                if id(row) in used:
                    continue
                used.add(id(row))
                selected.append(row)
    else:
        selected = list(materialized)
        missing = []

    needle = _clean_text(search_text).casefold()
    if needle:
        selected = [
            row
            for row in selected
            if needle
            in " ".join(str(row.get(field, "")) for field in INDICATOR_FIELDS).casefold()
        ]
    return selected, missing


def indicator_summary(
    rows: Iterable[Mapping[str, Any]],
    missing: Iterable[object] = (),
) -> dict[str, Any]:
    """Liczy podsumowanie widoku: ile działek ma identyfikator, ile brakuje."""

    materialized = [make_indicator_row(row) for row in rows]
    with_identifier = [row for row in materialized if row["identifier"]]
    without_identifier = [row["number"] for row in materialized if not row["identifier"]]

    counts: dict[str, int] = {}
    for row in materialized:
        if row["identifier"]:
            counts[row["identifier"].casefold()] = counts.get(row["identifier"].casefold(), 0) + 1
    duplicates = sorted(
        {
            row["identifier"]
            for row in materialized
            if row["identifier"] and counts.get(row["identifier"].casefold(), 0) > 1
        }
    )

    return {
        "total": len(materialized),
        "with_identifier": len(with_identifier),
        "without_identifier": without_identifier,
        "missing": [normalize_parcel_number(value) for value in missing if str(value).strip()],
        "duplicate_identifiers": duplicates,
    }


# Nagłówki kolumn używane przy zapisie do pliku i w podglądzie.
EXPORT_COLUMN_LABELS: dict[str, str] = {
    "number": "Nr działki",
    "identifier": "Identyfikator działki",
    "precinct": "Obręb",
    "precinct_number": "Nr obrębu",
    "municipality": "Jednostka ewidencyjna",
    "county": "Powiat",
    "voivodeship": "Województwo",
    "note": "Notatka",
}


def format_indicator_export(
    rows: Iterable[Mapping[str, Any]],
    *,
    columns: Iterable[str] = ("number", "identifier"),
    separator: str = ";",
    header: bool = False,
) -> str:
    """Buduje tekst do zapisania w pliku TXT/CSV lub skopiowania do schowka."""

    selected_columns = tuple(columns)
    labels = EXPORT_COLUMN_LABELS

    lines: list[str] = []
    if header:
        lines.append(separator.join(labels.get(name, name) for name in selected_columns))
    for row in rows:
        materialized = make_indicator_row(row)
        lines.append(
            separator.join(str(materialized.get(name, "")) for name in selected_columns)
        )
    return "\n".join(lines)
