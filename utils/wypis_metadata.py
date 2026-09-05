"""Odczyt metadanych wypisu, gdy dokument obejmuje wiele obrębów lub gmin.

Wcześniej program brał wyłącznie **pierwszą** znalezioną wartość pola
„Obręb ewidencyjny:”, „Jednostka ewidencyjna:”, „Powiat:” i „Województwo:”.
Jeden wypis potrafi jednak zawierać działki z kilku obrębów, a nawet z kilku
gmin — wtedy pozostałe wartości znikały.

Ten moduł zbiera **wszystkie** wystąpienia każdego pola z zachowaniem kolejności
i bez duplikatów, a dodatkowo potrafi przypisać właściwą wartość do konkretnej
działki na podstawie miejsca jej wystąpienia w tekście.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

META_FIELDS = ("voivodeship", "county", "municipality", "precinct", "precinct_number")

# Wartości oznaczające nieudany odczyt nagłówka wypisu.
_BAD_VALUES = {"", "-", "--", "owe w", "w", "powiatowe w", "brak", "nie dotyczy"}

_LABEL_PATTERNS = {
    "voivodeship": re.compile(r"Wojew[oó]dztwo\s*:?\s*([^\n]*)", re.I),
    "county": re.compile(r"Powiat\s*:?\s*([^\n]*)", re.I),
    "municipality": re.compile(
        r"(?:Jednostka\s+ewidencyjna|Gmina)\s*:?\s*([^\n]*)", re.I
    ),
    "precinct": re.compile(r"Obr[eę]b(?:\s+ewidencyjny)?\s*:?\s*([^\n]*)", re.I),
}

_STOP_WORDS = {
    "voivodeship": r"\b(Powiat|Gmina|Jednostka|Obr[eę]b)\b",
    "county": r"\b(Gmina|Jednostka|Obr[eę]b|Wojew[oó]dztwo)\b",
    "municipality": r"\b(Obr[eę]b|Wojew[oó]dztwo|Powiat|Nr\s+Kancelaryjny)\b",
    "precinct": r"\b(Wojew[oó]dztwo|Powiat|Jednostka|Nr\s+Kancelaryjny|Numer\s+jednostki)\b",
}

_PARCEL_LINE_RE = re.compile(r"\b(\d{1,6}(?:/\d+[a-zA-Z]?)?)\b")


def _normalize(value: object) -> str:
    return " ".join(str("" if value is None else value).split()).strip(" ,;:-")


def _is_usable(value: str) -> bool:
    return bool(value) and value.casefold() not in _BAD_VALUES


def _clean_field_value(field: str, raw_value: str) -> str:
    """Ucina wartość na kolejnej etykiecie nagłówka wypisu."""

    value = _normalize(raw_value)
    stop = _STOP_WORDS.get(field)
    if stop:
        value = _normalize(re.split(stop, value, maxsplit=1, flags=re.I)[0])
    if field == "municipality" and "," in value:
        # „powiat kartuski, Żukowo” → „Żukowo”
        value = _normalize(value.split(",")[-1])
    return value


def split_precinct_value(value: object) -> tuple[str, str]:
    """Rozdziela zapis obrębu na (nazwa, numer).

    Obsługiwane warianty: ``0001, Polki``, ``Nr 0001 Polki``, ``Polki``, ``0001``.
    """

    text = _normalize(value)
    if not text:
        return "", ""

    text = _normalize(re.split(r"(?i)Nr\s+Kancelaryjny", text)[0])

    match = re.match(r"^(?:Nr\.?\s*)?0*(\d{1,5})\s*[,\-–—/ ]+\s*(.+)$", text, re.I)
    if match:
        return _normalize(match.group(2)), str(int(match.group(1)))

    match = re.match(r"^(.+?)\s*[,\-–—]\s*(?:Nr\.?\s*)?0*(\d{1,5})$", text, re.I)
    if match:
        return _normalize(match.group(1)), str(int(match.group(2)))

    if re.fullmatch(r"0*\d{1,5}", text):
        return "", str(int(text))
    return text, ""


def extract_meta_values(text: object) -> dict[str, list[str]]:
    """Zwraca wszystkie wartości każdego pola nagłówka, w kolejności z pliku.

    Dzięki temu wypis obejmujący np. dwa obręby zwróci obie nazwy, a nie tylko
    pierwszą z nich.
    """

    source = str("" if text is None else text)
    values: dict[str, list[str]] = {field: [] for field in META_FIELDS}

    for field, pattern in _LABEL_PATTERNS.items():
        for match in pattern.finditer(source):
            cleaned = _clean_field_value(field, match.group(1))
            if field == "precinct":
                name, number = split_precinct_value(cleaned)
                if _is_usable(name) and name not in values["precinct"]:
                    values["precinct"].append(name)
                if number and number not in values["precinct_number"]:
                    values["precinct_number"].append(number)
                continue
            if _is_usable(cleaned) and cleaned not in values[field]:
                values[field].append(cleaned)
    return values


def extract_meta_positions(text: object) -> dict[str, list[tuple[int, str]]]:
    """Zwraca pozycje w tekście, w których pojawia się każda wartość pola.

    Pozycje pozwalają przypisać działce metadane z najbliższego wcześniejszego
    nagłówka, zamiast nadpisywać wszystko pierwszą znalezioną wartością.
    """

    source = str("" if text is None else text)
    positions: dict[str, list[tuple[int, str]]] = {field: [] for field in META_FIELDS}

    for field, pattern in _LABEL_PATTERNS.items():
        for match in pattern.finditer(source):
            cleaned = _clean_field_value(field, match.group(1))
            if field == "precinct":
                name, number = split_precinct_value(cleaned)
                if _is_usable(name):
                    positions["precinct"].append((match.start(), name))
                if number:
                    positions["precinct_number"].append((match.start(), number))
                continue
            if _is_usable(cleaned):
                positions[field].append((match.start(), cleaned))

    for field in positions:
        positions[field].sort(key=lambda item: item[0])
    return positions


def value_at_position(entries: Iterable[tuple[int, str]], position: int) -> str:
    """Zwraca wartość z ostatniego nagłówka przed podaną pozycją w tekście."""

    result = ""
    for start, value in entries:
        if start <= position:
            result = value
        else:
            break
    return result


def parcel_meta_map(text: object) -> dict[str, dict[str, str]]:
    """Przypisuje każdej działce metadane z jej sekcji dokumentu.

    Klucz to numer działki, wartość to słownik pól. Wypis z kilkoma obrębami
    dostaje dzięki temu poprawny obręb przy każdej działce.
    """

    source = str("" if text is None else text)
    positions = extract_meta_positions(source)
    result: dict[str, dict[str, str]] = {}

    for match in re.finditer(r"(?im)^\s*(?:Oznaczenie\s+dzia[łl]ki\s*:?\s*)?(\d{1,6}(?:/\d+[a-zA-Z]?)?)\s*$", source):
        number = match.group(1)
        entry = result.setdefault(number, {})
        for field in META_FIELDS:
            value = value_at_position(positions[field], match.start())
            if value and not entry.get(field):
                entry[field] = value

    # Wariant spotykany w wypisach pełnych: "Numer działki: 12/3" w jednej linii.
    for match in re.finditer(
        r"(?im)^\s*Numer\s+dzia[łl]ki\s*:?\s*(\d{1,6}(?:/\d+[a-zA-Z]?)?)\s*$", source
    ):
        number = match.group(1)
        entry = result.setdefault(number, {})
        for field in META_FIELDS:
            value = value_at_position(positions[field], match.start())
            if value and not entry.get(field):
                entry[field] = value

    for match in re.finditer(r"Identyfikator\s+dzia[łl]ki\s*:?\s*([0-9A-Za-z_.\-/]+)", source, re.I):
        identifier = match.group(1)
        number = identifier.rsplit(".", 1)[-1]
        if not _PARCEL_LINE_RE.fullmatch(number):
            continue
        entry = result.setdefault(number, {})
        for field in META_FIELDS:
            value = value_at_position(positions[field], match.start())
            if value and not entry.get(field):
                entry[field] = value
    return result


def combine_meta_values(values: Mapping[str, Iterable[str]], separator: str = ", ") -> dict[str, str]:
    """Łączy wiele wartości pola w jeden czytelny tekst dla pól formularza."""

    combined: dict[str, str] = {}
    for field in META_FIELDS:
        entries = [
            _normalize(value) for value in values.get(field, []) if _is_usable(_normalize(value))
        ]
        unique: list[str] = []
        for entry in entries:
            if entry not in unique:
                unique.append(entry)
        combined[field] = separator.join(unique)
    return combined


def extract_wypis_metadata(text: object, separator: str = ", ") -> dict[str, Any]:
    """Główna funkcja: zwraca połączone i rozbite metadane wypisu.

    Klucze ``voivodeship``…``precinct_number`` zawierają połączony tekst (dla
    zgodności z resztą programu), a ``*_values`` pełne listy wartości.
    """

    values = extract_meta_values(text)
    result: dict[str, Any] = combine_meta_values(values, separator=separator)
    for field in META_FIELDS:
        result[f"{field}_values"] = list(values[field])
    result["has_multiple"] = any(len(values[field]) > 1 for field in META_FIELDS)
    return result


def merge_meta_into_parcels(
    parcels: Iterable[dict],
    text: object,
    fallback: Mapping[str, Any] | None = None,
) -> list[dict]:
    """Uzupełnia metadane w działkach zgodnie z ich miejscem w dokumencie.

    Działki spoza rozpoznanych sekcji dostają wartość zapasową (``fallback``),
    czyli dotychczasowe zachowanie programu.
    """

    per_parcel = parcel_meta_map(text)
    defaults = {
        field: _normalize((fallback or {}).get(field, "")) for field in META_FIELDS
    }

    updated: list[dict] = []
    for parcel in parcels:
        if not isinstance(parcel, dict):
            updated.append(parcel)
            continue
        number = str(parcel.get("number", "")).strip()
        specific = per_parcel.get(number, {})
        for field in META_FIELDS:
            value = specific.get(field) or defaults.get(field, "")
            if value and not _normalize(parcel.get(field, "")):
                parcel[field] = value
        updated.append(parcel)
    return updated
