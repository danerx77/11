"""Czyste reguły pomocnicze dla modułu pobierania Ksiąg Wieczystych."""

from __future__ import annotations


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
