"""
shipment_tracker.py – Zakładka śledzenia wysłanych przesyłek i historii generowania
"""
import json
import re
import webbrowser
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog, QGroupBox,
    QHeaderView, QAbstractItemView, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication


class ShipmentTrackerWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.shipments = []
        self.owners = []
        self.active_project_path = None
        self.current_project_name = ''
        self.global_mode = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Nagłówek
        hdr = QLabel('📦 Śledzenie i Historia Przesyłek')
        hdr.setStyleSheet('font-size:16px; font-weight:700;')
        layout.addWidget(hdr)

        # Górny pasek opcji (filtr i przyciski akcji)
        top_row = QHBoxLayout()
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Szukaj po adresacie lub kodzie znaczka...')
        self.search_edit.textChanged.connect(self._apply_filter)
        top_row.addWidget(self.search_edit)

        self.chk_global_history = QCheckBox('Historia globalna')
        self.chk_global_history.setChecked(bool(self.config.get('shipment_global_mode', False)))
        self.chk_global_history.stateChanged.connect(self._on_global_mode_changed)
        top_row.addWidget(self.chk_global_history)

        self.project_filter_combo = QComboBox()
        self.project_filter_combo.setMinimumWidth(180)
        self.project_filter_combo.currentIndexChanged.connect(self._refresh_table)
        top_row.addWidget(self.project_filter_combo)

        self.chk_show_c5 = QCheckBox('C5')
        self.chk_show_c5.setChecked(bool(self.config.get('shipment_show_c5', True)))
        self.chk_show_c5.stateChanged.connect(self._on_type_filter_changed)
        top_row.addWidget(self.chk_show_c5)
        self.chk_show_c6 = QCheckBox('C6')
        self.chk_show_c6.setChecked(bool(self.config.get('shipment_show_c6', True)))
        self.chk_show_c6.stateChanged.connect(self._on_type_filter_changed)
        top_row.addWidget(self.chk_show_c6)

        self.btn_fetch_status = QPushButton('🔄 Pobierz statusy')
        self.btn_fetch_status.clicked.connect(self._fetch_all_tracking_statuses)
        top_row.addWidget(self.btn_fetch_status)

        self.btn_export_csv = QPushButton('💾 Eksportuj do CSV')
        self.btn_export_csv.clicked.connect(self._export_csv)
        top_row.addWidget(self.btn_export_csv)

        self.btn_clear_history = QPushButton('🗑️ Wyczyść historię')
        self.btn_clear_history.setObjectName('btn_danger')
        self.btn_clear_history.clicked.connect(self._clear_history)
        top_row.addWidget(self.btn_clear_history)

        layout.addLayout(top_row)

        # Tabela przesyłek
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            'Projekt', 'Data generowania', 'Adresat / Opis', 'Działki', 'Typ koperty', 'Kod znaczka', 'Kopiuj', 'Śledzenie', 'Status', 'Ścieżka pliku'
        ])
        
        # Ustawienia kolumn
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        for col in range(0, 9):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Interactive)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setWordWrap(False)
        table_state = self.config.get('table_state_shipments', '')
        if table_state:
            from PySide6.QtCore import QByteArray
            header.restoreState(QByteArray.fromHex(table_state.encode()))
        header.sectionResized.connect(lambda *args: self.config.update({'table_state_shipments': header.saveState().toHex().data().decode()}))
        header.sectionMoved.connect(lambda *args: self.config.update({'table_state_shipments': header.saveState().toHex().data().decode()}))
        
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        
        layout.addWidget(self.table)

        self.lbl_summary = QLabel('Łącznie przesyłek: 0')
        self.lbl_summary.setStyleSheet('color:#aaa; font-size:12px;')
        layout.addWidget(self.lbl_summary)

    # ──────────────────────────────────────────────────────────────
    # Logika ładowania i zapisu danych
    # ──────────────────────────────────────────────────────────────

    def set_owners(self, owners: list):
        self.owners = owners or []
        self._refresh_table()

    def _normalize_stamp_code(self, code: str) -> str:
        code = str(code or '').strip().replace('(00)', '00')
        return re.sub(r'[^0-9A-Za-z]', '', code)

    def _copy_stamp_code(self, code: str):
        QGuiApplication.clipboard().setText(self._normalize_stamp_code(code))

    def _open_tracking(self, code: str):
        normalized = self._normalize_stamp_code(code)
        if not normalized:
            return QMessageBox.warning(self, 'Brak kodu', 'Brak kodu znaczka.')
        webbrowser.open(f'https://emonitoring.poczta-polska.pl/?numer={normalized}')

    def _guess_parcels_for_addressee(self, addressee: str) -> str:
        text = str(addressee or '').lower()
        best = []
        best_score = 0
        for o in self.owners:
            names = [o.get('full_name',''), o.get('last_name',''), o.get('name_plural',''), o.get('name_separate','')]
            score = max((len(n) for n in names if n and n.lower() in text), default=0)
            if score > best_score:
                best_score = score
                best = [str(p.get('number', p)) if isinstance(p, dict) else str(p) for p in o.get('parcels', [])]
        return ', '.join(best)

    def _current_tracking_status(self, shipment: dict) -> str:
        return shipment.get('tracking_status') or 'Nie pobrano'

    def _fetch_tracking_status_from_www(self, code: str) -> str:
        code = self._normalize_stamp_code(code)
        if not code:
            return 'Brak kodu'
        try:
            from urllib.request import Request, urlopen
            from xml.etree import ElementTree as ET
            from datetime import datetime, timezone

            endpoint = 'https://tt.poczta-polska.pl/Sledzenie/services/Sledzenie/SledzenieHttpSoap11Endpoint'
            created = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            logins = ('sledeniepp', 'sledzeniepp', 'trackingpp')
            last_error = ''
            for login in logins:
                body = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:sled="http://sledzenie.pocztapolska.pl">
  <soapenv:Header>
    <wsse:Security soapenv:mustUnderstand="1" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <wsse:UsernameToken xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
        <wsse:Username>{login}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">PPSA</wsse:Password>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <sled:sprawdzPrzesylkePl><sled:numer>{code}</sled:numer></sled:sprawdzPrzesylkePl>
  </soapenv:Body>
</soapenv:Envelope>'''.encode('utf-8')
                req = Request(endpoint, data=body, headers={
                    'Content-Type': 'text/xml; charset=utf-8',
                    'SOAPAction': 'urn:sprawdzPrzesylkePl',
                    'User-Agent': 'Mozilla/5.0'
                })
                try:
                    with urlopen(req, timeout=25) as resp:
                        xml = resp.read()
                    root = ET.fromstring(xml)
                    events = []
                    for elem in root.iter():
                        lname = elem.tag.split('}', 1)[-1].lower()
                        if lname in ('zdarzenie', 'event', 'zdarzenia'):
                            data = {}
                            for child in elem.iter():
                                cl = child.tag.split('}', 1)[-1].lower()
                                txt = (child.text or '').strip()
                                if txt:
                                    data[cl] = txt
                            if data:
                                events.append(data)
                    if events:
                        # Wybierz najważniejszy realny status, nie techniczny wpis.
                        priorities = [
                            (120, ('odebran', 'odebrana', 'odebrano', 'wydano')),
                            (100, ('doręcz', 'dorecz')),
                            (80, ('awiz',)),
                            (60, ('przekazano do doręczenia', 'przekazano do doreczenia')),
                        ]
                        best_score = -1
                        ev = None
                        for candidate in events:
                            blob = ' '.join(str(v) for v in candidate.values()).lower()
                            if 'udostępnienie podpisu' in blob or 'udostepnienie podpisu' in blob:
                                score = 10
                            else:
                                score = 20
                            for val, keys in priorities:
                                if any(k in blob for k in keys):
                                    score = max(score, val)
                            if score >= best_score:
                                best_score = score
                                ev = candidate
                        if ev is None:
                            ev = events[-1]
                        vals = [str(v) for v in ev.values() if v]
                        status = (ev.get('nazwa') or ev.get('nazwa_zdarzenia') or ev.get('status') or ev.get('rodzaj') or '')
                        if not status:
                            status = next((v for v in vals if not re.search(r'\d{4}-\d{2}-\d{2}|\d{2}:\d{2}', v)), '')
                        if 'udostępnienie podpisu' in status.lower() or 'udostepnienie podpisu' in status.lower():
                            status = next((v for v in vals if 'doręcz' in v.lower() or 'dorecz' in v.lower()), status)
                        when = ev.get('czas') or ev.get('data') or ev.get('dataiczas') or ev.get('data_i_czas') or ''
                        if not when:
                            when = next((v for v in vals if re.search(r'\d{4}-\d{2}-\d{2}|\d{2}:\d{2}', v)), '')
                        if status and when:
                            return f'{status} | Data i czas: {when}'[:300]
                        if status:
                            return status[:300]
                        return str(ev)[:300]
                    text = xml.decode('utf-8', errors='ignore')
                    m = re.search(r'<[^>]*(?:opis|komunikat|status)[^>]*>(.*?)</', text, re.I | re.S)
                    if m:
                        return re.sub(r'\s+', ' ', m.group(1)).strip()[:250]
                    last_error = 'brak zdarzeń w odpowiedzi SOAP'
                except Exception as e:
                    last_error = str(e)
            return f'Nie pobrano statusu: {last_error}'[:300]
        except Exception as e:
            return f'Błąd pobrania: {e}'[:300]

    def _fetch_all_tracking_statuses(self):
        updated = 0
        for shipment in self.shipments:
            code = self._normalize_stamp_code(shipment.get('stamp_barcode', ''))
            if not code:
                continue
            shipment['tracking_status'] = self._fetch_tracking_status_from_www(code)
            updated += 1
        if updated:
            self._save_shipments()
            self._refresh_table()
        QMessageBox.information(self, 'Statusy przesyłek', f'Pobrano/odświeżono statusy: {updated}')

    def _refresh_project_filter(self):
        if not hasattr(self, 'project_filter_combo'):
            return
        current = self.project_filter_combo.currentText()
        self.project_filter_combo.blockSignals(True)
        self.project_filter_combo.clear()
        self.project_filter_combo.addItem('Bieżący projekt')
        self.project_filter_combo.addItem('Wszystkie projekty')
        for p in self.config.get('projects', []):
            name = p.get('name') or Path(p.get('path', '')).name
            self.project_filter_combo.addItem(name, p.get('path', ''))
        idx = self.project_filter_combo.findText(current)
        if idx >= 0:
            self.project_filter_combo.setCurrentIndex(idx)
        self.project_filter_combo.blockSignals(False)

    def _load_global_shipments(self):
        records = []
        for project in self.config.get('projects', []):
            p_path = project.get('path', '')
            if not p_path:
                continue
            f = Path(p_path) / 'przesylki' / 'shipments.json'
            if not f.exists():
                continue
            try:
                data = json.load(open(f, 'r', encoding='utf-8'))
            except Exception:
                continue
            name = project.get('name') or Path(p_path).name
            for rec in data:
                if isinstance(rec, dict):
                    x = dict(rec)
                    x['_project_name'] = name
                    x['_project_path'] = p_path
                    records.append(x)
        return records

    def _on_global_mode_changed(self):
        self.config['shipment_global_mode'] = self.chk_global_history.isChecked()
        self.global_mode = self.chk_global_history.isChecked()
        self._refresh_project_filter()
        self._refresh_table()

    def set_project(self, project: dict):
        self.active_project_path = project.get('path')
        self.current_project_name = project.get('name', '')
        self.global_mode = self.chk_global_history.isChecked() if hasattr(self, 'chk_global_history') else False
        self._refresh_project_filter()
        self._load_shipments()

    def _get_shipments_filepath(self) -> Path | None:
        if not self.active_project_path:
            return None
        return Path(self.active_project_path) / 'przesylki' / 'shipments.json'

    def _load_shipments(self):
        self.shipments.clear()
        filepath = self._get_shipments_filepath()
        if filepath and filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.shipments = json.load(f)
            except Exception as e:
                print(f"Błąd odczytu pliku przesyłek: {e}")
        
        self._refresh_table()

    def _save_shipments(self):
        filepath = self._get_shipments_filepath()
        if filepath:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.shipments, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"Błąd zapisu pliku przesyłek: {e}")

    def _refresh_table(self):
        self.table.setRowCount(0)
        filter_text = self.search_edit.text().lower() if hasattr(self, 'search_edit') else ''
        show_c5 = self.chk_show_c5.isChecked() if hasattr(self, 'chk_show_c5') else True
        show_c6 = self.chk_show_c6.isChecked() if hasattr(self, 'chk_show_c6') else True

        source_records = self.shipments
        if hasattr(self, 'chk_global_history') and self.chk_global_history.isChecked():
            source_records = self._load_global_shipments()
            chosen = self.project_filter_combo.currentData() if hasattr(self, 'project_filter_combo') else None
            chosen_text = self.project_filter_combo.currentText() if hasattr(self, 'project_filter_combo') else ''
            if chosen_text == 'Bieżący projekt' and self.active_project_path:
                source_records = [r for r in source_records if r.get('_project_path') == self.active_project_path]
            elif chosen_text not in ('', 'Wszystkie projekty', 'Bieżący projekt') and chosen:
                source_records = [r for r in source_records if r.get('_project_path') == chosen]

        shown = 0
        for s in source_records:
            addr = s.get('addressee', '')
            env_type = s.get('envelope_type', s.get('env_type', ''))
            if env_type == 'C5' and not show_c5: continue
            if env_type == 'C6' and not show_c6: continue
            bc = self._normalize_stamp_code(s.get('stamp_barcode', ''))
            parcels = s.get('parcels', s.get('parcel_numbers', ''))
            if isinstance(parcels, list): parcels = ', '.join(map(str, parcels))
            if not parcels:
                parcels = self._guess_parcels_for_addressee(addr)

            search_blob = f"{addr} {bc} {parcels} {env_type}".lower()
            if filter_text and filter_text not in search_blob:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(s.get('_project_name', self.current_project_name)))
            self.table.setItem(row, 1, QTableWidgetItem(s.get('date', '')))
            self.table.setItem(row, 2, QTableWidgetItem(addr))
            self.table.setItem(row, 3, QTableWidgetItem(str(parcels or '')))
            self.table.setItem(row, 4, QTableWidgetItem(env_type))

            bc_item = QTableWidgetItem(bc or '[brak]')
            if bc:
                bc_item.setForeground(QColor('#00b4d8'))
                bc_item.setFont(QFont('', -1, QFont.Weight.Bold))
            self.table.setItem(row, 5, bc_item)

            btn_copy = QPushButton('📋')
            btn_copy.setToolTip('Kopiuj kod znaczka')
            btn_copy.clicked.connect(lambda _=False, c=bc: self._copy_stamp_code(c))
            self.table.setCellWidget(row, 6, btn_copy)

            btn_track = QPushButton('🔎 Przejdź')
            btn_track.clicked.connect(lambda _=False, c=bc: self._open_tracking(c))
            self.table.setCellWidget(row, 7, btn_track)

            status_item = QTableWidgetItem(self._current_tracking_status(s))
            status_item.setForeground(QColor('#f1c40f') if status_item.text() == 'Nie pobrano' else QColor('#2ecc71'))
            self.table.setItem(row, 8, status_item)
            self.table.setItem(row, 9, QTableWidgetItem(s.get('path', '')))
            shown += 1

        self.lbl_summary.setText(f'Wyświetlono przesyłek: {shown} (Razem w projekcie: {len(self.shipments)})')

    def _apply_filter(self):
        self._refresh_table()

    def _on_type_filter_changed(self):
        if hasattr(self, 'chk_show_c5'):
            self.config['shipment_show_c5'] = self.chk_show_c5.isChecked()
        if hasattr(self, 'chk_show_c6'):
            self.config['shipment_show_c6'] = self.chk_show_c6.isChecked()
        self._refresh_table()

    # ──────────────────────────────────────────────────────────────
    # Reakcja na sygnały zewnętrzne
    # ──────────────────────────────────────────────────────────────

    def add_shipment(self, shipment: dict):
        """Dodaje nową przesyłkę i zapisuje do pliku."""
        # Zapobiegamy duplikowaniu identycznych wpisów w tym samym czasie
        for s in self.shipments:
            if s.get('path') == shipment.get('path') and s.get('envelope_type') == shipment.get('envelope_type'):
                return
                
        self.shipments.append(shipment)
        self._save_shipments()
        self._refresh_table()

    # ──────────────────────────────────────────────────────────────
    # Akcje użytkownika
    # ──────────────────────────────────────────────────────────────

    def _on_row_double_clicked(self, index):
        row = index.row()
        path_item = self.table.item(row, 9)
        if path_item and path_item.text():
            try:
                import os
                target = Path(path_item.text())
                os.startfile(str(target.parent if target.is_file() else target))
            except Exception:
                pass

    def _clear_history(self):
        if not self.shipments:
            return
            
        reply = QMessageBox.question(
            self, 'Wyczyść historię',
            'Czy na pewno chcesz usunąć całą historię wygenerowanych przesyłek w tym projekcie?\n'
            'Pliki kopert na dysku NIE zostaną usunięte.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.shipments.clear()
            self._save_shipments()
            self._refresh_table()

    def _export_csv(self):
        if not self.shipments:
            QMessageBox.information(self, "Brak danych", "Brak przesyłek do wyeksportowania.")
            return
            
        path, _ = QFileDialog.getSaveFileName(
            self, 'Eksportuj historię przesyłek', 'historia_przesylek.csv', 'Pliki CSV (*.csv)'
        )
        if not path:
            return
            
        try:
            import csv
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['Data', 'Adresat', 'Dzialki', 'Typ koperty', 'Kod znaczka', 'Status', 'Sciezka pliku'])
                for s in self.shipments:
                    writer.writerow([
                        s.get('date', ''),
                        s.get('addressee', ''),
                        ', '.join(map(str, s.get('parcels', s.get('parcel_numbers', [])))) if isinstance(s.get('parcels', s.get('parcel_numbers', [])), list) else s.get('parcels', s.get('parcel_numbers', '')),
                        s.get('envelope_type', s.get('env_type', '')),
                        self._normalize_stamp_code(s.get('stamp_barcode', '')),
                        self._current_tracking_status(s),
                        s.get('path', '')
                    ])
            QMessageBox.information(self, "Sukces", f"Historia została wyeksportowana do pliku:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się wyeksportować danych:\n{e}")
