"""
legal_titles.py – Zakładka Tytuły Prawne (Pięć osobnych zakładek tabel)
"""
import json
import re
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QScrollArea, QSizePolicy, QSplitter, QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QGuiApplication, QShortcut

from utils.parcel_location import split_parcel_location
from utils.output_paths import project_output_dir

from modules.legal_titles_dialogs import OddzialEditorDialog, ComboBoxDelegate
from modules.legal_titles_excel import LegalTitlesExcelExporter

class MultiLineTextDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        editor.setStyleSheet("QTextEdit { padding: 1px; }")
        return editor

    def setEditorData(self, editor, index):
        text = index.model().data(index, Qt.ItemDataRole.EditRole)
        if text: editor.setPlainText(str(text))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class LegalTitlesWidget(QWidget):
    owners_changed = Signal(list)

    def showEvent(self, event):
        super().showEvent(event)
        t1 = self.config.get('legal_tmpl_1', '')
        if t1: self.tmpl_1_edit.setText(t1)
        t2 = self.config.get('legal_tmpl_2', '')
        if t2: self.tmpl_2_edit.setText(t2)
        t3 = self.config.get('legal_tmpl_3', '')
        if t3: self.tmpl_3_edit.setText(t3)

    def eventFilter(self, source, event):
        if event.type() == event.Type.KeyPress and isinstance(source, QTableWidget):
            if event.matches(QKeySequence.Copy):
                selected = source.selectedRanges()
                if selected:
                    r = selected[0].topRow()
                    c = selected[0].leftColumn()
                    w = source.cellWidget(r, c)
                    text = w.currentText() if isinstance(w, QComboBox) else (source.item(r, c).text() if source.item(r, c) else "")
                    QGuiApplication.clipboard().setText(text)
                return True
            elif event.matches(QKeySequence.Paste):
                text = QGuiApplication.clipboard().text()
                selected = source.selectedRanges()
                if selected:
                    for sel in selected:
                        for r in range(sel.topRow(), sel.bottomRow() + 1):
                            for c in range(sel.leftColumn(), sel.rightColumn() + 1):
                                w = source.cellWidget(r, c)
                                if isinstance(w, QComboBox): w.setCurrentText(text)
                                else:
                                    if source.item(r, c): source.item(r, c).setText(text)
                                    else: source.setItem(r, c, QTableWidgetItem(text))
                return True
        return super().eventFilter(source, event)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.owners = []
        self.parcels = []
        self.records_1b = {}
        self.records_2 = {}
        self.deleted_keys = set()
        self.active_project = {}
        self._build_ui()

        self.tmpl_1_edit.setText(self.config.get('legal_tmpl_1', ''))
        self.tmpl_2_edit.setText(self.config.get('legal_tmpl_2', ''))
        self.tmpl_3_edit.setText(self.config.get('legal_tmpl_3', ''))

    def _copy_cells(self, table):
        selected = table.selectedRanges()
        if selected:
            r, c = selected[0].topRow(), selected[0].leftColumn()
            text = table.item(r, c).text() if table.item(r, c) else ""
            QGuiApplication.clipboard().setText(text)

    def _paste_cells(self, table):
        text = QGuiApplication.clipboard().text()
        selected = table.selectedRanges()
        if selected:
            for sel in selected:
                for r in range(sel.topRow(), sel.bottomRow() + 1):
                    for c in range(sel.leftColumn(), sel.rightColumn() + 1):
                        if table.item(r, c): table.item(r, c).setText(text)
                        else: table.setItem(r, c, QTableWidgetItem(text))

    def _delete_cells(self, table):
        selected = table.selectedRanges()
        if selected:
            for sel in selected:
                for r in range(sel.topRow(), sel.bottomRow() + 1):
                    for c in range(sel.leftColumn(), sel.rightColumn() + 1):
                        if table.item(r, c): table.item(r, c).setText("")

    def _manual_merge(self, table):
        sel = table.selectedRanges()
        if not sel: return
        for r in sel: table.setSpan(r.topRow(), r.leftColumn(), r.bottomRow() - r.topRow() + 1, r.rightColumn() - r.leftColumn() + 1)

    def _manual_unmerge(self, table):
        sel = table.selectedRanges()
        if not sel: return
        for r in sel: table.setSpan(r.topRow(), r.leftColumn(), 1, 1)

    def _edit_odd_options(self):
        odd_str = self.config.get('legal_odd_opcje', 'Gdańsk, Starogard Gdański')
        current_options = [x.strip() for x in odd_str.split(',') if x.strip()]
        dlg = OddzialEditorDialog(current_options, self)
        if dlg.exec():
            new_options = dlg.get_options()
            text = ", ".join(new_options)
            self.config['legal_odd_opcje'] = text
            import sys
            if getattr(sys, 'frozen', False): cfg_path = Path(sys.executable).parent.resolve() / 'dane' / 'app_config.json'
            else: cfg_path = Path(__file__).parent.parent.resolve() / 'dane' / 'app_config.json'
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f: cfg = json.load(f)
                cfg['legal_odd_opcje'] = text
                with open(cfg_path, 'w', encoding='utf-8') as f: json.dump(cfg, f, ensure_ascii=False, indent=2)
            except: pass

    def _get_combo_items_for_col(self, col):
        if col == 1:
            odd_str = self.config.get('legal_odd_opcje', 'Gdańsk, Starogard Gdański')
            return [""] + [x.strip() for x in odd_str.split(',') if x.strip()]
        elif col == 2:
            return ["", "Inna forma nabycia praw do nieruchomości", "Decyzja administracyjna o umieszczeniu urządzenia w pasach drogowych", "Umowa użyczenia", "Odpłatne oświadczenie woli o udostępnieniu nieruchomości pod projektowanym urządzeniem elektroenergetycznym", "Nieodpłatne oświadczenie woli o udostępnieniu nieruchomości pod projektowanym urządzeniem elektroenergetycznym", "Zakup prawa służebności przesyłu", "Nieodpłatne ustanowienie służebności przesyłu", "Oświadczenie woli o udostępnieniu nieruchomości w związku z demontażem urządzeń elektroenergetycznych", "Decyzja ZRID", "Istniejąca służebność przesyłu", "Działka Energa-Operator S.A.", "Umowa dzierżawy", "Odpłatne oświadczenie woli o udostępnieniu nieruchomości pod projektowanym urządzeniem elektroenergetycznym", "Odpłatne oświadczenie woli o udostępnieniu nieruchomości pod istniejącym urządzeniem elektroenergetycznym", "Nieodpłatne oświadczenie woli o udostępnieniu nieruchomości pod istniejącym urządzeniem elektroenergetycznym", "Artykuł 124", "Decyzja kolejowa ULLK", "Decyzja na podstawie specustawy ULISP"]
        elif col == 12:
            return ["", "Złącze Kablowe SN", "Stacja transformatorowa kontenerowa", "Stacja transformatorowa wkomponowana", "Stacja transformatorowa słupowa", "Przyłącze kablowe nn", "Przyłącze napowietrzne nn", "Złącze kablowe nn", "Rozłącznik SN", "Słup nn", "Słup SN", "Słup WN", "Linia napowietrzna nn", "Linia napowietrzna SN", "Linia napowietrzna WN", "Linia Kablowa nn", "Linia Kablowa SN", "Linia Kablowa WN", "GPZ", "PZ", "RS", "Transformator SN/nn", "Kanalizacja światłowodowa", "Światłowód", "Inne urządzenia EOP"]
        elif col == 15: return ["", "Nowe", "Demontaż", "Wymiana", "Inne (np. Regulacja wysokości)"]
        return []

    def _apply_legal_view_options(self):
        """Stosuje ustawienia wyglądu tabel Tytułów prawnych bez przebudowy danych."""
        tables = [
            getattr(self, 'table_1a', None),
            getattr(self, 'table_1b', None),
            getattr(self, 'table_2', None),
            getattr(self, 'table_3', None),
        ]
        alternating = self.config.get('legal_view_alternating_rows', True)
        word_wrap = self.config.get('legal_view_word_wrap', True)
        show_grid = self.config.get('legal_view_show_grid', True)
        stretch_last = self.config.get('legal_view_stretch_last_column', False)
        auto_resize = self.config.get('legal_view_auto_resize_rows', True)
        for table in tables:
            if table is None:
                continue
            table.setAlternatingRowColors(alternating)
            table.setWordWrap(word_wrap)
            table.setShowGrid(show_grid)
            header = table.horizontalHeader()
            if header:
                header.setSectionsMovable(True)
                if stretch_last and table.columnCount() > 0:
                    header.setStretchLastSection(True)
                else:
                    header.setStretchLastSection(False)
            if auto_resize:
                table.resizeRowsToContents()

    def _rebuild_legal_tables_from_settings(self):
        """Czyści i buduje tabele ponownie po zmianie ustawień grupowania."""
        self.table_1a.setRowCount(0)
        self.table_1b.setRowCount(0)
        self.table_2.setRowCount(0)
        self.table_3.setRowCount(0)
        self._sync_with_owners(show_info=False)
        self._apply_legal_view_options()

    def _on_t12_parcel_mode_changed(self, idx):
        self.config['legal_t12_multi_parcels_mode'] = int(idx)
        self._rebuild_legal_tables_from_settings()

    def _on_t12_owner_mode_changed(self, idx):
        self.config['legal_t12_multi_owners_mode'] = int(idx)
        self._rebuild_legal_tables_from_settings()

    def _open_grouping_settings_dialog(self):
        """Szczegółowe ustawienia działania grupowania i wyglądu tabel Tytułów prawnych."""
        dlg = QDialog(self)
        dlg.setObjectName("legalGroupingSettingsDialog")
        dlg.setWindowTitle("⚙️ Tytuły prawne — grupowanie i wygląd")
        # Otwieraj od razu szerokie okno, ale zawsze mieszczące się na ekranie,
        # na którym znajduje się główne okno programu.
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            dialog_width = min(1440, max(720, available.width() - 48))
            dialog_height = min(960, max(520, available.height() - 48))
        else:
            dialog_width, dialog_height = 1320, 880
        dlg.resize(dialog_width, dialog_height)
        dlg.setMinimumSize(min(1040, dialog_width), min(680, dialog_height))
        dlg.setSizeGripEnabled(True)
        dlg.setStyleSheet(
            """
            QDialog#legalGroupingSettingsDialog { background: #f6f8fb; }
            QDialog#legalGroupingSettingsDialog QGroupBox {
                border: 1px solid #d8e1ec; border-radius: 8px;
                margin-top: 12px; padding: 12px 10px 10px 10px;
                font-weight: 700; color: #263b53; background: white;
            }
            QDialog#legalGroupingSettingsDialog QGroupBox::title {
                subcontrol-origin: margin; left: 12px; padding: 0 6px;
            }
            QDialog#legalGroupingSettingsDialog QTabBar::tab {
                background: #e8eef5; color: #40556d; border: none;
                border-radius: 6px; margin: 2px; padding: 9px 14px;
                font-weight: 700;
            }
            QDialog#legalGroupingSettingsDialog QTabBar::tab:selected {
                background: #2b78c5; color: white;
            }
            QDialog#legalGroupingSettingsDialog QLabel,
            QDialog#legalGroupingSettingsDialog QCheckBox,
            QDialog#legalGroupingSettingsDialog QRadioButton {
                color: #263b53; background: transparent; padding: 4px 2px;
            }
            QDialog#legalGroupingSettingsDialog QComboBox {
                min-height: 26px; padding-left: 6px;
                color: #263b53; background: #ffffff; border: 1px solid #b9c9d9;
                border-radius: 4px;
            }
            QDialog#legalGroupingSettingsDialog QDialogButtonBox QPushButton {
                min-width: 120px; padding: 8px 14px; border-radius: 5px;
            }
            """
        )
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Ustawienia grupowania i wyglądu tabel")
        title.setStyleSheet("font-size:20px; font-weight:800; color:#1d4f80;")
        layout.addWidget(title)
        info = QLabel(
            "Wybierz sposób prezentacji danych, a następnie doprecyzuj tabele. "
            "Po kliknięciu <b>Zapisz i przebuduj</b> zmiany będą widoczne od razu."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color:#4f6478; background:#eaf4ff; border-left:4px solid #2b78c5; "
            "padding:9px; border-radius:5px;"
        )
        layout.addWidget(info)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        layout.addWidget(tabs, 1)

        def add_settings_tab(page, title):
            """Dodaje zakładkę z przewijaniem, aby żadna opcja nie znikała."""
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setWidget(page)
            tabs.addTab(scroll, title)

        # W każdym kroku pokazujemy mały, czytelny fragment tabeli. Dzięki
        # temu ustawienie nie jest wyłącznie techniczną nazwą — od razu widać,
        # jaki będzie efekt w zestawieniu.
        def table_fragment(headers, rows, *, show_grid=True, alternating=False):
            """Tworzy mały fragment tabeli używany przez interaktywne podglądy."""
            border = "1" if show_grid else "0"
            header_cells = "".join(
                "<th bgcolor='#dcecff' style='padding:5px; color:#1d4f80;'>"
                f"{header}</th>"
                for header in headers
            )
            body_rows = "".join(
                ("<tr bgcolor='#eef6fd'>" if alternating and index % 2 else "<tr>")
                + "".join(
                    "<td style='padding:5px; color:#263b53;'>"
                    f"{value}</td>"
                    for value in row
                )
                + "</tr>"
                for index, row in enumerate(rows)
            )
            return (
                f"<table border='{border}' cellspacing='0' cellpadding='0' width='100%' "
                "style='border-color:#a9c4de;'>"
                f"<tr>{header_cells}</tr>{body_rows}</table>"
            )

        def help_label(text):
            label = QLabel(f"↳ {text}")
            label.setWordWrap(True)
            label.setStyleSheet("color:#64798d; font-size:11px; padding:0 2px 5px 8px;")
            return label

        def option_with_hint(control, explanation):
            control.setToolTip(explanation)
            holder = QWidget()
            holder_layout = QVBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setSpacing(0)
            holder_layout.addWidget(control)
            holder_layout.addWidget(help_label(explanation))
            return holder

        def update_example_panel(
            preview, description, headers, rows, note, *, show_grid=True, alternating=False
        ):
            """Odświeża mały, żywy podgląd po zmianie ustawienia."""
            preview["summary"].setText(description)
            preview["fragment"].setText(
                table_fragment(
                    headers,
                    rows,
                    show_grid=show_grid,
                    alternating=alternating,
                )
            )
            preview["note"].setText(f"<b>Co zmienia bieżący wybór:</b> {note}")

        def example_panel(title, description, headers, rows, note):
            panel = QGroupBox(title)
            panel.setMinimumWidth(330)
            panel_layout = QVBoxLayout(panel)
            summary = QLabel()
            summary.setWordWrap(True)
            summary.setStyleSheet("color:#45647c; font-size:12px; font-weight:600;")
            panel_layout.addWidget(summary)
            fragment = QLabel()
            fragment.setTextFormat(Qt.TextFormat.RichText)
            fragment.setWordWrap(True)
            fragment.setStyleSheet(
                "background:#f7fbff; border:1px dashed #a9c4de; border-radius:5px; "
                "padding:7px;"
            )
            panel_layout.addWidget(fragment)
            note_label = QLabel()
            note_label.setTextFormat(Qt.TextFormat.RichText)
            note_label.setWordWrap(True)
            note_label.setStyleSheet("color:#607d8b; font-size:11px;")
            panel_layout.addWidget(note_label)
            panel_layout.addStretch()
            preview = {
                "summary": summary,
                "fragment": fragment,
                "note": note_label,
            }
            update_example_panel(preview, description, headers, rows, note)
            return panel, preview

        # ───────────────────────── 1. Tryb grupowania
        tab_group = QWidget()
        group_layout = QVBoxLayout(tab_group)
        group_layout.setSpacing(10)
        group_intro = QLabel(
            "<b>Krok 1.</b> Wybierz jeden z pięciu trybów. Po prawej stronie "
            "od razu zobaczysz uproszczony efekt grupowania."
        )
        group_intro.setWordWrap(True)
        group_intro.setStyleSheet("color:#607d8b; padding:4px 2px;")
        group_layout.addWidget(group_intro)

        mode_specs = (
            (
                "1. Osobne wpisy",
                "Każdy właściciel i każda działka otrzymują własny wiersz.",
                table_fragment(
                    ("Lp.", "Działka", "Właściciel"),
                    (("1", "12/1", "Anna Kowalska"), ("2", "12/1", "Jan Nowak")),
                ),
            ),
            (
                "2. Współwłaściciele wg działki",
                "Jedna działka, jeden wiersz; współwłaściciele są razem.",
                table_fragment(
                    ("Lp.", "Działka", "Właściciele"),
                    (("1", "12/1", "Anna Kowalska<br>Jan Nowak"),),
                ),
            ),
            (
                "3. Działki wg właściciela",
                "Wszystkie działki jednej osoby są zebrane przy jej nazwie.",
                table_fragment(
                    ("Lp.", "Właściciel", "Działki"),
                    (("1", "Anna Kowalska", "12/1, 12/2, 13/1"),),
                ),
            ),
            (
                "4. Identyczne pakiety",
                "Łączy powtarzające się zestawy działek i współwłaścicieli.",
                table_fragment(
                    ("Lp.", "Działki", "Współwłaściciele"),
                    (("1", "12/1<br>12/2", "Anna Kowalska<br>Jan Nowak"),),
                ),
            ),
            (
                "5. Zestawienie wg działki",
                "Grupuje według działki także w Tabeli 5, ze scaleniami.",
                table_fragment(
                    ("Działka", "Właściciele", "Tytuł prawny"),
                    (("12/1", "Anna Kowalska<br>Jan Nowak", "Służebność"),),
                ),
            ),
        )
        current_group_mode = self.combo_group_owners.currentIndex()
        if current_group_mode < 0 or current_group_mode >= len(mode_specs):
            current_group_mode = 1
        mode_button_group = QButtonGroup(dlg)
        mode_cards: dict[int, QFrame] = {}

        modes_layout = QHBoxLayout()
        modes_layout.setSpacing(14)
        modes_column = QVBoxLayout()
        modes_column.setSpacing(6)
        for index, (mode_title, description, _example) in enumerate(mode_specs):
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 7, 10, 7)
            card_layout.setSpacing(2)
            radio = QRadioButton(mode_title)
            radio.setChecked(index == current_group_mode)
            radio.setStyleSheet("font-weight:700; color:#244566;")
            mode_button_group.addButton(radio, index)
            card_layout.addWidget(radio)
            description_label = QLabel(description)
            description_label.setWordWrap(True)
            description_label.setStyleSheet("color:#607080; font-size:11px;")
            card_layout.addWidget(description_label)
            modes_column.addWidget(card)
            mode_cards[index] = card
        modes_column.addStretch()
        modes_layout.addLayout(modes_column, 3)

        preview_box = QGroupBox("Podgląd wybranego trybu")
        preview_layout = QVBoxLayout(preview_box)
        preview_title = QLabel()
        preview_title.setWordWrap(True)
        preview_title.setStyleSheet("font-size:15px; font-weight:800; color:#1d5f99;")
        preview_layout.addWidget(preview_title)
        preview_description = QLabel()
        preview_description.setWordWrap(True)
        preview_description.setStyleSheet("color:#52687a;")
        preview_layout.addWidget(preview_description)
        preview_example = QLabel()
        preview_example.setWordWrap(True)
        preview_example.setTextFormat(Qt.TextFormat.RichText)
        preview_example.setMinimumHeight(90)
        preview_example.setStyleSheet(
            "background:#f3f7fb; border:1px dashed #9ebbd7; border-radius:5px; "
            "padding:10px; color:#294b67;"
        )
        preview_layout.addWidget(preview_example)
        preview_note = QLabel(
            "To schemat pomocniczy — rzeczywiste wartości nadal pochodzą z danych projektu."
        )
        preview_note.setWordWrap(True)
        preview_note.setStyleSheet("color:#8091a0; font-size:10px; font-style:italic;")
        preview_layout.addWidget(preview_note)
        preview_layout.addStretch()
        modes_layout.addWidget(preview_box, 2)
        group_layout.addLayout(modes_layout, 1)

        def update_group_preview(index: int):
            index = max(0, min(index, len(mode_specs) - 1))
            mode_title, description, example = mode_specs[index]
            try:
                pair_on_separate_lines = combo_pair.currentIndex() == 1
            except NameError:
                # Pierwsze zbudowanie kart następuje przed utworzeniem comboboxa.
                pair_on_separate_lines = True
            if not pair_on_separate_lines:
                example = example.replace(
                    "Anna Kowalska<br>Jan Nowak", "Anna Kowalska i Jan Nowak"
                )
            preview_title.setText(mode_title)
            preview_description.setText(description)
            preview_example.setText(
                f"<b>Przykładowy fragment tabeli</b><br><br>{example}"
            )
            for card_index, card in mode_cards.items():
                if card_index == index:
                    card.setStyleSheet(
                        "QFrame { border:2px solid #2b78c5; border-radius:8px; "
                        "background:#eaf4ff; }"
                    )
                else:
                    card.setStyleSheet(
                        "QFrame { border:1px solid #d8e1ec; border-radius:8px; "
                        "background:#ffffff; }"
                    )

        for index in range(len(mode_specs)):
            button = mode_button_group.button(index)
            if button is not None:
                button.toggled.connect(
                    lambda checked, i=index: update_group_preview(i) if checked else None
                )
        update_group_preview(current_group_mode)

        base_box = QGroupBox("Dodatkowe ustawienia podstawowe")
        form = QFormLayout(base_box)
        combo_pair = QComboBox()
        for i in range(self.combo_owner_sep.count()):
            combo_pair.addItem(self.combo_owner_sep.itemText(i))
        combo_pair.setCurrentIndex(self.combo_owner_sep.currentIndex())
        combo_pair.setToolTip(
            "Pierwszy wariant łączy parę jako „Anna i Jan”; drugi wpisuje "
            "każdą osobę w osobnej linii tej samej komórki."
        )
        form.addRow("Format par / współwłaścicieli:", combo_pair)
        form.addRow(
            "",
            help_label(
                "„Anna i Jan” jest zwięzłe; wariant wielowierszowy ułatwia "
                "czytanie dłuższych list współwłaścicieli."
            ),
        )

        chk_sort = QCheckBox("Sortuj działki rosnąco przy zaciąganiu")
        chk_sort.setChecked(self.chk_sort_parcels.isChecked())
        form.addRow(
            "",
            option_with_hint(
                chk_sort,
                "Np. 2/1, 2/10, 10/1 zamiast kolejności wynikającej z importu.",
            ),
        )

        chk_exclude_dead = QCheckBox("Pomiń zmarłych i osoby bez poprawnego adresu")
        chk_exclude_dead.setChecked(self.config.get('legal_exclude_dead_missing', True))
        form.addRow(
            "",
            option_with_hint(
                chk_exclude_dead,
                "Takie pozycje nie pojawią się w automatycznie zbudowanych tabelach.",
            ),
        )

        def update_group_settings_preview(*_args):
            pair_layout = (
                "w osobnych liniach"
                if combo_pair.currentIndex() == 1
                else "w jednej wspólnej nazwie"
            )
            mode_title = mode_specs[max(0, mode_button_group.checkedId())][0]
            preview_note.setText(
                "<b>Aktualny wybór:</b> "
                f"{mode_title}; pary: {pair_layout}; działki: "
                f"{'rosnąco' if chk_sort.isChecked() else 'w kolejności danych'}; "
                f"pozycje zmarłe/niepełne: "
                f"{'pomijane' if chk_exclude_dead.isChecked() else 'uwzględniane'}.")

        def refresh_group_pair_preview(*_args):
            update_group_preview(max(0, mode_button_group.checkedId()))
            update_group_settings_preview()

        combo_pair.currentIndexChanged.connect(refresh_group_pair_preview)
        chk_sort.toggled.connect(update_group_settings_preview)
        chk_exclude_dead.toggled.connect(update_group_settings_preview)
        for index in range(len(mode_specs)):
            button = mode_button_group.button(index)
            if button is not None:
                button.toggled.connect(
                    lambda checked: update_group_settings_preview() if checked else None
                )
        refresh_group_pair_preview()
        group_layout.addWidget(base_box)
        add_settings_tab(tab_group, "① Grupowanie")

        # ───────────────────────── 2. Osobne wiersze / scalanie
        tab_rows = QWidget()
        rows_layout = QVBoxLayout(tab_rows)
        rows_intro = QLabel(
            "<b>Krok 2.</b> Zdecyduj, które powtarzające się dane mają zostać "
            "połączone, a które należy pozostawić w oddzielnych wierszach."
        )
        rows_intro.setWordWrap(True)
        rows_intro.setStyleSheet("color:#607d8b; padding:4px 2px;")
        rows_layout.addWidget(rows_intro)
        rows_content = QHBoxLayout()
        rows_content.setSpacing(14)
        box_rows = QGroupBox("Co ma być w osobnych wierszach, a co scalone")
        rows_form = QFormLayout(box_rows)

        chk_split_couples = QCheckBox("Opcja 1: rozdzielaj pary na osobne osoby / osobne wiersze")
        chk_split_couples.setChecked(self.config.get('legal_split_couples_option1', True))
        rows_form.addRow(
            "",
            option_with_hint(
                chk_split_couples,
                "Zamiast jednego wpisu „Anna i Jan”, powstaną dwa osobne wiersze.",
            ),
        )

        chk_option4_separate = QCheckBox("Opcja 4: właściciele w osobnych wierszach zamiast jednej komórki")
        chk_option4_separate.setChecked(self.config.get('legal_option4_owners_separate', True))
        rows_form.addRow(
            "",
            option_with_hint(
                chk_option4_separate,
                "W pakiecie działek każdy współwłaściciel zajmie własny wiersz; "
                "po odznaczeniu wszyscy pozostaną w jednej komórce.",
            ),
        )

        chk_option5_owner_one_cell = QCheckBox("Opcja 5: właściciele jednej działki w jednej scalonej komórce")
        chk_option5_owner_one_cell.setChecked(self.config.get('legal_option5_owner_one_cell', True))
        rows_form.addRow(
            "",
            option_with_hint(
                chk_option5_owner_one_cell,
                "Dla jednej działki lista współwłaścicieli będzie wizualnie jedną "
                "wspólną komórką, co zmniejsza powtarzanie numeru działki.",
            ),
        )

        chk_span_lp_owner = QCheckBox("Tabela 1 i 2: scalaj Lp. i Właściciela dla wspólnych bloków")
        chk_span_lp_owner.setChecked(self.config.get('legal_span_lp_owner_t1', True))
        rows_form.addRow(
            "",
            option_with_hint(
                chk_span_lp_owner,
                "Przy kilku działkach jednego właściciela numer Lp. i nazwa nie "
                "będą powielane w każdym kolejnym wierszu.",
            ),
        )

        chk_merge_kw = QCheckBox("Tabela 1 i 2: scalaj identyczne Nr KW w sąsiadujących wierszach")
        chk_merge_kw.setChecked(self.chk_merge_kw.isChecked())
        rows_form.addRow(
            "",
            option_with_hint(
                chk_merge_kw,
                "Ten sam numer KW w bezpośrednio sąsiadujących wierszach tworzy "
                "jedną wyższą komórkę zamiast powtarzającego się tekstu.",
            ),
        )

        chk_keep_manual = QCheckBox("Chroń ręczne edycje w istniejących wierszach, jeśli klucz wiersza się zgadza")
        chk_keep_manual.setChecked(self.config.get('legal_keep_manual_edits', True))
        rows_form.addRow(
            "",
            option_with_hint(
                chk_keep_manual,
                "Po przebudowie zachowa ręcznie wpisane wartości, np. status "
                "wysyłki lub uwagę, gdy dany wiersz nadal odpowiada temu samemu wpisowi.",
            ),
        )

        rows_preview_box, rows_preview = example_panel(
            "Podgląd — wiersze i scalenia",
            "Zmień dowolny przełącznik po lewej, aby zobaczyć wynik.",
            ("Lp.", "Działka", "Właściciel", "Nr KW"),
            (),
            "",
        )

        def update_rows_preview(*_args):
            split_couple = chk_split_couples.isChecked()
            span_owner = chk_span_lp_owner.isChecked()
            merge_kw = chk_merge_kw.isChecked()
            if split_couple:
                rows = (
                    ("1", "12/1", "Anna Kowalska", "GD1G/00012345/6"),
                    (
                        "" if span_owner else "2",
                        "12/1",
                        "" if span_owner else "Jan Nowak",
                        "" if merge_kw else "GD1G/00012345/6",
                    ),
                )
                description = "Para jest pokazana jako dwa wiersze — po jednym dla każdej osoby."
            else:
                rows = (("1", "12/1", "Anna Kowalska i Jan Nowak", "GD1G/00012345/6"),)
                description = "Para pozostaje wspólnie w jednej komórce i jednym wierszu."

            owner_block = (
                "w osobnych wierszach"
                if chk_option4_separate.isChecked()
                else "w jednej komórce"
            )
            parcel_owner_block = (
                "w jednej scalonej komórce"
                if chk_option5_owner_one_cell.isChecked()
                else "w osobnych komórkach"
            )
            note = (
                f"Opcja 4: współwłaściciele pakietu są {owner_block}. "
                f"Opcja 5: właściciele działki są {parcel_owner_block}. "
                f"Ręczne edycje: {'chronione' if chk_keep_manual.isChecked() else 'mogą zostać nadpisane przy przebudowie'}."
            )
            update_example_panel(
                rows_preview,
                description,
                ("Lp.", "Działka", "Właściciel", "Nr KW"),
                rows,
                note,
            )

        for control in (
            chk_split_couples,
            chk_option4_separate,
            chk_option5_owner_one_cell,
            chk_span_lp_owner,
            chk_merge_kw,
            chk_keep_manual,
        ):
            control.toggled.connect(update_rows_preview)
        update_rows_preview()
        rows_content.addWidget(box_rows, 3)
        rows_content.addWidget(rows_preview_box, 2)
        rows_layout.addLayout(rows_content, 1)
        add_settings_tab(tab_rows, "② Wiersze i scalenia")

        # ───────────────────────── 3. Tabela 1 i 2
        tab_t12 = QWidget()
        t12_layout = QVBoxLayout(tab_t12)
        t12_intro = QLabel(
            "<b>Krok 3.</b> Te opcje dotyczą szczegółów Tabeli 1 i 2: "
            "dodatkowych kolumn, brakującego KW oraz zapisu wielu działek i właścicieli."
        )
        t12_intro.setWordWrap(True)
        t12_intro.setStyleSheet("color:#607d8b; padding:4px 2px;")
        t12_layout.addWidget(t12_intro)
        t12_content = QHBoxLayout()
        t12_content.setSpacing(14)
        box_t12 = QGroupBox("Ustawienia Tabeli 1 i 2")
        t12_form = QFormLayout(box_t12)
        lbl_t12_help = QLabel(
            "Ustawienie działa po kliknięciu „Zapisz i przebuduj”; nie zmienia źródłowych danych właścicieli."
        )
        lbl_t12_help.setWordWrap(True)
        lbl_t12_help.setStyleSheet("color:#2b5797; font-weight:bold;")
        t12_form.addRow("", lbl_t12_help)

        chk_extra_1a = QCheckBox("Tabela 1: pokaż Wysłano / Otrzymano / Uwagi")
        chk_extra_1a.setChecked(self.chk_extra_1a.isChecked())
        t12_form.addRow(
            "",
            option_with_hint(
                chk_extra_1a,
                "Dodaje trzy robocze kolumny do Tabeli 1, np. do odnotowania "
                "daty wysłania, odpowiedzi i własnej notatki.",
            ),
        )

        chk_extra_1b = QCheckBox("Tabela 2: pokaż Wysłano / Otrzymano / Uwagi")
        chk_extra_1b.setChecked(self.chk_extra_1b.isChecked())
        t12_form.addRow(
            "",
            option_with_hint(
                chk_extra_1b,
                "Dodaje takie same trzy kolumny robocze do Tabeli 2.",
            ),
        )

        chk_przylacza_separate = QCheckBox("Przyłącza trzymaj w Tabeli 1, pozostałe w Tabeli 2")
        chk_przylacza_separate.setChecked(self.config.get('legal_przylacza_to_t1', True))
        t12_form.addRow(
            "",
            option_with_hint(
                chk_przylacza_separate,
                "Rozdziela wpisy według kategorii: przyłącza trafiają do Tabeli 1, "
                "a budowa/demontaż do Tabeli 2.",
            ),
        )

        combo_empty_kw = QComboBox()
        combo_empty_kw.addItems(["Zostaw puste", "Wpisz '-'", "Wpisz 'brak'"])
        combo_empty_kw.setCurrentIndex(self.config.get('legal_empty_kw_mode', 0))
        combo_empty_kw.setToolTip(
            "Wybierz wizualny zapis komórki, gdy dane działki nie zawierają numeru KW."
        )
        t12_form.addRow("Gdy brak KW:", combo_empty_kw)
        t12_form.addRow(
            "",
            help_label("Pusty wpis jest neutralny, „-” oznacza brak wartości, a „brak” opisuje go słownie."),
        )

        combo_multi_parcels = QComboBox()
        combo_multi_parcels.addItems([
            "Wiele działek w jednej komórce – każda w nowej linii",
            "Wiele działek w jednej komórce – po przecinku",
            "Wiele działek rozbijaj na osobne wiersze"
        ])
        combo_multi_parcels.setCurrentIndex(self.config.get('legal_t12_multi_parcels_mode', 0))
        combo_multi_parcels.setToolTip(
            "Wybiera układ działek jednego właściciela: pionowa lista, krótka lista "
            "po przecinku lub pełne rozbicie na rekordy."
        )
        t12_form.addRow("Gdy właściciel ma wiele działek:", combo_multi_parcels)
        t12_form.addRow(
            "",
            help_label("Nowe linie są najczytelniejsze; przecinki są najbardziej zwarte; osobne wiersze ułatwiają dalsze filtrowanie."),
        )

        combo_multi_owners = QComboBox()
        combo_multi_owners.addItems([
            "Wielu właścicieli w jednej komórce – każdy w nowej linii",
            "Wielu właścicieli w jednej komórce – po przecinku",
            "Właściciele w osobnych wierszach, gdy tryb na to pozwala"
        ])
        combo_multi_owners.setCurrentIndex(self.config.get('legal_t12_multi_owners_mode', 0))
        combo_multi_owners.setToolTip(
            "Wybiera sposób pokazania współwłaścicieli jednej działki."
        )
        t12_form.addRow("Gdy działka ma wielu właścicieli:", combo_multi_owners)
        t12_form.addRow(
            "",
            help_label("W jednej komórce dane są zwarte; osobne wiersze ułatwiają przypisanie odrębnych statusów osobom."),
        )

        t12_preview_box, t12_preview = example_panel(
            "Podgląd — Tabela 1 / Tabela 2",
            "Zmień ustawienia po lewej, aby porównać układ komórek.",
            ("Tabela", "Kategoria", "Działki", "Właściciele", "Nr KW"),
            (),
            "",
        )

        def update_t12_preview(*_args):
            parcel_mode = combo_multi_parcels.currentIndex()
            owner_mode = combo_multi_owners.currentIndex()
            parcel_value = (
                "12/1<br>12/2"
                if parcel_mode == 0
                else "12/1, 12/2"
            )
            owner_value = (
                "Anna Kowalska<br>Jan Nowak"
                if owner_mode == 0
                else "Anna Kowalska, Jan Nowak"
            )
            missing_kw = ("", "-", "brak")[max(0, min(combo_empty_kw.currentIndex(), 2))]
            first_table = "Tabela 1" if chk_przylacza_separate.isChecked() else "Tabela 1 / 2"
            second_table = "Tabela 2" if chk_przylacza_separate.isChecked() else "Tabela 1 / 2"

            headers = ["Tabela", "Kategoria", "Działki", "Właściciele", "Nr KW"]
            if chk_extra_1a.isChecked():
                headers.append("Wysłano T1")
            if chk_extra_1b.isChecked():
                headers.append("Wysłano T2")

            def make_row(table, category, parcels, owners, kw):
                row = [table, category, parcels, owners, kw]
                if chk_extra_1a.isChecked():
                    row.append("2026-08-29" if table == "Tabela 1" else "")
                if chk_extra_1b.isChecked():
                    row.append("2026-08-29" if table == "Tabela 2" else "")
                return tuple(row)

            if parcel_mode == 2:
                rows = [
                    make_row(first_table, "Przyłącze", "12/1", owner_value, "GD1G/00012345/6"),
                    make_row(first_table, "Przyłącze", "12/2", owner_value, "GD1G/00012345/6"),
                ]
            elif owner_mode == 2:
                rows = [
                    make_row(first_table, "Przyłącze", parcel_value, "Anna Kowalska", "GD1G/00012345/6"),
                    make_row(first_table, "Przyłącze", "", "Jan Nowak", "GD1G/00012345/6"),
                ]
            else:
                rows = [
                    make_row(first_table, "Przyłącze", parcel_value, owner_value, "GD1G/00012345/6"),
                ]
            rows.append(
                make_row(second_table, "Budowa", "15/1", "Jan Nowak", missing_kw)
            )

            parcel_layout = (
                "osobne wiersze"
                if parcel_mode == 2
                else "nowe linie" if parcel_mode == 0 else "lista po przecinku"
            )
            owner_layout = (
                "osobne wiersze"
                if owner_mode == 2
                else "nowe linie" if owner_mode == 0 else "lista po przecinku"
            )
            note = (
                f"Działki: {parcel_layout}; współwłaściciele: {owner_layout}; "
                f"brak KW: {'pusta komórka' if not missing_kw else missing_kw!r}. "
                f"Przyłącza: {'Tabela 1' if chk_przylacza_separate.isChecked() else 'wspólny układ Tabel 1/2'}."
            )
            update_example_panel(
                t12_preview,
                "Podgląd odzwierciedla aktualnie zaznaczone kolumny, podział kategorii i format wielokrotnych danych.",
                tuple(headers),
                tuple(rows),
                note,
            )

        for control in (chk_extra_1a, chk_extra_1b, chk_przylacza_separate):
            control.toggled.connect(update_t12_preview)
        for control in (combo_empty_kw, combo_multi_parcels, combo_multi_owners):
            control.currentIndexChanged.connect(update_t12_preview)
        update_t12_preview()
        t12_content.addWidget(box_t12, 3)
        t12_content.addWidget(t12_preview_box, 2)
        t12_layout.addLayout(t12_content, 1)
        add_settings_tab(tab_t12, "③ Tabele 1 i 2")

        # ───────────────────────── 4. Tabela 3
        tab_t3 = QWidget()
        t3_layout = QVBoxLayout(tab_t3)
        t3_intro = QLabel(
            "<b>Krok 4.</b> Tabela 3 jest wykazem szczegółowym. Tutaj wybierasz, "
            "czy ma pokazać każdy związek właściciela z działką i jak traktować braki danych."
        )
        t3_intro.setWordWrap(True)
        t3_intro.setStyleSheet("color:#607d8b; padding:4px 2px;")
        t3_layout.addWidget(t3_intro)
        t3_content = QHBoxLayout()
        t3_content.setSpacing(14)
        box_t3 = QGroupBox("Ustawienia Tabeli 3")
        t3_form = QFormLayout(box_t3)

        chk_dash = QCheckBox("W T3 zmień ulicę na '-' jeśli jest taka sama jak miasto")
        chk_dash.setChecked(self.chk_dash_street.isChecked())
        t3_form.addRow(
            "",
            option_with_hint(
                chk_dash,
                "Gdy ulica zawiera dokładnie tę samą nazwę co miejscowość, komórka "
                "ulicy pokaże „-”, aby nie dublować informacji.",
            ),
        )

        chk_t3_every_owner_parcel = QCheckBox("T3: zawsze jeden wiersz na właściciela i działkę")
        chk_t3_every_owner_parcel.setChecked(self.config.get('legal_t3_each_owner_parcel', True))
        t3_form.addRow(
            "",
            option_with_hint(
                chk_t3_every_owner_parcel,
                "Dla działki z dwiema osobami powstaną dwa wiersze. Po wyłączeniu "
                "układ może korzystać z grupowania wybranego w kroku 1.",
            ),
        )

        chk_t3_skip_no_kw = QCheckBox("T3: pomijaj pozycje bez KW")
        chk_t3_skip_no_kw.setChecked(self.config.get('legal_t3_skip_no_kw', False))
        t3_form.addRow(
            "",
            option_with_hint(
                chk_t3_skip_no_kw,
                "Nie doda do Tabeli 3 działek, dla których nie ma przypisanego numeru KW.",
            ),
        )

        t3_preview_box, t3_preview = example_panel(
            "Podgląd — Tabela 3",
            "Zmień ustawienia po lewej, aby zobaczyć liczbę i treść wierszy.",
            ("Lp.", "Właściciel", "Działka", "Ulica", "Nr KW"),
            (),
            "",
        )

        def update_t3_preview(*_args):
            street_value = "-" if chk_dash.isChecked() else "Gdańsk"
            if chk_t3_every_owner_parcel.isChecked():
                rows = [
                    ("1", "Anna Kowalska", "12/1", street_value, "GD1G/00012345/6"),
                    ("2", "Jan Nowak", "12/1", street_value, "GD1G/00012345/6"),
                ]
                description = "Każdy współwłaściciel otrzymuje własny, szczegółowy wiersz."
            else:
                rows = [
                    ("1", "Anna Kowalska<br>Jan Nowak", "12/1", street_value, "GD1G/00012345/6"),
                ]
                description = "Współwłaściciele mogą zostać zebrani w jednym wierszu zgodnie z trybem grupowania."
            if not chk_t3_skip_no_kw.isChecked():
                rows.append((str(len(rows) + 1), "Piotr Zieliński", "15/1", "ul. Polna", "brak"))
            note = (
                f"Ulica powtarzająca nazwę miasta: {'„-”' if chk_dash.isChecked() else 'pokazana w całości'}. "
                f"Pozycje bez KW: {'pomijane' if chk_t3_skip_no_kw.isChecked() else 'pokazywane jako „brak”'}."
            )
            update_example_panel(
                t3_preview,
                description,
                ("Lp.", "Właściciel", "Działka", "Ulica", "Nr KW"),
                tuple(rows),
                note,
            )

        for control in (chk_dash, chk_t3_every_owner_parcel, chk_t3_skip_no_kw):
            control.toggled.connect(update_t3_preview)
        update_t3_preview()
        t3_content.addWidget(box_t3, 3)
        t3_content.addWidget(t3_preview_box, 2)
        t3_layout.addLayout(t3_content, 1)
        add_settings_tab(tab_t3, "④ Tabela 3")

        # ───────────────────────── 5. Tabela 5
        tab_t5 = QWidget()
        t5_layout = QVBoxLayout(tab_t5)
        t5_intro = QLabel(
            "<b>Krok 5.</b> Tabela 5 jest końcowym zestawieniem. Wybierz źródło "
            "ulicy oraz pola, które powinny wizualnie tworzyć wspólne bloki."
        )
        t5_intro.setWordWrap(True)
        t5_intro.setStyleSheet("color:#607d8b; padding:4px 2px;")
        t5_layout.addWidget(t5_intro)
        t5_content = QHBoxLayout()
        t5_content.setSpacing(14)
        box_t5 = QGroupBox("Ustawienia Tabeli 5")
        t5_form = QFormLayout(box_t5)

        chk_t5_street = QCheckBox("Zaciągaj ulicę do T5")
        chk_t5_street.setChecked(self.chk_t5_street.isChecked())
        t5_form.addRow(
            "",
            option_with_hint(
                chk_t5_street,
                "Dodaje kolumnę ulicy do końcowego zestawienia. Po odznaczeniu "
                "Tabela 5 pozostaje krótsza i nie zawiera danych ulicy.",
            ),
        )

        chk_t5_city = QCheckBox("Zaciągaj miejscowość do T5")
        chk_t5_city.setChecked(
            self.chk_t5_city.isChecked()
            if hasattr(self, 'chk_t5_city')
            else self.config.get('legal_t5_pull_city', False)
        )
        t5_form.addRow(
            "",
            option_with_hint(
                chk_t5_city,
                "Wypełnia kolumnę Miejscowość w Tabeli 5 według źródła "
                "wybranego poniżej. Po odznaczeniu kolumna zostaje pusta.",
            ),
        )

        combo_city_source = QComboBox()
        combo_city_source.addItems([
            "Miejscowość z projektu (domyślnie)",
            "Miejscowośc działki z wypisu",
            "Adres właściciela – miejscowość",
        ])
        combo_city_source.setCurrentIndex(self.config.get('legal_t5_city_source', 0))
        combo_city_source.setToolTip(
            "Wskazuje, skąd pobierana jest treść kolumny Miejscowość w Tabeli 5."
        )
        t5_form.addRow("Źródło miejscowości T5:", combo_city_source)
        t5_form.addRow(
            "",
            help_label(
                "Domyślnie wpisywana jest miejscowość z danych projektu. "
                "Drugi wariant bierze „Miejscowośc działki” z Wypisów, "
                "trzeci – miejscowość z adresu właściciela. Gdy wybrane "
                "źródło jest puste, program sięga po miejscowość projektu."
            ),
        )

        combo_street_source = QComboBox()
        combo_street_source.addItems([
            "Adres właściciela – sama ulica",
            "Adres właściciela – ulica i numer domu",
            "Ulica działki z wypisu / pola Ulica Działki",
        ])
        combo_street_source.setCurrentIndex(self.config.get('legal_t5_street_source', 0))
        combo_street_source.setToolTip("Wskazuje, skąd pobierana jest treść kolumny Ulica w Tabeli 5.")
        t5_form.addRow("Źródło ulicy T5:", combo_street_source)
        t5_form.addRow(
            "",
            help_label("Sama ulica ukrywa numer domu; drugi wariant go zachowuje; trzeci korzysta z adresu przypisanego do działki."),
        )

        chk_group_odd = QCheckBox("T5: grupuj/scalaj Oddziały")
        chk_group_odd.setChecked(getattr(self, 'chk_group_odd', None).isChecked() if hasattr(self, 'chk_group_odd') else False)
        t5_form.addRow(
            "",
            option_with_hint(
                chk_group_odd,
                "Identyczne, sąsiadujące nazwy oddziału pojawią się jako jeden "
                "wspólny blok zamiast w każdym wierszu.",
            ),
        )

        chk_group_tytul = QCheckBox("T5: grupuj/scalaj Tytuły prawne")
        chk_group_tytul.setChecked(getattr(self, 'chk_group_tytul', None).isChecked() if hasattr(self, 'chk_group_tytul') else False)
        t5_form.addRow(
            "",
            option_with_hint(
                chk_group_tytul,
                "Powtarzający się tytuł prawny jest scalany pionowo dla kolejnych wpisów.",
            ),
        )

        chk_group_urz = QCheckBox("T5: grupuj/scalaj Rodzaje urządzenia")
        chk_group_urz.setChecked(getattr(self, 'chk_group_urz', None).isChecked() if hasattr(self, 'chk_group_urz') else False)
        t5_form.addRow(
            "",
            option_with_hint(
                chk_group_urz,
                "Powtarzający się rodzaj urządzenia będzie widoczny raz dla wspólnego bloku.",
            ),
        )

        chk_t5_merge_kw = QCheckBox("T5: scalaj identyczne KW")
        chk_t5_merge_kw.setChecked(self.config.get('legal_t5_merge_kw', True))
        t5_form.addRow(
            "",
            option_with_hint(
                chk_t5_merge_kw,
                "Ten sam numer KW w kolejnych wierszach będzie pokazany jako jedna "
                "scalona komórka, zamiast wielokrotnie powtórzony.",
            ),
        )

        t5_preview_box, t5_preview = example_panel(
            "Podgląd — Tabela 5",
            "Zmień ustawienia po lewej, aby zobaczyć od razu efekt scalenia kolumn.",
            ("Działka", "Ulica", "Oddział", "Tytuł", "Urządzenie", "KW"),
            (),
            "",
        )

        def update_t5_preview(*_args):
            source_index = max(0, min(combo_street_source.currentIndex(), 2))
            street_values = ("ul. Leśna", "ul. Leśna 12", "ul. Działkowa")
            city_index = max(0, min(combo_city_source.currentIndex(), 2))
            city_values = ("Maki", "Żukowo", "Gdańsk")
            headers = ["Działka"]
            if chk_t5_city.isChecked():
                headers.append("Miejscowość")
            if chk_t5_street.isChecked():
                headers.append("Ulica")
            headers.extend(("Oddział", "Tytuł", "Urządzenie", "KW"))

            def make_row(parcel, second_row=False):
                row = [parcel]
                if chk_t5_city.isChecked():
                    row.append(city_values[city_index])
                if chk_t5_street.isChecked():
                    row.append(street_values[source_index])
                row.extend(
                    (
                        "" if second_row and chk_group_odd.isChecked() else "Gdańsk",
                        "" if second_row and chk_group_tytul.isChecked() else "Służebność",
                        "" if second_row and chk_group_urz.isChecked() else "Linia SN",
                        "" if second_row and chk_t5_merge_kw.isChecked() else "GD1G/00012345/6",
                    )
                )
                return tuple(row)

            rows = (make_row("12/1"), make_row("12/2", second_row=True))
            street_note = (
                f"ulica: {street_values[source_index]}"
                if chk_t5_street.isChecked()
                else "kolumna ulicy ukryta"
            )
            city_note = (
                f"miejscowość: {city_values[city_index]}"
                if chk_t5_city.isChecked()
                else "kolumna miejscowości pusta"
            )
            grouped_columns = [
                name
                for name, control in (
                    ("Oddział", chk_group_odd),
                    ("Tytuł", chk_group_tytul),
                    ("Urządzenie", chk_group_urz),
                    ("KW", chk_t5_merge_kw),
                )
                if control.isChecked()
            ]
            note = (
                f"{city_note}, {street_note}. Scalone kolumny: "
                f"{', '.join(grouped_columns) if grouped_columns else 'brak — dane są powtarzane w każdym wierszu'}."
            )
            update_example_panel(
                t5_preview,
                "Puste komórki drugiego wiersza oznaczają wartość scaloną z pierwszym rekordem.",
                tuple(headers),
                rows,
                note,
            )

        for control in (
            chk_t5_street,
            chk_t5_city,
            chk_group_odd,
            chk_group_tytul,
            chk_group_urz,
            chk_t5_merge_kw,
        ):
            control.toggled.connect(update_t5_preview)
        combo_street_source.currentIndexChanged.connect(update_t5_preview)
        combo_city_source.currentIndexChanged.connect(update_t5_preview)
        update_t5_preview()
        t5_content.addWidget(box_t5, 3)
        t5_content.addWidget(t5_preview_box, 2)
        t5_layout.addLayout(t5_content, 1)
        add_settings_tab(tab_t5, "⑤ Tabela 5")

        # ───────────────────────── 6. Wygląd
        tab_view = QWidget()
        view_layout = QVBoxLayout(tab_view)
        view_intro = QLabel(
            "<b>Krok 6.</b> Te ustawienia zmieniają wyłącznie czytelność tabel na ekranie. "
            "Nie zmieniają danych ani plików źródłowych."
        )
        view_intro.setWordWrap(True)
        view_intro.setStyleSheet("color:#607d8b; padding:4px 2px;")
        view_layout.addWidget(view_intro)
        view_content = QHBoxLayout()
        view_content.setSpacing(14)
        box_view = QGroupBox("Czytelność tabel na ekranie")
        view_form = QFormLayout(box_view)

        chk_wrap = QCheckBox("Zawijaj tekst w komórkach")
        chk_wrap.setChecked(self.config.get('legal_view_word_wrap', True))
        view_form.addRow(
            "",
            option_with_hint(
                chk_wrap,
                "Długi adres lub nazwa właściciela przejdzie do kolejnej linii, "
                "zamiast zostać ucięta w wąskiej kolumnie.",
            ),
        )

        chk_resize = QCheckBox("Automatycznie dopasuj wysokość wierszy")
        chk_resize.setChecked(self.config.get('legal_view_auto_resize_rows', True))
        view_form.addRow(
            "",
            option_with_hint(
                chk_resize,
                "Wiersz zwiększy wysokość, aby pokazać cały zawinięty tekst. "
                "Najlepiej używać razem z zawijaniem tekstu.",
            ),
        )

        chk_alt = QCheckBox("Naprzemienne kolory wierszy")
        chk_alt.setChecked(self.config.get('legal_view_alternating_rows', True))
        view_form.addRow(
            "",
            option_with_hint(
                chk_alt,
                "Co drugi wiersz otrzyma delikatnie inny kolor tła, dzięki czemu "
                "łatwiej śledzić dane w szerokiej tabeli.",
            ),
        )

        chk_grid = QCheckBox("Pokaż linie siatki")
        chk_grid.setChecked(self.config.get('legal_view_show_grid', True))
        view_form.addRow(
            "",
            option_with_hint(
                chk_grid,
                "Włącza cienkie linie między komórkami; wyłącz je dla bardziej "
                "minimalistycznego wyglądu.",
            ),
        )

        chk_stretch = QCheckBox("Rozciągaj ostatnią kolumnę")
        chk_stretch.setChecked(self.config.get('legal_view_stretch_last_column', False))
        view_form.addRow(
            "",
            option_with_hint(
                chk_stretch,
                "Ostatnia kolumna wykorzysta pozostałe wolne miejsce zamiast "
                "pozostawiać pusty obszar po prawej stronie tabeli.",
            ),
        )

        view_preview_box, view_preview = example_panel(
            "Podgląd — wygląd wierszy",
            "Zmień ustawienia po lewej, aby porównać czytelność tego samego fragmentu.",
            ("Lp.", "Właściciel", "Adres / uwaga"),
            (),
            "",
        )

        def update_view_preview(*_args):
            wrapping = chk_wrap.isChecked()
            auto_height = chk_resize.isChecked()
            long_text = (
                "ul. Bardzo Długa 123<br>80-001 Gdańsk"
                if wrapping
                else "ul. Bardzo Długa 123, 80-001 Gdańsk"
            )
            if not auto_height and wrapping:
                long_text = "ul. Bardzo Długa 123<br><i>(wysokość wiersza stała)</i>"
            last_header = (
                "Adres / uwaga — szeroka kolumna"
                if chk_stretch.isChecked()
                else "Adres / uwaga"
            )
            note = (
                f"Zawijanie: {'włączone' if wrapping else 'wyłączone'}; "
                f"automatyczna wysokość: {'włączona' if auto_height else 'wyłączona'}; "
                f"naprzemienne tło: {'włączone' if chk_alt.isChecked() else 'wyłączone'}; "
                f"siatka: {'widoczna' if chk_grid.isChecked() else 'ukryta'}; "
                f"ostatnia kolumna: {'rozciągnięta' if chk_stretch.isChecked() else 'standardowa'}."
            )
            update_example_panel(
                view_preview,
                "Ten sam przykład zmienia wygląd natychmiast po zaznaczeniu opcji.",
                ("Lp.", "Właściciel", last_header),
                (
                    ("1", "Anna Kowalska", long_text),
                    ("2", "Jan Nowak", "Oczekuje na odpowiedź"),
                ),
                note,
                show_grid=chk_grid.isChecked(),
                alternating=chk_alt.isChecked(),
            )

        for control in (chk_wrap, chk_resize, chk_alt, chk_grid, chk_stretch):
            control.toggled.connect(update_view_preview)
        update_view_preview()
        view_content.addWidget(box_view, 3)
        view_content.addWidget(view_preview_box, 2)
        view_layout.addLayout(view_content, 1)
        add_settings_tab(tab_view, "⑥ Wygląd")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("💾 Zapisz i przebuduj")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_group = mode_button_group.checkedId()
        if new_group < 0:
            new_group = current_group_mode
        self.config['legal_group_owners'] = new_group
        self.config['legal_owner_sep'] = combo_pair.currentIndex()
        self.config['legal_split_couples_option1'] = chk_split_couples.isChecked()
        self.config['legal_option4_owners_separate'] = chk_option4_separate.isChecked()
        self.config['legal_option5_owner_one_cell'] = chk_option5_owner_one_cell.isChecked()
        self.config['legal_span_lp_owner_t1'] = chk_span_lp_owner.isChecked()
        self.config['legal_merge_kw_t1'] = chk_merge_kw.isChecked()
        self.config['legal_keep_manual_edits'] = chk_keep_manual.isChecked()
        self.config['legal_exclude_dead_missing'] = chk_exclude_dead.isChecked()
        self.config['legal_sort_parcels'] = chk_sort.isChecked()
        self.config['legal_przylacza_to_t1'] = chk_przylacza_separate.isChecked()
        self.config['legal_empty_kw_mode'] = combo_empty_kw.currentIndex()
        self.config['legal_t12_multi_parcels_mode'] = combo_multi_parcels.currentIndex()
        self.config['legal_t12_multi_owners_mode'] = combo_multi_owners.currentIndex()
        self.config['legal_dash_same_street'] = chk_dash.isChecked()
        self.config['legal_t3_each_owner_parcel'] = chk_t3_every_owner_parcel.isChecked()
        self.config['legal_t3_skip_no_kw'] = chk_t3_skip_no_kw.isChecked()
        self.config['legal_t5_pull_street'] = chk_t5_street.isChecked()
        self.config['legal_t5_street_source'] = combo_street_source.currentIndex()
        self.config['legal_t5_city_source'] = combo_city_source.currentIndex()
        self.config['legal_t5_pull_city'] = chk_t5_city.isChecked()
        self.config['legal_t5_merge_kw'] = chk_t5_merge_kw.isChecked()
        self.config['legal_view_word_wrap'] = chk_wrap.isChecked()
        self.config['legal_view_auto_resize_rows'] = chk_resize.isChecked()
        self.config['legal_view_alternating_rows'] = chk_alt.isChecked()
        self.config['legal_view_show_grid'] = chk_grid.isChecked()
        self.config['legal_view_stretch_last_column'] = chk_stretch.isChecked()

        self.combo_group_owners.blockSignals(True)
        self.combo_group_owners.setCurrentIndex(new_group)
        self.combo_group_owners.blockSignals(False)
        self.combo_owner_sep.blockSignals(True)
        self.combo_owner_sep.setCurrentIndex(combo_pair.currentIndex())
        self.combo_owner_sep.blockSignals(False)
        self.chk_sort_parcels.blockSignals(True); self.chk_sort_parcels.setChecked(chk_sort.isChecked()); self.chk_sort_parcels.blockSignals(False)
        self.chk_merge_kw.blockSignals(True); self.chk_merge_kw.setChecked(chk_merge_kw.isChecked()); self.chk_merge_kw.blockSignals(False)
        if hasattr(self, 'combo_t12_parcel_mode'):
            self.combo_t12_parcel_mode.blockSignals(True); self.combo_t12_parcel_mode.setCurrentIndex(combo_multi_parcels.currentIndex()); self.combo_t12_parcel_mode.blockSignals(False)
        if hasattr(self, 'combo_t12_owner_mode'):
            self.combo_t12_owner_mode.blockSignals(True); self.combo_t12_owner_mode.setCurrentIndex(combo_multi_owners.currentIndex()); self.combo_t12_owner_mode.blockSignals(False)
        self.chk_t5_street.blockSignals(True); self.chk_t5_street.setChecked(chk_t5_street.isChecked()); self.chk_t5_street.blockSignals(False)
        self.chk_t5_city.blockSignals(True); self.chk_t5_city.setChecked(chk_t5_city.isChecked()); self.chk_t5_city.blockSignals(False)
        self.chk_dash_street.blockSignals(True); self.chk_dash_street.setChecked(chk_dash.isChecked()); self.chk_dash_street.blockSignals(False)
        self.chk_extra_1a.setChecked(chk_extra_1a.isChecked())
        self.chk_extra_1b.setChecked(chk_extra_1b.isChecked())
        if hasattr(self, 'chk_group_odd'): self.chk_group_odd.setChecked(chk_group_odd.isChecked())
        if hasattr(self, 'chk_group_tytul'): self.chk_group_tytul.setChecked(chk_group_tytul.isChecked())
        if hasattr(self, 'chk_group_urz'): self.chk_group_urz.setChecked(chk_group_urz.isChecked())

        self._rebuild_legal_tables_from_settings()
        QMessageBox.information(self, "Ustawienia", "Zastosowano szczegółowe ustawienia grupowania i wyglądu tabel.")


    def _on_group_changed(self, i):
        old_i = self.config.get('legal_group_owners', 1)
        if i == old_i: return
        reply = QMessageBox.question(self, "Przebudowa tabel", "Zmiana trybu grupowania wymaga przebudowania Tabeli 1 i 2.\nUwaga: niezapisane ręcznie dane w tych tabelach (np. Wysłano/Otrzymano) mogą zostać zresetowane.\nCzy chcesz kontynuować?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.config.update({'legal_group_owners': i})
            self.table_1a.setRowCount(0)
            self.table_1b.setRowCount(0)
            self._sync_with_owners(show_info=False)
            QMessageBox.information(self, "Zaktualizowano", "Tabele zostały pomyślnie przebudowane według nowego ustawienia.")
        else:
            self.combo_group_owners.blockSignals(True)
            self.combo_group_owners.setCurrentIndex(old_i)
            self.combo_group_owners.blockSignals(False)

    def _on_sort_parcels_toggled(self, checked):
        self.config['legal_sort_parcels'] = bool(checked)
        # Zmiana sortowania ma działać od razu: przebuduj tabele z aktualnej bazy.
        self.table_1a.setRowCount(0)
        self.table_1b.setRowCount(0)
        self.table_2.setRowCount(0)
        self.table_3.setRowCount(0)
        self._sync_with_owners(show_info=False)

    def _build_ui(self):
        # Cała zakładka jest przewijana — dzięki temu przy mniejszym oknie
        # programu żadna sekcja (a zwłaszcza pola Metryki) nie znika.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page = QWidget()
        page_scroll.setWidget(page)
        outer_layout.addWidget(page_scroll)

        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        self.multi_line_delegate = MultiLineTextDelegate(self)

        hdr = QLabel('⚖️ Tytuły Prawne (Edytor i Eksport do Excela)')
        hdr.setStyleSheet('font-size:16px; font-weight:700;')
        layout.addWidget(hdr)

        sync_box = QGroupBox('Dane z bazy i Ustawienia Generatora')
        sync_box.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        sync_layout = QVBoxLayout(sync_box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Formatowanie par:"))
        self.combo_owner_sep = QComboBox()
        self.combo_owner_sep.addItems(["Łącz imiona jako: ' Monika i Marcin '", "Łącz imiona w nowych liniach (Alt+Enter)"])
        self.combo_owner_sep.currentIndexChanged.connect(lambda i: self.config.update({'legal_owner_sep': i}))
        self.combo_owner_sep.setCurrentIndex(self.config.get('legal_owner_sep', 0))
        row1.addWidget(self.combo_owner_sep)

        row1.addWidget(QLabel(" | Grupowanie Tabel:"))
        self.combo_group_owners = QComboBox()
        self.combo_group_owners.addItems([
            "Każdy właściciel osobno [Opcja 1]", 
            "Grupuj współwłaścicieli w 1 wierszu (wg działki) [Opcja 2] (domyślnie)", 
            "Grupuj działki wg właściciela [Opcja 3]", 
            "Grupuj identyczne pakiety działek i współwłaścicieli [Opcja 4]",
            "Grupuj wg działki (Tabela 1, 2 i 5) ze scalaniem właścicieli w jednej komórce [Opcja 5]"
        ])
        self.combo_group_owners.blockSignals(True)
        self.combo_group_owners.setCurrentIndex(self.config.get('legal_group_owners', 1))
        self.combo_group_owners.blockSignals(False)
        self.combo_group_owners.currentIndexChanged.connect(self._on_group_changed)
        row1.addWidget(self.combo_group_owners)
        btn_legal_settings = QPushButton("⚙️ Ustawienia grupowania / wyglądu")
        btn_legal_settings.clicked.connect(self._open_grouping_settings_dialog)
        row1.addWidget(btn_legal_settings)
        row1.addStretch()
        sync_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_t5_street = QCheckBox("Zaciągaj ulicę do T5")
        self.chk_t5_street.setChecked(self.config.get('legal_t5_pull_street', False))
        self.chk_t5_street.toggled.connect(lambda checked: self.config.update({'legal_t5_pull_street': checked}))
        row2.addWidget(self.chk_t5_street)
        row2.addWidget(QLabel(" | "))

        self.chk_t5_city = QCheckBox("Zaciągaj miejscowość do T5")
        self.chk_t5_city.setToolTip(
            "Wypełnia kolumnę Miejscowość w Tabeli 5. Źródło (projekt, "
            "wypis albo adres właściciela) wybierzesz w Ustawieniach."
        )
        self.chk_t5_city.setChecked(self.config.get('legal_t5_pull_city', False))
        self.chk_t5_city.toggled.connect(lambda checked: self.config.update({'legal_t5_pull_city': checked}))
        row2.addWidget(self.chk_t5_city)
        row2.addWidget(QLabel(" | "))
        
        self.chk_dash_street = QCheckBox("W T3 zmień ulicę na '-' jeśli jest jak miasto")
        self.chk_dash_street.setChecked(self.config.get('legal_dash_same_street', False))
        self.chk_dash_street.toggled.connect(lambda checked: self.config.update({'legal_dash_same_street': checked}))
        row2.addWidget(self.chk_dash_street)
        row2.addWidget(QLabel(" | "))

        self.chk_sort_parcels = QCheckBox("Sortuj działki rosnąco")
        self.chk_sort_parcels.setChecked(self.config.get('legal_sort_parcels', False))
        self.chk_sort_parcels.toggled.connect(self._on_sort_parcels_toggled)
        row2.addWidget(self.chk_sort_parcels)
        row2.addStretch()

        btn_sync = QPushButton('🔄 Zaciągnij / Odśwież dane z bazy Właścicieli')
        btn_sync.setObjectName('btn_primary')
        btn_sync.clicked.connect(lambda: self._sync_with_owners(show_info=True))
        row2.addWidget(btn_sync)
        sync_layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.chk_merge_kw = QCheckBox("Tabela 1 i 2: Scalaj identyczne 'Nr KW' w sąsiadujących wierszach (np. dla Opcji 5)")
        self.chk_merge_kw.setChecked(self.config.get('legal_merge_kw_t1', False))
        self.chk_merge_kw.toggled.connect(self._on_merge_kw_toggled)
        row3.addWidget(self.chk_merge_kw)
        row3.addStretch()
        sync_layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Tabela 1/2 – działki:"))
        self.combo_t12_parcel_mode = QComboBox()
        self.combo_t12_parcel_mode.addItems([
            "w jednej komórce, nowe linie",
            "w jednej komórce, po przecinku",
            "każda działka osobny wiersz"
        ])
        self.combo_t12_parcel_mode.setCurrentIndex(self.config.get('legal_t12_multi_parcels_mode', 0))
        self.combo_t12_parcel_mode.currentIndexChanged.connect(self._on_t12_parcel_mode_changed)
        row4.addWidget(self.combo_t12_parcel_mode)

        row4.addWidget(QLabel("Właściciele:"))
        self.combo_t12_owner_mode = QComboBox()
        self.combo_t12_owner_mode.addItems([
            "w jednej komórce, nowe linie",
            "w jednej komórce, po przecinku",
            "osobne wiersze gdy możliwe"
        ])
        self.combo_t12_owner_mode.setCurrentIndex(self.config.get('legal_t12_multi_owners_mode', 0))
        self.combo_t12_owner_mode.currentIndexChanged.connect(self._on_t12_owner_mode_changed)
        row4.addWidget(self.combo_t12_owner_mode)
        row4.addStretch()
        sync_layout.addLayout(row4)

        layout.addWidget(sync_box)
        self.tabs = QTabWidget()

        tab1 = QWidget()
        ly_1a = QVBoxLayout(tab1)
        btn_row_1a = QHBoxLayout()
        btn_add_1a = QPushButton("+ Dodaj pusty wiersz")
        btn_add_1a.clicked.connect(self._add_row_1a)
        btn_del_1a = QPushButton("🗑️ Usuń wiersz")
        btn_del_1a.clicked.connect(lambda: self._del_row(self.table_1a))
        btn_merge_1a = QPushButton("🔗 Scal")
        btn_merge_1a.clicked.connect(lambda: self._manual_merge(self.table_1a))
        btn_unmerge_1a = QPushButton("✂️ Rozgrupuj")
        btn_unmerge_1a.clicked.connect(lambda: self._manual_unmerge(self.table_1a))
        btn_row_1a.addWidget(btn_add_1a)
        btn_row_1a.addWidget(btn_del_1a)
        btn_row_1a.addWidget(btn_merge_1a)
        btn_row_1a.addWidget(btn_unmerge_1a)
        btn_row_1a.addStretch()

        self.chk_extra_1a = QCheckBox("Pokaż Wysłano/Otrzymano")
        self.chk_extra_1a.setChecked(self.config.get('legal_show_extra_1a', False))
        self.chk_extra_1a.toggled.connect(self._toggle_extra_cols_1a)
        btn_row_1a.addWidget(self.chk_extra_1a)
        ly_1a.addLayout(btn_row_1a)

        self.table_1a = QTableWidget(0, 9)
        self.table_1a.setItemDelegate(self.multi_line_delegate)
        self.table_1a.setHorizontalHeaderLabels(["Lp", "Właściciel", "Nr Działki", "Montaż\n(Tak/Nie)", "Demontaż\n(Tak/Nie)", "Nr KW / Uwagi", "Wysłano", "Otrzymano", "Uwagi 2"])
        self.table_1a.setAlternatingRowColors(True)
        self._toggle_extra_cols_1a()
        h1a = self.table_1a.horizontalHeader()
        for i in range(9): h1a.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        ly_1a.addWidget(self.table_1a)
        self.tabs.addTab(tab1, "Tabela 1 - Przyłączane (Szablon 1)")

        tab2 = QWidget()
        ly_1b = QVBoxLayout(tab2)
        btn_row_1b = QHBoxLayout()
        btn_add_1b = QPushButton("+ Dodaj pusty wiersz")
        btn_add_1b.clicked.connect(self._add_row_1b)
        btn_del_1b = QPushButton("🗑️ Usuń wiersz")
        btn_del_1b.clicked.connect(lambda: self._del_row(self.table_1b))
        btn_merge_1b = QPushButton("🔗 Scal")
        btn_merge_1b.clicked.connect(lambda: self._manual_merge(self.table_1b))
        btn_unmerge_1b = QPushButton("✂️ Rozgrupuj")
        btn_unmerge_1b.clicked.connect(lambda: self._manual_unmerge(self.table_1b))
        btn_row_1b.addWidget(btn_add_1b)
        btn_row_1b.addWidget(btn_del_1b)
        btn_row_1b.addWidget(btn_merge_1b)
        btn_row_1b.addWidget(btn_unmerge_1b)
        btn_row_1b.addStretch()

        self.chk_extra_1b = QCheckBox("Pokaż Wysłano/Otrzymano")
        self.chk_extra_1b.setChecked(self.config.get('legal_show_extra_1b', False))
        self.chk_extra_1b.toggled.connect(self._toggle_extra_cols_1b)
        btn_row_1b.addWidget(self.chk_extra_1b)
        ly_1b.addLayout(btn_row_1b)

        self.table_1b = QTableWidget(0, 9)
        self.table_1b.setItemDelegate(self.multi_line_delegate)
        self.table_1b.setHorizontalHeaderLabels(["Lp", "Właściciel", "Nr Działki", "Montaż\n(Tak/Nie)", "Demontaż\n(Tak/Nie)", "Nr KW", "Wysłano", "Otrzymano", "Uwagi"])
        self.table_1b.setAlternatingRowColors(True)
        self.table_1b.itemChanged.connect(self._on_item_changed_1b)
        self._toggle_extra_cols_1b()
        h1b = self.table_1b.horizontalHeader()
        for i in range(9): h1b.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        ly_1b.addWidget(self.table_1b)
        self.tabs.addTab(tab2, "Tabela 2 - Pozostałe (Szablon 1)")

        tab3 = QWidget()
        ly2 = QVBoxLayout(tab3)
        btn_row_2 = QHBoxLayout()
        btn_add_2 = QPushButton("+ Dodaj pusty wiersz")
        btn_add_2.clicked.connect(self._add_row_2)
        btn_del_2 = QPushButton("🗑️ Usuń wiersz")
        btn_del_2.clicked.connect(lambda: self._del_row(self.table_2))
        btn_merge_2 = QPushButton("🔗 Scal")
        btn_merge_2.clicked.connect(lambda: self._manual_merge(self.table_2))
        btn_unmerge_2 = QPushButton("✂️ Rozgrupuj")
        btn_unmerge_2.clicked.connect(lambda: self._manual_unmerge(self.table_2))
        btn_row_2.addWidget(btn_add_2)
        btn_row_2.addWidget(btn_del_2)
        btn_row_2.addWidget(btn_merge_2)
        btn_row_2.addWidget(btn_unmerge_2)
        btn_row_2.addStretch()
        ly2.addLayout(btn_row_2)

        self.table_2 = QTableWidget(0, 16)
        self.table_2.setItemDelegate(self.multi_line_delegate)
        self.table_2.setHorizontalHeaderLabels(["Lp", "Nr Działki", "Właściciel", "Kod pocztowy", "Miasto", "Ulica", "Nr domu", "Nr tel", "Email", "Spadkobierca/Zarządca", "Kod 2", "Miasto 2", "Ulica 2", "Nr domu 2", "Nr tel 2", "Email 2"])
        self.table_2.setAlternatingRowColors(True)
        self.table_2.itemChanged.connect(self._on_item_changed_2)
        h2 = self.table_2.horizontalHeader()
        for i in range(16): h2.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        ly2.addWidget(self.table_2)
        self.tabs.addTab(tab3, "Tabela 3 - Wykaz szczegółowy (Szablon 2)")

        # Metryka w oknie przewijanym — przy mniejszym oknie programu pola
        # do wpisywania pozostają dostępne (pionowy pasek przewijania).
        tab4 = QWidget()
        tab4_outer = QVBoxLayout(tab4)
        tab4_outer.setContentsMargins(0, 0, 0, 0)
        tab4_scroll = QScrollArea()
        tab4_scroll.setWidgetResizable(True)
        tab4_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tab4_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tab4_inner = QWidget()
        ly_4 = QFormLayout(tab4_inner)
        ly_4.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        ly_4.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        ly_4.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        tab4_scroll.setWidget(tab4_inner)
        tab4_scroll.setMinimumHeight(160)
        tab4_outer.addWidget(tab4_scroll)
        self.t4_tabela = QLineEdit()
        ly_4.addRow("TABELA:", self.t4_tabela)
        self.t4_temat = QLineEdit()
        ly_4.addRow("TEMAT:", self.t4_temat)
        self.t4_nr_obi = QLineEdit()
        ly_4.addRow("NR OBI:", self.t4_nr_obi)
        self.t4_projektant = QLineEdit()
        ly_4.addRow("PROJEKTANT:", self.t4_projektant)
        self.t4_lokalizacja = QLineEdit()
        ly_4.addRow("LOKALIZACJA:", self.t4_lokalizacja)
        self.t4_inwestor = QLineEdit()
        ly_4.addRow("INWESTOR:", self.t4_inwestor)
        for field in (
            self.t4_tabela, self.t4_temat, self.t4_nr_obi,
            self.t4_projektant, self.t4_lokalizacja, self.t4_inwestor,
        ):
            field.setMinimumWidth(180)
            field.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )

        btn_save_defaults = QPushButton("💾 Zapisz aktualnie wpisane dane jako DOMYŚLNE dla nowych projektów")
        btn_save_defaults.setStyleSheet("margin-top: 20px; padding: 5px; background-color: #e9ecef;")
        btn_save_defaults.clicked.connect(self._save_global_defaults)
        ly_4.addRow("", btn_save_defaults)
        self.tabs.addTab(tab4, "Tabela 4 - Metryka (Szablon 3)")

        tab5 = QWidget()
        ly_5 = QVBoxLayout(tab5)
        btn_row_3 = QHBoxLayout()
        btn_add_3 = QPushButton("+ Dodaj pusty wiersz")
        btn_add_3.clicked.connect(self._add_row_3)
        btn_del_3 = QPushButton("🗑️ Usuń wiersz")
        btn_del_3.clicked.connect(lambda: self._del_row(self.table_3))
        btn_merge_3 = QPushButton("🔗 Scal komórki")
        btn_merge_3.clicked.connect(lambda: self._manual_merge(self.table_3))
        btn_unmerge_3 = QPushButton("✂️ Rozgrupuj komórki")
        btn_unmerge_3.clicked.connect(lambda: self._manual_unmerge(self.table_3))
        btn_row_3.addWidget(btn_add_3)
        btn_row_3.addWidget(btn_del_3)
        btn_row_3.addWidget(btn_merge_3)
        btn_row_3.addWidget(btn_unmerge_3)

        self.chk_group_odd = QCheckBox("Grupuj: Oddziały")
        self.chk_group_odd.setChecked(True)
        self.chk_group_tytul = QCheckBox("Grupuj: Tytuły Prawne")
        self.chk_group_tytul.setChecked(True)
        self.chk_group_urz = QCheckBox("Grupuj: Urządzenia")
        btn_apply_grouping = QPushButton("🔄 Zastosuj Auto-Grupowanie")
        btn_apply_grouping.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        btn_apply_grouping.clicked.connect(self._apply_auto_grouping_t5)
        btn_row_3.addWidget(self.chk_group_odd)
        btn_row_3.addWidget(self.chk_group_tytul)
        btn_row_3.addWidget(self.chk_group_urz)
        btn_row_3.addWidget(btn_apply_grouping)
        btn_row_3.addStretch()
        btn_edit_odd = QPushButton("✏️ Edytuj listę oddziałów")
        btn_edit_odd.clicked.connect(self._edit_odd_options)
        btn_row_3.addWidget(btn_edit_odd)
        ly_5.addLayout(btn_row_3)

        self.table_3 = QTableWidget(0, 17)
        self.table_3.setItemDelegate(self.multi_line_delegate)
        self.table_3.setHorizontalHeaderLabels(["Lp.", "Nazwa Oddziału", "Tytuł Prawny do nieruchomości", "Znaki Dokumentu", "Gmina", "Miejscowość", "Ulica", "Właściciel", "Użytkownik Wieczysty", "Numer księgi wieczystej", "Numer ewidencyjny działki", "Numer obrębu", "Rodzaje Urządzenia", "Ilość", "Długość linii (km)", "Zaszłość / Nowa Inwestycja", "Data nabycia tytułu prawnego"])
        self.table_3.setAlternatingRowColors(True)

        self.combo_delegate = ComboBoxDelegate(self._get_combo_items_for_col, self.table_3)
        self.table_3.setItemDelegateForColumn(1, self.combo_delegate)
        self.table_3.setItemDelegateForColumn(2, self.combo_delegate)
        self.table_3.setItemDelegateForColumn(12, self.combo_delegate)
        self.table_3.setItemDelegateForColumn(15, self.combo_delegate)

        h3 = self.table_3.horizontalHeader()
        for i in range(17): h3.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        ly_5.addWidget(self.table_3)
        self.tabs.addTab(tab5, "Tabela 5 - Wykaz końcowy (Szablon 3)")

        self.tabs.setMinimumHeight(320)
        layout.addWidget(self.tabs, 1)

        export_box = QGroupBox('Eksport do Twoich szablonów Excel (.xlsm / .xlsx)')
        export_box.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        export_layout = QVBoxLayout(export_box)

        paths_layout = QFormLayout()
        row1 = QHBoxLayout()
        self.tmpl_1_edit = QLineEdit()
        self.tmpl_1_edit.setPlaceholderText('Brak. Ustaw w zakładce Ustawienia')
        btn_tmpl1 = QPushButton('📂')
        btn_tmpl1.clicked.connect(lambda: self._browse_tmpl(self.tmpl_1_edit, 'legal_tmpl_1'))
        row1.addWidget(self.tmpl_1_edit)
        row1.addWidget(btn_tmpl1)
        paths_layout.addRow('Szablon 1 — Wykaz działek podmiotów pozostałych:', row1)

        row2 = QHBoxLayout()
        self.tmpl_2_edit = QLineEdit()
        self.tmpl_2_edit.setPlaceholderText('Brak. Ustaw w zakładce Ustawienia')
        btn_tmpl2 = QPushButton('📂')
        btn_tmpl2.clicked.connect(lambda: self._browse_tmpl(self.tmpl_2_edit, 'legal_tmpl_2'))
        row2.addWidget(self.tmpl_2_edit)
        row2.addWidget(btn_tmpl2)
        paths_layout.addRow('Szablon 2 — Wykaz właścicieli nieruchomości szczegółowy:', row2)

        row3 = QHBoxLayout()
        self.tmpl_3_edit = QLineEdit()
        self.tmpl_3_edit.setPlaceholderText('Brak. Ustaw w zakładce Ustawienia')
        btn_tmpl3 = QPushButton('📂')
        btn_tmpl3.clicked.connect(lambda: self._browse_tmpl(self.tmpl_3_edit, 'legal_tmpl_3'))
        row3.addWidget(self.tmpl_3_edit)
        row3.addWidget(btn_tmpl3)
        paths_layout.addRow('Szablon 3 — Nowa tabela końcowa:', row3)

        export_layout.addLayout(paths_layout)

        btns_layout = QHBoxLayout()
        btn_export_1 = QPushButton('📊 Wypełnij i zapisz: Szablon 1 (Tabele 1 i 2)')
        btn_export_1.setObjectName('btn_primary')
        btn_export_1.setMinimumHeight(40)
        btn_export_1.clicked.connect(self._export_format_1)
        btns_layout.addWidget(btn_export_1)

        btn_export_2 = QPushButton('📊 Wypełnij i zapisz: Szablon 2 (Tabela 3)')
        btn_export_2.setObjectName('btn_accent')
        btn_export_2.setMinimumHeight(40)
        btn_export_2.clicked.connect(self._export_format_2)
        btns_layout.addWidget(btn_export_2)

        btn_export_3 = QPushButton('📊 Wypełnij i zapisz: Szablon 3 (Tabela końcowa)')
        btn_export_3.setObjectName('btn_accent')
        btn_export_3.setMinimumHeight(40)
        btn_export_3.clicked.connect(self._export_format_3)
        btns_layout.addWidget(btn_export_3)

        export_layout.addLayout(btns_layout)
        layout.addWidget(export_box)

        self.table_1a.installEventFilter(self)
        self.table_1b.installEventFilter(self)
        self.table_2.installEventFilter(self)
        self.table_3.installEventFilter(self)

        for t in [self.table_1a, self.table_1b, self.table_2, self.table_3]:
            sc_c = QShortcut(QKeySequence("Ctrl+C"), t)
            sc_c.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc_c.activated.connect(lambda tbl=t: self._copy_cells(tbl))

            sc_v = QShortcut(QKeySequence("Ctrl+V"), t)
            sc_v.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc_v.activated.connect(lambda tbl=t: self._paste_cells(tbl))

            sc_del = QShortcut(QKeySequence("Delete"), t)
            sc_del.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc_del.activated.connect(lambda tbl=t: self._delete_cells(tbl))

    def _on_merge_kw_toggled(self, checked):
        self.config['legal_merge_kw_t1'] = checked
        self._renumber_and_span_t1(self.table_1a)
        self._renumber_and_span_t1(self.table_1b)

    def _save_global_defaults(self):
        self.config['legal_default_tabela'] = self.t4_tabela.text()
        self.config['legal_default_projektant'] = self.t4_projektant.text()
        self.config['legal_default_lokalizacja'] = self.t4_lokalizacja.text()
        import sys
        if getattr(sys, 'frozen', False): cfg_path = Path(sys.executable).parent.resolve() / 'dane' / 'app_config.json'
        else: cfg_path = Path(__file__).parent.parent.resolve() / 'dane' / 'app_config.json'
        
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Zapisano", "Ustawienia zostały zapisane jako globalne i będą podpowiadane przy nowych projektach.")
        except Exception as e:
            QMessageBox.warning(self, "Błąd", f"Nie udało się zapisać ustawień: {e}")

    def _toggle_extra_cols_1a(self):
        show = self.chk_extra_1a.isChecked()
        self.table_1a.setColumnHidden(6, not show)
        self.table_1a.setColumnHidden(7, not show)
        self.table_1a.setColumnHidden(8, not show)
        self.config['legal_show_extra_1a'] = show

    def _toggle_extra_cols_1b(self):
        show = self.chk_extra_1b.isChecked()
        self.table_1b.setColumnHidden(6, not show)
        self.table_1b.setColumnHidden(7, not show)
        self.table_1b.setColumnHidden(8, not show)
        self.config['legal_show_extra_1b'] = show

    def _apply_auto_grouping_t5(self):
        self.table_3.clearSpans()
        rows = self.table_3.rowCount()
        if rows == 0: return

        blocks = []
        start_r = 0
        while start_r < rows:
            it_w = self.table_3.item(start_r, 7)
            w_val = it_w.text().strip() if it_w else ""
            it_uw = self.table_3.item(start_r, 8)
            uw_val = it_uw.text().strip() if it_uw else ""
            
            end_r = start_r + 1
            while end_r < rows:
                next_w = self.table_3.item(end_r, 7)
                next_w_val = next_w.text().strip() if next_w else ""
                next_uw = self.table_3.item(end_r, 8)
                next_uw_val = next_uw.text().strip() if next_uw else ""
                
                if w_val == next_w_val and uw_val == next_uw_val and (w_val != "" or uw_val != ""): end_r += 1
                else: break
            
            blocks.append((start_r, end_r))
            start_r = end_r

        current_lp = 1
        for (s_r, e_r) in blocks:
            for r in range(s_r, e_r):
                it_lp = self.table_3.item(r, 0)
                if it_lp: it_lp.setText(f"{current_lp}.")
            current_lp += 1

        force_group_cols = [0, 3, 7, 8]
        if self.chk_group_odd.isChecked(): force_group_cols.append(1) 
        if self.chk_group_tytul.isChecked(): force_group_cols.append(2) 
        
        for (s_r, e_r) in blocks:
            span_len = e_r - s_r
            if span_len > 1:
                for c in force_group_cols:
                    self.table_3.setSpan(s_r, c, span_len, 1)

        cols_to_cond_group = [4, 5, 6, 9, 16]
        if self.chk_group_urz.isChecked(): cols_to_cond_group.append(12)
        
        for c in cols_to_cond_group:
            s_r = 0
            while s_r < rows:
                it = self.table_3.item(s_r, c)
                val = it.text().strip() if it else ""
                it_w = self.table_3.item(s_r, 7)
                w_val = it_w.text().strip() if it_w else ""
                
                e_r = s_r + 1
                while e_r < rows:
                    it_next = self.table_3.item(e_r, c)
                    next_val = it_next.text().strip() if it_next else ""
                    it_next_w = self.table_3.item(e_r, 7)
                    next_w_val = it_next_w.text().strip() if it_next_w else ""
                    
                    if next_val == val and val != "" and w_val == next_w_val: e_r += 1
                    else: break
                
                if e_r - s_r > 1: self.table_3.setSpan(s_r, c, e_r - s_r, 1)
                s_r = e_r

        self.table_3.viewport().update()

    def _browse_tmpl(self, line_edit, config_key):
        from utils.templates import (
            LEGAL_TITLES_FOLDER_NAMES,
            resolve_template_start_directory,
        )

        start_dir = resolve_template_start_directory(
            self.config,
            config_key='path_tytuly',
            folder_names=LEGAL_TITLES_FOLDER_NAMES,
            current_path=line_edit.text(),
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            'Wybierz szablon Excel',
            str(start_dir),
            'Excel (*.xlsx *.xlsm)',
        )
        if path:
            line_edit.setText(path)
            self.config[config_key] = path

    def set_project(self, project: dict):
        self.active_project = project
        self._load_state()

    def _load_state(self):
        self.tmpl_1_edit.setText(self.config.get('legal_tmpl_1', ''))
        self.tmpl_2_edit.setText(self.config.get('legal_tmpl_2', ''))
        self.tmpl_3_edit.setText(self.config.get('legal_tmpl_3', ''))
        self.chk_extra_1a.setChecked(self.config.get('legal_show_extra_1a', False))
        self.chk_extra_1b.setChecked(self.config.get('legal_show_extra_1b', False))
        self._toggle_extra_cols_1a()
        self._toggle_extra_cols_1b()

        if hasattr(self, 'chk_merge_kw'):
            self.chk_merge_kw.blockSignals(True)
            self.chk_merge_kw.setChecked(self.config.get('legal_merge_kw_t1', False))
            self.chk_merge_kw.blockSignals(False)

        path_str = self.active_project.get('path', '')
        if not path_str: return

        try:
            with open(Path(path_str) / "legal_deleted.json", 'r', encoding='utf-8') as f:
                self.deleted_keys = set(json.load(f))
        except: self.deleted_keys = set()

        self._load_table_from_json(self.table_1a, Path(path_str) / "legal_1a_data.json", 9)
        self._load_table_from_json(self.table_1b, Path(path_str) / "legal_1b_data.json", 9)
        self._load_table_from_json(self.table_2, Path(path_str) / "legal_2_data.json", 16)
        self._load_table_from_json(self.table_3, Path(path_str) / "legal_3_data.json", 17)

        self._renumber_and_span_t1(self.table_1a)
        self._renumber_and_span_t1(self.table_1b)
        self._renumber(self.table_2)
        self._apply_auto_grouping_t5()

        t4_data = {}
        t4_path = Path(path_str) / "legal_t4_data.json"
        if t4_path.exists():
            try:
                with open(t4_path, 'r', encoding='utf-8') as f:
                    t4_data = json.load(f)
            except: pass

        val_tabela = t4_data.get('t4_tabela', self.active_project.get('t4_tabela', ''))
        if not val_tabela: val_tabela = self.config.get('legal_default_tabela', 'Tytuły prawne do nieruchomości')
        self.t4_tabela.setText(val_tabela)

        val_temat = t4_data.get('t4_temat', self.active_project.get('t4_temat', ''))
        self.t4_temat.setText(val_temat)

        val_obi = t4_data.get('t4_nr_obi', self.active_project.get('t4_nr_obi', ''))
        if not val_obi: val_obi = self.active_project.get('symbol', '')
        self.t4_nr_obi.setText(val_obi)

        val_proj = t4_data.get('t4_projektant', self.active_project.get('t4_projektant', ''))
        if not val_proj: val_proj = self.config.get('legal_default_projektant', '')
        self.t4_projektant.setText(val_proj)

        val_lok = t4_data.get('t4_lokalizacja', self.active_project.get('t4_lokalizacja', ''))
        if not val_lok: val_lok = self.config.get('legal_default_lokalizacja', '')
        self.t4_lokalizacja.setText(val_lok)

        val_inw = t4_data.get('t4_inwestor', self.active_project.get('t4_inwestor', ''))
        if not val_inw: val_inw = "Energa-Operator S.A."
        self.t4_inwestor.setText(val_inw)

        self.table_1a.resizeRowsToContents()
        self.table_1b.resizeRowsToContents()
        self.table_2.resizeRowsToContents()
        self.table_3.resizeRowsToContents()

    def _load_table_from_json(self, table, filepath, cols):
        table.setRowCount(0)
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for r_data in data:
                        key = r_data.pop() if len(r_data) > cols else None
                        r = table.rowCount()
                        table.insertRow(r)
                        for c in range(min(cols, len(r_data))):
                            it = QTableWidgetItem(str(r_data[c]))
                            if c == 0 and key: it.setData(Qt.ItemDataRole.UserRole, key)
                            table.setItem(r, c, it)
            except: pass

    def _save_state(self, silent=False):
        path_str = self.active_project.get('path', '')
        if not path_str: return
        
        try:
            with open(Path(path_str) / "legal_deleted.json", 'w', encoding='utf-8') as f:
                json.dump(list(self.deleted_keys), f, ensure_ascii=False)
        except: pass

        self._save_table_to_json(self.table_1a, Path(path_str) / "legal_1a_data.json", 9)
        self._save_table_to_json(self.table_1b, Path(path_str) / "legal_1b_data.json", 9)
        self._save_table_to_json(self.table_2, Path(path_str) / "legal_2_data.json", 16)
        self._save_table_to_json(self.table_3, Path(path_str) / "legal_3_data.json", 17)

        t4_data = {
            't4_tabela': self.t4_tabela.text(), 't4_temat': self.t4_temat.text(), 't4_nr_obi': self.t4_nr_obi.text(),
            't4_projektant': self.t4_projektant.text(), 't4_lokalizacja': self.t4_lokalizacja.text(), 't4_inwestor': self.t4_inwestor.text()
        }
        try:
            with open(Path(path_str) / "legal_t4_data.json", 'w', encoding='utf-8') as f:
                json.dump(t4_data, f, ensure_ascii=False, indent=2)
        except: pass

        self.active_project.update(t4_data)
        if not silent: QMessageBox.information(self, "Zapisano", "Stan wszystkich tabel oraz wpisane dane zostały zapisane w folderze projektu.")

    def _save_table_to_json(self, table, filepath, cols):
        data = []
        for r in range(table.rowCount()):
            row_data = []
            key = None
            for c in range(cols):
                w = table.cellWidget(r, c)
                if w and isinstance(w, QComboBox):
                    row_data.append(w.currentText())
                    it = table.item(r, c)
                    if c == 0 and it: key = it.data(Qt.ItemDataRole.UserRole)
                else:
                    it = table.item(r, c)
                    if it:
                        row_data.append(it.text())
                        if c == 0: key = it.data(Qt.ItemDataRole.UserRole)
                    else: row_data.append("")
            row_data.append(key or "")
            data.append(row_data)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def _on_item_changed_1b(self, item):
        row = item.row()
        col = item.column()
        it_lp = self.table_1b.item(row, 0)
        if not it_lp: return
        key = it_lp.data(Qt.ItemDataRole.UserRole)
        if not key: return

        if key not in self.records_1b: self.records_1b[key] = {}
        val = item.text().strip()
        cols_map = {3: 'montaz', 4: 'demontaz', 5: 'kw', 6: 'wyslano', 7: 'otrzymano', 8: 'uwagi'}
        if col in cols_map: self.records_1b[key][cols_map[col]] = val

    def _on_item_changed_2(self, item):
        row = item.row()
        col = item.column()
        it_lp = self.table_2.item(row, 0)
        if not it_lp: return
        key = it_lp.data(Qt.ItemDataRole.UserRole)
        if not key: return

        if key not in self.records_2: self.records_2[key] = {}
        val = item.text().strip()
        cols_map = {3: 'zip', 4: 'city', 5: 'street', 6: 'house', 7: 'tel', 8: 'email'}
        if col in cols_map: self.records_2[key][cols_map[col]] = val
        elif col >= 9: self.records_2[key][str(col)] = val

    def _add_row_1a(self):
        r = self.table_1a.rowCount()
        self.table_1a.insertRow(r)
        self.table_1a.setItem(r, 0, QTableWidgetItem(f"{r+1}."))
        self.table_1a.setItem(r, 3, QTableWidgetItem("Tak"))
        self.table_1a.setItem(r, 4, QTableWidgetItem("Nie"))

    def _add_row_1b(self):
        r = self.table_1b.rowCount()
        self.table_1b.insertRow(r)
        self.table_1b.setItem(r, 0, QTableWidgetItem(f"{r+1}."))
        self.table_1b.setItem(r, 3, QTableWidgetItem("Nie"))
        self.table_1b.setItem(r, 4, QTableWidgetItem("Nie"))

    def _add_row_3(self):
        r = self.table_3.rowCount()
        self.table_3.insertRow(r)
        self.table_3.setItem(r, 0, QTableWidgetItem(f"{r+1}."))
        self.table_3.setItem(r, 1, QTableWidgetItem("Gdańsk"))
        self.table_3.setItem(r, 13, QTableWidgetItem("0"))
        self.table_3.setItem(r, 14, QTableWidgetItem("0"))

    def _add_row_2(self):
        r = self.table_2.rowCount()
        self.table_2.insertRow(r)
        self.table_2.setItem(r, 0, QTableWidgetItem(f"{r+1}."))

    def _del_row(self, table):
        selected_rows = set()
        for idx in table.selectionModel().selectedIndexes(): selected_rows.add(idx.row())
        rows = sorted(list(selected_rows), reverse=True)
        if not rows: return
        for r in rows:
            it = table.item(r, 0)
            if it:
                key = it.data(Qt.ItemDataRole.UserRole)
                if key: self.deleted_keys.add(key)
            table.removeRow(r)

    def _insert_to_table(self, table, key, row_data):
        r = table.rowCount()
        table.insertRow(r)
        for c, val in enumerate(row_data):
            it = QTableWidgetItem(str(val))
            if c == 0 and key: it.setData(Qt.ItemDataRole.UserRole, key)
            table.setItem(r, c, it)

    def set_owners(self, owners: list):
        self.owners = owners

    def set_parcels(self, parcels: list):
        self.parcels = parcels

    def _parse_street_and_house(self, address_str: str):
        addr = address_str.split(',')[0].strip()
        if addr.lower().startswith("ul."): addr = addr[3:].strip()
        elif addr.lower().startswith("ul "): addr = addr[3:].strip()

        m = re.search(r'\s+(\d+[a-zA-Z]*(?:/\d+[a-zA-Z]*)?)$', addr)
        if m:
            house = m.group(1).strip()
            street = addr[:m.start()].strip()
            return street, house
        m2 = re.search(r'\d', addr)
        if m2:
            idx = m2.start()
            street = addr[:idx].strip()
            house = addr[idx:].strip()
            return street, house
        return addr, ""

    def _sort_whole_table(self, table, col_idx):
        def natural_sort_key(val):
            first_val = val.split('\n')[0].strip() if val else ""
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', first_val)]

        row_count = table.rowCount()
        col_count = table.columnCount()
        
        rows_data = []
        for r in range(row_count):
            it_val = table.item(r, col_idx)
            val = it_val.text() if it_val else ""
            
            row_items = []
            for c in range(col_count):
                row_items.append(table.takeItem(r, c))
            rows_data.append((natural_sort_key(val), row_items))
            
        rows_data.sort(key=lambda x: x[0])
        
        table.setRowCount(0)
        for _, row_items in rows_data:
            r = table.rowCount()
            table.insertRow(r)
            for c, it in enumerate(row_items):
                if it:
                    table.setItem(r, c, it)

    def _renumber_and_span_t1(self, table):
        table.clearSpans()
        rows = table.rowCount()
        if rows == 0: return

        current_lp = 0
        start_r = 0
        while start_r < rows:
            owner_val = table.item(start_r, 1).text().strip() if table.item(start_r, 1) else ""
            
            end_r = start_r + 1
            while end_r < rows:
                next_owner_val = table.item(end_r, 1).text().strip() if table.item(end_r, 1) else ""
                if next_owner_val == owner_val and owner_val != "": end_r += 1
                else: break
            
            current_lp += 1
            for r in range(start_r, end_r):
                it = table.item(r, 0)
                if it: it.setText(f"{current_lp}.")
            
            span_length = end_r - start_r
            if span_length > 1:
                table.setSpan(start_r, 0, span_length, 1)
                table.setSpan(start_r, 1, span_length, 1)
                
            for col in [3, 4]:
                sub_start = start_r
                while sub_start < end_r:
                    val = table.item(sub_start, col).text().strip() if table.item(sub_start, col) else ""
                    sub_end = sub_start + 1
                    while sub_end < end_r:
                        next_val = table.item(sub_end, col).text().strip() if table.item(sub_end, col) else ""
                        if next_val == val and val != "": sub_end += 1
                        else: break
                    if sub_end - sub_start > 1:
                        table.setSpan(sub_start, col, sub_end - sub_start, 1)
                    sub_start = sub_end
                    
            start_r = end_r
            
        if getattr(self, 'chk_merge_kw', None) and self.chk_merge_kw.isChecked():
            s_kw = 0
            while s_kw < rows:
                it_kw = table.item(s_kw, 5)
                val_kw = it_kw.text().strip() if it_kw else ""
                
                e_kw = s_kw + 1
                while e_kw < rows:
                    next_it = table.item(e_kw, 5)
                    next_val = next_it.text().strip() if next_it else ""
                    
                    if next_val == val_kw and val_kw != "": 
                        e_kw += 1
                    else: 
                        break
                
                if e_kw - s_kw > 1:
                    table.setSpan(s_kw, 5, e_kw - s_kw, 1)
                
                s_kw = e_kw

        table.viewport().update()

    def _renumber(self, table):
        current_lp = 0
        last_key = None
        for r in range(table.rowCount()):
            it = table.item(r, 0)
            if not it: continue
            key = it.data(Qt.ItemDataRole.UserRole)
            if key != last_key:
                current_lp += 1
                last_key = key
            it.setText(f"{current_lp}.")

    def _sync_with_owners(self, show_info=True):
        if self.deleted_keys:
            reply = QMessageBox.question(self, 'Przywracanie usuniętych', 'Wykryto wcześniej usunięte wiersze.\nCzy chcesz je przywrócić na nowo do tabel?\n\n(Dzięki unikalnym identyfikatorom, Twoje ręczne edycje w już istniejących wierszach są w pełni bezpieczne i nie zostaną zmienione).', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes: self.deleted_keys.clear()

        exclude_dead_noaddr = self.config.get('legal_exclude_dead_missing', True)
        sep_mode = self.combo_owner_sep.currentIndex()
        group_mode = self.config.get('legal_group_owners', 1)
        multi_parcels_mode = self.config.get('legal_t12_multi_parcels_mode', 0)
        multi_owners_mode = self.config.get('legal_t12_multi_owners_mode', 0)
        # Szczegółowa opcja: w trybie grupowania działek wg właściciela rozbij wiele działek na osobne wiersze.
        if group_mode == 2 and multi_parcels_mode == 2:
            group_mode = 0
        pull_t5_street = self.chk_t5_street.isChecked()
        t5_street_source = self.config.get('legal_t5_street_source', 0)
        pull_t5_city = self.chk_t5_city.isChecked()
        t5_city_source = self.config.get('legal_t5_city_source', 0)
        project_city = str(self.active_project.get('city', '') or '').strip()
        dash_t3_street = self.chk_dash_street.isChecked()
        sort_parcels = self.chk_sort_parcels.isChecked()

        def natural_sort_key(s): return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]
        def pair_format_old(name: str) -> str: return name.replace(' i ', '\n') if sep_mode == 1 else name
        def pair_key_alt(name: str) -> str: return name.replace(' i ', '\n')

        def build_rowmap(table: QTableWidget):
            m = {}
            for r in range(table.rowCount()):
                it = table.item(r, 0)
                if not it: continue
                k = it.data(Qt.ItemDataRole.UserRole)
                if k: m[k] = r
            return m

        rowmap_1a = build_rowmap(self.table_1a)
        rowmap_1b = build_rowmap(self.table_1b)
        rowmap_2 = build_rowmap(self.table_2)
        rowmap_3 = build_rowmap(self.table_3)

        exist_1a = set(rowmap_1a.keys())
        exist_1b = set(rowmap_1b.keys())
        exist_2 = set(rowmap_2.keys())
        exist_3 = set(rowmap_3.keys())

        added = 0
        przylacza_grouped = {}
        pozostale_grouped = {}
        t5_grouped = {}
        mode3_przylacza_rows = {}
        mode3_pozostale_rows = {}

        join_char_mode4 = "\n" if sep_mode == 1 else ", "
        parcel_join_char_t12 = ", " if multi_parcels_mode == 1 else "\n"
        owner_join_char_t12 = ", " if multi_owners_mode == 1 else "\n"

        owners_for_sync = []
        for src_owner in self.owners:
            # Opcja 1: każdy właściciel osobno, czyli parę rozbijamy na dwie osoby.
            if group_mode == 0 and self.config.get('legal_split_couples_option1', True) and src_owner.get('is_couple'):
                separate = src_owner.get('name_separate') or src_owner.get('full_name', '')
                parts = [x.strip() for x in re.split(r'\s+i\s+', separate) if x.strip()]
                if len(parts) == 2:
                    for part in parts:
                        clone = dict(src_owner)
                        clone['full_name'] = part
                        clone['name_plural'] = part
                        clone['name_separate'] = part
                        clone['is_couple'] = False
                        owners_for_sync.append(clone)
                    continue
            owners_for_sync.append(src_owner)

        for o in owners_for_sync:
            if exclude_dead_noaddr:
                if o.get('is_dead', False): continue
                addr = o.get('address', '')
                if not addr.strip() or not re.search(r'\d{2}-\d{3}', addr): continue

            base_name = o.get('full_name', f"{o.get('first_name','')} {o.get('last_name','')}")
            name_t12 = base_name if group_mode == 4 else pair_format_old(base_name)
            name_t5 = base_name

            addr = o.get('address', '')
            zip_code, city, street, house = "", "", "", ""
            addr_parts = addr.split(',')
            if len(addr_parts) > 1:
                city_part = addr_parts[-1].strip()
                m = re.match(r'(\d{2}-\d{3})\s+(.*)', city_part)
                if m: zip_code, city = m.group(1), m.group(2)
                else: city = city_part

            street, house = self._parse_street_and_house(addr)
            
            street_t3 = street
            if dash_t3_street and city and street:
                if city.strip().lower() == street.strip().lower():
                    street_t3 = "-"

            o_parcels = o.get('parcels', [])
            if not o_parcels: o_parcels = [{'number': n, 'kw': ''} for n in o.get('parcel_numbers', [])]

            if sort_parcels:
                o_parcels.sort(key=lambda x: natural_sort_key(x.get('number', x) if isinstance(x, dict) else str(x)))

            przylacza = []
            pozostale = []

            for p in o_parcels:
                p_num = p.get('number', '') if isinstance(p, dict) else str(p)
                p_kw = p.get('kw', '') if isinstance(p, dict) else ''
                p_addr = p.get('parcel_address', '') if isinstance(p, dict) else ''

                if pull_t5_street:
                    if t5_street_source == 0:
                        street_t5 = street
                    elif t5_street_source == 1:
                        street_t5 = f"{street} {house}".strip() if street else house
                    else:
                        street_t5 = p_addr if p_addr else o.get('parcel_street', '')
                        # Wypis trzyma miejscowość i ulicę razem
                        # („MAKI, WYBICKIEGO J. 50”) — bierzemy samą ulicę.
                        street_t5 = split_parcel_location(street_t5).street or street_t5
                else:
                    street_t5 = ""

                # Miejscowość: własne źródło, z zapasem w danych projektu.
                if pull_t5_city:
                    if t5_city_source == 1:
                        city_t5 = split_parcel_location(p_addr).city if p_addr else ''
                        if not city_t5:
                            city_t5 = str(o.get('city', '') or '').strip()
                    elif t5_city_source == 2:
                        city_t5 = str(o.get('city', '') or '').strip()
                    else:
                        city_t5 = project_city
                    if not city_t5:
                        city_t5 = project_city
                else:
                    city_t5 = ""

                key_t5 = f"{base_name}::{p_num}"
                key_t5_alt = f"{pair_key_alt(base_name)}::{p_num}"

                cat = ""
                for pp in self.parcels:
                    if str(pp['number']).strip() == str(p_num).strip():
                        cat = pp.get('category', '')
                        break

                is_przylacze = "Przyłącze" in cat
                has_budowa = "Budowa" in cat or "Pełna" in cat
                has_demontaz = "Demontaż" in cat or "Pełna" in cat

                m_val = "Tak" if has_budowa else "Nie"
                d_val = "Tak" if has_demontaz else "Nie"

                if group_mode in [1, 4, 5]:
                    if is_przylacze:
                        if p_num not in przylacza_grouped: przylacza_grouped[p_num] = {'owners': [], 'kw': [], 'm': "Tak", 'd': d_val}
                        if name_t12 not in przylacza_grouped[p_num]['owners']: przylacza_grouped[p_num]['owners'].append(name_t12)
                        if p_kw and p_kw not in przylacza_grouped[p_num]['kw']: przylacza_grouped[p_num]['kw'].append(p_kw)

                    if has_budowa or has_demontaz or not is_przylacze:
                        if p_num not in pozostale_grouped: pozostale_grouped[p_num] = {'owners': [], 'kw': [], 'm': m_val, 'd': d_val}
                        if name_t12 not in pozostale_grouped[p_num]['owners']: pozostale_grouped[p_num]['owners'].append(name_t12)
                        if p_kw and p_kw not in pozostale_grouped[p_num]['kw']: pozostale_grouped[p_num]['kw'].append(p_kw)

                elif group_mode == 0:
                    key_base = f"{base_name}::{p_num}"
                    key_base_alt = f"{pair_key_alt(base_name)}::{p_num}"
                    if key_base not in self.deleted_keys and key_base_alt not in self.deleted_keys:
                        if is_przylacze: przylacza.append({'num': p_num, 'kw': p_kw, 'm': "Tak", 'd': d_val})
                        if has_budowa or has_demontaz or not is_przylacze: pozostale.append({'num': p_num, 'kw': p_kw, 'm': m_val, 'd': d_val})

                else:
                    if is_przylacze: przylacza.append({'num': p_num, 'kw': p_kw, 'm': "Tak", 'd': d_val})
                    if has_budowa or has_demontaz or not is_przylacze: pozostale.append({'num': p_num, 'kw': p_kw, 'm': m_val, 'd': d_val})

                if group_mode in [4, 5]:
                    p_muni = p.get('municipality', o.get('municipality', '')) if isinstance(p, dict) else o.get('municipality', '')
                    p_prec_num = p.get('precinct_number', o.get('precinct_number', '')) if isinstance(p, dict) else o.get('precinct_number', '')
                    if p_num not in t5_grouped:
                        t5_grouped[p_num] = {
                            'owners': [], 'kw': [], 'gmina': p_muni,
                            'miejscowosc': city_t5, 'ulica': street_t5, 'obreb': p_prec_num
                        }
                    if name_t5 not in t5_grouped[p_num]['owners']: t5_grouped[p_num]['owners'].append(name_t5)
                    if p_kw and p_kw not in t5_grouped[p_num]['kw']: t5_grouped[p_num]['kw'].append(p_kw)
                else:
                    if key_t5 in self.deleted_keys or key_t5_alt in self.deleted_keys: continue

                    if (key_t5 not in exist_3) and (key_t5_alt not in exist_3):
                        p_muni = p.get('municipality', o.get('municipality', '')) if isinstance(p, dict) else o.get('municipality', '')
                        p_prec_num = p.get('precinct_number', o.get('precinct_number', '')) if isinstance(p, dict) else o.get('precinct_number', '')
                        self._insert_to_table(self.table_3, key_t5, [
                            "", "Gdańsk", "", "", p_muni, city_t5, street_t5, name_t5, "",
                            p_kw, p_num, p_prec_num, "", "0", "0", "", ""
                        ])
                        new_r = self.table_3.rowCount() - 1
                        rowmap_3[key_t5] = new_r
                        exist_3.add(key_t5)
                    else:
                        r_exist = rowmap_3.get(key_t5)
                        if r_exist is None: r_exist = rowmap_3.get(key_t5_alt)
                        if r_exist is not None:
                            it_owner = self.table_3.item(r_exist, 7)
                            if it_owner and it_owner.text() != name_t5: it_owner.setText(name_t5)
                            it_street = self.table_3.item(r_exist, 6)
                            if it_street and it_street.text() != street_t5: it_street.setText(street_t5)

            if group_mode == 0:
                if przylacza:
                    for p in przylacza:
                        key1a = f"{base_name}::PRZYL::{p['num']}"
                        key1a_alt = f"{pair_key_alt(base_name)}::PRZYL::{p['num']}"
                        if (key1a not in self.deleted_keys and key1a_alt not in self.deleted_keys and key1a not in exist_1a and key1a_alt not in exist_1a):
                            self._insert_to_table(self.table_1a, key1a, ["", name_t12, str(p['num']), str(p['m']), str(p['d']), str(p['kw']), "", "", ""])
                            exist_1a.add(key1a)
                            rowmap_1a[key1a] = self.table_1a.rowCount() - 1
                            added += 1

                if pozostale:
                    for p in pozostale:
                        key1b = f"{base_name}::POZ::{p['num']}"
                        key1b_alt = f"{pair_key_alt(base_name)}::POZ::{p['num']}"
                        if (key1b not in self.deleted_keys and key1b_alt not in self.deleted_keys and key1b not in exist_1b and key1b_alt not in exist_1b):
                            self._insert_to_table(self.table_1b, key1b, ["", name_t12, str(p['num']), str(p['m']), str(p['d']), str(p['kw']), "", "", ""])
                            exist_1b.add(key1b)
                            rowmap_1b[key1b] = self.table_1b.rowCount() - 1
                            added += 1

            elif group_mode == 2:
                g_przylacza = {}
                for p in przylacza:
                    k = (p['kw'], p['m'], p['d'])
                    g_przylacza.setdefault(k, []).append(str(p['num']))

                for k, nums in g_przylacza.items():
                    if sort_parcels: nums.sort(key=natural_sort_key)
                    p_nums_str = parcel_join_char_t12.join(nums)
                    key1a = f"{base_name}::PRZYL::{p_nums_str}"
                    key1a_alt = f"{pair_key_alt(base_name)}::PRZYL::{p_nums_str}"
                    if (key1a not in self.deleted_keys and key1a_alt not in self.deleted_keys and key1a not in exist_1a and key1a_alt not in exist_1a):
                        self._insert_to_table(self.table_1a, key1a, ["", name_t12, p_nums_str, k[1], k[2], k[0], "", "", ""])
                        exist_1a.add(key1a)
                        rowmap_1a[key1a] = self.table_1a.rowCount() - 1
                        added += 1

                g_pozostale = {}
                for p in pozostale:
                    k = (p['kw'], p['m'], p['d'])
                    g_pozostale.setdefault(k, []).append(str(p['num']))

                for k, nums in g_pozostale.items():
                    if sort_parcels: nums.sort(key=natural_sort_key)
                    p_nums_str = parcel_join_char_t12.join(nums)
                    key1b = f"{base_name}::POZ::{p_nums_str}"
                    key1b_alt = f"{pair_key_alt(base_name)}::POZ::{p_nums_str}"
                    if (key1b not in self.deleted_keys and key1b_alt not in self.deleted_keys and key1b not in exist_1b and key1b_alt not in exist_1b):
                        self._insert_to_table(self.table_1b, key1b, ["", name_t12, p_nums_str, k[1], k[2], k[0], "", "", ""])
                        exist_1b.add(key1b)
                        rowmap_1b[key1b] = self.table_1b.rowCount() - 1
                        added += 1

            elif group_mode == 3:
                g_przylacza = {}
                for p in przylacza:
                    k = (p['kw'], p['m'], p['d'])
                    g_przylacza.setdefault(k, []).append(str(p['num']))
                for k, nums in g_przylacza.items():
                    if sort_parcels: nums.sort(key=natural_sort_key)
                    p_nums_str = parcel_join_char_t12.join(nums)
                    row_key = (p_nums_str, k[0], k[1], k[2])
                    mode3_przylacza_rows.setdefault(row_key, []).append(base_name)

                g_pozostale = {}
                for p in pozostale:
                    k = (p['kw'], p['m'], p['d'])
                    g_pozostale.setdefault(k, []).append(str(p['num']))
                for k, nums in g_pozostale.items():
                    if sort_parcels: nums.sort(key=natural_sort_key)
                    p_nums_str = parcel_join_char_t12.join(nums)
                    row_key = (p_nums_str, k[0], k[1], k[2])
                    mode3_pozostale_rows.setdefault(row_key, []).append(base_name)

            key2 = f"{base_name}::ALL"
            key2_alt = f"{pair_key_alt(base_name)}::ALL"
            if (key2 not in exist_2 and key2_alt not in exist_2 and key2 not in self.deleted_keys and key2_alt not in self.deleted_keys):
                p_nums_list = [str(pp.get('number', pp)) for pp in o_parcels]
                if sort_parcels: p_nums_list.sort(key=natural_sort_key)
                p_nums_str = parcel_join_char_t12.join(p_nums_list)
                
                self._insert_to_table(self.table_2, key2, ["", p_nums_str, name_t5, zip_code, city, street_t3, house, "", "", "", "", "", "", "", "", ""])
                exist_2.add(key2)
                rowmap_2[key2] = self.table_2.rowCount() - 1

        if group_mode in [1, 4, 5]:
            przylacza_items = list(przylacza_grouped.items())
            for p_num, data in przylacza_items:
                key1a = f"GROUP::PRZYL::{p_num}"
                if key1a in self.deleted_keys: continue
                unique_kws = list(dict.fromkeys([k for k in data['kw'] if k]))
                o_str = owner_join_char_t12.join(data['owners'])
                k_str = ", ".join(unique_kws)

                if key1a not in exist_1a:
                    self._insert_to_table(self.table_1a, key1a, ["", o_str, str(p_num), data['m'], data['d'], k_str, "", "", ""])
                    exist_1a.add(key1a)
                    rowmap_1a[key1a] = self.table_1a.rowCount() - 1
                    added += 1
                else:
                    r_exist = rowmap_1a.get(key1a)
                    if r_exist is not None:
                        it_o = self.table_1a.item(r_exist, 1)
                        if it_o and it_o.text() != o_str: it_o.setText(o_str); added += 1
                        it_k = self.table_1a.item(r_exist, 5)
                        if it_k and k_str and it_k.text() != k_str: it_k.setText(k_str)

            pozostale_items = list(pozostale_grouped.items())
            for p_num, data in pozostale_items:
                key1b = f"GROUP::POZ::{p_num}"
                if key1b in self.deleted_keys: continue
                unique_kws = list(dict.fromkeys([k for k in data['kw'] if k]))
                o_str = owner_join_char_t12.join(data['owners'])
                k_str = ", ".join(unique_kws)

                if key1b not in exist_1b:
                    self._insert_to_table(self.table_1b, key1b, ["", o_str, str(p_num), data['m'], data['d'], k_str, "", "", ""])
                    exist_1b.add(key1b)
                    rowmap_1b[key1b] = self.table_1b.rowCount() - 1
                    added += 1
                else:
                    r_exist = rowmap_1b.get(key1b)
                    if r_exist is not None:
                        it_o = self.table_1b.item(r_exist, 1)
                        if it_o and it_o.text() != o_str: it_o.setText(o_str); added += 1
                        it_k = self.table_1b.item(r_exist, 5)
                        if it_k and k_str and it_k.text() != k_str: it_k.setText(k_str)

        if group_mode == 3:
            m3_przyl_items = list(mode3_przylacza_rows.items())
            for row_key, owners_list in m3_przyl_items:
                p_nums_str, kw, m, d = row_key
                o_str = (owner_join_char_t12 if multi_owners_mode in (0, 1) else join_char_mode4).join(owners_list)
                key1a = f"GROUP3::PRZYL::{p_nums_str}"
                if key1a in self.deleted_keys: continue

                if key1a not in exist_1a:
                    if self.config.get('legal_option4_owners_separate', True):
                        for single_o in owners_list:
                            self._insert_to_table(self.table_1a, key1a, ["", single_o, p_nums_str, m, d, kw, "", "", ""])
                    else:
                        self._insert_to_table(self.table_1a, key1a, ["", o_str, p_nums_str, m, d, kw, "", "", ""])
                    exist_1a.add(key1a)
                    added += 1
                else:
                    r_exist = rowmap_1a.get(key1a)
                    if r_exist is not None:
                        it_k = self.table_1a.item(r_exist, 5)
                        if it_k and kw and it_k.text() != kw: it_k.setText(kw)

            m3_poz_items = list(mode3_pozostale_rows.items())
            for row_key, owners_list in m3_poz_items:
                p_nums_str, kw, m, d = row_key
                o_str = (owner_join_char_t12 if multi_owners_mode in (0, 1) else join_char_mode4).join(owners_list)
                key1b = f"GROUP3::POZ::{p_nums_str}"
                if key1b in self.deleted_keys: continue

                if key1b not in exist_1b:
                    if self.config.get('legal_option4_owners_separate', True):
                        for single_o in owners_list:
                            self._insert_to_table(self.table_1b, key1b, ["", single_o, p_nums_str, m, d, kw, "", "", ""])
                    else:
                        self._insert_to_table(self.table_1b, key1b, ["", o_str, p_nums_str, m, d, kw, "", "", ""])
                    exist_1b.add(key1b)
                    added += 1
                else:
                    r_exist = rowmap_1b.get(key1b)
                    if r_exist is not None:
                        it_k = self.table_1b.item(r_exist, 5)
                        if it_k and kw and it_k.text() != kw: it_k.setText(kw)

        if group_mode in [4, 5]:
            t5_items = list(t5_grouped.items())
            for p_num, data in t5_items:
                key5 = f"GROUP5::T5::{p_num}"
                if key5 in self.deleted_keys: continue

                o_str = owner_join_char_t12.join(data['owners'])
                k_str = ", ".join(list(dict.fromkeys([k for k in data['kw'] if k])))

                if key5 not in exist_3:
                    self._insert_to_table(self.table_3, key5, [
                        "", "Gdańsk", "", "", data['gmina'], data['miejscowosc'], data['ulica'], o_str, "",
                        k_str, p_num, data['obreb'], "", "0", "0", "", ""
                    ])
                    exist_3.add(key5)
                    rowmap_3[key5] = self.table_3.rowCount() - 1
                    added += 1
                else:
                    r_exist = rowmap_3.get(key5)
                    if r_exist is not None:
                        it_o = self.table_3.item(r_exist, 7)
                        if it_o and it_o.text() != o_str: it_o.setText(o_str); added += 1
                        it_k = self.table_3.item(r_exist, 9)
                        if it_k and k_str and it_k.text() != k_str: it_k.setText(k_str)
                        it_street = self.table_3.item(r_exist, 6)
                        if it_street and it_street.text() != data['ulica']: it_street.setText(data['ulica'])

        if sort_parcels:
            self._sort_whole_table(self.table_1a, 2)
            self._sort_whole_table(self.table_1b, 2)
            self._sort_whole_table(self.table_2, 1)
            self._sort_whole_table(self.table_3, 10)

        self._renumber_and_span_t1(self.table_1a)
        self._renumber_and_span_t1(self.table_1b)
        self._renumber(self.table_2)
        self._apply_auto_grouping_t5()

        self.table_1a.resizeRowsToContents()
        self.table_1b.resizeRowsToContents()
        self.table_2.resizeRowsToContents()
        self.table_3.resizeRowsToContents()

        if show_info:
            QMessageBox.information(self, "Zakończono", f"Zaktualizowano / Dodano {added} powiązań do tabel.")

    def _auto_export_dir(self):
        """Podfolder projektu na tytuły prawne (albo ``None`` = pytaj)."""
        return project_output_dir(
            self.config, 'legal_titles', self.active_project.get('path', '')
        )

    def _ask_export_path(self, title: str, default_path: str):
        """Zwraca ścieżkę zapisu — automatyczną albo wskazaną w oknie."""
        auto_dir = self._auto_export_dir()
        if auto_dir is not None:
            return str(auto_dir / Path(default_path).name)
        path, _ = QFileDialog.getSaveFileName(
            self, title, default_path, 'Excel (*.xlsx)'
        )
        return path

    def _get_default_export_path(self, config_key: str, default_pattern: str):
        auto_dir = self._auto_export_dir()
        if auto_dir is not None:
            last_dir = str(auto_dir)
        else:
            last_dir = self.config.get('last_legal_export_dir', '')
            if not last_dir or not Path(last_dir).exists():
                last_dir = self.active_project.get('path', '')

        symbol = self.active_project.get('symbol', 'PROJEKT')
        city = self.active_project.get('city', 'Miejscowosc')
        suffix_mode = self.config.get('legal_filename_suffix', 0)
        suffix_chars = self.config.get('legal_suffix_chars', 4)

        if suffix_mode == 1: suffix = symbol[-suffix_chars:] if len(symbol) >= suffix_chars else symbol
        elif suffix_mode == 2: suffix = city
        else: suffix = symbol

        suffix = re.sub(r'[\\/*?:"<>|]', '_', suffix)

        filename = self.config.get(config_key, default_pattern).replace('{symbol}', suffix)
        if not filename.lower().endswith('.xlsx'): filename = filename.rsplit('.', 1)[0] + '.xlsx'

        return str(Path(last_dir) / filename) if last_dir else filename

    def _export_format_1(self):
        self._renumber_and_span_t1(self.table_1a)
        self._renumber_and_span_t1(self.table_1b)

        tmpl_path = self.tmpl_1_edit.text()
        if not tmpl_path or not Path(tmpl_path).exists():
            return QMessageBox.warning(self, 'Brak Szablonu', 'Wybierz najpierw istniejący szablon programu Excel.')

        default_path = self._get_default_export_path('legal_name_1', 'Wykaz_dzialek_podmiotow_{symbol}.xlsx')
        path = self._ask_export_path('Zapisz jako (Zawsze format .xlsx)', default_path)
        if not path: return
        if not path.endswith('.xlsx'): path += '.xlsx'

        self.config['last_legal_export_dir'] = str(Path(path).parent)

        col_mapping = [0, 2, 1, 3, 4, 5, 6, 7, 8]
        cols_1a = 9 if self.chk_extra_1a.isChecked() else 6

        data_1a = []
        for r in range(self.table_1a.rowCount()):
            row_data = [self.table_1a.item(r, i).text() if self.table_1a.item(r, i) else "" for i in col_mapping[:cols_1a]]
            data_1a.append(row_data)

        data_1b = []
        for r in range(self.table_1b.rowCount()):
            data_1b.append([self.table_1b.item(r, i).text() if self.table_1b.item(r, i) else "" for i in col_mapping])

        QMessageBox.information(self, 'Eksport w toku', 'Proszę czekać, program Microsoft Excel w tle wypełnia szablon (Może to potrwać kilka sekund)...')

        success, err = LegalTitlesExcelExporter.export_format_1(tmpl_path, path, data_1a, data_1b, cols_1a, self.table_1a, self.table_1b)
        if success: QMessageBox.information(self, 'Sukces', f'Wypełniono szablon 1:\n{path}')
        else: QMessageBox.critical(self, 'Błąd Excel', f'Wystąpił problem z silnikiem MS Excel:\n{err}')

    def _export_format_2(self):
        self._renumber(self.table_2)

        tmpl_path = self.tmpl_2_edit.text()
        if not tmpl_path or not Path(tmpl_path).exists():
            return QMessageBox.warning(self, 'Brak Szablonu', 'Wybierz najpierw istniejący szablon programu Excel.')

        default_path = self._get_default_export_path('legal_name_2', 'Wykaz_szczegolowy_{symbol}.xlsx')
        path = self._ask_export_path('Zapisz jako (Zawsze .xlsx)', default_path)
        if not path: return
        if not path.endswith('.xlsx'): path += '.xlsx'

        self.config['last_legal_export_dir'] = str(Path(path).parent)

        data_matrix = []
        for r in range(self.table_2.rowCount()):
            data_matrix.append([self.table_2.item(r, c).text() if self.table_2.item(r, c) else "" for c in range(16)])

        QMessageBox.information(self, 'Eksport w toku', 'Proszę czekać, program Microsoft Excel w tle wypełnia szablon (Może to potrwać kilka sekund)...')

        success, err = LegalTitlesExcelExporter.export_format_2(tmpl_path, path, data_matrix, 16, self.table_2)
        if success: QMessageBox.information(self, 'Sukces', f'Wypełniono szablon 2:\n{path}')
        else: QMessageBox.critical(self, 'Błąd Excel', f'Wystąpił problem z silnikiem MS Excel:\n{err}')

    def _export_format_3(self):
        self._apply_auto_grouping_t5()

        tmpl_path = self.tmpl_3_edit.text()
        if not tmpl_path or not Path(tmpl_path).exists():
            return QMessageBox.warning(self, 'Brak Szablonu', 'Wybierz najpierw istniejący szablon programu Excel.')

        default_path = self._get_default_export_path('legal_name_3', 'Tabela_koncowa_{symbol}.xlsx')
        path = self._ask_export_path('Zapisz jako (Zawsze .xlsx)', default_path)
        if not path: return
        if not path.endswith('.xlsx'): path += '.xlsx'

        self.config['last_legal_export_dir'] = str(Path(path).parent)

        data_matrix = []
        for r in range(self.table_3.rowCount()):
            row_data = []
            for c in range(17):
                w = self.table_3.cellWidget(r, c)
                if w and isinstance(w, QComboBox): row_data.append(w.currentText())
                else: row_data.append(self.table_3.item(r, c).text() if self.table_3.item(r, c) else "")
            data_matrix.append(row_data)

        QMessageBox.information(self, 'Eksport w toku', 'Proszę czekać, program Microsoft Excel w tle wypełnia szablon (Może to potrwać kilka sekund)...')

        t4_data = {
            'tabela': self.t4_tabela.text(), 'temat': self.t4_temat.text(), 'nr_obi': self.t4_nr_obi.text(),
            'projektant': self.t4_projektant.text(), 'lokalizacja': self.t4_lokalizacja.text(),
            'inwestor': self.t4_inwestor.text()
        }
        success, err = LegalTitlesExcelExporter.export_format_3(tmpl_path, path, data_matrix, t4_data, self.table_3)
        if success: QMessageBox.information(self, 'Sukces', f'Wypełniono szablon 3:\n{path}')
        else: QMessageBox.critical(self, 'Błąd Excel', f'Wystąpił problem z silnikiem MS Excel:\n{err}')