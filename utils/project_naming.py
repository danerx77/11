"""Schematy nazw folderów projektów.

Nazwa folderu projektu powstaje z czterech danych: nazwy, numeru projektu,
miejscowości i terminu. Użytkownik może wybrać gotowy wariant albo wpisać
własny wzór, a osobno zdecydować, czym zastąpić ukośnik w numerze projektu
(``OBI/23/23220`` → ``OBI.23.23220`` albo ``OBI-23-23220``).

Ustawienia domyślne odtwarzają dotychczasowe zachowanie programu:
``Maki OBI.23.23220 04-12-2026``.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

TEMPLATE_KEY = "project_folder_template"
SYMBOL_SEPARATOR_KEY = "project_folder_symbol_separator"
SPACE_REPLACEMENT_KEY = "project_folder_space_replacement"
DATE_FORMAT_KEY = "project_folder_date_format"

# Dotychczasowa nazwa folderu: miejscowość, numer projektu, termin.
DEFAULT_TEMPLATE = "{miasto} {symbol} {termin}"
DEFAULT_SYMBOL_SEPARATOR = "."
DEFAULT_SPACE_REPLACEMENT = " "
DEFAULT_DATE_FORMAT = "dd-MM-yyyy"

PROJECT_FOLDER_DEFAULTS: dict[str, str] = {
    TEMPLATE_KEY: DEFAULT_TEMPLATE,
    SYMBOL_SEPARATOR_KEY: DEFAULT_SYMBOL_SEPARATOR,
    SPACE_REPLACEMENT_KEY: DEFAULT_SPACE_REPLACEMENT,
    DATE_FORMAT_KEY: DEFAULT_DATE_FORMAT,
}

# Gotowe wzory pokazywane na liście wyboru.
TEMPLATE_PRESETS: tuple[tuple[str, str], ...] = (
    ("Miejscowość, numer, termin", "{miasto} {symbol} {termin}"),
    ("Termin, miejscowość, numer", "{termin} {miasto} {symbol}"),
    ("Numer, miejscowość, termin", "{symbol} {miasto} {termin}"),
    ("Miejscowość i numer", "{miasto} {symbol}"),
    ("Numer i miejscowość", "{symbol} {miasto}"),
    ("Termin i miejscowość", "{termin} {miasto}"),
    ("Nazwa i numer w nawiasie", "{nazwa} [{symbol}]"),
    ("Nazwa, miejscowość, termin", "{nazwa} {miasto} {termin}"),
    ("Sama nazwa projektu", "{nazwa}"),
)

# Czym zastąpić ukośnik w numerze projektu (w nazwie pliku jest zabroniony).
SYMBOL_SEPARATOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("Kropka — OBI.23.23220", "."),
    ("Myślnik — OBI-23-23220", "-"),
    ("Podkreślnik — OBI_23_23220", "_"),
    ("Spacja — OBI 23 23220", " "),
    ("Bez separatora — OBI2323220", ""),
)

SPACE_REPLACEMENT_CHOICES: tuple[tuple[str, str], ...] = (
    ("Zostaw spacje", " "),
    ("Zamień na myślnik", "-"),
    ("Zamień na podkreślnik", "_"),
)

DATE_FORMAT_CHOICES: tuple[tuple[str, str], ...] = (
    ("04-12-2026 (dzień-miesiąc-rok)", "dd-MM-yyyy"),
    ("04.12.2026 (z kropkami)", "dd.MM.yyyy"),
    ("2026-12-04 (rok na początku)", "yyyy-MM-dd"),
    ("2026.12.04 (rok, z kropkami)", "yyyy.MM.dd"),
    ("12-2026 (sam miesiąc i rok)", "MM-yyyy"),
)

PLACEHOLDERS: tuple[tuple[str, str], ...] = (
    ("{nazwa}", "Nazwa projektu z formularza"),
    ("{symbol}", "Numer projektu, np. OBI.23.23220"),
    ("{miasto}", "Miejscowość"),
    ("{termin}", "Termin realizacji"),
)

# Znaki zakazane w nazwach plików i folderów Windows.
_FORBIDDEN = re.compile(r'[\\/*?:"<>|]')


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _setting(config: Mapping[str, Any] | None, key: str, default: str) -> str:
    if not isinstance(config, Mapping):
        return default
    value = config.get(key, default)
    if value is None:
        return default
    return str(value)


def format_symbol(symbol: Any, separator: str = DEFAULT_SYMBOL_SEPARATOR) -> str:
    """Zamienia ukośniki w numerze projektu na wybrany separator."""

    text = _text(symbol)
    if not text:
        return ""
    text = text.replace("\\", "/")
    parts = [part.strip() for part in text.split("/")]
    parts = [part for part in parts if part]
    return separator.join(parts)


def sanitize_folder_name(name: Any) -> str:
    """Usuwa znaki zabronione i nadmiarowe spacje z nazwy folderu."""

    text = _text(name)
    if not text:
        return ""
    text = _FORBIDDEN.sub("_", text)
    text = re.sub(r"\s+", " ", text)
    # Windows nie pozwala na kropkę ani spację na końcu nazwy folderu.
    return text.strip(" .")


def build_project_folder_name(
    config: Mapping[str, Any] | None,
    *,
    name: Any = "",
    symbol: Any = "",
    city: Any = "",
    deadline: Any = "",
    template: str | None = None,
) -> str:
    """Buduje nazwę folderu projektu według wybranego schematu.

    Puste dane nie zostawiają po sobie podwójnych spacji, a gdy wzór
    da pustą nazwę, wracamy do nazwy projektu.
    """

    tpl = template if template is not None else _setting(
        config, TEMPLATE_KEY, DEFAULT_TEMPLATE
    )
    tpl = tpl.strip() or DEFAULT_TEMPLATE
    separator = _setting(config, SYMBOL_SEPARATOR_KEY, DEFAULT_SYMBOL_SEPARATOR)

    values = {
        "nazwa": _text(name),
        "symbol": format_symbol(symbol, separator),
        "miasto": _text(city),
        "termin": _text(deadline),
    }

    result = tpl
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    # Nieznane pola nie mogą zostać w nazwie folderu.
    result = re.sub(r"\{[a-ząćęłńóśźż_]+\}", "", result, flags=re.I)
    # Puste nawiasy po nieuzupełnionych danych, np. "Nazwa []".
    result = re.sub(r"\[\s*\]|\(\s*\)", "", result)

    result = sanitize_folder_name(result)
    if not result:
        result = sanitize_folder_name(values["nazwa"]) or sanitize_folder_name(
            values["symbol"]
        )

    space_replacement = _setting(
        config, SPACE_REPLACEMENT_KEY, DEFAULT_SPACE_REPLACEMENT
    )
    if space_replacement and space_replacement != " ":
        result = result.replace(" ", space_replacement)
        result = re.sub(re.escape(space_replacement) + r"{2,}", space_replacement, result)
        result = result.strip(space_replacement)

    return result


def project_folder_preview(
    config: Mapping[str, Any] | None,
    *,
    template: str | None = None,
    name: str = "Modernizacja linii",
    symbol: str = "OBI/23/23220",
    city: str = "Maki",
    deadline: str = "04-12-2026",
) -> str:
    """Zwraca przykładową nazwę folderu dla podglądu w Ustawieniach."""

    return build_project_folder_name(
        config,
        name=name,
        symbol=symbol,
        city=city,
        deadline=deadline,
        template=template,
    )
