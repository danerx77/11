"""Formatowanie pól odczytanych z wypisów.

Trzy sprawy zgłoszone przez użytkownika:

1. „Jednostka ewidencyjna” bywa zapisana jako ``Maki - G`` (gmina) albo
   ``Maki - M`` (miasto). Czasem chcemy samą miejscowość, czasem miejscowość
   z zachowanym oznaczeniem miasta, a czasem pełny zapis jak w wypisie.
2. Identyfikator działki bywa rozdzielony spacjami
   (``110101 2 0010 202``), a powinien mieć podkreślnik i kropki
   (``110101_2.0010.202``).
3. Forma władania i udział to osobne dane, które trzeba czytać z wypisu.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

# ── Jednostka ewidencyjna ────────────────────────────────────────────

MUNICIPALITY_MODE_KEY = "wypis_municipality_mode"

MODE_FULL = "full"          # Maki - G  (jak w wypisie)
MODE_CITY_ONLY = "city"     # Maki
MODE_KEEP_CITY = "keep_m"   # Maki, ale "Maki - M" zostaje

DEFAULT_MUNICIPALITY_MODE = MODE_FULL

MUNICIPALITY_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    ("Tak jak w wypisie — „Maki - G”, „Maki - M”", MODE_FULL),
    ("Tylko miejscowość — „Maki”", MODE_CITY_ONLY),
    ("Miejscowość, ale zostaw „- M” dla miasta", MODE_KEEP_CITY),
)

# Oznaczenie rodzaju jednostki na końcu nazwy: "Maki - G", "Maki-M", "Maki – W".
_UNIT_SUFFIX = re.compile(
    r"\s*[-–—]\s*(?P<kind>[GMWgmw])\s*$"
)


def split_municipality(value: Any) -> tuple[str, str]:
    """Rozdziela „Maki - G” na („Maki”, „G”).

    Gdy oznaczenia nie ma, druga wartość jest pusta.
    """

    text = "" if value is None else str(value).strip()
    if not text:
        return "", ""
    match = _UNIT_SUFFIX.search(text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), match.group("kind").upper()


def format_municipality(value: Any, mode: str = DEFAULT_MUNICIPALITY_MODE) -> str:
    """Formatuje jednostkę ewidencyjną według wybranego trybu."""

    text = "" if value is None else str(value).strip()
    if not text:
        return ""

    # Wypis potrafi podać kilka jednostek po przecinku — formatujemy każdą.
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        formatted = [format_municipality(part, mode) for part in parts]
        seen: list[str] = []
        for item in formatted:
            if item and item not in seen:
                seen.append(item)
        return ", ".join(seen)

    city, kind = split_municipality(text)
    if not kind:
        return text
    if mode == MODE_CITY_ONLY:
        return city
    if mode == MODE_KEEP_CITY:
        # Miasto zachowuje oznaczenie, gmina je traci.
        return f"{city} - M" if kind == "M" else city
    return text


def municipality_mode(config: Mapping[str, Any] | None) -> str:
    if not isinstance(config, Mapping):
        return DEFAULT_MUNICIPALITY_MODE
    mode = str(config.get(MUNICIPALITY_MODE_KEY, DEFAULT_MUNICIPALITY_MODE) or "")
    valid = {choice for _, choice in MUNICIPALITY_MODE_CHOICES}
    return mode if mode in valid else DEFAULT_MUNICIPALITY_MODE


def format_municipality_for_config(
    value: Any, config: Mapping[str, Any] | None
) -> str:
    return format_municipality(value, municipality_mode(config))


# ── Identyfikator działki ────────────────────────────────────────────

# Prawidłowy zapis: 110101_2.0010.202 albo 110101_2.0010.22/21
_IDENT_OK = re.compile(r"^\d{6}_\d+\.\d+\.\S+$")


def normalize_parcel_identifier(value: Any) -> str:
    """Doprowadza identyfikator działki do zapisu z podkreślnikiem i kropkami.

    ``110101 2 0010 202``    → ``110101_2.0010.202``
    ``110101 2 0010 22 21``  → ``110101_2.0010.22/21``

    Zapis już poprawny zostaje bez zmian.
    """

    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    if _IDENT_OK.match(text):
        return text

    # Ujednolicamy separatory: podkreślnik, kropka i spacja znaczą to samo.
    working = text.replace("_", " ").replace(".", " ")
    # Ukośnik w numerze działki zostawiamy — to część numeru (22/21).
    parts = [part for part in re.split(r"\s+", working) if part]
    if len(parts) < 3:
        return text

    # Pierwsze trzy człony to TERYT, rodzaj i numer obrębu.
    head, kind, precinct = parts[0], parts[1], parts[2]
    rest = parts[3:]
    if not (head.isdigit() and kind.isdigit() and precinct.isdigit()):
        return text

    if not rest:
        return f"{head}_{kind}.{precinct}"

    # Numer działki: „22 21” to w rzeczywistości 22/21.
    parcel = "/".join(rest)
    parcel = re.sub(r"/{2,}", "/", parcel)
    return f"{head}_{kind}.{precinct}.{parcel}"


def identifier_matches_parcel(identifier: Any, parcel_number: Any) -> bool:
    """Sprawdza, czy identyfikator kończy się danym numerem działki."""

    ident = normalize_parcel_identifier(identifier)
    number = "" if parcel_number is None else str(parcel_number).strip()
    if not ident or not number:
        return False
    return ident.rsplit(".", 1)[-1] == number


# ── Forma władania i udział ──────────────────────────────────────────

# Formy spotykane w wypisach. Kolejność ma znaczenie: dłuższe i bardziej
# szczegółowe napisy sprawdzamy przed krótszymi, żeby "współwłasność" nie
# została rozpoznana jako "własność".
_OWNERSHIP_FORMS: tuple[str, ...] = (
    "wspólność ustawowa majątkowa małżeńska",
    "wspólność ustawowa",
    "współwłasność ustawowa",
    "współwłasność w częściach ułamkowych",
    "współwłasność łączna",
    "współwłasność",
    "współużytkowanie wieczyste",
    "użytkowanie wieczyste",
    "udział łączny",
    "trwały zarząd",
    "posiadanie samoistne",
    "posiadanie zależne",
    "dzierżawa",
    "władanie",
    "własność",
)

# Wypisy bywają drukowane bez polskich znaków ("wspolnosc ustawowa",
# "udzial laczny"), więc porównujemy napisy po zdjęciu ogonków.
_DIACRITICS = str.maketrans(
    "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ"
)


def _fold(value: str) -> str:
    """Sprowadza napis do postaci bez ogonków i bez wielkich liter."""

    return " ".join(str(value or "").translate(_DIACRITICS).lower().split())


_SHARE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")


def normalize_share(value: Any) -> str:
    """Porządkuje zapis udziału: ``14 / 48`` → ``14/48``."""

    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    match = _SHARE.search(text)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return text


def extract_ownership_form(text: Any) -> str:
    """Wyszukuje formę władania w tekście wypisu.

    Działa niezależnie od polskich znaków — „wspolnosc ustawowa” z wypisu
    drukowanego bez ogonków zostanie rozpoznana tak samo jak „wspólność
    ustawowa”. Zwracany zapis jest zawsze kanoniczny, z ogonkami.
    """

    folded = _fold(text)
    if not folded:
        return ""
    for form in _OWNERSHIP_FORMS:
        if _fold(form) in folded:
            return form
    return ""


def extract_ownership_forms(text: Any) -> list[str]:
    """Zwraca wszystkie formy władania znalezione w tekście.

    Wypis potrafi podać dwie informacje naraz, np. „wspólność ustawowa”
    i „współwłasność” albo „udział łączny” i „współwłasność”. Zwracamy je
    w kolejności występowania w dokumencie, bez powtórzeń.
    """

    folded = _fold(text)
    if not folded:
        return []
    found: list[tuple[int, str]] = []
    used: list[str] = []
    for form in _OWNERSHIP_FORMS:
        needle = _fold(form)
        position = folded.find(needle)
        if position < 0:
            continue
        # "współwłasność" nie może się zdublować z "współwłasność łączna".
        if any(needle in _fold(other) or _fold(other) in needle for other in used):
            continue
        used.append(form)
        found.append((position, form))
    return [form for _position, form in sorted(found)]


def combine_ownership_forms(text: Any) -> str:
    """Skleja znalezione formy władania w jeden opis do kolumny tabeli."""

    return ", ".join(extract_ownership_forms(text))


def parse_ownership_line(line: Any) -> dict[str, str]:
    """Rozbiera wiersz wypisu na udział i formę władania.

    ``"14/48 współwłasność"`` → ``{'share': '14/48', 'form': 'współwłasność'}``
    """

    text = "" if line is None else str(line).strip()
    if not text:
        return {"share": "", "form": ""}
    return {
        "share": normalize_share(text),
        "form": extract_ownership_form(text),
    }


def format_ownership(share: Any, form: Any) -> str:
    """Łączy udział i formę w jeden opis do kolumny tabeli."""

    share_text = normalize_share(share)
    form_text = "" if form is None else str(form).strip()
    if share_text and form_text:
        return f"{share_text} {form_text}"
    return share_text or form_text
