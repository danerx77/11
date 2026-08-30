"""Czysta logika wyboru adresów do seryjnego generowania dokumentów."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from typing import Any

Owner = Mapping[str, Any]
TargetPredicate = Callable[[Owner, str], bool]

# Klucze odpowiadają oznaczeniom właścicieli w module Wypisy. Domyślne
# wartości zachowują dotychczasowe zasady Pism przewodnich: instytucje,
# parafie, osoby zmarłe i niepełne adresy nie trafiają do serii, zaś firmy i
# spółki można włączać lub wyłączać świadomie.
COVER_GENERATION_RULES = (
    ("cover_skip_dead", "is_dead", "Osoba zmarła", True),
    ("cover_skip_institution", "is_institution", "Instytucja / gmina", True),
    ("cover_skip_church", "is_church", "Parafia / kościół", True),
    ("cover_skip_company", "is_company", "Firma", False),
    ("cover_skip_spolka", "is_spolka", "Spółka", False),
)
COVER_ADDRESS_RULES = (
    ("cover_skip_missing_address", "Brak adresu", True),
    ("cover_skip_invalid_postal_code", "Brak kodu pocztowego", True),
)


def cover_generation_rule_defaults() -> dict[str, bool]:
    """Zwraca domyślne reguły pomijania pism przewodnich."""
    defaults = {config_key: default for config_key, _flag, _reason, default in COVER_GENERATION_RULES}
    defaults.update({config_key: default for config_key, _reason, default in COVER_ADDRESS_RULES})
    return defaults


def cover_generation_exclusion_reason(
    owner: Owner,
    address: str,
    preferences: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Sprawdza, czy pismo przewodnie może trafić do seryjnego generowania.

    Reguły są celowo konfigurowalne w Ustawieniach. Zwracany opis można
    pokazać w podsumowaniu pominiętych pozycji, bez ukrywania ich po cichu.
    """
    settings = preferences if isinstance(preferences, Mapping) else {}
    for config_key, owner_flag, reason, default in COVER_GENERATION_RULES:
        if bool(settings.get(config_key, default)) and bool(owner.get(owner_flag)):
            return False, reason

    text_address = str(address or "").strip()
    if bool(settings.get("cover_skip_missing_address", True)) and not text_address:
        return False, "Brak adresu"
    if (
        bool(settings.get("cover_skip_invalid_postal_code", True))
        and not re.search(r"\d{2}-\d{3}", text_address)
    ):
        return False, "Brak kodu pocztowego"
    return True, "OK"


def owner_addresses(owner: Owner) -> list[str]:
    """Zwraca adres główny i ewentualny drugi adres właściciela.

    Pusty adres główny jest zachowany celowo: moduł generowania przekazuje go
    dalej do swojego filtra poprawności i może pokazać użytkownikowi powód
    pominięcia, zamiast po cichu ukryć wpis.
    """
    addresses = [str(owner.get("address", "") or "")]
    secondary_address = owner.get("address_2", "")
    if secondary_address:
        addresses.append(str(secondary_address))
    return addresses


def select_address_targets(
    owners: Iterable[Owner],
    *,
    hide_done: bool = False,
    is_done: TargetPredicate | None = None,
    matches_filter: TargetPredicate | None = None,
) -> list[tuple[Owner, str]]:
    """Wybiera adresy, dla których ma zostać wykonane generowanie.

    Predykaty zawsze dostają *konkretny adres*, a nie tylko właściciela. To
    jest istotne dla wpisów z ``address_2``: wygenerowanie dokumentu na jeden
    adres nie może ukryć drugiego adresu tego samego właściciela.
    """
    targets: list[tuple[Owner, str]] = []
    for owner in owners:
        for address in owner_addresses(owner):
            if hide_done and is_done is not None and is_done(owner, address):
                continue
            if matches_filter is not None and not matches_filter(owner, address):
                continue
            targets.append((owner, address))
    return targets
