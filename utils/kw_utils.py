"""Czyste reguły pomocnicze dla modułu pobierania Ksiąg Wieczystych."""

from __future__ import annotations

import re
from typing import Any


ACCESS_DENIED_MARKERS = (
    "access denied",
    "error 15",
    "request rejected",
    "bot support id",
    "odmowa dostepu",
)


def ekw_access_denied_reason(value: Any) -> str:
    """Zwraca czytelny opis blokady strony eKW albo pusty tekst.

    Nie próbuje obchodzić zabezpieczenia serwisu. Moduł wykorzystuje tę
    funkcję wyłącznie do opisania strony po nieudanym oczekiwaniu na formularz
    lub wynik, gdy serwis zwróci np. ``Access Denied / Error 15``.
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    normalized = text.casefold()
    if not any(marker in normalized for marker in ACCESS_DENIED_MARKERS):
        return ""

    support_id = re.search(
        r"(?:bot\s+support\s+id|support\s+id)\s*(?:is\s*:?|:)?\s*<?([0-9-]{5,})",
        text,
        re.IGNORECASE,
    )
    suffix = f" (identyfikator: {support_id.group(1)})" if support_id else ""
    return (
        "Serwis eKW odrzucił połączenie (Access Denied / Error 15)"
        f"{suffix}. Nie jest to błąd zapisu PDF — spróbuj ponownie później "
        "lub otwórz stronę eKW ręcznie w tej samej sieci."
    )


def should_use_native_pdf_export(
    direct_save_enabled: bool,
    pdf_printer_name: str,
    browser_engine: str,
) -> bool:
    """Czy PDF może zostać zapisany bez okna drukowania systemowego.

    Playwright potrafi zapisać PDF bezpośrednio w silniku Chromium (Chrome,
    Edge, Opera), ale Firefox nie udostępnia ``page.pdf()``. Dla Firefox
    pozostaje zwykła drukarka PDF systemu Windows.
    """
    wants_direct_pdf = bool(direct_save_enabled) or str(pdf_printer_name) == "Save as PDF"
    return wants_direct_pdf and str(browser_engine).casefold() == "chromium"
