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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from utils.parcel_sorting import (
    find_duplicate_parcel_numbers,
    format_parcel_list,
    parse_parcel_list,
    remove_duplicate_parcel_numbers,
    sort_parcel_numbers,
)


class ParcelSortingWidget(QWidget):
    """Pozwala wkleić listę numerów działek i uporządkować ją rosnąco."""

    INPUT_KEY = "parcel_sorter_input"
    RESULT_KEY = "parcel_sorter_result"
    UNIQUE_KEY = "parcel_sorter_remove_duplicates"
    DUPLICATE_INPUT_KEY = "parcel_duplicate_cleaner_input"
    DUPLICATE_RESULT_KEY = "parcel_duplicate_cleaner_result"
    ACTIVE_TAB_KEY = "parcel_sorter_active_tab"

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

        title = QLabel("↕️ Sortowanie numerów działek")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("parcel_sorter_tabs")
        layout.addWidget(self.tabs, 1)

        self._build_sorting_tab()
        self._build_duplicates_tab()

        self.input_edit.textChanged.connect(self._on_input_changed)
        self.input_edit.returnPressed.connect(self._sort_ascending)
        self.input_edit.installEventFilter(self)
        self.chk_remove_duplicates.toggled.connect(self._on_unique_toggled)

        self.duplicate_input_edit.textChanged.connect(self._on_duplicate_input_changed)
        self.duplicate_input_edit.returnPressed.connect(self._remove_duplicates)
        self.duplicate_input_edit.installEventFilter(self)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _build_sorting_tab(self):
        sorting_page = QWidget()
        layout = QVBoxLayout(sorting_page)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        description = QLabel(
            "Ułóż numery rosnąco w naturalnej kolejności, np. "
            "1, 1/2, 1/10, 2, 10."
        )
        description.setWordWrap(True)
        header.addWidget(description, 1)
        self.chk_remove_duplicates = QCheckBox("Usuń powtórzenia przy sortowaniu")
        self.chk_remove_duplicates.setToolTip(
            "Opcjonalnie usuwa duplikaty przed sortowaniem. Aby wyczyścić "
            "powtórzenia bez zmiany kolejności, użyj zakładki Duplikaty."
        )
        header.addWidget(self.chk_remove_duplicates)
        layout.addLayout(header)

        hint = QLabel(
            "Wpisz lub wklej numery w jednej linii, rozdzielając je przecinkami. "
            "Możesz także wkleić starszą listę z nowymi wierszami, tabulatorami "
            "lub średnikami — zostanie zapisana jako zwykła lista z przecinkami."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px;")
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
        result_buttons.addWidget(self.lbl_count)
        result_layout.addLayout(result_buttons)
        layout.addWidget(result_box)
        layout.addStretch()

        self.tabs.addTab(sorting_page, "↕️ Sortowanie")

    def _build_duplicates_tab(self):
        duplicates_page = QWidget()
        layout = QVBoxLayout(duplicates_page)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        title = QLabel("🧹 Duplikaty — zachowaj kolejność pierwszych wpisów")
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        hint = QLabel(
            "Ta operacja nie sortuje listy. Dla wpisów „1/2, 1/3, 1/2, 1/4” "
            "wynikiem będzie „1/2, 1/3, 1/4”. Warianty zapisu „1 / 2” i "
            "„1/2” są traktowane jako ten sam numer."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(hint)

        input_box = QGroupBox("Lista do sprawdzenia")
        input_layout = QVBoxLayout(input_box)
        self.duplicate_input_edit = QLineEdit()
        self.duplicate_input_edit.setPlaceholderText("np. 1/2, 1/3, 1/2, 1/4")
        self.duplicate_input_edit.setMinimumHeight(32)
        input_layout.addWidget(self.duplicate_input_edit)

        input_buttons = QHBoxLayout()
        self.btn_duplicate_paste = QPushButton("📋 Wklej ze schowka")
        self.btn_duplicate_paste.clicked.connect(self._paste_duplicates_from_clipboard)
        input_buttons.addWidget(self.btn_duplicate_paste)
        self.btn_duplicate_load_project = QPushButton("📥 Wczytaj działki projektu")
        self.btn_duplicate_load_project.setToolTip(
            "Wstawia numery z aktywnej zakładki Lista Działek."
        )
        self.btn_duplicate_load_project.clicked.connect(self._load_project_parcels_for_duplicates)
        input_buttons.addWidget(self.btn_duplicate_load_project)
        input_buttons.addStretch()
        self.btn_duplicate_clear = QPushButton("🗑 Wyczyść")
        self.btn_duplicate_clear.clicked.connect(self._clear_duplicates)
        input_buttons.addWidget(self.btn_duplicate_clear)
        input_layout.addLayout(input_buttons)
        layout.addWidget(input_box)

        self.btn_remove_duplicates = QPushButton(
            "🧹 Znajdź i usuń powtórzenia bez sortowania"
        )
        self.btn_remove_duplicates.setObjectName("btn_primary")
        self.btn_remove_duplicates.setMinimumHeight(38)
        self.btn_remove_duplicates.clicked.connect(self._remove_duplicates)
        layout.addWidget(self.btn_remove_duplicates)

        self.lbl_found_duplicates = QLabel(
            "Powtórzenia zostaną pokazane tutaj po sprawdzeniu listy."
        )
        self.lbl_found_duplicates.setWordWrap(True)
        layout.addWidget(self.lbl_found_duplicates)

        result_box = QGroupBox("Lista po usunięciu powtórzeń")
        result_layout = QVBoxLayout(result_box)
        self.duplicate_result_edit = QLineEdit()
        self.duplicate_result_edit.setReadOnly(True)
        self.duplicate_result_edit.setPlaceholderText(
            "Lista bez powtórzeń pojawi się tutaj w tej samej kolejności."
        )
        self.duplicate_result_edit.setMinimumHeight(32)
        result_layout.addWidget(self.duplicate_result_edit)

        result_buttons = QHBoxLayout()
        self.btn_copy_duplicates = QPushButton("📋 Kopiuj wynik")
        self.btn_copy_duplicates.clicked.connect(self._copy_duplicate_result)
        result_buttons.addWidget(self.btn_copy_duplicates)
        self.btn_send_to_sorting = QPushButton("↕️ Przenieś do sortowania")
        self.btn_send_to_sorting.setToolTip(
            "Wstawia listę bez duplikatów do zakładki Sortowanie."
        )
        self.btn_send_to_sorting.clicked.connect(self._send_duplicate_result_to_sorting)
        result_buttons.addWidget(self.btn_send_to_sorting)
        result_buttons.addStretch()
        self.lbl_duplicate_count = QLabel("Wpisów: 0 • unikalnych: 0")
        result_buttons.addWidget(self.lbl_duplicate_count)
        result_layout.addLayout(result_buttons)
        layout.addWidget(result_box)
        layout.addStretch()

        self.tabs.addTab(duplicates_page, "🧹 Duplikaty")

    def eventFilter(self, watched, event):
        """Normalizuje także listy wklejone skrótem Ctrl+V/Cmd+V.

        Pola są celowo jednoliniowe, dlatego przechwytujemy wklejenie
        wielowierszowe zanim Qt ograniczy je do jednego wiersza.
        """
        if (
            watched in (self.input_edit, self.duplicate_input_edit)
            and event.type() == QEvent.Type.KeyPress
            and event.matches(QKeySequence.StandardKey.Paste)
        ):
            self._paste_values_into(watched)
            return True
        return super().eventFilter(watched, event)

    def _restore_state(self):
        self.input_edit.blockSignals(True)
        self.chk_remove_duplicates.blockSignals(True)
        self.duplicate_input_edit.blockSignals(True)
        self.tabs.blockSignals(True)

        saved_input = format_parcel_list(
            parse_parcel_list(self.config.get(self.INPUT_KEY, ""))
        )
        saved_duplicate_input = format_parcel_list(
            parse_parcel_list(self.config.get(self.DUPLICATE_INPUT_KEY, ""))
        )
        self.input_edit.setText(saved_input)
        self.duplicate_input_edit.setText(saved_duplicate_input)
        self.chk_remove_duplicates.setChecked(
            bool(self.config.get(self.UNIQUE_KEY, False))
        )

        tab_index = self.config.get(self.ACTIVE_TAB_KEY, 0)
        try:
            tab_index = int(tab_index)
        except (TypeError, ValueError):
            tab_index = 0
        self.tabs.setCurrentIndex(max(0, min(tab_index, self.tabs.count() - 1)))

        self.input_edit.blockSignals(False)
        self.chk_remove_duplicates.blockSignals(False)
        self.duplicate_input_edit.blockSignals(False)
        self.tabs.blockSignals(False)

        # Starsze konfiguracje mogły zawierać numery po jednym wierszu. Przy
        # odczycie normalizujemy oba pola, aby kolejne zapisanie zachowało
        # wyłącznie poziomy format z przecinkami.
        self.config[self.INPUT_KEY] = saved_input
        self.config[self.DUPLICATE_INPUT_KEY] = saved_duplicate_input
        previous_result = parse_parcel_list(self.config.get(self.RESULT_KEY, ""))
        self._set_result_values(previous_result, persist=True)

        previous_duplicate_result = parse_parcel_list(
            self.config.get(self.DUPLICATE_RESULT_KEY, "")
        )
        if previous_duplicate_result:
            duplicate_values = parse_parcel_list(saved_duplicate_input)
            self._set_duplicate_result_values(
                previous_duplicate_result,
                input_count=len(duplicate_values),
                duplicate_groups=find_duplicate_parcel_numbers(duplicate_values),
                persist=True,
            )
        else:
            self._set_duplicate_result_values(
                [], input_count=0, duplicate_groups=[], persist=True
            )
        self.btn_load_project.setEnabled(False)
        self.btn_duplicate_load_project.setEnabled(False)

    def set_parcels(self, parcels: list):
        """Udostępnia numery z aktywnego projektu jako opcjonalne źródło listy."""

        self._project_parcels = list(parcels or [])
        enabled = bool(self._project_parcels)
        if hasattr(self, "btn_load_project"):
            self.btn_load_project.setEnabled(enabled)
        if hasattr(self, "btn_duplicate_load_project"):
            self.btn_duplicate_load_project.setEnabled(enabled)

    def _on_tab_changed(self, index: int):
        self.config[self.ACTIVE_TAB_KEY] = index

    def _on_input_changed(self):
        self.config[self.INPUT_KEY] = self.input_edit.text()
        # Po zmianie listy poprzedni wynik nie powinien wyglądać jak aktualny.
        if self.result_edit.text():
            self._set_result_values([], persist=True)

    def _on_duplicate_input_changed(self):
        self.config[self.DUPLICATE_INPUT_KEY] = self.duplicate_input_edit.text()
        if self.duplicate_result_edit.text():
            self._set_duplicate_result_values(
                [], input_count=0, duplicate_groups=[], persist=True
            )
        else:
            self.lbl_duplicate_count.setText("Wpisów: 0 • unikalnych: 0")
            self.lbl_found_duplicates.setText(
                "Lista została zmieniona — sprawdź ją ponownie."
            )

    def _on_unique_toggled(self, checked: bool):
        self.config[self.UNIQUE_KEY] = bool(checked)

    def _paste_values_into(self, edit: QLineEdit):
        clipboard_text = QApplication.clipboard().text()
        values = parse_parcel_list(clipboard_text)
        if not values:
            return

        pasted_text = format_parcel_list(values)
        current_text = edit.text()
        if (
            current_text.strip()
            and not edit.hasSelectedText()
            and not current_text.rstrip().endswith((",", ";", "\t", "\n"))
        ):
            pasted_text = ", " + pasted_text
        edit.insert(pasted_text)
        edit.setFocus()

    def _paste_from_clipboard(self):
        self._paste_values_into(self.input_edit)

    def _paste_duplicates_from_clipboard(self):
        self._paste_values_into(self.duplicate_input_edit)

    def _project_parcel_values(self) -> list[str]:
        values = []
        for parcel in self._project_parcels:
            value = parcel.get("number", "") if isinstance(parcel, dict) else parcel
            if str("" if value is None else value).strip():
                values.append(str(value))
        return values

    def _load_project_parcels_into(self, edit: QLineEdit, list_name: str):
        if not self._project_parcels:
            QMessageBox.information(
                self,
                "Brak działek",
                "Aktywny projekt nie zawiera jeszcze działek.",
            )
            return

        if edit.text().strip():
            answer = QMessageBox.question(
                self,
                "Zastąpić listę?",
                f"Zastąpić {list_name} numerami działek z aktywnego projektu?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        edit.setText(format_parcel_list(self._project_parcel_values()))

    def _load_project_parcels(self):
        self._load_project_parcels_into(self.input_edit, "obecną listę")

    def _load_project_parcels_for_duplicates(self):
        self._load_project_parcels_into(
            self.duplicate_input_edit, "listę do sprawdzenia"
        )

    def _clear(self):
        self.input_edit.clear()
        self._set_result_values([], persist=True)

    def _clear_duplicates(self):
        self.duplicate_input_edit.clear()
        self._set_duplicate_result_values(
            [], input_count=0, duplicate_groups=[], persist=True
        )

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

    def _remove_duplicates(self):
        values = parse_parcel_list(self.duplicate_input_edit.text())
        if not values:
            self._set_duplicate_result_values(
                [], input_count=0, duplicate_groups=[], persist=True
            )
            QMessageBox.information(
                self,
                "Brak numerów",
                "Wpisz lub wklej co najmniej jeden numer działki.",
            )
            return

        formatted_input = format_parcel_list(values)
        if self.duplicate_input_edit.text() != formatted_input:
            self.duplicate_input_edit.setText(formatted_input)

        duplicate_groups = find_duplicate_parcel_numbers(values)
        result = remove_duplicate_parcel_numbers(values)
        self._set_duplicate_result_values(
            result,
            input_count=len(values),
            duplicate_groups=duplicate_groups,
            persist=True,
        )

    def _set_result_values(self, values: list[str], *, persist: bool):
        self._result_values = list(values)
        text = format_parcel_list(self._result_values)
        self.result_edit.setText(text)
        self.lbl_count.setText(f"Działek: {len(self._result_values)}")
        if persist:
            self.config[self.RESULT_KEY] = text

    def _set_duplicate_result_values(
        self,
        values: list[str],
        *,
        input_count: int,
        duplicate_groups: list[tuple[str, int]],
        persist: bool,
    ):
        self._duplicate_result_values = list(values)
        text = format_parcel_list(self._duplicate_result_values)
        self.duplicate_result_edit.setText(text)
        removed_count = max(0, input_count - len(self._duplicate_result_values))
        self.lbl_duplicate_count.setText(
            f"Wpisów: {input_count} • unikalnych: "
            f"{len(self._duplicate_result_values)} • usunięto: {removed_count}"
        )
        if duplicate_groups:
            duplicate_text = ", ".join(
                f"{number} ({count}×)" for number, count in duplicate_groups
            )
            self.lbl_found_duplicates.setText(
                f"Wykryte powtórzenia: {duplicate_text}"
            )
        elif input_count:
            self.lbl_found_duplicates.setText(
                "Nie wykryto powtórzeń — kolejność listy została zachowana."
            )
        else:
            self.lbl_found_duplicates.setText(
                "Powtórzenia zostaną pokazane tutaj po sprawdzeniu listy."
            )
        if persist:
            self.config[self.DUPLICATE_RESULT_KEY] = text

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

    def _copy_duplicate_result(self):
        result = self.duplicate_result_edit.text()
        if not result:
            QMessageBox.information(
                self,
                "Brak wyniku",
                "Najpierw sprawdź listę i usuń powtórzenia.",
            )
            return

        QApplication.clipboard().setText(result)
        self.lbl_duplicate_count.setText(
            f"Wpisów: {len(self._duplicate_result_values)} • unikalnych: "
            f"{len(self._duplicate_result_values)} — skopiowano do schowka"
        )

    def _send_duplicate_result_to_sorting(self):
        result = self.duplicate_result_edit.text()
        if not result:
            QMessageBox.information(
                self,
                "Brak wyniku",
                "Najpierw sprawdź listę i usuń powtórzenia.",
            )
            return

        self.input_edit.setText(result)
        self.tabs.setCurrentIndex(0)
        self.input_edit.setFocus()
