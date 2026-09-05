"""Okno „Wzory odczytu wypisów (PDF)”.

Pozwala wczytać przykładowy wypis, zobaczyć **co program z niego
odczytał i po jakiej etykiecie**, a następnie poprawić przypisania dla
dokumentów o innej budowie. Ustawienia zapisują się jako profil, więc
kolejny wypis z tego samego urzędu odczyta się już poprawnie.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.wypis_pdf_view import (
    WypisPdfView,
    load_page,
    page_count,
    read_area_value,
    read_pdf_text,
)

from utils.global_settings import wypis_profiles_path
from utils.wypis_profiles import (
    FIELD_DEFS,
    FIELD_HINTS,
    FIELD_KEYS,
    FIELD_LABELS,
    analyze_text,
    detect_profile,
    find_profile,
    load_settings,
    normalize_profile,
    save_settings,
    summarize,
    custom_field_key,
    is_custom_field,
    profile_field_defs,
)

STATUS_COLORS = {
    "area": "#e67e22",
    "manual": "#f1c40f",
    "ok": "#2ecc71",
    "found": "#f1c40f",
    "missing": "#8fa3b8",
}

STATUS_TEXTS = {
    "area": "🔲 z obszaru",
    "manual": "✏️ wpisano ręcznie",
    "ok": "✅ odczytano",
    "found": "⚠️ brak wartości",
    "missing": "➖ nieokreślony",
}

#: Pełne wyjaśnienia statusów — pokazywane jako podpowiedź.
STATUS_HINTS = {
    "area": "Wartość czytana z prostokąta narysowanego na dokumencie.",
    "manual": "Wartość poprawiona ręcznie — program nie nadpisze jej odczytem z PDF.",
    "ok": "Program znalazł etykietę i odczytał wartość.",
    "found": "Etykieta jest w dokumencie, ale nie ma przy niej wartości.",
    "missing": "Pole nieokreślone — wskaż je na dokumencie albo wpisz wartość ręcznie.",
}


class WypisProfileDialog(QDialog):
    """Kreator wzorów odczytu wypisów."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self.setWindowTitle("Wzory odczytu wypisów (PDF)")
        # Okno robocze — na małych ekranach zajmie tyle, ile się da.
        self.resize(1480, 940)
        self.setMinimumSize(1000, 640)
        self.setSizeGripEnabled(True)

        settings = load_settings(self.config)
        self.profiles = settings["profiles"]
        self._active_name = settings["active"]
        self._auto = settings["auto"]
        self.pdf_text = ""
        self.pdf_path = ""
        self._loading = False
        self._page_index = 0
        self._page_total = 0
        self._zoom = 100          # procent powiększenia podglądu
        self._fit_zoom = 100      # powiększenie dopasowane do szerokości okna
        #: Historia zmian etykiet — pozwala cofnąć i ponowić przypisanie.
        self._undo: list[tuple[str, dict]] = []
        self._redo: list[tuple[str, dict]] = []
        self._before_edit: dict | None = None
        #: Wartości poprawione ręcznie: {klucz pola: tekst}.
        self._manual_values: dict[str, str] = {}
        #: Obszary odczytu narysowane myszką: {klucz pola: prostokąt %}.
        self._areas: dict[str, dict] = {}
        # Pola, których wartość użytkownik świadomie skasował.
        self._skipped_values: set[str] = set()

        self._build_ui()
        self._apply_style()
        self._reload_profile_combo()

    # ── Budowa okna ──────────────────────────────────────────────────

    def _apply_style(self) -> None:
        """Nowoczesny wygląd okna — czytelne zakładki, ramki i przyciski."""

        self.setStyleSheet("""
            QDialog { background: #14232e; }
            QLabel { color: #e6eef5; }
            QLabel#muted_hint { color: #8fa6b8; }
            QLabel#info_banner {
                background: #1b3242;
                border: 1px solid #27506b;
                border-radius: 8px;
                padding: 10px 12px;
                color: #dbe9f4;
            }
            QGroupBox {
                border: 1px solid #274255;
                border-radius: 10px;
                margin-top: 14px;
                padding-top: 10px;
                font-weight: 600;
                color: #dbe9f4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QTabWidget::pane {
                border: 1px solid #274255;
                border-radius: 10px;
                top: -1px;
                background: #162733;
            }
            QTabBar::tab {
                background: #1b2d3a;
                color: #9fb3c5;
                border: 1px solid #274255;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 9px 20px;
                margin-right: 4px;
                font-size: 13px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #162733;
                color: #ffffff;
                border-color: #3a7fb0;
            }
            QTabBar::tab:hover:!selected { color: #d5e4f0; }
            QPushButton {
                background: #22394a;
                color: #e6eef5;
                border: 1px solid #31556e;
                border-radius: 7px;
                padding: 7px 14px;
            }
            QPushButton:hover { background: #2b4759; border-color: #3f7ea6; }
            QPushButton:pressed { background: #1d3141; }
            QPushButton:disabled { color: #6b8398; border-color: #24404f; }
            QPushButton#btn_primary {
                background: #2f7fb5;
                border-color: #3f9ad4;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#btn_primary:hover { background: #3b93cc; }
            QTableWidget {
                background: #162733;
                alternate-background-color: #1a2e3c;
                color: #e6eef5;
                border: 1px solid #274255;
                border-radius: 8px;
                gridline-color: #24404f;
                selection-background-color: #2f7fb5;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background: #1e3648;
                color: #cfe0ee;
                border: none;
                border-bottom: 2px solid #31556e;
                padding: 8px 6px;
                font-weight: 700;
            }
            QComboBox, QLineEdit, QPlainTextEdit {
                background: #1a2e3c;
                color: #e6eef5;
                border: 1px solid #31556e;
                border-radius: 6px;
                padding: 5px 8px;
                selection-background-color: #2f7fb5;
            }
            QComboBox:hover, QLineEdit:hover { border-color: #3f7ea6; }
            QCheckBox { color: #dbe9f4; spacing: 7px; }
            QScrollArea { border: 1px solid #274255; border-radius: 8px; }
            QSlider::groove:horizontal {
                height: 5px; background: #24404f; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #3f9ad4; width: 15px; margin: -6px 0;
                border-radius: 7px;
            }
        """)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Wczytaj przykładowy wypis i <b>klikaj pola wprost na dokumencie</b>, "
            "aby ustawić, co jest czym. Zapisany wzór posłuży kolejnym wypisom "
            "z tego samego urzędu."
        )
        intro.setObjectName("info_banner")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Użytkownik ma wiedzieć, gdzie leży plik — łatwiej go skopiować
        # na inny komputer albo przekazać współpracownikowi.
        self.lbl_file = QLabel(f"Wzory zapisują się w pliku: {wypis_profiles_path()}")
        self.lbl_file.setObjectName("muted_hint")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setToolTip(
            "Osobny plik — niezależny od pozostałych ustawień programu. "
            "Możesz go skopiować, aby przenieść wzory na inny komputer."
        )
        layout.addWidget(self.lbl_file)

        # ── Pasek wzoru ──
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Wzór:"))

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(260)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self.profile_combo)

        for text, slot, tip in (
            ("➕ Nowy", self._new_profile, "Tworzy nowy, pusty wzór."),
            ("📄 Kopiuj", self._copy_profile, "Kopiuje bieżący wzór pod nową nazwą."),
            ("✏️ Zmień nazwę", self._rename_profile, "Zmienia nazwę wzoru."),
            ("🗑️ Usuń", self._delete_profile, "Usuwa wzór (wbudowanych nie można usunąć)."),
        ):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            profile_row.addWidget(btn)

        profile_row.addStretch()
        layout.addLayout(profile_row)

        # ── Tryb pracy ──
        mode_row = QHBoxLayout()
        self.chk_auto = QCheckBox("Tryb automatyczny — sam dobieraj wzór do dokumentu")
        self.chk_auto.setToolTip(
            "Program porówna treść PDF ze znacznikami wszystkich wzorów i "
            "wybierze najlepiej pasujący. Po odznaczeniu zawsze używany jest "
            "wzór wybrany powyżej."
        )
        self.chk_auto.setChecked(bool(self._auto))
        mode_row.addWidget(self.chk_auto)

        mode_row.addWidget(QLabel(" | Znaczniki rozpoznawania:"))
        self.markers_edit = QLineEdit()
        self.markers_edit.setPlaceholderText(
            "np. wypis z rejestru gruntów; Starostwo Powiatowe w Kartuzach"
        )
        self.markers_edit.setToolTip(
            "Teksty z nagłówka dokumentu, po których program pozna, że wypis "
            "pochodzi z tego urzędu. Oddziel średnikami."
        )
        self.markers_edit.editingFinished.connect(self._store_markers)
        mode_row.addWidget(self.markers_edit, 1)
        layout.addLayout(mode_row)

        # ── Wczytanie PDF ──
        pdf_row = QHBoxLayout()
        btn_load = QPushButton("📂 Wczytaj przykładowy wypis (PDF)")
        btn_load.setObjectName("btn_primary")
        btn_load.clicked.connect(self._load_pdf)
        pdf_row.addWidget(btn_load)

        btn_reanalyze = QPushButton("🔄 Sprawdź ponownie")
        btn_reanalyze.setToolTip("Ponawia analizę po zmianie etykiet.")
        btn_reanalyze.clicked.connect(self._analyze)
        pdf_row.addWidget(btn_reanalyze)

        btn_detect = QPushButton("🔎 Dobierz wzór automatycznie")
        btn_detect.setToolTip("Sprawdza, który zapisany wzór pasuje do wczytanego PDF.")
        btn_detect.clicked.connect(self._detect_for_loaded)
        pdf_row.addWidget(btn_detect)

        self.lbl_pdf = QLabel("Nie wczytano dokumentu.")
        self.lbl_pdf.setObjectName("muted_hint")
        pdf_row.addWidget(self.lbl_pdf, 1)
        layout.addLayout(pdf_row)

        # ── Tabela pól + tekst PDF ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        fields_box = QGroupBox("Co jest czym — pola wypisu")
        fields_layout = QVBoxLayout(fields_box)

        self.table = QTableWidget(len(FIELD_KEYS), 4)
        self.table.setHorizontalHeaderLabels(
            [
                "① Pole w programie",
                "② Etykiety w PDF",
                "③ Stan",
                "④ Odczytana wartość",
            ]
        )
        self.table.horizontalHeaderItem(1).setToolTip(
            "Nazwy pól używane w Twoim PDF. Kilka wariantów oddziel średnikiem."
        )
        self.table.setColumnWidth(1, 240)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_label_edited)
        self.table.itemDoubleClicked.connect(self._before_cell_edit)
        self.table.currentCellChanged.connect(
            lambda *_args: self._before_cell_edit(None)
        )
        fields_layout.addWidget(self.table)

        # ── Cofanie, ponawianie i usuwanie przypisań ──
        edit_row = QHBoxLayout()
        edit_row.setSpacing(6)

        self.btn_undo = QPushButton("↩️ Cofnij")
        self.btn_undo.setToolTip("Cofa ostatnią zmianę przypisań (Ctrl+Z)")
        self.btn_undo.setShortcut("Ctrl+Z")
        self.btn_undo.clicked.connect(self._undo_change)
        self.btn_undo.setEnabled(False)
        edit_row.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↪️ Ponów")
        self.btn_redo.setToolTip("Ponawia cofniętą zmianę (Ctrl+Y)")
        self.btn_redo.setShortcut("Ctrl+Y")
        self.btn_redo.clicked.connect(self._redo_change)
        self.btn_redo.setEnabled(False)
        edit_row.addWidget(self.btn_redo)

        edit_row.addSpacing(12)

        self.btn_clear_row = QPushButton("🗑️ Usuń z pola")
        self.btn_clear_row.setToolTip(
            "Usuwa etykiety przypisane do zaznaczonego wiersza (Delete)"
        )
        self.btn_clear_row.setShortcut("Delete")
        self.btn_clear_row.clicked.connect(self._clear_row)
        edit_row.addWidget(self.btn_clear_row)

        self.btn_clear_value = QPushButton("🚫 Usuń wartość")
        self.btn_clear_value.setToolTip(
            "Kasuje odczytaną wartość w zaznaczonym wierszu — razem z\n"
            "narysowanym obszarem i ręcznym wpisem. Etykiety zostają."
        )
        self.btn_clear_value.clicked.connect(self._clear_row_value)
        edit_row.addWidget(self.btn_clear_value)

        self.btn_clear_all = QPushButton("🧹 Wyczyść wszystkie")
        self.btn_clear_all.setToolTip("Usuwa wszystkie przypisania w tym wzorze")
        self.btn_clear_all.clicked.connect(self._clear_all_rows)
        edit_row.addWidget(self.btn_clear_all)

        edit_row.addStretch()
        fields_layout.addLayout(edit_row)

        # ── Zarządzanie polami: wypisy z różnych urzędów mają różne rubryki ──
        pola_row = QHBoxLayout()
        pola_row.addWidget(QLabel("Pola:"))

        self.btn_field_add = QPushButton("➕ Dodaj pole")
        self.btn_field_add.setToolTip(
            "Dodaje własne pole, jeśli w Twoim wypisie jest rubryka,\n"
            "której program jeszcze nie zna."
        )
        self.btn_field_add.clicked.connect(self._add_custom_field)
        pola_row.addWidget(self.btn_field_add)

        self.btn_field_rename = QPushButton("✏️ Zmień nazwę pola")
        self.btn_field_rename.setToolTip(
            "Zmienia nazwę własnego pola (wbudowanych nazw nie zmieniamy)."
        )
        self.btn_field_rename.clicked.connect(self._rename_custom_field)
        pola_row.addWidget(self.btn_field_rename)

        self.btn_field_remove = QPushButton("➖ Usuń pole")
        self.btn_field_remove.setToolTip(
            "Chowa niepotrzebne pole z tabeli. Pole wbudowane możesz\n"
            "przywrócić przyciskiem „Przywróć pola”."
        )
        self.btn_field_remove.clicked.connect(self._remove_field)
        pola_row.addWidget(self.btn_field_remove)

        self.btn_field_restore = QPushButton("↩ Przywróć pola")
        self.btn_field_restore.setToolTip(
            "Pokazuje z powrotem wszystkie ukryte pola wbudowane."
        )
        self.btn_field_restore.clicked.connect(self._restore_hidden_fields)
        pola_row.addWidget(self.btn_field_restore)

        pola_row.addStretch()
        fields_layout.addLayout(pola_row)

        self.lbl_summary = QLabel("Wczytaj PDF, aby zobaczyć wynik odczytu.")
        self.lbl_summary.setWordWrap(True)
        fields_layout.addWidget(self.lbl_summary)

        hint = QLabel(
            "Jak przypisać pole: <b>1.</b> kliknij wiersz w tabeli, "
            "<b>2.</b> wybierz tryb nad podglądem i wskaż dane na dokumencie. "
            "Gdy dopasowanie po tekście zawodzi, użyj <b>🔲 OBSZAR</b> — "
            "przeciągnij prostokąt wokół wartości, a program będzie czytał "
            "dokładnie stamtąd."
        )
        hint.setObjectName("muted_hint")
        hint.setWordWrap(True)
        fields_layout.addWidget(hint)
        splitter.addWidget(fields_box)

        # ── Prawa strona: podgląd graficzny (domyślny) i tekst zapasowo ──
        self.doc_tabs = QTabWidget()

        # 1. Widok graficzny — klikanie po prawdziwej stronie wypisu.
        page_box = QWidget()
        page_layout = QVBoxLayout(page_box)
        page_layout.setContentsMargins(6, 6, 6, 6)

        page_hint = QLabel(
            "Kliknij w dokumencie nazwę pola (np. „Powiat”) <b>lub jego "
            "wartość</b> — program przypisze ją do wiersza zaznaczonego "
            "w tabeli po lewej. Podświetlenie pokazuje, w co trafisz."
        )
        page_hint.setObjectName("muted_hint")
        page_hint.setWordWrap(True)
        page_layout.addWidget(page_hint)

        # ── Co robi kliknięcie: uczy nazwy pola czy wpisuje wartość? ──
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(QLabel("<b>Klikam, żeby wskazać:</b>"))

        # Dwa duże przyciski — widać od razu, co zrobi kliknięcie.
        self.btn_mode_label = QPushButton("🏷️ NAZWĘ POLA")
        self.btn_mode_label.setCheckable(True)
        self.btn_mode_label.setChecked(True)
        self.btn_mode_label.setMinimumHeight(34)
        self.btn_mode_label.setToolTip(
            "Program zapamięta nazwę pola i sam znajdzie ją\n"
            "w kolejnych wypisach z tego urzędu."
        )

        self.btn_mode_value = QPushButton("✏️ WARTOŚĆ")
        self.btn_mode_value.setCheckable(True)
        self.btn_mode_value.setMinimumHeight(34)
        self.btn_mode_value.setToolTip(
            "Kliknięty tekst trafia wprost do kolumny\n"
            "„Odczytana wartość” — etykiety zostają nietknięte."
        )

        grupa = QButtonGroup(self)
        grupa.setExclusive(True)
        grupa.addButton(self.btn_mode_label)
        grupa.addButton(self.btn_mode_value)
        self._mode_group = grupa

        for przycisk in (self.btn_mode_label, self.btn_mode_value):
            przycisk.setStyleSheet(
                "QPushButton { padding: 4px 14px; font-weight: 600; }"
                "QPushButton:checked { background: #2ecc71; color: #10222b;"
                " border: 2px solid #7ef5b0; }"
            )
            przycisk.toggled.connect(self._on_mode_changed)

        self.btn_mode_area = QPushButton("🔲 OBSZAR (rysuj)")
        self.btn_mode_area.setCheckable(True)
        self.btn_mode_area.setMinimumHeight(34)
        self.btn_mode_area.setToolTip(
            "Przeciągnij myszką prostokąt wokół wartości.\n"
            "Program będzie czytał dokładnie z tego miejsca —\n"
            "bez dopasowywania tekstu."
        )
        grupa.addButton(self.btn_mode_area)
        self.btn_mode_area.setStyleSheet(
            "QPushButton { padding: 4px 14px; font-weight: 600; }"
            "QPushButton:checked { background: #e67e22; color: #201005;"
            " border: 2px solid #ffb366; }"
        )
        self.btn_mode_area.toggled.connect(self._on_mode_changed)

        self.btn_mode_area_label = QPushButton("🏷️🔲 ETYKIETA (rysuj)")
        self.btn_mode_area_label.setCheckable(True)
        self.btn_mode_area_label.setMinimumHeight(34)
        self.btn_mode_area_label.setToolTip(
            "Przeciągnij prostokąt wokół NAZWY pola na dokumencie.\n"
            "Tekst z zaznaczenia trafi do kolumny „Etykiety w PDF”."
        )
        grupa.addButton(self.btn_mode_area_label)
        self.btn_mode_area_label.setStyleSheet(
            "QPushButton { padding: 4px 14px; font-weight: 600; }"
            "QPushButton:checked { background: #16a085; color: #06231e;"
            " border: 2px solid #6ff0d4; }"
        )
        self.btn_mode_area_label.toggled.connect(self._on_mode_changed)

        mode_row.addWidget(self.btn_mode_label)
        mode_row.addWidget(self.btn_mode_value)
        mode_row.addWidget(self.btn_mode_area)
        mode_row.addWidget(self.btn_mode_area_label)
        mode_row.addStretch()
        page_layout.addLayout(mode_row)

        # Pasek stanu — mówi wprost, co się stanie po kliknięciu.
        self.lbl_mode_hint = QLabel()
        self.lbl_mode_hint.setWordWrap(True)
        page_layout.addWidget(self.lbl_mode_hint)
        self._on_mode_changed()

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setToolTip("Poprzednia strona")
        self.btn_prev_page.setFixedWidth(38)
        self.btn_prev_page.clicked.connect(lambda: self._change_page(-1))
        nav_row.addWidget(self.btn_prev_page)

        self.lbl_page = QLabel("Strona —")
        self.lbl_page.setMinimumWidth(110)
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self.lbl_page)

        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setToolTip("Następna strona")
        self.btn_next_page.setFixedWidth(38)
        self.btn_next_page.clicked.connect(lambda: self._change_page(1))
        nav_row.addWidget(self.btn_next_page)

        nav_row.addSpacing(16)

        # ── Powiększenie ──
        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.setToolTip("Pomniejsz (Ctrl + kółko myszy)")
        self.btn_zoom_out.setFixedWidth(38)
        self.btn_zoom_out.clicked.connect(lambda: self._zoom_step(-1))
        nav_row.addWidget(self.btn_zoom_out)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.setToolTip("Powiększenie podglądu")
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        nav_row.addWidget(self.zoom_slider)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setToolTip("Powiększ (Ctrl + kółko myszy)")
        self.btn_zoom_in.setFixedWidth(38)
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_step(1))
        nav_row.addWidget(self.btn_zoom_in)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setMinimumWidth(52)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self.lbl_zoom)

        self.btn_fit = QPushButton("Dopasuj")
        self.btn_fit.setToolTip("Dopasuj szerokość strony do okna")
        self.btn_fit.clicked.connect(self._zoom_fit)
        nav_row.addWidget(self.btn_fit)

        nav_row.addStretch()

        self.chk_show_marks = QCheckBox("Pokaż oznaczenia")
        self.chk_show_marks.setChecked(True)
        self.chk_show_marks.setToolTip(
            "Zielone ramki to etykiety przypisane do pól, niebieskie "
            "przerywane — odczytane wartości."
        )
        self.chk_show_marks.toggled.connect(self._refresh_marks)
        nav_row.addWidget(self.chk_show_marks)
        page_layout.addLayout(nav_row)

        # Legenda kolorów — od razu wiadomo, co oznacza która ramka.
        legend = QLabel(
            '<span style="color:#2ecc71;">■</span> etykieta przypisana &nbsp; '
            '<span style="color:#3498db;">▪</span> odczytana wartość &nbsp; '
            '<span style="color:#f1c40f;">■</span> pod kursorem'
        )
        legend.setObjectName("muted_hint")
        page_layout.addWidget(legend)

        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(False)
        self.page_view = WypisPdfView()
        self.page_view.label_clicked.connect(self._on_label_clicked)
        self.page_view.area_selected.connect(self._on_area_selected)
        self.page_view.zoom_requested.connect(self._zoom_step)
        self.page_scroll.setWidget(self.page_view)
        page_layout.addWidget(self.page_scroll, 1)

        self.doc_tabs.addTab(page_box, "🖱️ Wskaż na dokumencie")

        # 2. Widok tekstowy — dotychczasowy sposób, przydatny przy skanach.
        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(6, 6, 6, 6)
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText(
            "Tu pojawi się tekst wypisu. Zaznacz w nim fragment i kliknij "
            "„Użyj zaznaczenia jako etykiety”, aby szybko przypisać pole."
        )
        text_layout.addWidget(self.text_view)

        use_row = QHBoxLayout()
        btn_use = QPushButton("🏷️ Zaznaczenie to NAZWA pola")
        btn_use.setToolTip(
            "Zaznacz w tekście nazwę pola (np. „Adres nieruchomości”) i "
            "przypisz ją do wiersza wybranego w tabeli po lewej."
        )
        btn_use.clicked.connect(self._use_selection_as_label)
        use_row.addWidget(btn_use)

        btn_use_value = QPushButton("👁️ Zaznaczenie to WARTOŚĆ")
        btn_use_value.setToolTip(
            "Zaznacz w tekście samą wartość (np. „POMORSKIE”).\n"
            "Program sam znajdzie stojącą przy niej nazwę pola i zapamięta ją,\n"
            "żeby czytać tę wartość z każdego kolejnego wypisu."
        )
        btn_use_value.clicked.connect(self._use_selection_as_value)
        use_row.addWidget(btn_use_value)
        use_row.addStretch()
        text_layout.addLayout(use_row)

        self.lbl_text_hint = QLabel(
            "Zaznacz fragment tekstu i kliknij jeden z przycisków — "
            "trafi do wiersza zaznaczonego w tabeli po lewej."
        )
        self.lbl_text_hint.setWordWrap(True)
        self.lbl_text_hint.setStyleSheet("color: #9fb3c8;")
        text_layout.addWidget(self.lbl_text_hint)

        self.doc_tabs.addTab(text_box, "📄 Tekst dokumentu")

        splitter.addWidget(self.doc_tabs)
        splitter.setSizes([620, 620])
        layout.addWidget(splitter, 1)

        # ── Przyciski ──
        buttons = QDialogButtonBox()
        self.btn_save = buttons.addButton(
            "💾 Zapisz wzory", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.btn_save.setObjectName("btn_primary")
        buttons.addButton("Anuluj", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Obsługa wzorów ───────────────────────────────────────────────

    def _reload_profile_combo(self, select_name: str = ""):
        self._loading = True
        self.profile_combo.clear()
        for profile in self.profiles:
            suffix = "  (wbudowany)" if profile.get("builtin") else ""
            self.profile_combo.addItem(f"{profile['name']}{suffix}", profile["name"])

        target = select_name or str(self._active_name or "")
        index = self.profile_combo.findData(target)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self._loading = False
        self._load_profile_into_table()

    def _current_profile(self) -> dict:
        name = self.profile_combo.currentData()
        profile = find_profile(self.profiles, str(name or ""))
        return profile or normalize_profile({})

    def _current_index(self) -> int:
        name = str(self.profile_combo.currentData() or "")
        for index, profile in enumerate(self.profiles):
            if profile["name"] == name:
                return index
        return -1

    def _on_profile_changed(self, _index):
        if not self._loading:
            self._load_profile_into_table()

    def _load_profile_into_table(self):
        profile = self._current_profile()
        self._loading = True

        self.markers_edit.setText("; ".join(profile.get("markers", [])))
        self._skipped_values = {
            str(k) for k in (profile.get("skipped_values") or [])
        }

        # Lista pól zależy od wzoru — użytkownik może dodać własne
        # i ukryć te, których jego urząd nie używa.
        widoczne = profile_field_defs(profile)
        self.table.setRowCount(len(widoczne))
        for row, (key, label, hint) in enumerate(widoczne):
            name_item = QTableWidgetItem(label)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setToolTip(hint)
            name_item.setData(Qt.ItemDataRole.UserRole, key)
            self.table.setItem(row, 0, name_item)

            labels = profile["fields"].get(key, [])
            label_item = QTableWidgetItem("; ".join(labels))
            label_item.setToolTip(
                "Nazwy, pod jakimi to pole występuje w PDF. Możesz podać kilka "
                "wariantów oddzielonych średnikiem."
            )
            self.table.setItem(row, 1, label_item)

            # Kolumna „Stan” jest tylko do odczytu…
            status_item = QTableWidgetItem("")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, status_item)

            # …a „Odczytana wartość” daje się poprawić ręcznie.
            value_item = QTableWidgetItem("")
            value_item.setToolTip("Kliknij dwa razy, aby poprawić wartość ręcznie.")
            self.table.setItem(row, 3, value_item)

        # Obszary odczytu zapisane w tym wzorze.
        self._areas = {
            str(k): dict(v)
            for k, v in dict(profile.get("areas") or {}).items()
            if isinstance(v, dict)
        }

        # Ręczne poprawki zapisane wcześniej w tym wzorze.
        self._manual_values = {
            str(k): str(v)
            for k, v in dict(profile.get("manual_values") or {}).items()
            if str(v).strip()
        }

        self._loading = False
        self.table.resizeRowsToContents()
        if self.pdf_text:
            self._analyze()
        if getattr(self, "page_view", None) is not None and self.pdf_path:
            self._refresh_marks()

    def _store_markers(self):
        index = self._current_index()
        if index < 0:
            return
        markers = [m.strip() for m in self.markers_edit.text().split(";") if m.strip()]
        self.profiles[index]["markers"] = markers

    def _on_value_edited(self, item) -> None:
        """Zapisuje wartość poprawioną ręcznie w kolumnie „Odczytana wartość”."""

        row = item.row()
        key_item = self.table.item(row, 0)
        if key_item is None:
            return
        key = key_item.data(Qt.ItemDataRole.UserRole)
        tekst = item.text().strip()

        if tekst:
            self._manual_values[key] = tekst
            self._skipped_values.discard(key)
            komunikat = f"✏️ Ręcznie ustawiono „{key_item.text()}” = {tekst}"
        else:
            # Pusta komórka = powrót do wartości odczytanej z dokumentu.
            self._manual_values.pop(key, None)
            komunikat = f"↺ Przywrócono odczyt z dokumentu dla „{key_item.text()}”"

        self._store_manual_into_profile()
        if self.pdf_text:
            self._analyze()
        self.lbl_summary.setText(komunikat + "  •  " + self.lbl_summary.text())

    def _store_manual_into_profile(self) -> None:
        """Zapisuje ręczne poprawki we wzorze, by przetrwały zamknięcie okna."""

        index = self._current_index()
        if index >= 0:
            self.profiles[index]["manual_values"] = dict(self._manual_values)

    def _on_area_selected(self, dane: dict) -> None:
        """Zapamiętuje narysowany prostokąt jako źródło odczytu pola."""

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Zaznacz najpierw w tabeli po lewej wiersz, dla którego "
                "rysujesz obszar odczytu.",
            )
            return

        rect = dane.get("rect")
        tekst = str(dane.get("text") or "").strip()
        if rect is None:
            return

        key_item = self.table.item(row, 0)
        key = key_item.data(Qt.ItemDataRole.UserRole)

        # Tryb etykiety: zaznaczony tekst zapisujemy jako nazwę pola.
        if self._click_mode() == "area_label":
            etykieta = tekst.rstrip(":").strip()
            if not etykieta:
                QMessageBox.information(
                    self,
                    "Puste zaznaczenie",
                    "W narysowanym prostokącie nie ma tekstu. "
                    "Zaznacz nazwę pola na dokumencie.",
                )
                return

            self._remember()
            item = self.table.item(row, 1)
            obecne = [
                czesc.strip()
                for czesc in (item.text() if item else "").split(";")
                if czesc.strip()
            ]
            if etykieta not in obecne:
                obecne.insert(0, etykieta)
            self._loading = True
            self.table.setItem(row, 1, QTableWidgetItem("; ".join(obecne)))
            self._loading = False
            self._store_table_into_profile()
            if self.pdf_text:
                self._analyze()
            self._refresh_marks()
            self.lbl_summary.setText(
                f"🏷️ Etykieta „{etykieta}” → {key_item.text()}"
                "  •  " + self.lbl_summary.text()
            )
            return

        obraz = self.page_view.page.image if self.page_view.page else None
        if obraz is None or obraz.width() <= 0 or obraz.height() <= 0:
            return

        # Zapis w procentach strony — niezależny od powiększenia.
        margines = self.page_view.margin_left
        self._remember()
        self._areas[key] = {
            "x": (rect.left() - margines) / obraz.width() * 100.0,
            "y": rect.top() / obraz.height() * 100.0,
            "w": rect.width() / obraz.width() * 100.0,
            "h": rect.height() / obraz.height() * 100.0,
            "page": self._page_index,
        }
        self._skipped_values.discard(key)
        self._store_areas_into_profile()

        if self.pdf_text:
            self._analyze()
        self._refresh_marks()

        if tekst:
            self.lbl_summary.setText(
                f"🔲 {key_item.text()} = {tekst} (z narysowanego obszaru)"
                "  •  " + self.lbl_summary.text()
            )
        else:
            self.lbl_summary.setText(
                f"🔲 Obszar dla „{key_item.text()}” zapisany, ale nie ma w nim "
                "tekstu. Narysuj go jeszcze raz.  •  " + self.lbl_summary.text()
            )

    def _store_areas_into_profile(self) -> None:
        """Zapisuje obszary odczytu we wzorze."""

        index = self._current_index()
        if index >= 0:
            self.profiles[index]["areas"] = dict(self._areas)

    def _area_value(self, key: str) -> str:
        """Czyta wartość pola z zapisanego obszaru, jeśli taki istnieje."""

        obszar = self._areas.get(key)
        if not obszar or not self.pdf_path:
            return ""
        try:
            return read_area_value(self.pdf_path, obszar)
        except Exception:  # pragma: no cover - zależne od pliku
            return ""

    def _click_mode(self) -> str:
        """Zwraca „label”, „value” albo „area” — co robi mysz na dokumencie."""

        if self.btn_mode_area_label.isChecked():
            return "area_label"
        if self.btn_mode_area.isChecked():
            return "area"
        return "value" if self.btn_mode_value.isChecked() else "label"

    def _on_mode_changed(self, *_args) -> None:
        """Odświeża pasek podpowiedzi i przełącza rysowanie w podglądzie."""

        tryb = self._click_mode()
        if getattr(self, "page_view", None) is not None:
            self.page_view.set_draw_mode(tryb in ("area", "area_label"))

        if tryb == "area_label":
            self.lbl_mode_hint.setText(
                "🏷️🔲 <b>Tryb etykiety z zaznaczenia.</b> Przeciągnij "
                "prostokąt wokół <b>nazwy pola</b> na dokumencie — trafi "
                "ona do kolumny <b>② Etykiety w PDF</b> zaznaczonego wiersza."
            )
            self.lbl_mode_hint.setStyleSheet("color: #6ff0d4;")
            return

        if tryb == "area":
            self.lbl_mode_hint.setText(
                "🔲 <b>Tryb obszaru.</b> Zaznacz w tabeli pole, a potem "
                "<b>przeciągnij myszką prostokąt</b> wokół wartości na "
                "dokumencie. Program będzie czytał dokładnie z tego miejsca."
            )
            self.lbl_mode_hint.setStyleSheet("color: #ffb366;")
            return

        if tryb == "value":
            self.lbl_mode_hint.setText(
                "✏️ <b>Tryb wartości.</b> Kliknij w dokumencie tekst, który ma "
                "trafić do kolumny <b>④ Odczytana wartość</b> zaznaczonego "
                "wiersza. Etykiety nie zostaną zmienione."
            )
            self.lbl_mode_hint.setStyleSheet("color: #f1c40f;")
        else:
            self.lbl_mode_hint.setText(
                "🏷️ <b>Tryb nazwy pola.</b> Kliknij nazwę pola w dokumencie, "
                "a program zapamięta ją w kolumnie <b>② Etykiety w PDF</b> i "
                "rozpozna w kolejnych wypisach."
            )
            self.lbl_mode_hint.setStyleSheet("color: #7ef5b0;")

    def _before_cell_edit(self, _item=None) -> None:
        """Zapamiętuje treść komórek tuż przed ręczną edycją."""

        if not self._loading:
            self._before_edit = self._fields_snapshot()

    # ── Cofanie i ponawianie ─────────────────────────────────────────

    def _fields_snapshot(self) -> dict:
        """Zapamiętuje etykiety i ręczne wartości wybranego wzoru."""

        labels = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if key_item is None:
                continue
            key = key_item.data(Qt.ItemDataRole.UserRole)
            labels[key] = value_item.text() if value_item else ""
        return {
            "labels": labels,
            "manual": dict(self._manual_values),
            "areas": {k: dict(v) for k, v in self._areas.items()},
            "skipped": set(self._skipped_values),
        }

    def _remember(self) -> None:
        """Odkłada stan przed zmianą, żeby dało się ją cofnąć."""

        name = str(self.profile_combo.currentData() or "")
        self._undo.append((name, self._fields_snapshot()))
        del self._undo[:-40]          # trzymamy ostatnie 40 kroków
        self._redo.clear()
        self._update_history_buttons()

    def _apply_snapshot(self, snapshot: dict) -> None:
        """Przywraca zapamiętane etykiety i ręczne wartości."""

        labels = snapshot.get("labels", {})
        self._manual_values = dict(snapshot.get("manual", {}))
        self._areas = {
            k: dict(v) for k, v in dict(snapshot.get("areas", {})).items()
        }
        self._skipped_values = set(snapshot.get("skipped", set()))

        self._loading = True
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            if key_item is None:
                continue
            key = key_item.data(Qt.ItemDataRole.UserRole)
            self.table.setItem(row, 1, QTableWidgetItem(labels.get(key, "")))
        self._loading = False
        self._store_table_into_profile()
        self._store_manual_into_profile()
        self._store_areas_into_profile()
        self._store_skipped_into_profile()
        if self.pdf_text:
            self._analyze()
        if self.pdf_path:
            self._refresh_marks()

    def _undo_change(self) -> None:
        """Cofa ostatnią zmianę przypisań."""

        if not self._undo:
            return
        name, snapshot = self._undo.pop()
        self._redo.append((name, self._fields_snapshot()))
        if name and name != str(self.profile_combo.currentData() or ""):
            self._reload_profile_combo(name)
        self._apply_snapshot(snapshot)
        self._update_history_buttons()
        self.lbl_summary.setText("↩️ Cofnięto zmianę.  •  " + self.lbl_summary.text())

    def _redo_change(self) -> None:
        """Ponawia cofniętą zmianę."""

        if not self._redo:
            return
        name, snapshot = self._redo.pop()
        self._undo.append((name, self._fields_snapshot()))
        if name and name != str(self.profile_combo.currentData() or ""):
            self._reload_profile_combo(name)
        self._apply_snapshot(snapshot)
        self._update_history_buttons()
        self.lbl_summary.setText("↪️ Ponowiono zmianę.  •  " + self.lbl_summary.text())

    def _update_history_buttons(self) -> None:
        self.btn_undo.setEnabled(bool(self._undo))
        self.btn_redo.setEnabled(bool(self._redo))

    # ── Usuwanie przypisań ───────────────────────────────────────────

    def _clear_row_value(self) -> None:
        """Kasuje odczytaną wartość, zostawiając przypisane etykiety."""

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Zaznacz w tabeli wiersz, którego wartość chcesz usunąć.",
            )
            return

        key_item = self.table.item(row, 0)
        key = key_item.data(Qt.ItemDataRole.UserRole)

        obecna = self.table.item(row, 3)
        obecna = obecna.text().strip() if obecna else ""
        if not obecna and key not in self._areas and key not in self._manual_values:
            return

        self._remember()
        # Kasujemy wszystkie źródła wartości: obszar, wpis ręczny i odczyt.
        self._areas.pop(key, None)
        self._manual_values.pop(key, None)
        self._skipped_values.add(key)
        self._store_areas_into_profile()
        self._store_manual_into_profile()
        self._store_skipped_into_profile()

        self._loading = True
        self.table.setItem(row, 3, QTableWidgetItem(""))
        self._loading = False

        if self.pdf_text:
            self._analyze()
        self._refresh_marks()
        self.lbl_summary.setText(
            f"🚫 Usunięto wartość pola „{key_item.text()}”. "
            + self.lbl_summary.text()
        )

    def _add_custom_field(self) -> None:
        """Dodaje własne pole — gdy wypis ma rubrykę, której program nie zna."""

        nazwa, ok = QInputDialog.getText(
            self,
            "Nowe pole",
            "Nazwa pola, tak jak ma się pokazywać w programie:",
        )
        if not ok:
            return

        nazwa = str(nazwa or "").strip()
        if not nazwa:
            QMessageBox.information(
                self, "Pusta nazwa", "Podaj nazwę nowego pola."
            )
            return

        profile = self.profiles[self._current_index()]
        wlasne = dict(profile.get("custom_fields") or {})
        zajete = set(FIELD_KEYS) | set(wlasne)
        klucz = custom_field_key(nazwa, zajete)

        self._remember()
        wlasne[klucz] = nazwa
        profile["custom_fields"] = wlasne

        # Nowe pole nie może zostać ukryte resztką po starym wpisie.
        ukryte = [k for k in (profile.get("hidden_fields") or []) if k != klucz]
        profile["hidden_fields"] = ukryte

        self._load_profile_into_table()
        self._select_row_by_key(klucz)
        self.lbl_summary.setText(f"➕ Dodano pole „{nazwa}”.")

    def _rename_custom_field(self) -> None:
        """Zmienia nazwę pola dodanego przez użytkownika."""

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Zaznacz w tabeli pole, któremu chcesz zmienić nazwę.",
            )
            return

        key_item = self.table.item(row, 0)
        key = key_item.data(Qt.ItemDataRole.UserRole)
        if not is_custom_field(key):
            QMessageBox.information(
                self,
                "Pole wbudowane",
                "Nazw pól wbudowanych nie zmieniamy — inne części programu "
                "korzystają z nich pod tymi nazwami.\n\n"
                "Możesz je ukryć przyciskiem „Usuń pole” i dodać własne.",
            )
            return

        nazwa, ok = QInputDialog.getText(
            self, "Zmiana nazwy pola", "Nowa nazwa:", text=key_item.text()
        )
        if not ok:
            return
        nazwa = str(nazwa or "").strip()
        if not nazwa:
            return

        self._remember()
        profile = self.profiles[self._current_index()]
        wlasne = dict(profile.get("custom_fields") or {})
        wlasne[key] = nazwa
        profile["custom_fields"] = wlasne
        self._load_profile_into_table()
        self._select_row_by_key(key)
        self.lbl_summary.setText(f"✏️ Zmieniono nazwę pola na „{nazwa}”.")

    def _remove_field(self) -> None:
        """Chowa pole z tabeli — wbudowane da się przywrócić."""

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Zaznacz w tabeli pole, które chcesz usunąć.",
            )
            return

        key_item = self.table.item(row, 0)
        key = key_item.data(Qt.ItemDataRole.UserRole)
        nazwa = key_item.text()

        pytanie = (
            f"Usunąć pole „{nazwa}” z tego wzoru?"
            if is_custom_field(key)
            else f"Ukryć pole „{nazwa}”?\n\n"
            "Pole wbudowane możesz przywrócić przyciskiem „Przywróć pola”."
        )
        if QMessageBox.question(
            self,
            "Usunięcie pola",
            pytanie,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self._remember()
        profile = self.profiles[self._current_index()]

        if is_custom_field(key):
            wlasne = dict(profile.get("custom_fields") or {})
            wlasne.pop(key, None)
            profile["custom_fields"] = wlasne
        else:
            ukryte = list(profile.get("hidden_fields") or [])
            if key not in ukryte:
                ukryte.append(key)
            profile["hidden_fields"] = ukryte

        # Sprzątamy dane, które zostałyby po niewidocznym polu.
        for slownik in (profile.get("fields"), profile.get("manual_values"),
                        profile.get("areas")):
            if isinstance(slownik, dict):
                slownik.pop(key, None)
        self._areas.pop(key, None)
        self._manual_values.pop(key, None)

        self._load_profile_into_table()
        self.lbl_summary.setText(f"➖ Usunięto pole „{nazwa}”.")

    def _restore_hidden_fields(self) -> None:
        """Przywraca ukryte pola wbudowane."""

        profile = self.profiles[self._current_index()]
        ukryte = list(profile.get("hidden_fields") or [])
        if not ukryte:
            QMessageBox.information(
                self, "Nie ma co przywracać", "Żadne pole nie jest ukryte."
            )
            return

        self._remember()
        profile["hidden_fields"] = []
        self._load_profile_into_table()
        self.lbl_summary.setText(f"↩ Przywrócono ukryte pola ({len(ukryte)}).")

    def _select_row_by_key(self, key: str) -> None:
        """Zaznacza w tabeli wiersz o wskazanym kluczu pola."""

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == key:
                self.table.setCurrentCell(row, 1)
                return

    def _store_skipped_into_profile(self) -> None:
        """Zapisuje listę pól z celowo skasowaną wartością."""

        index = self._current_index()
        if index >= 0:
            self.profiles[index]["skipped_values"] = sorted(self._skipped_values)

    def _clear_row(self) -> None:
        """Usuwa etykiety z zaznaczonego pola."""

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Zaznacz w tabeli wiersz, którego przypisanie chcesz usunąć.",
            )
            return

        item = self.table.item(row, 1)
        key = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        ma_obszar = key in self._areas
        if not (item and item.text().strip()) and not ma_obszar:
            return

        self._remember()
        name = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
        self._areas.pop(key, None)
        self._manual_values.pop(key, None)
        self._store_areas_into_profile()
        self._store_manual_into_profile()
        self._loading = True
        self.table.setItem(row, 1, QTableWidgetItem(""))
        self._loading = False
        self._store_table_into_profile()
        if self.pdf_text:
            self._analyze()
        if self.pdf_path:
            self._refresh_marks()
        self.lbl_summary.setText(
            f"🗑️ Usunięto przypisanie pola „{name}”.  •  " + self.lbl_summary.text()
        )

    def _clear_all_rows(self) -> None:
        """Czyści wszystkie przypisania bieżącego wzoru."""

        if self._current_profile().get("builtin"):
            QMessageBox.information(
                self,
                "Wzór wbudowany",
                "Wzoru wbudowanego nie da się wyczyścić.\n"
                "Użyj „📄 Kopiuj”, aby zrobić własną wersję do edycji.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Wyczyść wszystkie pola",
            "Usunąć wszystkie przypisania w tym wzorze?\n"
            "Zmianę można cofnąć przyciskiem „↩️ Cofnij”.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._remember()
        self._apply_snapshot({"labels": {}, "manual": {}, "areas": {}})
        self.lbl_summary.setText(
            "🧹 Wyczyszczono wszystkie przypisania.  •  " + self.lbl_summary.text()
        )

    def _store_table_into_profile(self):
        index = self._current_index()
        if index < 0:
            return
        fields = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if not key_item:
                continue
            key = key_item.data(Qt.ItemDataRole.UserRole)
            text = value_item.text() if value_item else ""
            fields[key] = [p.strip() for p in text.split(";") if p.strip()]
        self.profiles[index]["fields"] = fields

    def _on_label_edited(self, item):
        if self._loading:
            return

        if item.column() == 3:
            self._on_value_edited(item)
            return

        if item.column() != 1:
            return
        # Snapshot pobrany po edycji zawierałby już nową treść, dlatego
        # odtwarzamy stan sprzed zmiany z zapamiętanej kopii komórki.
        if self._before_edit is not None:
            name = str(self.profile_combo.currentData() or "")
            self._undo.append((name, self._before_edit))
            del self._undo[:-40]
            self._redo.clear()
            self._before_edit = None
            self._update_history_buttons()
        self._store_table_into_profile()
        if self.pdf_text:
            self._analyze()

    def _new_profile(self):
        name, ok = QInputDialog.getText(
            self, "Nowy wzór", "Nazwa wzoru (np. Starostwo Kartuzy):"
        )
        if not ok or not name.strip():
            return
        if find_profile(self.profiles, name):
            QMessageBox.warning(self, "Nazwa zajęta", "Wzór o tej nazwie już istnieje.")
            return
        self.profiles.append(normalize_profile({"name": name.strip()}))
        self._reload_profile_combo(name.strip())

    def _copy_profile(self):
        source = self._current_profile()
        name, ok = QInputDialog.getText(
            self, "Kopiuj wzór", "Nazwa kopii:", text=f"{source['name']} — kopia"
        )
        if not ok or not name.strip():
            return
        if find_profile(self.profiles, name):
            QMessageBox.warning(self, "Nazwa zajęta", "Wzór o tej nazwie już istnieje.")
            return
        clone = normalize_profile(source)
        clone["name"] = name.strip()
        clone["builtin"] = False
        self.profiles.append(clone)
        self._reload_profile_combo(clone["name"])

    def _rename_profile(self):
        index = self._current_index()
        if index < 0:
            return
        if self.profiles[index].get("builtin"):
            QMessageBox.information(
                self,
                "Wzór wbudowany",
                "Nazwy wzoru wbudowanego nie można zmienić.\n"
                "Użyj przycisku „Kopiuj”, aby zrobić własną wersję.",
            )
            return
        name, ok = QInputDialog.getText(
            self, "Zmień nazwę", "Nowa nazwa:", text=self.profiles[index]["name"]
        )
        if not ok or not name.strip():
            return
        self.profiles[index]["name"] = name.strip()
        self._reload_profile_combo(name.strip())

    def _delete_profile(self):
        index = self._current_index()
        if index < 0:
            return
        if self.profiles[index].get("builtin"):
            QMessageBox.information(
                self, "Wzór wbudowany", "Wzoru wbudowanego nie można usunąć."
            )
            return
        reply = QMessageBox.question(
            self,
            "Usuń wzór",
            f"Usunąć wzór „{self.profiles[index]['name']}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self.profiles[index]
            self._reload_profile_combo()

    # ── Praca z dokumentem ───────────────────────────────────────────

    def _load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Wybierz przykładowy wypis", "", "PDF (*.pdf)"
        )
        if not path:
            return
        self.load_pdf_path(path)

    def load_pdf_path(self, path: str) -> bool:
        """Wczytuje tekst z PDF (wydzielone, by dało się testować)."""

        try:
            self.pdf_text = read_pdf_text(path)
        except Exception as exc:  # pragma: no cover - zależne od pliku
            QMessageBox.critical(
                self,
                "Nie udało się odczytać PDF",
                f"Program nie zdołał otworzyć tego pliku.\n\n{exc}",
            )
            return False

        self.pdf_path = path
        self.text_view.setPlainText(self.pdf_text)
        self.lbl_pdf.setText(f"Wczytano: {Path(path).name}")

        # Podgląd graficzny — to na nim wskazuje się pola myszą.
        self._page_total = page_count(path)
        self._page_index = 0
        self._load_page_view()

        if self.chk_auto.isChecked():
            self._detect_for_loaded(silent=True)
        else:
            self._analyze()
        return True

    # ── Podgląd graficzny ────────────────────────────────────────────

    def _load_page_view(self) -> None:
        """Renderuje bieżącą stronę wypisu do podglądu graficznego."""

        if not self.pdf_path:
            self.page_view.set_page(None)
            self.lbl_page.setText("Strona —")
            return

        # Powiększenie 100% = strona dopasowana do szerokości panelu.
        # Odejmujemy margines na podpisy pól, żeby strona zmieściła się w oknie.
        available = max(
            self.page_scroll.viewport().width() - 26 - self.page_view.margin_left,
            340,
        )
        probe = load_page(self.pdf_path, self._page_index, dpi=96)
        if probe is None:
            self.page_view.set_page(None)
            self.lbl_page.setText(
                "Nie udało się narysować strony — użyj zakładki „Tekst dokumentu”."
            )
            return
        self._fit_zoom = 96 * available / probe.image.width()

        dpi = max(int(self._fit_zoom * self._zoom / 100), 40)
        page = load_page(self.pdf_path, self._page_index, dpi=dpi) or probe
        self.page_view.set_page(page)
        if page is None:
            self.lbl_page.setText(
                "Nie udało się narysować strony — użyj zakładki „Tekst dokumentu”."
            )
        else:
            self.lbl_page.setText(
                f"Strona {self._page_index + 1} z {self._page_total}"
            )
        self.btn_prev_page.setEnabled(self._page_index > 0)
        self.btn_next_page.setEnabled(self._page_index + 1 < self._page_total)
        self._refresh_marks()

    def _on_zoom_changed(self, value: int) -> None:
        """Suwak powiększenia — przerysowuje stronę w nowej skali."""

        self._zoom = int(value)
        self.lbl_zoom.setText(f"{self._zoom}%")
        if self.pdf_path:
            self._load_page_view()

    def _zoom_step(self, direction: int) -> None:
        """Powiększa lub pomniejsza o jeden krok (przyciski, Ctrl+kółko)."""

        self.zoom_slider.setValue(
            max(50, min(300, self._zoom + (25 if direction > 0 else -25)))
        )

    def _zoom_fit(self) -> None:
        """Wraca do powiększenia dopasowanego do szerokości okna."""

        self.zoom_slider.setValue(100)

    def _change_page(self, step: int) -> None:
        new_index = self._page_index + step
        if 0 <= new_index < self._page_total:
            self._page_index = new_index
            self._load_page_view()

    def _refresh_marks(self) -> None:
        """Rysuje ramki pól, które mają już przypisane etykiety."""

        if not self.chk_show_marks.isChecked():
            self.page_view.set_marks({}, {})
            self.page_view.set_area_marks({})
            return

        profile = self._current_profile()
        marks: dict[str, object] = {}
        values: dict[str, object] = {}
        etykiety = {k: l for k, l, _h in profile_field_defs(profile)}
        for key, nazwa in etykiety.items():
            rect, value_rect = self.page_view.label_and_value_rects(
                profile["fields"].get(key, [])
            )
            if rect is not None:
                marks[nazwa] = rect
            if value_rect is not None:
                values[nazwa] = value_rect
        self.page_view.set_marks(marks, values)

        # Narysowane obszary przeliczamy z procentów na piksele podglądu.
        obraz = self.page_view.page.image if self.page_view.page else None
        obszary = {}
        if obraz is not None and obraz.width() > 0:
            margines = self.page_view.margin_left
            for key, obszar in self._areas.items():
                if int(obszar.get("page", 0)) != self._page_index:
                    continue
                obszary[key] = QRectF(
                    float(obszar.get("x", 0)) / 100.0 * obraz.width() + margines,
                    float(obszar.get("y", 0)) / 100.0 * obraz.height(),
                    float(obszar.get("w", 0)) / 100.0 * obraz.width(),
                    float(obszar.get("h", 0)) / 100.0 * obraz.height(),
                )

        aktywne = ""
        row = self.table.currentRow()
        if row >= 0 and self.table.item(row, 0) is not None:
            aktywne = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.page_view.set_area_marks(obszary, aktywne)

    def _on_label_clicked(self, hit: dict) -> None:
        """Przypisuje klikniętą etykietę do wiersza wybranego w tabeli."""

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Kliknij najpierw wiersz w tabeli po lewej, aby wskazać, "
                "do którego pola przypisać tę etykietę.",
            )
            return

        label = str(hit.get("label") or "").strip()
        value = str(hit.get("value") or "").strip()

        # Tryb „wartość”: uczymy program, skąd brać tę daną. Zapamiętujemy
        # nazwę pola (nagłówek kolumny lub tekst przed dwukropkiem), więc
        # wartość zostanie ODCZYTANA — także z kolejnych wypisów.
        if self._click_mode() == "value":
            wpis = value or str(hit.get("word") or "").strip()
            key_item = self.table.item(row, 0)
            key = key_item.data(Qt.ItemDataRole.UserRole)

            if label:
                # Znamy nazwę pola — uczymy jej i czytamy automatycznie.
                self._remember()
                item = self.table.item(row, 1)
                obecne = [
                    czesc.strip()
                    for czesc in (item.text() if item else "").split(";")
                    if czesc.strip()
                ]
                if label not in obecne:
                    obecne.insert(0, label)
                self._loading = True
                self.table.setItem(row, 1, QTableWidgetItem("; ".join(obecne)))
                self._loading = False
                self._manual_values.pop(key, None)
                self._store_table_into_profile()
                self._store_manual_into_profile()
                if self.pdf_text:
                    self._analyze()
                self._refresh_marks()

                odczytane = self.table.item(row, 3)
                odczytane = odczytane.text() if odczytane else ""
                if odczytane:
                    self.lbl_summary.setText(
                        f"✅ {key_item.text()} = {odczytane} "
                        f"(odczytane z „{label}”)  •  " + self.lbl_summary.text()
                    )
                    return
                # Nie udało się odczytać — wpisujemy to, co kliknięto.

            if not wpis:
                return
            self._remember()
            self._manual_values[key] = wpis
            self._skipped_values.discard(key)
            self._store_manual_into_profile()
            self._loading = True
            self.table.setItem(row, 3, QTableWidgetItem(wpis))
            self._loading = False
            if self.pdf_text:
                self._analyze()
            self._refresh_marks()
            self.lbl_summary.setText(
                f"✏️ Wpisano „{wpis}” → {key_item.text()}"
                "  •  " + self.lbl_summary.text()
            )
            return

        if not label:
            return

        item = self.table.item(row, 1)
        self._remember()
        current = [p.strip() for p in (item.text() if item else "").split(";") if p.strip()]
        if label in current:
            QMessageBox.information(
                self,
                "Etykieta już przypisana",
                f"„{label}” jest już przypisana do tego pola.",
            )
            return

        current.insert(0, label)
        self.table.setItem(row, 1, QTableWidgetItem("; ".join(current)))
        self._store_table_into_profile()
        self._analyze()
        self._refresh_marks()

        field_name = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
        self.lbl_summary.setText(
            f"Przypisano „{label}” → {field_name}"
            + (f" (odczytano: {value})" if value else "")
            + "  •  "
            + self.lbl_summary.text()
        )

    def _detect_for_loaded(self, silent: bool = False):
        if not self.pdf_text:
            if not silent:
                QMessageBox.information(
                    self, "Brak dokumentu", "Najpierw wczytaj przykładowy wypis."
                )
            return

        profile, score = detect_profile(self.profiles, self.pdf_text)
        if not profile:
            if not silent:
                QMessageBox.information(
                    self,
                    "Nie rozpoznano",
                    "Żaden wzór nie pasuje do tego dokumentu.\n\n"
                    "Utwórz nowy wzór i przypisz pola ręcznie.",
                )
            return

        self._reload_profile_combo(profile["name"])
        if not silent:
            QMessageBox.information(
                self,
                "Dobrano wzór",
                f"Najlepiej pasuje wzór „{profile['name']}” (trafność: {score}).",
            )

    def _analyze(self):
        if not self.pdf_text:
            self.lbl_summary.setText("Wczytaj PDF, aby zobaczyć wynik odczytu.")
            return

        profile = self._current_profile()
        rows = {r["field"]: r for r in analyze_text(self.pdf_text, profile)}

        self._loading = True
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            if not key_item:
                continue
            key = key_item.data(Qt.ItemDataRole.UserRole)
            data = rows.get(key, {})
            status = data.get("status", "missing")

            # Wartość skasowana przyciskiem „Usuń wartość” ma zostać pusta,
            # dopóki użytkownik sam nie wskaże jej na nowo.
            if key in self._skipped_values:
                status = "missing"
                data = {}

            # Komórki tworzymy tylko raz — ponowne setItem() na istniejącym
            # elemencie Qt zgłasza ostrzeżenie o zmianie właściciela.
            status_item = self.table.item(row, 2)
            if status_item is None:
                status_item = QTableWidgetItem()
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 2, status_item)
            status_item.setText(STATUS_TEXTS.get(status, ""))
            status_item.setForeground(QColor(STATUS_COLORS.get(status, "#cccccc")))
            tip = STATUS_HINTS.get(status, "")
            if data.get("matched_label"):
                tip += f"\nDopasowana etykieta: {data['matched_label']}"
            status_item.setToolTip(tip)

            value_item = self.table.item(row, 3)
            if value_item is None:
                value_item = QTableWidgetItem()
                value_item.setToolTip(
                    "Kliknij dwa razy, aby poprawić wartość ręcznie."
                )
                self.table.setItem(row, 3, value_item)

            # Obszar narysowany myszką ma pierwszeństwo — użytkownik
            # wskazał wprost, skąd czytać tę wartość.
            z_obszaru = self._area_value(key)
            if z_obszaru:
                value_item.setText(z_obszaru)
                value_item.setForeground(QColor("#ffb366"))
                value_item.setToolTip(
                    "Odczytane z obszaru narysowanego na dokumencie."
                )
                status_item.setText(STATUS_TEXTS["area"])
                status_item.setForeground(QColor(STATUS_COLORS["area"]))
                status_item.setToolTip(STATUS_HINTS["area"])
                value_item.setFont(QFont("", -1, QFont.Weight.Bold))
                continue

            # Ręczna poprawka użytkownika jest ważniejsza niż odczyt z PDF.
            reczna = self._manual_values.get(key)
            if reczna is not None:
                value_item.setText(reczna)
                value_item.setForeground(QColor("#f1c40f"))
                value_item.setToolTip(
                    "Wartość wpisana ręcznie.\n"
                    "Wyczyść komórkę, aby wrócić do odczytu z dokumentu."
                )
                status_item.setText(STATUS_TEXTS["manual"])
                status_item.setForeground(QColor(STATUS_COLORS["manual"]))
                status_item.setToolTip(STATUS_HINTS["manual"])
            else:
                value_item.setText(data.get("value", ""))
                value_item.setForeground(QColor("#e8eef4"))
                value_item.setToolTip(
                    "Kliknij dwa razy, aby poprawić wartość ręcznie."
                )
            pogrubienie = status == "ok" or reczna is not None
            value_item.setFont(
                QFont("", -1, QFont.Weight.Bold if pogrubienie else QFont.Weight.Normal)
            )
        self._loading = False

        self.lbl_summary.setText(summarize(rows.values()))
        self.table.resizeRowsToContents()

    def _selected_text(self) -> str:
        """Zaznaczony tekst z zakładki tekstowej.

        Qt oddziela wiersze znakiem ``\u2029`` (separator akapitu), a nie
        zwykłym końcem linii — bez zamiany zaznaczenie obejmujące kilka
        wierszy nie dawało się z niczym porównać.
        """

        zaznaczenie = self.text_view.textCursor().selectedText()
        return zaznaczenie.replace("\u2029", "\n").replace("\u2028", "\n").strip()

    def _use_selection_as_label(self):
        selection = self._selected_text()
        if not selection:
            QMessageBox.information(
                self,
                "Brak zaznaczenia",
                "Zaznacz w tekście nazwę pola, np. „Adres nieruchomości”.",
            )
            return

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Kliknij najpierw wiersz w tabeli po lewej, aby wskazać, "
                "do którego pola przypisać tę etykietę.",
            )
            return

        # Etykieta to zwykle tekst przed dwukropkiem.
        label = selection.split(":")[0].strip(" :,;-")
        if not label:
            return

        item = self.table.item(row, 1)
        current = [p.strip() for p in (item.text() if item else "").split(";") if p.strip()]
        if label not in current:
            self._remember()
            current.insert(0, label)
        self.table.setItem(row, 1, QTableWidgetItem("; ".join(current)))
        self._store_table_into_profile()
        self._analyze()

    def _use_selection_as_value(self):
        """Zaznaczono WARTOŚĆ — program sam szuka stojącej przy niej nazwy."""

        zaznaczenie = self._selected_text()
        if not zaznaczenie:
            QMessageBox.information(
                self,
                "Brak zaznaczenia",
                "Zaznacz w tekście wartość, np. „POMORSKIE”.",
            )
            return

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Nie wybrano pola",
                "Kliknij najpierw wiersz w tabeli po lewej, aby wskazać, "
                "którego pola dotyczy ta wartość.",
            )
            return

        etykieta = self._label_for_value(zaznaczenie)
        key_item = self.table.item(row, 0)
        key = key_item.data(Qt.ItemDataRole.UserRole)
        self._remember()

        if etykieta:
            # Znaleziono nazwę pola — zapamiętujemy ją, żeby program czytał
            # tę wartość także z kolejnych wypisów tego samego urzędu.
            item = self.table.item(row, 1)
            obecne = [
                czesc.strip()
                for czesc in (item.text() if item else "").split(";")
                if czesc.strip()
            ]
            if etykieta not in obecne:
                obecne.insert(0, etykieta)
            self._loading = True
            self.table.setItem(row, 1, QTableWidgetItem("; ".join(obecne)))
            self._loading = False
            self._manual_values.pop(key, None)
            self._store_table_into_profile()
            self._store_manual_into_profile()
            self._analyze()
            self._refresh_marks()
            self.lbl_text_hint.setText(
                f"✅ {key_item.text()} = „{zaznaczenie}” — odczytane po "
                f"nazwie „{etykieta}”. Zadziała też w kolejnych wypisach."
            )
            self.lbl_text_hint.setStyleSheet("color: #2ecc71;")
            return

        # Nie ma nazwy przy wartości — zapisujemy ją jako wpis ręczny.
        self._manual_values[key] = zaznaczenie
        self._skipped_values.discard(key)
        self._store_manual_into_profile()
        self._analyze()
        self._refresh_marks()
        self.lbl_text_hint.setText(
            f"✏️ {key_item.text()} = „{zaznaczenie}” — wpisane ręcznie, bo "
            "przy tej wartości nie ma nazwy pola."
        )
        self.lbl_text_hint.setStyleSheet("color: #f1c40f;")

    def _label_for_value(self, wartosc: str) -> str:
        """Szuka nazwy pola stojącej przy wskazanej wartości w tekście.

        Sprawdza po kolei cztery układy spotykane w wypisach:
        „Nazwa: wartość”, „Nazwa   wartość”, nazwę w wierszu wyżej
        (tabela w kratkę) oraz nazwę w wierszu wyżej po lewej.
        """

        import re

        tekst = self.pdf_text or ""
        wartosc = str(wartosc or "").strip()
        if not tekst or not wartosc:
            return ""

        # Wieloliniowe zaznaczenie — bierzemy pierwszy niepusty wiersz.
        if "\n" in wartosc:
            czesci = [c.strip() for c in wartosc.split("\n") if c.strip()]
            if not czesci:
                return ""
            wartosc = czesci[0]

        linie = tekst.splitlines()
        for numer, linia in enumerate(linie):
            if wartosc not in linia:
                continue

            przed = linia.split(wartosc)[0].strip()

            # 1. „Województwo: POMORSKIE”
            if przed.endswith(":"):
                kandydat = przed.rstrip(":").strip(" ,;-")
                # Przy kilku parach w wierszu bierzemy tę bliżej wartości.
                kandydat = re.split(r"\s{2,}", kandydat)[-1].strip()
                if kandydat:
                    return kandydat

            # 2. „Województwo   POMORSKIE” — nazwa to ostatnia kolumna przed.
            #    Gdy tuż przed wartością stoi dana („0019, BOJANO”),
            #    cofamy się do wcześniejszej kolumny w tym samym wierszu.
            if przed:
                kolumny = [
                    czesc.strip(" :,;-")
                    for czesc in re.split(r"\s{2,}", przed)
                    if czesc.strip(" :,;-")
                ]
                for kandydat in reversed(kolumny):
                    if kandydat and not self._wyglada_na_dane(kandydat):
                        return kandydat

            # 3. Tabela w kratkę: nazwa kolumny stoi w wierszu wyżej,
            #    w tym samym miejscu co wartość.
            poczatek = linia.index(wartosc)
            koniec = poczatek + len(wartosc)
            for wyzej in range(numer - 1, max(numer - 4, -1), -1):
                naglowek = self._kolumna_w_wierszu(
                    linie[wyzej], poczatek, koniec
                )
                if naglowek and not self._wyglada_na_dane(naglowek):
                    return naglowek

        return ""

    @staticmethod
    def _wyglada_na_dane(tekst: str) -> bool:
        """Czy tekst wygląda na daną (ma cyfry), a nie na nazwę pola?"""

        return any(znak.isdigit() for znak in str(tekst or ""))

    @staticmethod
    def _kolumna_w_wierszu(linia: str, od: int, do: int | None = None) -> str:
        """Zwraca kolumnę wiersza najlepiej pokrywającą się z zakresem.

        Wypisy bywają nierówno wyrównane, więc zamiast wymagać trafienia
        co do znaku wybieramy kolumnę o największym wspólnym fragmencie.
        """

        import re

        if not linia.strip():
            return ""

        do = od + 1 if do is None else do
        najlepsza, najlepsze_pokrycie = "", 0
        for dopasowanie in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", linia):
            poczatek, koniec = dopasowanie.span()
            pokrycie = min(koniec, do) - max(poczatek, od)
            if pokrycie > najlepsze_pokrycie:
                najlepsze_pokrycie = pokrycie
                najlepsza = dopasowanie.group().strip(" :,;-")
        return najlepsza

    # ── Zapis ────────────────────────────────────────────────────────

    def _save_and_close(self):
        self._store_table_into_profile()
        self._store_markers()

        active = str(self.profile_combo.currentData() or "")
        auto = self.chk_auto.isChecked()
        # Wzory trafiają do własnego pliku dane/wypis_profiles.json, więc
        # zapis nie rusza pozostałych ustawień programu.
        if not save_settings(self.profiles, active=active, auto=auto):
            QMessageBox.critical(
                self,
                "Nie udało się zapisać",
                "Program nie zdołał zapisać pliku ze wzorami:\n"
                f"{wypis_profiles_path()}\n\n"
                "Sprawdź, czy folder „dane” nie jest tylko do odczytu.",
            )
            return

        self._active_name = active
        self._auto = auto
        self.accept()
