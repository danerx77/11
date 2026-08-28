"""Samodzielny moduł do naturalnego sortowania numerów działek."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils.parcel_sorting import parse_parcel_list, sort_parcel_numbers


class ParcelSortingWidget(QWidget):
    """Pozwala wkleić listę numerów działek i uporządkować ją rosnąco."""

    INPUT_KEY = "parcel_sorter_input"
    RESULT_KEY = "parcel_sorter_result"
    UNIQUE_KEY = "parcel_sorter_remove_duplicates"

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._project_parcels: list = []
        self._build_ui()
        self._restore_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("↕️ Sortowanie numerów działek")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        self.chk_remove_duplicates = QCheckBox("Usuń powtórzenia")
        header.addWidget(self.chk_remove_duplicates)
        layout.addLayout(header)

        hint = QLabel(
            "Wpisz lub wklej numery rozdzielone nowymi wierszami, tabulatorami, "
            "przecinkami albo średnikami. Numery są sortowane naturalnie, np. "
            "1, 1/2, 1/10, 2, 10."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        input_box = QGroupBox("Lista do posortowania")
        input_layout = QVBoxLayout(input_box)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("np.\n12/10\n2\n12/3\n1")
        self.input_edit.setMinimumWidth(300)
        input_layout.addWidget(self.input_edit, 1)

        input_buttons = QHBoxLayout()
        self.btn_paste = QPushButton("📋 Wklej ze schowka")
        self.btn_paste.clicked.connect(self._paste_from_clipboard)
        input_buttons.addWidget(self.btn_paste)
        self.btn_load_project = QPushButton("📥 Wczytaj działki projektu")
        self.btn_load_project.setToolTip(
            "Wstawia numery z aktywnej zakładki Lista Działek."
        )
        self.btn_load_project.clicked.connect(self._load_project_parcels)
        input_buttons.addWidget(self.btn_load_project)
        input_buttons.addStretch()
        self.btn_clear = QPushButton("🗑 Wyczyść")
        self.btn_clear.clicked.connect(self._clear)
        input_buttons.addWidget(self.btn_clear)
        input_layout.addLayout(input_buttons)
        splitter.addWidget(input_box)

        result_box = QGroupBox("Posortowana lista — od najmniejszego numeru")
        result_layout = QVBoxLayout(result_box)
        self.result_edit = QPlainTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("Wynik sortowania pojawi się tutaj.")
        self.result_edit.setMinimumWidth(300)
        result_layout.addWidget(self.result_edit, 1)

        self.results_table = QTableWidget(0, 2)
        self.results_table.setObjectName("parcel_sorter_results")
        self.results_table.setHorizontalHeaderLabels(["Lp.", "Numer działki"])
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.results_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.results_table.setMaximumHeight(210)
        result_layout.addWidget(self.results_table)

        result_buttons = QHBoxLayout()
        self.btn_copy = QPushButton("📋 Kopiuj wynik")
        self.btn_copy.clicked.connect(self._copy_result)
        result_buttons.addWidget(self.btn_copy)
        result_buttons.addStretch()
        self.lbl_count = QLabel("Działek: 0")
        self.lbl_count.setStyleSheet("color: #888;")
        result_buttons.addWidget(self.lbl_count)
        result_layout.addLayout(result_buttons)
        splitter.addWidget(result_box)

        splitter.setSizes([520, 520])

        self.btn_sort = QPushButton("↕️ Sortuj rosnąco")
        self.btn_sort.setObjectName("btn_primary")
        self.btn_sort.setMinimumHeight(38)
        self.btn_sort.clicked.connect(self._sort_ascending)
        layout.addWidget(self.btn_sort)

        self.input_edit.textChanged.connect(self._on_input_changed)
        self.chk_remove_duplicates.toggled.connect(self._on_unique_toggled)

    def _restore_state(self):
        self.input_edit.blockSignals(True)
        self.chk_remove_duplicates.blockSignals(True)
        self.input_edit.setPlainText(str(self.config.get(self.INPUT_KEY, "")))
        self.chk_remove_duplicates.setChecked(
            bool(self.config.get(self.UNIQUE_KEY, False))
        )
        self.input_edit.blockSignals(False)
        self.chk_remove_duplicates.blockSignals(False)

        previous_result = parse_parcel_list(self.config.get(self.RESULT_KEY, ""))
        self._set_result_values(previous_result, persist=False)
        self.btn_load_project.setEnabled(False)

    def set_parcels(self, parcels: list):
        """Udostępnia numery z aktywnego projektu jako opcjonalne źródło listy."""

        self._project_parcels = list(parcels or [])
        if hasattr(self, "btn_load_project"):
            self.btn_load_project.setEnabled(bool(self._project_parcels))

    def _on_input_changed(self):
        self.config[self.INPUT_KEY] = self.input_edit.toPlainText()
        # Po zmianie listy poprzedni wynik nie powinien wyglądać jak aktualny.
        if self.result_edit.toPlainText():
            self._set_result_values([], persist=True)

    def _on_unique_toggled(self, checked: bool):
        self.config[self.UNIQUE_KEY] = bool(checked)

    def _paste_from_clipboard(self):
        self.input_edit.setFocus()
        self.input_edit.paste()

    def _load_project_parcels(self):
        if not self._project_parcels:
            QMessageBox.information(
                self,
                "Brak działek",
                "Aktywny projekt nie zawiera jeszcze działek.",
            )
            return

        if self.input_edit.toPlainText().strip():
            answer = QMessageBox.question(
                self,
                "Zastąpić listę?",
                "Zastąpić obecną listę numerami działek z aktywnego projektu?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        values = []
        for parcel in self._project_parcels:
            value = parcel.get("number", "") if isinstance(parcel, dict) else parcel
            if str("" if value is None else value).strip():
                values.append(str(value))
        self.input_edit.setPlainText("\n".join(values))

    def _clear(self):
        self.input_edit.clear()
        self._set_result_values([], persist=True)

    def _sort_ascending(self):
        values = parse_parcel_list(self.input_edit.toPlainText())
        if not values:
            self._set_result_values([], persist=True)
            QMessageBox.information(
                self,
                "Brak numerów",
                "Wpisz lub wklej co najmniej jeden numer działki.",
            )
            return

        result = sort_parcel_numbers(
            values, unique=self.chk_remove_duplicates.isChecked()
        )
        self._set_result_values(result, persist=True)

    def _set_result_values(self, values: list[str], *, persist: bool):
        text = "\n".join(values)
        self.result_edit.setPlainText(text)
        self.results_table.setRowCount(0)
        for row, value in enumerate(values):
            self.results_table.insertRow(row)
            index_item = QTableWidgetItem(str(row + 1))
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(row, 0, index_item)
            self.results_table.setItem(row, 1, QTableWidgetItem(value))

        self.lbl_count.setText(f"Działek: {len(values)}")
        if persist:
            self.config[self.RESULT_KEY] = text

    def _copy_result(self):
        result = self.result_edit.toPlainText()
        if not result:
            QMessageBox.information(
                self,
                "Brak wyniku",
                "Najpierw posortuj listę działek.",
            )
            return

        QApplication.clipboard().setText(result)
        self.lbl_count.setText(
            f"Działek: {self.results_table.rowCount()} — skopiowano do schowka"
        )
