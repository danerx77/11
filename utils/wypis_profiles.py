"""Profile odczytu wypisów z PDF — „co jest czym” w dokumencie.

Wypisy z różnych powiatów wyglądają inaczej: jeden pisze „Bliższe
określenie położenia”, drugi „Położenie działki”, trzeci „Adres
nieruchomości”. Zamiast zaszywać wszystkie warianty w kodzie, program
trzyma je jako **profile** — zestawy etykiet przypisanych do pól.

Profil składa się z:

* ``name``       — nazwa widoczna dla użytkownika,
* ``fields``     — słownik ``pole -> lista etykiet`` szukanych w PDF,
* ``markers``    — teksty, po których poznajemy, że dokument pasuje do
  tego profilu (np. nazwa urzędu w nagłówku),
* ``builtin``    — czy profil jest wbudowany (nie da się go usunąć).

Program zapamiętuje profile w konfiguracji, więc raz zdefiniowany układ
działa dla kolejnych wypisów z tego samego urzędu.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# ── Pola, które program potrafi odczytać z wypisu ────────────────────
# (klucz, etykieta w oknie, krótkie wyjaśnienie)
FIELD_DEFS: tuple[tuple[str, str, str], ...] = (
    ("voivodeship", "Województwo", "Nazwa województwa z nagłówka wypisu."),
    ("county", "Powiat", "Nazwa powiatu."),
    ("municipality", "Jednostka ewidencyjna / Gmina", "Gmina albo jednostka ewidencyjna."),
    ("precinct", "Obręb", "Nazwa obrębu ewidencyjnego."),
    ("precinct_number", "Nr obrębu", "Numer obrębu, zwykle przed jego nazwą."),
    ("parcel_number", "Numer działki", "Oznaczenie działki, np. 12/3."),
    ("identifier", "Identyfikator działki", "Pełny identyfikator, np. 110101_2.0010.12/3."),
    ("parcel_address", "Położenie działki", "Miejscowość i ulica działki."),
    ("area", "Powierzchnia", "Powierzchnia działki w hektarach."),
    ("kw", "Numer księgi wieczystej", "Numer KW, np. GD1G/00012345/6."),
    ("owner", "Właściciel / władający", "Blok z danymi właściciela."),
    ("share", "Udział", "Udział we współwłasności, np. 1/2."),
    ("ownership_form", "Forma władania", "Własność, współwłasność, użytkowanie wieczyste…"),
)

FIELD_KEYS: tuple[str, ...] = tuple(key for key, _l, _h in FIELD_DEFS)
FIELD_LABELS: dict[str, str] = {key: label for key, label, _h in FIELD_DEFS}
FIELD_HINTS: dict[str, str] = {key: hint for key, _l, hint in FIELD_DEFS}

CONFIG_KEY = "wypis_profiles"
ACTIVE_KEY = "wypis_active_profile"
AUTO_KEY = "wypis_profile_auto"

# ── Profil wbudowany: dotychczasowe zachowanie programu ──────────────
DEFAULT_PROFILE: dict[str, Any] = {
    "name": "Standardowy (EGiB)",
    "builtin": True,
    "markers": ["wypis z rejestru gruntów", "rejestru gruntów"],
    "fields": {
        "voivodeship": ["Województwo"],
        "county": ["Powiat"],
        "municipality": ["Jednostka ewidencyjna", "Gmina"],
        "precinct": ["Obręb ewidencyjny", "Obręb"],
        "precinct_number": ["Nr obrębu", "Numer obrębu"],
        "parcel_number": ["Oznaczenie działki", "Numer działki", "Nr działki"],
        "identifier": ["Identyfikator działki"],
        "parcel_address": [
            "Bliższe określenie położenia",
            "Położenie",
            "Położenie działki",
        ],
        "area": ["Powierzchnia działki", "Powierzchnia", "Pow."],
        "kw": ["Numer księgi wieczystej", "Księga wieczysta", "KW"],
        "owner": ["Właściciel", "Władający", "Osoba"],
        "share": ["Udział", "Udział w prawie"],
        "ownership_form": ["Forma władania", "Rodzaj prawa", "Tytuł władania"],
    },
}

# Dodatkowy profil pokazujący, że etykiety bywają inne.
SIMPLIFIED_PROFILE: dict[str, Any] = {
    "name": "Wypis uproszczony",
    "builtin": True,
    "markers": ["wypis uproszczony", "uproszczony z rejestru"],
    "fields": {
        "voivodeship": ["Województwo"],
        "county": ["Powiat"],
        "municipality": ["Jednostka ewidencyjna", "Gmina"],
        "precinct": ["Obręb"],
        "precinct_number": ["Nr obrębu"],
        "parcel_number": ["Oznaczenie działki", "Działka nr", "Działka"],
        "identifier": ["Identyfikator działki", "IDD"],
        "parcel_address": ["Położenie", "Adres nieruchomości", "Miejscowość"],
        "area": ["Powierzchnia", "Pow. [ha]"],
        "kw": ["Księga wieczysta", "Nr KW", "KW"],
        "owner": ["Właściciel", "Podmiot"],
        "share": ["Udział"],
        "ownership_form": ["Forma władania", "Rodzaj prawa"],
    },
}

BUILTIN_PROFILES: tuple[dict[str, Any], ...] = (DEFAULT_PROFILE, SIMPLIFIED_PROFILE)


# ── Pomocnicze ───────────────────────────────────────────────────────

def _fold(value: str) -> str:
    """Tekst bez ogonków i wielkich liter — do porównań."""

    table = str.maketrans(
        "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
        "acelnoszzACELNOSZZ",
    )
    return str(value or "").translate(table).lower().strip()


def normalize_profile(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Doprowadza zapisany profil do kompletnej, bezpiecznej postaci."""

    source = raw if isinstance(raw, Mapping) else {}
    fields: dict[str, list[str]] = {}
    raw_fields = source.get("fields")
    raw_fields = raw_fields if isinstance(raw_fields, Mapping) else {}

    for key in FIELD_KEYS:
        value = raw_fields.get(key, [])
        if isinstance(value, str):
            value = [value]
        labels: list[str] = []
        for label in value or []:
            text = str(label or "").strip()
            if text and text not in labels:
                labels.append(text)
        fields[key] = labels

    markers = source.get("markers", [])
    if isinstance(markers, str):
        markers = [markers]
    clean_markers = []
    for marker in markers or []:
        text = str(marker or "").strip()
        if text and text not in clean_markers:
            clean_markers.append(text)

    return {
        "name": str(source.get("name", "") or "Nowy profil").strip() or "Nowy profil",
        "builtin": bool(source.get("builtin", False)),
        "override": bool(source.get("override", True)),
        "markers": clean_markers,
        "fields": fields,
    }


def default_profiles() -> list[dict[str, Any]]:
    """Kopia profili wbudowanych."""

    return [normalize_profile(profile) for profile in BUILTIN_PROFILES]


def load_profiles(config: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Wczytuje profile z konfiguracji, uzupełniając brakujące wbudowane."""

    stored = []
    if isinstance(config, Mapping):
        raw = config.get(CONFIG_KEY)
        if isinstance(raw, list):
            stored = [normalize_profile(item) for item in raw if isinstance(item, Mapping)]

    if not stored:
        return default_profiles()

    # Profile wbudowane muszą istnieć zawsze — użytkownik mógł je usunąć
    # ze starszego pliku konfiguracji.
    names = {_fold(p["name"]) for p in stored}
    for builtin in default_profiles():
        if _fold(builtin["name"]) not in names:
            stored.append(builtin)
    return stored


def save_profiles(config: Any, profiles: Iterable[Mapping[str, Any]]) -> None:
    """Zapisuje profile do konfiguracji."""

    if config is None:
        return
    config[CONFIG_KEY] = [normalize_profile(p) for p in profiles]


def find_profile(profiles: Iterable[Mapping[str, Any]], name: str) -> dict[str, Any] | None:
    """Szuka profilu po nazwie (bez rozróżniania ogonków i wielkości liter)."""

    needle = _fold(name)
    for profile in profiles or ():
        if _fold(profile.get("name", "")) == needle:
            return normalize_profile(profile)
    return None


def should_override(profile: Mapping[str, Any] | None) -> bool:
    """Czy wzór ma nadpisywać wartości odczytane standardowo.

    Wzór własny (nie wbudowany) tworzy użytkownik świadomie dla swojego
    urzędu, więc jego przypisania mają poprawiać także to, co program
    odczytał błędnie — nie tylko uzupełniać puste pola.
    """

    clean = normalize_profile(profile)
    if clean["builtin"]:
        return False
    return bool(clean.get("override", True))


def labels_for(profile: Mapping[str, Any] | None, field: str) -> list[str]:
    """Etykiety przypisane do pola w danym profilu."""

    return normalize_profile(profile)["fields"].get(field, [])


# ── Dopasowanie profilu do dokumentu ─────────────────────────────────

def marker_matches(profile: Mapping[str, Any], text: str) -> bool:
    """Czy któryś znacznik profilu występuje w dokumencie."""

    haystack = _fold(text)
    if not haystack:
        return False
    return any(_fold(m) in haystack for m in normalize_profile(profile)["markers"])


def score_profile(profile: Mapping[str, Any], text: str) -> int:
    """Ocena dopasowania profilu do treści PDF.

    Znacznik (``markers``) liczy się potrójnie, bo jednoznacznie wskazuje
    wydawcę dokumentu; każda odnaleziona etykieta dokłada jeden punkt.
    """

    clean = normalize_profile(profile)
    haystack = _fold(text)
    if not haystack:
        return 0

    score = 0
    for marker in clean["markers"]:
        if _fold(marker) in haystack:
            score += 3
    for labels in clean["fields"].values():
        for label in labels:
            if _fold(label) in haystack:
                score += 1
                break
    return score


def detect_profile(
    profiles: Iterable[Mapping[str, Any]],
    text: str,
) -> tuple[dict[str, Any] | None, int]:
    """Wybiera profil najlepiej pasujący do tekstu PDF.

    Profil **własny** ma pierwszeństwo przed wbudowanym, o ile jego
    znacznik występuje w dokumencie. Skoro użytkownik świadomie opisał
    wypis ze swojego urzędu, to jego ustawienia mają decydować — nawet
    jeśli profil wbudowany rozpoznaje przypadkiem więcej etykiet.
    """

    best: dict[str, Any] | None = None
    best_rank: tuple[int, int] = (-1, -1)

    for profile in profiles or ():
        score = score_profile(profile, text)
        if score <= 0:
            continue
        clean = normalize_profile(profile)
        priority = 1 if (not clean["builtin"] and marker_matches(clean, text)) else 0
        rank = (priority, score)
        if rank > best_rank:
            best, best_rank = clean, rank

    return best, (best_rank[1] if best else 0)


# ── Odczyt wartości według profilu ───────────────────────────────────

def _label_pattern(label: str) -> re.Pattern:
    """Wyrażenie dopasowujące etykietę niezależnie od ogonków i spacji."""

    parts = []
    for char in str(label or "").strip():
        folded = _fold(char)
        if char.isspace():
            parts.append(r"\s+")
        elif folded and folded != char.lower():
            # Litera z ogonkiem: dopuszczamy obie postacie.
            parts.append(f"[{re.escape(char)}{re.escape(folded)}]")
        elif char.isalpha():
            parts.append(f"[{re.escape(char.lower())}{re.escape(char.upper())}]")
        else:
            parts.append(re.escape(char))
    body = "".join(parts)
    label_text = str(label or "").strip()
    # \b działa tylko obok znaku alfanumerycznego. Etykiety typu „Pow. [ha]”
    # kończą się nawiasem, więc granicę dodajemy warunkowo.
    prefix = r"\b" if label_text[:1].isalnum() else ""
    suffix = r"\b" if label_text[-1:].isalnum() else ""
    return re.compile(prefix + body + suffix + r"\s*:?\s*(.*)", re.IGNORECASE)


def extract_field(
    text: str,
    profile: Mapping[str, Any] | None,
    field: str,
    *,
    max_length: int = 200,
) -> str:
    """Wyciąga wartość pola z tekstu według etykiet z profilu.

    Wartość może stać po etykiecie w tej samej linii albo w następnej —
    oba układy występują w wypisach.
    """

    labels = labels_for(profile, field)
    if not labels or not str(text or "").strip():
        return ""

    lines = [re.sub(r"\s+", " ", line).strip() for line in str(text).split("\n")]

    for label in labels:
        pattern = _label_pattern(label)
        for index, line in enumerate(lines):
            if not line:
                continue
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(1).strip(" :,;-")
            if value:
                return value[:max_length]
            # Wartość w kolejnej niepustej linii.
            for nxt in lines[index + 1: index + 3]:
                candidate = nxt.strip(" :,;-")
                if candidate and not _looks_like_label(candidate, profile):
                    return candidate[:max_length]
    return ""


def _looks_like_label(value: str, profile: Mapping[str, Any] | None) -> bool:
    """Czy tekst sam jest etykietą innego pola."""

    folded = _fold(value)
    for labels in normalize_profile(profile)["fields"].values():
        for label in labels:
            if folded.startswith(_fold(label)):
                return True
    return False


def analyze_text(
    text: str,
    profile: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    """Zestawienie „co jest czym” dla podglądu w Ustawieniach.

    Zwraca listę rekordów: pole, jego etykieta, dopasowana etykieta z PDF
    i odczytana wartość. Dzięki temu użytkownik od razu widzi, które pola
    program rozpoznał, a które wymagają poprawki.
    """

    clean = normalize_profile(profile)
    haystack = _fold(text)
    rows: list[dict[str, str]] = []

    for key in FIELD_KEYS:
        labels = clean["fields"].get(key, [])
        matched = ""
        for label in labels:
            if _fold(label) in haystack:
                matched = label
                break
        value = extract_field(text, clean, key) if matched else ""
        rows.append({
            "field": key,
            "label": FIELD_LABELS[key],
            "matched_label": matched,
            "value": value,
            "status": "ok" if value else ("found" if matched else "missing"),
        })
    return rows


def summarize(rows: Iterable[Mapping[str, str]]) -> str:
    """Krótkie podsumowanie wyniku analizy."""

    rows = list(rows or ())
    total = len(rows)
    ok = sum(1 for r in rows if r.get("status") == "ok")
    found = sum(1 for r in rows if r.get("status") == "found")
    missing = total - ok - found
    return (
        f"Odczytano {ok} z {total} pól • "
        f"etykieta znaleziona, brak wartości: {found} • "
        f"nierozpoznane: {missing}."
    )
