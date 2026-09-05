"""Okno „Wzory odczytu wypisów (PDF)”.

Pozwala wczytać przykładowy wypis, zobaczyć **co program z niego
odczytał i po jakiej etykiecie**, a następnie poprawić przypisania dla
dokumentów o innej budowie. Ustawienia zapisują się jako profil, więc
kolejny wypis z tego samego urzędu odczyta się już poprawnie.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
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
)

STATUS_COLORS = {
    "ok": "#2ecc71",
    "found": "#f1c40f",
    "missing": "#e74c3c",
}

STATUS_TEXTS = {
    "ok": "✅ odczytano",
    "found": "⚠️ etykieta jest, brak wartości",
    "missing": "❌ nie znaleziono",
}


class WypisProfileDialog(QDialog):
    """Kreator wzorów odczytu wypisów."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self.setWindowTitle("Wzory odczytu wypisów (PDF)")
        self.resize(1180, 780)

        settings = load_settings(self.config)
        self.profiles = settings["profiles"]
        self._active_name = settings["active"]
        self._auto = settings["auto"]
        self.pdf_text = ""
        self.pdf_path = ""
        self._loading = False

        self._build_ui()
        self._reload_profile_combo()

    # ── Budowa okna ──────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Wczytaj przykładowy wypis, a program pokaże, <b>co odczytał i po "
            "jakiej etykiecie</b>. Jeśli Twój urząd używa innych nazw pól, "
            "dopisz je w kolumnie „Etykiety w PDF” i zapisz jako nowy wzór — "
            "kolejne wypisy z tego urzędu odczytają się już poprawnie."
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
            ["Pole w programie", "Etykiety w PDF", "Rozpoznano", "Odczytana wartość"]
        )
        self.table.horizontalHeaderItem(1).setToolTip(
            "Nazwy pól używane w Twoim PDF. Kilka wariantów oddziel średnikiem."
        )
        self.table.setColumnWidth(1, 230)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_label_edited)
        fields_layout.addWidget(self.table)

        self.lbl_summary = QLabel("Wczytaj PDF, aby zobaczyć wynik odczytu.")
        self.lbl_summary.setWordWrap(True)
        fields_layout.addWidget(self.lbl_summary)

        hint = QLabel(
            "Jak poprawić odczyt: kliknij wiersz w tabeli, zaznacz w tekście "
            "po prawej właściwą nazwę pola i użyj przycisku „⬅️ Użyj "
            "zaznaczenia jako etykiety”. Możesz też wpisać etykiety wprost "
            "w kolumnie „Etykiety w PDF”, oddzielając je średnikami."
        )
        hint.setObjectName("muted_hint")
        hint.setWordWrap(True)
        fields_layout.addWidget(hint)
        splitter.addWidget(fields_box)

        text_box = QGroupBox("Tekst wczytanego dokumentu")
        text_layout = QVBoxLayout(text_box)
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText(
            "Tu pojawi się tekst wypisu. Zaznacz w nim fragment i kliknij "
            "„Użyj zaznaczenia jako etykiety”, aby szybko przypisać pole."
        )
        text_layout.addWidget(self.text_view)

        use_row = QHBoxLayout()
        btn_use = QPushButton("⬅️ Użyj zaznaczenia jako etykiety")
        btn_use.setToolTip(
            "Zaznacz w tekście nazwę pola (np. „Adres nieruchomości”) i "
            "przypisz ją do wiersza wybranego w tabeli po lewej."
        )
        btn_use.clicked.connect(self._use_selection_as_label)
        use_row.addWidget(btn_use)
        use_row.addStretch()
        text_layout.addLayout(use_row)

        splitter.addWidget(text_box)
        splitter.setSizes([680, 480])
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

        self.table.setRowCount(len(FIELD_KEYS))
        for row, (key, label, hint) in enumerate(FIELD_DEFS):
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

            for column in (2, 3):
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)

        self._loading = False
        self.table.resizeRowsToContents()
        if self.pdf_text:
            self._analyze()

    def _store_markers(self):
        index = self._current_index()
        if index < 0:
            return
        markers = [m.strip() for m in self.markers_edit.text().split(";") if m.strip()]
        self.profiles[index]["markers"] = markers

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
        if self._loading or item.column() != 1:
            return
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
            import fitz

            with fitz.open(path) as doc:
                pages = [page.get_text() for page in doc]
            self.pdf_text = "\n".join(pages)
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

        if self.chk_auto.isChecked():
            self._detect_for_loaded(silent=True)
        else:
            self._analyze()
        return True

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

            # Komórki tworzymy tylko raz — ponowne setItem() na istniejącym
            # elemencie Qt zgłasza ostrzeżenie o zmianie właściciela.
            status_item = self.table.item(row, 2)
            if status_item is None:
                status_item = QTableWidgetItem()
                status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 2, status_item)
            status_item.setText(STATUS_TEXTS.get(status, ""))
            status_item.setForeground(QColor(STATUS_COLORS.get(status, "#cccccc")))
            status_item.setToolTip(
                f"Dopasowano etykietę: {data['matched_label']}"
                if data.get("matched_label")
                else ""
            )

            value_item = self.table.item(row, 3)
            if value_item is None:
                value_item = QTableWidgetItem()
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 3, value_item)
            value_item.setText(data.get("value", ""))
            value_item.setFont(QFont("", -1, QFont.Weight.Bold if status == "ok" else QFont.Weight.Normal))
        self._loading = False

        self.lbl_summary.setText(summarize(rows.values()))
        self.table.resizeRowsToContents()

    def _use_selection_as_label(self):
        selection = self.text_view.textCursor().selectedText().strip()
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
            current.insert(0, label)
        self.table.setItem(row, 1, QTableWidgetItem("; ".join(current)))
        self._store_table_into_profile()
        self._analyze()

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
