"""Sekcja „Wypisy” w Ustawieniach — odczyt danych z dokumentu PDF.

Cały ten fragment ustawień mieszkał wcześniej w ``modules/ustawienia.py``,
razem z kilkunastoma innymi sekcjami. Tutaj jest osobno, dzięki czemu:

* zmiany w odczycie wypisów nie wymagają grzebania w pliku, który obsługuje
  wszystkie pozostałe ustawienia programu,
* widać w jednym miejscu komplet: pola na ekranie, ich odczyt z konfiguracji
  i zapis z powrotem,
* okno „Wzory odczytu wypisów (PDF)” ma tu jedyne miejsce podpięcia.

Sekcja jest zwykłym ``QGroupBox``, więc Ustawienia dodają ją do układu tak
samo jak wcześniej — jedną linijką.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from utils.wypis_fields import (
    DEFAULT_MUNICIPALITY_MODE,
    MUNICIPALITY_MODE_CHOICES,
    MUNICIPALITY_MODE_KEY,
)

#: Klucze konfiguracji obsługiwane przez tę sekcję.
FIX_IDENTIFIER_KEY = "wypis_fix_identifier"
READ_OWNERSHIP_KEY = "wypis_read_ownership"

#: Wartości domyślne — używane, gdy konfiguracja jeszcze ich nie zawiera.
DEFAULTS: dict[str, Any] = {
    MUNICIPALITY_MODE_KEY: DEFAULT_MUNICIPALITY_MODE,
    FIX_IDENTIFIER_KEY: True,
    READ_OWNERSHIP_KEY: True,
}


class WypisSettingsSection(QGroupBox):
    """Ramka „Wypisy — odczyt danych z dokumentu”.

    Sekcja sama buduje swoje pola, sama wczytuje je z konfiguracji
    (:meth:`load_from_config`) i sama je zapisuje (:meth:`save_to_config`).
    Zakładka Ustawienia nie musi znać żadnego z tych kluczy.
    """

    def __init__(self, parent=None):
        super().__init__("Wypisy — odczyt danych z dokumentu", parent)
        self._build_ui()

    # ── Budowa ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "Jednostka ewidencyjna bywa zapisana jako „Maki - G” (gmina) albo "
            "„Maki - M” (miasto). Tutaj wybierasz, w jakiej postaci program ma "
            "zapisywać tę wartość."
        )
        info.setObjectName("naming_hint")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.municipality_mode = QComboBox()
        for label, value in MUNICIPALITY_MODE_CHOICES:
            self.municipality_mode.addItem(label, value)
        form.addRow("Jednostka ewidencyjna:", self.municipality_mode)
        layout.addLayout(form)

        self.chk_fix_identifier = QCheckBox(
            "Poprawiaj zapis identyfikatora działki "
            "(110101 2 0010 202 → 110101_2.0010.202)"
        )
        self.chk_fix_identifier.setToolTip(
            "Numer działki rozdzielony spacjami zostanie zapisany z ukośnikiem, "
            "np. 110101 2 0010 22 21 → 110101_2.0010.22/21."
        )
        layout.addWidget(self.chk_fix_identifier)

        self.chk_read_ownership = QCheckBox(
            "Odczytuj „Formę władania” i udział z wypisu (kolumna w tabeli)"
        )
        self.chk_read_ownership.setToolTip(
            "Np. „14/48 współwłasność”, „wspólność ustawowa”, „udział łączny”."
        )
        layout.addWidget(self.chk_read_ownership)

        layout.addWidget(self._build_profiles_row())

    def _build_profiles_row(self) -> QGroupBox:
        """Podsekcja z wejściem do okna wzorów odczytu PDF."""
        box = QGroupBox("Wzory odczytu wypisów (PDF)")
        layout = QVBoxLayout(box)

        hint = QLabel(
            "Wypisy z różnych urzędów mają inne nazwy pól — jeden pisze "
            "„Bliższe określenie położenia”, inny „Adres nieruchomości”. "
            "W oknie poniżej wczytasz przykładowy PDF, zobaczysz co program "
            "z niego odczytał i poprawisz przypisania. Ustawienia zapiszą się "
            "jako wzór dla kolejnych dokumentów z tego samego urzędu."
        )
        hint.setObjectName("muted_hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.btn_profiles = QPushButton("🧩 Wzory odczytu wypisów (PDF)…")
        self.btn_profiles.setObjectName("btn_primary")
        self.btn_profiles.setToolTip(
            "Wczytaj przykładowy wypis, sprawdź co jest czym i dostosuj "
            "odczyt do dokumentów o innej budowie."
        )
        self.btn_profiles.clicked.connect(self.open_profiles_dialog)
        row.addWidget(self.btn_profiles)

        self.lbl_profiles = QLabel()
        self.lbl_profiles.setObjectName("muted_hint")
        self.lbl_profiles.setWordWrap(True)
        row.addWidget(self.lbl_profiles, 1)
        layout.addLayout(row)

        return box

    # ── Odczyt i zapis ustawień ──────────────────────────────────────

    def load_from_config(self, config: dict | None) -> None:
        """Ustawia pola na ekranie według zapisanej konfiguracji."""
        config = config if isinstance(config, dict) else {}

        index = self.municipality_mode.findData(
            config.get(MUNICIPALITY_MODE_KEY, DEFAULT_MUNICIPALITY_MODE)
        )
        self.municipality_mode.setCurrentIndex(index if index >= 0 else 0)

        self.chk_fix_identifier.setChecked(
            bool(config.get(FIX_IDENTIFIER_KEY, DEFAULTS[FIX_IDENTIFIER_KEY]))
        )
        self.chk_read_ownership.setChecked(
            bool(config.get(READ_OWNERSHIP_KEY, DEFAULTS[READ_OWNERSHIP_KEY]))
        )
        self.refresh_profiles_label(config)

    def settings(self) -> dict[str, Any]:
        """Zwraca ustawienia wybrane na ekranie."""
        return {
            MUNICIPALITY_MODE_KEY: self.municipality_mode.currentData(),
            FIX_IDENTIFIER_KEY: self.chk_fix_identifier.isChecked(),
            READ_OWNERSHIP_KEY: self.chk_read_ownership.isChecked(),
        }

    def save_to_config(self, config: dict | None) -> dict[str, Any]:
        """Przepisuje ustawienia z ekranu do konfiguracji programu."""
        values = self.settings()
        if isinstance(config, dict):
            config.update(values)
        return values

    # ── Wzory odczytu PDF ────────────────────────────────────────────

    def refresh_profiles_label(self, config: dict | None = None) -> str:
        """Pokazuje, ile wzorów zapisano, który jest aktywny i gdzie leżą."""
        from utils.global_settings import WYPIS_PROFILES_FILE
        from utils.wypis_profiles import load_settings

        settings = load_settings(config)
        tryb = (
            "automatyczny"
            if settings["auto"]
            else f"ręczny — „{settings['active'] or 'brak'}”"
        )
        text = (
            f"Zapisanych wzorów: {len(settings['profiles'])} • tryb: {tryb} "
            f"• plik: dane/{WYPIS_PROFILES_FILE}"
        )
        self.lbl_profiles.setText(text)
        return text

    def open_profiles_dialog(self, config: dict | None = None) -> bool:
        """Otwiera okno wzorów odczytu wypisów."""
        from modules.wypis_profil_dialog import WypisProfileDialog

        if config is None:
            config = self._config_from_parent()

        dialog = WypisProfileDialog(config, self)
        if dialog.exec():
            self.refresh_profiles_label(config)
            return True
        return False

    def _config_from_parent(self) -> dict:
        """Sięga po konfigurację do zakładki Ustawienia."""
        parent = self.parent()
        while parent is not None:
            config = getattr(parent, "config", None)
            if isinstance(config, dict):
                return config
            parent = parent.parent()
        return {}
