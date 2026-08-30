"""utils/templates.py – Automatyczne znajdowanie najnowszych wersji plików szablonów.

Problem: w konfiguracji były "na sztywno" wpisane nazwy plików z numerami
wersji, np. "Oświadczenie woli budowa kabla 4.docx". Gdy użytkownik dodał
nowszą wersję ("... kabla 5.docx"), program dalej brał "4".

Rozwiązanie: funkcje poniżej znajdują najnowszą dostępną wersję pliku
pasującego do podanej nazwy bazowej (bez numeru wersji).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path

# Numer wersji na końcu nazwy: "kabla 4", "kabla 10", "kabla v2", "kabla_7" itp.
_VERSION_SUFFIX = re.compile(r"[\s._-]*[vV]?[\s._-]*(\d{1,4})\b")

# Wersje zapisu folderów dołączanych do programu. W systemie Windows wielkość
# liter nie ma znaczenia, ale w pozostałych systemach chcemy rozpoznać także
# folder zapisany przez użytkownika wielką literą lub bez polskich znaków.
EXAMPLES_FOLDER_NAMES = ("przykłady", "Przykłady", "przyklady", "Przyklady")
STAMP_FOLDER_NAMES = ("znaczki", "Znaczki")
LEGAL_TITLES_FOLDER_NAMES = (
    "tytuły prawne",
    "Tytuły prawne",
    "tytuly prawne",
    "Tytuly prawne",
)

# (Etykieta widoczna w programie, możliwe początki nazwy pliku).
# Pierwsze dwa warianty obsługują nazwy wzorów z polskimi znakami i bez nich,
# a dwa ostatnie zachowują zgodność z dotychczasowymi plikami szablon1–3.
LEGAL_TITLES_TEMPLATE_SPECS = (
    (
        "Wykaz działek podmiotów pozostałych",
        (
            "Wykaz działek podmiotów pozostałych",
            "Wykaz dzialek podmiotow pozostalych",
            "szablon1",
            "szablon 1",
        ),
    ),
    (
        "Wykaz właścicieli nieruchomości szczegółowy",
        (
            "Wykaz właścicieli nieruchomości szczegółowy",
            "Wykaz wlascicieli nieruchomosci szczegolowy",
            "szablon2",
            "szablon 2",
        ),
    ),
    (
        "Nowa tabela końcowa",
        (
            "Nowa tabela końcowa",
            "Nowa tabela koncowa",
            "szablon3",
            "szablon 3",
        ),
    ),
)


def _existing_directory(value: object) -> Path | None:
    """Zwraca istniejący katalog wskazany przez folder albo plik."""
    text = str(value or "").strip()
    if not text:
        return None

    try:
        path = Path(text).expanduser()
        if path.is_file():
            return path.parent
        if path.is_dir():
            return path
    except OSError:
        return None
    return None


def resolve_template_start_directory(
    config: Mapping | None,
    *,
    config_key: str,
    folder_names: tuple[str, ...],
    current_path: object = "",
    preferred_folder: object = "",
) -> Path:
    """Wybiera folder początkowy okna wyboru szablonu.

    Kolejność jest celowa: najpierw używany jest folder wskazany właśnie w
    Ustawieniach, potem zapisana konfiguracja, następnie katalog obecnie
    wybranego pliku. Jeśli żaden z nich nie istnieje, szukamy folderu
    dołączonych przykładów obok aplikacji (oraz obok jej folderu nadrzędnego).
    Dzięki temu przycisk ``Wybierz`` otwiera od razu folder z przykładami,
    zamiast przypadkowego katalogu roboczego systemu.
    """
    candidates: list[object] = [preferred_folder]
    if isinstance(config, Mapping):
        candidates.append(config.get(config_key, ""))
    candidates.append(current_path)

    for candidate in candidates:
        directory = _existing_directory(candidate)
        if directory is not None:
            return directory

    if getattr(sys, "frozen", False):
        app_directory = Path(sys.executable).parent.resolve()
    else:
        app_directory = Path(__file__).resolve().parent.parent

    for base_directory in (app_directory, app_directory.parent):
        for folder_name in folder_names:
            directory = _existing_directory(base_directory / folder_name)
            if directory is not None:
                return directory

    # QFileDialog może otworzyć katalog, który zostanie utworzony/dostarczony
    # później wraz z szablonami. Zwracamy więc przewidywalną ścieżkę zamiast
    # katalogu domowego albo bieżącego katalogu procesu.
    return app_directory / (folder_names[0] if folder_names else "")


def _version_of(stem: str, base: str):
    """Zwraca numer wersji pliku, jeśli `stem` odpowiada nazwie `base`.

    - dokładne dopasowanie -> wersja 0,
    - "base 4" / "base v2" / "base_7" -> odpowiedni numer,
    - brak dopasowania -> None.
    """
    base_l = base.strip().lower()
    stem_l = stem.strip().lower()

    if stem_l == base_l:
        return 0

    if not stem_l.startswith(base_l):
        return None

    remainder = stem_l[len(base_l):]
    m = _VERSION_SUFFIX.match(remainder)
    if m:
        return int(m.group(1))
    return None


def find_latest_file(folder, bases, extensions=(".docx",)):
    """Znajdź najnowszą wersję pliku (wg numeru wersji, potem wg daty modyfikacji).

    Args:
        folder: katalog, w którym szukamy.
        bases: lista nazw bazowych bez numeru wersji, np. ["Oświadczenie woli budowa kabla"].
        extensions: dopuszczalne rozszerzenia.

    Returns:
        Path do najnowszego pliku lub None, gdy nic nie znaleziono.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None

    exts = {e.lower() if e.startswith(".") else "." + e.lower() for e in extensions}

    best_path = None
    best_version = -1
    best_mtime = -1.0

    try:
        entries = list(folder.iterdir())
    except OSError:
        return None

    for entry in entries:
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        if entry.suffix.lower() not in exts:
            continue

        for base in bases:
            version = _version_of(entry.stem, base)
            if version is None:
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                mtime = 0.0
            if version > best_version or (version == best_version and mtime > best_mtime):
                best_path = entry
                best_version = version
                best_mtime = mtime
            break

    return best_path


def find_file_newest(folder, bases, extensions=(".xlsx", ".xlsm")):
    """Znajdź plik, którego nazwa zaczyna się od którejś z `bases` (najnowszy wg daty).

    Używane dla szablonów bez numeru wersji (np. "szablon1.xlsx", "druczek.pdf").
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None

    exts = {e.lower() if e.startswith(".") else "." + e.lower() for e in extensions}
    base_lows = [b.strip().lower() for b in bases if b.strip()]

    best_path = None
    best_mtime = -1.0

    try:
        entries = list(folder.iterdir())
    except OSError:
        return None

    for entry in entries:
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        if entry.suffix.lower() not in exts:
            continue
        stem_l = entry.stem.lower()
        if not any(stem_l.startswith(b) for b in base_lows):
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime > best_mtime:
            best_path = entry
            best_mtime = mtime

    return best_path
