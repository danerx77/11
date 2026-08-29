"""Czysta logika wyboru adresów do seryjnego generowania dokumentów."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

Owner = Mapping[str, Any]
TargetPredicate = Callable[[Owner, str], bool]


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
