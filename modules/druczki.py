"""
druczek_tab.py - Zakładka do wypełniania pocztowych druczków PDF (Neoznaczki)
"""
import json
import os
import shutil
import sys
from pathlib import Path

from utils.global_settings import (
    load_global_druczek_profile,
    save_global_druczek_profile,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QFileDialog, QHeaderView, QAbstractItemView,
    QGroupBox, QFrame, QDialog, QDialogButtonBox, QFormLayout, QSpinBox, 
    QDoubleSpinBox, QScrollArea, QTabWidget, QComboBox, QCheckBox, QLineEdit, QListWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap, QShortcut, QKeySequence

class DruczekSettingsDialog(QDialog):
    def __init__(self, parent, config, tmpl_path):
        super().__init__(parent)
        self.config = config
        self.tmpl_path = tmpl_path
        self.setWindowTitle("⚙️ Zaawansowany Edytor Wizualny Druczków")
        self.resize(1500, 900) 
        
        default_profile = {
            'cols': 2, 'rows': 2, 'delta_x': 288, 'delta_y': 405, 
            's_font': 'Arial', 'a_font': 'Arial', 
            'sn_x': 36, 'sn_y': 42, 'sn_w': 150, 'sn_h': 30, 'sn_size': 10, 'sn_align': 0, 'sn_lh': 1.2, 
            'ss_x': 36, 'ss_y': 70, 'ss_w': 150, 'ss_h': 30, 'ss_size': 10, 'ss_align': 0, 'ss_lh': 1.2, 
            'sz_x': 36, 'sz_y': 105, 'sz_w': 40, 'sz_h': 20, 'sz_size': 10, 'sz_align': 0, 'sz_lh': 1.2, 
            'sc_x': 80, 'sc_y': 105, 'sc_w': 100, 'sc_h': 20, 'sc_size': 10, 'sc_align': 0, 'sc_lh': 1.2, 
            'an_x': 95, 'an_y': 124, 'an_w': 180, 'an_h': 30, 'an_size': 12, 'an_align': 0, 'an_lh': 1.2, 
            'as_x': 95, 'as_y': 150, 'as_w': 180, 'as_h': 30, 'as_size': 12, 'as_align': 0, 'as_lh': 1.2, 
            'az_x': 95, 'az_y': 180, 'az_w': 50, 'az_h': 20, 'az_size': 12, 'az_align': 0, 'az_lh': 1.2, 
            'ac_x': 150, 'ac_y': 180, 'ac_w': 120, 'ac_h': 20, 'ac_size': 12, 'ac_align': 0, 'ac_lh': 1.2
        }
        
        saved_profile = self.config.get('druczek_profile', {})
        self.profile = {**default_profile, **saved_profile}

        self.widgets = {}
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        
        left_panel = QWidget()
        left_panel.setFixedWidth(520)
        layout = QVBoxLayout(left_panel)
        layout.setContentsMargins(0, 0, 10, 0)
        
        info = QLabel(
            "<b>Tryb Zaawansowany:</b> Ustal szerokość i wysokość każdego "
            "pola, aby tekst się zmieścił.<br>Po kliknięciu OK pozycje i "
            "czcionki są zapisywane globalnie w <b>dane/druczek_profile.json</b>."
        )
        info.setStyleSheet("color: #2b5797; padding-bottom: 5px; font-size: 13px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #c0c0c0; border-radius: 5px; } QTabBar::tab { padding: 8px 15px; font-weight: bold; }")
        
        tab_grid = QWidget()
        form_grid = QFormLayout(tab_grid)
        form_grid.setSpacing(12)
        form_grid.addRow("Kolumny na stronie:", self._mk_w('cols', 1, 20))
        form_grid.addRow("Wiersze na stronie:", self._mk_w('rows', 1, 50))
        form_grid.addRow("Odstęp kolumn (X):", self._mk_w('delta_x', 0, 1000))
        form_grid.addRow("Odstęp wierszy (Y):", self._mk_w('delta_y', 0, 1000))
        self.tabs.addTab(tab_grid, "📐 Siatka PDF")
        
        tab_ns = QWidget()
        ly_ns = QVBoxLayout(tab_ns)
        ly_ns.addWidget(QLabel("<b>Czcionka dla Nadawcy:</b>"))
        ly_ns.addWidget(self._mk_c('s_font'))
        ly_ns.addWidget(self._build_field_group("1. Imię i Nazwisko Nadawcy", 'sn'))
        ly_ns.addWidget(self._build_field_group("2. Ulica Nadawcy", 'ss'))
        ly_ns.addWidget(self._build_field_group("3. Kod Pocztowy Nadawcy", 'sz'))
        ly_ns.addWidget(self._build_field_group("4. Miejscowość Nadawcy", 'sc'))
        scroll_ns = QScrollArea()
        scroll_ns.setWidget(tab_ns)
        scroll_ns.setWidgetResizable(True)
        scroll_ns.setStyleSheet("QScrollArea { border: none; }")
        self.tabs.addTab(scroll_ns, "👤 NADAWCA")
        
        tab_as = QWidget()
        ly_as = QVBoxLayout(tab_as)
        ly_as.addWidget(QLabel("<b>Czcionka dla Adresata:</b>"))
        ly_as.addWidget(self._mk_c('a_font'))
        ly_as.addWidget(self._build_field_group("1. Imię i Nazwisko Adresata", 'an'))
        ly_as.addWidget(self._build_field_group("2. Ulica Adresata", 'as'))
        ly_as.addWidget(self._build_field_group("3. Kod Pocztowy Adresata", 'az'))
        ly_as.addWidget(self._build_field_group("4. Miejscowość Adresata", 'ac'))
        scroll_as = QScrollArea()
        scroll_as.setWidget(tab_as)
        scroll_as.setWidgetResizable(True)
        scroll_as.setStyleSheet("QScrollArea { border: none; }")
        self.tabs.addTab(scroll_as, "📬 ADRESAT")
        
        layout.addWidget(self.tabs)
        layout.addStretch()
        
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.setStyleSheet("QPushButton { padding: 6px 20px; font-weight: bold; }")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("QScrollArea { border: 2px dashed #a4b0be; background: #e0e0e0; }")
        self.lbl_preview = QLabel("Generowanie podglądu...")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.lbl_preview)
        self.scroll_area.setWidgetResizable(True)
        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.scroll_area, 1)

    def _mk_w(self, key, mn, mx, is_float=False):
        w = QDoubleSpinBox() if is_float else QSpinBox()
        if is_float: w.setSingleStep(0.1)
        w.setRange(mn, mx)
        w.setValue(self.profile.get(key, 1.2 if is_float else 10))
        w.valueChanged.connect(self._update_preview)
        w.setStyleSheet("QSpinBox, QDoubleSpinBox { padding-right: 25px; padding-left: 5px; border: 1px solid #aaa; border-radius: 3px; background: white; }")
        self.widgets[key] = w
        return w

    def _mk_c(self, key, items=None):
        w = QComboBox()
        if not items: items = ["Arial", "Calibri", "Times New Roman", "Tahoma"]
        w.addItems(items)
        idx = w.findText(self.profile.get(key, items[0])) if items[0] == "Arial" else self.profile.get(key, 0)
        if isinstance(idx, int): w.setCurrentIndex(idx)
        w.currentIndexChanged.connect(self._update_preview)
        w.setStyleSheet("QComboBox { padding: 3px; border: 1px solid #aaa; border-radius: 3px; background: white; }")
        self.widgets[key] = w
        return w

    def _build_field_group(self, title, pfx):
        gb = QGroupBox(title)
        gb.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #d1d8e0; border-radius: 5px; margin-top: 10px; padding-top: 12px; background: #f8f9fa; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #3b3b98; }
        """)
        ly = QFormLayout(gb)
        ly.addRow("Pozycja (X, Y):", self._row_widgets(self._mk_w(f'{pfx}_x', 0, 1000), self._mk_w(f'{pfx}_y', 0, 1000)))
        ly.addRow("Rozmiar (Szer, Wys):", self._row_widgets(self._mk_w(f'{pfx}_w', 10, 500), self._mk_w(f'{pfx}_h', 10, 200)))
        ly.addRow("Wielkość i Wyrów.:", self._row_widgets(self._mk_w(f'{pfx}_size', 6, 30), self._mk_c(f'{pfx}_align', ["Lewo", "Środek", "Prawo", "Justuj"])))
        ly.addRow("Interlinia wierszy:", self._mk_w(f'{pfx}_lh', 0.5, 3.0, True))
        return gb

    def _row_widgets(self, w1, w2):
        ly = QHBoxLayout()
        ly.setContentsMargins(0,0,0,0)
        ly.addWidget(w1)
        ly.addWidget(w2)
        wdg = QWidget()
        wdg.setLayout(ly)
        return wdg

    def _update_preview(self):
        from utils.pdf_utils import render_druczek_preview
        if not self.tmpl_path or not Path(self.tmpl_path).exists(): return
        img_bytes = render_druczek_preview(self.tmpl_path, self.get_profile(), self.config.get('sender', {}))
        if img_bytes:
            pix = QPixmap()
            pix.loadFromData(img_bytes)
            self.lbl_preview.setPixmap(pix)
            self.lbl_preview.setFixedSize(pix.size())

    def get_profile(self):
        return {k: v.value() if isinstance(v, (QSpinBox, QDoubleSpinBox)) else (v.currentText() if "font" in k else v.currentIndex()) for k, v in self.widgets.items()}


class DruczekTabWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        # Profil pozycji i czcionek jest wspólny dla wszystkich projektów.
        # Odczyt pliku obsługuje także profile zapisane przez wcześniejsze
        # wersje programu.
        saved_profile = load_global_druczek_profile()
        if saved_profile:
            self.config['druczek_profile'] = saved_profile
        self.active_project_path = None
        self.shipments_c5 = []
        self._build_ui()

    def showEvent(self, event):
        super().showEvent(event)
        tmpl = self.config.get('druczek_template_path', '')
        if tmpl and Path(tmpl).exists():
            current_selection = self.combo_files.itemData(self.combo_files.currentIndex())
            if current_selection != tmpl:
                self.combo_files.blockSignals(True)
                exists = False
                for i in range(self.combo_files.count()):
                    if self.combo_files.itemData(i) == tmpl:
                        self.combo_files.setCurrentIndex(i)
                        exists = True
                        break
                if not exists:
                    self.combo_files.insertItem(0, f"[Z Ustawień] {Path(tmpl).name}", tmpl)
                    self.combo_files.setCurrentIndex(0)
                self.combo_files.blockSignals(False)
                self._refresh_template_path()

    def _get_memory_file(self) -> Path:
        # Pamięć druczków (zajęte sloty) ląduje GLOBALNIE w głównym folderze 'dane'
        if getattr(sys, 'frozen', False):
            base = Path(sys.executable).parent.resolve()
        else:
            base = Path(__file__).parent.parent.resolve()
        data_dir = base / 'dane'
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / 'druczek_memory.json'

    def _load_skips(self, tmpl_path):
        mem_file = self._get_memory_file()
        if mem_file.exists():
            try:
                with open(mem_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get(tmpl_path, 0)
            except: pass
        return 0

    def _save_skips(self, tmpl_path, count):
        mem_file = self._get_memory_file()
        data = {}
        if mem_file.exists():
            try:
                with open(mem_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except: pass
        data[tmpl_path] = count
        try:
            with open(mem_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except: pass

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        hdr = QHBoxLayout()
        title = QLabel('🖨️ Inteligentne Wypełnianie Poczty Polskiej')
        title.setStyleSheet('font-size:16px; font-weight:700;')
        hdr.addWidget(title)
        hdr.addStretch()
        
        btn_settings = QPushButton('⚙️ Edytor Pozycji i Czcionek')
        btn_settings.setStyleSheet("background-color: #2b5797; color: white; font-weight: bold; padding: 6px 15px;")
        btn_settings.clicked.connect(self._open_settings)
        hdr.addWidget(btn_settings)
        layout.addLayout(hdr)
        
        tmpl_box = QGroupBox('Dokument bazowy (Pusty PDF od Poczty)')
        tmpl_layout = QVBoxLayout(tmpl_box)
        
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(self.config.get('druczek_auto_dir', ''))
        self.dir_edit.setPlaceholderText('Ścieżka do folderu z plikami PDF...')
        
        btn_browse_dir = QPushButton('Wybierz Folder')
        btn_browse_dir.clicked.connect(self._browse_directory)
        
        dir_row.addWidget(self.dir_edit)
        dir_row.addWidget(btn_browse_dir)
        tmpl_layout.addLayout(dir_row)
        
        file_row = QHBoxLayout()
        self.combo_files = QComboBox()
        self.combo_files.currentIndexChanged.connect(self._on_file_selected)
        
        btn_reload_dir = QPushButton('Odśwież Folder')
        btn_reload_dir.clicked.connect(self._scan_directory)
        
        btn_single_file = QPushButton('Wczytaj POJEDYNCZY Plik')
        btn_single_file.clicked.connect(self._browse_single_file)
        
        file_row.addWidget(self.combo_files, 1)
        file_row.addWidget(btn_reload_dir)
        file_row.addWidget(btn_single_file)
        tmpl_layout.addLayout(file_row)

        info_match = QLabel("✨ <b>Inteligentne Dopasowanie:</b> Program sam czyta kody (00) z pliku PDF i dopasowuje je do konkretnych osób na liście poniżej!")
        info_match.setStyleSheet("color: #2b5797;")
        tmpl_layout.addWidget(info_match)
        
        skip_layout = QHBoxLayout()
        skip_lbl = QLabel("🛑 Zajęte miejsca (Program sam je przeskoczy):")
        skip_lbl.setStyleSheet("font-weight: bold;")
        skip_layout.addWidget(skip_lbl)
        
        self.spin_skip_slots = QSpinBox()
        self.spin_skip_slots.setRange(0, 500)
        self.spin_skip_slots.setFixedWidth(80)
        self.spin_skip_slots.valueChanged.connect(self._on_spin_changed)
        skip_layout.addWidget(self.spin_skip_slots)
        
        help_lbl = QLabel("(Działa gdy osoby nie mają kodu kreskowego C5)")
        help_lbl.setStyleSheet("color:#aaa; font-size:11px;")
        skip_layout.addWidget(help_lbl)
        skip_layout.addStretch()
        
        tmpl_layout.addLayout(skip_layout)
        
        self.tmpl_edit = QLabel('Brak załadowanego pliku.')
        self.tmpl_edit.setStyleSheet('color:#aaa; font-size:11px;')
        tmpl_layout.addWidget(self.tmpl_edit)
        layout.addWidget(tmpl_box)
        
        filter_layout = QHBoxLayout()
        self.chk_hide_printed = QCheckBox("Ukryj osoby już ZIELONE (wydrukowane)")
        self.chk_hide_printed.setChecked(True)
        self.chk_hide_printed.stateChanged.connect(self._load_c5_shipments)
        filter_layout.addWidget(self.chk_hide_printed)
        self.chk_show_only_printed = QCheckBox("Pokaż tylko wygenerowane/wydrukowane")
        self.chk_show_only_printed.stateChanged.connect(self._load_c5_shipments)
        filter_layout.addWidget(self.chk_show_only_printed)
        filter_layout.addStretch()
        
        self.btn_select_all = QPushButton('☑️ Zaznacz wszystkie widoczne')
        filter_layout.addWidget(self.btn_select_all)
        layout.addLayout(filter_layout)
        
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Wydruk', 'Data', 'Kod Kreskowy C5', 'Adresat', 'Ulica/Miejscowość'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        QShortcut(QKeySequence("Delete"), self.table).activated.connect(self._delete_selected_shipments)
        
        layout.addWidget(self.table)
        self.generated_list = QListWidget()
        self.generated_list.setMaximumHeight(110)
        layout.addWidget(self.generated_list)
        self.btn_select_all.clicked.connect(self.table.selectAll)
        
        btn_row = QHBoxLayout()
        self.btn_mark_printed = QPushButton('✅ Oznacz jako WYDRUKOWANE')
        self.btn_mark_printed.clicked.connect(self._mark_printed_status)
        btn_row.addWidget(self.btn_mark_printed)
        
        self.btn_reset_status = QPushButton('⭕ Odznacz "Wydrukowano"')
        self.btn_reset_status.clicked.connect(self._reset_print_status)
        btn_row.addWidget(self.btn_reset_status)
        
        self.btn_delete_shipment = QPushButton('🗑️ Usuń z bazy (Delete)')
        self.btn_delete_shipment.setObjectName('btn_danger')
        self.btn_delete_shipment.clicked.connect(self._delete_selected_shipments)
        btn_row.addWidget(self.btn_delete_shipment)
        
        btn_row.addStretch()
        
        self.lbl_selected = QLabel('Wybrano: 0')
        self.lbl_selected.setStyleSheet('color:#aaa; font-weight:bold;')
        btn_row.addWidget(self.lbl_selected)
        
        self.btn_fill = QPushButton('🖨️ Generuj dla zaznaczonych')
        self.btn_fill.setObjectName('btn_accent')
        self.btn_fill.clicked.connect(self._fill_druczek)
        btn_row.addWidget(self.btn_fill)
        
        self.btn_fill_all = QPushButton('🚀 Generuj WSZYSTKIE')
        self.btn_fill_all.setStyleSheet("background-color: #3b3b98; color: white; font-weight: bold;")
        self.btn_fill_all.clicked.connect(self._fill_all_druczek)
        btn_row.addWidget(self.btn_fill_all)
        
        layout.addLayout(btn_row)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self._scan_directory()

    def set_project(self, project: dict): 
        self.active_project_path = project.get('path')
        self._load_c5_shipments()
        self._refresh_template_path()

    def _get_shipments_filepath(self) -> Path | None:
        # LISTA ADRESÓW (HISTORIA WYSYŁEK) JEST PROJEKTOWA:
        return Path(self.active_project_path) / 'przesylki' / 'shipments.json' if self.active_project_path else None

    def _browse_single_file(self):
        start_dir = self.config.get('druczek_template_path', '')
        if start_dir and Path(start_dir).is_file():
            start_dir = str(Path(start_dir).parent)
            
        path, _ = QFileDialog.getOpenFileName(self, 'Wybierz plik PDF', start_dir, 'Plik PDF (*.pdf)')
        if path: 
            self.config['druczek_template_path'] = path
            self.combo_files.blockSignals(True)
            self.combo_files.clear()
            self.combo_files.addItem(f"[Pojedynczy] {Path(path).name}", path)
            self.combo_files.setCurrentIndex(0)
            self.combo_files.blockSignals(False)
            self._refresh_template_path()

    def _browse_directory(self):
        start_dir = self.dir_edit.text()
        folder = QFileDialog.getExistingDirectory(self, 'Wybierz folder', start_dir)
        if folder: 
            self.dir_edit.setText(folder)
            self.config['druczek_auto_dir'] = folder
            self._scan_directory()

    def _scan_directory(self):
        d = self.dir_edit.text()
        self.combo_files.blockSignals(True)
        self.combo_files.clear()
        self.combo_files.addItem("— Wybierz plik z folderu —", "")
        if d and Path(d).exists():
            for f in Path(d).glob('*.pdf'): 
                self.combo_files.addItem(f.name, str(f))
        self.combo_files.blockSignals(False)
        self._refresh_template_path()

    def _on_file_selected(self):
        idx = self.combo_files.currentIndex()
        self.config['druczek_template_path'] = self.combo_files.itemData(idx) if idx > 0 else ''
        self._refresh_template_path()

    def _refresh_template_path(self):
        tmpl = self.config.get('druczek_template_path', '')
        if tmpl and Path(tmpl).exists():
            from utils.pdf_utils import get_druczek_capacity
            cap = get_druczek_capacity(tmpl, self.config.get('druczek_profile', {}).get('cols', 2), self.config.get('druczek_profile', {}).get('rows', 2))
            
            saved_val = self._load_skips(tmpl)
            self.spin_skip_slots.blockSignals(True)
            self.spin_skip_slots.setValue(saved_val)
            self.spin_skip_slots.blockSignals(False)
            
            free_slots = max(0, cap - self.spin_skip_slots.value())
            self.tmpl_edit.setText(f"Aktywny plik: {Path(tmpl).name} | Faktycznych miejsc w PDF: {cap}")
            self.tmpl_edit.setStyleSheet('color:#88cc88; font-weight: bold;' if free_slots > 0 else 'color:#ff6b6b; font-weight: bold;')
        else: 
            self.tmpl_edit.setText('Brak pliku PDF.')
            self.tmpl_edit.setStyleSheet('color:#cc8888;')
        
        self._on_selection_changed()

    def _on_spin_changed(self):
        tmpl = self.config.get('druczek_template_path', '')
        if tmpl:
            self._save_skips(tmpl, self.spin_skip_slots.value())
        self._on_selection_changed()

    def _open_settings(self):
        tmpl = self.config.get('druczek_template_path', '')
        if not tmpl or not Path(tmpl).exists(): 
            return QMessageBox.warning(self, "Błąd", "Wczytaj wpierw PDF z folderu lub dysku, by użyć edytora.")
            
        dialog = DruczekSettingsDialog(self, self.config, str(tmpl))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config['druczek_profile'] = dialog.get_profile()
            if not save_global_druczek_profile(self.config['druczek_profile']):
                QMessageBox.warning(
                    self,
                    "Nie zapisano profilu",
                    "Nie udało się zapisać ustawień w dane/druczek_profile.json.",
                )
            self._refresh_template_path()

    def _load_c5_shipments(self):
        self.shipments_c5.clear()
        self.table.setRowCount(0)
        if hasattr(self, 'generated_list'):
            self.generated_list.clear()
        filepath = self._get_shipments_filepath()
        if not filepath or not filepath.exists(): return
        
        with open(filepath, 'r', encoding='utf-8') as f: 
            all_shipments = json.load(f)
            
        hide_printed = self.chk_hide_printed.isChecked()
        for s in all_shipments:
            if s.get('envelope_type', s.get('env_type', '')) == 'C5':
                is_printed = s.get('printed_on_druczek', False)
                if hide_printed and is_printed: 
                    continue
                if hasattr(self, 'chk_show_only_printed') and self.chk_show_only_printed.isChecked() and not is_printed:
                    continue
                self.shipments_c5.append(s)
                if hasattr(self, 'generated_list') and is_printed:
                    self.generated_list.addItem(f"{s.get('addressee','')} | {s.get('stamp_barcode','')}")
                
        for s in self.shipments_c5:
            row = self.table.rowCount()
            self.table.insertRow(row)
            p = s.get('printed_on_druczek', False)
            st = QTableWidgetItem("✅ TAK" if p else "⭕ NIE")
            st.setForeground(QColor('#1dd1a1') if p else QColor('#ff6b6b'))
            bc = s.get('stamp_barcode', '')
            self.table.setItem(row, 0, st)
            self.table.setItem(row, 1, QTableWidgetItem(s.get('date', '')))
            self.table.setItem(row, 2, QTableWidgetItem(bc if bc else "Brak"))
            self.table.setItem(row, 3, QTableWidgetItem(s.get('addressee', '')))
            self.table.setItem(row, 4, QTableWidgetItem(f"{s.get('addressee_street', '')}, {s.get('addressee_city', '')}"))
            
        self._on_selection_changed()

    def _on_selection_changed(self):
        selected = len(self.table.selectionModel().selectedRows())
        from utils.pdf_utils import get_druczek_capacity
        cap = get_druczek_capacity(self.config.get('druczek_template_path', ''), self.config.get('druczek_profile', {}).get('cols', 2), self.config.get('druczek_profile', {}).get('rows', 2))
        free_slots = max(0, cap - self.spin_skip_slots.value())
        
        if selected > free_slots:
            self.lbl_selected.setText(f"Wybrano: {selected} (Masz miejsce na max: {cap})")
            self.lbl_selected.setStyleSheet('color:#ff6b6b; font-weight:bold;')
        else:
            self.lbl_selected.setText(f"Wybrano: {selected}")
            self.lbl_selected.setStyleSheet('color:#1dd1a1; font-weight:bold;')

    def _reset_print_status(self): self._change_print_status(False)
    def _mark_printed_status(self): self._change_print_status(True)
        
    def _change_print_status(self, state: bool):
        sel = self.table.selectionModel().selectedRows()
        if not sel: return
        filepath = self._get_shipments_filepath()
        with open(filepath, 'r', encoding='utf-8') as f: 
            all_shipments = json.load(f)
            
        for idx in sel:
            d = self.shipments_c5[idx.row()]
            for glob_s in all_shipments:
                if (glob_s.get('date') == d.get('date') and 
                    glob_s.get('addressee') == d.get('addressee') and
                    glob_s.get('addressee_street') == d.get('addressee_street') and
                    glob_s.get('addressee_city') == d.get('addressee_city')): 
                    glob_s['printed_on_druczek'] = state
                    
        with open(filepath, 'w', encoding='utf-8') as f: 
            json.dump(all_shipments, f, ensure_ascii=False, indent=4)
        self._load_c5_shipments()

    def _delete_selected_shipments(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel: return QMessageBox.warning(self, "Brak", "Wybierz przesyłki do usunięcia z listy druczków.")
        
        if QMessageBox.question(self, "Usuń", "Czy na pewno trwale usunąć zaznaczone przesyłki z bazy danych?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            filepath = self._get_shipments_filepath()
            try:
                with open(filepath, 'r', encoding='utf-8') as f: 
                    all_shipments = json.load(f)
                
                items_to_remove = [self.shipments_c5[idx.row()] for idx in sel]
                
                new_all_shipments = []
                for s in all_shipments:
                    is_deleted = any(
                        d.get('date') == s.get('date') and 
                        d.get('addressee') == s.get('addressee') and
                        d.get('addressee_street') == s.get('addressee_street') and
                        d.get('addressee_city') == s.get('addressee_city')
                        for d in items_to_remove
                    )
                    if not is_deleted:
                        new_all_shipments.append(s)
                        
                with open(filepath, 'w', encoding='utf-8') as f: 
                    json.dump(new_all_shipments, f, ensure_ascii=False, indent=4)
                    
                self._load_c5_shipments()
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie można usunąć: {e}")

    def _fill_all_druczek(self): 
        self.table.selectAll()
        self._fill_druczek()

    def _fill_druczek(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel: return QMessageBox.warning(self, "Brak", "Zaznacz przesyłki do nałożenia z listy poniżej.")
            
        tmpl_path = self.config.get('druczek_template_path', '')
        if not tmpl_path or not Path(tmpl_path).exists(): 
            return QMessageBox.warning(self, "Brak", "Wybierz plik PDF z druczkami (np. pobrany od Poczty).")
            
        used_slots = self.spin_skip_slots.value()
        from utils.pdf_utils import get_druczek_capacity, fill_neoznacze_pdf
        cap = get_druczek_capacity(tmpl_path, self.config.get('druczek_profile', {}).get('cols', 2), self.config.get('druczek_profile', {}).get('rows', 2))
        free_slots = max(0, cap - used_slots)
        
        if len(sel) > free_slots: 
            return QMessageBox.critical(self, "Błąd", f"Zaznaczyłeś {len(sel)} osób, ale w pliku PDF jest wolnych tylko {free_slots} miejsc!\nZmniejsz ilość osób, lub wczytaj nową stronę PDF.")
            
        real_shipments = [self.shipments_c5[i.row()] for i in sorted(sel)]
        padded_shipments = [{}] * used_slots + real_shipments
        
        default_name = f"Wydruk_{Path(tmpl_path).name}"
        out_path, _ = QFileDialog.getSaveFileName(self, 'Zapisz gotowy PDF do druku jako:', default_name, 'PDF (*.pdf)')
        if not out_path: return
        
        sender_data = self.config.get('sender', {'name': '', 'street': '', 'city': ''})
        temp_out_file = str(out_path) + ".tmp.pdf"
        
        success, count = fill_neoznacze_pdf(tmpl_path, temp_out_file, padded_shipments, sender_data, self.config.get('druczek_profile', {}))
        
        if success:
            if os.path.exists(out_path):
                os.remove(out_path)
            shutil.move(temp_out_file, out_path)
            
            new_used_count = used_slots + len(real_shipments)
            self._save_skips(tmpl_path, new_used_count)
            self.spin_skip_slots.setValue(new_used_count)
            
            actual_saved = 0
            filepath = self._get_shipments_filepath()
            with open(filepath, 'r', encoding='utf-8') as f: 
                all_shipments = json.load(f)
                
            for s_to_mark in real_shipments:
                for glob_s in all_shipments:
                    if (glob_s.get('date') == s_to_mark.get('date') and 
                        glob_s.get('addressee') == s_to_mark.get('addressee') and
                        glob_s.get('addressee_street') == s_to_mark.get('addressee_street') and
                        glob_s.get('addressee_city') == s_to_mark.get('addressee_city')):
                        glob_s['printed_on_druczek'] = True
                        actual_saved += 1
                        break
                        
            with open(filepath, 'w', encoding='utf-8') as f: 
                json.dump(all_shipments, f, ensure_ascii=False, indent=4)
                
            self._load_c5_shipments() 
            self._refresh_template_path()
            QMessageBox.information(self, "Sukces", f"Zrobione! Nałożono {actual_saved} adresów na dokument.\n\nKażdy adres został przypisany pod konkretny kod kreskowy przesyłki!")
        else: 
            if os.path.exists(temp_out_file):
                os.remove(temp_out_file)
            QMessageBox.critical(self, "Błąd", "Wystąpił błąd zapisu do pliku PDF.")