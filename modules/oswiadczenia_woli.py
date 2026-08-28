"""
decl_generator.py – Zakładka generowania oświadczeń woli
"""
import json
import re
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QGroupBox, QSplitter, QTextEdit, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QTableWidget, QTableWidgetItem, QFileDialog, QInputDialog,
    QProgressDialog, QCheckBox, QScrollArea, QFrame, QHeaderView,
    QAbstractItemView, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

class NoWheelComboBox(QComboBox):
    def wheelEvent(self, e): e.ignore()

class ManageExamplesDialog(QDialog):
    def __init__(self, examples: list, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Przykłady – {title}')
        self.setMinimumSize(500, 400)
        layout = QVBoxLayout(self)
        self.examples = list(examples)
        self.list_widget = QListWidget()
        for ex in self.examples: self.list_widget.addItem(ex)
        layout.addWidget(self.list_widget)
        add_row = QHBoxLayout()
        self.new_edit = QLineEdit()
        self.new_edit.setPlaceholderText('Nowy przykład...')
        add_row.addWidget(self.new_edit)
        btn_add = QPushButton('Dodaj')
        btn_add.clicked.connect(self._add)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)
        btn_row = QHBoxLayout()
        btn_edit = QPushButton('Edytuj zaznaczony')
        btn_edit.clicked.connect(self._edit)
        btn_row.addWidget(btn_edit)
        btn_del = QPushButton('Usuń zaznaczony')
        btn_del.clicked.connect(self._delete)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add(self):
        text = self.new_edit.text().strip()
        if text:
            self.examples.append(text)
            self.list_widget.addItem(text)
            self.new_edit.clear()

    def _delete(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.examples.pop(row)
            self.list_widget.takeItem(row)

    def _edit(self):
        item = self.list_widget.currentItem()
        if item:
            old_text = item.text()
            new_text, ok = QInputDialog.getText(self, "Edycja", "Zmień tekst przykładu:", QLineEdit.EchoMode.Normal, old_text)
            if ok and new_text.strip():
                row = self.list_widget.row(item)
                self.examples[row] = new_text.strip()
                item.setText(new_text.strip())
    def get_examples(self): return self.examples

def format_area_pl(val) -> str:
    if not val: return ""
    s = f"{float(val):.4f}".rstrip('0')
    if s.endswith('.'): return s[:-1] + ",00"
    if len(s.split('.')[1]) < 2: s += '0'
    return s.replace('.', ',')

class DeclGeneratorWidget(QWidget):
    owners_changed = Signal(list)

    def __init__(self, config: dict, examples: dict, save_callback=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.examples = examples
        self.save_callback = save_callback
        self.owners = []
        self.parcels = []
        self.checked_keys = set()
        self.parcel_groups = {}
        self.active_project_path = ''
        self.setAcceptDrops(True)
        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        b = self.config.get('decl_template_budowa', '')
        if b: self.template_budowa_edit.setText(b)
        d = self.config.get('decl_template_demontaz', '')
        if d: self.template_demontaz_edit.setText(d)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                lower = path.lower()
                if lower.endswith('.txt'):
                    self._import_group_txt(path)
                elif lower.endswith('.docx'):
                    if 'demonta' in lower: self.template_demontaz_edit.setText(path)
                    else: self.template_budowa_edit.setText(path)
                break

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        main_v = QVBoxLayout(inner)
        main_v.setSpacing(10)

        hdr = QLabel('📄 Generator Oświadczeń Woli')
        hdr.setStyleSheet('font-size:16px; font-weight:700;')
        main_v.addWidget(hdr)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel('Typ (dla podglądu i manualnego generowania pojedynczej osoby):'))
        self.type_combo = NoWheelComboBox()
        self.type_combo.addItems(['Budowa (oświadczenie woli)', 'Demontaż (oświadczenie woli)', 'Obie (Budowa + Demontaż)'])
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        main_v.addLayout(type_row)

        proj_box = QGroupBox('Dane projektu')
        proj_form = QFormLayout(proj_box)
        self.project_num_edit = QLineEdit() 
        proj_form.addRow('Nr projektu (OBI/OBM):', self.project_num_edit)
        self.date_edit = QLineEdit()
        proj_form.addRow('Data:', self.date_edit)
        self.place_edit = QLineEdit() 
        proj_form.addRow('Miejscowość złożenia:', self.place_edit)
        main_v.addWidget(proj_box)

        owner_box = QGroupBox('Lista Właścicieli (Wybierz aby edytować dane do formularza)')
        owner_layout = QVBoxLayout(owner_box)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel('Wyszukaj (np. Jan Kowalski, 123/1):'))
        self.search_owners_edit = QLineEdit()
        self.search_owners_edit.textChanged.connect(self._refresh_owners_table)
        search_row.addWidget(self.search_owners_edit)
        owner_layout.addLayout(search_row)

        chk_layout = QHBoxLayout()
        self.chk_hide_generated = QCheckBox("Ukryj w pełni wygenerowane osoby")
        self.chk_hide_generated.setChecked(False)
        self.chk_hide_generated.stateChanged.connect(self._refresh_owners_table)
        chk_layout.addWidget(self.chk_hide_generated)
        self.chk_show_only_generated = QCheckBox('Pokaż tylko wygenerowane')
        self.chk_show_only_generated.stateChanged.connect(self._refresh_owners_table)
        chk_layout.addWidget(self.chk_show_only_generated)
        
        btn_sel_all = QPushButton('☑️ Zaznacz wszystkie ptaszki')
        btn_sel_all.clicked.connect(self._check_all_visible)
        chk_layout.addWidget(btn_sel_all)

        btn_unsel_all = QPushButton('⬜ Odznacz wszystkie ptaszki')
        btn_unsel_all.clicked.connect(self._uncheck_all_visible)
        chk_layout.addWidget(btn_unsel_all)
        chk_layout.addStretch()

        owner_layout.addLayout(chk_layout)

        group_layout = QHBoxLayout()
        group_layout.addWidget(QLabel('Grupa działek:'))
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(180)
        self.group_combo.currentTextChanged.connect(self._on_group_changed)
        group_layout.addWidget(self.group_combo)
        self.chk_show_only_group = QCheckBox('Pokaż tylko grupę')
        self.chk_show_only_group.stateChanged.connect(self._refresh_owners_table)
        group_layout.addWidget(self.chk_show_only_group)
        self.chk_exclude_grouped_from_all = QCheckBox('Wszystkie bez działek z grup')
        self.chk_exclude_grouped_from_all.setToolTip('Gdy wybierzesz "Wszystkie działki", działki użyte w innych grupach nie będą pokazywane.')
        self.chk_exclude_grouped_from_all.stateChanged.connect(self._refresh_owners_table)
        group_layout.addWidget(self.chk_exclude_grouped_from_all)
        btn_group_create = QPushButton('➕ Utwórz z ptaszków')
        btn_group_create.clicked.connect(self._create_group_from_checked)
        group_layout.addWidget(btn_group_create)
        btn_group_apply = QPushButton('☑️ Zaznacz grupę')
        btn_group_apply.clicked.connect(self._apply_selected_group)
        group_layout.addWidget(btn_group_apply)
        btn_group_import = QPushButton('📥 Import TXT jako grupa')
        btn_group_import.clicked.connect(self._import_group_txt)
        group_layout.addWidget(btn_group_import)
        btn_group_delete = QPushButton('🗑 Usuń grupę')
        btn_group_delete.clicked.connect(self._delete_selected_group)
        group_layout.addWidget(btn_group_delete)
        group_layout.addStretch()
        owner_layout.addLayout(group_layout)

        self.table_owners = QTableWidget(0, 7)
        self.table_owners.setHorizontalHeaderLabels(['✓', 'Wymagane', 'Budowa', 'Demontaż', 'Właściciel', 'Działki', 'Adres (Tylko info)'])
        self.table_owners.setMinimumHeight(280)
        
        self.table_owners.horizontalHeader().setSectionsMovable(True)
        table_state_decl_hex = self.config.get('table_state_decl', '')
        if table_state_decl_hex:
            from PySide6.QtCore import QByteArray
            self.table_owners.horizontalHeader().restoreState(QByteArray.fromHex(table_state_decl_hex.encode()))

        header = self.table_owners.horizontalHeader()
        for col in range(self.table_owners.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self.table_owners.setColumnWidth(0, 60)
        self.table_owners.setColumnWidth(1, 95)
        self.table_owners.setColumnWidth(2, 85)
        self.table_owners.setColumnWidth(3, 105)
        self.table_owners.setColumnWidth(4, 250)
        self.table_owners.setColumnWidth(5, 150)
        self.table_owners.setColumnWidth(6, 240)
        self.table_owners.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.table_owners.horizontalHeader().sectionResized.connect(lambda *args: self.config.update({'table_state_decl': self.table_owners.horizontalHeader().saveState().toHex().data().decode()}))
        self.table_owners.horizontalHeader().sectionMoved.connect(lambda *args: self.config.update({'table_state_decl': self.table_owners.horizontalHeader().saveState().toHex().data().decode()}))

        self.table_owners.setAlternatingRowColors(True)
        self.table_owners.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_owners.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_owners.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        self.table_owners.itemSelectionChanged.connect(self._on_owner_selected)
        self.table_owners.itemChanged.connect(self._on_check_changed)
        
        owner_layout.addWidget(self.table_owners)


        manual_btns = QHBoxLayout()
        btn_mark_gen = QPushButton('✅ Oznacz wybrane wiersze jako Gotowe')
        btn_mark_gen.clicked.connect(self._mark_selected_as_generated)
        manual_btns.addWidget(btn_mark_gen)

        btn_mark_ungen = QPushButton('❌ Oznacz wybrane wiersze jako Brak')
        btn_mark_ungen.clicked.connect(self._mark_selected_as_ungenerated)
        manual_btns.addWidget(btn_mark_ungen)
        
        manual_btns.addStretch()
        owner_layout.addLayout(manual_btns)

        owner_form = QFormLayout()
        self.owner_name_edit = QLineEdit()
        owner_form.addRow('Edytuj Imię i nazwisko:', self.owner_name_edit)
        
        self.pesel_edit = QLineEdit()
        self.pesel_edit.editingFinished.connect(self._save_owner_edits)
        owner_form.addRow('PESEL:', self.pesel_edit)
        
        self.nip_edit = QLineEdit()
        self.nip_edit.editingFinished.connect(self._save_owner_edits)
        owner_form.addRow('NIP:', self.nip_edit)
        
        owner_layout.addLayout(owner_form)
        main_v.addWidget(owner_box)

        land_box = QGroupBox('Dane gruntu (Tylko to pole tworzy Adres w oświadczeniu)')
        land_form = QFormLayout(land_box)
        self.location_edit = QLineEdit()
        land_form.addRow('Miejscowość działki:', self.location_edit)
        
        self.street_edit = QLineEdit()
        land_form.addRow('Ulica działki:', self.street_edit)
        
        self.voivodeship_edit = QLineEdit()
        land_form.addRow('Województwo:', self.voivodeship_edit)
        self.county_edit = QLineEdit()
        land_form.addRow('Powiat:', self.county_edit)
        self.municipality_edit = QLineEdit()
        land_form.addRow('Gmina:', self.municipality_edit)
        self.parcels_budowa_edit = QLineEdit()
        land_form.addRow('Działki Budowa:', self.parcels_budowa_edit)
        self.parcels_demontaz_edit = QLineEdit()
        land_form.addRow('Działki Demontaż:', self.parcels_demontaz_edit)
        
        self.area_budowa_edit = QLineEdit()
        land_form.addRow('Pow. [ha] Budowa:', self.area_budowa_edit)
        self.area_demontaz_edit = QLineEdit()
        land_form.addRow('Pow. [ha] Demontaż:', self.area_demontaz_edit)
        
        self.precinct_edit = QLineEdit()
        land_form.addRow('Obręb:', self.precinct_edit)
        
        self.kw_budowa_edit = QLineEdit()
        land_form.addRow('Nr KW Budowa:', self.kw_budowa_edit)
        self.kw_demontaz_edit = QLineEdit()
        land_form.addRow('Nr KW Demontaż:', self.kw_demontaz_edit)
        main_v.addWidget(land_box)

        device_box = QGroupBox('Postać urządzenia elektroenergetycznego')
        device_layout = QFormLayout(device_box)

        h_bud = QHBoxLayout()
        self.device_budowa_combo = NoWheelComboBox()
        self.device_budowa_combo.currentTextChanged.connect(lambda t: self.device_budowa_edit.setText(t) if t else None)
        h_bud.addWidget(self.device_budowa_combo, 1)
        btn_manage_bud = QPushButton('✏ Przykłady')
        btn_manage_bud.clicked.connect(lambda: self._manage_device_examples('budowa'))
        h_bud.addWidget(btn_manage_bud)
        self.device_budowa_edit = QLineEdit()
        h_bud.addWidget(self.device_budowa_edit, 2)
        device_layout.addRow('Budowa:', h_bud)

        h_dem = QHBoxLayout()
        self.device_demontaz_combo = NoWheelComboBox()
        self.device_demontaz_combo.currentTextChanged.connect(lambda t: self.device_demontaz_edit.setText(t) if t else None)
        h_dem.addWidget(self.device_demontaz_combo, 1)
        btn_manage_dem = QPushButton('✏ Przykłady')
        btn_manage_dem.clicked.connect(lambda: self._manage_device_examples('demontaz'))
        h_dem.addWidget(btn_manage_dem)
        self.device_demontaz_edit = QLineEdit()
        h_dem.addWidget(self.device_demontaz_edit, 2)
        device_layout.addRow('Demontaż:', h_dem)

        self._update_device_examples()
        main_v.addWidget(device_box)

        tmpl_box = QGroupBox('Ścieżki szablonów')
        tmpl_layout = QFormLayout(tmpl_box)
        h_tb = QHBoxLayout()
        self.template_budowa_edit = QLineEdit()
        h_tb.addWidget(self.template_budowa_edit)
        btn_browse_tb = QPushButton('📂 Wybierz...')
        btn_browse_tb.clicked.connect(lambda: self._browse_template('budowa'))
        h_tb.addWidget(btn_browse_tb)
        tmpl_layout.addRow('Szablon Budowa:', h_tb)

        h_td = QHBoxLayout()
        self.template_demontaz_edit = QLineEdit()
        h_td.addWidget(self.template_demontaz_edit)
        btn_browse_td = QPushButton('📂 Wybierz...')
        btn_browse_td.clicked.connect(lambda: self._browse_template('demontaz'))
        h_td.addWidget(btn_browse_td)
        tmpl_layout.addRow('Szablon Demontaż:', h_td)

        btn_default_tmpl = QPushButton('↩ Załaduj domyślne szablony')
        btn_default_tmpl.clicked.connect(self._set_default_template)
        tmpl_layout.addRow('', btn_default_tmpl)
        main_v.addWidget(tmpl_box)

        gen_box = QGroupBox('Generuj')
        gen_layout = QVBoxLayout(gen_box)
        gen_btn_row = QHBoxLayout()
        self.btn_preview = QPushButton('👁 Podgląd tekstu')
        self.btn_preview.clicked.connect(self._preview)
        gen_btn_row.addWidget(self.btn_preview)

        self.btn_generate = QPushButton('💾 Generuj dla formularza')
        self.btn_generate.clicked.connect(self._generate)
        gen_btn_row.addWidget(self.btn_generate)

        self.btn_generate_sel = QPushButton('⚙️ Generuj dla ZAZNACZONYCH w tabeli')
        self.btn_generate_sel.clicked.connect(self._generate_selected)
        gen_btn_row.addWidget(self.btn_generate_sel)

        self.btn_generate_all = QPushButton('⚡ GENERUJ AUTOMATYCZNIE WSZYSTKIE')
        self.btn_generate_all.setObjectName('btn_accent')
        self.btn_generate_all.clicked.connect(self._generate_all)
        gen_btn_row.addWidget(self.btn_generate_all)
        gen_layout.addLayout(gen_btn_row)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(120)
        gen_layout.addWidget(self.preview_text)
        main_v.addWidget(gen_box)

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self._set_default_template()

    def _check_all_visible(self):
        for r in range(self.table_owners.rowCount()):
            if not self.table_owners.isRowHidden(r):
                it = self.table_owners.item(r, 0)
                if it: it.setCheckState(Qt.CheckState.Checked)

    def _uncheck_all_visible(self):
        for r in range(self.table_owners.rowCount()):
            it = self.table_owners.item(r, 0)
            if it: it.setCheckState(Qt.CheckState.Unchecked)

    def _save_owner_edits(self):
        sel = self.table_owners.selectedItems()
        if not sel: return
        data = self.table_owners.item(sel[0].row(), 4).data(Qt.ItemDataRole.UserRole)
        if not data: return
        idx, _ = data
        if 0 <= idx < len(self.owners):
            self.owners[idx]['pesel'] = self.pesel_edit.text().strip()
            self.owners[idx]['nip'] = self.nip_edit.text().strip()
            self.owners_changed.emit(self.owners)

    def _update_device_examples(self):
        self.device_budowa_combo.clear()
        self.device_budowa_combo.addItem('')
        for ex in self.examples.get('device_types_budowa', []): self.device_budowa_combo.addItem(ex)
        self.device_demontaz_combo.clear()
        self.device_demontaz_combo.addItem('')
        for ex in self.examples.get('device_types_demontaz', []): self.device_demontaz_combo.addItem(ex)

    def _manage_device_examples(self, dev_type: str):
        key = 'device_types_budowa' if dev_type == 'budowa' else 'device_types_demontaz'
        title = 'Budowa' if dev_type == 'budowa' else 'Demontaż'
        dlg = ManageExamplesDialog(self.examples.get(key, []), title, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.examples[key] = dlg.get_examples()
            self._update_device_examples()
            if self.save_callback: self.save_callback()

    def _decl_done(self, owner, specific_addr, typ):
        by_addr = owner.get(f'decl_gen_{typ}_by_addr')
        if isinstance(by_addr, dict):
            return bool(by_addr.get(specific_addr or '', False))
        return bool(owner.get(f'decl_gen_{typ}', False))

    def _set_decl_done(self, owner, specific_addr, typ, value):
        key = f'decl_gen_{typ}_by_addr'
        by_addr = owner.get(key)
        if not isinstance(by_addr, dict):
            by_addr = {}
            owner[key] = by_addr
        by_addr[specific_addr or ''] = bool(value)
        # Nie ustawiamy globalnego decl_gen_budowa/demontaz, bo właściciel może mieć drugi adres.
        owner[f'decl_gen_{typ}'] = any(bool(v) for v in by_addr.values())

    def _row_key(self, idx, specific_addr):
        return f"{idx}|{specific_addr or ''}"

    def _on_check_changed(self, item):
        if item.column() != 0:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if not key:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self.checked_keys.add(key)
        else:
            self.checked_keys.discard(key)

    def _update_generated_list(self):
        if not hasattr(self, 'generated_list'):
            return
        self.generated_list.clear()
        for o in self.owners:
            name = o.get('full_name') or o.get('name_plural') or ''
            parcels = ', '.join([str(p.get('number', p)) if isinstance(p, dict) else str(p) for p in o.get('parcels', [])])
            flags = []
            if o.get('decl_gen_budowa'): flags.append('Budowa')
            if o.get('decl_gen_demontaz'): flags.append('Demontaż')
            if flags:
                self.generated_list.addItem(f"{name} | {parcels} | {', '.join(flags)}")

    def _toggle_generated_list(self):
        self.generated_list.setVisible(not self.generated_list.isVisible())

    def _owner_parcels(self, owner):
        return {str(p.get('number', p)) if isinstance(p, dict) else str(p) for p in owner.get('parcels', [])}

    def _set_group_fields(self, group: dict | None):
        """Ustawia pola urządzeń dla wybranej grupy. Dla 'Wszystkie działki' czyści pola."""
        if not group:
            self.device_budowa_edit.clear()
            self.device_demontaz_edit.clear()
            return
        self.device_budowa_edit.setText(group.get('budowa', '') or '')
        self.device_demontaz_edit.setText(group.get('demontaz', '') or '')

    def _on_group_changed(self, *_args):
        name = self.group_combo.currentText() if hasattr(self, 'group_combo') else ''
        if name == 'Wszystkie działki' or not name:
            self._set_group_fields(None)
        else:
            self._set_group_fields(self.parcel_groups.get(name, {}))
        if hasattr(self, 'chk_show_only_group') and self.chk_show_only_group.isChecked():
            self._refresh_owners_table()

    def _groups_state_file(self):
        project_path = self.active_project_path or self.config.get('last_project_path', '')
        return Path(project_path) / 'decl_groups.json' if project_path else None

    def _save_groups(self):
        path = self._groups_state_file()
        if not path: return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.parcel_groups, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_groups(self):
        path = self._groups_state_file()
        self.parcel_groups = {}
        if path and path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.parcel_groups = data
            except Exception:
                self.parcel_groups = {}
        self._refresh_group_combo()

    def _refresh_group_combo(self):
        if not hasattr(self, 'group_combo'):
            return
        current = self.group_combo.currentText()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem('Wszystkie działki')
        self.group_combo.addItems(sorted(self.parcel_groups.keys()))
        if current:
            idx = self.group_combo.findText(current)
            if idx >= 0: self.group_combo.setCurrentIndex(idx)
        self.group_combo.blockSignals(False)
        self._on_group_changed()

    def _owner_group_key(self, owner, specific_addr):
        parcels = ','.join(sorted(self._owner_parcels(owner)))
        name = owner.get('full_name') or owner.get('name_plural') or owner.get('name_separate') or owner.get('last_name', '')
        return f"{name}|{specific_addr or ''}|{parcels}"

    def _selected_group_owner_keys(self):
        if not hasattr(self, 'group_combo'):
            return set()
        name = self.group_combo.currentText()
        group = self.parcel_groups.get(name, {})
        return set(group.get('owner_keys', []))

    def _selected_group_parcels(self):
        if not hasattr(self, 'group_combo'):
            return set()
        name = self.group_combo.currentText()
        if name == 'Wszystkie działki':
            all_nums = set(self._all_project_parcels())
            if hasattr(self, 'chk_exclude_grouped_from_all') and self.chk_exclude_grouped_from_all.isChecked():
                used = set()
                for group in self.parcel_groups.values():
                    used.update(group.get('parcels', []))
                all_nums -= used
            return all_nums
        group = self.parcel_groups.get(name, {})
        return set(group.get('parcels', []))

    def _all_project_parcels(self):
        nums = set()
        for p in self.parcels:
            if isinstance(p, dict) and p.get('number'):
                nums.add(str(p.get('number')))
        for o in self.owners:
            nums.update(self._owner_parcels(o))
        return nums

    def _ask_group_descriptions(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Postać urządzenia dla grupy')
        layout = QFormLayout(dlg)

        bud_combo = NoWheelComboBox()
        bud_combo.setEditable(True)
        bud_combo.addItem('')
        for ex in self.examples.get('device_types_budowa', []):
            bud_combo.addItem(ex)
        layout.addRow('Budowa – wybierz z listy lub wpisz:', bud_combo)

        dem_combo = NoWheelComboBox()
        dem_combo.setEditable(True)
        dem_combo.addItem('')
        for ex in self.examples.get('device_types_demontaz', []):
            dem_combo.addItem(ex)
        layout.addRow('Demontaż – wybierz z listy lub wpisz:', dem_combo)

        info = QLabel('Możesz wybrać istniejące zadanie z listy albo wpisać własne dla tej grupy.')
        info.setStyleSheet('color: gray; font-size: 11px;')
        layout.addRow('', info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return bud_combo.currentText().strip(), dem_combo.currentText().strip()


    def _create_group_from_checked(self):
        parcels = set()
        owner_keys = set()
        for key in self.checked_keys:
            try:
                raw = str(key).split('|', 1)
                idx = int(raw[0])
                specific_addr = raw[1] if len(raw) > 1 else ''
                if 0 <= idx < len(self.owners):
                    owner = self.owners[idx]
                    parcels.update(self._owner_parcels(owner))
                    owner_keys.add(self._owner_group_key(owner, specific_addr))
            except Exception:
                pass
        if not owner_keys:
            return QMessageBox.warning(self, 'Brak', 'Najpierw zaznacz ptaszkiem konkretne osoby/adresy do grupy.')
        name, ok = QInputDialog.getText(self, 'Nowa grupa', 'Nazwa grupy:')
        if not ok or not name.strip(): return
        descs = self._ask_group_descriptions()
        if descs is None: return
        self.parcel_groups[name.strip()] = {'parcels': sorted(parcels), 'owner_keys': sorted(owner_keys), 'budowa': descs[0], 'demontaz': descs[1]}
        self._save_groups()
        self._refresh_group_combo()
        self.group_combo.setCurrentText(name.strip())


    def _apply_selected_group(self):
        name = self.group_combo.currentText() if hasattr(self, 'group_combo') else ''
        if name == 'Wszystkie działki':
            group = {'parcels': sorted(self._all_project_parcels()), 'budowa': '', 'demontaz': ''}
        else:
            group = self.parcel_groups.get(name)
        if not group: return

        owner_keys = set(group.get('owner_keys', []))
        wanted = set(group.get('parcels', []))
        for idx, o in enumerate(self.owners):
            addresses = [o.get('address', '')] + ([o.get('address_2')] if o.get('address_2') else [])
            for addr in addresses:
                if owner_keys:
                    if self._owner_group_key(o, addr) in owner_keys:
                        self.checked_keys.add(self._row_key(idx, addr))
                elif self._owner_parcels(o) & wanted:
                    self.checked_keys.add(self._row_key(idx, addr))
        self._set_group_fields(None if name == 'Wszystkie działki' else group)
        self._refresh_owners_table()


    def _delete_selected_group(self):
        name = self.group_combo.currentText() if hasattr(self, 'group_combo') else ''
        if name and name != 'Wszystkie działki' and name in self.parcel_groups:
            del self.parcel_groups[name]
            self._save_groups()
            self._refresh_group_combo()

    def _import_group_txt(self, path: str = ''):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, 'Import grupy działek TXT', '', 'Pliki TXT (*.txt);;Wszystkie pliki (*.*)')
        if not path: return
        try:
            text = Path(path).read_text(encoding='utf-8')
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding='cp1250')
        from utils.pdf_utils import parse_parcel_list_text
        parsed = parse_parcel_list_text(text)
        lines = []
        for cat in ['demolition', 'construction', 'connection', 'full']:
            lines.extend(parsed.get(cat, []))
        # deduplikacja z zachowaniem kolejności
        seen = set()
        lines = [x for x in lines if not (x in seen or seen.add(x))]
        if not lines:
            QMessageBox.warning(self, 'Brak działek', 'Nie znaleziono numerów działek w pliku TXT.')
            return
        group_name, ok = QInputDialog.getText(self, 'Nazwa grupy', 'Podaj nazwę grupy:', QLineEdit.EchoMode.Normal, Path(path).stem)
        if not ok or not group_name.strip(): return
        descs = self._ask_group_descriptions()
        if descs is None: return
        self.parcel_groups[group_name.strip()] = {'parcels': lines, 'budowa': descs[0], 'demontaz': descs[1]}
        self._save_groups()
        self._refresh_group_combo()
        self.group_combo.setCurrentText(group_name.strip())
        self._on_group_changed()
        self._apply_selected_group()


    def set_owners(self, owners: list):
        self.owners = owners
        self._refresh_group_combo()
        self._refresh_owners_table()

    def _mark_selected_as_generated(self):
        sel = self.table_owners.selectionModel().selectedRows()
        if not sel: return QMessageBox.warning(self, "Brak", "Wybierz wiersze z tabeli.")
        for i in sel:
            data = self.table_owners.item(i.row(), 4).data(Qt.ItemDataRole.UserRole)
            if data:
                idx, _ = data
                o = self.owners[idx]
                req = self.table_owners.item(i.row(), 1).text()
                if 'Budowa' in req: self._set_decl_done(o, _, 'budowa', True)
                if 'Demontaż' in req: self._set_decl_done(o, _, 'demontaz', True)
        self.owners_changed.emit(self.owners)
        self._refresh_owners_table()

    def _mark_selected_as_ungenerated(self):
        sel = self.table_owners.selectionModel().selectedRows()
        if not sel: return QMessageBox.warning(self, "Brak", "Wybierz wiersze z tabeli.")
        for i in sel:
            data = self.table_owners.item(i.row(), 4).data(Qt.ItemDataRole.UserRole)
            if data:
                idx, _ = data
                o = self.owners[idx]
                self._set_decl_done(o, _, 'budowa', False)
                self._set_decl_done(o, _, 'demontaz', False)
        self.owners_changed.emit(self.owners)
        self._refresh_owners_table()

    def _refresh_owners_table(self):
        self.table_owners.blockSignals(True)
        self.table_owners.setRowCount(0)
        
        hide_generated = self.chk_hide_generated.isChecked()
        filter_text = self.search_owners_edit.text().strip().lower()
        
        for idx, o in enumerate(self.owners):
            addresses = [o.get('address', '')]
            if o.get('address_2'):
                addresses.append(o.get('address_2'))
                
            for specific_addr in addresses:
                cats = set()
                parcels = o.get('parcels', [])
                for p_info in parcels:
                    num = p_info['number'] if isinstance(p_info, dict) else str(p_info)
                    for known_p in self.parcels:
                        if known_p.get('number') == num:
                            c = known_p.get('category', '')
                            if 'Demonta' in c or 'Demontaż' in c: cats.add('demontaz')
                            if 'Budowa' in c: cats.add('budowa')
                            if 'Pe' in c or 'Przyłącze' in c or 'Przylacze' in c: cats.add('budowa')
                            
                req_budowa = 'budowa' in cats
                req_demontaz = 'demontaz' in cats
                
                got_budowa = self._decl_done(o, specific_addr, 'budowa')
                got_demontaz = self._decl_done(o, specific_addr, 'demontaz')
                
                is_complete = True
                if req_budowa and not got_budowa: is_complete = False
                if req_demontaz and not got_demontaz: is_complete = False
                is_any_generated = bool(got_budowa or got_demontaz or o.get('decl_generated'))
                if hide_generated and is_complete: continue
                if hasattr(self, 'chk_show_only_generated') and self.chk_show_only_generated.isChecked() and not is_any_generated: continue
                
                fmt = self.config.get('couple_format_decl', 0)
                display_name = o.get('name_plural', o.get('full_name', '')) if fmt == 0 else o.get('name_separate', o.get('full_name', ''))
                parcels_str = ', '.join([str(p.get('number', p)) if isinstance(p, dict) else str(p) for p in parcels])
                if hasattr(self, 'chk_show_only_group') and self.chk_show_only_group.isChecked():
                    wanted_owner_keys = self._selected_group_owner_keys()
                    if wanted_owner_keys:
                        if self._owner_group_key(o, specific_addr) not in wanted_owner_keys:
                            continue
                    else:
                        wanted_group = self._selected_group_parcels()
                        owner_nums = {str(p.get('number', p)) if isinstance(p, dict) else str(p) for p in parcels}
                        if wanted_group and not (owner_nums & wanted_group):
                            continue

                if filter_text:
                    search_target = f"{display_name} {specific_addr} {parcels_str}".lower()
                    if filter_text not in search_target: continue

                flags = []
                if o.get('is_dead'): flags.append("[ZMARŁY/A]")
                elif o.get('is_institution'): flags.append("[INSTYTUCJA]")
                elif o.get('is_church'): flags.append("[PARAFIA]")
                elif o.get('is_company'): flags.append("[FIRMA]")
                else:
                    if not specific_addr.strip(): flags.append("[BRAK ADRESU]")
                    elif not re.search(r'\d{2}-\d{3}', specific_addr): flags.append("[BŁĄD KODU]")
                    
                flag_str = " ".join(flags) + " " if flags else ""
                
                typ_str = "Brak"
                if req_budowa and req_demontaz: typ_str = "Budowa+Demontaż"
                elif req_budowa: typ_str = "Budowa"
                elif req_demontaz: typ_str = "Demontaż"

                row = self.table_owners.rowCount()
                self.table_owners.insertRow(row)
                
                it_chk = QTableWidgetItem()
                it_chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                key = self._row_key(idx, specific_addr)
                it_chk.setData(Qt.ItemDataRole.UserRole, key)
                it_chk.setCheckState(Qt.CheckState.Checked if key in self.checked_keys else Qt.CheckState.Unchecked)
                self.table_owners.setItem(row, 0, it_chk)
                
                it_typ = QTableWidgetItem(typ_str)
                it_typ.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_owners.setItem(row, 1, it_typ)
                
                txt_bud = "—"
                color_bud = QColor("#555")
                if req_budowa:
                    if got_budowa:
                        txt_bud = "TAK"
                        color_bud = QColor("#2ecc71")
                    else:
                        txt_bud = "NIE"
                        color_bud = QColor("#e74c3c")
                it_bud = QTableWidgetItem(txt_bud)
                it_bud.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_bud.setForeground(color_bud)
                it_bud.setFont(QFont('', -1, QFont.Weight.Bold))
                self.table_owners.setItem(row, 2, it_bud)
                
                txt_dem = "—"
                color_dem = QColor("#555")
                if req_demontaz:
                    if got_demontaz:
                        txt_dem = "TAK"
                        color_dem = QColor("#2ecc71")
                    else:
                        txt_dem = "NIE"
                        color_dem = QColor("#e74c3c")
                it_dem = QTableWidgetItem(txt_dem)
                it_dem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_dem.setForeground(color_dem)
                it_dem.setFont(QFont('', -1, QFont.Weight.Bold))
                self.table_owners.setItem(row, 3, it_dem)
                
                it_name = QTableWidgetItem(f"{flag_str}{display_name}")
                it_name.setData(Qt.ItemDataRole.UserRole, (idx, specific_addr))
                if o.get('is_dead'): it_name.setForeground(QColor("#e74c3c"))
                elif o.get('is_institution'): it_name.setForeground(QColor("#9b5de5"))
                elif o.get('is_church'): it_name.setForeground(QColor("#f39c12"))
                elif o.get('is_company'): it_name.setForeground(QColor("#3498db"))
                elif flags: it_name.setForeground(QColor("#e67e22"))
                else: it_name.setForeground(QColor("#2ecc71"))
                self.table_owners.setItem(row, 4, it_name)
                
                it_parcels = QTableWidgetItem(parcels_str)
                self.table_owners.setItem(row, 5, it_parcels)

                it_addr = QTableWidgetItem(specific_addr)
                self.table_owners.setItem(row, 6, it_addr)
                
        self.table_owners.blockSignals(False)

    def _on_owner_selected(self):
        sel = self.table_owners.selectedItems()
        if not sel: return
        
        row = sel[0].row()
        data = self.table_owners.item(row, 4).data(Qt.ItemDataRole.UserRole)
        if not data: return
        idx, specific_addr = data
        o = self.owners[idx]
        
        typ_item = self.table_owners.item(row, 1)
        if typ_item:
            typ_str = typ_item.text()
            self.type_combo.blockSignals(True)
            if typ_str == "Budowa+Demontaż": self.type_combo.setCurrentIndex(2)
            elif typ_str == "Demontaż": self.type_combo.setCurrentIndex(1)
            elif typ_str == "Budowa": self.type_combo.setCurrentIndex(0)
            self.type_combo.blockSignals(False)
        
        fmt = self.config.get('couple_format_decl', 0)
        display_name = o.get('name_plural', o.get('full_name', '')) if fmt == 0 else o.get('name_separate', o.get('full_name', ''))
        self.owner_name_edit.setText(display_name)
        
        if o.get('pesel'): self.pesel_edit.setText(o.get('pesel', ''))
        if o.get('nip'): self.nip_edit.setText(o.get('nip', ''))

        parcels = o.get('parcels', [])
        
        street_dz_list = []
        if self.config.get('extract_parcel_address', True):
            for p_info in parcels:
                if isinstance(p_info, dict) and p_info.get('parcel_address'):
                    a = p_info.get('parcel_address')
                    if a and a not in street_dz_list: street_dz_list.append(a)
        
        self.street_edit.setText(", ".join(street_dz_list))

        if parcels:
            bud_list, dem_list = [], []
            kw_bud, kw_dem = [], []
            area_bud, area_dem = 0.0, 0.0
            v_list, c_list, m_list, p_list = [], [], [], []
            
            for p_info in parcels:
                num = p_info['number'] if isinstance(p_info, dict) else str(p_info)
                kw = p_info.get('kw', '') if isinstance(p_info, dict) else ''
                area = p_info.get('area_ha', 0.0) if isinstance(p_info, dict) else 0.0
                
                is_valid = False
                for known_p in self.parcels:
                    if known_p.get('number') == num:
                        c = known_p.get('category', '')
                        if 'Budowa' in c or 'Pe' in c or 'Przyłącze' in c or 'Przylacze' in c: 
                            bud_list.append(num)
                            if kw and kw not in kw_bud: kw_bud.append(kw)
                            area_bud += area
                            is_valid = True
                        if 'Demonta' in c or 'Demontaż' in c: 
                            dem_list.append(num)
                            if kw and kw not in kw_dem: kw_dem.append(kw)
                            area_dem += area
                            is_valid = True

                if is_valid and isinstance(p_info, dict):
                    if p_info.get('voivodeship') and p_info['voivodeship'] not in v_list: v_list.append(p_info['voivodeship'])
                    if p_info.get('county') and p_info['county'] not in c_list: c_list.append(p_info['county'])
                    if p_info.get('municipality') and p_info['municipality'] not in m_list: m_list.append(p_info['municipality'])
                    if p_info.get('precinct') and p_info['precinct'] not in p_list: p_list.append(p_info['precinct'])

            self.voivodeship_edit.setText(', '.join(v_list) if v_list else o.get('voivodeship', ''))
            self.county_edit.setText(', '.join(c_list) if c_list else o.get('county', ''))
            self.municipality_edit.setText(', '.join(m_list) if m_list else o.get('municipality', ''))
            self.precinct_edit.setText(', '.join(p_list) if p_list else o.get('precinct', ''))
            self.location_edit.setText(o.get('city', ''))

            self.parcels_budowa_edit.setText(', '.join(bud_list))
            self.parcels_demontaz_edit.setText(', '.join(dem_list))
            
            if len(bud_list) > 1:
                self.area_budowa_edit.setText(f"łącznej {format_area_pl(area_bud)}")
            else:
                self.area_budowa_edit.setText(format_area_pl(area_bud) if area_bud else "")
                
            if len(dem_list) > 1:
                self.area_demontaz_edit.setText(f"łącznej {format_area_pl(area_dem)}")
            else:
                self.area_demontaz_edit.setText(format_area_pl(area_dem) if area_dem else "")

            self.kw_budowa_edit.setText(', '.join(kw_bud))
            self.kw_demontaz_edit.setText(', '.join(kw_dem))

    def _browse_template(self, tmpl_type: str):
        path, _ = QFileDialog.getOpenFileName(self, f'Wybierz szablon ({tmpl_type})', '', 'Word (*.docx)')
        if path:
            if tmpl_type == 'budowa': self.template_budowa_edit.setText(path)
            else: self.template_demontaz_edit.setText(path)

    def _set_default_template(self):
        import sys
        from utils.templates import find_latest_file

        if getattr(sys, 'frozen', False):
            przyk_path = str(Path(sys.executable).parent.resolve() / 'przykłady')
        else:
            przyk_path = str(Path(__file__).parent.parent.parent / 'przykłady')

        budowa_tmpl = self.config.get('decl_template_budowa', '')
        if not budowa_tmpl or not Path(budowa_tmpl).exists():
            latest = find_latest_file(
                przyk_path,
                ["Oświadczenie woli budowa kabla", "Oświadczenie woli budowa",
                 "oswiadczenie woli budowa kabla", "oswiadczenie woli budowa"],
                (".docx",),
            )
            budowa_tmpl = str(latest) if latest else ""

        demontaz_tmpl = self.config.get('decl_template_demontaz', '')
        if not demontaz_tmpl or not Path(demontaz_tmpl).exists():
            latest = find_latest_file(
                przyk_path,
                ["Oświadczenie woli demontaż linii", "Oświadczenie woli demontaz linii",
                 "Oświadczenie woli demontaż", "Oświadczenie woli demontaz"],
                (".docx",),
            )
            demontaz_tmpl = str(latest) if latest else ""

        self.template_budowa_edit.setText(budowa_tmpl)
        self.template_demontaz_edit.setText(demontaz_tmpl)

    def _get_params(self) -> dict:
        date_str = self.date_edit.text().strip()
        decl_type_idx = self.type_combo.currentIndex()
        decl_type_str = 'budowa' if decl_type_idx == 0 else ('demontaz' if decl_type_idx == 1 else 'obie')
        
        precinct_val = self.precinct_edit.text().strip()
        if self.config.get('decl_precinct_uppercase', False):
            precinct_val = precinct_val.upper()
            
        return {
            'declaration_type': decl_type_str,
            'project_number': self.project_num_edit.text().strip(),
            'date_str': date_str,
            'place': self.place_edit.text().strip(),
            'owner_name': self.owner_name_edit.text().strip(),
            'pesel': self.pesel_edit.text().strip() or '–',
            'nip': self.nip_edit.text().strip() or '–',
            'location': self.location_edit.text().strip(),
            'street': self.street_edit.text().strip(),
            'voivodeship': self.voivodeship_edit.text().strip(),
            'county': self.county_edit.text().strip(),
            'municipality': self.municipality_edit.text().strip(),
            'parcel_numbers_budowa': self.parcels_budowa_edit.text().strip(),
            'parcel_numbers_demontaz': self.parcels_demontaz_edit.text().strip(),
            'area_ha_budowa': self.area_budowa_edit.text().strip(),
            'area_ha_demontaz': self.area_demontaz_edit.text().strip(),
            'precinct': precinct_val,
            'kw_numbers_budowa': self.kw_budowa_edit.text().strip(),
            'kw_numbers_demontaz': self.kw_demontaz_edit.text().strip(),
            'device_description_budowa': self.device_budowa_edit.text().strip(),
            'device_description_demontaz': self.device_demontaz_edit.text().strip(),
            'template_path_budowa': self.template_budowa_edit.text().strip(),
            'template_path_demontaz': self.template_demontaz_edit.text().strip(),
        }

    def _preview(self):
        p = self._get_params()
        preview = (
            f"=== OŚWIADCZENIE WOLI – {p['declaration_type'].upper()} ===\n"
            f"Nr projektu: {p['project_number']}\n"
            f"Data/miejsce: {p['place']}, {p['date_str']}\n"
            f"Właściciel: {p['owner_name']}\n"
            f"Ulica: {p['street']}\n"
            f"Miejscowość: {p['location']}\n"
            f"Obręb (Tag): {p['precinct']}\n"
            f"Działki (Budowa): {p['parcel_numbers_budowa']}\n"
            f"Działki (Demontaż): {p['parcel_numbers_demontaz']}\n"
            f"KW (Budowa): {p['kw_numbers_budowa']}\n"
            f"KW (Demontaż): {p['kw_numbers_demontaz']}\n"
        )
        self.preview_text.setText(preview)

    def _generate(self):
        sel = self.table_owners.selectedItems()
        if sel:
            data = self.table_owners.item(sel[0].row(), 4).data(Qt.ItemDataRole.UserRole)
            if data:
                idx, specific_addr = data
                o = self.owners[idx]
                if not self._is_valid_for_gen(o, specific_addr):
                    reply = QMessageBox.question(self, "Uwaga", "Właściciel ma braki w adresie lub jest oznaczony jako Zmarły/Instytucja. Chcesz wymusić generowanie?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if reply == QMessageBox.StandardButton.No: return

        out_dir = QFileDialog.getExistingDirectory(self, 'Folder wyjściowy')
        if not out_dir: return

        p = self._get_params()
        b_tmpl = self.config.get('decl_template_budowa', '')
        d_tmpl = self.config.get('decl_template_demontaz', '')

        t_idx = self.type_combo.currentIndex()
        types = ['budowa', 'demontaz'] if t_idx == 2 else (['budowa'] if t_idx == 0 else ['demontaz'])

        for t in types:
            if t == 'budowa' and not self.parcels_budowa_edit.text().strip(): continue
            if t == 'demontaz' and not self.parcels_demontaz_edit.text().strip(): continue
            
            current_p = p.copy()
            if t == 'budowa':
                current_p['parcel_numbers'] = p['parcel_numbers_budowa']
                current_p['device_description'] = p['device_description_budowa']
                current_p['area_ha'] = p['area_ha_budowa']
                current_p['kw_numbers'] = p['kw_numbers_budowa']
            else:
                current_p['parcel_numbers'] = p['parcel_numbers_demontaz']
                current_p['device_description'] = p['device_description_demontaz']
                current_p['area_ha'] = p['area_ha_demontaz']
                current_p['kw_numbers'] = p['kw_numbers_demontaz']
                
            parts = self.owner_name_edit.text().split()
            fn = " ".join(parts[:-1]) if len(parts) > 1 else ""
            ln = parts[-1] if parts else ""
            short = self._get_short_name(fn, ln)
            
            fname = f"Oświadczenie woli {t} {short}.docx"
            out_path = str(Path(out_dir) / fname)
            
            from utils.docx_utils import generate_declaration
            generate_declaration(
                template_path=b_tmpl if t == 'budowa' else d_tmpl,
                output_path=out_path,
                project_number=self.project_num_edit.text(),
                place=self.place_edit.text(),
                date_str=self.date_edit.text(),
                owner_name=self.owner_name_edit.text(),
                pesel=self.pesel_edit.text(),
                nip=self.nip_edit.text(),
                location=self._location_for_decl(self.location_edit.text()),
                street=self._street_for_decl(self.street_edit.text()),
                voivodeship=self.voivodeship_edit.text(),
                county=self._county_for_powiat(self.county_edit.text(), self.location_edit.text()),
                municipality=self.municipality_edit.text(),
                parcel_numbers_budowa=self.parcels_budowa_edit.text(),
                parcel_numbers_demontaz=self.parcels_demontaz_edit.text(),
                area_ha=current_p['area_ha'],
                area_ha_budowa=self.area_budowa_edit.text(),
                area_ha_demontaz=self.area_demontaz_edit.text(),
                precinct=p['precinct'],
                kw_numbers=current_p['kw_numbers'],
                kw_numbers_budowa=self.kw_budowa_edit.text(),
                kw_numbers_demontaz=self.kw_demontaz_edit.text(),
                device_description=p['device_description_budowa'] if t == 'budowa' else p['device_description_demontaz'],
                declaration_type=t,
                tag_map=self.config.get("declaration_tag_map"),
                unlock_docs=self.config.get("unlock_generated_docs", False)
            )
            
        if sel:
            try:
                data = self.table_owners.item(sel[0].row(), 4).data(Qt.ItemDataRole.UserRole)
                idx, specific_addr = data
                req = self.table_owners.item(sel[0].row(), 1).text()
                if 'budowa' in types and 'Budowa' in req: self._set_decl_done(self.owners[idx], specific_addr, 'budowa', True)
                if 'demontaz' in types and 'Demontaż' in req: self._set_decl_done(self.owners[idx], specific_addr, 'demontaz', True)
                
                self.owners_changed.emit(self.owners)
                self._refresh_owners_table()
            except: pass

        QMessageBox.information(self, "Sukces", "Wygenerowano ręczne oświadczenie.")

    def _location_for_decl(self, city: str) -> str:
        """Odmienia miejscowość działki (miejscownik) — np. Gdańsk → Gdańsku, Opole → Opolu."""
        if not self.config.get('decl_location_locative', False):
            return str(city or '')
        from utils.polish_declension import decline_city
        # Odmiana każdej miejscowości z listy (rozdzielonej przecinkami)
        parts = [p.strip() for p in str(city or '').split(',') if p.strip()]
        if not parts:
            return str(city or '')
        return ', '.join(decline_city(p) for p in parts)

    def _street_for_decl(self, street: str) -> str:
        if not self.config.get('decl_decline_streets', False):
            return str(street or '')
        from utils.polish_declension import decline_street
        # Odmiana każdej ulicy z listy (rozdzielonej przecinkami)
        parts = [p.strip() for p in str(street or '').split(',') if p.strip()]
        if not parts:
            return str(street or '')
        return ', '.join(decline_street(p) for p in parts)

    def _county_for_powiat(self, county: str, location: str = '') -> str:
        """Zamienia miejscowość/powiat na właściwą nazwę powiatu (ZAMIENIA, nie odmienia)."""
        if not self.config.get('decl_powiat_zamiana', False):
            return str(county or '')
        from utils.polish_declension import city_to_powiat
        source = str(county or '').strip() or str(location or '').strip()
        parts = [p.strip() for p in source.split(',') if p.strip()]
        if not parts:
            return str(county or '')
        return ', '.join(city_to_powiat(p) for p in parts)

    def _get_short_name(self, first_name: str, last_name: str) -> str:
        import re
        f_names = re.split(r'\s+i\s+|\s+', first_name.strip()) if first_name else []
        initials = "".join([f"{n[0].upper()}." for n in f_names if n])
        l = last_name.strip() if last_name else ""
        if not initials and not l: return "BrakNazwiska"
        return f"{initials}{l}"

    def _is_valid_for_gen(self, owner: dict, specific_addr: str) -> bool:
        import re
        if owner.get('is_dead') or owner.get('is_institution'): return False
        if not specific_addr or not re.search(r'\d{2}-\d{3}', specific_addr): return False
        return True

    def _generate_selected(self):
        targets = []
        for r in range(self.table_owners.rowCount()):
            it = self.table_owners.item(r, 0)
            if it and it.checkState() == Qt.CheckState.Checked and not self.table_owners.isRowHidden(r):
                data = self.table_owners.item(r, 4).data(Qt.ItemDataRole.UserRole)
                if data:
                    idx, specific_addr = data
                    targets.append((self.owners[idx], specific_addr))
                    
        if not targets: return QMessageBox.warning(self, 'Brak', 'Nie zaznaczono nikogo ptaszkiem z listy.')
                
        self._generate_batch(targets)

    def _generate_all(self):
        if not self.owners: return QMessageBox.warning(self, 'Brak właścicieli', 'Wczytaj właścicieli na zakładce Wypisy.')
        
        targets = []
        hide_generated = self.chk_hide_generated.isChecked()
        filter_text = self.search_owners_edit.text().strip().lower()
        
        for o in self.owners:
            cats = set()
            for p_info in o.get('parcels', []):
                num = p_info['number'] if isinstance(p_info, dict) else str(p_info)
                for known_p in self.parcels:
                    if known_p.get('number') == num:
                        c = known_p.get('category', '')
                        if 'Demonta' in c or 'Demontaż' in c: cats.add('demontaz')
                        if 'Budowa' in c: cats.add('budowa')
                        if 'Pe' in c or 'Przyłącze' in c or 'Przylacze' in c: cats.add('budowa')
                        
            req_budowa = 'budowa' in cats
            req_demontaz = 'demontaz' in cats
            got_budowa = self._decl_done(o, specific_addr, 'budowa')
            got_demontaz = self._decl_done(o, specific_addr, 'demontaz')
            
            is_complete = True
            if req_budowa and not got_budowa: is_complete = False
            if req_demontaz and not got_demontaz: is_complete = False

            if hide_generated and is_complete: continue
            
            addresses = [o.get('address', '')]
            if o.get('address_2'):
                addresses.append(o.get('address_2'))
                
            for addr in addresses:
                if filter_text:
                    fmt = self.config.get('couple_format_decl', 0)
                    display_name = o.get('name_plural', o.get('full_name', '')) if fmt == 0 else o.get('name_separate', o.get('full_name', ''))
                    parcels_str = ' '.join([str(p.get('number', p)) if isinstance(p, dict) else str(p) for p in o.get('parcels', [])])
                    search_target = f"{display_name} {addr} {parcels_str}".lower()
                    if filter_text not in search_target: continue

                targets.append((o, addr))
                
        self._generate_batch(targets)

    def _generate_batch(self, targets):
        out_dir = QFileDialog.getExistingDirectory(self, 'Wybierz folder wyjściowy')
        if not out_dir: return
        
        p = self._get_params()
        if not p['template_path_budowa'] or not p['template_path_demontaz']:
            self._set_default_template()
            p = self._get_params()

        from utils.docx_utils import generate_declaration
        success, errors = 0, []
        skipped_info = []
        
        fmt = self.config.get('couple_format_decl', 0)
        
        for o, specific_addr in targets:
            if not self._is_valid_for_gen(o, specific_addr):
                skipped_info.append(f"{o.get('full_name', 'Nieznany')} (brak adresu/kodu, zmarły lub instytucja)")
                continue
                
            parcels = o.get('parcels', [])
            
            cats = set()
            b_nums, d_nums = [], []
            area_bud, area_dem = 0.0, 0.0
            kw_bud, kw_dem = [], []
            
            for p_info in parcels:
                num = p_info['number'] if isinstance(p_info, dict) else str(p_info)
                kw = p_info.get('kw', '') if isinstance(p_info, dict) else ''
                p_area = p_info.get('area_ha', 0.0) if isinstance(p_info, dict) else 0.0
                
                for known_p in self.parcels:
                    if known_p.get('number') == num:
                        c = known_p.get('category', '')
                        if 'Demonta' in c or 'Demontaż' in c: cats.add('demontaz')
                        if 'Budowa' in c: cats.add('budowa')
                        if 'Pe' in c or 'Przyłącze' in c or 'Przylacze' in c: cats.add('budowa')
                        
                        if 'Budowa' in c or 'Pe' in c or 'Przyłącze' in c or 'Przylacze' in c: 
                            b_nums.append(num)
                            area_bud += p_area
                            if kw and kw not in kw_bud: kw_bud.append(kw)
                        if 'Demonta' in c or 'Demontaż' in c: 
                            d_nums.append(num)
                            area_dem += p_area
                            if kw and kw not in kw_dem: kw_dem.append(kw)
            
            b_str, d_str = ', '.join(set(b_nums)), ', '.join(set(d_nums))
            auto_type = p['declaration_type']
            if 'demontaz' in cats and 'budowa' in cats: auto_type = 'obie'
            elif 'demontaz' in cats: auto_type = 'demontaz'
            elif 'budowa' in cats: auto_type = 'budowa'

            types_to_gen = ['budowa', 'demontaz'] if auto_type == 'obie' else [auto_type]
            short_name = self._get_short_name(o.get('first_name', ''), o.get('last_name', ''))
            
            has_two_addresses = bool(o.get('address_2'))
            addr_suffix = ""
            if has_two_addresses:
                street_match = re.search(r'ul\.\s*([A-Za-zŻżÓóŁłĆćŃńŚśŹźŻż])', specific_addr, re.I)
                if street_match: addr_suffix = f" {street_match.group(1).upper()}"
                else: addr_suffix = f" 2" if specific_addr == o.get('address_2') else ""

            generated_anything_for_owner = False

            for t in types_to_gen:
                current_valid_nums = set(b_nums) if t == 'budowa' else set(d_nums)
                v_list, c_list, m_list, p_list, pn_list = [], [], [], [], []
                street_dz_list = []
                
                for p_info in parcels:
                    if isinstance(p_info, dict):
                        num = p_info.get('number', '')
                        if num not in current_valid_nums: continue
                        if p_info.get('voivodeship') and p_info['voivodeship'] not in v_list: v_list.append(p_info['voivodeship'])
                        if p_info.get('county') and p_info['county'] not in c_list: c_list.append(p_info['county'])
                        if p_info.get('municipality') and p_info['municipality'] not in m_list: m_list.append(p_info['municipality'])
                        if p_info.get('precinct') and p_info['precinct'] not in p_list: p_list.append(p_info['precinct'])
                        if p_info.get('precinct_number') and p_info['precinct_number'] not in pn_list: pn_list.append(p_info['precinct_number'])
                        if self.config.get('extract_parcel_address', True):
                            a = p_info.get('parcel_address')
                            if a and a not in street_dz_list: street_dz_list.append(a)

                v_str = ', '.join(v_list) if v_list else o.get('voivodeship', '') or p['voivodeship']
                c_str = ', '.join(c_list) if c_list else o.get('county', '') or p['county']
                m_str = ', '.join(m_list) if m_list else o.get('municipality', '') or p['municipality']
                precinct_str = ', '.join(p_list) if p_list else o.get('precinct', '') or p['precinct']
                precinct_number_str = ', '.join(pn_list) if pn_list else o.get('precinct_number', '')
                
                # Zastosowanie opcji "Wymuś wielkie litery"
                if self.config.get('decl_precinct_uppercase', False):
                    precinct_str = precinct_str.upper()

                t_tmpl = p['template_path_budowa'] if t == 'budowa' else p['template_path_demontaz']
                dev_desc = p['device_description_budowa'] if t == 'budowa' else p['device_description_demontaz']

                if not Path(t_tmpl).exists(): continue

                fname = f"Oświadczenie woli {t} {short_name}{addr_suffix}.docx".replace('  ', ' ')
                fname = re.sub(r'[<>:"/\\|?*]', '', fname)
                out_path = str(Path(out_dir) / fname)
                
                display_name = o.get('name_plural', o.get('full_name', '')) if fmt == 0 else o.get('name_separate', o.get('full_name', ''))
                
                street_field = ", ".join(street_dz_list) if street_dz_list else p['street']
                
                ok = generate_declaration(
                    template_path=t_tmpl,
                    output_path=out_path,
                    project_number=p['project_number'],
                    place=p['place'], 
                    date_str=p['date_str'],
                    owner_name=display_name,
                    pesel=o.get('pesel') or '',
                    nip=o.get('nip') or '',
                    location=self._location_for_decl(o.get('city', '') or p['location']),
                    street=self._street_for_decl(street_field),
                    voivodeship=v_str,
                    county=self._county_for_powiat(c_str, o.get('city', '') or p['location']),
                    municipality=m_str,
                    parcel_numbers_budowa=b_str,
                    parcel_numbers_demontaz=d_str,
                    area_ha=(f"łącznej {format_area_pl(area_bud)}" if len(b_nums)>1 else format_area_pl(area_bud)) if t == 'budowa' else (f"łącznej {format_area_pl(area_dem)}" if len(d_nums)>1 else format_area_pl(area_dem)),
                    area_ha_budowa=(f"łącznej {format_area_pl(area_bud)}" if len(b_nums)>1 else format_area_pl(area_bud)),
                    area_ha_demontaz=(f"łącznej {format_area_pl(area_dem)}" if len(d_nums)>1 else format_area_pl(area_dem)),
                    precinct=precinct_str,
                    precinct_number=precinct_number_str,
                    kw_numbers=(', '.join(kw_bud) if t == 'budowa' else ', '.join(kw_dem)),
                    kw_numbers_budowa=', '.join(kw_bud),
                    kw_numbers_demontaz=', '.join(kw_dem),
                    device_description=dev_desc,
                    declaration_type=t,
                    tag_map=self.config.get("declaration_tag_map"),
                    unlock_docs=self.config.get("unlock_generated_docs", False)
                )
                if ok: 
                    success += 1
                    generated_anything_for_owner = True
                    
                    if t == 'budowa':
                        self._set_decl_done(o, specific_addr, 'budowa', True)
                    elif t == 'demontaz':
                        self._set_decl_done(o, specific_addr, 'demontaz', True)
                        
                else: 
                    errors.append(f"{display_name} ({t})")
            
            if generated_anything_for_owner:
                o['decl_generated'] = True

        self.owners_changed.emit(self.owners)
        self._refresh_owners_table()

        msg = f'Wygenerowano dokumentów: {success}.'
        if errors: msg += f'\n\nBłędy generowania:\n' + "\n".join(errors)
        if skipped_info:
            msg += f'\n\nNie utworzono / pominięto (Ilość: {len(skipped_info)}):\n' + "\n".join(skipped_info[:15])
            if len(skipped_info) > 15: msg += "\n...i więcej."
        QMessageBox.information(self, 'Wynik', msg)

    def set_project(self, project: dict):
        self.active_project_path = project.get('path', '')
        self.project_num_edit.setText(project.get('symbol', ''))
        self._load_groups()

    def set_parcels(self, parcels: list):
        self.parcels = parcels
        self._refresh_owners_table()