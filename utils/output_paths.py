"""Foldery docelowe dla dokumentów generowanych przez program.

Domyślnie każdy moduł zapisuje swoje pliki do własnego podfolderu w katalogu
projektu — Oświadczenia do ``Oswiadczenia``, Pisma do ``Pisma`` itd. Dzięki
temu po kliknięciu „Generuj” nie trzeba już wskazywać folderu ręcznie.

Każdy moduł ma osobny przełącznik w Ustawieniach: gdy jest wyłączony,
program pyta o folder tak jak dotąd.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

# Klucz włącznika i nazwa podfolderu dla każdego modułu.
AUTO_KEY_PREFIX = "auto_output_"
FOLDER_KEY_PREFIX = "output_folder_"

# (identyfikator, etykieta w Ustawieniach, domyślna nazwa podfolderu)
OUTPUT_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("declarations", "Oświadczenia woli", "Oswiadczenia"),
    ("cover_letters", "Pisma przewodnie", "Pisma"),
    ("druczki", "Druczki pocztowe", "Druczki"),
    ("split_pdf", "Wydzielone działki (PDF)", "Wydzielone dzialki"),
    ("legal_titles", "Tytuły prawne", "Tytuly prawne"),
)

DEFAULT_FOLDERS: dict[str, str] = {
    key: folder for key, _label, folder in OUTPUT_TARGETS
}

TARGET_LABELS: dict[str, str] = {
    key: label for key, label, _folder in OUTPUT_TARGETS
}


def auto_key(target: str) -> str:
    """Klucz konfiguracji z włącznikiem automatycznego zapisu."""

    return f"{AUTO_KEY_PREFIX}{target}"


def folder_key(target: str) -> str:
    """Klucz konfiguracji z nazwą podfolderu."""

    return f"{FOLDER_KEY_PREFIX}{target}"


def output_defaults() -> dict[str, Any]:
    """Ustawienia domyślne: automatyczny zapis włączony dla każdego modułu."""

    defaults: dict[str, Any] = {}
    for key, _label, folder in OUTPUT_TARGETS:
        defaults[auto_key(key)] = True
        defaults[folder_key(key)] = folder
    return defaults


def is_auto_enabled(config: Mapping[str, Any] | None, target: str) -> bool:
    """Czy program ma sam wybierać folder dla tego modułu."""

    if not isinstance(config, Mapping):
        return True
    return bool(config.get(auto_key(target), True))


def folder_name(config: Mapping[str, Any] | None, target: str) -> str:
    """Nazwa podfolderu w katalogu projektu."""

    default = DEFAULT_FOLDERS.get(target, target)
    if not isinstance(config, Mapping):
        return default
    value = str(config.get(folder_key(target), default) or "").strip()
    # Nazwa podfolderu nie może wyprowadzać poza katalog projektu.
    value = value.replace("\\", "/").strip("/")
    if not value or ".." in value.split("/"):
        return default
    return value


def project_output_dir(
    config: Mapping[str, Any] | None,
    target: str,
    project_path: Any,
    *,
    create: bool = True,
) -> Path | None:
    """Zwraca folder docelowy w katalogu projektu albo ``None``.

    ``None`` oznacza, że program ma zapytać użytkownika o folder — bo
    automatyczny zapis jest wyłączony, nie ma otwartego projektu albo
    katalogu nie da się utworzyć.
    """

    if not is_auto_enabled(config, target):
        return None

    raw_path = str(project_path or "").strip()
    if not raw_path:
        return None

    try:
        base = Path(raw_path)
        if not base.is_dir():
            return None
        destination = base / folder_name(config, target)
        if create:
            destination.mkdir(parents=True, exist_ok=True)
        return destination
    except OSError:
        return None


def describe_target(config: Mapping[str, Any] | None, target: str) -> str:
    """Krótki opis dla podpowiedzi w Ustawieniach."""

    label = TARGET_LABELS.get(target, target)
    if not is_auto_enabled(config, target):
        return f"{label}: program pyta o folder przy każdym zapisie."
    return f"{label}: zapis do podfolderu „{folder_name(config, target)}”."


# ── Folder nadrzędny nowych projektów ────────────────────────────────

PROJECTS_ROOT_KEY = "default_project_root"
PROJECTS_SUBFOLDER_KEY = "projects_root_subfolder"
USE_PROJECTS_SUBFOLDER_KEY = "projects_use_subfolder"

DEFAULT_PROJECTS_SUBFOLDER = "Projekty"


def projects_root(
    config: Mapping[str, Any] | None,
    app_dir: Any,
    *,
    create: bool = False,
) -> Path:
    """Folder, w którym mają powstawać nowe projekty.

    Kolejność: folder wskazany w Ustawieniach, a gdy go nie ma — podfolder
    ``Projekty`` obok programu (zamiast zaśmiecania katalogu głównego).
    """

    configured = ""
    if isinstance(config, Mapping):
        configured = str(config.get(PROJECTS_ROOT_KEY, "") or "").strip()

    if configured:
        base = Path(configured)
    else:
        base = Path(str(app_dir or "."))
        use_subfolder = True
        subfolder = DEFAULT_PROJECTS_SUBFOLDER
        if isinstance(config, Mapping):
            use_subfolder = bool(
                config.get(USE_PROJECTS_SUBFOLDER_KEY, True)
            )
            subfolder = str(
                config.get(PROJECTS_SUBFOLDER_KEY, DEFAULT_PROJECTS_SUBFOLDER)
                or DEFAULT_PROJECTS_SUBFOLDER
            ).strip()
        if use_subfolder and subfolder:
            base = base / subfolder

    if create:
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            return Path(str(app_dir or "."))
    return base
