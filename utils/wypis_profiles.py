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
from pathlib import Path
from typing import Any, Iterable, Mapping

from utils.global_settings import (
    load_json_dict,
    save_json_dict,
    wypis_profiles_path,
)

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
    ("parcel_address", "Położenie działki", "Miejscowość i ulica działki razem."),
    ("parcel_city", "Miejscowość działki", "Sama miejscowość, bez ulicy."),
    ("parcel_street", "Ulica działki", "Sama ulica z numerem, np. ul. Polna 3."),
    ("land_use", "Opis użytku", "Oznaczenie użytku, np. RIVa, dr, Bi."),
    ("area", "Powierzchnia", "Powierzchnia działki w hektarach."),
    ("kw", "Numer księgi wieczystej", "Numer KW, np. GD1G/00012345/6."),
    ("owner", "Właściciel / władający", "Blok z danymi właściciela."),
    ("owner_address", "Adres właściciela", "Adres zamieszkania lub siedziby."),
    ("owner_city", "Miejscowość właściciela", "Miejscowość z adresu właściciela."),
    ("pesel", "PESEL", "Numer PESEL właściciela."),
    ("nip", "NIP", "Numer NIP właściciela lub firmy."),
    ("regon", "REGON", "Numer REGON instytucji."),
    ("share", "Udział", "Udział we współwłasności, np. 1/2."),
    ("ownership_form", "Forma władania", "Własność, współwłasność, użytkowanie wieczyste…"),
    ("document_date", "Data wypisu", "Data sporządzenia wypisu."),
    ("document_number", "Numer wypisu", "Znak sprawy lub numer kancelaryjny."),
    ("office", "Urząd wydający", "Starostwo lub urząd, który wydał wypis."),
)

FIELD_KEYS: tuple[str, ...] = tuple(key for key, _l, _h in FIELD_DEFS)
FIELD_LABELS: dict[str, str] = {key: label for key, label, _h in FIELD_DEFS}

#: Przedrostek kluczy pól dodanych przez użytkownika. Dzięki niemu wiadomo,
#: które pola można usunąć i zmienić im nazwę, a których ruszać nie wolno.
CUSTOM_PREFIX = "custom_"

#: Skąd czytać wartość względem nazwy pola.
DIRECTION_AUTO = "auto"        # program sam decyduje (jak dotąd)
DIRECTION_RIGHT = "right"      # zawsze z prawej strony
DIRECTION_BELOW = "below"      # zawsze spod spodu
DIRECTION_LEFT = "left"        # zawsze obok, po lewej stronie
DIRECTION_ABOVE = "above"      # zawsze nad nazwą pola
DIRECTION_BELOW2 = "below2"    # drugi wiersz pod spodem
DIRECTION_PICK = "pick"        # wskazana ręcznie pozycja w wierszu

DIRECTIONS: tuple[tuple[str, str], ...] = (
    (DIRECTION_AUTO, "🔎 Sam wybierz"),
    (DIRECTION_RIGHT, "➡️ Obok, z prawej"),
    (DIRECTION_LEFT, "⬅️ Obok, z lewej"),
    (DIRECTION_BELOW, "⬇️ Pod spodem"),
    (DIRECTION_BELOW2, "⬇️⬇️ Dwa pod spodem"),
    (DIRECTION_ABOVE, "⬆️ Nad nazwą"),
    (DIRECTION_PICK, "🎯 Wybrana pozycja"),
)

DIRECTION_LABELS: dict[str, str] = dict(DIRECTIONS)


def field_direction(profile: Mapping[str, Any] | None, key: str) -> str:
    """Kierunek odczytu ustawiony dla pola."""

    if isinstance(profile, Mapping):
        raw = profile.get("directions")
        if isinstance(raw, Mapping):
            wartosc = str(raw.get(key, "") or "").strip()
            if wartosc in DIRECTION_LABELS:
                return wartosc
    return DIRECTION_AUTO


def is_custom_field(key: str) -> bool:
    """Czy to pole dodane przez użytkownika (a nie wbudowane)?"""

    return str(key or "").startswith(CUSTOM_PREFIX)


def custom_field_key(label: str, taken: Iterable[str] = ()) -> str:
    """Buduje klucz nowego pola na podstawie jego nazwy."""

    podstawa = _fold(str(label or "").strip()).replace(" ", "_")
    podstawa = "".join(z for z in podstawa if z.isalnum() or z == "_").strip("_")
    if not podstawa:
        podstawa = "pole"

    zajete = set(taken)
    klucz = f"{CUSTOM_PREFIX}{podstawa}"
    numer = 2
    while klucz in zajete:
        klucz = f"{CUSTOM_PREFIX}{podstawa}_{numer}"
        numer += 1
    return klucz


def profile_field_defs(
    profile: Mapping[str, Any] | None,
) -> list[tuple[str, str, str]]:
    """Lista pól do pokazania: wbudowane plus dodane przez użytkownika.

    Pola można ukryć (klucz w ``hidden_fields``) — wtedy nie zaśmiecają
    tabeli. Wbudowanych nie usuwamy na stałe, żeby dało się je przywrócić.
    """

    ukryte = set()
    wlasne: dict[str, str] = {}
    if isinstance(profile, Mapping):
        raw_hidden = profile.get("hidden_fields")
        if isinstance(raw_hidden, (list, tuple, set)):
            ukryte = {str(k) for k in raw_hidden}
        raw_custom = profile.get("custom_fields")
        if isinstance(raw_custom, Mapping):
            wlasne = {
                str(k): str(v).strip()
                for k, v in raw_custom.items()
                if str(v or "").strip()
            }

    defs = [
        (key, label, hint)
        for key, label, hint in FIELD_DEFS
        if key not in ukryte
    ]
    for key, label in wlasne.items():
        if key in ukryte:
            continue
        defs.append((key, label, "Pole dodane przez Ciebie."))
    return defs


def profile_field_keys(profile: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Klucze pól widocznych w danym wzorze."""

    return tuple(key for key, _l, _h in profile_field_defs(profile))


def profile_field_labels(profile: Mapping[str, Any] | None) -> dict[str, str]:
    """Nazwy pól widocznych w danym wzorze."""

    return {key: label for key, label, _h in profile_field_defs(profile)}
FIELD_HINTS: dict[str, str] = {key: hint for key, _l, hint in FIELD_DEFS}

# Wzory mieszkają w osobnym pliku ``dane/wypis_profiles.json``. Poniższe
# klucze pochodzą z wcześniejszej wersji, gdy wszystko trafiało do
# ``app_config.json`` — czytamy je jeszcze przy przenoszeniu starych danych,
# ale program już ich nie zapisuje.
CONFIG_KEY = "wypis_profiles"
ACTIVE_KEY = "wypis_active_profile"
AUTO_KEY = "wypis_profile_auto"

#: Wersja formatu pliku — ułatwia późniejsze zmiany budowy zapisu.
FILE_VERSION = 1

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
        "parcel_city": ["Miejscowość", "Miejscowość działki"],
        "parcel_street": ["Ulica", "Ulica działki", "Adres działki"],
        "land_use": ["Opis użytku", "Użytek", "Oznaczenie użytku", "Rodzaj użytku"],
        "area": ["Powierzchnia działki", "Powierzchnia", "Pow."],
        "kw": ["Numer księgi wieczystej", "Księga wieczysta", "KW"],
        "owner": ["Właściciel", "Władający", "Osoba"],
        "owner_address": ["Adres właściciela", "Adres zamieszkania", "Adres", "Siedziba"],
        "owner_city": ["Miejscowość właściciela", "Miejscowość zamieszkania"],
        "pesel": ["PESEL", "Nr PESEL"],
        "nip": ["NIP", "Nr NIP"],
        "regon": ["REGON", "Nr REGON"],
        "share": ["Udział", "Udział w prawie"],
        "ownership_form": ["Forma władania", "Rodzaj prawa", "Tytuł władania"],
        "document_date": ["Data wypisu", "Data sporządzenia", "Data wydania"],
        "document_number": ["Numer wypisu", "Znak sprawy", "Nr sprawy", "Znak"],
        "office": ["Starostwo Powiatowe", "Starostwo", "Urząd Miasta", "Urząd Gminy"],
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
        "parcel_city": ["Miejscowość"],
        "parcel_street": ["Ulica", "Adres"],
        "land_use": ["Użytek", "Opis użytku"],
        "area": ["Powierzchnia", "Pow. [ha]"],
        "kw": ["Księga wieczysta", "Nr KW", "KW"],
        "owner": ["Właściciel", "Podmiot"],
        "owner_address": ["Adres właściciela", "Adres zamieszkania", "Siedziba"],
        "owner_city": ["Miejscowość właściciela"],
        "pesel": ["PESEL"],
        "nip": ["NIP"],
        "regon": ["REGON"],
        "share": ["Udział"],
        "ownership_form": ["Forma władania", "Rodzaj prawa"],
        "document_date": ["Data wypisu", "Data"],
        "document_number": ["Numer wypisu", "Znak sprawy"],
        "office": ["Starostwo", "Urząd"],
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

    klucze_pol = list(FIELD_KEYS) + [
        str(k) for k in raw_fields if is_custom_field(str(k))
    ]
    for key in klucze_pol:
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

    # Wartości poprawione ręcznie przez użytkownika — mają pierwszeństwo
    # przed tym, co program odczyta z dokumentu.
    raw_manual = source.get("manual_values")
    raw_manual = raw_manual if isinstance(raw_manual, Mapping) else {}
    manual_values = {
        str(key): str(value).strip()
        for key, value in raw_manual.items()
        if (str(key) in FIELD_KEYS or is_custom_field(str(key)))
        and str(value or "").strip()
    }

    # Pola dodane przez użytkownika: {klucz: nazwa}. Trzymamy je razem
    # ze wzorem, bo w różnych urzędach wypisy mają różne rubryki.
    raw_custom = source.get("custom_fields")
    raw_custom = raw_custom if isinstance(raw_custom, Mapping) else {}
    custom_fields: dict[str, str] = {}
    for key, value in raw_custom.items():
        klucz = str(key or "").strip()
        nazwa = str(value or "").strip()
        if klucz.startswith(CUSTOM_PREFIX) and nazwa:
            custom_fields[klucz] = nazwa

    # Kierunek odczytu ustawiony ręcznie dla poszczególnych pól.
    raw_dirs = source.get("directions")
    raw_dirs = raw_dirs if isinstance(raw_dirs, Mapping) else {}
    directions: dict[str, str] = {}
    for key, value in raw_dirs.items():
        kierunek = str(value or "").strip()
        if kierunek in DIRECTION_LABELS and kierunek != DIRECTION_AUTO:
            directions[str(key)] = kierunek

    # Numer kolumny wskazany ręcznie (dla kierunku „🎯 Wybrana pozycja”).
    raw_cols = source.get("columns")
    raw_cols = raw_cols if isinstance(raw_cols, Mapping) else {}
    columns: dict[str, int] = {}
    for key, value in raw_cols.items():
        try:
            numer = int(value)
        except (TypeError, ValueError):
            continue
        if numer > 0:
            columns[str(key)] = numer

    # Pola z celowo skasowaną wartością — program nie ma ich odczytywać.
    raw_skipped = source.get("skipped_values")
    skipped_values = []
    if isinstance(raw_skipped, (list, tuple, set)):
        for key in raw_skipped:
            klucz = str(key or "").strip()
            if klucz and klucz not in skipped_values:
                skipped_values.append(klucz)

    # Pola ukryte — te, których użytkownik nie chce widzieć w tabeli.
    raw_hidden = source.get("hidden_fields")
    hidden_fields = []
    if isinstance(raw_hidden, (list, tuple, set)):
        for key in raw_hidden:
            klucz = str(key or "").strip()
            if klucz and klucz not in hidden_fields:
                hidden_fields.append(klucz)

    # Obszary odczytu narysowane myszką. Trzymamy je w procentach strony
    # (0-100), więc działają niezależnie od powiększenia i rozdzielczości.
    raw_areas = source.get("areas")
    raw_areas = raw_areas if isinstance(raw_areas, Mapping) else {}
    areas: dict[str, dict[str, float]] = {}
    for key, value in raw_areas.items():
        if (
            str(key) not in FIELD_KEYS and not is_custom_field(str(key))
        ) or not isinstance(value, Mapping):
            continue
        try:
            obszar = {
                "x": float(value.get("x", 0.0)),
                "y": float(value.get("y", 0.0)),
                "w": float(value.get("w", 0.0)),
                "h": float(value.get("h", 0.0)),
                "page": int(value.get("page", 0)),
            }
        except (TypeError, ValueError):
            continue
        if obszar["w"] > 0 and obszar["h"] > 0:
            areas[str(key)] = obszar

    return {
        "name": str(source.get("name", "") or "Nowy profil").strip() or "Nowy profil",
        "builtin": bool(source.get("builtin", False)),
        "override": bool(source.get("override", True)),
        "markers": clean_markers,
        "fields": fields,
        "manual_values": manual_values,
        "areas": areas,
        "custom_fields": custom_fields,
        "hidden_fields": hidden_fields,
        "skipped_values": skipped_values,
        "directions": directions,
        "columns": columns,
    }


def default_profiles() -> list[dict[str, Any]]:
    """Kopia profili wbudowanych."""

    return [normalize_profile(profile) for profile in BUILTIN_PROFILES]


def _profiles_from_list(raw: Any) -> list[dict[str, Any]]:
    """Zamienia surową listę na komplet poprawnych profili."""

    if not isinstance(raw, list):
        return []
    return [normalize_profile(item) for item in raw if isinstance(item, Mapping)]


def _with_builtins(stored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dokłada brakujące profile wbudowane — muszą istnieć zawsze."""

    if not stored:
        return default_profiles()
    names = {_fold(p["name"]) for p in stored}
    for builtin in default_profiles():
        if _fold(builtin["name"]) not in names:
            stored.append(builtin)
    return stored


def read_profiles_file(data_dir: str | Path | None = None) -> dict[str, Any]:
    """Czyta plik ``wypis_profiles.json``.

    Zwraca słownik z kluczami ``profiles``, ``active`` i ``auto``. Brakujący
    lub uszkodzony plik daje pusty wynik, dzięki czemu program startuje
    z ustawieniami domyślnymi zamiast zgłaszać błąd.
    """

    raw = load_json_dict(wypis_profiles_path(data_dir))
    profiles = _profiles_from_list(raw.get("profiles"))
    active = raw.get("active")
    auto = raw.get("auto")
    return {
        "profiles": profiles,
        "active": str(active or "") if isinstance(active, str) else "",
        "auto": auto if isinstance(auto, bool) else True,
        "exists": bool(raw),
    }


def write_profiles_file(
    profiles: Iterable[Mapping[str, Any]],
    *,
    active: str = "",
    auto: bool = True,
    data_dir: str | Path | None = None,
) -> bool:
    """Zapisuje wzory do ``dane/wypis_profiles.json``.

    Plik jest oddzielny od ``app_config.json``, więc można go skopiować
    na inny komputer albo wysłać koledze bez przenoszenia całych ustawień.
    """

    payload = {
        "version": FILE_VERSION,
        "active": str(active or ""),
        "auto": bool(auto),
        "profiles": [normalize_profile(p) for p in profiles or ()],
    }
    return save_json_dict(wypis_profiles_path(data_dir), payload)


def migrate_from_config(
    config: Any,
    data_dir: str | Path | None = None,
) -> bool:
    """Przenosi wzory ze starego ``app_config.json`` do osobnego pliku.

    Wcześniejsza wersja programu trzymała wzory razem z resztą ustawień.
    Przy pierwszym uruchomieniu po aktualizacji przepisujemy je do nowego
    pliku i usuwamy stare klucze, aby dane nie istniały w dwóch miejscach.
    Zwraca ``True``, jeśli coś faktycznie przeniesiono.
    """

    if not isinstance(config, Mapping):
        return False
    if not any(key in config for key in (CONFIG_KEY, ACTIVE_KEY, AUTO_KEY)):
        return False

    # Plik z wzorami już istnieje — ma pierwszeństwo, stare klucze tylko
    # sprzątamy, żeby nie wracały przy kolejnym zapisie konfiguracji.
    current = read_profiles_file(data_dir)
    if not current["exists"]:
        stored = _profiles_from_list(config.get(CONFIG_KEY))
        active = config.get(ACTIVE_KEY)
        auto = config.get(AUTO_KEY)
        write_profiles_file(
            _with_builtins(stored),
            active=str(active or "") if isinstance(active, str) else "",
            auto=auto if isinstance(auto, bool) else True,
            data_dir=data_dir,
        )

    for key in (CONFIG_KEY, ACTIVE_KEY, AUTO_KEY):
        try:
            del config[key]
        except (KeyError, TypeError):
            pass
    return True


def load_profiles(
    config: Mapping[str, Any] | None = None,
    data_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Wczytuje wzory z pliku, uzupełniając brakujące wbudowane.

    ``config`` jest przyjmowany dla zgodności ze starszymi wywołaniami: gdy
    plik jeszcze nie istnieje, a w konfiguracji siedzą wzory z poprzedniej
    wersji, korzystamy z nich.
    """

    stored = read_profiles_file(data_dir)
    if stored["profiles"]:
        return _with_builtins(stored["profiles"])

    if not stored["exists"] and isinstance(config, Mapping):
        legacy = _profiles_from_list(config.get(CONFIG_KEY))
        if legacy:
            return _with_builtins(legacy)

    return default_profiles()


def save_profiles(
    config: Any,
    profiles: Iterable[Mapping[str, Any]],
    data_dir: str | Path | None = None,
) -> bool:
    """Zapisuje wzory do osobnego pliku, zachowując tryb i wybór użytkownika."""

    current = read_profiles_file(data_dir)
    active = current["active"]
    auto = current["auto"]

    # Zapis nie może zgubić ustawień, które wcześniej były w konfiguracji.
    if isinstance(config, Mapping):
        if isinstance(config.get(ACTIVE_KEY), str):
            active = config.get(ACTIVE_KEY) or active
        if isinstance(config.get(AUTO_KEY), bool):
            auto = config.get(AUTO_KEY)

    return write_profiles_file(profiles, active=active, auto=auto, data_dir=data_dir)


def load_settings(
    config: Mapping[str, Any] | None = None,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Zwraca komplet ustawień odczytu: wzory, aktywny wzór i tryb."""

    stored = read_profiles_file(data_dir)
    profiles = load_profiles(config, data_dir)

    active = stored["active"]
    auto = stored["auto"]
    if not stored["exists"] and isinstance(config, Mapping):
        if isinstance(config.get(ACTIVE_KEY), str):
            active = config.get(ACTIVE_KEY) or ""
        if isinstance(config.get(AUTO_KEY), bool):
            auto = config.get(AUTO_KEY)

    return {"profiles": profiles, "active": active, "auto": auto}


def save_settings(
    profiles: Iterable[Mapping[str, Any]],
    *,
    active: str = "",
    auto: bool = True,
    data_dir: str | Path | None = None,
) -> bool:
    """Zapisuje wzory razem z wyborem aktywnego wzoru i trybem pracy."""

    return write_profiles_file(profiles, active=active, auto=auto, data_dir=data_dir)


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
    if label_text[-1:].isalnum():
        suffix = r"\b"
    elif label_text.endswith("."):
        # „Pow.” nie może dopasować się wewnątrz „Pow. [ha]” — po kropce
        # musi kończyć się tekst albo zaczynać wartość, a nie dalszy
        # ciąg nazwy pola.
        suffix = r"(?!\s*[\[\(A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])"
    else:
        suffix = ""
    return re.compile(prefix + body + suffix + r"\s*:?\s*(.*)", re.IGNORECASE)


def _value_until_next_column(
    text: str, known_labels: Iterable[str] = ()
) -> str:
    """Zwraca wartość stojącą po etykiecie, bez sąsiedniej kolumny.

    Wiersz wypisu bywa tabelką: ``Powiat: kartuski    Gmina: Żukowo``.
    Wartością pola „Powiat” jest wyłącznie ``kartuski`` — kolejną kolumnę
    odcinamy po szerokim odstępie (dwie lub więcej spacji).

    Uwaga: nie tniemy „przed słowem z dwukropkiem”, bo psuło to etykiety
    wielowyrazowe — ``Nr obrębu: 0019`` dawało wartość ``Nr``.
    """

    value = str(text or "")

    # 1. Dwie lub więcej spacji = następna kolumna.
    value = re.split(r"\s{2,}", value.strip(), maxsplit=1)[0]

    # 2. Wypisy bez wyraźnych odstępów: „kartuski Gmina: Żukowo”. Tniemy
    #    tylko przed etykietą, którą wzór faktycznie zna — inaczej
    #    „Nr obrębu: 0019” zostałoby pocięte na „Nr”.
    najblizsze = None
    for label in known_labels:
        label = str(label or "").strip()
        if not label:
            continue
        match = re.search(
            r"\s+" + re.escape(label) + r"\s*:", value, flags=re.IGNORECASE
        )
        if match and (najblizsze is None or match.start() < najblizsze):
            najblizsze = match.start()
    if najblizsze is not None:
        value = value[:najblizsze]

    return re.sub(r"\s+", " ", value).strip(" :,;-")


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

    # Uwaga: nie zbijamy tu wielokrotnych spacji, bo to one oddzielają
    # kolumny w wypisach tabelarycznych („Powiat: X    Gmina: Y”).
    lines = [line.rstrip() for line in str(text).split("\n")]

    # Etykiety pozostałych pól — po nich poznajemy kolejną kolumnę wiersza.
    wlasne = {_fold(l) for l in labels}
    inne_etykiety = []
    for key in profile_field_keys(profile):
        for other in labels_for(profile, key):
            if _fold(other) not in wlasne and other not in inne_etykiety:
                inne_etykiety.append(other)
    # Najdłuższe najpierw: „Nr obrębu” zanim „Nr”.
    inne_etykiety.sort(key=len, reverse=True)

    # Kierunek wymuszony ręcznie w kolumnie „③ Skąd czytać” rozstrzygamy
    # NAJPIERW. Inaczej zwykłe dopasowanie „Etykieta: wartość” zwracałoby
    # to samo niezależnie od ustawienia i zmiana nic by nie dawała.
    kierunek = field_direction(profile, field)
    if kierunek != DIRECTION_AUTO:
        if kierunek == DIRECTION_BELOW2:
            wynik = _extract_from_column(lines, labels, profile, pomin=1)
        elif kierunek == DIRECTION_PICK:
            wynik = _extract_from_pick(lines, labels, profile, field)
        else:
            czytaj = {
                DIRECTION_RIGHT: _extract_from_same_row,
                DIRECTION_LEFT: _extract_from_left,
                DIRECTION_BELOW: _extract_from_column,
                DIRECTION_ABOVE: _extract_from_above,
            }.get(kierunek)
            if czytaj is None:
                return ""
            wynik = czytaj(lines, labels, profile)
        if wynik:
            return wynik[:max_length]
        # Etykieta z dwukropkiem („Powiat: kartuski”) tworzy jedną kolumnę,
        # więc podział na kolumny jej nie rozdzieli. Dla kierunku „z prawej”
        # dobieramy jeszcze wartość stojącą tuż za dwukropkiem.
        if kierunek == DIRECTION_RIGHT:
            for label in sorted(labels, key=len, reverse=True):
                wzor = _label_pattern(label)
                for line in lines:
                    trafienie = wzor.search(line)
                    if not trafienie:
                        continue
                    wartosc = _value_until_next_column(
                        trafienie.group(1), inne_etykiety
                    )
                    if wartosc and not _looks_like_label(wartosc, profile):
                        return wartosc[:max_length]
        return ""

    # Najdłuższe etykiety sprawdzamy najpierw, inaczej „Pow.” dopasowałoby
    # się wewnątrz „Pow. [ha]” i zwróciło „[ha]” jako wartość.
    for label in sorted(labels, key=len, reverse=True):
        pattern = _label_pattern(label)
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            match = pattern.search(line)
            if not match:
                continue
            value = _value_until_next_column(match.group(1), inne_etykiety)

            # Wiersz nagłówków tabeli: etykieta i „wartość” to dwie osobne
            # kolumny tego samego wiersza. Wtedy prawdziwa wartość stoi
            # pod spodem, więc takie trafienie pomijamy.
            kolumny = _split_columns(line)
            wiersz_naglowkow = False
            if len(kolumny) >= 2 and value:
                pozycje = {
                    _fold(tekst): numer for numer, (_, tekst) in enumerate(kolumny)
                }
                numer_etykiety = pozycje.get(_fold(label))
                numer_wartosci = pozycje.get(_fold(value))
                wiersz_naglowkow = (
                    numer_wartosci is not None and numer_etykiety != numer_wartosci
                )

            fragment_etykiety = _fold(value) and _fold(value) in _fold(label)
            if (
                value
                and not wiersz_naglowkow
                and not fragment_etykiety
                and not _looks_like_label(value, profile)
            ):
                return value[:max_length]
            # Wartość w kolejnej niepustej linii — ale tylko gdy etykieta
            # stoi sama w wierszu. Inaczej w tabeli w kratkę wzięlibyśmy
            # sąsiedni nagłówek zamiast danych spod spodu.
            if len(_split_columns(line)) <= 1:
                # Jeśli etykieta stoi jako pierwsza kolumna, a obok niej
                # jest już wartość, nie zaglądamy do następnej linii —
                # tam zaczyna się kolejne pole („Jednostka ewidencyjna”).
                kolumny_linii = _split_columns(line)
                if len(kolumny_linii) >= 2 and any(
                    _fold(kolumny_linii[0][1]) == _fold(label)
                    for label in labels
                ):
                    obok = kolumny_linii[1][1].strip(" :,;-")
                    if obok and not _looks_like_label(obok, profile):
                        return obok[:max_length]
                    continue

                for nxt in lines[index + 1: index + 3]:
                    candidate = _value_until_next_column(nxt, inne_etykiety)
                    if candidate and not _looks_like_label(candidate, profile):
                        return candidate[:max_length]

    # Pionowa lista pól bez dwukropków — „Województwo   POMORSKIE”.
    # Etykieta jest pierwszą kolumną, wartość następną w TYM SAMYM wierszu.
    # Sprawdzamy to PRZED tabelą, bo inaczej jako wartość wzięlibyśmy
    # nazwę kolejnego pola z wiersza poniżej.
    obok = _extract_from_same_row(lines, labels, profile)
    if obok:
        return obok[:max_length]

    # Tabela w kratkę: etykieta stoi w nagłówku kolumny, a wartość
    # w wierszu poniżej, w tej samej kolumnie znakowej.
    kolumnowa = _extract_from_column(lines, labels, profile)
    if kolumnowa:
        return kolumnowa[:max_length]

    return ""


def _extract_from_same_row(
    lines: list[str],
    labels: Iterable[str],
    profile: Mapping[str, Any] | None,
) -> str:
    """Czyta wartość stojącą obok etykiety w tym samym wierszu.

    Dotyczy wypisów, w których pola są wypisane jedno pod drugim bez
    dwukropka, a wartość oddziela od nazwy tylko odstęp.
    """

    for numer, line in enumerate(lines):
        if not line.strip():
            continue
        kolumny = _split_columns(line)
        if len(kolumny) < 2:
            continue

        # Wiersz nagłówków tabeli w kratkę („Obręb  Nr działki  Pow. [ha]”)
        # — wartości stoją tam pod spodem, nie obok. Poznajemy go po tym,
        # że co najmniej dwie kolumny są nazwami pól.
        nazwy = sum(
            1 for _start, tekst in kolumny if _looks_like_label(tekst, profile)
        )
        if nazwy >= 2:
            continue
        # Nagłówek bywa piętrowy: „Oznaczenie działki | Opis”, a pod spodem
        # „Numer działki | Numer KW | użytku”. Wzór zna zwykle tylko jedną
        # z tych nazw, więc licznik wyżej takiego wiersza nie złapie.
        # Rozpoznajemy go po tym, że pod spodem stoi kolejny wiersz bez
        # cyfr, a dopiero niżej dane.
        if _naglowek_pietrowy(lines, numer, profile):
            continue

        for pozycja, (_start, tekst) in enumerate(kolumny[:-1]):
            goly = tekst.rstrip(" :").strip()
            if not any(_fold(goly) == _fold(label) for label in labels):
                continue
            wartosc = kolumny[pozycja + 1][1].strip(" :,;-")
            if not wartosc or _looks_like_label(wartosc, profile):
                continue
            # Gdy pod spodem stoi wiersz danych o tej samej budowie, to
            # tabela — wartość jest niżej, a obok stoi kolejna rubryka.
            if _ma_wiersz_danych_pod(lines, numer, kolumny, profile):
                continue
            return wartosc
    return ""


def _naglowek_pietrowy(
    lines: list[str],
    numer: int,
    profile: Mapping[str, Any] | None,
) -> bool:
    """Czy pod tym wierszem stoi jeszcze jedno piętro nagłówka?

    W wypisach nagłówek bywa rozbity na dwie linie („Oznaczenie działki”
    nad „Numer działki”). Wartość stoi wtedy dopiero pod nimi, więc
    czytanie „obok” dałoby nazwę sąsiedniej rubryki.
    """

    kolumny = _split_columns(lines[numer]) if numer < len(lines) else []
    if len(kolumny) < 2:
        return False

    for nizej in lines[numer + 1: numer + 3]:
        if not nizej.strip() or _pasek_strony(nizej):
            continue
        ponizej = _split_columns(nizej)
        # Kolejne piętro nagłówka ma WIĘCEJ rubryk niż to nad nim
        # („Oznaczenie działki | Opis” nad „Numer działki | Numer KW |
        # użytku”). W pionowej liście pól kolumny są dwie i dwie, więc
        # ten warunek jej nie dotyczy.
        if len(ponizej) <= len(kolumny):
            return False
        teksty = [tekst for _start, tekst in ponizej]
        if any(any(znak.isdigit() for znak in tekst) for tekst in teksty):
            return False          # to już dane, nie nagłówek
        # Pod spodem muszą stać prawdziwe dane — inaczej to nie tabela.
        return _ma_dane_ponizej(lines, numer + 1)
    return False


def _ma_dane_ponizej(lines: list[str], od: int) -> bool:
    """Czy niżej stoi wiersz z danymi (zawierający cyfrę)?"""

    for linia in lines[od + 1: od + 4]:
        if not linia.strip():
            continue
        if any(znak.isdigit() for znak in linia):
            return True
    return False


def _ma_wiersz_danych_pod(
    lines: list[str],
    numer: int,
    kolumny: list[tuple[int, str]],
    profile: Mapping[str, Any] | None,
) -> bool:
    """Czy pod wierszem stoi wiersz danych ustawiony w tych samych kolumnach?

    Tak wygląda tabela: „Numer działki | Bliższe określenie” u góry, a pod
    spodem wartości zaczynające się w tych samych miejscach. W pionowej
    liście pól kolumny są poprzesuwane, więc reguła tam nie zadziała.
    """

    zakresy = [(start, start + len(tekst)) for start, tekst in kolumny]
    for nizej in lines[numer + 1: numer + 3]:
        if not nizej.strip():
            continue
        ponizej = _split_columns(nizej)
        if len(ponizej) != len(kolumny):
            return False
        # Kolumny muszą stać jedna pod drugą — każda komórka niżej musi
        # zachodzić na rubrykę nad sobą (napisy bywają różnej długości,
        # więc same początki nie wystarczą).
        if any(
            start >= koniec_gory or start + len(tekst) <= poczatek_gory
            for (start, tekst), (poczatek_gory, koniec_gory)
            in zip(ponizej, zakresy)
        ):
            return False
        # Same nazwy pól to nie są dane.
        if all(_looks_like_label(tekst, profile) for _start, tekst in ponizej):
            return False
        # Pierwsza kolumna niżej musi wyglądać na daną. W pionowej liście
        # („Powiat  kartuski” nad „Gmina  Zukowo”) stoi tam nazwa rubryki,
        # więc to nie jest wiersz danych, tylko kolejne pole.
        pierwsza = ponizej[0][1] if ponizej else ""
        if _looks_like_label(pierwsza, profile):
            return False
        # Wiersz danych: pierwsza komórka zawiera cyfrę.
        return any(znak.isdigit() for znak in pierwsza)
    return False


def _split_columns(line: str) -> list[tuple[int, str]]:
    """Dzieli wiersz na kolumny po dwóch lub więcej spacjach."""

    kolumny = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", line):
        tekst = match.group().strip()
        if tekst:
            kolumny.append((match.start(), tekst))
    return kolumny


def _extract_from_column(
    lines: list[str],
    labels: Iterable[str],
    profile: Mapping[str, Any] | None,
    *,
    pomin: int = 0,
) -> str:
    """Czyta wartość z tabeli, w której nazwa pola jest nagłówkiem kolumny.

    Szuka wiersza, w którym któraś z etykiet stoi jako osobna kolumna,
    a potem bierze z następnego wiersza kolumnę zaczynającą się w tym
    samym miejscu.
    """

    for index, line in enumerate(lines):
        if not line.strip():
            continue
        kolumny = _split_columns(line)
        if not kolumny:
            continue
        # Uwaga: nazwa pola może stać SAMA w linii, a wartość pod nią —
        # to najczęstszy układ w wypisach. Wcześniej takie linie były
        # odrzucane i „⬇️ Pod spodem” nie znajdowało nic.

        for pozycja, (start, tekst) in enumerate(kolumny):
            goly = tekst.rstrip(" :").strip()
            trafiona = any(
                _fold(goly) == _fold(label) for label in labels
            )
            if not trafiona:
                continue

            # Pierwszy niepusty wiersz poniżej z tą samą liczbą kolumn.
            for nizej in lines[index + 1: index + 6]:
                if not nizej.strip() or _pasek_strony(nizej):
                    continue
                ponizej = _split_columns(nizej)
                if not ponizej:
                    continue

                # Dopasowanie po pozycji znakowej, z zapasem na drobne
                # przesunięcia; awaryjnie po numerze kolumny.
                najlepsza = min(
                    ponizej, key=lambda para: abs(para[0] - start), default=None
                )
                if najlepsza is not None and abs(najlepsza[0] - start) <= 4:
                    wartosc = najlepsza[1]
                elif pozycja < len(ponizej):
                    wartosc = ponizej[pozycja][1]
                else:
                    continue

                wartosc = wartosc.strip(" :,;-")
                if not wartosc:
                    continue
                # Nagłówek bywa piętrowy („Oznaczenie działki” nad „Numer
                # działki”) albo zawinięty na dwie linie („Opis” / „użytku”).
                # Wtedy schodzimy niżej, aż trafimy na prawdziwe dane —
                # wcześniej odczyt zatrzymywał się na drugim nagłówku.
                if _looks_like_label(wartosc, profile):
                    continue
                if _wyglada_na_naglowek(ponizej, profile):
                    continue
                # Zawinięty ogon nagłówka („i klas” pod „Użytków i klas”):
                # nie ma cyfry, a niżej stoi prawdziwy wiersz danych.
                if not any(znak.isdigit() for znak in nizej) and _ma_dane_ponizej(
                    lines, lines.index(nizej)
                ):
                    continue
                # „Dwa pod spodem”: pomijamy pierwszy znaleziony wiersz
                # danych i bierzemy następny (tabele z kilkoma wierszami).
                if pomin > 0:
                    pomin -= 1
                    continue
                return wartosc
    return ""


def field_column(profile: Mapping[str, Any] | None, key: str) -> int:
    """Numer kolumny wskazanej ręcznie dla pola (0 = pierwsza)."""

    if isinstance(profile, Mapping):
        raw = profile.get("columns")
        if isinstance(raw, Mapping):
            try:
                return max(0, int(raw.get(key, 0)))
            except (TypeError, ValueError):
                return 0
    return 0


def _extract_from_pick(
    lines: list[str],
    labels: Iterable[str],
    profile: Mapping[str, Any] | None,
    field: str,
) -> str:
    """Bierze wartość z kolumny wskazanej ręcznie przez użytkownika.

    Przydaje się w tabelach, gdzie pod nazwą stoi kilka liczb obok siebie
    („Użytków i klas” oraz „Działki”) i trzeba powiedzieć wprost, która
    z nich jest tą właściwą.
    """

    numer = field_column(profile, field)
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        kolumny = _split_columns(line)
        if not kolumny:
            continue
        trafiona = any(
            _fold(tekst.rstrip(" :").strip()) == _fold(label)
            for _start, tekst in kolumny
            for label in labels
        )
        if not trafiona:
            continue

        for nizej in lines[index + 1: index + 6]:
            if not nizej.strip() or _pasek_strony(nizej):
                continue
            ponizej = _split_columns(nizej)
            if not ponizej or _wyglada_na_naglowek(ponizej, profile):
                continue
            if numer < len(ponizej):
                wartosc = ponizej[numer][1].strip(" :,;-")
                if wartosc:
                    return wartosc
            return ""
    return ""


def _pasek_strony(tekst: str) -> bool:
    """Czy to pasek oddzielający strony, a nie dane z dokumentu?"""

    return "STRONA" in tekst and "─" in tekst


def _wyglada_na_naglowek(
    kolumny: list[tuple[int, str]],
    profile: Mapping[str, Any] | None,
) -> bool:
    """Czy ten wiersz to kolejne piętro nagłówka, a nie dane?

    Nagłówek poznajemy po tym, że żadna z jego komórek nie zawiera cyfry,
    a co najmniej jedna jest nazwą rubryki znaną z wzoru.
    """

    if not kolumny:
        return False
    teksty = [tekst for _start, tekst in kolumny]
    if any(any(znak.isdigit() for znak in tekst) for tekst in teksty):
        return False          # jest cyfra — to dane
    # Bez cyfr: jedna komórka to zwykła wartość tekstowa („Jan Kowalski”).
    # Kilka komórek obok siebie to kolejne piętro nagłówka albo jego
    # zawinięty ogon („i klas” pod „Użytków”), a nie wiersz danych.
    if len(teksty) >= 2:
        return True
    return any(_looks_like_label(tekst, profile) for tekst in teksty)


def _extract_from_left(
    lines: list[str],
    labels: Iterable[str],
    profile: Mapping[str, Any] | None,
) -> str:
    """Czyta wartość stojącą po LEWEJ stronie etykiety w tym samym wierszu.

    Tak bywa w formularzach, gdzie liczba stoi przed opisem, np.
    „27/176   Numer działki”.
    """

    for line in lines:
        if not line.strip():
            continue
        kolumny = _split_columns(line)
        if len(kolumny) < 2:
            continue

        for pozycja, (_start, tekst) in enumerate(kolumny):
            if pozycja == 0:
                continue                 # po lewej nic już nie ma
            goly = tekst.rstrip(" :").strip()
            if not any(_fold(goly) == _fold(label) for label in labels):
                continue
            wartosc = kolumny[pozycja - 1][1].strip(" :,;-")
            if wartosc and not _looks_like_label(wartosc, profile):
                return wartosc
    return ""


def _extract_from_above(
    lines: list[str],
    labels: Iterable[str],
    profile: Mapping[str, Any] | None,
) -> str:
    """Czyta wartość stojącą NAD etykietą, w tej samej kolumnie.

    Odwrotność tabeli w kratkę: podpis rubryki jest pod danymi, np. suma
    nad opisem „Powierzchnia razem”.
    """

    for index, line in enumerate(lines):
        if not line.strip():
            continue
        kolumny = _split_columns(line)
        if not kolumny:
            continue

        for pozycja, (start, tekst) in enumerate(kolumny):
            goly = tekst.rstrip(" :").strip()
            if not any(_fold(goly) == _fold(label) for label in labels):
                continue

            # Pierwszy niepusty wiersz powyżej — szukamy w nim kolumny
            # stojącej w tym samym miejscu co nasza etykieta.
            for wyzej in reversed(lines[max(0, index - 5): index]):
                if not wyzej.strip() or _pasek_strony(wyzej):
                    continue
                powyzej = _split_columns(wyzej)
                if not powyzej:
                    continue

                najlepsza = min(
                    powyzej, key=lambda para: abs(para[0] - start), default=None
                )
                if najlepsza is not None and abs(najlepsza[0] - start) <= 4:
                    wartosc = najlepsza[1]
                elif pozycja < len(powyzej):
                    wartosc = powyzej[pozycja][1]
                else:
                    continue

                wartosc = wartosc.strip(" :,;-")
                if wartosc and not _looks_like_label(wartosc, profile):
                    return wartosc
                break
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

    etykiety_pol = profile_field_labels(clean)
    for key in profile_field_keys(clean):
        labels = clean["fields"].get(key, [])
        matched = ""
        for label in labels:
            if _fold(label) in haystack:
                matched = label
                break
        value = extract_field(text, clean, key) if matched else ""
        rows.append({
            "field": key,
            "label": etykiety_pol.get(key, key),
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
