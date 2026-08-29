"""Trwałe, globalne ustawienia przechowywane w folderze ``dane``.

Dane projektu pozostają w katalogu projektu. Ustawienia narzędzi wspólnych
(np. kadrowanie znaczków i pozycje druczka) są natomiast celowo niezależne od
projektu i są dostępne po ponownym uruchomieniu aplikacji.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

STAMP_SETTINGS_FILE = "stamp_profiles.json"
DRUCZEK_PROFILE_FILE = "druczek_profile.json"
ENVELOPE_PREFERENCES_FILE = "envelope_preferences.json"

# Ustawienia sposobu pracy w zakładce Koperty. Nie zapisujemy tu danych
# projektu (adresatów, historii generowania ani katalogu wyjściowego), tylko
# wybory interfejsu, które użytkownik chce mieć takie same w każdym projekcie.
ENVELOPE_PREFERENCE_KEYS = (
    "envelope_view_sort",
    "envelope_generation_sort",
    "envelope_hide_generated",
    "envelope_show_only_generated",
    "envelope_single_files",
    "envelope_stamps_tab",
    "envelope_table_state",
)

STAMP_SETTING_KEYS = (
    "stamp_profile_c5",
    "stamp_profile_c6",
    "stamp_window_geom_C5",
    "stamp_window_geom_C6",
)


def get_global_data_dir(base_dir: str | Path | None = None) -> Path:
    """Zwraca wspólny dla aplikacji folder ``dane``.

    ``base_dir`` służy testom oraz wywołaniom, które mają już ustalony katalog
    aplikacji. W zwykłym uruchomieniu ścieżka jest taka sama jak katalog danych
    używany przez ``main.py``.
    """
    if base_dir is None:
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parent.parent
    return Path(base_dir).expanduser().resolve() / "dane"


def _data_dir(data_dir: str | Path | None = None) -> Path:
    return Path(data_dir).expanduser() if data_dir is not None else get_global_data_dir()


def load_json_dict(path: str | Path) -> dict[str, Any]:
    """Czyta słownik JSON; uszkodzony lub brakujący plik oznacza pusty słownik."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def save_json_dict(path: str | Path, data: Mapping[str, Any]) -> bool:
    """Zapisuje JSON atomowo, aby przerwany zapis nie uszkodził profilu."""
    destination = Path(path)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def stamp_settings_path(data_dir: str | Path | None = None) -> Path:
    return _data_dir(data_dir) / STAMP_SETTINGS_FILE


def load_global_stamp_settings(
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Odczytuje profile cięcia C5/C6 i geometrię ich okien z ``dane``."""
    raw = load_json_dict(stamp_settings_path(data_dir))
    result: dict[str, Any] = {}
    for key in ("stamp_profile_c5", "stamp_profile_c6"):
        value = raw.get(key)
        if isinstance(value, Mapping):
            result[key] = dict(value)
    for key in ("stamp_window_geom_C5", "stamp_window_geom_C6"):
        value = raw.get(key)
        if isinstance(value, str):
            result[key] = value
    return result


def save_global_stamp_settings(
    config: Mapping[str, Any],
    data_dir: str | Path | None = None,
) -> bool:
    """Natychmiast zapisuje globalne profile wycinania znaczków C5 i C6."""
    payload: dict[str, Any] = {"version": 1}
    for key in ("stamp_profile_c5", "stamp_profile_c6"):
        value = config.get(key)
        if isinstance(value, Mapping):
            payload[key] = dict(value)
    for key in ("stamp_window_geom_C5", "stamp_window_geom_C6"):
        value = config.get(key)
        if isinstance(value, str):
            payload[key] = value
    return save_json_dict(stamp_settings_path(data_dir), payload)


def envelope_preferences_path(data_dir: str | Path | None = None) -> Path:
    return _data_dir(data_dir) / ENVELOPE_PREFERENCES_FILE


def load_global_envelope_preferences(
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Odczytuje globalne wybory sortowania i widoku zakładki Koperty."""
    raw = load_json_dict(envelope_preferences_path(data_dir))
    result: dict[str, Any] = {}
    boolean_keys = {
        "envelope_hide_generated",
        "envelope_show_only_generated",
        "envelope_single_files",
    }
    index_keys = {
        "envelope_view_sort",
        "envelope_generation_sort",
        "envelope_stamps_tab",
    }
    for key in ENVELOPE_PREFERENCE_KEYS:
        value = raw.get(key)
        if key in boolean_keys and isinstance(value, bool):
            result[key] = value
        elif key in index_keys and isinstance(value, int) and not isinstance(value, bool):
            result[key] = value
        elif key == "envelope_table_state" and isinstance(value, str):
            result[key] = value
    return result


def save_global_envelope_preferences(
    config: Mapping[str, Any],
    data_dir: str | Path | None = None,
) -> bool:
    """Zapisuje od razu globalne wybory użytkownika w module Koperty."""
    payload: dict[str, Any] = {"version": 1}
    boolean_keys = {
        "envelope_hide_generated",
        "envelope_show_only_generated",
        "envelope_single_files",
    }
    index_keys = {
        "envelope_view_sort",
        "envelope_generation_sort",
        "envelope_stamps_tab",
    }
    for key in ENVELOPE_PREFERENCE_KEYS:
        value = config.get(key)
        if key in boolean_keys and isinstance(value, bool):
            payload[key] = value
        elif key in index_keys and isinstance(value, int) and not isinstance(value, bool):
            payload[key] = value
        elif key == "envelope_table_state" and isinstance(value, str):
            payload[key] = value
    return save_json_dict(envelope_preferences_path(data_dir), payload)


def druczek_profile_path(data_dir: str | Path | None = None) -> Path:
    return _data_dir(data_dir) / DRUCZEK_PROFILE_FILE


def load_global_druczek_profile(
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Odczytuje globalne pozycje i czcionki druczka."""
    raw = load_json_dict(druczek_profile_path(data_dir))
    # Wcześniejsze wersje zapisywały profil bez dodatkowego zagnieżdżenia.
    profile = raw.get("profile") if isinstance(raw.get("profile"), Mapping) else raw
    return dict(profile) if isinstance(profile, Mapping) else {}


def save_global_druczek_profile(
    profile: Mapping[str, Any],
    data_dir: str | Path | None = None,
) -> bool:
    """Zapisuje globalnie pozycje, rozmiary i czcionki pól druczka."""
    return save_json_dict(druczek_profile_path(data_dir), profile)
