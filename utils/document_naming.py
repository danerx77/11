"""Konfigurowalne nazwy plików Oświadczeń woli i Pism przewodnich.

Nazwy powstają z szablonu z polami w nawiasach klamrowych. Domyślne szablony
odtwarzają dotychczasowe nazewnictwo programu, więc bez zmian w Ustawieniach
pliki nazywają się dokładnie tak jak wcześniej.

Osobno obsługiwany jest dopisek z numerem działki. Użytkownik chciał, aby numer
działki trafiał na koniec nazwy tylko wtedy, gdy właściciel ma dokładnie jedną
działkę — służy do tego tryb ``single`` (patrz PARCEL_SUFFIX_MODES). Domyślnie
program zachowuje dotychczasowe nazwy, czyli tryb ``none``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
import unicodedata
from typing import Any

from utils.parcel_sorting import normalize_parcel_number, sort_parcel_numbers

# Znaki zabronione w nazwach plików Windows.
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
# Ukośnik jest zabroniony, ale występuje w numerach działek i projektów.
# Zamieniamy go na myślnik, aby „12/3” pozostało czytelne jako „12-3”,
# zamiast zlewać się w „123”.
_PATH_SEPARATORS = re.compile(r"[/\\]+")
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")

DECLARATION_TEMPLATE_KEY = "decl_filename_template"
COVER_TEMPLATE_KEY = "cover_filename_template"
DECLARATION_PARCEL_MODE_KEY = "decl_filename_parcel_mode"
COVER_PARCEL_MODE_KEY = "cover_filename_parcel_mode"
DECLARATION_PARCEL_LIMIT_KEY = "decl_filename_parcel_limit"
COVER_PARCEL_LIMIT_KEY = "cover_filename_parcel_limit"
DECLARATION_PARCEL_SEPARATOR_KEY = "decl_filename_parcel_separator"
COVER_PARCEL_SEPARATOR_KEY = "cover_filename_parcel_separator"
NAME_STYLE_KEY = "filename_owner_name_style"
ASCII_KEY = "filename_ascii_only"
SPACE_KEY = "filename_space_replacement"

DEFAULT_DECLARATION_TEMPLATE = "Oświadczenie woli {typ} {nazwisko}{adres}{dzialki}"
DEFAULT_COVER_TEMPLATE = "Pismo przewodnie {nazwisko}{adres}{dzialki}"

# Gotowe warianty pokazywane w Ustawieniach jako lista wyboru.
DECLARATION_TEMPLATE_PRESETS = (
    (DEFAULT_DECLARATION_TEMPLATE, "Obecny — Oświadczenie woli budowa J.Kowalski"),
    (
        "Oświadczenie woli {typ} {nazwisko} dz. {dzialki_lista}{adres}",
        "Z numerami działek — Oświadczenie woli budowa J.Kowalski dz. 12-3",
    ),
    (
        "{typ_wielkimi} {nazwisko}{adres}{dzialki}",
        "Krótki — BUDOWA J.Kowalski",
    ),
    (
        "{projekt} Oświadczenie woli {typ} {nazwisko}{adres}{dzialki}",
        "Z numerem projektu na początku",
    ),
    (
        "{data} Oświadczenie woli {typ} {nazwisko}{adres}{dzialki}",
        "Z datą na początku",
    ),
    (
        "Oświadczenie woli {typ} {nazwisko_pelne}{adres}{dzialki}",
        "Z pełnym imieniem i nazwiskiem",
    ),
    (
        "Oświadczenie woli {typ} {obreb} {nazwisko}{dzialki}",
        "Z nazwą obrębu",
    ),
)

COVER_TEMPLATE_PRESETS = (
    (DEFAULT_COVER_TEMPLATE, "Obecny — Pismo przewodnie J.Kowalski"),
    (
        "Pismo przewodnie {nazwisko} dz. {dzialki_lista}{adres}",
        "Z numerami działek — Pismo przewodnie J.Kowalski dz. 12-3",
    ),
    (
        "{projekt} Pismo przewodnie {nazwisko}{adres}{dzialki}",
        "Z numerem projektu na początku",
    ),
    (
        "{data} Pismo przewodnie {nazwisko}{adres}{dzialki}",
        "Z datą na początku",
    ),
    (
        "Pismo przewodnie {nazwisko_pelne}{adres}{dzialki}",
        "Z pełnym imieniem i nazwiskiem",
    ),
    (
        "Pismo przewodnie {obreb} {nazwisko}{dzialki}",
        "Z nazwą obrębu",
    ),
)

# Tryby dopisywania numerów działek na końcu nazwy pliku.
PARCEL_SUFFIX_MODES = (
    ("none", "Nigdy nie dodawaj numeru działki"),
    ("single", "Tylko gdy właściciel ma dokładnie jedną działkę"),
    ("always", "Zawsze dodawaj wszystkie działki"),
    ("limit", "Dodawaj do ustalonej liczby działek, potem skrót „i inne”"),
)

NAME_STYLES = (
    ("initials", "Inicjał imienia i nazwisko (J.Kowalski)"),
    ("full", "Pełne imię i nazwisko (Jan Kowalski)"),
    ("last_first", "Nazwisko i imię (Kowalski Jan)"),
    ("last_only", "Samo nazwisko (Kowalski)"),
)

SPACE_REPLACEMENTS = (
    (" ", "Zostaw spacje"),
    ("_", "Zamień spacje na podkreślenia"),
    ("-", "Zamień spacje na myślniki"),
)

# Opis pól dostępnych w szablonie — pokazywany w Ustawieniach.
TEMPLATE_FIELDS = (
    ("{nazwisko}", "Nazwisko wg wybranego stylu, np. J.Kowalski"),
    ("{nazwisko_pelne}", "Pełne imię i nazwisko właściciela"),
    ("{imie}", "Samo imię"),
    ("{typ}", "budowa / demontaz (tylko Oświadczenia)"),
    ("{typ_wielkimi}", "BUDOWA / DEMONTAZ (tylko Oświadczenia)"),
    ("{dzialki}", "Automatyczny dopisek działek wg reguły poniżej"),
    ("{dzialki_lista}", "Numery działek zawsze, bez reguły"),
    ("{dzialka}", "Pierwszy numer działki"),
    ("{liczba_dzialek}", "Liczba działek właściciela"),
    ("{adres}", "Rozróżnienie drugiego adresu, np. „ K”"),
    ("{projekt}", "Numer / symbol projektu"),
    ("{data}", "Data z formularza"),
    ("{miejscowosc}", "Miejscowość działki"),
    ("{obreb}", "Obręb ewidencyjny"),
    ("{gmina}", "Jednostka ewidencyjna / gmina"),
)


def document_naming_defaults() -> dict[str, Any]:
    """Zwraca domyślne ustawienia nazewnictwa (zgodne z dotychczasowymi nazwami)."""

    return {
        DECLARATION_TEMPLATE_KEY: DEFAULT_DECLARATION_TEMPLATE,
        COVER_TEMPLATE_KEY: DEFAULT_COVER_TEMPLATE,
        # Domyślnie nazwy plików są dokładnie takie jak dotychczas — dopisek
        # z numerem działki jest opcją, którą użytkownik włącza w Ustawieniach.
        DECLARATION_PARCEL_MODE_KEY: "none",
        COVER_PARCEL_MODE_KEY: "none",
        # Domyślnie w nazwie mieści się jeden numer działki.
        DECLARATION_PARCEL_LIMIT_KEY: 1,
        COVER_PARCEL_LIMIT_KEY: 1,
        DECLARATION_PARCEL_SEPARATOR_KEY: ", ",
        COVER_PARCEL_SEPARATOR_KEY: ", ",
        NAME_STYLE_KEY: "initials",
        ASCII_KEY: False,
        SPACE_KEY: " ",
    }


def _clean(value: object) -> str:
    return " ".join(str("" if value is None else value).split()).strip()


def format_owner_name(first_name: object, last_name: object, style: str = "initials") -> str:
    """Buduje część nazwy pliku z danych właściciela.

    Styl ``initials`` zachowuje dotychczasowe zachowanie programu, łącznie z
    obsługą par małżeńskich („Agata i Eryk” → ``A.E.Paradowscy``).
    """

    first = _clean(first_name)
    last = _clean(last_name)

    if style == "full":
        combined = f"{first} {last}".strip()
        return combined or last or first or "BrakNazwiska"
    if style == "last_first":
        combined = f"{last} {first}".strip()
        return combined or last or first or "BrakNazwiska"
    if style == "last_only":
        return last or first or "BrakNazwiska"

    names = [part for part in re.split(r"\s+i\s+|\s+", first) if part]
    initials = "".join(f"{part[0].upper()}." for part in names)
    if not initials and not last:
        return "BrakNazwiska"
    return f"{initials}{last}"


def format_parcel_suffix(
    parcels: Iterable[object],
    *,
    mode: str = "single",
    limit: int = 1,
    separator: str = ", ",
) -> str:
    """Buduje dopisek z numerami działek zgodnie z wybraną regułą.

    Tryb ``single`` realizuje prośbę: numer działki trafia do nazwy tylko wtedy,
    gdy właściciel ma dokładnie jedną działkę.
    """

    numbers = [
        normalized
        for value in parcels
        if (normalized := normalize_parcel_number(_parcel_number(value)))
    ]
    # Usuwamy duplikaty i porządkujemy naturalnie, aby nazwa była powtarzalna.
    numbers = sort_parcel_numbers(numbers, unique=True)
    if not numbers or mode == "none":
        return ""

    if mode == "single":
        return numbers[0] if len(numbers) == 1 else ""

    if mode == "limit":
        try:
            maximum = max(1, int(limit))
        except (TypeError, ValueError):
            maximum = 3
        if len(numbers) > maximum:
            shown = separator.join(numbers[:maximum])
            return f"{shown} i inne"
        return separator.join(numbers)

    return separator.join(numbers)


def _parcel_number(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("number", ""))
    return str("" if value is None else value)


def _strip_diacritics(value: str) -> str:
    replaced = value.translate(str.maketrans({"ł": "l", "Ł": "L"}))
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", replaced)
        if not unicodedata.combining(char)
    )


def sanitize_filename(name: object, *, ascii_only: bool = False, space: str = " ") -> str:
    """Usuwa znaki zabronione w Windows i porządkuje odstępy w nazwie."""

    text = str("" if name is None else name)
    text = _PATH_SEPARATORS.sub("-", text)
    text = _INVALID_FILENAME_CHARS.sub("", text)
    if ascii_only:
        text = _strip_diacritics(text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if space and space != " ":
        text = text.replace(" ", space)
        text = re.sub(re.escape(space) + r"{2,}", space, text)
    return text or "dokument"


def build_document_filename(
    template: object,
    values: Mapping[str, Any],
    *,
    extension: str = ".docx",
    ascii_only: bool = False,
    space: str = " ",
    fallback_template: str = "",
) -> str:
    """Buduje nazwę pliku z szablonu, ignorując nieznane pola.

    Nierozpoznane pole jest zastępowane pustym tekstem, więc literówka w
    szablonie nie przerywa generowania dokumentów.
    """

    text = _clean(template) or _clean(fallback_template) or "dokument"

    def replace(match: re.Match[str]) -> str:
        return str(values.get(match.group(1), "") or "")

    filled = _PLACEHOLDER_RE.sub(replace, text)
    filled = sanitize_filename(filled, ascii_only=ascii_only, space=space)

    if extension and not filled.lower().endswith(extension.lower()):
        filled = f"{filled}{extension}"
    return filled


def _parcel_values(
    parcels: Sequence[object],
    *,
    mode: str,
    limit: int,
    separator: str,
) -> dict[str, str]:
    numbers = sort_parcel_numbers(
        (_parcel_number(parcel) for parcel in parcels), unique=True
    )
    suffix = format_parcel_suffix(parcels, mode=mode, limit=limit, separator=separator)
    return {
        "dzialki": f" {suffix}" if suffix else "",
        "dzialki_lista": separator.join(numbers),
        "dzialka": numbers[0] if numbers else "",
        "liczba_dzialek": str(len(numbers)),
    }


def declaration_filename(
    settings: Mapping[str, Any] | None,
    *,
    declaration_type: object = "",
    first_name: object = "",
    last_name: object = "",
    full_name: object = "",
    address_suffix: object = "",
    parcels: Sequence[object] = (),
    project_number: object = "",
    date_str: object = "",
    location: object = "",
    precinct: object = "",
    municipality: object = "",
) -> str:
    """Zwraca nazwę pliku Oświadczenia woli zgodną z Ustawieniami."""

    config = dict(document_naming_defaults())
    if isinstance(settings, Mapping):
        config.update({key: settings[key] for key in config if key in settings})

    style = str(config.get(NAME_STYLE_KEY, "initials"))
    short_name = format_owner_name(first_name, last_name, style)
    full = _clean(full_name) or _clean(f"{first_name} {last_name}")
    type_text = _clean(declaration_type)

    values: dict[str, Any] = {
        "nazwisko": short_name,
        "nazwisko_pelne": full or short_name,
        "imie": _clean(first_name),
        "typ": type_text,
        "typ_wielkimi": _strip_diacritics(type_text).upper(),
        "adres": _clean(address_suffix) and f" {_clean(address_suffix)}",
        "projekt": _clean(project_number),
        "data": _clean(date_str),
        "miejscowosc": _clean(location),
        "obreb": _clean(precinct),
        "gmina": _clean(municipality),
    }
    values.update(
        _parcel_values(
            list(parcels),
            mode=str(config.get(DECLARATION_PARCEL_MODE_KEY, "single")),
            limit=config.get(DECLARATION_PARCEL_LIMIT_KEY, 1),
            separator=str(config.get(DECLARATION_PARCEL_SEPARATOR_KEY, ", ")),
        )
    )

    return build_document_filename(
        config.get(DECLARATION_TEMPLATE_KEY),
        values,
        ascii_only=bool(config.get(ASCII_KEY, False)),
        space=str(config.get(SPACE_KEY, " ")),
        fallback_template=DEFAULT_DECLARATION_TEMPLATE,
    )


def cover_letter_filename(
    settings: Mapping[str, Any] | None,
    *,
    first_name: object = "",
    last_name: object = "",
    full_name: object = "",
    address_suffix: object = "",
    parcels: Sequence[object] = (),
    project_number: object = "",
    date_str: object = "",
    location: object = "",
    precinct: object = "",
    municipality: object = "",
) -> str:
    """Zwraca nazwę pliku Pisma przewodniego zgodną z Ustawieniami."""

    config = dict(document_naming_defaults())
    if isinstance(settings, Mapping):
        config.update({key: settings[key] for key in config if key in settings})

    style = str(config.get(NAME_STYLE_KEY, "initials"))
    short_name = format_owner_name(first_name, last_name, style)
    full = _clean(full_name) or _clean(f"{first_name} {last_name}")

    values: dict[str, Any] = {
        "nazwisko": short_name,
        "nazwisko_pelne": full or short_name,
        "imie": _clean(first_name),
        "typ": "",
        "typ_wielkimi": "",
        "adres": _clean(address_suffix) and f" {_clean(address_suffix)}",
        "projekt": _clean(project_number),
        "data": _clean(date_str),
        "miejscowosc": _clean(location),
        "obreb": _clean(precinct),
        "gmina": _clean(municipality),
    }
    values.update(
        _parcel_values(
            list(parcels),
            mode=str(config.get(COVER_PARCEL_MODE_KEY, "single")),
            limit=config.get(COVER_PARCEL_LIMIT_KEY, 1),
            separator=str(config.get(COVER_PARCEL_SEPARATOR_KEY, ", ")),
        )
    )

    return build_document_filename(
        config.get(COVER_TEMPLATE_KEY),
        values,
        ascii_only=bool(config.get(ASCII_KEY, False)),
        space=str(config.get(SPACE_KEY, " ")),
        fallback_template=DEFAULT_COVER_TEMPLATE,
    )


def preview_declaration_filename(settings: Mapping[str, Any] | None) -> str:
    """Podgląd nazwy w Ustawieniach — jedna działka i przykładowe dane."""

    return declaration_filename(
        settings,
        declaration_type="budowa",
        first_name="Jan",
        last_name="Kowalski",
        full_name="Jan Kowalski",
        parcels=["123/4"],
        project_number="OBI/123/2026",
        date_str="2026-09-03",
        location="Gdynia",
        precinct="Polki",
        municipality="Żukowo",
    )


def preview_cover_filename(settings: Mapping[str, Any] | None) -> str:
    """Podgląd nazwy Pisma przewodniego z dwiema działkami."""

    return cover_letter_filename(
        settings,
        first_name="Jan",
        last_name="Kowalski",
        full_name="Jan Kowalski",
        parcels=["123/4", "123/5"],
        project_number="OBI/123/2026",
        date_str="2026-09-03",
        location="Gdynia",
        precinct="Polki",
        municipality="Żukowo",
    )
