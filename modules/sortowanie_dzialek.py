"""Samodzielny moduł do naturalnego sortowania numerów działek."""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.parcel_sorting import (
    format_parcel_list,
    parse_parcel_list,
    sort_parcel_numbers,
)


class ParcelSortingWidget(QWidget):
    """Pozwala wkleić listę numerów działek i uporządkować ją rosnąco."""

    INPUT_KEY = "parcel_sorter_input"
    RESULT_KEY = "parcel_sorter_result"
    UNIQUE_KEY = "parcel_sorter_remove_duplicates"

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._project_parcels: list = []
        self._result_values: list[str] = []
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
            "Wpisz lub wklej numery w jednej linii, rozdzielając je przecinkami. "
            "Możesz także wkleić starszą listę z nowymi wierszami, tabulatorami "
            "lub średnikami — zostanie zapisana jako zwykła lista z przecinkami. "
            "Numery są sortowane naturalnie, np. 1, 1/2, 1/10, 2, 10."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        input_box = QGroupBox("Lista do posortowania")
        input_layout = QVBoxLayout(input_box)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("np. 12/10, 2, 12/3, 1")
        self.input_edit.setMinimumHeight(32)
        input_layout.addWidget(self.input_edit)

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
        layout.addWidget(input_box)

        self.btn_sort = QPushButton("↕️ Sortuj rosnąco")
        self.btn_sort.setObjectName("btn_primary")
        self.btn_sort.setMinimumHeight(38)
        self.btn_sort.clicked.connect(self._sort_ascending)
        layout.addWidget(self.btn_sort)

        result_box = QGroupBox("Posortowana lista — od najmniejszego numeru")
        result_layout = QVBoxLayout(result_box)
        self.result_edit = QLineEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText(
            "Wynik sortowania pojawi się tutaj w jednej linii."
        )
        self.result_edit.setMinimumHeight(32)
        self.result_edit.setToolTip(
            "Lista jest gotowa do skopiowania w formacie: 1/1, 1/2, 1/10."
        )
        result_layout.addWidget(self.result_edit)

        result_buttons = QHBoxLayout()
        self.btn_copy = QPushButton("📋 Kopiuj wynik")
        self.btn_copy.clicked.connect(self._copy_result)
        result_buttons.addWidget(self.btn_copy)
        result_buttons.addStretch()
        self.lbl_count = QLabel("Działek: 0")
        self.lbl_count.setStyleSheet("color: #888;")
        result_buttons.addWidget(self.lbl_count)
        result_layout.addLayout(result_buttons)
        layout.addWidget(result_box)
        layout.addStretch()

        self.input_edit.textChanged.connect(self._on_input_changed)
        self.input_edit.returnPressed.connect(self._sort_ascending)
        self.input_edit.installEventFilter(self)
        self.chk_remove_duplicates.toggled.connect(self._on_unique_toggled)

    def eventFilter(self, watched, event):
        """Normalizuje także listę wklejoną skrótem Ctrl+V/Cmd+V.

        QLineEdit jest celowo polem jednoliniowym, dlatego przechwytujemy
        wklejenie wielowierszowe zanim Qt ograniczy je do jednego wiersza.
        """
        if (
            watched is self.input_edit
            and event.type() == QEvent.Type.KeyPress
            and event.matches(QKeySequence.StandardKey.Paste)
        ):
            self._paste_from_clipboard()
            return True
        return super().eventFilter(watched, event)

    def _restore_state(self):
        self.input_edit.blockSignals(True)
        self.chk_remove_duplicates.blockSignals(True)
        saved_input = format_parcel_list(
            parse_parcel_list(self.config.get(self.INPUT_KEY, ""))
        )
        self.input_edit.setText(saved_input)
        self.chk_remove_duplicates.setChecked(
            bool(self.config.get(self.UNIQUE_KEY, False))
        )
        self.input_edit.blockSignals(False)
        self.chk_remove_duplicates.blockSignals(False)

        # Starsze konfiguracje mogły zawierać numery po jednym wierszu. Przy
        # odczycie normalizujemy oba pola, aby kolejne zapisanie zachowało
        # wyłącznie poziomy format z przecinkami.
        self.config[self.INPUT_KEY] = saved_input
        previous_result = parse_parcel_list(self.config.get(self.RESULT_KEY, ""))
        self._set_result_values(previous_result, persist=True)
        self.btn_load_project.setEnabled(False)

    def set_parcels(self, parcels: list):
        """Udostępnia numery z aktywnego projektu jako opcjonalne źródło listy."""

        self._project_parcels = list(parcels or [])
        if hasattr(self, "btn_load_project"):
            self.btn_load_project.setEnabled(bool(self._project_parcels))

    def _on_input_changed(self):
        self.config[self.INPUT_KEY] = self.input_edit.text()
        # Po zmianie listy poprzedni wynik nie powinien wyglądać jak aktualny.
        if self.result_edit.text():
            self._set_result_values([], persist=True)

    def _on_unique_toggled(self, checked: bool):
        self.config[self.UNIQUE_KEY] = bool(checked)

    def _paste_from_clipboard(self):
        clipboard_text = QApplication.clipboard().text()
        values = parse_parcel_list(clipboard_text)
        if not values:
            return

        pasted_text = format_parcel_list(values)
        current_text = self.input_edit.text()
        if (
            current_text.strip()
            and not self.input_edit.hasSelectedText()
            and not current_text.rstrip().endswith((",", ";", "\t", "\n"))
        ):
            pasted_text = ", " + pasted_text
        self.input_edit.insert(pasted_text)
        self.input_edit.setFocus()

    def _load_project_parcels(self):
        if not self._project_parcels:
            QMessageBox.information(
                self,
                "Brak działek",
                "Aktywny projekt nie zawiera jeszcze działek.",
            )
            return

        if self.input_edit.text().strip():
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
        self.input_edit.setText(format_parcel_list(values))

    def _clear(self):
        self.input_edit.clear()
        self._set_result_values([], persist=True)

    def _sort_ascending(self):
        values = parse_parcel_list(self.input_edit.text())
        if not values:
            self._set_result_values([], persist=True)
            QMessageBox.information(
                self,
                "Brak numerów",
                "Wpisz lub wklej co najmniej jeden numer działki.",
            )
            return

        # Zapis wejścia również normalizujemy do poziomego formatu, bez
        # zmieniania kolejności podanej przez użytkownika przed sortowaniem.
        formatted_input = format_parcel_list(values)
        if self.input_edit.text() != formatted_input:
            self.input_edit.setText(formatted_input)

        result = sort_parcel_numbers(
            values, unique=self.chk_remove_duplicates.isChecked()
        )
        self._set_result_values(result, persist=True)

    def _set_result_values(self, values: list[str], *, persist: bool):
        self._result_values = list(values)
        text = format_parcel_list(self._result_values)
        self.result_edit.setText(text)
        self.lbl_count.setText(f"Działek: {len(self._result_values)}")
        if persist:
            self.config[self.RESULT_KEY] = text

    def _copy_result(self):
        result = self.result_edit.text()
        if not result:
            QMessageBox.information(
                self,
                "Brak wyniku",
                "Najpierw posortuj listę działek.",
            )
            return

        QApplication.clipboard().setText(result)
        self.lbl_count.setText(
            f"Działek: {len(self._result_values)} — skopiowano do schowka"
        )
