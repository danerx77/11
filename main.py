"""
main.py – Główny punkt wejściowy aplikacji Pysilde 6.

Wersja z dwurzędowym paskiem modułów. Zakładki można ręcznie
przeciągać między pozycjami, a ich kolejność jest zapisywana w konfiguracji.
"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
)


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


app_dir = get_app_dir()


def setup_playwright_browsers() -> None:
    """Ustawia ścieżkę do przeglądarek Playwright po zbudowaniu PyInstallerem.

    Dzięki temu KW/KRS na innym komputerze znajduje dołączony folder
    ms-playwright zamiast szukać go w profilu użytkownika komputera,
    na którym program jest uruchamiany.
    """
    import os

    if not getattr(sys, "frozen", False):
        return

    candidates = []
    exe_dir = Path(sys.executable).parent
    candidates.append(exe_dir / "ms-playwright")

    meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
    candidates.append(meipass / "ms-playwright")

    # PyInstaller 6 w trybie --onedir często trzyma dane w folderze _internal.
    candidates.append(exe_dir / "_internal" / "ms-playwright")

    for path in candidates:
        if path.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(path)
            break


setup_playwright_browsers()

if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))


from modules.projekty import ProjectManagerWidget
from modules.status import DashboardTabWidget
from modules.dzialki import ParcelListWidget
from modules.sortowanie_dzialek import ParcelSortingWidget
from modules.wypisy import OwnersListWidget
from modules.oswiadczenia_woli import DeclGeneratorWidget
from modules.pisma_przewodnie import CoverLetterWidget
from modules.koperty import EnvelopeGenWidget
from modules.historia import ShipmentTrackerWidget
from modules.druczki import DruczekTabWidget
from modules.ocr import OcrOverlayWindow
from modules.ustawienia import SettingsTabWidget
from modules.drukuj import PrintManagerWidget
from modules.tytuly_prawne import LegalTitlesWidget
from modules.wydziel_pdf import ExtractPdfWidget
from modules.statystyki_dzialek import ParcelOwnersStatsWidget
from modules.kw import KWDownloaderWidget
from modules.krs import KrsDownloaderWidget
from utils.global_settings import (
    load_global_druczek_profile,
    load_global_envelope_preferences,
    load_global_stamp_settings,
)


class NoComboWheelFilter(QObject):
    """Blokuje zmianę wartości QComboBox kółkiem myszy w całej aplikacji."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox)):
            event.ignore()
            return True
        return super().eventFilter(obj, event)


TAB_MIME_TYPE = "application/x-pysilde-module-tab"


class DraggableTabButton(QToolButton):
    """Przycisk modułu obsługujący rozpoczęcie przeciągania."""

    def __init__(self, navigator, text: str, parent=None):
        super().__init__(parent)
        self.navigator = navigator
        self._press_position = QPoint()

        self.setObjectName("module_tab_button")
        self.setText(text)
        self.setToolTip(f"{text}\nPrzeciągnij, aby zmienić położenie zakładki.")
        self.setCheckable(True)
        self.setAutoRaise(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(38)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return

        distance = (event.position().toPoint() - self._press_position).manhattanLength()
        if distance < QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return

        source_index = self.navigator.index_of_button(self)
        if source_index < 0:
            return

        mime_data = QMimeData()
        mime_data.setData(TAB_MIME_TYPE, str(source_index).encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._press_position)

        self.setDown(False)
        drag.exec(Qt.DropAction.MoveAction)


class TabNavigationPanel(QWidget):
    """Panel przyjmujący upuszczane przyciski zakładek."""

    def __init__(self, navigator, parent=None):
        super().__init__(parent)
        self.navigator = navigator
        self.setObjectName("module_navigation")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(TAB_MIME_TYPE):
            event.ignore()
            return

        target_index = self.navigator.index_at_position(event.position().toPoint())
        self.navigator.show_drop_target(target_index)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.navigator.clear_drop_target()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.navigator.clear_drop_target()

        if not event.mimeData().hasFormat(TAB_MIME_TYPE):
            event.ignore()
            return

        try:
            raw_index = bytes(event.mimeData().data(TAB_MIME_TYPE)).decode("utf-8")
            source_index = int(raw_index)
        except (TypeError, ValueError):
            event.ignore()
            return

        target_index = self.navigator.index_at_position(event.position().toPoint())
        self.navigator.move_tab(source_index, target_index)
        event.acceptProposedAction()


class ModuleTabWidget(QWidget):
    """
    Dwurzędowy zamiennik QTabWidget.

    Przy 17 modułach i columns=9 powstają nadal tylko dwa rzędy.
    Zakładki można przeciągać pomiędzy wszystkimi pozycjami.
    """

    currentChanged = Signal(int)
    orderChanged = Signal()

    def __init__(self, parent=None, columns: int = 8):
        super().__init__(parent)

        self.columns = max(1, columns)
        self.buttons = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)

        # Górny pasek na przyciski Zapisz, Motyw i OCR.
        self.actions_widget = QWidget()
        self.actions_widget.setObjectName("module_actions_widget")
        self.actions_layout = QHBoxLayout(self.actions_widget)
        self.actions_layout.setContentsMargins(4, 0, 4, 0)
        self.actions_layout.setSpacing(5)
        self.actions_layout.addStretch(1)
        self.actions_widget.hide()
        main_layout.addWidget(self.actions_widget)

        # Dwurzędowa nawigacja modułów.
        self.navigation_widget = TabNavigationPanel(self)
        self.navigation_layout = QGridLayout(self.navigation_widget)
        self.navigation_layout.setContentsMargins(5, 5, 5, 5)
        self.navigation_layout.setHorizontalSpacing(5)
        self.navigation_layout.setVerticalSpacing(5)
        main_layout.addWidget(self.navigation_widget)

        # Obszar aktualnie wybranego modułu.
        self.stack = QStackedWidget()
        self.stack.setObjectName("module_stack")
        main_layout.addWidget(self.stack, 1)

        self.stack.currentChanged.connect(self.currentChanged.emit)

    def addTab(self, widget: QWidget, text: str) -> int:
        index = self.stack.addWidget(widget)

        button = DraggableTabButton(self, text, self.navigation_widget)
        button.clicked.connect(
            lambda checked=False, tab_button=button: self._activate_button(tab_button)
        )
        self.buttons.append(button)

        self._rebuild_navigation_grid()

        if index == 0:
            self.setCurrentIndex(0)

        return index

    def _activate_button(self, button):
        index = self.index_of_button(button)
        if index >= 0:
            self.setCurrentIndex(index)

    def index_of_button(self, button) -> int:
        try:
            return self.buttons.index(button)
        except ValueError:
            return -1

    def index_at_position(self, position: QPoint) -> int:
        """Zwraca pozycję zakładki najbliższą miejscu upuszczenia."""
        if not self.buttons:
            return -1

        child = self.navigation_widget.childAt(position)
        while child is not None and not isinstance(child, DraggableTabButton):
            child = child.parentWidget()

        if isinstance(child, DraggableTabButton):
            return self.index_of_button(child)

        # Gdy upuszczono w odstępie między przyciskami, wybieramy najbliższy.
        nearest_index = 0
        nearest_distance = None

        for index, button in enumerate(self.buttons):
            center = button.geometry().center()
            distance = (center.x() - position.x()) ** 2 + (center.y() - position.y()) ** 2
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_index = index

        return nearest_index

    def show_drop_target(self, index: int):
        for button_index, button in enumerate(self.buttons):
            is_target = button_index == index
            if button.property("dropTarget") != is_target:
                button.setProperty("dropTarget", is_target)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()

    def clear_drop_target(self):
        self.show_drop_target(-1)

    def move_tab(self, source_index: int, target_index: int, emit_signal: bool = True):
        if not (0 <= source_index < len(self.buttons)):
            return
        if not (0 <= target_index < len(self.buttons)):
            return
        if source_index == target_index:
            return

        current_widget = self.stack.currentWidget()

        button = self.buttons.pop(source_index)
        page = self.stack.widget(source_index)
        self.stack.removeWidget(page)

        self.buttons.insert(target_index, button)
        self.stack.insertWidget(target_index, page)

        self._rebuild_navigation_grid()

        if current_widget is not None:
            self.stack.setCurrentWidget(current_widget)
            self._update_checked_button()

        if emit_signal:
            self.orderChanged.emit()

    def _rebuild_navigation_grid(self):
        while self.navigation_layout.count():
            item = self.navigation_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(self.navigation_widget)

        for index, button in enumerate(self.buttons):
            row = index // self.columns
            column = index % self.columns
            self.navigation_layout.addWidget(button, row, column)

        # Wszystkie kolumny mają jednakową szerokość.
        for column in range(self.columns):
            self.navigation_layout.setColumnStretch(column, 1)

    def setCurrentIndex(self, index: int):
        if not (0 <= index < self.stack.count()):
            return

        self.stack.setCurrentIndex(index)
        self._update_checked_button()

    def _update_checked_button(self):
        current_index = self.stack.currentIndex()
        for index, button in enumerate(self.buttons):
            button.setChecked(index == current_index)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()

    def currentWidget(self):
        return self.stack.currentWidget()

    def widget(self, index: int):
        return self.stack.widget(index)

    def count(self) -> int:
        return self.stack.count()

    def tab_order(self) -> list[str]:
        return [button.text() for button in self.buttons]

    def restore_order(self, saved_order):
        """Odtwarza kolejność zapisaną wcześniej w app_config.json."""
        if not isinstance(saved_order, list):
            return

        for target_index, tab_name in enumerate(saved_order):
            source_index = next(
                (
                    index
                    for index, button in enumerate(self.buttons)
                    if button.text() == tab_name
                ),
                -1,
            )
            if source_index >= 0 and source_index != target_index:
                self.move_tab(source_index, target_index, emit_signal=False)

    def setCornerWidget(self, widget, corner=None):
        # Parametr corner pozostaje dla zgodności z API QTabWidget.
        self.actions_layout.addWidget(widget)
        self.actions_widget.show()

    # Zachowane dla zgodności ze starszym kodem korzystającym z QTabWidget.
    def setMovable(self, movable: bool):
        pass

    def setDocumentMode(self, enabled: bool):
        pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Pysilde 6 – Zarządzanie Inwestycjami Elektroenergetycznymi"
        )
        self.setMinimumSize(1200, 800)

        self._is_switching_project = False

        self.load_configuration()
        self.ocr_overlay = None
        self.current_theme = self.config.get("theme", "dark")

        self._build_ui()
        self._setup_connections()

        if self.current_theme == "light":
            self._apply_light_stylesheet()
            self.btn_theme_toggle.setText("🌙 Noc")
        else:
            self._apply_dark_stylesheet()
            self.btn_theme_toggle.setText("☀️ Dzień")

        self.statusBar().showMessage(
            "Aplikacja uruchomiona. Wybierz lub utwórz projekt, aby rozpocząć pracę."
        )

    def load_configuration(self):
        self.data_dir = app_dir / "dane"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.data_dir / "app_config.json"
        self.examples_path = self.data_dir / "examples.json"

        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as file:
                    self.config = json.load(file)
            except Exception:
                self.config = self._get_default_config()
        else:
            self.config = self._get_default_config()

        # Profile wspólnych narzędzi są celowo niezależne od projektu i są
        # zapisywane od razu w katalogu dane. Wczytaj je przed utworzeniem
        # zakładek, aby Ustawienia, Koperty i Druczki używały tych samych
        # wartości od pierwszego wyświetlenia.
        self._load_global_tool_profiles()

        if self.examples_path.exists():
            try:
                with open(self.examples_path, "r", encoding="utf-8") as file:
                    self.examples = json.load(file)
            except Exception:
                self.examples = self._get_default_examples()
        else:
            self.examples = self._get_default_examples()

    def _load_global_tool_profiles(self):
        stamp_settings = load_global_stamp_settings(self.data_dir)
        if stamp_settings:
            self.config.update(stamp_settings)

        envelope_preferences = load_global_envelope_preferences(self.data_dir)
        if envelope_preferences:
            self.config.update(envelope_preferences)

        druczek_profile = load_global_druczek_profile(self.data_dir)
        if druczek_profile:
            self.config["druczek_profile"] = druczek_profile

    def save_configuration(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as file:
                json.dump(self.config, file, ensure_ascii=False, indent=4)
        except Exception:
            pass

        if hasattr(self, "examples") and self.examples:
            try:
                with open(self.examples_path, "w", encoding="utf-8") as file:
                    json.dump(self.examples, file, ensure_ascii=False, indent=4)
            except Exception:
                pass

        if not self._is_switching_project:
            if hasattr(self, "owners_tab") and self.owners_tab.owners:
                self.owners_tab._refresh_table()
            if hasattr(self, "decl_tab") and self.decl_tab.owners:
                self.decl_tab._refresh_owners_table()
            if hasattr(self, "cover_tab") and self.cover_tab.owners:
                self.cover_tab._refresh_owners_table()
            if hasattr(self, "envelope_tab") and self.envelope_tab.owners:
                self.envelope_tab._refresh_owners_table()

    def _get_default_config(self) -> dict:
        return {
            "app_version": "1.0.0",
            "sender": {
                "name": "Imie Nazwisko",
                "company": "ENERGA-OPERATOR SA",
                "street": "ul. Przykladowa 1",
                "city": "80-000 Gdansk",
            },
            "default_project_root": "",
            "last_project_path": "",
            "theme": "dark",
            "projects": [],
            "module_tab_order": [],
            "module_tab_order_classic": [],
            "tab_layout_mode": "modern",
            "parcel_list_filter": "Wszystkie",
            "parcel_list_sort": "Domyślne",
            "owners_list_sort_index": 0,
            "envelope_hide_generated": False,
            "envelope_show_only_generated": False,
            "envelope_view_sort": 0,
            "envelope_generation_sort": 0,
            "envelope_single_files": False,
            "envelope_output_dir": "",
            "envelope_stamps_tab": 0,
            "envelope_table_state": "",
            "envelope_splitter_sizes": [],
            "cover_skip_dead": True,
            "cover_skip_institution": True,
            "cover_skip_church": True,
            "cover_skip_company": False,
            "cover_skip_spolka": False,
            "cover_skip_missing_address": True,
            "cover_skip_invalid_postal_code": True,
            "parcel_sorter_input": "",
            "parcel_sorter_result": "",
            "parcel_sorter_remove_duplicates": False,
        }

    def _get_default_examples(self) -> dict:
        return {
            "device_types_budowa": [],
            "device_types_demontaz": [],
        }

    def _build_ui(self):
        if not hasattr(self, '_no_combo_wheel_filter'):
            self._no_combo_wheel_filter = NoComboWheelFilter(self)
            QApplication.instance().installEventFilter(self._no_combo_wheel_filter)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Użytkownik może wybrać nowy układ dwurzędowy albo klasyczny QTabWidget.
        self.tab_layout_mode = self.config.get("tab_layout_mode", "modern")
        if self.tab_layout_mode == "classic":
            self.tabs = QTabWidget()
            self.tabs.setMovable(True)
            self.tabs.setDocumentMode(True)
            self.tabs.tabBar().setUsesScrollButtons(True)
            self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        else:
            self.tab_layout_mode = "modern"
            self.tabs = ModuleTabWidget(columns=9)

        self.project_tab = ProjectManagerWidget(self.config)
        self.dashboard_tab = DashboardTabWidget(self.config)
        self.parcel_tab = ParcelListWidget(self.config)
        self.parcel_sort_tab = ParcelSortingWidget(self.config)
        self.owners_tab = OwnersListWidget(self.config)
        self.legal_titles_tab = LegalTitlesWidget(self.config)

        self.decl_tab = DeclGeneratorWidget(
            self.config, self.examples, self.save_configuration
        )
        self.cover_tab = CoverLetterWidget(
            self.config, self.examples, self.save_configuration
        )

        self.envelope_tab = EnvelopeGenWidget(self.config)
        self.druczek_tab = DruczekTabWidget(self.config)
        self.tracker_tab = ShipmentTrackerWidget(self.config)
        self.print_tab = PrintManagerWidget(self.config)
        self.extract_pdf_tab = ExtractPdfWidget(self)
        self.kw_tab = KWDownloaderWidget(self.config)
        self.krs_downloader_tab = KrsDownloaderWidget(self.config)
        self.settings_tab = SettingsTabWidget(
            self.config, self.save_configuration
        )
        self.stats_tab = ParcelOwnersStatsWidget(self)

        modules = [
            (self.project_tab, "📁 Projekty", "📁 Projekty"),
            (self.dashboard_tab, "📊 Status", "📊 Status"),
            (self.parcel_tab, "📋 Działki", "📋 Lista Działek"),
            (self.parcel_sort_tab, "↕️ Sortuj działki", "↕️ Sortowanie Działek"),
            (self.owners_tab, "👥 Wypisy", "👥 Wypisy"),
            (self.legal_titles_tab, "⚖️ Tytuły prawne", "⚖️ Tytuły Prawne"),
            (self.decl_tab, "📄 Oświadczenia", "📄 Oświadczenia"),
            (self.cover_tab, "📬 Pisma", "📬 Pisma"),
            (self.envelope_tab, "✉️ Koperty", "✉️ Koperty C5/C6"),
            (self.druczek_tab, "🖨️ Druczki", "🖨️ Druczki"),
            (self.tracker_tab, "📦 Historia", "📦 Historia"),
            (self.print_tab, "🖨️ Drukuj", "🖨️ Drukuj"),
            (self.extract_pdf_tab, "✂️ Wydziel PDF", "✂️ Wydzielanie PDF"),
            (self.stats_tab, "📈 Statystyki", "📈 Statystyki Działek"),
            (self.kw_tab, "📚 Księgi wieczyste KW", "📚 Księgi Wieczyste KW (PDF)"),
            (self.krs_downloader_tab, "🏛️ KRS", "🏛️ Odpisy KRS"),
            (self.settings_tab, "⚙️ Ustawienia", "⚙️ Ustawienia"),
        ]

        for widget, modern_name, classic_name in modules:
            name = classic_name if self.tab_layout_mode == "classic" else modern_name
            self.tabs.addTab(widget, name)

        # Każdy wygląd zachowuje własną kolejność zakładek.
        if self.tab_layout_mode == "classic":
            self._restore_classic_tab_order(
                self.config.get("module_tab_order_classic", [])
            )
        else:
            self.tabs.restore_order(self.config.get("module_tab_order", []))

        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(5)

        self.btn_save_project = QPushButton("💾 Zapisz")
        self.btn_save_project.setObjectName("btn_ocr_corner")
        self.btn_save_project.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_project.clicked.connect(self._save_project_global)
        corner_layout.addWidget(self.btn_save_project)

        self.btn_theme_toggle = QPushButton("☀️ Dzień")
        self.btn_theme_toggle.setObjectName("btn_ocr_corner")
        self.btn_theme_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_toggle.clicked.connect(self._toggle_theme)
        corner_layout.addWidget(self.btn_theme_toggle)

        self.btn_ocr_trigger = QPushButton("📸 OCR")
        self.btn_ocr_trigger.setObjectName("btn_ocr_corner")
        self.btn_ocr_trigger.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ocr_trigger.clicked.connect(self._toggle_ocr_overlay)
        corner_layout.addWidget(self.btn_ocr_trigger)

        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        main_layout.addWidget(self.tabs)
        self._setup_all_table_state_memory()

        self.setStatusBar(QStatusBar(self))

    def _setup_all_table_state_memory(self):
        """Zapamiętuje szerokości i kolejność kolumn we wszystkich tabelach modułów."""
        for idx, table in enumerate(self.findChildren(QTableWidget)):
            header = table.horizontalHeader()
            if header is None:
                continue
            if not table.objectName():
                parent_name = table.parentWidget().metaObject().className() if table.parentWidget() else 'table'
                table.setObjectName(f'{parent_name}_{idx}')
            key = f'global_table_state_{table.objectName()}'
            state_hex = self.config.get(key, '')
            if state_hex:
                try:
                    from PySide6.QtCore import QByteArray
                    header.restoreState(QByteArray.fromHex(state_hex.encode()))
                except Exception:
                    pass
            header.setSectionsMovable(True)
            header.sectionResized.connect(lambda *args, h=header, k=key: self.config.update({k: h.saveState().toHex().data().decode()}))
            header.sectionMoved.connect(lambda *args, h=header, k=key: self.config.update({k: h.saveState().toHex().data().decode()}))

    def _setup_connections(self):
        self.project_tab.project_selected.connect(self._on_project_changed)

        self.owners_tab.owners_changed.connect(self._on_owners_changed)
        self.parcel_tab.parcels_changed.connect(self._on_parcels_changed)

        self.envelope_tab.shipment_generated.connect(
            self.tracker_tab.add_shipment
        )
        self.envelope_tab.shipment_generated.connect(
            lambda *args: self.druczek_tab._load_c5_shipments()
        )

        self.legal_titles_tab.owners_changed.connect(self._on_owners_changed)
        self.decl_tab.owners_changed.connect(self._on_owners_changed)
        self.cover_tab.owners_changed.connect(self._on_owners_changed)

        # Po każdym przeciągnięciu zapamiętujemy bieżącą kolejność.
        if isinstance(self.tabs, ModuleTabWidget):
            self.tabs.orderChanged.connect(self._remember_module_tab_order)
        else:
            self.tabs.tabBar().tabMoved.connect(
                lambda _from, _to: self._remember_module_tab_order()
            )

    def _restore_classic_tab_order(self, saved_order):
        if not isinstance(saved_order, list):
            return

        tab_bar = self.tabs.tabBar()
        for target_index, tab_name in enumerate(saved_order):
            source_index = next(
                (
                    index
                    for index in range(self.tabs.count())
                    if self.tabs.tabText(index) == tab_name
                ),
                -1,
            )
            if source_index >= 0 and source_index != target_index:
                tab_bar.moveTab(source_index, target_index)

    def _remember_module_tab_order(self):
        if isinstance(self.tabs, ModuleTabWidget):
            self.config["module_tab_order"] = self.tabs.tab_order()
        else:
            self.config["module_tab_order_classic"] = [
                self.tabs.tabText(index) for index in range(self.tabs.count())
            ]

    def _on_project_changed(self, project: dict):
        self._is_switching_project = True

        try:
            project_name = project.get("name", "Brak nazwy")
            self.statusBar().showMessage(
                f"Aktywny projekt: {project_name} ({project.get('path')})"
            )
            self.setWindowTitle(f"Pysilde 6 – [Projekt: {project_name}]")

            self.config["last_project_path"] = project.get("path")
            self.config["last_project_symbol"] = project.get("symbol", "")
            self.save_configuration()

            # Zaktualizuj ścieżkę projektu w zakładkach ZANIM wyczyszczone
            # zostaną dane. Zakładka Koperty zapisuje plik adresaci.json już
            # podczas set_owners(), więc musi znać nową ścieżkę — inaczej
            # zapisze go do STAREJ ścieżki i odtworzy stary folder projektu.
            self.envelope_tab.set_project(project)

            # Czyszczenie danych przed załadowaniem nowego projektu.
            empty_list = []
            self.owners_tab.owners = []
            self.parcel_tab.parcels = []

            self.decl_tab.set_owners(empty_list)
            self.cover_tab.set_owners(empty_list)
            self.envelope_tab.set_owners(empty_list)
            self.tracker_tab.set_owners(empty_list)
            self.kw_tab.set_owners(empty_list)
            self.legal_titles_tab.set_owners(empty_list)
            self.krs_downloader_tab.set_owners(empty_list)

            # Załadowanie projektu w poszczególnych modułach.
            self.parcel_tab.set_project(project)
            self.owners_tab.set_project(project)

            self.decl_tab.set_project(project)
            self.cover_tab.set_project(project)
            self.druczek_tab.set_project(project)
            self.tracker_tab.set_project(project)
            self.print_tab.set_project(project)
            self.legal_titles_tab.set_project(project)
            self.krs_downloader_tab.set_project(project)

            fresh_owners = self.owners_tab.get_owners()
            self.dashboard_tab.set_owners(fresh_owners)
            self.stats_tab.set_owners(fresh_owners)
            self.decl_tab.set_owners(fresh_owners)
            self.cover_tab.set_owners(fresh_owners)
            self.envelope_tab.set_owners(fresh_owners)
            self.tracker_tab.set_owners(fresh_owners)
            self.print_tab.set_owners(fresh_owners)
            self.kw_tab.set_owners(fresh_owners)
            self.legal_titles_tab.set_owners(fresh_owners)
            self.krs_downloader_tab.set_owners(fresh_owners)

            fresh_parcels = self.parcel_tab.get_parcels()
            self.parcel_sort_tab.set_parcels(fresh_parcels)
            self.decl_tab.set_parcels(fresh_parcels)
            self.cover_tab.set_parcels(fresh_parcels)
            self.legal_titles_tab.set_parcels(fresh_parcels)
            self.owners_tab.set_active_parcels(fresh_parcels)
            self.extract_pdf_tab.set_global_parcels(fresh_parcels)
        finally:
            self._is_switching_project = False

    def _on_owners_changed(self, owners: list):
        if self._is_switching_project:
            return

        # Utrzymaj jedną kanoniczną listę właścicieli. Dzięki temu statusy TAK/NIE
        # ustawione w Oświadczeniach/Pismach nie znikają po kliknięciu „Zapisz”.
        self.owners_tab.owners = owners
        self.dashboard_tab.set_owners(owners)
        self.stats_tab.set_owners(owners)
        self.kw_tab.set_owners(owners)
        self.decl_tab.set_owners(owners)
        self.cover_tab.set_owners(owners)
        self.envelope_tab.set_owners(owners)
        self.tracker_tab.set_owners(owners)
        self.print_tab.set_owners(owners)
        self.legal_titles_tab.set_owners(owners)
        self.krs_downloader_tab.set_owners(owners)
        self.owners_tab._save_to_project_state()

    def _on_parcels_changed(self, parcels: list):
        if self._is_switching_project:
            return

        self.parcel_sort_tab.set_parcels(parcels)
        self.decl_tab.set_parcels(parcels)
        self.cover_tab.set_parcels(parcels)
        self.legal_titles_tab.set_parcels(parcels)
        self.owners_tab.set_active_parcels(parcels)
        self.extract_pdf_tab.set_global_parcels(parcels)

    def _save_project_global(self):
        self._remember_module_tab_order()
        self.save_configuration()
        self.legal_titles_tab._save_state(silent=True)
        if hasattr(self.decl_tab, '_save_groups'):
            self.decl_tab._save_groups()
        if hasattr(self.cover_tab, '_save_groups'):
            self.cover_tab._save_groups()
        self.owners_tab._save_to_project_state()
        self.parcel_tab._save_to_project_state()

        QMessageBox.information(
            self,
            "Zapis",
            "Projekt, tabele, układ zakładek i ustawienia zostały pomyślnie zapisane.",
        )

    def _toggle_theme(self):
        if self.current_theme == "dark":
            self.current_theme = "light"
            self.btn_theme_toggle.setText("🌙 Noc")
            self._apply_light_stylesheet()
        else:
            self.current_theme = "dark"
            self.btn_theme_toggle.setText("☀️ Dzień")
            self._apply_dark_stylesheet()

        self.config["theme"] = self.current_theme
        self.save_configuration()

    def _toggle_ocr_overlay(self):
        if self.ocr_overlay is not None and self.ocr_overlay.isVisible():
            self.ocr_overlay.close()
            return

        self.ocr_overlay = OcrOverlayWindow()
        self.ocr_overlay.parcel_captured.connect(self._on_ocr_parcel_captured)
        self.ocr_overlay.show()
        self.ocr_overlay.raise_()
        self.ocr_overlay.activateWindow()

    def _on_ocr_parcel_captured(self, parcel_data: dict):
        existing_nums = {parcel["number"] for parcel in self.parcel_tab.parcels}

        if parcel_data["number"] not in existing_nums:
            self.parcel_tab.parcels.append(parcel_data)
            self.parcel_tab._refresh_table()
            self.parcel_tab._save_to_project_state()
            self.statusBar().showMessage(
                f"OCR: Dodano działkę {parcel_data['number']} "
                f"jako {parcel_data['category']}."
            )
        else:
            self.statusBar().showMessage(
                f"OCR: Działka {parcel_data['number']} już istnieje na liście."
            )

    def closeEvent(self, event):
        self._remember_module_tab_order()
        self.save_configuration()

        if self.ocr_overlay is not None:
            self.ocr_overlay.close()

        event.accept()

    def _apply_dark_stylesheet(self):
        dark_stylesheet = """
            QMainWindow, QDialog, QMessageBox {
                background-color: #121212;
                color: #e0e0e0;
            }

            QWidget {
                background-color: #121212;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }

            QLabel, QCheckBox, QRadioButton, QMessageBox QLabel {
                color: #e0e0e0;
                background: transparent;
            }

            QStatusBar {
                background-color: #1e1e1e;
                color: #a0a0a0;
                border-top: 1px solid #333333;
            }

            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1a1a1a;
                border-radius: 6px;
                top: -1px;
            }

            QTabBar::tab {
                background-color: #252525;
                color: #a0a0a0;
                border: 1px solid #333333;
                border-bottom: none;
                padding: 10px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-weight: bold;
            }

            QTabBar::tab:hover {
                background-color: #2e2e2e;
                color: #ffffff;
            }

            QTabBar::tab:selected {
                background-color: #1a1a1a;
                color: #4da6ff;
                border-top: 3px solid #4da6ff;
            }

            QWidget#module_actions_widget {
                background: transparent;
            }

            QWidget#module_navigation {
                background-color: #181818;
                border: 1px solid #333333;
                border-radius: 7px;
            }

            QStackedWidget#module_stack {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 7px;
            }

            QToolButton#module_tab_button {
                background-color: #252525;
                color: #b8b8b8;
                border: 1px solid #383838;
                border-radius: 6px;
                padding: 6px 4px;
                font-weight: bold;
            }

            QToolButton#module_tab_button:hover {
                background-color: #303030;
                color: #ffffff;
                border-color: #4da6ff;
            }

            QToolButton#module_tab_button:checked {
                background-color: #005a9e;
                color: #ffffff;
                border: 1px solid #4da6ff;
            }

            QToolButton#module_tab_button[dropTarget="true"] {
                background-color: #5b3a00;
                color: #ffffff;
                border: 2px solid #ffb900;
            }

            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                color: #ffffff;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #3d3d3d;
                border-color: #4da6ff;
            }

            QPushButton#btn_primary {
                background-color: #0078d7;
                border: 1px solid #005a9e;
                color: white;
            }

            QPushButton#btn_primary:hover { background-color: #0086f0; }

            QPushButton#btn_accent {
                background-color: #d83b01;
                border: 1px solid #ea4000;
                color: white;
            }

            QPushButton#btn_accent:hover { background-color: #f04e13; }

            QPushButton#btn_danger {
                background-color: #c50f1f;
                border: 1px solid #a30b17;
                color: white;
            }

            QPushButton#btn_danger:hover { background-color: #d11324; }

            QPushButton#btn_ocr_corner {
                background-color: #1e1e1e;
                border: 1px solid #4da6ff;
                color: #4da6ff;
                margin: 4px;
            }

            QPushButton#btn_ocr_corner:hover {
                background-color: #4da6ff;
                color: #000000;
            }

            QLineEdit, QTextEdit, QDateEdit, QComboBox,
            QSpinBox, QDoubleSpinBox {
                background-color: #252525;
                border: 1px solid #404040;
                border-radius: 4px;
                color: #ffffff;
                padding: 5px;
            }

            QGroupBox {
                border: 1px solid #404040;
                border-radius: 6px;
                margin-top: 15px;
                padding-top: 12px;
                background-color: #1e1e1e;
                font-weight: bold;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                color: #4da6ff;
            }

            QTableWidget, QTreeWidget, QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                gridline-color: #333333;
                color: #e0e0e0;
            }

            QHeaderView::section {
                background-color: #2d2d2d;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #404040;
                font-weight: bold;
            }

            QScrollArea, QScrollArea > QWidget > QWidget {
                background-color: #121212;
                border: none;
            }

            QTreeView::item:hover,
            QTableWidget::item:hover,
            QListWidget::item:hover {
                background-color: transparent;
            }

            QTreeView::item:selected,
            QCheckBox {
                spacing: 8px;
                color: #e0e0e0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #606060;
                border-radius: 4px;
                background-color: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #4da6ff;
                border-color: #4da6ff;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #606060;
                border-radius: 9px;
                background-color: #2a2a2a;
            }
            QRadioButton::indicator:checked {
                background-color: #4da6ff;
                border-color: #4da6ff;
            }

            QTableWidget::item:selected,
            QListWidget::item:selected {
                background-color: #005a9e;
                color: white;
            }
        """
        self.setStyleSheet(dark_stylesheet)

    def _apply_light_stylesheet(self):
        light_stylesheet = """
            QMainWindow, QDialog, QMessageBox {
                background-color: #f3f3f3;
                color: #202020;
            }

            QWidget {
                background-color: #f3f3f3;
                color: #202020;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }

            QLabel, QCheckBox, QRadioButton, QMessageBox QLabel {
                color: #202020;
                background: transparent;
            }

            QStatusBar {
                background-color: #e1e1e1;
                color: #505050;
                border-top: 1px solid #cccccc;
            }

            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: #ffffff;
                border-radius: 6px;
                top: -1px;
            }

            QTabBar::tab {
                background-color: #e8e8e8;
                color: #505050;
                border: 1px solid #cccccc;
                border-bottom: none;
                padding: 10px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-weight: bold;
            }

            QTabBar::tab:hover {
                background-color: #f8f8f8;
                color: #000000;
            }

            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #005a9e;
                border-top: 3px solid #005a9e;
            }

            QWidget#module_actions_widget {
                background: transparent;
            }

            QWidget#module_navigation {
                background-color: #eeeeee;
                border: 1px solid #cccccc;
                border-radius: 7px;
            }

            QStackedWidget#module_stack {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 7px;
            }

            QToolButton#module_tab_button {
                background-color: #ffffff;
                color: #303030;
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 6px 4px;
                font-weight: bold;
            }

            QToolButton#module_tab_button:hover {
                background-color: #e5f1fb;
                color: #000000;
                border-color: #0078d7;
            }

            QToolButton#module_tab_button:checked {
                background-color: #0078d7;
                color: #ffffff;
                border: 1px solid #005a9e;
            }

            QToolButton#module_tab_button[dropTarget="true"] {
                background-color: #fff4ce;
                color: #202020;
                border: 2px solid #d18b00;
            }

            QPushButton {
                background-color: #fdfdfd;
                border: 1px solid #cccccc;
                color: #202020;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #e5f1fb;
                border-color: #0078d7;
            }

            QPushButton#btn_primary {
                background-color: #0078d7;
                border: 1px solid #005a9e;
                color: white;
            }

            QPushButton#btn_primary:hover { background-color: #006ec6; }

            QPushButton#btn_accent {
                background-color: #d83b01;
                border: 1px solid #c23300;
                color: white;
            }

            QPushButton#btn_accent:hover { background-color: #e94914; }

            QPushButton#btn_danger {
                background-color: #c50f1f;
                border: 1px solid #a30b17;
                color: white;
            }

            QPushButton#btn_danger:hover { background-color: #d11324; }

            QPushButton#btn_ocr_corner {
                background-color: #ffffff;
                border: 1px solid #005a9e;
                color: #005a9e;
                margin: 4px;
            }

            QPushButton#btn_ocr_corner:hover {
                background-color: #005a9e;
                color: white;
            }

            QLineEdit, QTextEdit, QDateEdit, QComboBox,
            QSpinBox, QDoubleSpinBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                border-radius: 4px;
                color: #202020;
                padding: 5px;
            }

            QGroupBox {
                border: 1px solid #cccccc;
                border-radius: 6px;
                margin-top: 15px;
                padding-top: 12px;
                background-color: #fafafa;
                font-weight: bold;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                color: #005a9e;
            }

            QTableWidget, QTreeWidget, QListWidget {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                gridline-color: #e0e0e0;
                color: #202020;
            }

            QHeaderView::section {
                background-color: #f0f0f0;
                color: #202020;
                padding: 5px;
                border: 1px solid #cccccc;
                font-weight: bold;
            }

            QScrollArea, QScrollArea > QWidget > QWidget {
                background-color: #ffffff;
                border: none;
            }

            QTreeView::item:hover,
            QTableWidget::item:hover,
            QListWidget::item:hover {
                background-color: transparent;
            }

            QTreeView::item:selected,
            QTableWidget::item:selected,
            QListWidget::item:selected {
                background-color: #cce4f7;
                color: #000000;
            }
        """
        self.setStyleSheet(light_stylesheet)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
