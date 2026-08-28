"""
print_manager.py – Zakładka Menedżera Drukowania
"""
import os
import time
import contextlib
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QAbstractItemView, QCheckBox, QGroupBox, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence

try:
    import win32print
    import win32con
    WIN32PRINT_AVAILABLE = True
except ImportError:
    WIN32PRINT_AVAILABLE = False


class PrintManagerWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.files_to_print = []
        self.all_found_files = [] 
        self.owners = []
        self.active_project_path = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        hdr = QLabel('🖨️ Menedżer Drukowania')
        hdr.setStyleSheet('font-size:16px; font-weight:700;')
        main_layout.addWidget(hdr)

        # Górny pasek opcji ładowania
        top_row = QHBoxLayout()
        self.btn_load_folder = QPushButton('📂 Wybierz folder (bez podfolderów)')
        self.btn_load_folder.clicked.connect(self._load_folder)
        top_row.addWidget(self.btn_load_folder)
        
        self.btn_load_folder_rec = QPushButton('📂 Wybierz folder i podfoldery')
        self.btn_load_folder_rec.clicked.connect(self._load_folder_recursive)
        top_row.addWidget(self.btn_load_folder_rec)
        
        self.btn_load_project = QPushButton('📂 Załaduj z aktualnego projektu')
        self.btn_load_project.clicked.connect(self._load_from_project)
        top_row.addWidget(self.btn_load_project)
        
        top_row.addStretch()
        main_layout.addLayout(top_row)
        
        # Opcje filtrowania drzewa
        filter_row = QHBoxLayout()
        self.chk_show_envelopes = QCheckBox('Pokaż koperty')
        self.chk_show_envelopes.stateChanged.connect(self._refresh_tree)
        filter_row.addWidget(self.chk_show_envelopes)
        
        self.chk_show_other = QCheckBox('Pokaż Inne dokumenty')
        self.chk_show_other.stateChanged.connect(self._refresh_tree)
        filter_row.addWidget(self.chk_show_other)
        filter_row.addStretch()
        main_layout.addLayout(filter_row)
        
        # Drzewo plików
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Właściciel / Dokument"])
        self.tree_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
        # Podpięcie klawisza Delete do usuwania z listy
        QShortcut(QKeySequence("Delete"), self.tree_widget).activated.connect(self._delete_selected_items)
        
        main_layout.addWidget(self.tree_widget)

        # ── Sekcja przycisków akcji ──
        actions_box = QGroupBox("Działania Drukowania / PDF")
        actions_layout = QVBoxLayout(actions_box)

        # Wiersz: Tryb WORD
        row_word = QHBoxLayout()
        self.btn_print_word_sel = QPushButton('🖨️ Drukuj zaznaczone (WORD)')
        self.btn_print_word_sel.setObjectName('btn_primary')
        self.btn_print_word_sel.clicked.connect(lambda: self._print_selected(mode="word"))
        row_word.addWidget(self.btn_print_word_sel)

        self.btn_print_word_all = QPushButton('🖨️ Drukuj wszystkie widoczne (WORD)')
        self.btn_print_word_all.setObjectName('btn_primary')
        self.btn_print_word_all.clicked.connect(lambda: self._print_all(mode="word"))
        row_word.addWidget(self.btn_print_word_all)
        row_word.addStretch()
        actions_layout.addLayout(row_word)

        # Wiersz: Tryb PDF
        row_pdf = QHBoxLayout()
        self.btn_print_pdf_sel = QPushButton('📄 Konwertuj na PDF i drukuj zaznaczone')
        self.btn_print_pdf_sel.setObjectName('btn_accent')
        self.btn_print_pdf_sel.clicked.connect(lambda: self._print_selected(mode="pdf"))
        row_pdf.addWidget(self.btn_print_pdf_sel)

        self.btn_print_pdf_all = QPushButton('📄 Konwertuj na PDF i drukuj wszystkie')
        self.btn_print_pdf_all.setObjectName('btn_accent')
        self.btn_print_pdf_all.clicked.connect(lambda: self._print_all(mode="pdf"))
        row_pdf.addWidget(self.btn_print_pdf_all)

        self.chk_only_generate_pdf = QCheckBox('Tylko generuj pliki PDF (nie drukuj)')
        row_pdf.addWidget(self.chk_only_generate_pdf)
        
        row_pdf.addStretch()
        actions_layout.addLayout(row_pdf)

        main_layout.addWidget(actions_box)
        
        # Ustawienia Parametrów Drukarki
        settings_box = QGroupBox("⚙️ Parametry Wydruku (Domyślna drukarka systemowa)")
        settings_layout = QHBoxLayout(settings_box)
        
        self.chk_force_bw = QCheckBox("Wymuś Czarno-Biały wydruk")
        settings_layout.addWidget(self.chk_force_bw)
        
        settings_layout.addWidget(QLabel(" | Drukarka WORD:"))
        self.combo_printer_word = QComboBox()
        self.combo_printer_word.setMinimumWidth(220)
        self._populate_word_printers()
        settings_layout.addWidget(self.combo_printer_word)

        settings_layout.addWidget(QLabel(" |  Duplex (Dwustronnie):"))
        self.combo_duplex = QComboBox()
        self.combo_duplex.addItems([
            "Domyślne ustawienie drukarki", 
            "Jednostronnie", 
            "Dwustronnie (Długa krawędź)", 
            "Dwustronnie (Krótka krawędź)"
        ])
        settings_layout.addWidget(self.combo_duplex)
        
        settings_layout.addStretch()
        
        self.btn_print_options_win = QPushButton('⚙️ Ustawienia Windows')
        self.btn_print_options_win.clicked.connect(self._open_print_settings_win)
        settings_layout.addWidget(self.btn_print_options_win)
        
        main_layout.addWidget(settings_box)

    def _populate_word_printers(self):
        self.combo_printer_word.clear()
        try:
            if WIN32PRINT_AVAILABLE:
                default = win32print.GetDefaultPrinter()
                printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
                for name in printers:
                    self.combo_printer_word.addItem(name)
                idx = self.combo_printer_word.findText(default)
                if idx >= 0: self.combo_printer_word.setCurrentIndex(idx)
            else:
                self.combo_printer_word.addItem('Domyślna drukarka systemowa')
        except Exception:
            self.combo_printer_word.addItem('Domyślna drukarka systemowa')

    def _selected_word_printer(self):
        if hasattr(self, 'combo_printer_word'):
            txt = self.combo_printer_word.currentText().strip()
            if txt and txt != 'Domyślna drukarka systemowa':
                return txt
        return ''

    @contextlib.contextmanager
    def _apply_printer_settings(self):
        """Modyfikuje ustawienia domyślnej drukarki na czas drukowania, a potem je przywraca."""
        if not WIN32PRINT_AVAILABLE:
            yield
            return

        force_bw = self.chk_force_bw.isChecked()
        duplex_idx = self.combo_duplex.currentIndex()

        # Jeśli nie wybrano zmian, po prostu wykonaj druk
        if not force_bw and duplex_idx == 0:
            yield
            return

        printer_name = win32print.GetDefaultPrinter()
        PRINTER_DEFAULTS = {"DesiredAccess": win32print.PRINTER_ALL_ACCESS}
        
        hPrinter = None
        pDevMode = None
        orig_color = None
        orig_duplex = None
        changed = False

        try:
            hPrinter = win32print.OpenPrinter(printer_name, PRINTER_DEFAULTS)
            # Pobranie obecnych właściwości drukarki (Poziom 2 = DEVMODE)
            properties = win32print.GetPrinter(hPrinter, 2)
            pDevMode = properties["pDevMode"]
            
            # Zapisz oryginalne wartości, aby móc je przywrócić
            orig_color = pDevMode.Color
            orig_duplex = pDevMode.Duplex

            # 1 = Monochrome (Czarno-Biały), 2 = Color
            if force_bw:
                pDevMode.Color = 1 
            
            # 1 = Simplex, 2 = Duplex Vertical (Długa krawędź), 3 = Duplex Horizontal (Krótka krawędź)
            if duplex_idx == 1:
                pDevMode.Duplex = 1
            elif duplex_idx == 2:
                pDevMode.Duplex = 2
            elif duplex_idx == 3:
                pDevMode.Duplex = 3

            # Zapisz nowe właściwości do drukarki
            properties["pDevMode"] = pDevMode
            win32print.SetPrinter(hPrinter, 2, properties, 0)
            changed = True

        except Exception as e:
            print(f"Nie udało się zmienić ustawień drukarki (brak uprawnień?): {e}")
        
        try:
            # Oddajemy sterowanie do funkcji drukującej
            yield
        finally:
            # Przywrócenie oryginalnych ustawień po zakończeniu drukowania
            if changed and hPrinter and pDevMode:
                try:
                    pDevMode.Color = orig_color
                    pDevMode.Duplex = orig_duplex
                    properties["pDevMode"] = pDevMode
                    win32print.SetPrinter(hPrinter, 2, properties, 0)
                except Exception as e:
                    print(f"Nie udało się przywrócić ustawień drukarki: {e}")
            if hPrinter:
                win32print.ClosePrinter(hPrinter)

    def set_project(self, project: dict):
        self.active_project_path = project.get('path')

    def set_owners(self, owners: list):
        self.owners = owners

    def _get_short_name(self, owner: dict) -> str:
        fn = owner.get('first_name', '').strip()
        ln = owner.get('last_name', '').strip()
        if owner.get('is_couple') or ' i ' in fn.lower():
            names = [n[0].upper() for n in fn.replace(' i ', ' ').split() if n.lower() != 'i']
            return f"{'.'.join(names)}.{ln}"
        else:
            return f"{fn[0].upper() if fn else ''}.{ln}"

    def _get_owner_name_for_file(self, filename: str) -> str:
        fname = filename.lower()
        
        if 'zbiorcze' in fname and 'kopert' in fname:
            return "Koperty Zbiorcze"
        
        for o in self.owners:
            short_name = self._get_short_name(o).lower()
            if short_name in fname:
                return f"{o.get('last_name', '')} {o.get('first_name', '')}".strip()
                
        best_match = "Inne dokumenty"
        best_len = 0
        for o in self.owners:
            name_parts = [p.lower() for p in o.get('last_name', '').split()] + [p.lower() for p in o.get('first_name', '').split() if p.lower() != 'i']
            matches = sum(1 for p in name_parts if p and p in fname)
            if matches > 0 and matches > best_len:
                best_len = matches
                best_match = f"{o.get('last_name', '')} {o.get('first_name', '')}".strip()
                if not best_match:
                    best_match = o.get('full_name', 'Nieznany')
                    
        return best_match

    def _load_from_project(self):
        if not self.active_project_path:
            QMessageBox.warning(self, 'Brak projektu', 'Brak aktywnego projektu.')
            return
        self._load_files_from_dir(Path(self.active_project_path), recursive=True)

    def _load_folder(self):
        last_path = self.config.get('last_print_dir', '')
        folder = QFileDialog.getExistingDirectory(self, 'Wybierz folder (bez podfolderów)', last_path)
        if not folder: return
        self.config['last_print_dir'] = folder
        self._load_files_from_dir(Path(folder), recursive=False)

    def _load_folder_recursive(self):
        last_path = self.config.get('last_print_dir', '')
        folder = QFileDialog.getExistingDirectory(self, 'Wybierz folder (i podfoldery)', last_path)
        if not folder: return
        self.config['last_print_dir'] = folder
        self._load_files_from_dir(Path(folder), recursive=True)

    def _load_files_from_dir(self, folder_path: Path, recursive: bool = True):
        if recursive:
            files = list(folder_path.rglob('*.docx')) + list(folder_path.rglob('*.pdf'))
        else:
            files = list(folder_path.glob('*.docx')) + list(folder_path.glob('*.pdf'))
            
        self.all_found_files = [f for f in files if not f.name.startswith('~$')]
        
        self._refresh_tree()
        QMessageBox.information(self, 'Wczytano', f'Wczytano {len(self.all_found_files)} plików.')

    def _refresh_tree(self):
        self.tree_widget.clear()
        if not self.all_found_files: return
        
        show_env = self.chk_show_envelopes.isChecked()
        show_oth = self.chk_show_other.isChecked()
        
        files = self.all_found_files
        if not show_env:
            files = [f for f in files if 'kopert' not in f.name.lower()]
        
        def sort_key(filepath):
            name = filepath.name.lower()
            if 'demontaz' in name or 'demontaż' in name: return 1
            elif 'budowa' in name: return 2
            elif 'pismo' in name: return 3
            elif 'kopert' in name: return 4
            else: return 5
                
        files.sort(key=sort_key)
        self.files_to_print = files
        
        grouped = {}
        for f in files:
            owner = self._get_owner_name_for_file(f.name)
            if owner not in grouped: grouped[owner] = []
            grouped[owner].append(f)
            
        for owner, flist in grouped.items():
            if owner == "Inne dokumenty" and not show_oth:
                continue
            if owner == "Koperty Zbiorcze" and not show_env:
                continue
                
            parent = QTreeWidgetItem(self.tree_widget, [owner])
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            for f in flist:
                item = QTreeWidgetItem(parent, [f.name])
                item.setData(0, Qt.ItemDataRole.UserRole, str(f))
                
                k = sort_key(f)
                if k == 1: item.setText(0, f"[DEMONTAŻ] {f.name}")
                elif k == 2: item.setText(0, f"[BUDOWA] {f.name}")
                elif k == 3: item.setText(0, f"[PISMO] {f.name}")
                elif k == 4: item.setText(0, f"[KOPERTA] {f.name}")
                
            parent.setExpanded(True)

    def _delete_selected_items(self):
        items = self.tree_widget.selectedItems()
        if not items: return
        
        paths_to_remove = set()
        for item in items:
            if item.childCount() == 0: 
                path = item.data(0, Qt.ItemDataRole.UserRole)
                if path: paths_to_remove.add(path)
            else: 
                for i in range(item.childCount()):
                    path = item.child(i).data(0, Qt.ItemDataRole.UserRole)
                    if path: paths_to_remove.add(path)
                    
        if not paths_to_remove: return
        
        self.all_found_files = [f for f in self.all_found_files if str(f) not in paths_to_remove]
        self._refresh_tree()

    def _open_print_settings_win(self):
        try:
            os.system('control printers')
        except Exception:
            QMessageBox.warning(self, "Błąd", "Nie udało się otworzyć ustawień drukarki.")

    def _print_files_word(self, files: list):
        # Tryb WORD drukuje bezpośrednio pliki .docx przez Word.
        # Nie konwertuje do PDF i nie wysyła PDF-ów z tej akcji.
        files = [f for f in files if str(f).lower().endswith('.docx')]
        if not files:
            QMessageBox.warning(self, 'Brak plików WORD', 'W zaznaczeniu/widoku nie ma plików .docx do bezpośredniego druku przez Word.')
            return
        
        try:
            with self._apply_printer_settings():
                import win32com.client
                # Uruchamiamy obiekt Word wewnątrz kontekstu, aby pobrał zmodyfikowane ustawienia drukarki
                word = win32com.client.DispatchEx("Word.Application")
                word.Visible = False
                word.DisplayAlerts = False
                selected_printer = self._selected_word_printer()
                if selected_printer:
                    if 'pdf' in selected_printer.lower():
                        QMessageBox.warning(self, 'Drukarka PDF', 'Wybrana drukarka WORD jest drukarką PDF. Wybierz fizyczną drukarkę, inaczej Windows pokaże okno zapisu PDF.')
                        word.Quit()
                        return
                    try:
                        word.ActivePrinter = selected_printer
                    except Exception as e:
                        QMessageBox.warning(self, 'Drukarka', f'Nie udało się ustawić drukarki WORD:\n{selected_printer}\n\n{e}')
                
                success = 0
                for f in files:
                    try:
                        doc = word.Documents.Open(os.path.abspath(f), ReadOnly=True)
                        doc.PrintOut(Background=False)
                        doc.Close(SaveChanges=False)
                        success += 1
                    except Exception as e:
                        print(f"Błąd drukowania pliku {f}: {e}")
                        
                word.Quit()
                QMessageBox.information(self, 'Drukowanie (WORD)', f'Wysłano do drukarki {success} plików.')
        except Exception as e:
            QMessageBox.critical(self, 'Błąd', f'Nie udało się połączyć z Wordem lub wystąpił błąd: {e}')

    def _print_files_pdf(self, files: list):
        if not files: return
        
        try:
            with self._apply_printer_settings():
                import win32com.client
                word = win32com.client.DispatchEx("Word.Application")
                word.Visible = False
                word.DisplayAlerts = False
                
                success = 0
                only_generate = self.chk_only_generate_pdf.isChecked()
                
                for f in files:
                    path = Path(f)
                    try:
                        if path.suffix.lower() == '.docx':
                            pdf_dir = path.parent / 'pdf'
                            pdf_dir.mkdir(exist_ok=True)
                            pdf_path = pdf_dir / f"{path.stem}.pdf"
                            
                            doc = word.Documents.Open(os.path.abspath(f), ReadOnly=True)
                            doc.SaveAs(str(pdf_path.resolve()), 17) # 17 = wdFormatPDF
                            doc.Close(SaveChanges=False)
                            
                            if not only_generate:
                                os.startfile(str(pdf_path.resolve()), "print")
                                time.sleep(2)
                            success += 1
                        elif path.suffix.lower() == '.pdf':
                            if not only_generate:
                                os.startfile(os.path.abspath(f), "print")
                                time.sleep(2)
                            success += 1
                    except Exception as e:
                        print(f"Błąd konwersji/druku pliku {f}: {e}")
                        
                word.Quit()
                
                if only_generate:
                    QMessageBox.information(self, 'Wygenerowano PDF', f'Skutecznie utworzono {success} plików PDF w podfolderach "pdf".\nNie wysyłano ich do drukarki.')
                else:
                    QMessageBox.information(self, 'Drukowanie (PDF)', f'Wygenerowano i wysłano do drukarki {success} plików PDF.')
        except Exception as e:
            QMessageBox.critical(self, 'Błąd', f'Wystąpił błąd podczas obsługi PDF: {e}')

    def _print_selected(self, mode="word"):
        items = self.tree_widget.selectedItems()
        files = []
        for item in items:
            if item.childCount() == 0: 
                files.append(item.data(0, Qt.ItemDataRole.UserRole))
            else: 
                for i in range(item.childCount()):
                    files.append(item.child(i).data(0, Qt.ItemDataRole.UserRole))
                    
        unique_files = list(dict.fromkeys(files))
        if not unique_files:
            QMessageBox.warning(self, 'Brak', 'Zaznacz pliki w drzewie (możesz zaznaczyć całego właściciela).')
            return
            
        if mode == "word":
            self._print_files_word(unique_files)
        else:
            self._print_files_pdf(unique_files)

    def _print_all(self, mode="word"):
        if not self.files_to_print:
            QMessageBox.warning(self, 'Brak', 'Brak plików widocznych do druku.')
            return
            
        files = [str(f) for f in self.files_to_print]
        
        if mode == "word":
            self._print_files_word(files)
        else:
            self._print_files_pdf(files)