"""Rozdzielanie położenia działki na miejscowość i ulicę.

W wypisach pole „Bliższe określenie położenia” bywa zapisane na wiele
sposobów i miesza obie informacje w jednej linii::

    MAKI, WYBICKIEGO J. 50   ->  miejscowość „Maki”, ulica „Wybickiego J. 50”
    Maki, ul. Górna 42       ->  miejscowość „Maki”, ulica „ul. Górna 42”
    ul. Górna 42             ->  sama ulica
    MAKI                     ->  sama miejscowość

Funkcje z tego modułu rozbijają taki zapis na dwa osobne pola, żeby
kolumny „Miejscowośc działki” i „Ulica Działki” w Wypisach wypełniały się
same. Zasada jest zachowawcza: gdy nie da się bezpiecznie orzec, gdzie
kończy się miejscowość, program woli zostawić tekst w polu ulicy, niż
zgadywać i rozdzielić go błędnie.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# Przedrostki jednoznacznie wskazujące, że dalej jest nazwa ulicy.
STREET_PREFIXES: tuple[str, ...] = (
    "ul", "ulica", "ulicy",
    "al", "aleja", "aleje", "alei",
    "os", "osiedle", "osiedla",
    "pl", "plac", "placu",
    "rondo", "ronda",
    "skwer", "bulwar", "pasaz", "pasaż",
    "droga", "dr",
)

# Wyrażenie wykrywające przedrostek ulicy na początku fragmentu tekstu.
_STREET_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in STREET_PREFIXES) + r")\.?\s+",
    re.IGNORECASE,
)

# Numer budynku na końcu: „50”, „42a”, „12/3”, „5 A”, „7B/2”.
_HOUSE_NUMBER_RE = re.compile(
    r"(?:^|\s)\d+[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]?(?:\s*[/-]\s*\d+[A-Za-z]?)?\.?$"
)

# Fragmenty, które nie są ani miejscowością, ani ulicą.
_NOISE = (
    "brak", "nie dotyczy", "n/d", "b/d", "-", "—", "brak danych",
)


class ParcelLocation(NamedTuple):
    """Rozdzielone położenie działki."""

    city: str
    street: str

    @property
    def is_empty(self) -> bool:
        return not (self.city or self.street)


def _clean(value: str) -> str:
    """Usuwa nadmiarowe spacje i znaki interpunkcyjne z brzegów."""

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.strip(" ,;:.")


def _titlecase_pl(value: str) -> str:
    """Zamienia ZAPIS WERSALIKAMI na Zapis Normalny.

    Tekst pisany normalnie zostaje bez zmian — poprawiamy tylko wypisy
    drukowane w całości wielkimi literami.
    """

    text = str(value or "")
    if not text or text != text.upper():
        return text

    def fix_word(word: str) -> str:
        # Skróty w rodzaju „J.” zostawiamy, resztę zapisujemy z wielkiej.
        parts = re.split(r"([-/])", word)
        out = []
        for part in parts:
            if part in "-/":
                out.append(part)
            elif len(part.rstrip(".")) <= 1:
                out.append(part.upper())
            elif re.match(r"^\d", part):
                # Numer domu: „12A” zostaje z wielką literą.
                out.append(part.upper())
            else:
                out.append(part[:1].upper() + part[1:].lower())
        return "".join(out)

    return " ".join(fix_word(w) for w in text.split())


def _normalize_street(value: str) -> str:
    """Porządkuje nazwę ulicy, zostawiając przedrostek małą literą."""

    text = _clean(value)
    if not text:
        return ""
    match = _STREET_PREFIX_RE.match(text)
    if match:
        prefix = match.group(0).strip()
        rest = text[match.end():]
        # „UL.” -> „ul.”, „Ulica” -> „ulica”
        prefix = prefix.lower()
        if not prefix.endswith(".") and prefix.rstrip(".") in ("ul", "al", "os", "pl", "dr"):
            prefix += "."
        return f"{prefix} {_titlecase_pl(rest)}".strip()
    return _titlecase_pl(text)


def has_street_prefix(value: str) -> bool:
    """Czy fragment zaczyna się od „ul.”, „al.”, „os.” itp."""

    return bool(_STREET_PREFIX_RE.match(_clean(value)))


def ends_with_house_number(value: str) -> bool:
    """Czy fragment kończy się numerem budynku."""

    text = _clean(value)
    if not text:
        return False
    # Sam numer bez nazwy nie jest jeszcze adresem ulicy.
    if re.fullmatch(r"\d+[A-Za-z]?(?:\s*[/-]\s*\d+[A-Za-z]?)?", text):
        return False
    return bool(_HOUSE_NUMBER_RE.search(text))


def looks_like_street(value: str) -> bool:
    """Czy fragment wygląda na ulicę, a nie na nazwę miejscowości."""

    text = _clean(value)
    if not text:
        return False
    return has_street_prefix(text) or ends_with_house_number(text)


def _is_noise(value: str) -> bool:
    return _clean(value).lower() in _NOISE


def split_parcel_location(value: str) -> ParcelLocation:
    """Rozdziela zapis położenia działki na miejscowość i ulicę.

    Reguły, od najpewniejszej:

    1. Jest przecinek — ostatni fragment wygląda na ulicę, więc trafia do
       ulicy, a wcześniejsze do miejscowości (``Maki, ul. Górna 42``).
       Gdy żaden fragment nie wygląda na ulicę, całość jest miejscowością.
    2. Brak przecinka, ale w środku stoi „ul.”/„al.”/„os.” — tekst przed
       przedrostkiem to miejscowość (``Maki ul. Górna 42``).
    3. Brak przecinka i przedrostka — gdy tekst kończy się numerem, całość
       traktujemy jako ulicę (``Górna 42``); w przeciwnym razie jako
       miejscowość (``Maki``).
    """

    text = _clean(value)
    if not text or _is_noise(text):
        return ParcelLocation("", "")

    # ── 1. Zapis z przecinkiem ──
    if "," in text:
        parts = [p for p in (_clean(p) for p in text.split(",")) if p and not _is_noise(p)]
        if not parts:
            return ParcelLocation("", "")
        if len(parts) == 1:
            return split_parcel_location(parts[0])

        if looks_like_street(parts[-1]):
            city = " ".join(_titlecase_pl(p) for p in parts[:-1])
            return ParcelLocation(_clean(city), _normalize_street(parts[-1]))

        # Żaden fragment nie przypomina ulicy — to sama miejscowość
        # (np. „Maki, gmina Żukowo”).
        return ParcelLocation(_titlecase_pl(parts[0]), "")

    # ── 2. Przedrostek ulicy w środku tekstu ──
    inner = re.search(
        r"\s(?:" + "|".join(re.escape(p) for p in STREET_PREFIXES) + r")\.?\s+",
        text,
        re.IGNORECASE,
    )
    if inner and not has_street_prefix(text):
        city = _clean(text[: inner.start()])
        street = _clean(text[inner.start():])
        if city:
            return ParcelLocation(_titlecase_pl(city), _normalize_street(street))

    # ── 3. Bez przecinka i bez przedrostka ──
    if looks_like_street(text):
        return ParcelLocation("", _normalize_street(text))
    return ParcelLocation(_titlecase_pl(text), "")


def split_many(values) -> ParcelLocation:
    """Scala kilka zapisów położenia w jedną parę miejscowość/ulica.

    Przydaje się, gdy właściciel ma kilka działek: powtórzone wartości
    pomijamy, a różne łączymy przecinkiem — tak jak dotąd robiły to
    Wypisy dla samej ulicy.
    """

    cities: list[str] = []
    streets: list[str] = []
    for raw in values or ():
        location = split_parcel_location(raw)
        if location.city and location.city not in cities:
            cities.append(location.city)
        if location.street and location.street not in streets:
            streets.append(location.street)
    return ParcelLocation(", ".join(cities), ", ".join(streets))
