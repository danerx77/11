"""Automatyczna data w pismach.

Program może sam wpisywać dzisiejszą datę w polach „Data sporządzenia”
(Pisma przewodnie) i „Data” (Oświadczenia woli). Datę zawsze można
poprawić ręcznie — wpisana zmiana zostaje i nie jest nadpisywana.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

#: Klucz w ustawieniach — czy wstawiać dzisiejszą datę automatycznie.
AUTO_DATE_KEY = "auto_today_date"

#: Format daty używany w pismach: 05.09.2026.
DATE_FORMAT = "%d.%m.%Y"

#: Domyślnie włączone — pole samo się wypełnia, ale da się je nadpisać.
AUTO_DATE_DEFAULT = True


def is_auto_date_enabled(config: Mapping[str, Any] | None) -> bool:
    """Czy automatyczne wstawianie dzisiejszej daty jest włączone?"""

    if not isinstance(config, Mapping):
        return AUTO_DATE_DEFAULT

    value = config.get(AUTO_DATE_KEY, AUTO_DATE_DEFAULT)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "nie", "off", "")
    if isinstance(value, (int, float)):
        return bool(value)
    return AUTO_DATE_DEFAULT


def today_text(today: date | None = None) -> str:
    """Dzisiejsza data komputera w formacie używanym w pismach."""

    return (today or date.today()).strftime(DATE_FORMAT)


def initial_date_text(
    config: Mapping[str, Any] | None,
    *,
    today: date | None = None,
) -> str:
    """Tekst, od którego zaczyna pole daty przy otwarciu zakładki.

    Gdy opcja jest wyłączona, pole zostaje puste — tak jak dawniej.
    """

    if not is_auto_date_enabled(config):
        return ""
    return today_text(today)
