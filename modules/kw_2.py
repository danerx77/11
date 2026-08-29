"""KW 2 – ręczne centrum pracy z Elektronicznymi Księgami Wieczystymi.

Ta zakładka celowo nie steruje stroną eKW, nie wykonuje zapytań do serwisu
ani nie automatyzuje pobierania. Ułatwia pracę w zwykłej przeglądarce:
porządkuje numery KW, kopiuje je do schowka i otwiera oficjalną stronę.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from utils.kw2_utils import collect_owner_kw_parcels, extract_kw_numbers


EKW_HOME_URL = "https://ekw.ms.gov.pl/"
STATE_FILE_NAME = "kw2_manual_state.json"
DRAFT_CONFIG_KEY = "kw2_manual_draft"


class KW2ManualWidget(QWidget):
    """Pomocnik do ręcznego przeglądania i zapisywania KW w zwykłej przeglądarce."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config if isinstance(config, dict) else {}
        self.owners: list[dict[str, Any]] = []
        self.project_path = ""
        self.manual_numbers: list[str] = []
        self.completed_numbers: set[str] = set()
        self._build_ui()
        self.input_edit.setPlainText(str(self.config.get(DRAFT_CONFIG_KEY, "") or ""))
        self._rebuild_table()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("📖 KW 2 — ręczne przeglądanie")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        self.btn_open_ekw = QPushButton("🌐 Otwórz eKW")
        self.btn_open_ekw.setToolTip(
            "Otwiera https://ekw.ms.gov.pl/ w domyślnej, zwykłej przeglądarce."
        )
        self.btn_open_ekw.clicked.connect(self._open_ekw)
        header.addWidget(self.btn_open_ekw)

        self.btn_open_pdf_folder = QPushButton("📂 Otwórz folder PDF")
        self.btn_open_pdf_folder.setToolTip(
            "Otwiera folder księgi_wieczyste_pdf aktywnego projektu."
        )
        self.btn_open_pdf_folder.clicked.connect(self._open_pdf_folder)
        header.addWidget(self.btn_open_pdf_folder)
        layout.addLayout(header)

        info = QLabel(
            "<b>Tryb ręczny:</b> zakładka nie łączy się z eKW i nie steruje stroną. "
            "Po skopiowaniu numeru otwiera wyłącznie oficjalną stronę w Twojej "
            "normalnej przeglądarce. Wyszukiwanie oraz zapis PDF wykonujesz tam ręcznie."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: #45647c; background: #eaf4ff; border-left: 4px solid #2b78c5; "
            "padding: 8px; border-radius: 4px;"
        )
        layout.addWidget(info)

        input_box = QGroupBox("Dodaj numery KW ręcznie")
        input_layout = QVBoxLayout(input_box)
        self.input_edit = QTextEdit()
        self.input_edit.setAcceptRichText(False)
        self.input_edit.setMaximumHeight(80)
        self.input_edit.setPlaceholderText(
            "Wklej numery, np. GD1G/00012345/6 — mogą być w osobnych wierszach, "
            "po przecinkach lub ze spacjami."
        )
        self.input_edit.textChanged.connect(self._remember_draft)
        input_layout.addWidget(self.input_edit)

        input_actions = QHBoxLayout()
        self.btn_add_numbers = QPushButton("➕ Dodaj numery do listy")
        self.btn_add_numbers.clicked.connect(self._add_numbers_from_input)
        input_actions.addWidget(self.btn_add_numbers)
        self.btn_paste_numbers = QPushButton("📋 Wklej ze schowka")
        self.btn_paste_numbers.clicked.connect(self._paste_from_clipboard)
        input_actions.addWidget(self.btn_paste_numbers)
        self.btn_clear_manual = QPushButton("🗑 Usuń ręcznie dodane")
        self.btn_clear_manual.clicked.connect(self._clear_manual_numbers)
        input_actions.addWidget(self.btn_clear_manual)
        input_actions.addStretch()
        input_layout.addLayout(input_actions)
        layout.addWidget(input_box)

        table_box = QGroupBox("Numery gotowe do ręcznego sprawdzenia")
        table_layout = QVBoxLayout(table_box)
        table_hint = QLabel(
            "Numery z modułu Wypisy są dodawane automatycznie. Zaznacz jeden lub "
            "więcej wierszy, aby skopiować je do schowka."
        )
        table_hint.setWordWrap(True)
        table_hint.setStyleSheet("color: #888; font-size: 11px;")
        table_layout.addWidget(table_hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Nr księgi wieczystej", "Powiązane działki", "Źródło", "Stan"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.doubleClicked.connect(lambda _index: self._copy_selected_numbers())
        header_view = self.table.horizontalHeader()
        header_view.setSectionsMovable(True)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table_layout.addWidget(self.table, 1)

        table_actions = QHBoxLayout()
        self.btn_copy = QPushButton("📋 Kopiuj zaznaczone")
        self.btn_copy.clicked.connect(self._copy_selected_numbers)
        table_actions.addWidget(self.btn_copy)
        self.btn_copy_open = QPushButton("📋🌐 Kopiuj i otwórz eKW")
        self.btn_copy_open.setObjectName("btn_primary")
        self.btn_copy_open.clicked.connect(self._copy_and_open_ekw)
        table_actions.addWidget(self.btn_copy_open)
        table_actions.addStretch()
        self.btn_mark_done = QPushButton("✓ Oznacz jako zapisane ręcznie")
        self.btn_mark_done.clicked.connect(lambda: self._mark_selected(True))
        table_actions.addWidget(self.btn_mark_done)
        self.btn_mark_pending = QPushButton("↺ Przywróć do pobrania")
        self.btn_mark_pending.clicked.connect(lambda: self._mark_selected(False))
        table_actions.addWidget(self.btn_mark_pending)
        table_layout.addLayout(table_actions)
        layout.addWidget(table_box, 1)

        self.status_label = QLabel("Wpisów: 0")
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)

    def set_project(self, project: dict) -> None:
        """Zmienia projekt i odtwarza jego lokalną listę ręcznie dodanych KW."""

        self.save_state()
        self.project_path = str((project or {}).get("path", "") or "")
        self.owners = []
        self._load_state()
        self._rebuild_table()

    def set_owners(self, owners: list) -> None:
        """Pobiera numery KW już obecne w danych właścicieli, bez Internetu."""

        self.owners = [owner for owner in (owners or []) if isinstance(owner, dict)]
        self._rebuild_table()

    def save_state(self) -> None:
        """Zapisuje wyłącznie lokalny stan listy dla aktywnego projektu."""

        draft = self.input_edit.toPlainText() if hasattr(self, "input_edit") else ""
        self.config[DRAFT_CONFIG_KEY] = draft
        state_file = self._state_file()
        if state_file is None:
            return

        state = {
            "manual_numbers": self.manual_numbers,
            "completed_numbers": sorted(self.completed_numbers),
            "draft": draft,
        }
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = state_file.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(state_file)
        except OSError as exc:
            self._set_status(f"Nie udało się zapisać stanu KW 2: {exc}")

    def _state_file(self) -> Path | None:
        if not self.project_path:
            return None
        return Path(self.project_path) / STATE_FILE_NAME

    def _load_state(self) -> None:
        self.manual_numbers = []
        self.completed_numbers = set()
        state_file = self._state_file()
        state: dict[str, Any] = {}

        if state_file is not None and state_file.is_file():
            try:
                parsed = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    state = parsed
            except (OSError, ValueError, TypeError):
                state = {}

        self.manual_numbers = extract_kw_numbers(state.get("manual_numbers", []))
        self.completed_numbers = set(extract_kw_numbers(state.get("completed_numbers", [])))
        draft = state.get("draft", self.config.get(DRAFT_CONFIG_KEY, ""))
        self.input_edit.blockSignals(True)
        self.input_edit.setPlainText(str(draft or ""))
        self.input_edit.blockSignals(False)
        self.config[DRAFT_CONFIG_KEY] = self.input_edit.toPlainText()

    def _build_records(self) -> list[dict[str, str]]:
        owner_records = collect_owner_kw_parcels(self.owners)
        manual_set = set(self.manual_numbers)
        records: list[dict[str, str]] = []

        for number, parcels in owner_records.items():
            source = "Wypisy + ręcznie" if number in manual_set else "Wypisy"
            records.append(
                {
                    "number": number,
                    "parcels": ", ".join(parcels) if parcels else "—",
                    "source": source,
                }
            )

        for number in self.manual_numbers:
            if number not in owner_records:
                records.append(
                    {"number": number, "parcels": "—", "source": "Wpis ręczny"}
                )

        return records

    def _rebuild_table(self) -> None:
        if not hasattr(self, "table"):
            return

        selected_numbers = set(self._selected_numbers())
        records = self._build_records()
        available_numbers = {record["number"] for record in records}
        # Podczas zmiany projektu główne okno na chwilę przekazuje pustą
        # listę właścicieli. Nie usuwaj wtedy ręcznie oznaczonych statusów;
        # zostaną pokazane ponownie po wczytaniu danych projektu.
        completed_on_list = self.completed_numbers.intersection(available_numbers)

        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        for row, record in enumerate(records):
            self.table.insertRow(row)
            number = record["number"]
            number_item = QTableWidgetItem(number)
            number_item.setData(Qt.ItemDataRole.UserRole, number)
            self.table.setItem(row, 0, number_item)
            self.table.setItem(row, 1, QTableWidgetItem(record["parcels"]))
            self.table.setItem(row, 2, QTableWidgetItem(record["source"]))

            is_done = number in self.completed_numbers
            status_item = QTableWidgetItem(
                "Zapisano ręcznie" if is_done else "Do ręcznego sprawdzenia"
            )
            status_item.setForeground(QColor("#2ecc71" if is_done else "#e69f00"))
            self.table.setItem(row, 3, status_item)
            if number in selected_numbers:
                self.table.selectRow(row)
        self.table.setUpdatesEnabled(True)
        self._set_status(
            f"Wpisów: {len(records)} • zapisanych ręcznie: "
            f"{len(completed_on_list)}"
        )

    def _selected_numbers(self) -> list[str]:
        selection_model = self.table.selectionModel() if hasattr(self, "table") else None
        if selection_model is None:
            return []

        result: list[str] = []
        for model_index in selection_model.selectedRows(0):
            item = self.table.item(model_index.row(), 0)
            if item is None:
                continue
            number = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
            if number and number not in result:
                result.append(number)
        return result

    def _remember_draft(self) -> None:
        self.config[DRAFT_CONFIG_KEY] = self.input_edit.toPlainText()

    def _paste_from_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        if not text.strip():
            self._set_status("Schowek nie zawiera tekstu z numerami KW.")
            return
        self.input_edit.insertPlainText(text)
        self.input_edit.setFocus()

    def _add_numbers_from_input(self) -> None:
        numbers = extract_kw_numbers(self.input_edit.toPlainText())
        if not numbers:
            QMessageBox.information(
                self,
                "Brak poprawnych numerów",
                "Wpisz pełny numer KW, np. GD1G/00012345/6.",
            )
            return

        existing = set(self.manual_numbers)
        added = [number for number in numbers if number not in existing]
        self.manual_numbers.extend(added)
        self.input_edit.clear()
        self._rebuild_table()
        self.save_state()
        self._set_status(f"Dodano ręcznie: {len(added)} numerów KW.")

    def _clear_manual_numbers(self) -> None:
        if not self.manual_numbers:
            self._set_status("Brak ręcznie dodanych numerów do usunięcia.")
            return

        answer = QMessageBox.question(
            self,
            "Usunąć ręcznie dodane numery?",
            "Numery pochodzące z Wypisów pozostaną na liście. Usunąć tylko wpisy ręczne?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.manual_numbers = []
        self.input_edit.clear()
        self._rebuild_table()
        self.save_state()

    def _copy_selected_numbers(self) -> bool:
        numbers = self._selected_numbers()
        if not numbers:
            QMessageBox.information(
                self,
                "Brak zaznaczenia",
                "Zaznacz co najmniej jeden wiersz z numerem KW.",
            )
            return False

        QGuiApplication.clipboard().setText("\n".join(numbers))
        self._set_status(
            f"Skopiowano do schowka: {len(numbers)} "
            f"{'numer' if len(numbers) == 1 else 'numery'} KW."
        )
        return True

    def _copy_and_open_ekw(self) -> None:
        if self._copy_selected_numbers():
            self._open_ekw()

    def _open_ekw(self) -> None:
        opened = QDesktopServices.openUrl(QUrl(EKW_HOME_URL))
        if opened:
            self._set_status("Otwarto eKW w domyślnej przeglądarce.")
        else:
            QMessageBox.warning(
                self,
                "Nie udało się otworzyć strony",
                f"Otwórz ręcznie w przeglądarce: {EKW_HOME_URL}",
            )

    def _open_pdf_folder(self) -> None:
        if not self.project_path:
            QMessageBox.information(
                self,
                "Brak projektu",
                "Najpierw wybierz aktywny projekt.",
            )
            return

        folder = Path(self.project_path) / "ksiegi_wieczyste_pdf"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Nie udało się otworzyć folderu",
                f"Nie można utworzyć folderu PDF: {exc}",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _mark_selected(self, completed: bool) -> None:
        numbers = self._selected_numbers()
        if not numbers:
            QMessageBox.information(
                self,
                "Brak zaznaczenia",
                "Zaznacz co najmniej jeden wiersz z numerem KW.",
            )
            return

        if completed:
            self.completed_numbers.update(numbers)
        else:
            self.completed_numbers.difference_update(numbers)
        self._rebuild_table()
        self.save_state()

    def _set_status(self, text: str) -> None:
        if hasattr(self, "status_label"):
            self.status_label.setText(text)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.save_state()
        super().closeEvent(event)
