"""
owners_list.py – Zakładka wypisów z rejestru gruntów / lista właścicieli  Wypisy
"""
import json
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QGroupBox, QSplitter, QTextEdit,
    QHeaderView, QAbstractItemView, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QShortcut, QKeySequence

from utils.parcel_sorting import parcel_sort_key as parcel_number_sort_key
from utils.table_layout import (
    apply_minimum_widths,
    ensure_columns_visible,
    remember_column_count,
    state_matches_columns,
)
from utils.wypis_fields import (
    format_municipality_for_config,
    format_ownership,
    normalize_parcel_identifier,
)

def format_area_pl(val) -> str:
    if not val: return "0,00"
    s = f"{float(val):.4f}".rstrip('0')
    if s.endswith('.'): return s[:-1] + ",00"
    if len(s.split('.')[1]) < 2: s += '0'
    return s.replace('.', ',')

def auto_classify_and_clean_owner(o: dict):
    full_name = f"{o.get('last_name', '')} {o.get('first_name', '')} {o.get('full_name', '')}".lower()
    inst_keywords = [
        'gmina', 'urząd', 'miasto', 'skarb państwa', 'państwowe', 'państwo', 
        'polskie koleje państwowe', 'pkp', 'nadleśnictwo', 'lasy państwowe', 
        'województw', 'powiat', 'starostwo', 'wody polskie', 'dyrekcja', 'agencja'
    ]
    church_keywords = ['parafia', 'kościół', 'diecezja', 'biskupstwo', 'zakon', 'rzymskokatolick']
    spolka_keywords = ['spółka', 'sp.', 'z o.o', 's.a.', 'spółdzielnia', 'spółdzielni']
    company_keywords = ['przedsiębiorstwo', 'f.h.u', 'p.p.h.u', 'firma', 'usługi']
    
    is_inst = any(k in full_name for k in inst_keywords)
    is_church = any(k in full_name for k in church_keywords)
    is_spolka = any(k in full_name for k in spolka_keywords)
    is_comp = any(k in full_name for k in company_keywords)
    
    if is_inst:
        o['is_institution'] = True; o['is_church'] = False; o['is_spolka'] = False; o['is_company'] = False
    elif is_church:
        o['is_institution'] = False; o['is_church'] = True; o['is_spolka'] = False; o['is_company'] = False
    elif is_spolka:
        o['is_institution'] = False; o['is_church'] = False; o['is_spolka'] = True; o['is_company'] = False
    elif is_comp:
        o['is_institution'] = False; o['is_church'] = False; o['is_spolka'] = False; o['is_company'] = True

    for addr_key in ['address', 'address_2']:
        val = o.get(addr_key, '')
        if val:
            val = re.sub(r'(?i)(adres\s*)?koresp[a-z\.]*\s*:?', '', val)
            o[addr_key] = val.strip()

class AddOwnerDialog(QDialog):
    def __init__(self, owner: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Właściciel / Instytucja / Firma / Spółka / Parafia')
        self.setMinimumWidth(500)
        layout = QFormLayout(self)
        layout.setSpacing(8)

        o = owner or {}
        self.last_name_edit = QLineEdit(o.get('last_name', ''))
        layout.addRow('Nazwisko (lub Pełna Nazwa Firmy/Spółki):', self.last_name_edit)
        
        self.first_name_edit = QLineEdit(o.get('first_name', ''))
        layout.addRow('Imię (zostaw puste dla firm/inst.):', self.first_name_edit)
        
        self.last_name_plural_edit = QLineEdit(o.get('last_name_plural', ''))
        layout.addRow('Nazwisko odmienione:', self.last_name_plural_edit)
        
        self.name_plural_edit = QLineEdit(o.get('name_plural', o.get('full_name', '')))
        layout.addRow('Pełna nazwa (Odmienione/Razem):', self.name_plural_edit)
        
        self.name_separate_edit = QLineEdit(o.get('name_separate', o.get('full_name', '')))
        layout.addRow('Pełna nazwa (Osobno):', self.name_separate_edit)
        
        self.address_edit = QLineEdit(o.get('address', ''))
        layout.addRow('Adres:', self.address_edit)
        
        self.address2_edit = QLineEdit(o.get('address_2', ''))
        layout.addRow('Adres 2:', self.address2_edit)
        
        self.city_edit = QLineEdit(o.get('city', ''))
        layout.addRow('Miejscowość działki:', self.city_edit)

        self.street_dz_edit = QLineEdit(o.get('parcel_street', ''))
        layout.addRow('Ulica działki:', self.street_dz_edit)
        
        self.pesel_edit = QLineEdit(o.get('pesel', ''))
        layout.addRow('PESEL:', self.pesel_edit)
        
        self.nip_edit = QLineEdit(o.get('nip', ''))
        layout.addRow('NIP:', self.nip_edit)
        
        self.voivodeship_edit = QLineEdit(o.get('voivodeship', ''))
        layout.addRow('Województwo:', self.voivodeship_edit)
        
        self.county_edit = QLineEdit(o.get('county', ''))
        layout.addRow('Powiat:', self.county_edit)
        
        self.municipality_edit = QLineEdit(o.get('municipality', ''))
        layout.addRow('Jedn. Ewid./Gmina:', self.municipality_edit)
        
        self.precinct_edit = QLineEdit(o.get('precinct', ''))
        layout.addRow('Obręb:', self.precinct_edit)
        
        self.precinct_num_edit = QLineEdit(o.get('precinct_number', ''))
        layout.addRow('Nr Obrębu:', self.precinct_num_edit)
        
        self.parcels_edit = QLineEdit(', '.join(o.get('parcel_numbers', [p.get('number', '') for p in o.get('parcels', [])])))
        layout.addRow('Działki:', self.parcels_edit)
        
        area_val = o.get('total_area_ha', 0.0)
        self.area_edit = QLineEdit("" if not area_val else format_area_pl(area_val).replace(',', '.'))
        layout.addRow('Pow. [ha]:', self.area_edit)
        
        self.kw_edit = QLineEdit(', '.join(o.get('kw_numbers', [])))
        layout.addRow('Numer KW:', self.kw_edit)
        
        self.share_edit = QLineEdit(o.get('share', '1/1'))
        layout.addRow('Udział:', self.share_edit)

        self.ownership_form_edit = QLineEdit(o.get('ownership_form', ''))
        self.ownership_form_edit.setPlaceholderText(
            'np. współwłasność, wspólność ustawowa, udział łączny'
        )
        layout.addRow('Forma władania:', self.ownership_form_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> dict:
        parcels_raw = self.parcels_edit.text().strip()
        parcels = [p.strip() for p in re.split(r'[,;\s]+', parcels_raw) if p.strip()] if parcels_raw else []
        kw_raw = self.kw_edit.text().strip()
        kws = [k.strip() for k in kw_raw.split(',') if k.strip()] if kw_raw else []
        try: area = float(self.area_edit.text().replace(',', '.'))
        except: area = 0.0
        
        fn = self.first_name_edit.text().strip()
        ln = self.last_name_edit.text().strip()
        full = f"{ln} {fn}".strip() if fn else ln
        
        return {
            'last_name': ln, 'first_name': fn, 'full_name': full,
            'last_name_plural': self.last_name_plural_edit.text().strip(),
            'name_plural': self.name_plural_edit.text().strip() or full,
            'name_separate': self.name_separate_edit.text().strip() or full,
            'address': self.address_edit.text().strip(), 'address_2': self.address2_edit.text().strip(),
            'city': self.city_edit.text().strip(), 
            'parcel_street': self.street_dz_edit.text().strip(),
            'pesel': self.pesel_edit.text().strip(),
            'nip': self.nip_edit.text().strip(), 'voivodeship': self.voivodeship_edit.text().strip(),
            'county': self.county_edit.text().strip(), 'municipality': self.municipality_edit.text().strip(),
            'precinct': self.precinct_edit.text().strip(), 'precinct_number': self.precinct_num_edit.text().strip(), 'parcel_numbers': parcels,
            'total_area_ha': area, 'kw_numbers': kws, 'share': self.share_edit.text().strip(),
            'ownership_form': self.ownership_form_edit.text().strip(),
            'parcels': [{'number': n, 'area_ha': 0.0, 'kw': kws[i] if i < len(kws) else (kws[-1] if kws else '')} for i, n in enumerate(parcels)],
            'is_dead': False, 'is_institution': False, 'is_company': False, 'is_spolka': False, 'is_church': False, 'is_couple': False
        }


class OwnersListWidget(QWidget):
    owners_changed = Signal(list)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.owners = []
        self.active_parcels = []
        self.current_project_city = ''
        
        self.setAcceptDrops(True) 
        self._build_ui()

    def set_active_parcels(self, parcels: list):
        self.active_parcels = parcels

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                ext = Path(path).suffix.lower()
                if ext in ['.pdf', '.jpg', '.jpeg', '.png']:
                    self.import_path_edit.setText(path)
                    self._load_wypis_file(path)
                    break

    def set_project(self, project: dict):
        self.current_project_city = project.get('city', '')
        self._load_from_project_state(project.get('path', ''))

    def _save_to_project_state(self):
        last_path = self.config.get('last_project_path', '')
        if not last_path: return
        state_file = Path(last_path) / 'owners_state.json'
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(self.owners, f, ensure_ascii=False, indent=2)
        except Exception: pass

    def _load_from_project_state(self, project_path: str):
        self.owners.clear()
        if not project_path:
            self._refresh_table()
            return
        state_file = Path(project_path) / 'owners_state.json'
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    self.owners = json.load(f)
            except Exception: pass
        self._refresh_table()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 4, 8)

        header_row = QHBoxLayout()
        lbl = QLabel('👥 Lista Właścicieli / Wypisy')
        lbl.setStyleSheet('font-size:15px; font-weight:700;')
        header_row.addWidget(lbl)
        header_row.addStretch()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Szukaj (nazwisko, działka, adres)...')
        self.search_edit.setMinimumWidth(250)
        self.search_edit.textChanged.connect(self._apply_search)
        header_row.addWidget(self.search_edit)
        header_row.addWidget(QLabel('Sortowanie:'))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['Domyślne', 'Alfabetycznie', 'Od najniższego numeru działki', 'Od najwyższego numeru działki'])
        try:
            saved_sort_index = int(self.config.get('owners_list_sort_index', 0))
        except (TypeError, ValueError):
            saved_sort_index = 0
        if 0 <= saved_sort_index < self.sort_combo.count():
            self.sort_combo.setCurrentIndex(saved_sort_index)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        header_row.addWidget(self.sort_combo)
        left_layout.addLayout(header_row)

        self.table = QTableWidget(0, 24)
        self.table.setHorizontalHeaderLabels([
            'Status Sprawy', 'Typ', 'Adres Status', 'Działki',
            'Nazwisko / Instytucja', 'Imię', 'Nazwisko odmienione', 'Nazwa (Odmieniona/Razem)', 'Nazwa (Osobno)',
            'Adres', 'Pow. [ha]', 'KW', 'Udział', 'Forma władania',
            'Miejscowośc działki', 'Ulica Działki', 'PESEL', 'NIP', 'Województwo', 'Powiat', 'Jedn. Ewid./Gmina', 'Obręb', 'Nr Obrębu', 'Identyfikator działki'
        ])
        
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        self.table.currentItemChanged.connect(self._on_selection)
        self.table.itemChanged.connect(self._on_cell_edited)
        
        QShortcut(QKeySequence("Delete"), self.table).activated.connect(self._delete_owner)

        self.table.horizontalHeader().setSectionsMovable(True)
        table_state_owners_hex = self.config.get('table_state_owners', '')
        # Układ zapisany dla innej liczby kolumn (np. sprzed dodania
        # „Identyfikatora działki”) potrafił ukryć nowe kolumny. Taki zapis
        # pomijamy i budujemy układ od nowa.
        state_is_current = state_matches_columns(
            self.config, 'table_state_owners', self.table.columnCount()
        )
        if table_state_owners_hex and state_is_current:
            from PySide6.QtCore import QByteArray
            self.table.horizontalHeader().restoreState(
                QByteArray.fromHex(str(table_state_owners_hex).encode())
            )

        # Żadna kolumna z danymi nie może pozostać ukryta ani zerowej
        # szerokości — inaczej znika z tabeli mimo poziomego przewijania.
        ensure_columns_visible(
            self.table,
            wide_columns={3: 200, 23: 220},
        )
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        for i in [5, 6, 7, 8]:
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        # Kolumny z długą treścią: działki oraz identyfikatory działek.
        self.table.horizontalHeader().setSectionResizeMode(
            23, QHeaderView.ResizeMode.Interactive
        )
        apply_minimum_widths(
            self.table,
            {5: 200, 6: 200, 7: 200, 8: 200, 3: 200, 23: 220},
        )

        remember_column_count(
            self.config, 'table_state_owners', self.table.columnCount()
        )
        self.config['table_state_owners'] = (
            self.table.horizontalHeader().saveState().toHex().data().decode()
        )
            
        self.table.horizontalHeader().sectionResized.connect(lambda *args: self.config.update({'table_state_owners': self.table.horizontalHeader().saveState().toHex().data().decode()}))
        self.table.horizontalHeader().sectionMoved.connect(lambda *args: self.config.update({'table_state_owners': self.table.horizontalHeader().saveState().toHex().data().decode()}))
        left_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton('+ Dodaj ręcznie')
        self.btn_add.setObjectName('btn_primary')
        self.btn_add.clicked.connect(self._add_owner)
        btn_row.addWidget(self.btn_add)
        
        self.btn_merge = QPushButton('🔗 Połącz w Parę')
        self.btn_merge.setStyleSheet('background-color: #9b5de5; color: white;')
        self.btn_merge.clicked.connect(self._merge_into_couple)
        btn_row.addWidget(self.btn_merge)

        self.btn_unmerge = QPushButton('✂️ Rozłącz Parę')
        self.btn_unmerge.setStyleSheet('background-color: #f39c12; color: white;')
        self.btn_unmerge.clicked.connect(self._unmerge_couple)
        btn_row.addWidget(self.btn_unmerge)

        self.btn_edit = QPushButton('✏ Edytuj')
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._edit_owner)
        btn_row.addWidget(self.btn_edit)

        self.btn_delete = QPushButton('🗑 Usuń zaznaczone (Delete)')
        self.btn_delete.setObjectName('btn_danger')
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_owner)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        self.lbl_count = QLabel('Właścicieli: 0')
        self.lbl_count.setStyleSheet('color:#aaa;')
        btn_row.addWidget(self.lbl_count)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 8, 8, 8)

        import_box = QGroupBox('Import wypisów (Przeciągnij plik w to okno)')
        import_layout = QVBoxLayout(import_box)

        self.import_path_edit = QLineEdit()
        self.import_path_edit.setReadOnly(True)
        self.import_path_edit.setPlaceholderText('PDF / JPG z wypisem...')
        import_layout.addWidget(self.import_path_edit)

        btn_browse_pdf = QPushButton('📂 Wybierz 1 plik PDF z wypisem')
        btn_browse_pdf.clicked.connect(self._browse_wypis)
        import_layout.addWidget(btn_browse_pdf)

        btn_load_folder = QPushButton('📁 Automatycznie wczytaj z "wypisy/"')
        btn_load_folder.clicked.connect(self._load_from_project_folder)
        import_layout.addWidget(btn_load_folder)

        btn_browse_folder = QPushButton('📂 Wybierz inny folder z plikami PDF...')
        btn_browse_folder.clicked.connect(self._browse_custom_folder)
        import_layout.addWidget(btn_browse_folder)

        self.ocr_output = QTextEdit()
        self.ocr_output.setReadOnly(True)
        self.ocr_output.setMaximumHeight(80)
        import_layout.addWidget(self.ocr_output)

        right_layout.addWidget(import_box)

        detail_box = QGroupBox('Szczegóły wybranego właściciela')
        detail_layout = QVBoxLayout(detail_box)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(250)
        detail_layout.addWidget(self.detail_text)
        right_layout.addWidget(detail_box)

        right_layout.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([750, 350])

    def _status_color(self, status):
        return {
            "Do zrobienia": "#e74c3c",
            "W toku": "#f1c40f",
            "Wygenerowano": "#e67e22",
            "Wysłane": "#3498db",
            "Zakończone": "#2ecc71",
        }.get(status, "#f1c40f")

    def _type_color(self, typ):
        return {
            "Osoba fiz.": "#2ecc71",
            "Para": "#1abc9c",
            "Firma": "#3498db",
            "Spółka": "#2980b9",
            "Parafia": "#f39c12",
            "Instytucja": "#9b5de5",
            "ZMARŁY/A": "#e74c3c",
        }.get(typ, "#2ecc71")

    def _apply_combo_colors(self, combo, color):
        combo.setStyleSheet(
            f"QComboBox {{ color: {color}; font-weight: bold; }} "
            "QComboBox QAbstractItemView { selection-background-color: #34495e; }"
        )

    def _get_address_status(self, address: str) -> str:
        if not address.strip(): return "Brak adresu"
        if not re.search(r'\d{2}-\d{3}', address): return "Brak kodu poczt."
        return "OK"

    def _create_status_combo(self, current_status, owner_idx):
        combo = QComboBox()
        combo.addItems(["Do zrobienia", "W toku", "Wygenerowano", "Wysłane", "Zakończone"])
        for i in range(combo.count()):
            st = combo.itemText(i)
            combo.setItemData(i, QColor(self._status_color(st)), Qt.ItemDataRole.ForegroundRole)
        combo.blockSignals(True)
        if current_status: combo.setCurrentText(current_status)
        combo.blockSignals(False)
        self._apply_combo_colors(combo, self._status_color(current_status))
        combo.currentTextChanged.connect(lambda t, idx=owner_idx, cb=combo: self._on_status_combo_changed(idx, t, cb))
        return combo

    def _on_status_combo_changed(self, owner_idx, new_status, combo=None):
        if 0 <= owner_idx < len(self.owners):
            if combo is None: combo = self.sender()
            if combo: self._apply_combo_colors(combo, self._status_color(new_status))
            self.owners[owner_idx]['status_sprawy'] = new_status
            self._save_to_project_state()
            self.owners_changed.emit(self.owners)

    def _create_type_combo(self, owner, owner_idx):
        combo = QComboBox()
        combo.addItems(["Osoba fiz.", "Para", "Firma", "Spółka", "Parafia", "Instytucja", "ZMARŁY/A"])
        for i in range(combo.count()):
            typ = combo.itemText(i)
            combo.setItemData(i, QColor(self._type_color(typ)), Qt.ItemDataRole.ForegroundRole)
        combo.blockSignals(True)
        
        color = "#2ecc71"
        if owner.get('is_dead'):
            combo.setCurrentText("ZMARŁY/A")
            color = "#e74c3c"
        elif owner.get('is_institution'):
            combo.setCurrentText("Instytucja")
            color = "#9b5de5"
        elif owner.get('is_spolka'):
            combo.setCurrentText("Spółka")
            color = "#2980b9" # Niebieski odcień
        elif owner.get('is_company'):
            combo.setCurrentText("Firma")
            color = "#3498db"
        elif owner.get('is_church'):
            combo.setCurrentText("Parafia")
            color = "#f39c12"
        elif owner.get('is_couple'):
            combo.setCurrentText("Para")
            color = "#1abc9c"
        else:
            combo.setCurrentText("Osoba fiz.")
            
        self._apply_combo_colors(combo, color)
        combo.blockSignals(False)
        combo.currentTextChanged.connect(lambda t, idx=owner_idx, cb=combo: self._on_type_combo_changed(idx, t, cb))
        return combo

    def _on_type_combo_changed(self, owner_idx, new_type, combo=None):
        if 0 <= owner_idx < len(self.owners):
            o = self.owners[owner_idx]
            o['is_dead'] = (new_type == "ZMARŁY/A")
            o['is_institution'] = (new_type == "Instytucja")
            o['is_spolka'] = (new_type == "Spółka")
            o['is_company'] = (new_type == "Firma")
            o['is_church'] = (new_type == "Parafia")
            o['is_couple'] = (new_type == "Para")
            
            if combo is None: combo = self.sender()
            if combo: self._apply_combo_colors(combo, self._type_color(new_type))
            self._save_to_project_state()
            self.owners_changed.emit(self.owners)

    def _on_sort_changed(self, index: int):
        self.config['owners_list_sort_index'] = index
        self._refresh_table(self.search_edit.text())

    @staticmethod
    def _owner_table_value(owner: dict, key: str, parcel_key: str = None) -> str:
        """Zwraca wartość właściciela albo dane zapisane przy jego działkach.

        Starsze importy trzymają część danych gruntu tylko w rekordach działek.
        Widok tabeli ma je pokazywać tak samo jak panel szczegółów, bez zmiany
        zapisanych danych właściciela.
        """
        value = str(owner.get(key, '') or '').strip()
        if value:
            return value

        source_key = parcel_key or key
        values = []
        for parcel in owner.get('parcels', []):
            if not isinstance(parcel, dict):
                continue
            parcel_value = str(parcel.get(source_key, '') or '').strip()
            if parcel_value and parcel_value not in values:
                values.append(parcel_value)
        return ', '.join(values)

    def _refresh_table(self, filter_text: str = ''):
        self.table.blockSignals(True) 
        self.table.setRowCount(0)
        shown = 0
        indexed_owners = list(enumerate(self.owners))
        if hasattr(self, 'sort_combo'):
            sort_mode = self.sort_combo.currentText()
            if sort_mode == 'Alfabetycznie':
                indexed_owners.sort(key=lambda pair: (pair[1].get('last_name') or pair[1].get('full_name') or '').lower())
            elif sort_mode in ('Od najniższego numeru działki', 'Od najwyższego numeru działki'):
                def owner_parcel_sort_key(owner):
                    keys = []
                    for parcel in owner.get('parcels', owner.get('parcel_numbers', [])):
                        number = parcel.get('number', parcel) if isinstance(parcel, dict) else parcel
                        keys.append(parcel_number_sort_key(number))
                    # Właściciele bez działek są wyświetlani za wpisami z numerem.
                    return min(keys) if keys else ((3, ''),)

                indexed_owners.sort(
                    key=lambda pair: owner_parcel_sort_key(pair[1]),
                    reverse=(sort_mode == 'Od najwyższego numeru działki'),
                )
        for idx, o in indexed_owners:
            full_name = o.get('full_name', f"{o.get('last_name','')} {o.get('first_name','')}")
            if filter_text:
                ft = filter_text.lower()
                parcels_str = ' '.join([str(p.get('number', p)) if isinstance(p, dict) else str(p) for p in o.get('parcels', [])])
                identifiers_str = ' '.join([str(p.get('identifier', '')) for p in o.get('parcels', []) if isinstance(p, dict)])
                search_target = f"{full_name} {o.get('address', '')} {o.get('pesel', '')} {o.get('nip', '')} {parcels_str} {identifiers_str}".lower()
                if ft not in search_target:
                    continue
                    
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            combo_status = self._create_status_combo(o.get('status_sprawy', 'Do zrobienia'), idx)
            self.table.setCellWidget(row, 0, combo_status)
            
            combo_type = self._create_type_combo(o, idx)
            self.table.setCellWidget(row, 1, combo_type)
            
            owner_address = self._owner_table_value(o, 'address')
            if not owner_address:
                owner_address = str(o.get('address_2', '') or '').strip()
            addr_stat = self._get_address_status(owner_address)
            it_addr = QTableWidgetItem(addr_stat)
            if addr_stat == "OK": it_addr.setForeground(QColor("#2ecc71"))
            else: it_addr.setForeground(QColor("#e67e22")); it_addr.setFont(QFont('', -1, QFont.Weight.Bold))
            self.table.setItem(row, 2, it_addr)
            
            self.table.setItem(row, 4, QTableWidgetItem(o.get('last_name', '')))
            self.table.setItem(row, 5, QTableWidgetItem(o.get('first_name', '')))
            
            self.table.setItem(row, 6, QTableWidgetItem(o.get('last_name_plural', '')))
            self.table.setItem(row, 7, QTableWidgetItem(o.get('name_plural', o.get('full_name', ''))))
            self.table.setItem(row, 8, QTableWidgetItem(o.get('name_separate', o.get('full_name', ''))))
            
            self.table.setItem(row, 9, QTableWidgetItem(owner_address))
            parcels = ', '.join([p['number'] if isinstance(p, dict) else str(p) for p in o.get('parcels', o.get('parcel_numbers', []))])
            self.table.setItem(row, 3, QTableWidgetItem(parcels))
            
            area_val = o.get('total_area_ha', 0.0)
            if not area_val:
                try:
                    area_val = sum(
                        float(parcel.get('area_ha', 0) or 0)
                        for parcel in o.get('parcels', [])
                        if isinstance(parcel, dict)
                    )
                except (TypeError, ValueError):
                    area_val = 0.0
            self.table.setItem(row, 10, QTableWidgetItem(format_area_pl(area_val)))
            
            kw_values = o.get('kw_numbers') or [
                p['kw'] for p in o.get('parcels', [])
                if isinstance(p, dict) and p.get('kw')
            ]
            kws = ', '.join(str(value) for value in kw_values)
            self.table.setItem(row, 11, QTableWidgetItem(kws))
            self.table.setItem(row, 12, QTableWidgetItem(o.get('share', '1/1')))
            self.table.setItem(
                row, 13,
                QTableWidgetItem(
                    self._owner_table_value(o, 'ownership_form')
                ),
            )
            
            self.table.setItem(
                row, 14, QTableWidgetItem(self._owner_table_value(o, 'city'))
            )
            self.table.setItem(
                row,
                14,
                QTableWidgetItem(
                    self._owner_table_value(
                        o, 'parcel_street', parcel_key='parcel_address'
                    )
                ),
            )

            self.table.setItem(row, 16, QTableWidgetItem(o.get('pesel', '')))
            self.table.setItem(row, 17, QTableWidgetItem(o.get('nip', '')))
            self.table.setItem(
                row, 18, QTableWidgetItem(self._owner_table_value(o, 'voivodeship'))
            )
            self.table.setItem(
                row, 19, QTableWidgetItem(self._owner_table_value(o, 'county'))
            )
            self.table.setItem(
                row, 20,
                QTableWidgetItem(
                    format_municipality_for_config(
                        self._owner_table_value(o, 'municipality'), self.config
                    )
                ),
            )
            self.table.setItem(
                row, 21, QTableWidgetItem(self._owner_table_value(o, 'precinct'))
            )
            self.table.setItem(
                row, 22, QTableWidgetItem(self._owner_table_value(o, 'precinct_number'))
            )
            identifiers = []
            for p_info in o.get('parcels', []):
                if not isinstance(p_info, dict) or not p_info.get('identifier'):
                    continue
                ident = normalize_parcel_identifier(p_info.get('identifier'))
                if ident and ident not in identifiers:
                    identifiers.append(ident)
            self.table.setItem(row, 23, QTableWidgetItem(', '.join(identifiers)))
            
            self.table.item(row, 3).setData(Qt.ItemDataRole.UserRole, idx)
            shown += 1

        self.table.blockSignals(False)
        self.lbl_count.setText(f'Właścicieli: {len(self.owners)} (widocznych: {shown})')
        self.owners_changed.emit(self.owners)

    def _on_cell_edited(self, item):
        row = item.row()
        col = item.column()
        idx_data = self.table.item(row, 3).data(Qt.ItemDataRole.UserRole)
        if idx_data is None or idx_data >= len(self.owners): return
        owner = self.owners[idx_data]
        new_val = item.text().strip()
        
        # Numery są zgodne z faktycznym układem nagłówków tabeli. Wcześniej
        # przesunięcie o jedną kolumnę zapisywało np. Adres jako Działki,
        # przez co dane widoczne w szczegółach znikały z właściwych pól.
        # Kolumna 13 to "Forma władania"; dalsze pola przesunięte o jeden.
        mapping = {4: 'last_name', 5: 'first_name', 6: 'last_name_plural',
                   7: 'name_plural', 8: 'name_separate', 9: 'address',
                   13: 'ownership_form',
                   14: 'city', 15: 'parcel_street', 16: 'pesel', 17: 'nip',
                   18: 'voivodeship', 19: 'county', 20: 'municipality',
                   21: 'precinct', 22: 'precinct_number'}
                   
        if col in mapping:
            owner[mapping[col]] = new_val
            if col in [4, 5]: owner['full_name'] = f"{owner.get('last_name','')} {owner.get('first_name','')}".strip()
            if col == 9: self._refresh_table(self.search_edit.text())
        elif col == 3:
            nums = [x.strip() for x in new_val.split(',') if x.strip()]
            owner['parcel_numbers'] = nums
            old_parcels = owner.get('parcels', [])
            new_parcels = []
            for n in nums:
                found = next((p for p in old_parcels if isinstance(p, dict) and p.get('number') == n), None)
                if found: new_parcels.append(found)
                else: new_parcels.append({'number': n, 'area_ha': 0.0, 'kw': ''})
            owner['parcels'] = new_parcels
        elif col == 10:
            try: owner['total_area_ha'] = float(new_val.replace(',', '.'))
            except: owner['total_area_ha'] = 0.0
        elif col == 11:
            kws = [x.strip() for x in new_val.split(',') if x.strip()]
            owner['kw_numbers'] = kws
            if owner.get('parcels'):
                for i, p in enumerate(owner['parcels']):
                    if isinstance(p, dict):
                        p['kw'] = kws[i] if i < len(kws) else (kws[-1] if kws else '')
        elif col == 12: owner['share'] = new_val
        
        self._save_to_project_state()
        if col == 11: self._on_selection(self.table.currentItem(), None)

    def _apply_search(self, text: str):
        self._refresh_table(text)

    def _on_selection(self, current, _):
        if not current: 
            self.detail_text.clear()
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return
            
        row = current.row()
        idx_data = self.table.item(row, 3).data(Qt.ItemDataRole.UserRole)
        if idx_data is not None and idx_data < len(self.owners):
            o = self.owners[idx_data]
            typ_info = "Osoba fizyczna"
            if o.get('is_dead'): typ_info = "⚠️ OSOBA ZMARŁA"
            elif o.get('is_institution'): typ_info = "🏛️ INSTYTUCJA / URZĄD"
            elif o.get('is_spolka'): typ_info = "🏢 SPÓŁKA"
            elif o.get('is_company'): typ_info = "🏢 FIRMA"
            elif o.get('is_church'): typ_info = "⛪ PARAFIA / KOŚCIÓŁ"
            elif o.get('is_couple'): typ_info = "Para / Wspólność"
            
            ulice_dz_list = []
            parcels_info = []
            for p in o.get('parcels', []):
                if isinstance(p, dict):
                    num = p.get('number', '')
                    kw = p.get('kw', '')
                    area = p.get('area_ha', 0.0)
                    addr_dz = p.get('parcel_address', '')
                    identifier = p.get('identifier', '')
                    
                    if addr_dz and addr_dz not in ulice_dz_list:
                        ulice_dz_list.append(addr_dz)
                        
                    area_str = f" pow. {area:.4f} ha" if area else ""
                    kw_str = f" {kw}" if kw else ""
                    addr_dz_str = f"\n      └─ Ulica działki z wypisu: {addr_dz}" if addr_dz else ""
                    ident_str = f"\n      └─ Identyfikator działki: {identifier}" if identifier else ""
                    
                    loc_parts = []
                    for key, prefix in [('voivodeship', 'Woj.'), ('county', 'Pow.'), ('municipality', 'Gm.'), ('precinct', 'Obr.'), ('precinct_number', 'Nr')]:
                        if p.get(key): loc_parts.append(f"{prefix}: {p[key]}")
                    loc_str = f"\n      └─ Lokalizacja: {', '.join(loc_parts)}" if loc_parts else ""
                    
                    parcels_info.append(f"  - działka nr {num}{area_str}{kw_str}{addr_dz_str}{ident_str}{loc_str}")
                else:
                    parcels_info.append(f"  - działka nr {p}")
                    
            final_street_dz = o.get('parcel_street', ", ".join(ulice_dz_list))
            
            lines = [
                f"=== {typ_info} ===",
                f"Status Sprawy: {o.get('status_sprawy', 'Do zrobienia')}",
                f"Weryfikacja Adresu: {self._get_address_status(o.get('address', ''))}",
                f"Nazwisko/Firma/Instytucja: {o.get('last_name', '')}",
                f"Imię: {o.get('first_name', '')}",
                f"Nazwisko odmienione: {o.get('last_name_plural', '')}",
                f"Pełna nazwa (Razem): {o.get('name_plural', '')}",
                f"Pełna nazwa (Osobno): {o.get('name_separate', '')}",
                f"Adres: {o.get('address', '')}",
                f"Adres 2: {o.get('address_2', '')}" if o.get('address_2') else "",
                f"Miejscowość działki: {o.get('city', '')}",
                f"Identyfikator działki: {', '.join([str(p.get('identifier', '')) for p in o.get('parcels', []) if isinstance(p, dict) and p.get('identifier')])}",
                f"Ulica działki: {final_street_dz}",
                f"PESEL: {o.get('pesel', '')}",
                f"NIP: {o.get('nip', '')}",
                f"Województwo: {o.get('voivodeship', '')}",
                f"Powiat: {o.get('county', '')}",
                f"Jedn. Ewid./Gmina: {o.get('municipality', '')}",
                f"Obręb: {o.get('precinct', '')}",
                f"Nr Obrębu: {o.get('precinct_number', '')}",
                f"Pow. łącznie: {format_area_pl(o.get('total_area_ha', 0))} ha",
                f"Udział: {o.get('share', '1/1')}",
                f"Forma władania: {self._owner_table_value(o, 'ownership_form')}",
                "Działki i Księgi Wieczyste:"
            ] + parcels_info
            
            self.detail_text.setText('\n'.join(x for x in lines if x))
            for btn in [self.btn_edit, self.btn_delete]: btn.setEnabled(True)

    def _add_owner(self):
        o_def = {'city': self.current_project_city}
        dlg = AddOwnerDialog(owner=o_def, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            o = dlg.get_values()
            if o['last_name'] or o['first_name']:
                self.owners.append(o)
                self._refresh_table()
                self._save_to_project_state()

    def _merge_into_couple(self):
        selected_items = self.table.selectedItems()
        if not selected_items: return QMessageBox.warning(self, 'Błąd', 'Zaznacz dwie osoby (wiersze), aby połączyć je w parę.')
        
        indices = set()
        for item in selected_items:
            idx_data = self.table.item(item.row(), 3).data(Qt.ItemDataRole.UserRole)
            if idx_data is not None: indices.add(idx_data)
            
        if len(indices) != 2: return QMessageBox.warning(self, 'Błąd', 'Wybierz DOKŁADNIE DWIE osoby z listy.')
            
        idx1, idx2 = tuple(indices)
        o1 = self.owners[idx1]
        o2 = self.owners[idx2]
        
        f1, n1 = o1.get('first_name', ''), o1.get('last_name', '')
        f2, n2 = o2.get('first_name', ''), o2.get('last_name', '')
        
        from utils.gender_utils import detect_gender, get_couple_last_name
        if detect_gender(f1.split()[0] if f1 else "") == 'M' and detect_gender(f2.split()[0] if f2 else "") == 'F':
            f1, f2 = f2, f1
            n1, n2 = n2, n1
            o1, o2 = o2, o1
            
        n_plural = get_couple_last_name(n1, n2)
        if n_plural: name_plural = f"{f1} i {f2} {n_plural}".strip()
        elif n1 == n2: name_plural = f"{f1} i {f2} {n1}".strip()
        else: name_plural = f"{f1} {n1} i {f2} {n2}".strip()

        name_separate = f"{f1} {n1} i {f2} {n2}".strip()
            
        new_parcels = o1.get('parcels', [])[:]
        existing_nums = {p['number'] for p in new_parcels}
        for p in o2.get('parcels', []):
            if p['number'] not in existing_nums:
                new_parcels.append(p)
                existing_nums.add(p['number'])
                
        total_area = sum(p['area_ha'] for p in new_parcels)
        kw_numbers = list(set(p['kw'] for p in new_parcels if p.get('kw')))
        
        addr1 = o1.get('address', '')
        addr2 = o2.get('address', '')
        final_addr2 = o1.get('address_2', '')
        if addr2 and addr2 != addr1 and not final_addr2: final_addr2 = addr2
            
        new_owner = {
            'full_name': name_plural, 'first_name': f"{f1} i {f2}".strip(), 'last_name': n1 if n_plural else n1,
            'last_name_plural': n_plural if n_plural else n1,
            'name_plural': name_plural, 'name_separate': name_separate,
            'address': addr1, 'address_2': final_addr2, 'city': o1.get('city', ''),
            'parcel_street': o1.get('parcel_street', ''),
            'pesel': o1.get('pesel', ''), 'nip': o1.get('nip', ''),
            'voivodeship': o1.get('voivodeship', ''), 'county': o1.get('county', ''),
            'municipality': o1.get('municipality', ''), 'precinct': o1.get('precinct', ''), 'precinct_number': o1.get('precinct_number', ''),
            'parcels': new_parcels, 'parcel_numbers': [p['number'] for p in new_parcels],
            'total_area_ha': total_area, 'kw_numbers': kw_numbers,
            'share': o1.get('share', '1/1'), 'is_couple': True,
            'is_dead': False, 'is_institution': False, 'is_company': False, 'is_spolka': False, 'is_church': False,
            'status_sprawy': 'Do zrobienia'
        }
        
        for idx in sorted([idx1, idx2], reverse=True): del self.owners[idx]
        self.owners.append(new_owner)
        self._refresh_table(self.search_edit.text())
        self._save_to_project_state()
        self.detail_text.clear()
        QMessageBox.information(self, "Sukces", f"Złączono w parę:\n{name_plural}")

    def _unmerge_couple(self):
        selected_items = self.table.selectedItems()
        if not selected_items: return
        indices = set()
        for item in selected_items:
            idx_data = self.table.item(item.row(), 3).data(Qt.ItemDataRole.UserRole)
            if idx_data is not None: indices.add(idx_data)
            
        if len(indices) != 1: return QMessageBox.warning(self, "Błąd", "Wybierz dokładnie jedną parę do rozłączenia.")
        idx = list(indices)[0]
        o = self.owners[idx]
        if not o.get('is_couple'): return QMessageBox.warning(self, "Błąd", "Wybrany element nie jest parą.")
            
        import copy
        fn1, ln1, fn2, ln2 = "", "", "", ""
        parts = o.get('first_name', '').split(' i ')
        
        if len(parts) == 2:
            fn1, fn2 = parts[0].strip(), parts[1].strip()
            ln1, ln2 = o.get('last_name', ''), o.get('last_name', '')
        else:
            fn1, ln1 = o.get('first_name', ''), o.get('last_name', '')
            fn2, ln2 = "Osoba", "Druga"

        o1 = copy.deepcopy(o)
        o1['full_name'] = f"{fn1} {ln1}".strip(); o1['name_plural'] = o1['full_name']; o1['name_separate'] = o1['full_name']
        o1['first_name'] = fn1; o1['last_name'] = ln1; o1['last_name_plural'] = ln1; o1['is_couple'] = False; o1['address_2'] = ""
        
        o2 = copy.deepcopy(o)
        o2['full_name'] = f"{fn2} {ln2}".strip(); o2['name_plural'] = o2['full_name']; o2['name_separate'] = o2['full_name']
        o2['first_name'] = fn2; o2['last_name'] = ln2; o2['last_name_plural'] = ln2; o2['is_couple'] = False
        o2['address'] = o.get('address_2') or o.get('address')
        o2['address_2'] = ""

        del self.owners[idx]
        self.owners.insert(idx, o2)
        self.owners.insert(idx, o1)
        self._refresh_table(self.search_edit.text())
        self._save_to_project_state()
        QMessageBox.information(self, "Sukces", "Para została rozłączona na dwie osoby.")

    def _edit_owner(self):
        row = self.table.currentRow()
        if row < 0: return
        idx_data = self.table.item(row, 3).data(Qt.ItemDataRole.UserRole)
        if idx_data is None or idx_data >= len(self.owners): return
        o = self.owners[idx_data]
        
        ulice_dz_list = []
        for p_info in o.get('parcels', []):
            if isinstance(p_info, dict) and p_info.get('parcel_address'):
                a = p_info.get('parcel_address')
                if a not in ulice_dz_list: ulice_dz_list.append(a)
        
        if not o.get('parcel_street'):
            o['parcel_street'] = ", ".join(ulice_dz_list)
        
        dlg = AddOwnerDialog(owner=o, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_vals = dlg.get_values()
            self.owners[idx_data].update(new_vals)
            self._refresh_table(self.search_edit.text())
            self._save_to_project_state()
            self._on_selection(self.table.currentItem(), None)

    def _delete_owner(self):
        selected_items = self.table.selectedItems()
        if not selected_items: return
        indices_to_delete = set()
        for item in selected_items:
            idx_data = self.table.item(item.row(), 3).data(Qt.ItemDataRole.UserRole)
            if idx_data is not None: indices_to_delete.add(idx_data)
        if not indices_to_delete: return
        if QMessageBox.question(self, 'Usuń', f"Usunąć zaznaczonych właścicieli ({len(indices_to_delete)})?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            for idx in sorted(list(indices_to_delete), reverse=True):
                if idx < len(self.owners): del self.owners[idx]
            self._refresh_table(self.search_edit.text())
            self._save_to_project_state()
            self.detail_text.clear()
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)

    def _browse_wypis(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Otwórz wypis', '', 'PDF lub Obraz (*.pdf *.jpg *.jpeg *.png *.bmp);;Wszystkie (*.*)')
        if path:
            self.import_path_edit.setText(path)
            self._load_wypis_file(path)

    def _browse_custom_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Wybierz folder z plikami PDF')
        if not folder: return
        files = [f for f in Path(folder).glob('*') if f.suffix.lower() in ('.pdf', '.jpg', '.jpeg', '.png')]
        if not files: return QMessageBox.information(self, 'Brak plików', 'Brak plików w wybranym folderze.')
        added = 0
        for f in files: added += self._load_wypis_file(str(f), silent=True)
        self._refresh_table(self.search_edit.text())
        self._save_to_project_state()
        QMessageBox.information(self, 'Wczytano', f'Wczytano {len(files)} plików, dodano {added} właścicieli.')

    def _load_from_project_folder(self):
        last_path = self.config.get('last_project_path', '')
        if not last_path: return QMessageBox.warning(self, 'Brak projektu', 'Nie wybrano aktywnego projektu.')
        wypisy_dir = Path(last_path) / 'wypisy'
        if not wypisy_dir.exists(): return QMessageBox.warning(self, 'Brak folderu', f'Brak folderu wypisy/ w projekcie.')
        files = [f for f in wypisy_dir.glob('*') if f.suffix.lower() in ('.pdf', '.jpg', '.jpeg', '.png')]
        if not files: return QMessageBox.information(self, 'Brak plików', 'Brak plików PDF/JPG w folderze wypisy/')
        total_added = 0
        for f in files: total_added += self._load_wypis_file(str(f), silent=True)
        self._refresh_table(self.search_edit.text())
        self._save_to_project_state()
        QMessageBox.information(self, 'Wczytano', f'Wczytano {len(files)} plików, dodano {total_added} właścicieli.')

    META_KEYS = ('voivodeship', 'county', 'municipality', 'precinct', 'precinct_number')

    def _apply_wypis_file_meta_to_current_owners(
        self, file_meta: dict, parcel_meta: dict | None = None
    ):
        """Wpisuje metadane odczytane z importowanego PDF na obecnej liście.

        Wypis może obejmować kilka obrębów, gmin, a nawet powiatów. Dlatego
        każda działka dostaje wartość z własnej sekcji dokumentu
        (``parcel_meta``), a właściciel — zestawienie wartości wszystkich
        swoich działek. Wcześniej program brał tylko pierwszą znalezioną
        wartość i nadpisywał nią wszystko.
        """
        if not file_meta or not any(
            file_meta.get(key) for key in self.META_KEYS
        ):
            return

        parcel_meta = parcel_meta or {}

        for owner in self.owners:
            owner_values = {key: [] for key in self.META_KEYS}

            for parcel in owner.get('parcels', []):
                if not isinstance(parcel, dict):
                    continue
                number = str(parcel.get('number', '')).replace(' ', '')
                specific = parcel_meta.get(number, {})
                for meta_key in self.META_KEYS:
                    value = str(
                        specific.get(meta_key)
                        or file_meta.get(meta_key, '')
                        or ''
                    ).strip()
                    if not value:
                        continue
                    parcel[meta_key] = value
                    if value not in owner_values[meta_key]:
                        owner_values[meta_key].append(value)

            for meta_key in self.META_KEYS:
                if owner_values[meta_key]:
                    # Kilka obrębów jednego właściciela wypisujemy po przecinku.
                    owner[meta_key] = ', '.join(owner_values[meta_key])
                    continue
                fallback = str(file_meta.get(meta_key, '') or '').strip()
                if fallback:
                    owner[meta_key] = fallback

    def _apply_meta_to_imported_owners(
        self, owners: list, file_meta: dict, parcel_meta: dict | None = None
    ):
        """Wpisuje metadane w świeżo zaimportowanych właścicielach.

        Każda działka dostaje wartości ze swojej sekcji wypisu, a właściciel
        listę wszystkich wartości swoich działek. Dzięki temu osoba mająca
        działki w dwóch obrębach ma w polu Obręb obie nazwy.
        """
        parcel_meta = parcel_meta or {}

        for owner in owners:
            owner_values = {key: [] for key in self.META_KEYS}
            for parcel in owner.get('parcels', []):
                if not isinstance(parcel, dict):
                    continue
                number = str(parcel.get('number', '')).replace(' ', '')
                specific = parcel_meta.get(number, {})
                for meta_key in self.META_KEYS:
                    value = str(
                        specific.get(meta_key)
                        or parcel.get(meta_key)
                        or file_meta.get(meta_key, '')
                        or ''
                    ).strip()
                    if not value:
                        continue
                    parcel[meta_key] = value
                    if value not in owner_values[meta_key]:
                        owner_values[meta_key].append(value)

            for meta_key in self.META_KEYS:
                if owner_values[meta_key]:
                    owner[meta_key] = ', '.join(owner_values[meta_key])
                elif file_meta.get(meta_key):
                    owner[meta_key] = str(file_meta[meta_key]).strip()

    def _format_meta_report(self, file_meta: dict, parcel_meta: dict | None = None) -> str:
        """Buduje czytelny raport metadanych z importowanego wypisu."""
        labels = [
            ('voivodeship', 'Województwo'),
            ('county', 'Powiat'),
            ('municipality', 'Jedn. Ewid./Gmina'),
            ('precinct', 'Obręb'),
            ('precinct_number', 'Nr Obrębu'),
        ]
        lines = ['Metadane odczytane z PDF:']
        for key, label in labels:
            values = file_meta.get(f'{key}_values') or []
            text = ', '.join(values) if values else str(file_meta.get(key, '') or '')
            suffix = f'   (różnych wartości: {len(values)})' if len(values) > 1 else ''
            lines.append(f'{label}: {text}{suffix}')

        if parcel_meta:
            distinct_precincts = {
                str(entry.get('precinct', '')).strip()
                for entry in parcel_meta.values()
                if str(entry.get('precinct', '')).strip()
            }
            if len(distinct_precincts) > 1:
                lines.append('')
                lines.append('Obręb przypisany do poszczególnych działek:')
                for number in sorted(parcel_meta, key=parcel_number_sort_key):
                    entry = parcel_meta[number]
                    precinct = str(entry.get('precinct', '') or '').strip()
                    precinct_number = str(entry.get('precinct_number', '') or '').strip()
                    if not precinct and not precinct_number:
                        continue
                    detail = ' '.join(part for part in (precinct_number, precinct) if part)
                    lines.append(f'  • {number}: {detail}')
        return '\n'.join(lines)

    def _load_wypis_file(self, filepath: str, silent: bool = False) -> int:
        active_nums = [p['number'].replace(' ', '') for p in getattr(self, 'active_parcels', [])]
        
        if not active_nums and not silent:
            reply = QMessageBox.question(self, 'Pusta Lista Działek', 'Twoja zakładka "Lista działek" jest pusta.\n\nCzy chcesz zaimportować WSZYSTKICH właścicieli z tego pliku PDF (bez filtrowania działek)?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No: return 0
                
        ext = Path(filepath).suffix.lower()
        added, added_bypassed = 0, 0
        
        try:
            if ext == '.pdf':
                from utils.pdf_utils import (
                    extract_wypis_metadata_file,
                    extract_wypis_parcel_metadata_file,
                    parse_wypis_pdf,
                )
                owners = parse_wypis_pdf(filepath)
                file_meta = extract_wypis_metadata_file(filepath)
                # Wypis potrafi obejmować działki z kilku obrębów, gmin,
                # a nawet powiatów. Odczytujemy metadane osobno dla każdej
                # działki, zamiast brać wyłącznie pierwszą wartość z pliku.
                parcel_meta = extract_wypis_parcel_metadata_file(filepath)
                # Najpierw popraw obecnych właścicieli projektu (stare wpisy po wcześniejszym imporcie).
                self._apply_wypis_file_meta_to_current_owners(file_meta, parcel_meta)
                if any(file_meta.get(key) for key in self.META_KEYS):
                    try:
                        self.ocr_output.setText(
                            self._format_meta_report(file_meta, parcel_meta)
                        )
                    except Exception:
                        pass
                    # Od razu odśwież i zapisz stare wpisy po poprawie metadanych,
                    # nawet gdy później filtr działek odrzuci importowane osoby.
                    self._refresh_table(self.search_edit.text())
                    self._save_to_project_state()
                # Te same zasady stosujemy do właścicieli z bieżącego importu.
                self._apply_meta_to_imported_owners(owners, file_meta, parcel_meta)
            else:
                from utils.ocr_utils import parse_wypis_from_image
                owners, raw_text = parse_wypis_from_image(filepath)
                if raw_text: self.ocr_output.setText(raw_text[:1000])

            # Jeśli importowany PDF ma metadane (woj/pow/gmina/obręb), uzupełnij także
            # istniejących właścicieli po numerach działek. To naprawia stare wpisy, które
            # miały np. błędny Powiat = 'owe w' albo pusty Obręb/Nr Obrębu.
            if (
                ext == '.pdf'
                and 'file_meta' in locals()
                and any(file_meta.get(key) for key in self.META_KEYS)
            ):
                imported_nums = set()
                for imp_owner in owners:
                    for imp_parcel in imp_owner.get('parcels', []):
                        if isinstance(imp_parcel, dict) and imp_parcel.get('number'):
                            imported_nums.add(str(imp_parcel.get('number')).replace(' ', ''))
                if imported_nums:
                    for existing_owner in self.owners:
                        owner_nums = {str(p.get('number', p)).replace(' ', '') for p in existing_owner.get('parcels', [])}
                        if owner_nums & imported_nums:
                            self._apply_meta_to_imported_owners(
                                [existing_owner], file_meta, parcel_meta
                            )

            existing_names = {o.get('full_name', '').lower() for o in self.owners}
            rejected_owners = []

            for o in owners:
                auto_classify_and_clean_owner(o)

                if not o.get('city'): o['city'] = self.current_project_city
                o['status_sprawy'] = 'Do zrobienia'
                if active_nums:
                    filtered_parcels = [p for p in o['parcels'] if p['number'].replace(' ', '') in active_nums]
                    if not filtered_parcels:
                        rejected_owners.append(o)
                        continue 
                    o['parcels'] = filtered_parcels
                    o['parcel_numbers'] = [p['number'] for p in filtered_parcels]
                    o['total_area_ha'] = sum(p['area_ha'] for p in filtered_parcels)
                    o['kw_numbers'] = list(set(p['kw'] for p in filtered_parcels if p.get('kw')))

                name_key = o.get('full_name', '').lower()
                if name_key not in existing_names:
                    self.owners.append(o)
                    existing_names.add(name_key)
                    added += 1
                else:
                    existing = next((ex for ex in self.owners if ex.get('full_name', '').lower() == name_key), None)
                    if existing is not None:
                        for key in ['voivodeship', 'county', 'municipality', 'precinct', 'precinct_number', 'city', 'parcel_street']:
                            if o.get(key) and existing.get(key) != o.get(key):
                                existing[key] = o.get(key)
                        by_num = {str(p.get('number', p)): p for p in existing.get('parcels', []) if isinstance(p, dict)}
                        for new_p in o.get('parcels', []):
                            if not isinstance(new_p, dict):
                                continue
                            num = str(new_p.get('number', ''))
                            if not num:
                                continue
                            if num not in by_num:
                                existing.setdefault('parcels', []).append(new_p)
                                by_num[num] = new_p
                            else:
                                old_p = by_num[num]
                                for pk in ['kw', 'area_ha', 'parcel_address', 'identifier', 'voivodeship', 'county', 'municipality', 'precinct', 'precinct_number']:
                                    if new_p.get(pk) and old_p.get(pk) != new_p.get(pk):
                                        old_p[pk] = new_p.get(pk)
                        existing['parcel_numbers'] = [p.get('number') for p in existing.get('parcels', []) if isinstance(p, dict) and p.get('number')]
                        existing['total_area_ha'] = sum(float(p.get('area_ha', 0) or 0) for p in existing.get('parcels', []) if isinstance(p, dict))
                        existing['kw_numbers'] = list(dict.fromkeys([p.get('kw') for p in existing.get('parcels', []) if isinstance(p, dict) and p.get('kw')]))
                        added_bypassed += 1

            if added == 0 and rejected_owners and not silent:
                pdf_p_set = set()
                for ro in rejected_owners:
                    for p in ro['parcels']: pdf_p_set.add(p['number'])
                pdf_p_str = ", ".join(list(pdf_p_set)[:10])
                act_p_str = ", ".join(active_nums[:10]) if active_nums else "Brak"
                msg = f"Program nie dodał nikogo, ponieważ odczytane numery działek nie pasują do Twojej 'Listy Działek'!\n\nZnalezione w dokumencie: {pdf_p_str}\nTwoja lista: {act_p_str}\n\nCzy chcesz MIMO TO wczytać tych właścicieli z pominięciem filtru?"
                reply = QMessageBox.question(self, 'Brak dopasowania działek', msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    for ro in rejected_owners:
                        ro_key = ro.get('full_name', '').lower()
                        if ro_key not in existing_names:
                            self.owners.append(ro)
                            existing_names.add(ro_key)
                            added_bypassed += 1
                    if added_bypassed > 0:
                        self._refresh_table(self.search_edit.text())
                        self._save_to_project_state()
                        QMessageBox.information(self, 'Wymuszono dodanie', f'Dodano {added_bypassed} właścicieli z pominięciem blokady.')
            else:
                if not silent:
                    self._refresh_table(self.search_edit.text())
                    self._save_to_project_state()
                    if added > 0: QMessageBox.information(self, 'Wczytano', f'Dopasowano i dodano {added} właścicieli powiązanych z Twoją listą działek.')
                    else: QMessageBox.information(self, 'Wczytano', 'Nie znaleziono nowych właścicieli.')
            if (
                ext == '.pdf'
                and 'file_meta' in locals()
                and any(file_meta.get(key) for key in self.META_KEYS)
            ):
                self._apply_wypis_file_meta_to_current_owners(file_meta, parcel_meta)
                self._refresh_table(self.search_edit.text())
                self._save_to_project_state()
        except Exception as e:
            if not silent: QMessageBox.critical(self, 'Błąd', f'Błąd wczytywania:\n{e}')
        return added + added_bypassed

    def get_owners(self) -> list:
        return self.owners

    def set_owners(self, owners: list):
        self.owners = owners
        self._refresh_table(self.search_edit.text())