"""
shipment_tracker.py – Zakładka śledzenia wysłanych przesyłek i historii generowania
"""
import json
import re
import webbrowser
from pathlib import Path
from datetime import datetime, timezone

from utils.shipment_tracking import (
    TRACKING_CATEGORY_ORDER,
    format_tracking_event,
    format_tracking_history,
    latest_tracking_event,
    normalize_tracking_code,
    parse_tracking_response,
    summarize_tracking_statuses,
    tracking_status_category,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog, QGroupBox,
    QHeaderView, QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout,
    QTabWidget
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
        layout.setSpacing(8)

        hdr = QLabel('📦 Śledzenie i Historia Przesyłek')
        hdr.setStyleSheet('font-size:16px; font-weight:700;')
        layout.addWidget(hdr)

        self.history_tabs = QTabWidget()
        self.history_tabs.setObjectName('shipment_history_tabs')
        layout.addWidget(self.history_tabs, 1)

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(10, 12, 10, 10)
        history_layout.setSpacing(8)

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

        self.btn_fetch_status = QPushButton('🔄 Pobierz statusy Poczty Polskiej')
        self.btn_fetch_status.setToolTip(
            'Pobiera najnowsze zdarzenia z systemu śledzenia Poczty Polskiej.'
        )
        self.btn_fetch_status.clicked.connect(self._fetch_all_tracking_statuses)
        top_row.addWidget(self.btn_fetch_status)

        self.btn_export_csv = QPushButton('💾 Eksportuj do CSV')
        self.btn_export_csv.clicked.connect(self._export_csv)
        top_row.addWidget(self.btn_export_csv)

        self.btn_clear_history = QPushButton('🗑️ Wyczyść historię')
        self.btn_clear_history.setObjectName('btn_danger')
        self.btn_clear_history.clicked.connect(self._clear_history)
        top_row.addWidget(self.btn_clear_history)
        history_layout.addLayout(top_row)

        # Tabela przesyłek
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            'Projekt', 'Data generowania', 'Adresat / Opis', 'Działki',
            'Typ koperty', 'Kod znaczka', 'Kopiuj', 'Śledzenie',
            'Status Poczty Polskiej', 'Ścieżka pliku'
        ])

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
        header.sectionResized.connect(
            lambda *args: self.config.update({
                'table_state_shipments': header.saveState().toHex().data().decode()
            })
        )
        header.sectionMoved.connect(
            lambda *args: self.config.update({
                'table_state_shipments': header.saveState().toHex().data().decode()
            })
        )

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        history_layout.addWidget(self.table, 1)

        self.lbl_summary = QLabel('Łącznie przesyłek: 0')
        self.lbl_summary.setObjectName('shipment_history_count')
        history_layout.addWidget(self.lbl_summary)
        self.history_tabs.addTab(history_page, '📋 Historia przesyłek')

        summary_page = QWidget()
        summary_page.setObjectName('shipment_summary_page')
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(14, 16, 14, 14)
        summary_layout.setSpacing(12)

        summary_intro = QFrame()
        summary_intro.setObjectName('shipment_summary_intro')
        intro_layout = QVBoxLayout(summary_intro)
        intro_layout.setContentsMargins(18, 16, 18, 16)
        intro_layout.setSpacing(5)
        summary_title = QLabel('Podsumowanie statusów kopert')
        summary_title.setObjectName('shipment_summary_title')
        intro_layout.addWidget(summary_title)
        summary_description = QLabel(
            'Zestawienie używa najnowszego zapisanego zdarzenia Poczty Polskiej '
            'i uwzględnia aktualne filtry Historii przesyłek.'
        )
        summary_description.setObjectName('shipment_summary_description')
        summary_description.setWordWrap(True)
        intro_layout.addWidget(summary_description)
        self.lbl_status_summary = QLabel(
            'Brak przesyłek do podsumowania. Pobierz statusy Poczty Polskiej.'
        )
        self.lbl_status_summary.setObjectName('shipment_summary_overview')
        self.lbl_status_summary.setWordWrap(True)
        self.lbl_status_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        intro_layout.addWidget(self.lbl_status_summary)
        summary_layout.addWidget(summary_intro)

        cards_caption = QLabel('Liczba przesyłek według statusu')
        cards_caption.setObjectName('shipment_summary_section_title')
        summary_layout.addWidget(cards_caption)

        cards_layout = QGridLayout()
        cards_layout.setHorizontalSpacing(12)
        cards_layout.setVerticalSpacing(10)
        self.status_cards: dict[str, QLabel] = {}
        card_tooltips = {
            'Doręczona / odebrana': 'Przesyłki potwierdzone jako doręczone lub odebrane.',
            'W doręczeniu': 'Przesyłki przekazane do doręczenia.',
            'W transporcie': 'Przesyłki w drodze albo w sortowni.',
            'Nadana': 'Przesyłki przyjęte lub nadane, bez kolejnego etapu.',
            'Awizowana': 'Przesyłki z pozostawionym awizem.',
            'Zwrot / niedoręczona': 'Przesyłki zwrócone albo niedoręczone.',
            'Nie pobrano': 'Przesyłki bez pobranego statusu.',
            'Problem z pobraniem': 'Przesyłki, dla których nie udało się pobrać statusu.',
            'Inny status': 'Pozostałe zdarzenia Poczty Polskiej.',
        }
        for index, category in enumerate(TRACKING_CATEGORY_ORDER):
            row, column = divmod(index, 3)
            cards_layout.addWidget(
                self._create_status_card(
                    category,
                    category,
                    card_tooltips.get(category, 'Liczba przesyłek w tej grupie.'),
                ),
                row,
                column,
            )
            cards_layout.setColumnStretch(column, 1)
        summary_layout.addLayout(cards_layout)

        detail_box = QGroupBox('Statusy według ostatniego zdarzenia')
        detail_box.setObjectName('shipment_status_detail_box')
        detail_layout = QVBoxLayout(detail_box)
        detail_layout.setContentsMargins(12, 18, 12, 12)
        self.status_summary_table = QTableWidget(0, 3)
        self.status_summary_table.setObjectName('shipment_status_summary_table')
        self.status_summary_table.setHorizontalHeaderLabels([
            'Status', 'Liczba', 'Przykładowe przesyłki'
        ])
        self.status_summary_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.status_summary_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.status_summary_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.status_summary_table.setAlternatingRowColors(True)
        self.status_summary_table.setWordWrap(True)
        self.status_summary_table.verticalHeader().setVisible(False)
        summary_header = self.status_summary_table.horizontalHeader()
        summary_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        summary_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        summary_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        detail_layout.addWidget(self.status_summary_table)
        summary_layout.addWidget(detail_box, 1)

        self.lbl_status_summary_scope = QLabel(
            'Zmiana wyszukiwania, projektu lub typu koperty odświeża to zestawienie.'
        )
        self.lbl_status_summary_scope.setObjectName('shipment_summary_scope')
        self.lbl_status_summary_scope.setWordWrap(True)
        summary_layout.addWidget(self.lbl_status_summary_scope)
        self.history_tabs.addTab(summary_page, '📊 Podsumowanie statusów')
        saved_tab = self.config.get('shipment_history_active_tab', 0)
        try:
            saved_tab = int(saved_tab)
        except (TypeError, ValueError):
            saved_tab = 0
        self.history_tabs.setCurrentIndex(max(0, min(saved_tab, self.history_tabs.count() - 1)))
        self.history_tabs.currentChanged.connect(
            lambda index: self.config.update({'shipment_history_active_tab': index})
        )

    def _create_status_card(self, key: str, title: str, tooltip: str) -> QFrame:
        """Tworzy czytelną kartę wskaźnika dla zakładki podsumowania."""

        card = QFrame()
        card.setObjectName('shipment_summary_card')
        card.setToolTip(tooltip)
        card.setMinimumHeight(96)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 12, 15, 12)
        card_layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName('shipment_summary_card_title')
        title_label.setWordWrap(True)
        card_layout.addWidget(title_label)
        value_label = QLabel('0')
        value_label.setObjectName('shipment_summary_card_value')
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        card_layout.addWidget(value_label)
        card_layout.addStretch()
        self.status_cards[key] = value_label
        return card

    # ──────────────────────────────────────────────────────────────
    # Logika ładowania i zapisu danych
    # ──────────────────────────────────────────────────────────────

    def set_owners(self, owners: list):
        self.owners = owners or []
        self._refresh_table()

    def _normalize_stamp_code(self, code: str) -> str:
        return normalize_tracking_code(code)

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

    def _tracking_error_result(self, message: str) -> dict:
        return {
            "tracking_status": f"Nie pobrano statusu: {message}"[:500],
            "tracking_latest_event": {},
            "tracking_events": [],
            "tracking_checked_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }

    def _tracking_result_from_response(self, xml: bytes) -> dict:
        parsed = parse_tracking_response(xml)
        events = [
            event for event in parsed.get("events", []) if isinstance(event, dict)
        ]
        latest_event = latest_tracking_event(events)
        if latest_event:
            return {
                # Pierwsza część to niezmieniona nazwa zdarzenia otrzymana od
                # Poczty Polskiej; dalsze części tylko ją czytelnie opisują.
                "tracking_status": format_tracking_event(latest_event),
                "tracking_latest_event": latest_event,
                "tracking_events": events,
                "tracking_checked_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            }

        message = str(parsed.get("message") or "brak zdarzeń w odpowiedzi SOAP")
        return self._tracking_error_result(message)

    def _fetch_tracking_status_from_www(self, code: str) -> dict:
        """Pobiera pełną historię zdarzeń przez oficjalne SOAP Poczty Polskiej."""
        code = self._normalize_stamp_code(code)
        if not code:
            return self._tracking_error_result("brak kodu przesyłki")

        try:
            from urllib.request import Request, urlopen

            endpoint = (
                "https://tt.poczta-polska.pl/Sledzenie/services/Sledzenie/"
                "SledzenieHttpSoap11Endpoint"
            )
            created = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.000Z"
            )
            # Pierwszy login jest aktualnym kontem jednorazowych zapytań
            # wskazanym w dokumentacji Poczty Polskiej. Pozostałe zachowują
            # zgodność z odpowiedziami starszych wdrożeń usługi.
            logins = ("sledeniepp", "sledzeniepp", "trackingpp")
            last_error = ""
            for login in logins:
                body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:sled="http://sledzenie.pocztapolska.pl">
  <soapenv:Header>
    <wsse:Security soapenv:mustUnderstand="1" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <wsse:UsernameToken wsu:Id="UsernameToken-2" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
        <wsse:Username>{login}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">PPSA</wsse:Password>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <sled:sprawdzPrzesylkePl><sled:numer>{code}</sled:numer></sled:sprawdzPrzesylkePl>
  </soapenv:Body>
</soapenv:Envelope>""".encode("utf-8")
                request = Request(
                    endpoint,
                    data=body,
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": "urn:sprawdzPrzesylkePl",
                        "User-Agent": "Mozilla/5.0",
                    },
                )
                try:
                    with urlopen(request, timeout=25) as response:
                        xml = response.read()
                    result = self._tracking_result_from_response(xml)
                    if result.get("tracking_events"):
                        return result
                    last_error = result["tracking_status"].removeprefix(
                        "Nie pobrano statusu: "
                    )
                except Exception as error:
                    last_error = str(error)
            return self._tracking_error_result(last_error or "brak odpowiedzi usługi")
        except Exception as error:
            return self._tracking_error_result(f"błąd pobrania: {error}")

    def _fetch_all_tracking_statuses(self):
        updated = 0
        for shipment in self.shipments:
            code = self._normalize_stamp_code(shipment.get('stamp_barcode', ''))
            if not code:
                continue
            shipment.update(self._fetch_tracking_status_from_www(code))
            updated += 1
        if updated:
            self._save_shipments()
            self._refresh_table()
        QMessageBox.information(
            self,
            'Statusy przesyłek',
            f'Pobrano/odświeżono statusy: {updated}',
        )

    def _tracking_tooltip(self, shipment: dict) -> str:
        checked_at = str(shipment.get("tracking_checked_at") or "").strip()
        events = shipment.get("tracking_events")
        if isinstance(events, list) and events:
            history = format_tracking_history(
                event for event in events if isinstance(event, dict)
            )
            if history:
                suffix = f"\n\nSprawdzono: {checked_at}" if checked_at else ""
                return "Pełna historia zdarzeń z Poczty Polskiej:\n" + history + suffix
        status = self._current_tracking_status(shipment)
        return f"{status}\nSprawdzono: {checked_at}" if checked_at else status

    def _shipment_summary_label(self, shipment: dict) -> str:
        recipient = re.sub(r"\s+", " ", str(shipment.get("addressee") or "")).strip()
        recipient = recipient or "[brak adresata]"
        if len(recipient) > 48:
            recipient = recipient[:45].rstrip() + "…"
        code = self._normalize_stamp_code(shipment.get("stamp_barcode", ""))
        return f"{recipient} [{code[-8:] if code else 'brak kodu'}]"

    def _set_status_card_values(self, status_groups: dict):
        """Ustawia licznik dla każdego rozpoznawanego statusu przesyłki."""

        for category in TRACKING_CATEGORY_ORDER:
            card = self.status_cards.get(category)
            if card is not None:
                card.setText(str(len(status_groups.get(category, []))))

    def _update_status_summary(self, shipments: list[dict]):
        """Odświeża podsumowanie statusów bez zmiany danych operatora."""

        if not hasattr(self, 'lbl_status_summary'):
            return

        status_groups = summarize_tracking_statuses(shipments)
        delivered_count = len(status_groups.get('Doręczona / odebrana', []))
        in_delivery_count = len(status_groups.get('W doręczeniu', []))
        in_transit_count = len(status_groups.get('W transporcie', []))
        sent_count = len(status_groups.get('Nadana', []))
        other_count = len(shipments) - delivered_count
        not_fetched_count = len(status_groups.get('Nie pobrano', []))
        self._set_status_card_values(status_groups)

        self.status_summary_table.setRowCount(0)
        if not shipments:
            self.lbl_status_summary.setText(
                'Brak przesyłek spełniających aktualne filtry.'
            )
            return

        c5_count = sum(
            shipment.get('envelope_type', shipment.get('env_type', '')) == 'C5'
            for shipment in shipments
        )
        c6_count = sum(
            shipment.get('envelope_type', shipment.get('env_type', '')) == 'C6'
            for shipment in shipments
        )
        printed_count = sum(
            bool(shipment.get('printed_on_druczek')) for shipment in shipments
        )
        self.lbl_status_summary.setText(
            f'Doręczono / odebrano: {delivered_count} • '
            f'w doręczeniu: {in_delivery_count} • '
            f'w transporcie: {in_transit_count} • nadano: {sent_count}.\n'
            f'Pozostałe statusy: {other_count} • nie pobrano: {not_fetched_count} • '
            f'wszystkie przesyłki: {len(shipments)}.\n'
            f'Koperty: C5 {c5_count}, C6 {c6_count} • '
            f'wydrukowane na druczku: {printed_count}.'
        )

        for category, entries in status_groups.items():
            labels = [self._shipment_summary_label(entry) for entry in entries[:4]]
            if len(entries) > len(labels):
                labels.append(f'… i {len(entries) - len(labels)} kolejne')

            row = self.status_summary_table.rowCount()
            self.status_summary_table.insertRow(row)
            category_item = QTableWidgetItem(category)
            count_item = QTableWidgetItem(str(len(entries)))
            count_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            count_item.setFont(QFont('', -1, QFont.Weight.Bold))
            example_item = QTableWidgetItem('; '.join(labels))
            example_item.setToolTip(
                'Przykładowi adresaci / kody z tej grupy statusów.'
            )
            self.status_summary_table.setItem(row, 0, category_item)
            self.status_summary_table.setItem(row, 1, count_item)
            self.status_summary_table.setItem(row, 2, example_item)

        self.status_summary_table.resizeRowsToContents()

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
        shown_records = []
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
            latest_event = s.get("tracking_latest_event")
            category = tracking_status_category(
                latest_event if isinstance(latest_event, dict) else status_item.text()
            )
            status_colors = {
                "Doręczona / odebrana": "#2ecc71",
                "W doręczeniu": "#40c4ff",
                "W transporcie": "#00b4d8",
                "Nadana": "#f1c40f",
                "Awizowana": "#ff9800",
                "Zwrot / niedoręczona": "#e74c3c",
                "Problem z pobraniem": "#e74c3c",
                "Nie pobrano": "#f1c40f",
                "Inny status": "#cfd8dc",
            }
            status_item.setForeground(QColor(status_colors.get(category, "#cfd8dc")))
            status_item.setToolTip(self._tracking_tooltip(s))
            self.table.setItem(row, 8, status_item)
            self.table.setItem(row, 9, QTableWidgetItem(s.get('path', '')))
            shown_records.append(s)
            shown += 1

        self._update_status_summary(shown_records)
        self.lbl_summary.setText(
            f'Wyświetlono przesyłek: {shown} '
            f'(w wybranym zakresie: {len(source_records)})'
        )

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
