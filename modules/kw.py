# -*- coding: utf-8 -*-
"""
kw_downloader.py – Zakładka do automatycznego pobierania Ksiąg Wieczystych

Wersja uproszczona: działa podobnie do modułu KRS.

Zostawione są tylko:
- tabela ksiąg,
- wybór działów,
- odstęp czasu między księgami,
- ustawienie szybkości,
- logi,
- automatyczne pobieranie PDF.

WAŻNE
------
Ta wersja OTWIERA WIDOCZNĄ przeglądarkę Playwright tak jak moduł KRS,
dzięki czemu użytkownik może zobaczyć stronę i ewentualnie ręcznie potwierdzić
komunikaty / zabezpieczenia. Sam zapis PDF odbywa się przez normalne okno drukowania
Windows do wybranej drukarki PDF.

Wymagane jednorazowo:
    pip install playwright pywinauto
    python -m playwright install chromium

Uwaga:
    tryb „normalnego drukowania" działa jako automatyzacja Windowsowego okna
    drukowania i zapisu PDF. Jest to rozwiązanie tylko dla Windows.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from utils.kw_utils import ekw_access_denied_reason, should_use_native_pdf_export

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# -----------------------------------------------------------------------------
# Logowanie
# -----------------------------------------------------------------------------

LOG_DIR = Path(os.environ.get("USERPROFILE", os.environ.get("HOME", "."))) / "kw_downloader_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"kw_downloader_{time.strftime('%Y%m%d_%H%M%S')}.log"
PROFILE_DIR = LOG_DIR / "playwright_kw_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("KW_Downloader")
logger.setLevel(logging.DEBUG)
logger.propagate = False

if not any(
    isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(LOG_FILE)
    for h in logger.handlers
):
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)

if not any(isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stdout for h in logger.handlers):
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(stream_handler)

# -----------------------------------------------------------------------------
# Konfiguracja
# -----------------------------------------------------------------------------

KW_RE = re.compile(r"^[A-Z0-9]{4}/[0-9]{1,8}/[0-9]$")
KW_SEARCH_URL = (
    "https://przegladarka-ekw.ms.gov.pl/eukw_prz/"
    "KsiegiWieczyste/wyszukiwanieKW?komunikaty=true&kontakt=true&okienkoSerwisowe=false"
)

KW_SPEED_SETTINGS: dict[str, dict[str, int | str]] = {
    "fast": {
        "label": "Szybka",
        "default_timeout_ms": 25000,
        "type_delay_ms": 30,
        "slow_mo_ms": 0,
        "after_search_wait_ms": 700,
        "after_section_wait_ms": 1200,
        "after_pdf_wait_ms": 250,
        "between_sections_ms": 300,
    },
    "normal": {
        "label": "Normalna",
        "default_timeout_ms": 45000,
        "type_delay_ms": 80,
        "slow_mo_ms": 0,
        "after_search_wait_ms": 1500,
        "after_section_wait_ms": 2200,
        "after_pdf_wait_ms": 900,
        "between_sections_ms": 600,
    },
    "slow": {
        "label": "Wolna / stabilna",
        "default_timeout_ms": 70000,
        "type_delay_ms": 160,
        "slow_mo_ms": 120,
        "after_search_wait_ms": 3000,
        "after_section_wait_ms": 4200,
        "after_pdf_wait_ms": 1800,
        "between_sections_ms": 1200,
    },
}


def kw_speed_settings(speed_mode: str) -> dict[str, int | str]:
    return KW_SPEED_SETTINGS.get(speed_mode, KW_SPEED_SETTINGS["normal"])


# -----------------------------------------------------------------------------
# Pomocnicze
# -----------------------------------------------------------------------------


def _find_browser_executable(browser_mode: str) -> str:
    """Zwraca ścieżkę do Opery/Firefoksa, jeśli są zainstalowane."""
    import os
    import shutil
    candidates = []
    if browser_mode == "opera":
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Opera", "opera.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Opera GX", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Opera", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Opera", "launcher.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Opera", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Opera", "launcher.exe"),
            shutil.which("opera") or "",
            shutil.which("opera.exe") or "",
        ]
    elif browser_mode == "firefox":
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Mozilla Firefox", "firefox.exe"),
            shutil.which("firefox") or "",
            shutil.which("firefox.exe") or "",
        ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return ""


def normalize_kw(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def safe_filename(value: str) -> str:
    """Zamienia znaki specjalne na _, ale zachowuje kropki i myślniki."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(value or ""))


def parcel_to_filename(value: str) -> str:
    """
    Zamienia numer działki na format bezpieczny dla nazwy pliku.
    Np. '123/1' -> '123.1', '45/2' -> '45.2'
    """
    return str(value or "").strip().replace("/", ".")


# Mapa pełnej nazwy działu na krótki numer używany w nazwie pliku.
SECTION_NUMBER_MAP: dict[str, str] = {
    "Dział I-O": "1o",
    "Dział I-Sp": "1sp",
    "Dział II": "2",
    "Dział III": "3",
    "Dział IV": "4",
}


def section_to_number(section: str) -> str:
    """Zwraca krótki numer działu (np. 'Dział II' -> '2') do użycia w nazwie pliku."""
    return SECTION_NUMBER_MAP.get(section, safe_filename(section))


def sanitize_filename_component(text: str) -> str:
    """
    Usuwa znaki niedozwolone w nazwach plików Windows (\\ / : * ? " < > |),
    zachowując przy tym spacje, kropki, podkreślenia i myślniki.
    """
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", str(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def build_kw_pdf_filename(parcels: list[str], section: str, kw: str) -> str:
    """
    Buduje nazwę pliku PDF na podstawie powiązanych działek i działu KW.

    Format: "<działki> kw <numer działu>.pdf"
    Np. działka 12/12, Dział II -> "12.12 kw 2.pdf"
    Kilka działek: "12.12_15.3 kw 2.pdf"
    Gdy księga nie ma powiązanych działek, w nazwie użyty jest numer KW.
    """
    if parcels:
        parcel_str = "_".join(parcel_to_filename(p) for p in parcels if str(p).strip())
    else:
        parcel_str = ""

    if not parcel_str:
        parcel_str = safe_filename(kw)

    section_num = section_to_number(section)
    name = f"{parcel_str} kw {section_num}"
    return sanitize_filename_component(name) + ".pdf"


def open_in_file_manager(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def powershell_escape(text: str) -> str:
    return str(text or "").replace("'", "''")


# -----------------------------------------------------------------------------
# Funkcja wstrzykująca nagłówek/stopkę do strony przed wydrukiem
# -----------------------------------------------------------------------------

def build_header_footer_js(
    header_footer_enabled: bool,
    current_url: str,
    black_white_enabled: bool = False,
    desired_filename: str = "",
) -> str:
    """
    Zwraca kod JavaScript wywołujący window.print().

    Nagłówek i stopka (data/godzina, adres URL, numer strony) są teraz
    zapewniane przez WBUDOWANY mechanizm Chrome (patrz
    prepare_chromium_print_preferences -> isHeaderFooterEnabled), więc
    program nie musi już wstrzykiwać własnego, ręcznie stylowanego
    nagłówka/stopki – dzięki temu wygląd wydruku jest identyczny jak w
    standardowym oknie drukowania Adobe PDF / Microsoft Print to PDF.

    Gdy black_white_enabled=True, przed wydrukiem strona dostaje filtr CSS
    grayscale(100%) – działa to niezależnie od ustawień samej drukarki/
    sterownika, więc gwarantuje czarno-biały wydruk bez względu na to, czy
    Adobe/Microsoft/„Save as PDF” respektują ustawienie koloru.

    Gdy desired_filename jest podane, ustawiamy document.title na tę
    nazwę PRZED wywołaniem window.print() – w praktyce jednak WYŁĄCZONE
    (nigdzie już nie wywołujemy tej funkcji z desired_filename), bo
    document.title jest też używany przez natywny nagłówek Chrome
    (isHeaderFooterEnabled) do wyświetlenia adresu strony – nadpisanie
    go nazwą pliku psuło wygląd nagłówka. Zamiast tego nazwa pliku jest
    ustawiana wyłącznie po zapisie, przez _wait_for_pdf_and_ensure_name.
    """
    grayscale_css = (
        "var kwStyle = document.createElement('style');"
        "kwStyle.id = 'kw-grayscale-style';"
        "kwStyle.textContent = '@media print { html { filter: grayscale(100%) !important; "
        "-webkit-filter: grayscale(100%) !important; } }';"
        "document.head.appendChild(kwStyle);"
        if black_white_enabled
        else ""
    )
    safe_title = str(desired_filename or "").replace("\\", "\\\\").replace("'", "\\'")
    title_js = f"document.title = '{safe_title}';" if safe_title else ""
    return f"""
    (function() {{
        {title_js}
        {grayscale_css}
        window.print();
    }})();
    """


def prepare_chromium_print_preferences(
    profile_dir: Path,
    printer_name: str,
    scale_percent: int = 70,
    save_directory: Optional[Path] = None,
    header_footer_enabled: bool = False,
    black_white_enabled: bool = False,
) -> None:
    """
    Ustawia preferencje drukowania Chromium/Chrome.

    isHeaderFooterEnabled odzwierciedla teraz rzeczywisty wybór użytkownika
    (checkbox „Pokaż nagłówek i stopkę”). Dzięki temu program korzysta z
    WBUDOWANEGO, natywnego nagłówka/stopki przeglądarki (data po lewej,
    tytuł/adres pośrodku u góry; adres URL i numer strony na dole) – czyli
    dokładnie takiego wyglądu, jaki widać w standardowym wydruku PDF z
    przeglądarki (Adobe PDF / Microsoft Print to PDF), zamiast własnej,
    ręcznie rysowanej wersji, która wyglądała inaczej.

    black_white_enabled ustawia dodatkowo tryb koloru drukarki na
    czarno-biały (jako uzupełnienie filtru CSS grayscale wstrzykiwanego
    w build_header_footer_js – dwa niezależne mechanizmy dla pewności).
    """
    default_dir = profile_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)

    pref_path = default_dir / "Preferences"
    prefs: dict[str, Any] = {}
    if pref_path.exists():
        try:
            prefs = json.loads(pref_path.read_text(encoding="utf-8"))
            if not isinstance(prefs, dict):
                prefs = {}
        except Exception:
            prefs = {}

    destination_id = "Save as PDF" if printer_name == "Save as PDF" else printer_name
    destination_origin = "local"

    app_state = {
        "recentDestinations": [
            {
                "id": destination_id,
                "origin": destination_origin,
                "account": "",
            }
        ],
        "selectedDestinationId": destination_id,
        "version": 2,
        "isHeaderFooterEnabled": bool(header_footer_enabled),
        "isCssBackgroundEnabled": False,
        "marginsType": 0,
        "isLandscapeEnabled": False,
        "scalingType": 4,
        "scalingTypePdf": 4,
        "scaling": str(int(scale_percent)),
        # 1 = czarno-biały (GRAY), 2 = kolor (COLOR) - schemat Chromium print_preview
        "color": 1 if black_white_enabled else 2,
        "isColorEnabled": not black_white_enabled,
        "mediaSize": {
            "name": "ISO_A4",
            "width_microns": 210000,
            "height_microns": 297000,
            "custom_display_name": "A4",
            "is_default": True,
        },
    }

    printing = prefs.get("printing", {})
    if not isinstance(printing, dict):
        printing = {}
    sticky = printing.get("print_preview_sticky_settings", {})
    if not isinstance(sticky, dict):
        sticky = {}
    sticky["appState"] = json.dumps(app_state, ensure_ascii=False)
    printing["print_preview_sticky_settings"] = sticky
    prefs["printing"] = printing

    target_directory = Path(save_directory) if save_directory else profile_dir

    savefile = prefs.get("savefile", {})
    if not isinstance(savefile, dict):
        savefile = {}
    savefile["default_directory"] = str(target_directory)
    prefs["savefile"] = savefile

    download = prefs.get("download", {})
    if not isinstance(download, dict):
        download = {}
    download["default_directory"] = str(target_directory)
    download["prompt_for_download"] = False
    download["directory_upgrade"] = True
    prefs["download"] = download

    profile_defaults = prefs.get("profile", {})
    if not isinstance(profile_defaults, dict):
        profile_defaults = {}
    content_settings = profile_defaults.get("default_content_setting_values", {})
    if not isinstance(content_settings, dict):
        content_settings = {}
    content_settings["automatic_downloads"] = 1
    profile_defaults["default_content_setting_values"] = content_settings
    prefs["profile"] = profile_defaults

    pref_path.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")


def windows_printer_exists(printer_name: str) -> bool:
    if printer_name == "Save as PDF":
        return True
    if sys.platform != "win32":
        return False
    safe_name = powershell_escape(printer_name)
    ps = (
        f"$p = Get-CimInstance Win32_Printer | Where-Object {{$_.Name -eq '{safe_name}'}}; "
        "if ($p) { 'YES' }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20
    )
    return "YES" in (result.stdout or "")


# -----------------------------------------------------------------------------
# Worker Playwright
# -----------------------------------------------------------------------------

SAVE_DIALOG_PATTERNS = [
    r"save print output as",
    r"save pdf file as",
    r"save as",
    r"save\s+\w+\s+as",
    r"zapisz wydruk jako",
    r"zapisz plik pdf jako",
    r"zapisz.*pdf",
    r"zapisz jako",
    r"drukuj do pliku",
    r"print to file",
    r"zapisywanie",
    r"saving",
    r"zapisz wynik wydruku",
    r"zapisz dokument",
    r"save document",
    r"zapisz plik",
    r"save file",
]


class KWDownloadWorker(QThread):
    log_msg = Signal(str)
    row_status = Signal(str, str)  # kw, status label
    item_finished = Signal(str, bool, str)  # kw, success, final status
    finished_queue = Signal()

    def __init__(
        self,
        kw_queue: list[tuple[str, list[str]]],
        sections: list[str],
        output_dir: Path,
        delay_sec: int = 3,
        speed_mode: str = "normal",
        pdf_printer_name: str = "Microsoft Print to PDF",
        direct_save_enabled: bool = False,
        header_footer_enabled: bool = False,
        direct_pdf_style: str = "zapisz",
        header_style: str = "p1",
        black_white_enabled: bool = False,
        background_mode_enabled: bool = False,
        browser_mode: str = "auto",
        browser_executable_path: str = "",
    ):
        super().__init__()
        # kw_queue to lista krotek (kw, lista_numerow_dzialek)
        self.kw_queue = [(normalize_kw(kw), parcels) for kw, parcels in kw_queue]
        self.sections = list(sections)
        self.output_dir = Path(output_dir)
        self.delay_sec = max(0, int(delay_sec))
        self.speed_mode = speed_mode if speed_mode in KW_SPEED_SETTINGS else "normal"
        self.pdf_printer_name = str(pdf_printer_name or "Microsoft Print to PDF")
        self.direct_save_enabled = bool(direct_save_enabled)
        self.header_footer_enabled = bool(header_footer_enabled)
        self.direct_pdf_style = direct_pdf_style if direct_pdf_style in ("zapisz", "microsoft", "adobe") else "zapisz"
        self.header_style = "p1"
        self.black_white_enabled = bool(black_white_enabled)
        self.background_mode_enabled = bool(background_mode_enabled)
        self.browser_mode = browser_mode if browser_mode in ("auto", "chrome", "msedge", "opera", "firefox") else "auto"
        self.browser_executable_path = str(browser_executable_path or "").strip()
        self.browser_engine = ""  # ustalany przy uruchomieniu kontekstu
        self.profile_dir = LOG_DIR / f"playwright_kw_profile_{int(time.time() * 1000)}"
        self._stop_requested = False
        self.browser_context: Any = None
        self._window_minimized = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        speed = kw_speed_settings(self.speed_mode)

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception:
            msg = (
                "Brak biblioteki Playwright. Zainstaluj:\n"
                "pip install playwright\n"
                "python -m playwright install chromium"
            )
            self.log_msg.emit(msg)
            for kw, _ in self.kw_queue:
                self.item_finished.emit(kw, False, "Błąd Playwright")
            self.finished_queue.emit()
            return

        logger.info("Start pobierania KW. Kolejka: %s", self.kw_queue)
        self.log_msg.emit(f"📋 Start pobierania KW. Log: {LOG_FILE}")
        self.log_msg.emit(f"⚙️ Tempo pracy: {speed.get('label', 'Normalna')}")
        self.log_msg.emit(f"🖨️ Wybrana drukarka PDF: {self.pdf_printer_name}")
        if self.header_footer_enabled:
            self.log_msg.emit("📝 Nagłówek/stopka: WŁĄCZONE (natywny wygląd Chrome – data, adres URL, numer strony)")

        if sys.platform != "win32":
            for kw, _ in self.kw_queue:
                self.item_finished.emit(kw, False, "Tylko Windows")
            self.log_msg.emit("❌ Tryb normalnego drukowania działa tylko na Windows.")
            self.finished_queue.emit()
            return

        if not windows_printer_exists(self.pdf_printer_name):
            for kw, _ in self.kw_queue:
                self.item_finished.emit(kw, False, "Brak drukarki PDF")
            self.log_msg.emit(f"❌ Nie znaleziono drukarki PDF: {self.pdf_printer_name}")
            self.finished_queue.emit()
            return

        self.log_msg.emit("🌐 Otwieram widoczną przeglądarkę Playwright, tak jak w module KRS...")

        try:
            if self.profile_dir.exists():
                shutil.rmtree(self.profile_dir, ignore_errors=True)
            self.profile_dir.mkdir(parents=True, exist_ok=True)

            prepare_chromium_print_preferences(
                self.profile_dir,
                self.pdf_printer_name,
                scale_percent=70,
                save_directory=self.output_dir,
                header_footer_enabled=self.header_footer_enabled,
                black_white_enabled=self.black_white_enabled,
            )
            self.log_msg.emit(
                f"⚙️ Ustawiono preferencje wydruku: drukarka/cel={self.pdf_printer_name}, "
                f"skala=70%, tło=wyłączone"
            )
        except Exception as exc:
            for kw, _ in self.kw_queue:
                self.item_finished.emit(kw, False, "Błąd konfiguracji wydruku")
            self.log_msg.emit(f"❌ Nie udało się przygotować preferencji drukowania: {exc}")
            self.finished_queue.emit()
            return

        visible_context = None
        try:
            with sync_playwright() as p:
                visible_context = self._launch_visible_context(p, speed)
                self.browser_context = visible_context
                try:
                    page = visible_context.pages[0] if visible_context.pages else visible_context.new_page()
                    page.set_default_timeout(int(speed.get("default_timeout_ms", 45000)))

                    for index, (kw, parcels) in enumerate(self.kw_queue):
                        if self._stop_requested:
                            self.log_msg.emit("⛔ Pobieranie przerwane przez użytkownika.")
                            break

                        try:
                            self._download_single_kw(
                                page=page,
                                kw=kw,
                                parcels=parcels,
                                speed=speed,
                                timeout_error_class=PlaywrightTimeoutError,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("Błąd przy pobieraniu KW %s", kw)
                            error_text = str(exc)
                            status = (
                                "Odmowa dostępu"
                                if "Access Denied / Error 15" in error_text
                                else "Błąd PDF"
                            )
                            self.log_msg.emit(f"❌ {kw}: błąd: {error_text}")
                            self.item_finished.emit(kw, False, status)

                        if (
                            index < len(self.kw_queue) - 1
                            and not self._stop_requested
                            and self.delay_sec > 0
                        ):
                            self.log_msg.emit(f"⏳ Czekam {self.delay_sec} s przed kolejną księgą...")
                            for _ in range(self.delay_sec * 10):
                                if self._stop_requested:
                                    break
                                time.sleep(0.1)
                finally:
                    # Zamykamy przeglądarkę TU, jeszcze wewnątrz bloku
                    # `with sync_playwright()` – po jego wyjściu silnik
                    # Playwright jest już zatrzymany i context.close()
                    # kończy się błędem "Event loop is closed".
                    self._close_browser(visible_context)
                    self.browser_context = None
        finally:
            self.finished_queue.emit()
            logger.info("Koniec pobierania KW")

    def _close_browser(self, context: Any) -> None:
        """Zamyka wszystkie karty i cały kontekst przeglądarki na koniec pobierania."""
        if context is None:
            return
        self.log_msg.emit("🧹 Zamykam przeglądarkę...")
        try:
            for pg in list(context.pages):
                try:
                    pg.close()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            context.close()
            self.log_msg.emit("✅ Przeglądarka zamknięta.")
        except Exception as exc:
            logger.warning("Nie udało się zamknąć przeglądarki: %s", exc)
            self.log_msg.emit(f"⚠️ Nie udało się zamknąć przeglądarki: {exc}")

    def _launch_visible_context(self, playwright: Any, speed: dict[str, int | str]) -> Any:
        """Uruchamia widoczną przeglądarkę jak w module KRS."""
        launch_kwargs = dict(
            headless=False,
            accept_downloads=False,
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={"width": 1600, "height": 1000},
            slow_mo=int(speed.get("slow_mo_ms", 0)),
            args=[
                "--start-maximized",
                "--enable-print-browser",
                "--force-renderer-accessibility",
                "--kiosk-printing",
            ],
        )

        last_error: Optional[Exception] = None
        if self.browser_mode == "firefox":
            # Użytkownik wybrał Firefox, więc świadomie używamy zwykłego,
            # zainstalowanego firefox.exe — nigdy po cichu wersji Nightly
            # dołączanej przez Playwright.
            if self.browser_executable_path:
                firefox_path = self.browser_executable_path
                if not Path(firefox_path).is_file():
                    raise RuntimeError(
                        "Wskazana ścieżka do Firefox nie istnieje: "
                        f"{firefox_path}"
                    )
            else:
                firefox_path = _find_browser_executable("firefox")
            if not firefox_path:
                raise RuntimeError(
                    "Nie znaleziono zwykłego Firefox. Zainstaluj Mozilla Firefox "
                    "albo wskaż firefox.exe w ustawieniach modułu KW."
                )

            kwargs = dict(launch_kwargs)
            kwargs.pop("args", None)
            kwargs["executable_path"] = firefox_path
            self.browser_engine = "firefox"
            self.log_msg.emit(
                f"🌐 Uruchamiam zainstalowany Firefox: {firefox_path}"
            )
            try:
                return playwright.firefox.launch_persistent_context(
                    str(self.profile_dir), **kwargs
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Nie udało się uruchomić zainstalowanego Firefox przez "
                    "Playwright. Wybierz Edge/Chrome albo zaktualizuj Firefox. "
                    f"Szczegóły: {exc}"
                ) from exc
        if self.browser_mode == "opera":
            opera_path = _find_browser_executable("opera")
            if not opera_path:
                raise RuntimeError("Nie znaleziono Opera. Zainstaluj Operę albo wybierz inną przeglądarkę.")
            kwargs = dict(launch_kwargs)
            kwargs["executable_path"] = opera_path
            self.browser_engine = "chromium"
            self.log_msg.emit(f"🌐 Uruchamiam Operę: {opera_path}")
            return playwright.chromium.launch_persistent_context(str(self.profile_dir), **kwargs)
        self.browser_engine = "chromium"
        channels = {"auto": ("chrome", "msedge", None), "chrome": ("chrome",), "msedge": ("msedge",)}.get(self.browser_mode, ("chrome", "msedge", None))
        for channel in channels:
            try:
                kwargs = dict(launch_kwargs)
                if channel:
                    kwargs["channel"] = channel
                    self.log_msg.emit(f"🌐 Próbuję uruchomić przeglądarkę kanałem: {channel}")
                else:
                    self.log_msg.emit("🌐 Próbuję uruchomić domyślne Playwright Chromium")
                return playwright.chromium.launch_persistent_context(str(self.profile_dir), **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Nie udało się uruchomić kanału %s: %s", channel, exc)

        raise RuntimeError(
            "Nie udało się uruchomić widocznej przeglądarki Playwright. "
            f"Szczegóły: {last_error}. Sprawdź instalację: python -m playwright install chromium"
        )

    def _download_single_kw(
        self,
        page: Any,
        kw: str,
        parcels: list[str],
        speed: dict[str, int | str],
        timeout_error_class: type[Exception],
    ) -> None:
        if not KW_RE.fullmatch(kw):
            self.log_msg.emit(f"❌ {kw}: niepoprawny format numeru KW.")
            self.item_finished.emit(kw, False, "Błąd formatu")
            return

        match = re.fullmatch(r"([A-Z0-9]{4})/([0-9]{1,8})/([0-9])", kw)
        assert match is not None
        department, number, control = match.groups()

        self.row_status.emit(kw, "W trakcie")
        self.log_msg.emit(f"🔎 Otwieram KW: {kw}")
        self.log_msg.emit(
            "ℹ️ Wykryta odmowa eKW (Access Denied / Error 15) zostanie zgłoszona "
            "dla tej księgi bez prób obchodzenia zabezpieczenia."
        )

        page.goto(KW_SEARCH_URL, wait_until="domcontentloaded", timeout=90000)
        self._wait_for_kw_form(page, timeout_error_class)

        if self._stop_requested:
            self.item_finished.emit(kw, False, "Przerwano")
            return

        self.log_msg.emit(f"⌨️ Wpisuję numer KW: {kw}")
        self._fill_form(page, department, number, control, int(speed.get("type_delay_ms", 80)))
        page.wait_for_timeout(int(speed.get("after_search_wait_ms", 1500)))

        result = self._wait_for_search_result(page)
        if result is None:
            self.log_msg.emit(f"⛔ {kw}: przerwano.")
            self.item_finished.emit(kw, False, "Przerwano")
            return
        if result.startswith("BLOCKED:"):
            error_text = result[8:].strip() or "Odmowa dostępu serwisu eKW"
            self.log_msg.emit(f"⛔ {kw}: {error_text}")
            self.item_finished.emit(kw, False, "Odmowa dostępu")
            return
        if result.startswith("ERR:"):
            error_text = result[4:].strip() or "Błąd księgi"
            self.log_msg.emit(f"❌ {kw}: {error_text}")
            self.item_finished.emit(kw, False, "Błąd księgi")
            return
        if result == "NO_RESULT":
            self.log_msg.emit(f"❌ {kw}: nie znaleziono księgi.")
            self.item_finished.emit(kw, False, "Błąd księgi")
            return

        self.log_msg.emit(f"📄 {kw}: otwieram stronę wydruku zwykłego...")
        try:
            page.click("#przyciskWydrukZwykly", timeout=15000)
        except Exception:
            pass
        try:
            page.wait_for_url("**/pokazWydruk**", timeout=45000)
        except Exception:
            pass
        page.wait_for_timeout(1500)

        if not self.sections:
            self.item_finished.emit(kw, False, "Brak działów")
            return

        blocked_reason = self._ekw_access_denied_reason(page)
        if blocked_reason:
            self.log_msg.emit(f"⛔ {kw}: {blocked_reason}")
            self.item_finished.emit(kw, False, "Odmowa dostępu")
            return

        first_selector = f'input[value="{self.sections[0]}"]'
        page.wait_for_selector(first_selector, timeout=30000)

        failed_sections: list[str] = []
        saved_files: list[Path] = []

        for idx, section in enumerate(self.sections):
            if self._stop_requested:
                self.item_finished.emit(kw, False, "Przerwano")
                return

            selector = f'input[value="{section}"]'
            self.log_msg.emit(f"📚 {kw}: pobieram {section}")

            # WAŻNE: linki/pola do wszystkich działów (I-O, I-Sp, II, III, IV)
            # są cały czas widoczne na TEJ SAMEJ stronie „pokazWydruk” –
            # niezależnie od tego, który dział jest akurat wyświetlony.
            # Dlatego między działami NIE nawigujemy (żadnego go_back()
            # ani goto()) – taka nawigacja unieważniała sesję na stronie
            # rządowej (przekierowanie na „sesjaWygasla=true”). Po prostu
            # klikamy kolejny dział bezpośrednio na aktualnej stronie.
            try:
                page.wait_for_selector(selector, timeout=10000)
                page.click(selector, timeout=10000)
                page.wait_for_timeout(int(speed.get("after_section_wait_ms", 2200)))
                blocked_reason = self._ekw_access_denied_reason(page)
                if blocked_reason:
                    self.log_msg.emit(f"⛔ {kw}: {blocked_reason}")
                    self.item_finished.emit(kw, False, "Odmowa dostępu")
                    return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nie udało się otworzyć działu %s dla %s: %s", section, kw, exc)
                self.log_msg.emit(f"⚠️ {kw}: nie udało się kliknąć działu {section}")
                failed_sections.append(section)
                continue

            try:
                pdf_path = self._save_current_section_as_pdf(
                    source_page=page,
                    kw=kw,
                    parcels=parcels,
                    section=section,
                    after_pdf_wait_ms=int(speed.get("after_pdf_wait_ms", 900)),
                )
                saved_files.append(pdf_path)
                self.log_msg.emit(f"✅ Zapisano: {pdf_path.name}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Błąd zapisu PDF dla %s / %s", kw, section)
                self.log_msg.emit(f"❌ {kw}: błąd zapisu PDF dla {section}: {exc}")
                failed_sections.append(section)

            if idx < len(self.sections) - 1:
                page.wait_for_timeout(int(speed.get("between_sections_ms", 600)))

        if failed_sections and saved_files:
            self.item_finished.emit(kw, False, "Błąd PDF")
            self.log_msg.emit(
                f"⚠️ {kw}: część działów pobrana, część nie ({', '.join(failed_sections)})"
            )
        elif failed_sections:
            self.item_finished.emit(kw, False, "Błąd PDF")
            self.log_msg.emit(
                f"❌ {kw}: nie udało się pobrać działów: {', '.join(failed_sections)}"
            )
        else:
            self.item_finished.emit(kw, True, "Pobrano PDF")
            self.log_msg.emit(f"✅ {kw}: pobrano {len(saved_files)} plików PDF.")

    def _minimize_browser_window(self, page: Any) -> None:
        """
        Minimalizuje okno przeglądarki, żeby program mógł pracować w tle
        i nie przeszkadzać w innej pracy na komputerze. Wywoływane raz, po
        potwierdzeniu, że formularz KW jest widoczny (żeby użytkownik miał
        szansę ręcznie potwierdzić ewentualny komunikat/blokadę zanim
        okno zniknie z widoku).
        """
        try:
            from pywinauto import Desktop
        except Exception:
            self.log_msg.emit("⚠️ Nie można zminimalizować przeglądarki – brak pywinauto.")
            return

        try:
            desktop = Desktop(backend="uia")
            title_pattern = re.compile(r"ekw\.ms\.gov\.pl|ksi[ęe]gi wieczyste|google chrome|microsoft edge|msedge|chromium|opera|firefox", re.IGNORECASE)
            target = None
            for window in desktop.windows():
                try:
                    if not window.is_visible():
                        continue
                    title = window.window_text() or ""
                    if title_pattern.search(title):
                        target = window
                        break
                except Exception:
                    continue

            if target is not None:
                target.minimize()
                self._window_minimized = True
                self.log_msg.emit("🔽 Okno przeglądarki zminimalizowane – program pracuje w tle.")
            else:
                self.log_msg.emit("⚠️ Nie znaleziono okna przeglądarki do zminimalizowania.")
        except Exception as exc:
            logger.warning("Nie udało się zminimalizować okna przeglądarki: %s", exc)
            self.log_msg.emit(f"⚠️ Nie udało się zminimalizować przeglądarki: {exc}")

    def _ekw_access_denied_reason(self, page: Any) -> str:
        """Rozpoznaje stronę odmowy eKW bez prób obchodzenia zabezpieczenia."""
        parts: list[str] = []
        try:
            parts.append(str(page.title() or ""))
        except Exception:
            pass
        try:
            parts.append(str(page.url or ""))
        except Exception:
            pass
        try:
            body = page.locator("body").inner_text(timeout=1500)
            parts.append(str(body or "")[:4000])
        except Exception:
            pass
        return ekw_access_denied_reason("\n".join(parts))

    def _wait_for_kw_form(self, page: Any, timeout_error_class: type[Exception]) -> None:
        start = time.time()
        while time.time() - start < 180:
            if self._stop_requested:
                raise RuntimeError("Pobieranie przerwane przez użytkownika.")
            blocked_reason = self._ekw_access_denied_reason(page)
            if blocked_reason:
                self.log_msg.emit(f"⛔ {blocked_reason}")
                raise RuntimeError(blocked_reason)
            try:
                if page.locator("#kodWydzialuInput").count() > 0:
                    page.wait_for_selector("#kodWydzialuInput", timeout=2000)
                else:
                    page.wait_for_selector("#kodWydzialu", timeout=2000)
                page.wait_for_selector("#numerKsiegiWieczystej", timeout=2000)
                page.wait_for_selector("#cyfraKontrolna", timeout=2000)
                page.wait_for_selector("#wyszukaj", timeout=2000)
                self.log_msg.emit("✅ Formularz KW jest widoczny.")
                if self.background_mode_enabled and not self._window_minimized:
                    self._minimize_browser_window(page)
                return
            except timeout_error_class:
                if int(time.time() - start) in (10, 30, 60, 120):
                    self.log_msg.emit(
                        "⏳ Nadal czekam na formularz KW. Sprawdź widoczną przeglądarkę — "
                        "jeśli pojawił się komunikat lub blokada, potwierdź ręcznie."
                    )
                continue

        current_url = ""
        current_title = ""
        try:
            current_url = page.url
        except Exception:
            pass
        try:
            current_title = page.title()
        except Exception:
            pass

        raise RuntimeError(
            "Nie pojawił się formularz KW (#kodWydzialu) w 180 s. "
            f"Aktualny URL: {current_url!r}, tytuł strony: {current_title!r}"
        )

    def _fill_form(self, page: Any, department: str, number: str, control: str, delay_ms: int) -> None:
        if page.locator("#kodWydzialuInput").count() > 0:
            department_input = page.locator("#kodWydzialuInput")
            department_input.click(timeout=5000)
            department_input.fill("")
            department_input.type(department, delay=delay_ms)
        else:
            try:
                page.select_option("#kodWydzialu", department)
            except Exception:
                department_input = page.locator("#kodWydzialu")
                department_input.click(timeout=5000)
                department_input.fill("")
                department_input.type(department, delay=delay_ms)

        number_input = page.locator("#numerKsiegiWieczystej")
        number_input.click(timeout=5000)
        number_input.fill("")
        number_input.type(number, delay=delay_ms)

        control_input = page.locator("#cyfraKontrolna")
        control_input.click(timeout=5000)
        control_input.fill("")
        control_input.type(control, delay=delay_ms)

        page.locator("#wyszukaj").click(timeout=10000, no_wait_after=True)

    def _wait_for_search_result(self, page: Any) -> Optional[str]:
        for _ in range(60):
            if self._stop_requested:
                return None
            page.wait_for_timeout(1000)
            blocked_reason = self._ekw_access_denied_reason(page)
            if blocked_reason:
                return f"BLOCKED:{blocked_reason}"
            result = page.evaluate(
                """() => {
                    if (location.href.indexOf('pokazWydruk') >= 0) return 'SECTIONS';
                    const btn = document.getElementById('przyciskWydrukZwykly');
                    if (btn) return 'MAIN';
                    const err = document.querySelector('.content .error, .content .msg, .error');
                    if (err && err.innerText && err.innerText.trim()) return 'ERR:' + err.innerText.trim();
                    return 'WAIT';
                }"""
            )
            if result in ("MAIN", "SECTIONS"):
                return "OK"
            if isinstance(result, str) and result.startswith("ERR:"):
                return result
        return "NO_RESULT"

    def _save_current_section_as_pdf(
        self,
        source_page: Any,
        kw: str,
        parcels: list[str],
        section: str,
        after_pdf_wait_ms: int,
    ) -> Path:
        # Nazwa pliku budowana z powiązanych działek + "kw" + numer działu,
        # np. działka 12/12, Dział II -> "12.12 kw 2.pdf"
        filename = build_kw_pdf_filename(parcels, section, kw)
        pdf_path = self.output_dir / filename

        source_page.wait_for_timeout(after_pdf_wait_ms)
        if should_use_native_pdf_export(
            self.direct_save_enabled,
            self.pdf_printer_name,
            self.browser_engine,
        ):
            # W Chrome/Edge/Operze page.pdf() zapisuje od razu wskazany plik.
            # Nie otwieramy window.print(), bo opcja „Save as PDF” w Edge nie
            # wybiera automatycznie nazwy pliku i wcześniej powodowała czekanie
            # bez utworzenia PDF.
            self._save_current_section_via_browser_pdf(source_page, pdf_path)
            return pdf_path

        if self.pdf_printer_name == "Save as PDF":
            raise RuntimeError(
                "Wybrana przeglądarka nie obsługuje bezpośredniego zapisu PDF. "
                "Dla Firefox wybierz Microsoft Print to PDF albo Adobe PDF."
            )

        self._print_page_via_system_dialog(source_page, pdf_path)
        return pdf_path

    def _save_current_section_via_browser_pdf(
        self,
        page: Any,
        pdf_path: Path,
    ) -> None:
        """Zapisuje bieżący dział bezpośrednio przez silnik Chromium.

        To świadomie nie używa systemowego dialogu „Save as PDF”. W Edge ten
        dialog nie przyjmuje nazwy z preferencji profilu i potrafi pozostawić
        zadanie na ekranie drukowania, mimo że moduł czeka na plik.
        """
        try:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            if pdf_path.exists():
                pdf_path.unlink()
        except OSError as exc:
            raise RuntimeError(
                f"Nie można przygotować pliku PDF: {pdf_path} ({exc})"
            ) from exc

        if self.black_white_enabled:
            try:
                page.add_style_tag(
                    content=(
                        "@media print { html { filter: grayscale(100%) !important; "
                        "-webkit-filter: grayscale(100%) !important; } }"
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nie udało się dodać filtru czarno-białego: %s", exc)

        options: dict[str, Any] = {
            "path": str(pdf_path),
            "format": "A4",
            "landscape": False,
            "scale": 0.70,
            "print_background": False,
            "prefer_css_page_size": False,
            "display_header_footer": bool(self.header_footer_enabled),
            "margin": {
                "top": "0.45in" if self.header_footer_enabled else "0.25in",
                "bottom": "0.45in" if self.header_footer_enabled else "0.25in",
                "left": "0.25in",
                "right": "0.25in",
            },
        }
        if self.header_footer_enabled:
            options["header_template"] = (
                "<div style='font-size:7px;width:100%;padding:0 12px;color:#555;'>"
                "<span class='date'></span> &nbsp; <span class='title'></span></div>"
            )
            options["footer_template"] = (
                "<div style='font-size:7px;width:100%;padding:0 12px;color:#555;'>"
                "<span class='url'></span>"
                "<span style='float:right'>Strona <span class='pageNumber'></span> / "
                "<span class='totalPages'></span></span></div>"
            )

        self.log_msg.emit(f"⚡ Zapisuję PDF bezpośrednio: {pdf_path.name}")
        try:
            page.pdf(**options)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Przeglądarka nie zapisała PDF bezpośrednio. "
                f"Szczegóły: {exc}"
            ) from exc

        try:
            if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
                raise OSError("plik nie został utworzony lub jest pusty")
        except OSError as exc:
            raise RuntimeError(
                f"PDF nie został zapisany w folderze docelowym: {pdf_path} ({exc})"
            ) from exc
        self.log_msg.emit(f"✅ Wydrukowano do PDF: {pdf_path.name}")

    def _print_page_via_system_dialog(self, page: Any, pdf_path: Path) -> None:
        # „Save as PDF” jest obsługiwane przez page.pdf() w metodzie wyżej.
        # Nie wolno tu wpadać w oczekiwanie na nieistniejący automatyczny zapis.
        if self.pdf_printer_name == "Save as PDF":
            raise RuntimeError(
                "Opcja „Save as PDF” wymaga bezpośredniego zapisu Chromium."
            )
        try:
            from pywinauto import Desktop
            from pywinauto.keyboard import send_keys
        except Exception:
            raise RuntimeError("Brak biblioteki pywinauto. Zainstaluj: pip install pywinauto")

        if pdf_path.exists():
            try:
                pdf_path.unlink()
            except Exception:
                pass

        # Migawka plików PDF istniejących w folderze PRZED wydrukiem – dzięki
        # temu, nawet jeśli system/Adobe zapisze plik pod inną nazwą (np.
        # wygenerowaną z adresu strony "przegladarka-ekw.ms.gov.pl_..."),
        # program rozpozna, który plik jest tym nowo zapisanym, i zmieni mu
        # nazwę na właściwą.
        before_snapshot = self._list_pdf_files(self.output_dir)

        if not self.background_mode_enabled:
            page.bring_to_front()
        self.log_msg.emit(f"🖨️ Drukuję do celu PDF: {self.pdf_printer_name}")

        current_url = ""
        try:
            current_url = page.url
        except Exception:
            pass

        # Nie wstrzykujemy żadnego CSS zmieniającego wygląd/rama/tabele.
        # Wygląd ma być taki jak w prawdziwym wydruku przeglądarki.
        js_code = build_header_footer_js(
            self.header_footer_enabled,
            current_url,
            black_white_enabled=self.black_white_enabled,
        )
        page.evaluate(js_code)

        desktop = Desktop(backend="uia")

        # Adobe PDF / Microsoft Print to PDF
        self.log_msg.emit("⏳ Oczekiwanie na okno dialogowe zapisu PDF...")
        self._log_visible_windows(desktop)

        save_window = self._find_save_dialog_robust(desktop, timeout_sec=120)
        if save_window is None:
            raise RuntimeError(
                "Nie znaleziono okna dialogowego zapisu PDF. "
                "Sprawdź, czy drukarka PDF jest dostępna i czy okno się pojawiło."
            )

        # Nie przechodzimy osobno do folderu przez Ctrl+L, bo w części okien
        # Adobe/Microsoft PDF fokus trafiał w pole nazwy pliku i folder był
        # wpisywany jako nazwa. Wpisujemy od razu PEŁNĄ ścieżkę pliku w pole
        # „Nazwa pliku”, co zapisuje bezpośrednio do właściwego folderu.
        self.log_msg.emit(f"💾 Znaleziono okno zapisu. Wpisuję pełną ścieżkę pliku: {pdf_path}")
        self._fill_and_confirm_save_dialog(save_window, pdf_path)

        self._handle_optional_overwrite_dialog(desktop)

        # Dłuższy timeout dla dużych ksiąg (nawet 5 minut). Sprawdzamy nie
        # tylko dokładną nazwę, ale KAŻDY nowy plik PDF w folderze – jeśli
        # zapisał się pod inną nazwą, program sam ją poprawi.
        self._wait_for_pdf_and_ensure_name(before_snapshot, pdf_path, timeout_sec=300)
        self.log_msg.emit(f"✅ Wydrukowano do PDF: {pdf_path.name}")

        # Po zapisie (szczególnie Adobe PDF potrafi otworzyć podgląd/okno
        # z zapisanym plikiem) domykamy wszystko, co mogło zostać otwarte,
        # i wracamy do przeglądarki – inaczej program „zawiesza się” na
        # otwartym oknie, a status pozycji nie aktualizuje się prawidłowo.
        self._finalize_after_pdf_save(page, desktop)

    def _list_pdf_files(self, folder: Path) -> dict[Path, float]:
        """Zwraca mapę {ścieżka: czas_modyfikacji} plików PDF w folderze."""
        result: dict[Path, float] = {}
        try:
            for f in folder.glob("*.pdf"):
                try:
                    result[f] = f.stat().st_mtime
                except Exception:
                    continue
        except Exception:
            pass
        return result

    def _navigate_save_dialog_to_folder(self, window: Any, folder: Path) -> bool:
        """
        Ustawia folder docelowy w oknie zapisu, wpisując pełną ścieżkę w
        pasku adresu. Ctrl+L to standardowy skrót Windows przełączający
        pasek adresu w tryb edycji – działa niezależnie od tego, jak
        dana aplikacja (Adobe, Microsoft Print to PDF) nazwała swoje
        kontrolki, więc jest dużo bardziej niezawodny niż szukanie
        konkretnej kontrolki.
        """
        from pywinauto.keyboard import send_keys

        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            window.set_focus()
            time.sleep(0.2)
            send_keys("^l")  # Ctrl+L -> tryb edycji paska adresu
            time.sleep(0.3)
            send_keys("^a{BACKSPACE}")
            time.sleep(0.1)
            send_keys(str(folder), with_spaces=True)
            time.sleep(0.2)
            send_keys("{ENTER}")
            time.sleep(0.8)
            self.log_msg.emit(f"✅ Ustawiono folder zapisu: {folder}")
            return True
        except Exception as exc:
            self.log_msg.emit(
                f"⚠️ Nie udało się ustawić folderu przez pasek adresu ({exc}); "
                "program i tak rozpozna zapisany plik po fakcie."
            )
            return False

    def _wait_for_pdf_and_ensure_name(
        self,
        before_snapshot: dict[Path, float],
        target_path: Path,
        timeout_sec: int,
    ) -> None:
        """
        Czeka na zapisanie pliku PDF i gwarantuje, że będzie miał właściwą
        nazwę. Rozpoznaje NOWY plik PDF w folderze docelowym (ten, którego
        nie było w migawce sprzed wydruku, lub który ma nowszy czas
        modyfikacji) niezależnie od tego, jaką nazwę faktycznie nadał mu
        system/drukarka – co rozwiązuje przypadek, gdy plik zapisuje się
        pod nazwą wygeneriowaną z adresu strony zamiast żądanej nazwy.
        """
        end_time = time.time() + timeout_sec
        last_size: dict[Path, int] = {}
        stable_counts: dict[Path, int] = {}

        while time.time() < end_time:
            if self._stop_requested:
                raise RuntimeError("Pobieranie przerwane przez użytkownika.")

            current = self._list_pdf_files(self.output_dir)

            candidates: list[Path] = []
            if target_path in current:
                candidates.append(target_path)
            for path, mtime in current.items():
                if path == target_path:
                    continue
                if path not in before_snapshot or mtime > before_snapshot.get(path, 0):
                    candidates.append(path)

            for candidate in candidates:
                try:
                    size = candidate.stat().st_size
                except Exception:
                    continue
                if size <= 0:
                    continue
                if last_size.get(candidate) == size:
                    stable_counts[candidate] = stable_counts.get(candidate, 0) + 1
                else:
                    stable_counts[candidate] = 0
                last_size[candidate] = size

                if stable_counts[candidate] >= 3:
                    if candidate != target_path:
                        self.log_msg.emit(
                            f"📝 Plik zapisał się pod inną nazwą ('{candidate.name}') – "
                            f"zmieniam na '{target_path.name}'."
                        )
                        self._rename_saved_pdf(candidate, target_path)
                    return

            time.sleep(0.5)

        raise RuntimeError(
            f"Plik PDF nie został zapisany w oczekiwanym czasie w folderze: {self.output_dir}"
        )

    def _rename_saved_pdf(self, source: Path, target: Path) -> None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                try:
                    target.unlink()
                except Exception:
                    pass
            source.rename(target)
        except Exception as exc:
            logger.warning("Nie udało się zmienić nazwy %s -> %s: %s", source, target, exc)
            self.log_msg.emit(f"⚠️ Nie udało się zmienić nazwy pliku {source.name}: {exc}")

    def _finalize_after_pdf_save(self, page: Any, desktop: Any) -> None:
        """Domyka okna pozostałe po zapisie PDF (np. podgląd Adobe Acrobat)
        i automatycznie wraca do karty z Księgą Wieczystą, żeby program mógł
        kontynuować pobieranie kolejnego działu."""
        try:
            self._close_lingering_print_windows(desktop)
        except Exception as exc:
            logger.warning("Nie udało się domknąć pozostałych okien po zapisie PDF: %s", exc)

        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

        self._switch_back_to_kw_tab(page)

    def _switch_back_to_kw_tab(self, page: Any) -> None:
        """
        Zamyka dodatkowe karty przeglądarki, które mogły zostać otwarte
        podczas drukowania (np. karta podglądu wydruku), i przełącza
        (bring_to_front) z powrotem na kartę z Księgą Wieczystą.
        """
        context = self.browser_context
        if context is not None:
            try:
                for other_page in list(context.pages):
                    if other_page is page:
                        continue
                    try:
                        other_page.close()
                        self.log_msg.emit("🧹 Zamknięto dodatkową kartę przeglądarki.")
                    except Exception:
                        pass
            except Exception:
                pass

        if self.background_mode_enabled:
            # W trybie pracy w tle NIE przywracamy okna (żadnego
            # bring_to_front) – ma pozostać zminimalizowane przez cały
            # czas działania programu, ani na sekundę się nie pokazując.
            return

        try:
            page.bring_to_front()
            self.log_msg.emit("↩️ Wracam do karty z Księgą Wieczystą.")
        except Exception as exc:
            logger.warning("Nie udało się wrócić do karty z KW: %s", exc)

    def _close_lingering_print_windows(self, desktop: Any) -> None:
        """
        Szuka i zamyka WYŁĄCZNIE okna Adobe Acrobat/Reader, które program
        Adobe potrafi otworzyć automatycznie po zapisaniu PDF (podgląd
        zapisanego pliku). Celowo NIE rozpoznajemy tu ogólnych fraz typu
        „podgląd wydruku” / „drukowanie”, bo strona Ksiąg Wieczystych może
        mieć podobny tytuł karty/okna – zamknięcie jej przerywałoby
        pobieranie kolejnych działów. Nie dotykamy też okna samej
        przeglądarki (Chrome/Edge/Chromium).
        """
        leftover_pattern = re.compile(
            r"\bacrobat\b",
            re.IGNORECASE,
        )
        browser_pattern = re.compile(
            r"google chrome|microsoft edge|chromium|opera|firefox|przegl[ąa]darka|ekw|ksi[ęe]gi wieczyste",
            re.IGNORECASE,
        )

        closed_any = False
        for window in desktop.windows():
            try:
                if not window.is_visible():
                    continue
                title = (window.window_text() or "").strip()
                if not title or not leftover_pattern.search(title):
                    continue
                if browser_pattern.search(title):
                    continue

                self.log_msg.emit(f"🧹 Domykam okno podglądu Adobe: '{title}'")
                try:
                    window.close()
                    closed_any = True
                except Exception:
                    try:
                        window.set_focus()
                        from pywinauto.keyboard import send_keys

                        send_keys("%{F4}")
                        closed_any = True
                    except Exception:
                        continue
            except Exception:

                continue

        if closed_any:
            time.sleep(0.5)

    def _log_visible_windows(self, desktop: Any) -> None:
        try:
            titles = []
            for window in desktop.windows():
                try:
                    if window.is_visible():
                        title = (window.window_text() or "").strip()
                        if title:
                            titles.append(title)
                except Exception:
                    continue
            if titles:
                self.log_msg.emit("🔍 Widoczne okna na pulpicie: " + " | ".join(titles[:20]))
        except Exception:
            pass

    def _find_save_dialog_robust(self, desktop: Any, timeout_sec: int) -> Optional[Any]:
        end_time = time.time() + timeout_sec
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in SAVE_DIALOG_PATTERNS]

        while time.time() < end_time:
            for window in desktop.windows():
                try:
                    if not window.is_visible():
                        continue
                    title = (window.window_text() or "").strip()
                    if not title:
                        continue

                    # Metoda 1: tytuł pasuje do wzorca
                    if any(p.search(title) for p in compiled_patterns):
                        self.log_msg.emit(f"✅ Znaleziono okno po tytule: '{title}'")
                        return window

                    # Metoda 2: ma Edit i przycisk Zapisz/Save
                    try:
                        edits = [
                            c for c in window.descendants(control_type="Edit")
                            if c.is_visible()
                        ]
                        if edits:
                            buttons = [
                                c for c in window.descendants(control_type="Button")
                                if c.is_visible()
                            ]
                            for btn in buttons:
                                btn_text = (btn.window_text() or "").strip().lower()
                                if any(kw in btn_text for kw in ["zapisz", "save", "drukuj", "print", "ok"]):
                                    self.log_msg.emit(
                                        f"✅ Znaleziono okno '{title}' z polem Edit i przyciskiem '{btn_text}'"
                                    )
                                    return window
                    except Exception:
                        continue

                except Exception:
                    continue
            time.sleep(0.3)

        self.log_msg.emit("⏰ Minął limit czasu oczekiwania na okno zapisu PDF")
        return None

    def _find_filename_edit_control(self, window: Any) -> Optional[Any]:
        """
        Znajduje pole „Nazwa pliku” w oknie zapisu, pomijając pole
        wyszukiwarki (np. „Szukaj w: Dokumenty”), które w oknie zapisu
        Microsoft Print to PDF też jest kontrolką typu Edit i bywa mylnie
        wybierane, przez co nazwa pliku trafiała do wyszukiwarki zamiast
        do pola nazwy pliku.
        """
        # Metoda 1: standardowy automation_id pola nazwy pliku w oknie
        # zapisu Windows (klasyczny common dialog GetSaveFileName).
        for auto_id in ("1148", "FileNameControlHost"):
            try:
                candidate = window.child_window(auto_id=auto_id, control_type="Edit")
                if candidate.exists() and candidate.is_visible():
                    return candidate
            except Exception:
                pass

        # Metoda 2: pole opisane etykietą „Nazwa pliku:” / „File name:”.
        try:
            candidate = window.child_window(
                title_re=r"(?i)^(nazwa pliku|file name)", control_type="Edit"
            )
            if candidate.exists() and candidate.is_visible():
                return candidate
        except Exception:
            pass

        # Metoda 3: przefiltruj widoczne pola Edit, odrzucając pole
        # wyszukiwarki oraz pasek adresu (które w oknie zapisu też są
        # kontrolkami typu Edit i bywały mylnie wybierane – nazwa pliku
        # trafiała wtedy do wyszukiwarki albo do adresu zamiast do pola
        # nazwy pliku).
        try:
            edits = [
                ctrl for ctrl in window.descendants(control_type="Edit")
                if ctrl.is_visible()
            ]
        except Exception:
            edits = []

        exclude_pattern = re.compile(
            r"search|szukaj|address|adres|location|[śs]cie[żz]ka|breadcrumb",
            re.IGNORECASE,
        )
        candidates: list[tuple[int, Any]] = []
        for ctrl in edits:
            auto_id = ""
            name = ""
            try:
                auto_id = str(getattr(getattr(ctrl, "element_info", None), "automation_id", "") or "")
            except Exception:
                pass
            try:
                name = str(getattr(getattr(ctrl, "element_info", None), "name", "") or "")
            except Exception:
                pass
            if exclude_pattern.search(auto_id) or exclude_pattern.search(name):
                continue
            try:
                top = ctrl.rectangle().top
            except Exception:
                top = -1
            candidates.append((top, ctrl))

        if candidates:
            # Pole „Nazwa pliku” znajduje się zwykle najniżej w oknie
            # (tuż nad przyciskami Zapisz/Anuluj), a pasek adresu i
            # wyszukiwarka są wyżej – sortujemy po pozycji pionowej.
            candidates.sort(key=lambda pair: pair[0])
            return candidates[-1][1]
        if edits:
            return edits[-1]
        return None

    def _edit_control_text(self, ctrl: Any) -> str:
        for getter in ("get_value", "window_text", "texts"):
            try:
                fn = getattr(ctrl, getter, None)
                if fn is None:
                    continue
                value = fn()
                if isinstance(value, list):
                    value = " ".join(str(v) for v in value)
                if value:
                    return str(value)
            except Exception:
                continue
        return ""

    def _verify_filename_typed(self, window: Any, pdf_path: Path) -> bool:
        """Sprawdza, czy w KTÓRYMKOLWIEK widocznym polu Edit okna zapisu
        pojawił się fragment wpisanej nazwy pliku – potwierdza to, że
        tekst trafił we właściwe miejsce, a nie np. do wyszukiwarki."""
        needle = pdf_path.stem.strip().lower()
        probe = needle[:10] if len(needle) > 10 else needle
        if not probe:
            return False
        try:
            edits = [c for c in window.descendants(control_type="Edit") if c.is_visible()]
        except Exception:
            edits = []
        for ctrl in edits:
            text = self._edit_control_text(ctrl).lower()
            if probe in text:
                return True
        return False

    def _type_filename_via_access_key(self, window: Any, pdf_path: Path) -> bool:
        """
        Ustawia fokus na polu „Nazwa pliku” standardowym skrótem Windows
        Alt+N (podkreślona litera N w „Nazwa pliku:” / „File _name:”),
        zamiast zgadywać, która kontrolka Edit to właściwe pole. Ten
        skrót działa identycznie w oknie zapisu Microsoft Print to PDF,
        Adobe PDF i w standardowym oknie „Zapisz jako” Windows, więc
        eliminuje ryzyko wpisania nazwy do paska adresu lub wyszukiwarki.
        """
        from pywinauto.keyboard import send_keys

        try:
            window.set_focus()
            time.sleep(0.2)
            send_keys("%n")  # Alt+N -> fokus na polu "Nazwa pliku:"
            time.sleep(0.3)
            send_keys("^a{BACKSPACE}")
            time.sleep(0.1)
            full_path = str(pdf_path.resolve())
            send_keys(full_path, with_spaces=True)
            time.sleep(0.3)
        except Exception as exc:
            self.log_msg.emit(f"⚠️ Skrót Alt+N nie zadziałał: {exc}")
            return False

        if self._verify_filename_typed(window, pdf_path):
            self.log_msg.emit(f"✅ Wpisano pełną ścieżkę pliku (Alt+N): {pdf_path}")
            return True

        self.log_msg.emit(
            "⚠️ Po Alt+N nie znaleziono wpisanej nazwy w żadnym polu – "
            "prawdopodobnie trafiła do niewłaściwego pola (np. adresu)."
        )
        return False

    def _fill_and_confirm_save_dialog(self, window: Any, pdf_path: Path) -> None:
        from pywinauto.keyboard import send_keys

        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            window.set_focus()
        except Exception:
            pass
        time.sleep(0.5)

        self.log_msg.emit(f"💾 Wpisuję pełną ścieżkę pliku: {pdf_path}")

        # KROK 1a: najpierw spróbuj standardowego skrótu Alt+N (najbardziej
        # niezawodna metoda – nie zależy od zgadywania która kontrolka
        # Edit to pole nazwy pliku).
        filename_set = self._type_filename_via_access_key(window, pdf_path)

        # KROK 1b: jeśli Alt+N zawiódł, spróbuj wskazać pole Edit ręcznie.
        if not filename_set:
            try:
                edit = self._find_filename_edit_control(window)
                if edit is not None:
                    try:
                        edit.set_focus()
                        time.sleep(0.2)
                        try:
                            edit.set_edit_text("")
                        except Exception:
                            send_keys("^a{BACKSPACE}")
                        time.sleep(0.1)
                        try:
                            edit.set_edit_text(str(pdf_path.resolve()))
                        except Exception:
                            send_keys(str(pdf_path.resolve()), with_spaces=True)
                        time.sleep(0.3)
                        if self._verify_filename_typed(window, pdf_path):
                            filename_set = True
                            self.log_msg.emit(f"✅ Wpisano pełną ścieżkę pliku (pole Edit): {pdf_path}")
                        else:
                            self.log_msg.emit(
                                "⚠️ Wpisano tekst, ale nie potwierdzono go w żadnym polu."
                            )
                    except Exception as exc:
                        self.log_msg.emit(f"⚠️ Błąd wpisywania nazwy: {exc}")
            except Exception as exc:
                self.log_msg.emit(f"⚠️ Nie znaleziono pola Edit: {exc}")

        if not filename_set:
            self.log_msg.emit("⚠️ Próba awaryjnego wpisania nazwy pliku...")
            try:
                window.set_focus()
                time.sleep(0.2)
                send_keys("^a{BACKSPACE}")
                send_keys(str(pdf_path.resolve()), with_spaces=True)
                time.sleep(0.3)
            except Exception:
                pass

        time.sleep(0.5)

        # KROK 2: Kliknij przycisk Zapisz/Save
        self.log_msg.emit("🔘 Klikanie przycisku Zapisz/Save...")
        confirmed = self._click_save_button(window, send_keys)

        if not confirmed:
            self.log_msg.emit("⚠️ Kliknięcie nie powiodło się, próbuję Enter...")
            for attempt in range(3):
                try:
                    window.set_focus()
                    time.sleep(0.3)
                    send_keys("{ENTER}")
                    time.sleep(1.5)
                    try:
                        if not window.exists() or not window.is_visible():
                            self.log_msg.emit("✅ Okno zapisu zamknięte Enter")
                            return
                    except Exception:
                        return
                except Exception:
                    pass
                self.log_msg.emit(f"⚠️ Próba {attempt + 1}/3 nie powiodła się")

    def _click_save_button(self, window: Any, send_keys: Any) -> bool:
        from pywinauto.keyboard import send_keys as sk

        # Słowa wykluczające - to nie są przyciski Zapisz
        EXCLUDE_WORDS = [
            "suwak", "scroll", "pasek", "slider", "thumb",
            "minimize", "maximize", "close", "zamknij", "minimalizuj",
            "maksymalizuj", "pomoc", "help", "menu", "minim",
        ]

        try:
            # Szukaj kontroli typu Button
            buttons = [
                ctrl for ctrl in window.descendants(control_type="Button")
                if ctrl.is_visible()
            ]

            for btn in buttons:
                try:
                    btn_text = (btn.window_text() or "").strip()
                    btn_name = ""
                    try:
                        btn_name = str(
                            getattr(getattr(btn, "element_info", None), "name", "") or ""
                        ).strip()
                    except Exception:
                        pass

                    combined = (btn_text + " " + btn_name).lower()

                    # POMIŃ: zawiera słowa wykluczające
                    if any(excl in combined for excl in EXCLUDE_WORDS):
                        continue

                    # POMIŃ: brak tekstu (to nie jest przycisk z etykietą)
                    if not btn_text and not btn_name:
                        continue

                    # SZUKAJ: przycisków Zapisz/Save/Drukuj/Print
                    SAVE_KEYWORDS = [
                        "zapisz", "save", "drukuj", "print",
                        "zapisz jako", "save as", "save pdf",
                        "zapisz plik", "save file",
                    ]

                    if any(kw in combined for kw in SAVE_KEYWORDS):
                        self.log_msg.emit(f"✅ Znaleziono przycisk: '{btn_text or btn_name}'")
                        try:
                            btn.set_focus()
                            time.sleep(0.3)
                            btn.click_input()
                            time.sleep(0.5)
                            try:
                                if not window.exists() or not window.is_visible():
                                    return True
                            except Exception:
                                return True
                        except Exception:
                            try:
                                btn.invoke()
                                time.sleep(0.5)
                                try:
                                    if not window.exists() or not window.is_visible():
                                        return True
                                except Exception:
                                    return True
                            except Exception:
                                continue
                except Exception:
                    continue

            # Jeśli nie znaleziono, spróbuj po automation_id
            self.log_msg.emit("⚠️ Szukam przycisku po automation_id...")
            try:
                for ctrl in window.descendants():
                    try:
                        if not ctrl.is_visible():
                            continue
                        ctrl_type = ""
                        try:
                            ctrl_type = str(getattr(getattr(ctrl, "element_info", None), "control_type", ""))
                        except Exception:
                            pass
                        if ctrl_type not in ("Button", "MenuItem"):
                            continue
                        auto_id = ""
                        try:
                            auto_id = str(getattr(getattr(ctrl, "element_info", None), "automation_id", "") or "")
                        except Exception:
                            pass
                        ctrl_name = ""
                        try:
                            ctrl_name = str(getattr(getattr(ctrl, "element_info", None), "name", "") or "")
                        except Exception:
                            pass
                        combined = (auto_id + " " + ctrl_name).lower()
                        if any(excl in combined for excl in EXCLUDE_WORDS):
                            continue
                        if any(kw in combined for kw in ["zapisz", "save", "print", "drukuj"]):
                            self.log_msg.emit(f"✅ Znaleziono (auto_id): '{ctrl_name}'")
                            ctrl.set_focus()
                            time.sleep(0.3)
                            ctrl.click_input()
                            time.sleep(0.5)
                            try:
                                if not window.exists() or not window.is_visible():
                                    return True
                            except Exception:
                                return True
                    except Exception:
                        continue
            except Exception:
                pass

            # Ostateczność: Enter
            self.log_msg.emit("⚠️ Wysyłam Enter...")
            try:
                window.set_focus()
                time.sleep(0.3)
                sk("{ENTER}")
                time.sleep(1.0)
                try:
                    if not window.exists() or not window.is_visible():
                        return True
                except Exception:
                    return True
            except Exception:
                pass

        except Exception:
            pass

        return False

    def _handle_optional_overwrite_dialog(self, desktop: Any) -> None:
        from pywinauto.keyboard import send_keys

        end_time = time.time() + 12
        while time.time() < end_time:
            for window in desktop.windows():
                try:
                    if not window.is_visible():
                        continue
                    title = (window.window_text() or "").strip()
                    if not title:
                        continue
                    if re.search(
                        r"potwierd|confirm|zamień|replace|already exists|już istnieje",
                        title, re.IGNORECASE,
                    ):
                        try:
                            window.set_focus()
                        except Exception:
                            pass
                        try:
                            buttons = [
                                ctrl for ctrl in window.descendants(control_type="Button")
                                if ctrl.is_visible()
                            ]
                            for btn in buttons:
                                btn_title = (btn.window_text() or "").strip()
                                if re.search(
                                    r"tak|yes|save|zapisz|replace|zamień|ok",
                                    btn_title, re.IGNORECASE,
                                ):
                                    btn.click_input()
                                    time.sleep(0.6)
                                    return
                        except Exception:
                            pass
                        for keys in ("%t", "%y", "%s", "{ENTER}"):
                            try:
                                send_keys(keys)
                                time.sleep(0.6)
                                return
                            except Exception:
                                continue
                except Exception:
                    continue
            time.sleep(0.3)


# -----------------------------------------------------------------------------
# Widget
# -----------------------------------------------------------------------------

class KWDownloaderWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.owners: list[dict[str, Any]] = []
        self.kw_list: list[dict[str, Any]] = []
        self.manual_kws: set[str] = set()
        self.project_path = ""
        self._checked_kws: set[str] = set()
        self._worker: Optional[KWDownloadWorker] = None
        self.setAcceptDrops(True)
        self._build_ui()
        self.log_to_console("System gotowy. Wybierz projekt, a wczytam księgi wieczyste.")
        self.log_to_console(f"Logi techniczne: {LOG_FILE}")

    def log_to_console(self, text: str) -> None:
        self.console.append(text)
        logger.info(text)

    def set_owners(self, owners: list) -> None:
        self.owners = owners or []
        self._extract_kws()

    def set_project(self, project: dict) -> None:
        self.project_path = (project or {}).get("path", "")
        self._load_state()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if Path(path).suffix.lower() in ('.txt', '.docx'):
                    self._import_kw_file(path)
                    break

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ---- Header ----
        header = QHBoxLayout()
        title = QLabel("📚 Pobieranie Ksiąg Wieczystych")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        header.addWidget(title)
        header.addStretch()

        btn_logs = QPushButton("📋 Otwórz logi")
        btn_logs.clicked.connect(self._open_log_folder)
        header.addWidget(btn_logs)

        btn_output = QPushButton("📂 Otwórz folder PDF")
        btn_output.clicked.connect(self._open_output_folder)
        header.addWidget(btn_output)

        btn_select_all = QPushButton("☑ Zaznacz wszystkie")
        btn_select_all.clicked.connect(lambda: self._set_all_checked(True))
        header.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("☐ Odznacz wszystkie")
        btn_deselect_all.clicked.connect(lambda: self._set_all_checked(False))
        header.addWidget(btn_deselect_all)

        btn_open_eukw = QPushButton("🌐 Otwórz stronę EUKW")
        btn_open_eukw.setToolTip(
            "Otwiera stronę „EUKW - Prezentacja Księgi Wieczystej” "
            "w domyślnej przeglądarce."
        )
        btn_open_eukw.clicked.connect(self._open_eukw_website)
        header.addWidget(btn_open_eukw)

        btn_prompt_kw = QPushButton("➕ Wpisz KW")
        btn_prompt_kw.setToolTip("Wklej ręcznie listę KW – spacje, przecinki i entery są obsługiwane")
        btn_prompt_kw.clicked.connect(self._prompt_manual_kw)
        header.addWidget(btn_prompt_kw)

        btn_import_kw_top = QPushButton("📥 Import KW TXT/DOCX")
        btn_import_kw_top.clicked.connect(self._import_kw_file)
        header.addWidget(btn_import_kw_top)

        main_layout.addLayout(header)

        # ---- Ustawienia ----
        settings_widget = QWidget()
        settings_layout = QHBoxLayout(settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(4)

        group_sections = QGroupBox("Działy PDF")
        sec_layout = QHBoxLayout(group_sections)
        self.chk_d1o = QCheckBox("Dział I-O")
        self.chk_d1s = QCheckBox("Dział I-Sp")
        self.chk_d2 = QCheckBox("Dział II")
        self.chk_d3 = QCheckBox("Dział III")
        self.chk_d4 = QCheckBox("Dział IV")
        for checkbox in (self.chk_d1o, self.chk_d1s, self.chk_d2, self.chk_d3, self.chk_d4):
            sec_layout.addWidget(checkbox)
        settings_layout.addWidget(group_sections)

        group_delay = QGroupBox("Odstęp")
        delay_layout = QHBoxLayout(group_delay)
        delay_layout.addWidget(QLabel("Czas:"))
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(0, 60)
        self.spin_delay.setValue(int(self.config.get("kw_delay_sec", 3)))
        self.spin_delay.setSuffix(" sek.")
        self.spin_delay.valueChanged.connect(self._on_delay_changed)
        delay_layout.addWidget(self.spin_delay)
        settings_layout.addWidget(group_delay)

        group_speed = QGroupBox("Tempo / przeglądarka")
        speed_layout = QVBoxLayout(group_speed)
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Tempo:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItem("Szybka", "fast")
        self.speed_combo.addItem("Normalna", "normal")
        self.speed_combo.addItem("Wolna / stabilna", "slow")
        initial_speed = str(self.config.get("kw_speed", "normal"))
        speed_index = self.speed_combo.findData(
            initial_speed if initial_speed in KW_SPEED_SETTINGS else "normal"
        )
        self.speed_combo.setCurrentIndex(max(0, speed_index))
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_combo)
        speed_row.addWidget(QLabel("Przeglądarka:"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItem("Domyślna z programu", "auto")
        self.browser_combo.addItem("Chrome", "chrome")
        self.browser_combo.addItem("Edge", "msedge")
        self.browser_combo.addItem("Opera", "opera")
        self.browser_combo.addItem("Firefox (zainstalowany)", "firefox")
        browser_index = self.browser_combo.findData(str(self.config.get("kw_browser", self.config.get("default_browser", "auto"))))
        self.browser_combo.setCurrentIndex(max(0, browser_index))
        self.browser_combo.currentIndexChanged.connect(self._on_browser_changed)
        speed_row.addWidget(self.browser_combo)
        speed_layout.addLayout(speed_row)

        self.firefox_path_widget = QWidget()
        firefox_path_layout = QHBoxLayout(self.firefox_path_widget)
        firefox_path_layout.setContentsMargins(0, 0, 0, 0)
        firefox_path_layout.addWidget(QLabel("Firefox.exe:"))
        self.firefox_path_edit = QLineEdit(
            str(self.config.get("kw_firefox_executable", ""))
        )
        self.firefox_path_edit.setPlaceholderText(
            "Automatycznie wykryj zainstalowany Firefox"
        )
        self.firefox_path_edit.editingFinished.connect(
            self._on_firefox_path_changed
        )
        firefox_path_layout.addWidget(self.firefox_path_edit, 1)
        btn_browse_firefox = QPushButton("📂")
        btn_browse_firefox.setToolTip("Wskaż zwykły plik firefox.exe")
        btn_browse_firefox.clicked.connect(self._browse_firefox_executable)
        firefox_path_layout.addWidget(btn_browse_firefox)
        speed_layout.addWidget(self.firefox_path_widget)
        self._update_firefox_path_visibility()
        settings_layout.addWidget(group_speed)

        group_printer = QGroupBox("PDF / tło")
        printer_layout = QHBoxLayout(group_printer)
        self.printer_combo = QComboBox()
        self.printer_combo.addItem("Adobe PDF", "Adobe PDF")
        self.printer_combo.addItem("Microsoft Print to PDF", "Microsoft Print to PDF")
        self.printer_combo.addItem("Zapisz jako PDF (przeglądarka)", "Save as PDF")
        initial_printer = str(self.config.get("kw_pdf_printer", "Microsoft Print to PDF"))
        printer_index = self.printer_combo.findData(initial_printer)
        self.printer_combo.setCurrentIndex(max(0, printer_index))
        self.printer_combo.currentIndexChanged.connect(self._on_printer_changed)
        printer_layout.addWidget(self.printer_combo)

        self.chk_direct_save = QCheckBox(
            "⚡ Zapisuj bezpośrednio jako PDF (pomiń okno drukowania Adobe/Microsoft)"
        )
        self.chk_direct_save.setToolTip(
            "Gdy zaznaczone: program zapisuje PDF od razu przez Chrome, Edge\n"
            "lub Operę — bez okna drukowania Adobe/Microsoft. To najbardziej\n"
            "niezawodna opcja. Firefox wymaga Microsoft Print to PDF lub Adobe PDF."
        )
        self.chk_direct_save.setChecked(bool(self.config.get("kw_direct_save", False)))
        self.chk_direct_save.toggled.connect(self._on_direct_save_toggled)
        printer_layout.addWidget(self.chk_direct_save)
        self.printer_combo.setEnabled(not self.chk_direct_save.isChecked())

        printer_layout.addWidget(QLabel("Motyw tylko przy zapisie bezpośrednim:"))
        self.direct_pdf_style_combo = QComboBox()
        self.direct_pdf_style_combo.setToolTip("Ten wybór działa WYŁĄCZNIE, gdy zaznaczone jest: Zapisuj bezpośrednio jako PDF. Przy normalnym drukowaniu nie zmienia wyglądu.")
        self.direct_pdf_style_combo.addItem("Zapisz jako PDF", "zapisz")
        self.direct_pdf_style_combo.addItem("Microsoft Print to PDF", "microsoft")
        self.direct_pdf_style_combo.addItem("Adobe PDF", "adobe")
        style_idx = self.direct_pdf_style_combo.findData(self.config.get("kw_direct_pdf_style", "zapisz"))
        self.direct_pdf_style_combo.setCurrentIndex(max(0, style_idx))
        self.direct_pdf_style_combo.currentIndexChanged.connect(self._on_direct_pdf_style_changed)
        self.direct_pdf_style_combo.setEnabled(self.chk_direct_save.isChecked())
        printer_layout.addWidget(self.direct_pdf_style_combo)

        self.chk_header_footer = QCheckBox(
            "📝 Pokaż nagłówek (data, godzina, adres URL) i stopkę"
        )
        self.chk_header_footer.setChecked(bool(self.config.get("kw_header_footer", False)))
        self.chk_header_footer.toggled.connect(self._on_header_footer_toggled)
        printer_layout.addWidget(self.chk_header_footer)


        self.chk_black_white = QCheckBox("⬛ Zapisuj czarno-białe (bez kolorów)")
        self.chk_black_white.setChecked(bool(self.config.get("kw_black_white", False)))
        self.chk_black_white.toggled.connect(self._on_black_white_toggled)
        printer_layout.addWidget(self.chk_black_white)

        self.chk_background_mode = QCheckBox("🔽 Praca w tle (zminimalizuj okno przeglądarki)")
        self.chk_background_mode.setToolTip(
            "Po otwarciu formularza KW okno przeglądarki zostanie\n"
            "automatycznie zminimalizowane, żeby nie przeszkadzało\n"
            "w innej pracy na komputerze."
        )
        self.chk_background_mode.setChecked(bool(self.config.get("kw_background_mode", False)))
        self.chk_background_mode.toggled.connect(self._on_background_mode_toggled)
        printer_layout.addWidget(self.chk_background_mode)

        settings_layout.addWidget(group_printer)
        main_layout.addWidget(settings_widget)

        manual_box = QGroupBox('Ręczne dodanie KW / import listy')
        manual_layout = QVBoxLayout(manual_box)
        self.manual_kw_edit = QTextEdit()
        self.manual_kw_edit.setMaximumHeight(70)
        self.manual_kw_edit.setPlaceholderText('Wklej numery KW – spacje, przecinki i entery są obsługiwane')
        manual_layout.addWidget(self.manual_kw_edit)
        manual_btns = QHBoxLayout()
        btn_add_manual_kw = QPushButton('➕ Dodaj wpisane KW')
        btn_add_manual_kw.clicked.connect(self._add_manual_kws_from_text)
        manual_btns.addWidget(btn_add_manual_kw)
        btn_import_kw = QPushButton('📥 Import TXT/DOCX')
        btn_import_kw.clicked.connect(lambda: self._import_kw_file())
        manual_btns.addWidget(btn_import_kw)
        hint = QLabel('Możesz też przeciągnąć plik TXT/DOCX na okno modułu KW.')
        hint.setStyleSheet('color: gray; font-size: 11px;')
        manual_btns.addWidget(hint)
        manual_btns.addStretch()
        manual_layout.addLayout(manual_btns)
        main_layout.addWidget(manual_box)

        # ---- Tabela ksiąg ----
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Zaznacz", "Nr Księgi Wieczystej", "Powiązane działki", "Status"]
        )
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        if not self.config.get('table_state_kw_downloader'):
            self.table.setColumnWidth(0, 80)
            self.table.setColumnWidth(1, 190)
            self.table.setColumnWidth(2, 260)
            self.table.setColumnWidth(3, 180)
        else:
            from PySide6.QtCore import QByteArray
            header.restoreState(QByteArray.fromHex(self.config.get('table_state_kw_downloader', '').encode()))
        header.sectionResized.connect(lambda *args: self.config.update({'table_state_kw_downloader': header.saveState().toHex().data().decode()}))
        header.sectionMoved.connect(lambda *args: self.config.update({'table_state_kw_downloader': header.saveState().toHex().data().decode()}))
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table)

        # ---- Przyciski akcji ----
        actions = QHBoxLayout()

        self.btn_start = QPushButton("📥 URUCHOM POBIERANIE ZAZNACZONYCH KSIĄG")
        self.btn_start.setObjectName("btn_primary")
        self.btn_start.setMinimumHeight(44)
        self.btn_start.clicked.connect(self._start_download)
        actions.addWidget(self.btn_start, 1)

        self.btn_stop = QPushButton("⛔ Przerwij pobieranie")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_download)
        actions.addWidget(self.btn_stop)

        self.btn_stop_module = QPushButton("⛔ ZATRZYMAJ MODUŁ")
        self.btn_stop_module.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: bold; padding: 8px 16px;"
        )
        self.btn_stop_module.clicked.connect(self._stop_module)
        actions.addWidget(self.btn_stop_module)

        main_layout.addLayout(actions)

        # ---- Konsola ----
        console_group = QGroupBox("📝 Diagnostyka na żywo")
        console_layout = QVBoxLayout(console_group)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(190)
        self.console.setStyleSheet(
            "background-color: #000; color: #0f0; font-family: Consolas, monospace;"
        )
        console_layout.addWidget(self.console)
        main_layout.addWidget(console_group)

    def _open_eukw_website(self) -> None:
        url = (
            "https://przegladarka-ekw.ms.gov.pl/eukw_prz/KsiegiWieczyste/wyszukiwanieKW"
            "?komunikaty=true&kontakt=true&okienkoSerwisowe=false"
        )
        QDesktopServices.openUrl(QUrl(url))
        self.log_to_console("🌐 Otwieram stronę EUKW – Prezentacja Księgi Wieczystej.")

    # ---------- Handlery ----------

    def _on_browser_changed(self, *_args) -> None:
        """Zapisuje wybór przeglądarki w konfiguracji."""
        mode = self._get_browser_mode()
        self.config["kw_browser"] = mode
        self._update_firefox_path_visibility()
        labels = {
            "auto": "Domyślna z programu",
            "chrome": "Chrome",
            "msedge": "Edge",
            "opera": "Opera",
            "firefox": "Firefox (zainstalowany)",
        }
        if hasattr(self, "log_to_console"):
            self.log_to_console(f"🌐 Ustawiono przeglądarkę KW: {labels.get(mode, mode)}")
            if mode == "firefox" and self._get_printer_name() == "Save as PDF":
                self.log_to_console(
                    "⚠️ Firefox nie obsługuje bezpośredniego zapisu PDF. "
                    "Wybierz Microsoft Print to PDF lub Adobe PDF."
                )

    def _update_firefox_path_visibility(self) -> None:
        widget = getattr(self, "firefox_path_widget", None)
        if widget is not None:
            widget.setVisible(self._get_browser_mode() == "firefox")

    def _on_firefox_path_changed(self) -> None:
        if hasattr(self, "firefox_path_edit"):
            self.config["kw_firefox_executable"] = (
                self.firefox_path_edit.text().strip()
            )

    def _browse_firefox_executable(self) -> None:
        start_path = ""
        if hasattr(self, "firefox_path_edit"):
            start_path = self.firefox_path_edit.text().strip()
        if start_path and Path(start_path).is_file():
            start_path = str(Path(start_path).parent)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wskaż zainstalowany Firefox",
            start_path,
            "Firefox (firefox.exe);;Pliki wykonywalne (*.exe);;Wszystkie pliki (*.*)",
        )
        if path and hasattr(self, "firefox_path_edit"):
            self.firefox_path_edit.setText(path)
            self._on_firefox_path_changed()

    def _get_browser_mode(self) -> str:
        combo = getattr(self, "browser_combo", None)
        if combo is None:
            mode = str(self.config.get("kw_browser", self.config.get("default_browser", "auto")))
        else:
            mode = str(combo.currentData() or "auto")
        return mode if mode in ("auto", "chrome", "msedge", "opera", "firefox") else "auto"

    def _get_browser_executable_path(self) -> str:
        if hasattr(self, "firefox_path_edit"):
            return self.firefox_path_edit.text().strip()
        return str(self.config.get("kw_firefox_executable", "") or "").strip()

    def _on_speed_changed(self, *_args) -> None:
        speed_mode = self._get_speed_mode()
        self.config["kw_speed"] = speed_mode
        label = KW_SPEED_SETTINGS.get(speed_mode, KW_SPEED_SETTINGS["normal"])["label"]
        self.log_to_console(f"⚙️ Ustawiono tempo pracy: {label}")

    def _on_delay_changed(self, value: int) -> None:
        self.config["kw_delay_sec"] = int(value)

    def _on_printer_changed(self, *_args) -> None:
        self.config["kw_pdf_printer"] = self._get_printer_name()
        self.log_to_console(f"🖨️ Ustawiono drukarkę PDF: {self._get_printer_name()}")

    def _on_direct_pdf_style_changed(self, *_args) -> None:
        self.config["kw_direct_pdf_style"] = self._get_direct_pdf_style()
        if hasattr(self, "direct_pdf_style_combo"):
            self.log_to_console(f"🎨 Motyw bezpośredniego PDF: {self.direct_pdf_style_combo.currentText()}")

    def _on_direct_save_toggled(self, checked: bool) -> None:
        self.config["kw_direct_save"] = bool(checked)
        if hasattr(self, "printer_combo"):
            self.printer_combo.setEnabled(not checked)
        if hasattr(self, "direct_pdf_style_combo"):
            self.direct_pdf_style_combo.setEnabled(checked)
        if checked:
            self.log_to_console(
                "⚡ Włączono bezpośredni zapis PDF – pomijam okno drukowania "
                "Adobe/Microsoft Print to PDF."
            )
        else:
            self.log_to_console("⚡ Wyłączono bezpośredni zapis PDF – używam okna drukowania.")

    def _on_header_footer_toggled(self, checked: bool) -> None:
        self.config["kw_header_footer"] = bool(checked)
        if checked:
            self.log_to_console("📝 Włączono nagłówek/stopkę: data, godzina i adres URL")
        else:
            self.log_to_console("📝 Wyłączono nagłówek/stopkę")

    def _on_black_white_toggled(self, checked: bool) -> None:
        self.config["kw_black_white"] = bool(checked)
        if checked:
            self.log_to_console("⬛ Włączono zapis czarno-biały (bez kolorów)")
        else:
            self.log_to_console("⬛ Wyłączono zapis czarno-biały – wydruk kolorowy")

    def _on_background_mode_toggled(self, checked: bool) -> None:
        self.config["kw_background_mode"] = bool(checked)
        if checked:
            self.log_to_console("🔽 Włączono pracę w tle – okno przeglądarki będzie minimalizowane")
        else:
            self.log_to_console("🔽 Wyłączono pracę w tle")

    def _get_speed_mode(self) -> str:
        mode = self.speed_combo.currentData()
        return mode if mode in KW_SPEED_SETTINGS else "normal"

    def _get_printer_name(self) -> str:
        if hasattr(self, "chk_direct_save") and self.chk_direct_save.isChecked():
            return "Save as PDF"
        printer = self.printer_combo.currentData() if hasattr(self, "printer_combo") else None
        return str(printer or "Microsoft Print to PDF")

    def _get_direct_pdf_style(self) -> str:
        combo = getattr(self, "direct_pdf_style_combo", None)
        style = combo.currentData() if combo is not None else self.config.get("kw_direct_pdf_style", "zapisz")
        return style if style in ("zapisz", "microsoft", "adobe") else "zapisz"

    def _get_header_footer(self) -> bool:
        return bool(self.chk_header_footer.isChecked())

    def _get_header_style(self) -> str:
        return "p1"

    def _get_black_white(self) -> bool:
        return bool(self.chk_black_white.isChecked()) if hasattr(self, "chk_black_white") else False

    def _get_background_mode(self) -> bool:
        return (
            bool(self.chk_background_mode.isChecked())
            if hasattr(self, "chk_background_mode")
            else False
        )

    def _parse_kw_text(self, text: str) -> list[str]:
        """Rozbudowany odczyt KW z dowolnego tekstu.

        Obsługuje m.in.:
        GW1W/0011953/1
        GD1W/00142953 /2
        GD1W/001429933/ 3
        GD1W / 00142953 / 5
        GD1W 00142953 5
        """
        raw = str(text or '').upper()
        # ujednolicenie separatorów i niewidocznych spacji
        raw = raw.replace('\u00a0', ' ').replace('\t', ' ')
        found = []

        patterns = [
            # klasyczny zapis z ukośnikami i dowolnymi spacjami
            r'\b([A-Z0-9]{4})\s*/\s*([0-9]{1,8})\s*/\s*([0-9])\b',
            # zapis ze spacjami zamiast ukośników
            r'\b([A-Z0-9]{4})\s+([0-9]{1,8})\s+([0-9])\b',
            # zapis z myślnikami/kropkami jako separatorami
            r'\b([A-Z0-9]{4})\s*[-.]\s*([0-9]{1,8})\s*[-.]\s*([0-9])\b',
        ]
        for pat in patterns:
            for m in re.finditer(pat, raw):
                kw = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
                kw = normalize_kw(kw)
                if KW_RE.fullmatch(kw):
                    found.append(kw)

        # Dodatkowa próba: usuń spacje przy slashach i szukaj po normalizacji.
        compact = re.sub(r'\s*/\s*', '/', raw)
        for m in re.finditer(r'\b[A-Z0-9]{4}/[0-9]{1,8}/[0-9]\b', compact):
            kw = normalize_kw(m.group(0))
            if KW_RE.fullmatch(kw):
                found.append(kw)

        seen = set()
        return [x for x in found if not (x in seen or seen.add(x))]


    def _prompt_manual_kw(self):
        text, ok = QInputDialog.getMultiLineText(
            self,
            'Wpisz / wklej listę KW',
            'Numery KW:',
            ''
        )
        if ok and text.strip():
            self._add_manual_kws_from_text(text)

    def _add_manual_kws_from_text(self, text: str = ''):
        if not text and hasattr(self, 'manual_kw_edit'):
            text = self.manual_kw_edit.toPlainText()
        kws = self._parse_kw_text(text)
        if not kws:
            QMessageBox.warning(self, 'Brak KW', 'Nie znaleziono poprawnych numerów KW.')
            return
        existing = {item['kw'] for item in self.kw_list}
        added = 0
        for kw in kws:
            if kw not in existing:
                self.kw_list.append({'kw': kw, 'dzialki': [], 'status': 'Oczekuje'})
                self.manual_kws.add(kw)
                self._checked_kws.add(kw)
                existing.add(kw)
                added += 1
        self._refresh_table()
        QMessageBox.information(self, 'Dodano KW', f'Dodano nowych KW: {added}')

    def _import_kw_file(self, path: str = ''):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, 'Import listy KW', '', 'Pliki (*.txt *.docx);;TXT (*.txt);;Word (*.docx)')
        if not path:
            return
        ext = Path(path).suffix.lower()
        try:
            if ext == '.docx':
                import docx as python_docx
                text = '\n'.join(p.text for p in python_docx.Document(path).paragraphs)
            else:
                try:
                    text = Path(path).read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    text = Path(path).read_text(encoding='cp1250')
        except Exception as e:
            QMessageBox.critical(self, 'Błąd', f'Nie udało się odczytać pliku:\n{e}')
            return
        if hasattr(self, 'manual_kw_edit'):
            self.manual_kw_edit.setPlainText(text)
        self._add_manual_kws_from_text(text)

    def _extract_kws(self) -> None:
        kw_dict: dict[str, dict[str, Any]] = {}
        for owner in self.owners:
            for parcel in owner.get("parcels", []):
                if not isinstance(parcel, dict):
                    continue
                kw = normalize_kw(parcel.get("kw", ""))
                number = str(parcel.get("number", "") or "").strip()
                if not KW_RE.fullmatch(kw):
                    continue
                if kw not in kw_dict:
                    kw_dict[kw] = {"dzialki": set(), "status": "Oczekuje"}
                if number:
                    kw_dict[kw]["dzialki"].add(number)

        for kw in self.manual_kws:
            if kw not in kw_dict:
                kw_dict[kw] = {"dzialki": set(), "status": "Oczekuje"}

        old_status = {item["kw"]: item["status"] for item in self.kw_list}
        self.kw_list = []
        for kw, data in kw_dict.items():
            self.kw_list.append(
                {
                    "kw": kw,
                    "dzialki": sorted(data["dzialki"]),
                    "status": old_status.get(kw, "Oczekuje"),
                }
            )

        self._checked_kws.intersection_update({item["kw"] for item in self.kw_list})
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        for row, item in enumerate(self.kw_list):
            self.table.insertRow(row)

            checkbox = QCheckBox()
            checkbox.setChecked(item["kw"] in self._checked_kws)
            checkbox.stateChanged.connect(
                lambda state, kw=item["kw"]: self._remember_check(kw, state)
            )
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, checkbox_widget)

            self.table.setItem(row, 1, QTableWidgetItem(item["kw"]))
            self.table.setItem(row, 2, QTableWidgetItem(", ".join(item["dzialki"])))

            status_item = QTableWidgetItem(item["status"])
            if item["status"] == "Pobrano PDF":
                status_item.setForeground(QColor("#2ecc71"))
                status_item.setFont(QFont("", -1, QFont.Weight.Bold))
            elif item["status"] == "Oczekuje":
                status_item.setForeground(QColor("#f1c40f"))
            elif item["status"] == "W trakcie":
                status_item.setForeground(QColor("#3498db"))
            elif item["status"] == "Przerwano":
                status_item.setForeground(QColor("#95a5a6"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self.table.setItem(row, 3, status_item)

    def _remember_check(self, kw: str, checked: int) -> None:
        if checked:
            self._checked_kws.add(kw)
        else:
            self._checked_kws.discard(kw)

    def _set_all_checked(self, state: bool) -> None:
        if state:
            self._checked_kws = {item["kw"] for item in self.kw_list}
        else:
            self._checked_kws.clear()
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            checkbox = widget.findChild(QCheckBox) if widget else None
            if checkbox:
                checkbox.blockSignals(True)
                checkbox.setChecked(state)
                checkbox.blockSignals(False)

    def _selected_sections(self) -> list[str]:
        sections: list[str] = []
        if self.chk_d1o.isChecked():
            sections.append("Dział I-O")
        if self.chk_d1s.isChecked():
            sections.append("Dział I-Sp")
        if self.chk_d2.isChecked():
            sections.append("Dział II")
        if self.chk_d3.isChecked():
            sections.append("Dział III")
        if self.chk_d4.isChecked():
            sections.append("Dział IV")
        return sections

    def _output_dir(self) -> Optional[Path]:
        output_root = self.project_path or self.config.get("last_project_path", "")
        if not output_root:
            return None
        return Path(output_root) / "ksiegi_wieczyste_pdf"

    def _open_log_folder(self) -> None:
        open_in_file_manager(LOG_DIR)

    def _open_output_folder(self) -> None:
        output_dir = self._output_dir()
        if output_dir is None:
            QMessageBox.warning(self, "Brak projektu", "Najpierw wybierz aktywny projekt.")
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        open_in_file_manager(output_dir)

    def _start_download(self) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "Pobieranie w toku", "Aktualne pobieranie jeszcze trwa.")
            return

        to_download = [
            item["kw"] for item in self.kw_list if item["kw"] in self._checked_kws
        ]
        if not to_download:
            QMessageBox.warning(self, "Brak zaznaczenia", "Zaznacz co najmniej jedną księgę na liście.")
            return

        sections = self._selected_sections()
        if not sections:
            QMessageBox.warning(self, "Brak działów", "Zaznacz przynajmniej jeden dział do pobrania.")
            return

        if (
            self._get_browser_mode() == "firefox"
            and self._get_printer_name() == "Save as PDF"
        ):
            QMessageBox.warning(
                self,
                "Firefox i zapis PDF",
                "Firefox nie udostępnia bezpośredniego zapisu PDF używanego "
                "przez program. Dla Firefox wybierz Microsoft Print to PDF "
                "lub Adobe PDF i wyłącz opcję bezpośredniego zapisu.",
            )
            return

        output_dir = self._output_dir()
        if output_dir is None:
            QMessageBox.warning(self, "Błąd", "Nie wybrano aktywnego projektu.")
            return

        output_dir.mkdir(parents=True, exist_ok=True)

        self.log_to_console("=== START pobierania KW ===")
        self.log_to_console(f"📚 Liczba ksiąg: {len(to_download)}")
        self.log_to_console(f"📄 Działy: {', '.join(sections)}")
        self.log_to_console(f"⏱️ Odstęp między księgami: {self.spin_delay.value()} s")
        self.log_to_console(f"⚙️ Tempo: {KW_SPEED_SETTINGS[self._get_speed_mode()]['label']}")
        self.log_to_console(f"🖨️ Drukarka PDF: {self._get_printer_name()}")
        self.log_to_console(f"📝 Nagłówek/stopka: {'WŁĄCZONE' if self._get_header_footer() else 'WYŁĄCZONE'}")
        self.log_to_console(f"📁 Folder docelowy: {output_dir}")

        for item in self.kw_list:
            if item["kw"] in to_download:
                item["status"] = "W trakcie"
        self._refresh_table()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        # Przygotuj kolejkę z numerami działek
        kw_queue_with_parcels = []
        for kw in to_download:
            parcels = []
            for item in self.kw_list:
                if item["kw"] == kw:
                    parcels = item.get("dzialki", [])
                    break
            kw_queue_with_parcels.append((kw, parcels))

        self._worker = KWDownloadWorker(
            kw_queue=kw_queue_with_parcels,
            sections=sections,
            output_dir=output_dir,
            delay_sec=self.spin_delay.value(),
            speed_mode=self._get_speed_mode(),
            pdf_printer_name=self._get_printer_name(),
            direct_save_enabled=bool(self.chk_direct_save.isChecked()) if hasattr(self, "chk_direct_save") else False,
            header_footer_enabled=self._get_header_footer(),
            direct_pdf_style=self._get_direct_pdf_style(),
            header_style=self._get_header_style(),
            black_white_enabled=self._get_black_white(),
            background_mode_enabled=self._get_background_mode(),
            browser_mode=self._get_browser_mode(),
            browser_executable_path=self._get_browser_executable_path(),
        )
        self._worker.log_msg.connect(self.log_to_console)
        self._worker.row_status.connect(self._on_row_status)
        self._worker.item_finished.connect(self._on_item_finished)
        self._worker.finished_queue.connect(self._on_queue_finished)
        self._worker.finished_queue.connect(self._worker.deleteLater)
        self._worker.start()

    def _stop_download(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self.log_to_console("⛔ Wysłano żądanie przerwania pobierania.")
            self.btn_stop.setEnabled(False)

    def _stop_module(self) -> None:
        """Zatrzymuje moduł KW, nie zamyka całego programu."""
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(5000)
            self._worker = None

        for item in self.kw_list:
            if item["status"] == "W trakcie":
                item["status"] = "Przerwano"

        self._refresh_table()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_to_console("⛔ Moduł pobierania KW został zatrzymany.")

    def _on_row_status(self, kw: str, _text: str) -> None:
        for item in self.kw_list:
            if item["kw"] == kw:
                item["status"] = "W trakcie"
                break
        self._refresh_table()

    def _on_item_finished(self, kw: str, success: bool, status: str) -> None:
        for item in self.kw_list:
            if item["kw"] == kw:
                item["status"] = status
                break
        if success and status == "Pobrano PDF":
            self._checked_kws.discard(kw)
        self._refresh_table()
        self._save_state()

    def _on_queue_finished(self) -> None:
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._save_state()
        self.log_to_console("=== KONIEC pobierania KW ===")
        self._worker = None

    def _state_file(self) -> Optional[Path]:
        if not self.project_path:
            return None
        return Path(self.project_path) / "kw_download_state.json"

    def _save_state(self) -> None:
        state_file = self._state_file()
        if state_file is None:
            return
        success_kws = [item["kw"] for item in self.kw_list if item["status"] == "Pobrano PDF"]
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            with state_file.open("w", encoding="utf-8") as fh:
                json.dump({"pobrane": success_kws, "manual_kws": sorted(self.manual_kws)}, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            self.log_to_console(f"⚠️ Nie udało się zapisać stanu KW: {exc}")

    def _load_state(self) -> None:
        state_file = self._state_file()
        if state_file is None or not state_file.exists():
            self._refresh_table()
            return
        try:
            with state_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.manual_kws = set(data.get("manual_kws", []))
            # dołącz ręczne KW zapisane w projekcie
            existing = {item["kw"] for item in self.kw_list}
            for kw in sorted(self.manual_kws):
                if kw not in existing and KW_RE.fullmatch(kw):
                    self.kw_list.append({"kw": kw, "dzialki": [], "status": "Oczekuje"})
                    existing.add(kw)
            downloaded = set(data.get("pobrane", []))
            for item in self.kw_list:
                if item["kw"] in downloaded:
                    item["status"] = "Pobrano PDF"
                    self._checked_kws.discard(item["kw"])
            self._refresh_table()
        except (OSError, ValueError, TypeError) as exc:
            self.log_to_console(f"⚠️ Nie udało się odczytać stanu KW: {exc}")
            self._refresh_table()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(5000)
        super().closeEvent(event)