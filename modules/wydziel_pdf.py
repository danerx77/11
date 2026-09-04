"""
extract_pdf_tab.py – Zakładka do automatycznego wydzielania działek z wielostronicowych wypisów PDF.
"""
import re
from pathlib import Path
import fitz  # PyMuPDF

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QGroupBox,
    QHeaderView, QProgressBar, QTextEdit, QSplitter, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QShortcut, QKeySequence

# Używamy gotowych funkcji z utils do czytania list
from utils.output_paths import project_output_dir
from utils.pdf_utils import parse_parcel_list_file, parse_parcel_list_text


class PdfExtractorThread(QThread):
    progress = Signal(int, int)  # current, total
    log = Signal(str)
    finished = Signal(dict)      # dict z wynikami {parcel_num: boolean}

    def __init__(self, pdf_path: str, output_dir: str, parcels: list):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.parcels = parcels

    def run(self):
        try:
            self.log.emit("Otwieranie pliku PDF...")
            doc = fitz.open(self.pdf_path)
            
            extracts = []
            current_pages = []
            current_text = ""
            last_jr = None
            
            self.log.emit("Analiza stron i łączenie wielostronicowych wypisów...")
            for i in range(len(doc)):
                page = doc[i]
                text = page.get_text()
                
                is_page_1 = bool(re.search(r'(?i)strona\s+1\s+z\s+\d+', text))
                
                m_jr = re.search(r'(?i)Nr\s+jednostki\s+rejestrowej:\s*([^\n]+)', text)
                current_jr = m_jr.group(1).strip() if m_jr else None

                start_new = False
                if is_page_1 and len(current_pages) > 0:
                    start_new = True
                elif current_jr and last_jr and current_jr != last_jr and len(current_pages) > 0:
                    start_new = True

                if start_new:
                    extracts.append({'pages': current_pages, 'text': current_text})
                    current_pages = []
                    current_text = ""
                    
                current_pages.append(i)
                current_text += text + "\n"
                
                if current_jr:
                    last_jr = current_jr

            if current_pages:
                extracts.append({'pages': current_pages, 'text': current_text})

            total_extracts = len(extracts)
            self.log.emit(f"Wykryto {total_extracts} osobnych wypisów/jednostek rejestrowych w dokumencie.")
            
            results = {p: False for p in self.parcels}
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

            patterns = {}
            for p in self.parcels:
                patterns[p] = re.compile(r'(?<![\d/])' + re.escape(p) + r'(?![\d/])')

            pending_parcels = set(self.parcels)

            for idx, extract in enumerate(extracts):
                self.progress.emit(idx + 1, total_extracts)
                
                found_in_this = []
                for p in list(pending_parcels):
                    if patterns[p].search(extract['text']):
                        found_in_this.append(p)
                
                if found_in_this:
                    safe_names = [p.replace('/', '.') for p in found_in_this]
                    
                    if len(safe_names) > 5:
                        combined_name = " ".join(safe_names[:5]) + f" i {len(safe_names)-5} inne.pdf"
                    else:
                        combined_name = " ".join(safe_names) + ".pdf"
                        
                    out_path = Path(self.output_dir) / combined_name
                    
                    new_doc = fitz.open()
                    for p_num in extract['pages']:
                        new_doc.insert_pdf(doc, from_page=p_num, to_page=p_num)
                        
                    new_doc.save(out_path)
                    new_doc.close()
                    
                    for p in found_in_this:
                        results[p] = True
                        pending_parcels.remove(p)
                        
                    self.log.emit(f"Wydzielono: {combined_name} (Strony: {[p+1 for p in extract['pages']]})")
            
            doc.close()
            self.finished.emit(results)
            
        except Exception as e:
            self.log.emit(f"Błąd krytyczny: {str(e)}")
            self.finished.emit({})


class ExtractPdfWidget(QWidget):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.config = config if config is not None else {}
        self.active_project_path = ''
        
        # Słownik: { 'nr_działki': {'source': '...', 'status': 'Oczekuje', 'color': '#7f8c8d'} }
        self.target_parcels = {} 
        self.global_parcels_cache = []
        self.pdf_path = ""
        self._build_ui()

    def set_project(self, project: dict):
        """Zapamiętuje otwarty projekt, by zapisywać PDF-y w jego folderze."""
        self.active_project_path = (project or {}).get('path', '')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                ext = Path(path).suffix.lower()
                
                if ext == '.pdf':
                    self.pdf_path = path
                    self.lbl_pdf_path.setText(path)
                    if self.target_parcels:
                        self.btn_extract.setEnabled(True)
                elif ext in ['.txt', '.docx', '.xlsx', '.xls']:
                    self._load_from_file_path(path)

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ---------------- LEWA STRONA (Źródło działek) ----------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        input_group = QGroupBox("Krok 1: Lista działek (Przeciągnij tu pliki txt/docx/xlsx)")
        input_layout = QVBoxLayout(input_group)

        lbl_hint = QLabel("Wklej numery działek (jeden pod drugim) lub wczytaj z pliku:")
        lbl_hint.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        input_layout.addWidget(lbl_hint)

        self.text_manual_input = QTextEdit()
        self.text_manual_input.setPlaceholderText("np.\n123/4\n555/2\n888")
        input_layout.addWidget(self.text_manual_input)

        btn_row_input = QHBoxLayout()
        self.btn_add_manual = QPushButton("➕ Dodaj wpisane")
        self.btn_add_manual.setObjectName("btn_primary")
        self.btn_add_manual.clicked.connect(self._add_manual_parcels)
        btn_row_input.addWidget(self.btn_add_manual)

        self.btn_load_file = QPushButton("📂 Wczytaj z pliku")
        self.btn_load_file.clicked.connect(self._browse_list_file)
        btn_row_input.addWidget(self.btn_load_file)

        self.btn_pull_project = QPushButton("📋 Zaciągnij listę działek z Działki")
        self.btn_pull_project.setToolTip("Wczytuje numery działek z zakładki Lista Działek aktywnego projektu.")
        self.btn_pull_project.clicked.connect(self._pull_global_parcels_clicked)
        btn_row_input.addWidget(self.btn_pull_project)
        input_layout.addLayout(btn_row_input)

        btn_row_clear = QHBoxLayout()
        self.btn_delete_selected = QPushButton("🗑️ Usuń zaznaczone")
        self.btn_delete_selected.clicked.connect(self._delete_selected_parcels)
        btn_row_clear.addWidget(self.btn_delete_selected)
        
        self.btn_clear_list = QPushButton("🗑️ Wyczyść całą listę")
        self.btn_clear_list.clicked.connect(self._clear_manual_parcels)
        btn_row_clear.addWidget(self.btn_clear_list)
        input_layout.addLayout(btn_row_clear)

        left_layout.addWidget(input_group)
        splitter.addWidget(left_widget)

        # ---------------- PRAWA STRONA (Plik PDF i tabela) ----------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        control_group = QGroupBox("Krok 2: Wydzielanie (Przeciągnij tu plik PDF)")
        control_layout = QHBoxLayout(control_group)

        self.btn_load_pdf = QPushButton("📄 Wybierz PDF")
        self.btn_load_pdf.setMinimumHeight(40)
        self.btn_load_pdf.clicked.connect(self._browse_pdf)
        
        self.lbl_pdf_path = QLineEdit()
        self.lbl_pdf_path.setReadOnly(True)
        self.lbl_pdf_path.setPlaceholderText("Brak wczytanego pliku PDF...")

        self.btn_extract = QPushButton("✂️ WYDZIEL DZIAŁKI")
        self.btn_extract.setMinimumHeight(40)
        self.btn_extract.setObjectName("btn_primary")
        self.btn_extract.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 0 20px;")
        self.btn_extract.setEnabled(False)
        self.btn_extract.clicked.connect(self._start_extraction)

        control_layout.addWidget(self.btn_load_pdf)
        control_layout.addWidget(self.lbl_pdf_path, stretch=1)
        control_layout.addWidget(self.btn_extract)
        right_layout.addWidget(control_group)

        # Tabela wynikowa
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Numer Działki', 'Źródło', 'Wydzielono (Status)'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        
        # Skrót klawiszowy DELETE do usuwania z tabeli
        QShortcut(QKeySequence("Delete"), self.table).activated.connect(self._delete_selected_parcels)
        
        right_layout.addWidget(self.table)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        right_layout.addWidget(self.progress_bar)
        
        self.log_label = QLabel("Gotowy.")
        self.log_label.setStyleSheet("color: #7f8c8d;")
        right_layout.addWidget(self.log_label)

        splitter.addWidget(right_widget)
        splitter.setSizes([350, 750])

    def set_global_parcels(self, parcels: list):
        """Metoda zasilana automatycznie z głównej Listy Działek projektu."""
        self.global_parcels_cache = [p['number'] for p in parcels if isinstance(p, dict) and p.get('number')]
        self._sync_target_parcels()

    def _pull_global_parcels_clicked(self):
        before = len(self.target_parcels)
        self._sync_target_parcels()
        added = max(0, len(self.target_parcels) - before)
        QMessageBox.information(self, 'Zaciągnięto działki', f'Lista z zakładki Działki została zaciągnięta. Dodano nowych: {added}.')

    def _sync_target_parcels(self):
        keys_to_remove = [k for k, v in self.target_parcels.items() if v['source'] == 'Globalna Lista Projektu']
        for k in keys_to_remove:
            del self.target_parcels[k]
            
        for p_num in self.global_parcels_cache:
            if p_num not in self.target_parcels:
                self.target_parcels[p_num] = {'source': 'Globalna Lista Projektu', 'status': 'Oczekuje', 'color': '#7f8c8d'}
                
        self._refresh_table()

    def _add_manual_parcels(self):
        text = self.text_manual_input.toPlainText()
        if not text.strip(): return
        
        result = parse_parcel_list_text(text)
        all_nums = result['demolition'] + result['construction'] + result['connection'] + result['full']
        
        added = 0
        for num in set(all_nums):
            if num not in self.target_parcels:
                self.target_parcels[num] = {'source': 'Wprowadzono ręcznie', 'status': 'Oczekuje', 'color': '#7f8c8d'}
                added += 1
                
        self.text_manual_input.clear()
        self._refresh_table()
        if added > 0:
            QMessageBox.information(self, "Dodano", f"Dodano {added} nowych działek z ręcznego wpisu.")

    def _browse_list_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Wybierz listę działek', '', 'Pliki tekstowe (*.txt *.docx *.xlsx *.xls)')
        if path:
            self._load_from_file_path(path)
            
    def _load_from_file_path(self, path: str):
        try:
            result = parse_parcel_list_file(path)
            all_nums = result['demolition'] + result['construction'] + result['connection'] + result['full']
            
            added = 0
            for num in set(all_nums):
                if num not in self.target_parcels:
                    self.target_parcels[num] = {'source': f'Z pliku ({Path(path).name})', 'status': 'Oczekuje', 'color': '#7f8c8d'}
                    added += 1
            
            self._refresh_table()
            if added > 0:
                QMessageBox.information(self, "Dodano", f"Dodano {added} działek z wczytanego pliku.")
        except Exception as e:
            QMessageBox.critical(self, 'Błąd', f'Nie udało się wczytać pliku:\n{e}')

    def _delete_selected_parcels(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
            
        rows = sorted(set(item.row() for item in selected_items), reverse=True)
        for row in rows:
            parcel_item = self.table.item(row, 0)
            if parcel_item:
                parcel_num = parcel_item.text()
                if parcel_num in self.target_parcels:
                    del self.target_parcels[parcel_num]
                    
        self._refresh_table()

    def _clear_manual_parcels(self):
        # Usuwa wszystkie, ale pyta o potwierdzenie
        if QMessageBox.question(self, 'Wyczyść', 'Czy na pewno chcesz usunąć WSZYSTKIE działki z tej zakładki?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.target_parcels.clear()
            self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for parcel, data in sorted(self.target_parcels.items()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            it_parcel = QTableWidgetItem(parcel)
            it_parcel.setFont(QFont('', -1, QFont.Weight.Bold))
            self.table.setItem(row, 0, it_parcel)
            
            source = data['source']
            it_source = QTableWidgetItem(source)
            if source == 'Globalna Lista Projektu':
                it_source.setForeground(QColor("#2980b9"))
            else:
                it_source.setForeground(QColor("#8e44ad"))
            self.table.setItem(row, 1, it_source)
            
            it_status = QTableWidgetItem(data['status'])
            it_status.setForeground(QColor(data['color']))
            if data['status'] == "TAK":
                it_status.setFont(QFont('', -1, QFont.Weight.Bold))
            it_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, it_status)
            
        if self.target_parcels and self.pdf_path:
            self.btn_extract.setEnabled(True)
        else:
            self.btn_extract.setEnabled(False)

    def _browse_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Wybierz wielostronicowy PDF z wypisami', '', 'Pliki PDF (*.pdf)')
        if path:
            self.pdf_path = path
            self.lbl_pdf_path.setText(path)
            if self.target_parcels:
                self.btn_extract.setEnabled(True)
                
    def _update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _start_extraction(self):
        if not self.pdf_path or not self.target_parcels:
            return
            
        # 1. Filtrowanie - wybieramy TYLKO te działki, które NIE MAJĄ jeszcze statusu "TAK"
        parcels_to_process = []
        for p, data in self.target_parcels.items():
            if data['status'] != "TAK":
                # Zmieniamy ich status tylko jeśli nie zostały jeszcze znalezione
                self.target_parcels[p]['status'] = "Oczekuje..."
                self.target_parcels[p]['color'] = "#7f8c8d"
                parcels_to_process.append(p)
                
        # Jeśli lista jest pusta, to znaczy że wszystko już wyciągnięto
        if not parcels_to_process:
            QMessageBox.information(self, "Informacja", "Wszystkie działki widoczne na liście zostały już poprawnie wydzielone (mają status TAK).\n\nAby ponowić, usuń je z listy i dodaj ponownie.")
            return
            
        auto_dir = project_output_dir(
            self.config, 'split_pdf', self.active_project_path
        )
        if auto_dir is not None:
            output_dir = str(auto_dir)
        else:
            output_dir = QFileDialog.getExistingDirectory(self, "Wybierz folder do zapisu WYDZIELONYCH plików PDF")
        if not output_dir:
            return
            
        self.btn_extract.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
            
        self._refresh_table()
        
        # 2. Wysyłamy do wątku TYLKO brakujące działki
        self.thread = PdfExtractorThread(self.pdf_path, output_dir, parcels_to_process)
        self.thread.progress.connect(self._update_progress)
        self.thread.log.connect(self.log_label.setText)
        self.thread.finished.connect(self._on_extraction_finished)
        self.thread.start()

    def _on_extraction_finished(self, results: dict):
        self.btn_extract.setEnabled(True)
        self.progress_bar.hide()
        
        success_count = 0
        # Aktualizujemy status TYLKO dla tych, które właśnie przetworzyliśmy
        for parcel_num, success in results.items():
            if parcel_num in self.target_parcels:
                if success:
                    self.target_parcels[parcel_num]['status'] = "TAK"
                    self.target_parcels[parcel_num]['color'] = "#2ecc71"
                    success_count += 1
                else:
                    self.target_parcels[parcel_num]['status'] = "NIE ZNALEZIONO"
                    self.target_parcels[parcel_num]['color'] = "#e74c3c"
                    
        self._refresh_table()

        total_missing = sum(1 for data in self.target_parcels.values() if data['status'] != "TAK")
        
        msg = f"Wydzielono {success_count} nowych działek z tego pliku PDF."
        if total_missing > 0:
            msg += f"\n\nNadal brakuje: {total_missing} działek. Wczytaj kolejny plik PDF i wciśnij Wydziel ponownie."
            
        QMessageBox.information(self, "Zakończono etap", msg)