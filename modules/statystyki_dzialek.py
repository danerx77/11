"""
parcel_owners_stats.py – Zakładka ze statystykami: Działka -> Ilość właścicieli
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QLineEdit, QGroupBox
)
from PySide6.QtCore import Qt

class ParcelOwnersStatsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.owners = []
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Nagłówek
        hdr = QLabel('📈 Statystyki: Działki i przypisani właściciele')
        hdr.setStyleSheet('font-size: 16px; font-weight: bold; padding-bottom: 5px;')
        main_layout.addWidget(hdr)

        # Pasek narzędzi (szukajka i podsumowanie)
        tools_layout = QHBoxLayout()
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Szukaj numeru działki...')
        self.search_edit.setMaximumWidth(250)
        self.search_edit.textChanged.connect(self._apply_search)
        tools_layout.addWidget(self.search_edit)
        
        tools_layout.addStretch()
        
        self.lbl_summary = QLabel('Liczba unikalnych działek: 0')
        self.lbl_summary.setStyleSheet('color: #aaa; font-weight: bold;')
        tools_layout.addWidget(self.lbl_summary)
        
        main_layout.addLayout(tools_layout)

        # Tabela
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Numer działki', 'Liczba właścicieli', 'Lista właścicieli (Podgląd)'])
        
        # Ustawienia kolumn
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers) # Tylko do odczytu
        
        main_layout.addWidget(self.table)

    def set_owners(self, owners: list):
        """Pobiera nową listę właścicieli z głównego programu i odświeża tabelę."""
        self.owners = owners
        self._refresh_table()

    def _refresh_table(self, filter_text: str = ''):
        self.table.setRowCount(0)
        
        # Grupowanie: Nr działki -> Lista nazwisk właścicieli
        stats = {}
        for o in self.owners:
            name = o.get('name_plural', o.get('full_name', 'Nieznany'))
            for p in o.get('parcels', []):
                parcel_num = p['number'] if isinstance(p, dict) else str(p)
                if parcel_num not in stats:
                    stats[parcel_num] = []
                stats[parcel_num].append(name)
                
        # Sortowanie alfabetyczne po numerze działki
        sorted_parcels = sorted(stats.keys())
        
        filter_text = filter_text.lower().strip()
        visible_count = 0

        for parcel_num in sorted_parcels:
            if filter_text and filter_text not in parcel_num.lower():
                continue
                
            owners_list = stats[parcel_num]
            owners_count = len(owners_list)
            owners_names_str = ", ".join(owners_list)
            
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Kolumna 0: Nr działki
            item_num = QTableWidgetItem(parcel_num)
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_num)
            
            # Kolumna 1: Ilość właścicieli
            item_count = QTableWidgetItem(f"{owners_count} właścicieli" if owners_count > 1 else "1 właściciel")
            item_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # Podświetlenie na czerwono, jeśli jest dużo współwłaścicieli
            if owners_count > 5:
                item_count.setForeground(Qt.GlobalColor.red)
                item_count.setFont(self._bold_font())
            self.table.setItem(row, 1, item_count)
            
            # Kolumna 2: Wypisane nazwiska
            item_names = QTableWidgetItem(owners_names_str)
            item_names.setToolTip(owners_names_str) # Wyświetla dymek po najechaniu myszką
            self.table.setItem(row, 2, item_names)
            
            visible_count += 1

        self.lbl_summary.setText(f'Liczba unikalnych działek: {len(stats)} (widoczne: {visible_count})')

    def _apply_search(self, text: str):
        self._refresh_table(text)
        
    def _bold_font(self):
        from PySide6.QtGui import QFont
        f = QFont()
        f.setBold(True)
        return f