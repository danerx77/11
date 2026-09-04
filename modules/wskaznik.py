"""Moduł Wskaźnik – lista działek wraz z ich identyfikatorami ewidencyjnymi.

Moduł pozwala:

* zebrać działki z listy projektu i z wypisów,
* wkleić albo wczytać z pliku TXT/CSV listę działek z identyfikatorami,
* przefiltrować widok wklejoną listą działek (np. ``1/1, 1/2``),
* uzupełnić brakujące identyfikatory ręcznie,
* wyeksportować lub skopiować gotowe zestawienie.

Cała logika danych mieszka w :mod:`utils.parcel_indicators`, dzięki czemu jest
pokryta testami bez uruchamiania Qt. Tutaj zostaje wyłącznie warstwa okna.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication
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
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils.parcel_indicators import (
    INDICATOR_FIELDS,
    filter_indicator_rows,
    format_indicator_export,
    indicator_rows_from_owners,
    indicator_rows_from_parcels,
    indicator_rows_from_project,
    indicator_summary,
    make_indicator_row,
    merge_indicator_rows,
    parse_indicator_text,
    sort_indicator_rows,
)

STATE_FILE_NAME = "wskaznik_state.json"

COLUMNS = (
    ("number", "Nr działki", 120),
    ("identifier", "Identyfikator działki", 260),
    ("precinct", "Obręb", 150),
    ("precinct_number", "Nr obrębu", 90),
    ("municipality", "Jednostka ewidencyjna", 180),
    ("county", "Powiat", 140),
    ("voivodeship", "Województwo", 140),
    ("note", "Notatka", 200),
)


class IndicatorImportDialog(QDialog):
    """Okno wklejania listy działek z identyfikatorami."""

    def __init__(self, parent=None, initial_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Wklej listę działek z identyfikatorami")
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Wklej dane w dowolnym z formatów:\n"
            "  1/2   221001_1.0001.1/2\n"
            "  1/2;221001_1.0001.1/2;Polki\n"
            "  221001_1.0001.1/2            (sam identyfikator — numer działki "
            "zostanie z niego odczytany)\n\n"
            "Kolumny można rozdzielać tabulatorem, średnikiem, pionową kreską, "
            "znakiem = lub dwiema spacjami.\n"
            "Wiersze zaczynające się od # są pomijane."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted_hint")
        layout.addWidget(hint)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("1/2  221001_1.0001.1/2")
        self.text_edit.setPlainText(initial_text)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_edit.setFont(font)
        layout.addWidget(self.text_edit, 1)

        self.chk_replace = QCheckBox(
            "Zastąp obecną listę zamiast dopisywać do niej"
        )
        layout.addWidget(self.chk_replace)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Wczytaj")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self.text_edit.toPlainText()

    def replace_existing(self) -> bool:
        return self.chk_replace.isChecked()


class ParcelIndicatorWidget(QWidget):
    """Zakładka „Wskaźnik”: działki i przypisane im identyfikatory."""

    rows_changed = Signal(list)

    FILTER_KEY = "wskaznik_filter_text"
    SEARCH_KEY = "wskaznik_search_text"
    SORT_KEY = "wskaznik_sort_column"
    ONLY_MISSING_KEY = "wskaznik_only_missing"

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.rows: list[dict] = []
        self.project_path = ""
        self._project_parcels: list = []
        self._owners: list = []
        self._visible_rows: list[dict] = []
        self._loading = False

        self._build_ui()
        self._restore_state()

    # ──────────────────────────────────────────────────────────────
    # Budowa okna
    # ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("🔢 Wskaźnik — identyfikatory działek")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        info = QLabel(
            "Zestawienie działek i ich identyfikatorów ewidencyjnych. "
            "Wklej listę działek w polu filtra, aby zobaczyć tylko wybrane "
            "pozycje. Dane możesz wczytać z pliku TXT/CSV, wkleić ze schowka "
            "albo pobrać z listy działek i wypisów."
        )
        info.setWordWrap(True)
        info.setObjectName("info_banner")
        layout.addWidget(info)

        layout.addWidget(self._build_source_box())
        layout.addWidget(self._build_filter_box())

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("wskaznik_table")
        self.table.setHorizontalHeaderLabels([label for _, label, _ in COLUMNS])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setSortingEnabled(False)
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        for index, (_, _, width) in enumerate(COLUMNS):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(index, width)
        header.setStretchLastSection(True)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        layout.addWidget(self._build_actions_box())

        self.lbl_summary = QLabel("Brak działek na liście.")
        self.lbl_summary.setWordWrap(True)
        layout.addWidget(self.lbl_summary)

    def _build_source_box(self) -> QGroupBox:
        box = QGroupBox("Skąd wziąć dane")
        row = QHBoxLayout(box)

        self.btn_from_parcels = QPushButton("📋 Pobierz z listy działek")
        self.btn_from_parcels.setToolTip(
            "Dodaje wszystkie działki z zakładki „Lista działek”. "
            "Istniejące identyfikatory nie są kasowane."
        )
        self.btn_from_parcels.clicked.connect(self._load_from_project_parcels)
        row.addWidget(self.btn_from_parcels)

        self.btn_from_owners = QPushButton("👥 Uzupełnij z wypisów")
        self.btn_from_owners.setToolTip(
            "Odczytuje identyfikatory i obręby z danych właścicieli "
            "zaimportowanych w zakładce Wypisy."
        )
        self.btn_from_owners.clicked.connect(self._load_from_owners)
        row.addWidget(self.btn_from_owners)

        self.btn_import_file = QPushButton("📂 Wczytaj plik TXT/CSV")
        self.btn_import_file.setToolTip(
            "Wczytuje listę działek z identyfikatorami z pliku tekstowego."
        )
        self.btn_import_file.clicked.connect(self._import_file)
        row.addWidget(self.btn_import_file)

        self.btn_paste = QPushButton("📥 Wklej listę")
        self.btn_paste.setToolTip(
            "Otwiera okno, w którym można wkleić działki z identyfikatorami."
        )
        self.btn_paste.clicked.connect(self._paste_list)
        row.addWidget(self.btn_paste)

        row.addStretch()
        return box

    def _build_filter_box(self) -> QGroupBox:
        box = QGroupBox("Filtr działek")
        outer = QVBoxLayout(box)

        first = QHBoxLayout()
        first.addWidget(QLabel("Pokaż tylko działki:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            "np. 1/1, 1/2, 15  — wklej listę działek oddzieloną przecinkami"
        )
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        first.addWidget(self.filter_edit, 1)

        self.btn_paste_filter = QPushButton("📋 Wklej ze schowka")
        self.btn_paste_filter.clicked.connect(self._paste_filter_from_clipboard)
        first.addWidget(self.btn_paste_filter)

        self.btn_clear_filter = QPushButton("✖ Wyczyść filtr")
        self.btn_clear_filter.clicked.connect(self.filter_edit.clear)
        first.addWidget(self.btn_clear_filter)
        outer.addLayout(first)

        second = QHBoxLayout()
        second.addWidget(QLabel("Szukaj w tabeli:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "fragment numeru, identyfikatora, obrębu lub notatki"
        )
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_filter_changed)
        second.addWidget(self.search_edit, 1)

        self.chk_only_missing = QCheckBox("Tylko bez identyfikatora")
        self.chk_only_missing.setToolTip(
            "Pokazuje wyłącznie działki, którym brakuje identyfikatora."
        )
        self.chk_only_missing.toggled.connect(self._on_filter_changed)
        second.addWidget(self.chk_only_missing)

        second.addWidget(QLabel("Sortuj wg:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Numeru działki (naturalnie)", "number")
        self.sort_combo.addItem("Identyfikatora", "identifier")
        self.sort_combo.addItem("Obrębu", "precinct")
        self.sort_combo.addItem("Jednostki ewidencyjnej", "municipality")
        self.sort_combo.currentIndexChanged.connect(self._on_filter_changed)
        second.addWidget(self.sort_combo)
        outer.addLayout(second)

        self.lbl_missing = QLabel("")
        self.lbl_missing.setWordWrap(True)
        self.lbl_missing.setStyleSheet("color: #e67e22;")
        self.lbl_missing.hide()
        outer.addWidget(self.lbl_missing)

        return box

    def _build_actions_box(self) -> QGroupBox:
        box = QGroupBox("Operacje na liście")
        row = QHBoxLayout(box)

        self.btn_add_row = QPushButton("➕ Dodaj wiersz")
        self.btn_add_row.clicked.connect(self._add_empty_row)
        row.addWidget(self.btn_add_row)

        self.btn_delete_rows = QPushButton("🗑️ Usuń zaznaczone")
        self.btn_delete_rows.clicked.connect(self._delete_selected_rows)
        row.addWidget(self.btn_delete_rows)

        self.btn_copy = QPushButton("📋 Kopiuj widok")
        self.btn_copy.setToolTip(
            "Kopiuje widoczne wiersze do schowka (numer i identyfikator)."
        )
        self.btn_copy.clicked.connect(self._copy_visible)
        row.addWidget(self.btn_copy)

        self.btn_copy_identifiers = QPushButton("🔢 Kopiuj identyfikatory")
        self.btn_copy_identifiers.setToolTip(
            "Kopiuje same identyfikatory widocznych działek, po jednym w wierszu."
        )
        self.btn_copy_identifiers.clicked.connect(self._copy_identifiers)
        row.addWidget(self.btn_copy_identifiers)

        self.btn_export = QPushButton("💾 Eksportuj widok")
        self.btn_export.setToolTip("Zapisuje widoczne wiersze do pliku TXT lub CSV.")
        self.btn_export.clicked.connect(self._export_visible)
        row.addWidget(self.btn_export)

        self.btn_clear_all = QPushButton("♻️ Wyczyść listę")
        self.btn_clear_all.setObjectName("btn_danger")
        self.btn_clear_all.clicked.connect(self._clear_all)
        row.addWidget(self.btn_clear_all)

        row.addStretch()
        return box

    # ──────────────────────────────────────────────────────────────
    # Dane wejściowe z innych modułów
    # ──────────────────────────────────────────────────────────────
    def set_parcels(self, parcels: list):
        """Zapamiętuje aktualną listę działek projektu."""
        self._project_parcels = list(parcels or [])

    def set_owners(self, owners: list):
        """Zapamiętuje właścicieli z wypisów (źródło identyfikatorów)."""
        self._owners = list(owners or [])

    def set_project(self, project: dict):
        self.project_path = str((project or {}).get("path", "") or "")
        self._load_from_project_state()

    def get_rows(self) -> list[dict]:
        return self.rows

    # ──────────────────────────────────────────────────────────────
    # Wczytywanie danych
    # ──────────────────────────────────────────────────────────────
    def _merge_rows(self, new_rows: list[dict], *, replace: bool = False) -> tuple[int, int]:
        if replace:
            self.rows = [make_indicator_row(row) for row in new_rows]
            added, updated = len(self.rows), 0
        else:
            self.rows, added, updated = merge_indicator_rows(self.rows, new_rows)
        self._after_change()
        return added, updated

    def _load_from_project_parcels(self):
        if not self._project_parcels:
            return QMessageBox.information(
                self,
                "Brak działek",
                "Lista działek projektu jest pusta. "
                "Uzupełnij ją w zakładce „Lista działek”.",
            )
        # Sama lista działek nie zna identyfikatorów — te są w Wypisach,
        # więc od razu łączymy oba źródła.
        added, updated = self._merge_rows(
            indicator_rows_from_project(self._project_parcels, self._owners)
        )
        with_identifier = sum(1 for row in self.rows if row.get("identifier"))
        missing = len(self.rows) - with_identifier
        message = (
            f"Dodano nowych działek: {added}\n"
            f"Uzupełniono istniejących: {updated}\n"
            f"Z identyfikatorem: {with_identifier}"
        )
        if missing:
            message += (
                f"\nBez identyfikatora: {missing}"
                "\n\nBrakujące dane znajdziesz w wypisach — wczytaj je "
                "w zakładce „Wypisy”, a potem kliknij „Uzupełnij z wypisów”."
            )
        QMessageBox.information(self, "Lista działek", message)

    def _load_from_owners(self):
        if not self._owners:
            return QMessageBox.information(
                self,
                "Brak wypisów",
                "Nie ma zaimportowanych właścicieli. "
                "Wczytaj wypis w zakładce „Wypisy”.",
            )
        rows = indicator_rows_from_owners(self._owners)
        if not rows:
            return QMessageBox.information(
                self,
                "Brak danych",
                "W danych właścicieli nie znaleziono numerów działek.",
            )
        added, updated = self._merge_rows(rows)
        QMessageBox.information(
            self,
            "Dane z wypisów",
            f"Dodano nowych działek: {added}\nUzupełniono istniejących: {updated}",
        )

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik z listą działek",
            "",
            "Pliki tekstowe (*.txt *.csv *.tsv);;Wszystkie pliki (*.*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = Path(path).read_text(encoding="cp1250")
            except Exception as exc:
                return QMessageBox.critical(
                    self, "Błąd odczytu", f"Nie udało się odczytać pliku:\n{exc}"
                )
        except Exception as exc:
            return QMessageBox.critical(
                self, "Błąd odczytu", f"Nie udało się odczytać pliku:\n{exc}"
            )

        rows = parse_indicator_text(text)
        if not rows:
            return QMessageBox.warning(
                self,
                "Pusty plik",
                "W pliku nie znaleziono numerów działek ani identyfikatorów.",
            )
        added, updated = self._merge_rows(rows)
        QMessageBox.information(
            self,
            "Import zakończony",
            f"Plik: {Path(path).name}\n"
            f"Dodano nowych działek: {added}\n"
            f"Uzupełniono istniejących: {updated}",
        )

    def _paste_list(self):
        dialog = IndicatorImportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        rows = parse_indicator_text(dialog.text())
        if not rows:
            return QMessageBox.warning(
                self,
                "Brak danych",
                "We wklejonym tekście nie znaleziono numerów działek.",
            )
        added, updated = self._merge_rows(rows, replace=dialog.replace_existing())
        QMessageBox.information(
            self,
            "Wczytano listę",
            f"Dodano nowych działek: {added}\nUzupełniono istniejących: {updated}",
        )

    def _paste_filter_from_clipboard(self):
        text = QGuiApplication.clipboard().text()
        if text.strip():
            self.filter_edit.setText(" ".join(text.split()))

    # ──────────────────────────────────────────────────────────────
    # Edycja
    # ──────────────────────────────────────────────────────────────
    def _add_empty_row(self):
        self.rows.append(make_indicator_row())
        self._after_change()
        # Nowy wiersz jest pusty, więc filtr mógłby go ukryć — czyścimy filtr.
        if self.filter_edit.text().strip():
            self.filter_edit.clear()
        if self.table.rowCount():
            last = self.table.rowCount() - 1
            self.table.setCurrentCell(last, 0)
            self.table.editItem(self.table.item(last, 0))

    def _delete_selected_rows(self):
        selected = sorted({index.row() for index in self.table.selectedIndexes()})
        if not selected:
            return QMessageBox.information(
                self, "Brak zaznaczenia", "Zaznacz wiersze, które chcesz usunąć."
            )
        targets = {
            id(self._visible_rows[row])
            for row in selected
            if 0 <= row < len(self._visible_rows)
        }
        if not targets:
            return
        reply = QMessageBox.question(
            self,
            "Usuń działki",
            f"Usunąć zaznaczone wiersze ({len(targets)}) z listy wskaźnika?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.rows = [row for row in self.rows if id(row) not in targets]
        self._after_change()

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._loading:
            return
        row_index = item.row()
        if not (0 <= row_index < len(self._visible_rows)):
            return
        field = COLUMNS[item.column()][0]
        record = self._visible_rows[row_index]
        record[field] = " ".join(item.text().split())
        if field == "identifier":
            # Numer i obręb da się odczytać wprost z identyfikatora.
            refreshed = make_indicator_row(record)
            record.update(refreshed)
        self._save_to_project_state()
        self._update_summary()
        self.rows_changed.emit(self.rows)

    def _clear_all(self):
        if not self.rows:
            return
        reply = QMessageBox.question(
            self,
            "Wyczyść listę",
            "Usunąć wszystkie działki z modułu Wskaźnik?\n"
            "Lista działek projektu i wypisy pozostaną nietknięte.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.rows = []
            self._after_change()

    # ──────────────────────────────────────────────────────────────
    # Eksport
    # ──────────────────────────────────────────────────────────────
    def _copy_visible(self):
        if not self._visible_rows:
            return QMessageBox.information(self, "Pusto", "Nie ma czego kopiować.")
        text = format_indicator_export(
            self._visible_rows,
            columns=("number", "identifier"),
            separator="\t",
        )
        QGuiApplication.clipboard().setText(text)
        self._flash_summary(f"Skopiowano wierszy: {len(self._visible_rows)}")

    def _copy_identifiers(self):
        identifiers = [
            row["identifier"] for row in self._visible_rows if row.get("identifier")
        ]
        if not identifiers:
            return QMessageBox.information(
                self, "Brak identyfikatorów", "Widoczne działki nie mają identyfikatorów."
            )
        QGuiApplication.clipboard().setText("\n".join(identifiers))
        self._flash_summary(f"Skopiowano identyfikatorów: {len(identifiers)}")

    def _export_visible(self):
        if not self._visible_rows:
            return QMessageBox.information(self, "Pusto", "Nie ma czego zapisać.")
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Zapisz zestawienie wskaźnika",
            "wskaznik_dzialek.csv",
            "Plik CSV (*.csv);;Plik tekstowy (*.txt)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv") or "CSV" in selected_filter:
                with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.writer(handle, delimiter=";")
                    writer.writerow([label for _, label, _ in COLUMNS])
                    for row in self._visible_rows:
                        writer.writerow([row.get(field, "") for field, _, _ in COLUMNS])
            else:
                text = format_indicator_export(
                    self._visible_rows,
                    columns=[field for field, _, _ in COLUMNS],
                    separator="\t",
                    header=True,
                )
                Path(path).write_text(text + "\n", encoding="utf-8")
        except Exception as exc:
            return QMessageBox.critical(
                self, "Błąd zapisu", f"Nie udało się zapisać pliku:\n{exc}"
            )
        QMessageBox.information(
            self, "Zapisano", f"Zapisano {len(self._visible_rows)} wierszy do:\n{path}"
        )

    # ──────────────────────────────────────────────────────────────
    # Widok
    # ──────────────────────────────────────────────────────────────
    def _on_filter_changed(self, *_):
        self._store_state()
        self._refresh_table()

    def _after_change(self):
        self._save_to_project_state()
        self._refresh_table()
        self.rows_changed.emit(self.rows)

    def _refresh_table(self):
        visible, missing = filter_indicator_rows(
            self.rows,
            self.filter_edit.text(),
            search_text=self.search_edit.text(),
        )
        # filter_indicator_rows zwraca kopie wierszy. Podmieniamy je na
        # oryginalne słowniki, aby edycja komórki zmieniała dane modułu,
        # a nie ich chwilową kopię.
        by_key: dict[tuple, list[dict]] = {}
        for row in self.rows:
            by_key.setdefault(self._row_key(row), []).append(row)

        resolved: list[dict] = []
        used: set[int] = set()
        for row in visible:
            candidates = by_key.get(self._row_key(row), [])
            for candidate in candidates:
                if id(candidate) not in used:
                    used.add(id(candidate))
                    resolved.append(candidate)
                    break
            else:
                resolved.append(row)

        if self.chk_only_missing.isChecked():
            resolved = [row for row in resolved if not row.get("identifier")]

        sort_field = self.sort_combo.currentData() or "number"
        ordered_copies = sort_indicator_rows(resolved, key=sort_field)
        order = {self._row_key(row): index for index, row in enumerate(ordered_copies)}
        resolved.sort(key=lambda row: order.get(self._row_key(row), 0))

        self._visible_rows = resolved
        self._fill_table(resolved)
        self._update_summary(missing)

    @staticmethod
    def _row_key(row) -> tuple:
        return tuple(str(row.get(field, "")) for field in INDICATOR_FIELDS)

    def _fill_table(self, rows: list[dict]):
        self._loading = True
        try:
            self.table.setRowCount(0)
            for row in rows:
                index = self.table.rowCount()
                self.table.insertRow(index)
                for column, (field, _, _) in enumerate(COLUMNS):
                    item = QTableWidgetItem(str(row.get(field, "")))
                    if field == "identifier":
                        if row.get("identifier"):
                            item.setForeground(QColor("#2ecc71"))
                            item.setFont(QFont("", -1, QFont.Weight.Bold))
                        else:
                            item.setForeground(QColor("#e67e22"))
                            item.setText("")
                            item.setToolTip("Brak identyfikatora — uzupełnij ręcznie.")
                    if field == "number":
                        item.setFont(QFont("", -1, QFont.Weight.Bold))
                    self.table.setItem(index, column, item)
        finally:
            self._loading = False

    def _update_summary(self, missing: list | None = None):
        stats = indicator_summary(self._visible_rows, missing or [])
        parts = [
            f"Widoczne działki: {stats['total']} (na liście: {len(self.rows)})",
            f"z identyfikatorem: {stats['with_identifier']}",
        ]
        if stats["without_identifier"]:
            parts.append(f"bez identyfikatora: {len(stats['without_identifier'])}")
        if stats["duplicate_identifiers"]:
            parts.append(
                "powtórzone identyfikatory: "
                + ", ".join(stats["duplicate_identifiers"][:5])
            )
        self.lbl_summary.setText(" • ".join(parts))

        if stats["missing"]:
            shown = ", ".join(stats["missing"][:20])
            suffix = " …" if len(stats["missing"]) > 20 else ""
            self.lbl_missing.setText(
                f"Nie znaleziono na liście {len(stats['missing'])} działek "
                f"z filtra: {shown}{suffix}"
            )
            self.lbl_missing.show()
        else:
            self.lbl_missing.hide()

    def _flash_summary(self, message: str):
        self.lbl_summary.setText(message)

    # ──────────────────────────────────────────────────────────────
    # Trwałość
    # ──────────────────────────────────────────────────────────────
    def _store_state(self):
        self.config[self.FILTER_KEY] = self.filter_edit.text()
        self.config[self.SEARCH_KEY] = self.search_edit.text()
        self.config[self.SORT_KEY] = self.sort_combo.currentData() or "number"
        self.config[self.ONLY_MISSING_KEY] = self.chk_only_missing.isChecked()

    def _restore_state(self):
        self._loading = True
        try:
            self.filter_edit.setText(str(self.config.get(self.FILTER_KEY, "")))
            self.search_edit.setText(str(self.config.get(self.SEARCH_KEY, "")))
            sort_field = str(self.config.get(self.SORT_KEY, "number"))
            index = self.sort_combo.findData(sort_field)
            if index >= 0:
                self.sort_combo.setCurrentIndex(index)
            self.chk_only_missing.setChecked(
                bool(self.config.get(self.ONLY_MISSING_KEY, False))
            )
        finally:
            self._loading = False
        self._refresh_table()

    def _state_file(self) -> Path | None:
        path = self.project_path or str(self.config.get("last_project_path", "") or "")
        if not path:
            return None
        return Path(path) / STATE_FILE_NAME

    def _save_to_project_state(self):
        state_file = self._state_file()
        if state_file is None:
            return
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(state_file, "w", encoding="utf-8") as handle:
                json.dump(self.rows, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_from_project_state(self):
        self.rows = []
        state_file = self._state_file()
        if state_file is not None and state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, list):
                    self.rows = [
                        make_indicator_row(row)
                        for row in data
                        if isinstance(row, dict)
                    ]
            except Exception:
                self.rows = []
        self._refresh_table()

    def save_state(self):
        """Publiczne zapisanie stanu — wywoływane przez główne okno."""
        self._save_to_project_state()
