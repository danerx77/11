"""
dashboard_tab.py – Centralny panel podsumowujący postęp prac i problemy  Status
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QGroupBox, QSplitter, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
import re

class DashboardTabWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.owners = []
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        hdr = QLabel('📊 Panel Zarządzania i Raportowania')
        hdr.setStyleSheet('font-size: 18px; font-weight: 700; padding-top: 0; padding-bottom: 0; margin-top: 0; margin-bottom: 0;')
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setFixedHeight(hdr.fontMetrics().height() + 14)
        main_layout.addWidget(hdr)

        stats_box = QGroupBox("Ogólny postęp prac")
        stats_layout = QHBoxLayout(stats_box)
        stats_layout.setSpacing(15)
        
        self.card_total = self._create_stat_card("Razem właścicieli", "0", "#34495e")  
        self.card_todo = self._create_stat_card("Do zrobienia", "0", "#e67e22")       
        self.card_sent = self._create_stat_card("Wysłane", "0", "#3498db")             
        self.card_done = self._create_stat_card("Zakończone", "0", "#2ecc71")          
        
        stats_layout.addWidget(self.card_total)
        stats_layout.addWidget(self.card_todo)
        stats_layout.addWidget(self.card_sent)
        stats_layout.addWidget(self.card_done)
        
        main_layout.addWidget(stats_box)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. Wymagają uwagi (Brak adresu)
        box_warn = QGroupBox("⚠️ Wymagają uwagi (Brak / błędny adres)")
        box_warn.setStyleSheet("QGroupBox { border: 1px solid #e67e22; } QGroupBox::title { color: #e67e22; }")
        ly_warn = QVBoxLayout(box_warn)
        self.table_warn = self._create_table()
        ly_warn.addWidget(self.table_warn)
        splitter.addWidget(box_warn)

        # 2. Zmarli
        box_dead = QGroupBox("✝️ Osoby Zmarłe (Wymaga postępowania)")
        box_dead.setStyleSheet("QGroupBox { border: 1px solid #e74c3c; } QGroupBox::title { color: #e74c3c; }")
        ly_dead = QVBoxLayout(box_dead)
        self.table_dead = self._create_table()
        ly_dead.addWidget(self.table_dead)
        splitter.addWidget(box_dead)

        # 3. Instytucje i Parafie
        box_inst = QGroupBox("🏛️ Instytucje / Gminy / Parafie (Wnioski odrębne)")
        box_inst.setStyleSheet("QGroupBox { border: 1px solid #9b5de5; } QGroupBox::title { color: #9b5de5; }")
        ly_inst = QVBoxLayout(box_inst)
        self.table_inst = self._create_table()
        ly_inst.addWidget(self.table_inst)
        splitter.addWidget(box_inst)

        main_layout.addWidget(splitter)

    def _create_stat_card(self, title, val, bg_color):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{ background-color: {bg_color}; border-radius: 8px; }}
            QLabel {{ color: white; background: transparent; border: none; }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_val = QLabel(str(val))
        lbl_val.setStyleSheet("font-size: 36px; font-weight: bold;")
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        frame.val_label = lbl_val
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        return frame

    def _create_table(self):
        t = QTableWidget(0, 3)
        t.setHorizontalHeaderLabels(['Właściciel', 'Działki', 'Info'])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return t

    def _get_address_status(self, address: str) -> str:
        if not address.strip(): return "Brak adresu"
        if not re.search(r'\d{2}-\d{3}', address): return "Brak kodu poczt."
        return "OK"

    def set_owners(self, owners: list):
        self.owners = owners
        
        total = len(owners)
        todo = sum(1 for o in owners if o.get('status_sprawy') in [None, "Do zrobienia", "W toku", "Wygenerowano"])
        sent = sum(1 for o in owners if o.get('status_sprawy') == "Wysłane")
        done = sum(1 for o in owners if o.get('status_sprawy') == "Zakończone")

        self.card_total.val_label.setText(str(total))
        self.card_todo.val_label.setText(str(todo))
        self.card_sent.val_label.setText(str(sent))
        self.card_done.val_label.setText(str(done))

        self.table_warn.setRowCount(0)
        self.table_dead.setRowCount(0)
        self.table_inst.setRowCount(0)

        for o in owners:
            name = o.get('full_name', '')
            parcels = ', '.join([p['number'] if isinstance(p, dict) else str(p) for p in o.get('parcels', [])])
            addr_status = self._get_address_status(o.get('address', ''))

            if o.get('is_dead', False):
                r = self.table_dead.rowCount()
                self.table_dead.insertRow(r)
                self.table_dead.setItem(r, 0, QTableWidgetItem(name))
                self.table_dead.setItem(r, 1, QTableWidgetItem(parcels))
                self.table_dead.setItem(r, 2, QTableWidgetItem("Brak spadkobierców"))

            # Tutaj teraz łapią się zarówno Instytucje jak i Parafie
            elif o.get('is_institution', False) or o.get('is_church', False):
                r = self.table_inst.rowCount()
                self.table_inst.insertRow(r)
                self.table_inst.setItem(r, 0, QTableWidgetItem(name))
                self.table_inst.setItem(r, 1, QTableWidgetItem(parcels))
                self.table_inst.setItem(r, 2, QTableWidgetItem("Wniosek odrębny"))

            # Firmy i ewentualne resztki bez adresu lecą na sam dół (żeby nie pominąć, jak firma nie ma adresu)
            elif addr_status != "OK":
                r = self.table_warn.rowCount()
                self.table_warn.insertRow(r)
                self.table_warn.setItem(r, 0, QTableWidgetItem(name))
                self.table_warn.setItem(r, 1, QTableWidgetItem(parcels))
                it = QTableWidgetItem(addr_status)
                it.setForeground(QColor("#e67e22"))
                self.table_warn.setItem(r, 2, it)