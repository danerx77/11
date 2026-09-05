"""Czyste funkcje pomocnicze dla ręcznego modułu KW 2.

Moduł nie łączy się z serwisem eKW. Służy jedynie do normalizacji i
porządkowania numerów, które użytkownik wpisuje lub kopiuje ręcznie.
"""

from __future__ import annotations

import re
from typing import Any


KW_RE = re.compile(r"^[A-Z0-9]{4}/[0-9]{1,8}/[0-9]$")


def normalize_kw(value: Any) -> str:
    """Normalizuje zapis numeru księgi do formatu ``AA1A/00000000/0``."""

    return re.sub(r"\s+", "", str(value or "")).upper()


def is_valid_kw(value: Any) -> bool:
    """Sprawdza format kompletnego numeru KW bez odpytywania eKW."""

    return bool(KW_RE.fullmatch(normalize_kw(value)))


def extract_kw_numbers(text: Any) -> list[str]:
    """Wyciąga poprawne numery KW z wklejonego tekstu.

    Akceptuje zwykły zapis z ukośnikami, wariant ze spacjami lub z kropkami /
    myślnikami jako separatorami. Wynik zachowuje kolejność pierwszego
    wystąpienia i nie zawiera duplikatów.
    """

    if isinstance(text, (list, tuple, set)):
        text = "\n".join(str(value) for value in text)
    raw = str(text or "").upper().replace("\u00a0", " ")
    patterns = (
        r"\b([A-Z0-9]{4})\s*/\s*([0-9]{1,8})\s*/\s*([0-9])\b",
        r"\b([A-Z0-9]{4})\s+([0-9]{1,8})\s+([0-9])\b",
        r"\b([A-Z0-9]{4})\s*[-.]\s*([0-9]{1,8})\s*[-.]\s*([0-9])\b",
    )

    matches: list[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, raw):
            value = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
            matches.append((match.start(), normalize_kw(value)))

    result: list[str] = []
    seen: set[str] = set()
    for _position, number in sorted(matches, key=lambda item: item[0]):
        if number not in seen and is_valid_kw(number):
            seen.add(number)
            result.append(number)

    return result


def collect_owner_kw_parcels(owners: list[Any]) -> dict[str, list[str]]:
    """Zbiera poprawne numery KW i powiązane działki z danych właścicieli.

    Funkcja nie pobiera żadnych danych z Internetu. Wynik ma stabilną kolejność
    pierwszego wystąpienia numeru KW i nie powiela numerów działek.
    """

    result: dict[str, list[str]] = {}
    seen_parcels: dict[str, set[str]] = {}

    for owner in owners or []:
        if not isinstance(owner, dict):
            continue
        for parcel in owner.get("parcels", []) or []:
            if not isinstance(parcel, dict):
                continue
            kw = normalize_kw(parcel.get("kw", ""))
            if not is_valid_kw(kw):
                continue

            if kw not in result:
                result[kw] = []
                seen_parcels[kw] = set()

            parcel_number = str(parcel.get("number", "") or "").strip()
            if parcel_number and parcel_number not in seen_parcels[kw]:
                result[kw].append(parcel_number)
                seen_parcels[kw].add(parcel_number)

    return result
