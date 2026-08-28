"""
ocr_overlay.py – Półprzezroczyste okno do przechwytywania tekstu z ekranu i OCR
"""
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QMessageBox, QFrame, QSizePolicy, QGraphicsDropShadowEffect, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QTimer, QThread
from PySide6.QtGui import QPainter, QColor, QPen, QCursor

from utils.ocr_utils import ocr_screen_region, parse_ocr_land_data

class OcrWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, x, y, w, h):
        super().__init__()
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def run(self):
        try:
            time.sleep(0.1)
            raw_text = ocr_screen_region(self.x, self.y, self.w, self.h)
            parsed_data = parse_ocr_land_data(raw_text)
            self.finished.emit(parsed_data)
        except Exception as e:
            self.error.emit(str(e))

class OcrOverlayWindow(QWidget):
    parcel_captured = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('OCR Snip Tool')
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(400, 250)
        self.resize(550, 350)

        self.setMouseTracking(True)
        self.drag_position = QPoint()
        
        self.resizing_edge = None
        self.edge_margin = 10
        self.worker = None

        self._build_ui()
        self.capture_area.setMouseTracking(True)
        self.control_panel.setMouseTracking(True)

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.capture_area = QFrame()
        self.capture_area.setObjectName("capture_area")
        self.capture_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.main_layout.addWidget(self.capture_area)

        self.control_panel = QFrame()
        self.control_panel.setObjectName("control_panel")
        self.control_panel.setStyleSheet("""
            QFrame#control_panel {
                background-color: #1e1e1e;
                border-top: 2px solid #00b4d8;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QLabel { color: #ffffff; font-size: 11px; }
            QLineEdit {
                background-color: #2b2b2b; border: 1px solid #444;
                color: #fff; padding: 4px; border-radius: 4px;
                font-weight: bold; font-size: 12px;
            }
            QPushButton {
                background-color: #3a3a3a; color: white; border: none;
                padding: 6px 12px; border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton#btn_snap { background-color: #00b4d8; color: black; font-size: 13px; }
            QPushButton#btn_snap:hover { background-color: #0096b4; }
            QPushButton#btn_close { background-color: #ff5555; color: white; }
            QPushButton#btn_close:hover { background-color: #ff3333; }
            QPushButton#btn_clear { background-color: #6c757d; color: white; }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, -3)
        self.control_panel.setGraphicsEffect(shadow)

        panel_layout = QVBoxLayout(self.control_panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)

        row1 = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.hide()
        row1.addWidget(self.progress_bar, 1)
        
        self.lbl_drag_info = QLabel("⚙️ Ustaw ramkę nad tekstem i naciśnij [Spacja]")
        self.lbl_drag_info.setStyleSheet("color: #aaa; font-style: italic;")
        row1.addWidget(self.lbl_drag_info, 2)
        
        self.btn_snap = QPushButton("📸 Przechwyć tekst [Spacja]")
        self.btn_snap.setObjectName("btn_snap")
        self.btn_snap.clicked.connect(self._snap_and_ocr)
        row1.addWidget(self.btn_snap)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("btn_close")
        self.btn_close.setFixedWidth(30)
        self.btn_close.clicked.connect(self.close)
        row1.addWidget(self.btn_close)
        panel_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Działka:"))
        self.edit_parcel = QLineEdit()
        row2.addWidget(self.edit_parcel, 2)
        row2.addWidget(QLabel("Obręb:"))
        self.edit_precinct = QLineEdit()
        row2.addWidget(self.edit_precinct, 3)
        
        self.btn_clear = QPushButton("Wyczyść")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.clicked.connect(self._clear_fields)
        row2.addWidget(self.btn_clear)
        panel_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Zapisz jako:"))
        row3.addStretch()

        self.btn_add_demolition = QPushButton("+ Demontaż")
        self.btn_add_demolition.setStyleSheet("background-color: #e74c3c; color: white;")
        # UWAGA: Usunięto lambda ze self.sender(). Używamy referencji do tego konkretnego przycisku.
        self.btn_add_demolition.clicked.connect(lambda: self._add_parcel_to_list("Demontaż", self.btn_add_demolition))
        row3.addWidget(self.btn_add_demolition)

        self.btn_add_construction = QPushButton("+ Budowa")
        self.btn_add_construction.setStyleSheet("background-color: #2ecc71; color: black;")
        self.btn_add_construction.clicked.connect(lambda: self._add_parcel_to_list("Budowa", self.btn_add_construction))
        row3.addWidget(self.btn_add_construction)
        
        self.btn_add_connection = QPushButton("+ Przyłącze")
        self.btn_add_connection.setStyleSheet("background-color: #f1c40f; color: black;")
        self.btn_add_connection.clicked.connect(lambda: self._add_parcel_to_list("Przyłącze", self.btn_add_connection))
        row3.addWidget(self.btn_add_connection)

        panel_layout.addLayout(row3)
        self.main_layout.addWidget(self.control_panel)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect_total = self.rect()
        rect_panel = self.control_panel.geometry()
        
        capture_rect = QRect(
            0, 0, 
            rect_total.width(), 
            rect_total.height() - rect_panel.height()
        )
        
        border_pen = QPen(QColor('#00b4d8'), 4, Qt.PenStyle.SolidLine)
        painter.setPen(border_pen)
        painter.drawRect(capture_rect.adjusted(2, 2, -2, -2))

        mask_color = QColor(0, 0, 0, 10)
        painter.fillRect(capture_rect, mask_color)

    def _get_edge_under_mouse(self, pos):
        rect = self.rect()
        x, y = pos.x(), pos.y()
        w, h = rect.width(), rect.height()
        m = self.edge_margin
        
        edge = ""
        if y < m: edge += "top"
        elif y > h - m: edge += "bottom"
        
        if x < m: edge += "left"
        elif x > w - m: edge += "right"
        
        return edge

    def _update_cursor_shape(self, edge):
        if edge in ["topleft", "bottomright"]: self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif edge in ["topright", "bottomleft"]: self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif edge in ["left", "right"]: self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif edge in ["top", "bottom"]: self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        else: self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.resizing_edge = self._get_edge_under_mouse(event.position().toPoint())
            if not self.resizing_edge:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        global_pos = event.globalPosition().toPoint()

        if not self.resizing_edge and event.buttons() == Qt.MouseButton.NoButton:
            edge = self._get_edge_under_mouse(pos)
            self._update_cursor_shape(edge)

        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.resizing_edge:
                geom = self.geometry()
                x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
                
                if "left" in self.resizing_edge:
                    diff = global_pos.x() - x
                    if w - diff >= self.minimumWidth():
                        x += diff
                        w -= diff
                if "right" in self.resizing_edge:
                    w = max(self.minimumWidth(), global_pos.x() - x)
                if "top" in self.resizing_edge:
                    diff = global_pos.y() - y
                    if h - diff >= self.minimumHeight():
                        y += diff
                        h -= diff
                if "bottom" in self.resizing_edge:
                    h = max(self.minimumHeight(), global_pos.y() - y)

                self.setGeometry(x, y, w, h)
            else:
                self.move(global_pos - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.resizing_edge = None
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space or event.key() == Qt.Key.Key_Return:
            self._snap_and_ocr()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _clear_fields(self):
        self.edit_parcel.clear()
        self.edit_precinct.clear()

    def _snap_and_ocr(self):
        if self.worker and self.worker.isRunning(): return
            
        geom = self.geometry()
        panel_height = self.control_panel.height()
        
        self.x_cap = geom.x() + 2
        self.y_cap = geom.y() + 2
        self.w_cap = geom.width() - 4
        self.h_cap = geom.height() - panel_height - 4

        self.btn_snap.setEnabled(False)
        self.lbl_drag_info.hide()
        self.progress_bar.show()
        
        self.worker = OcrWorker(self.x_cap, self.y_cap, self.w_cap, self.h_cap)
        self.worker.finished.connect(self._on_ocr_finished)
        self.worker.error.connect(self._on_ocr_error)
        self.worker.start()

    def _on_ocr_finished(self, parsed_data):
        self.progress_bar.hide()
        self.lbl_drag_info.show()
        self.btn_snap.setEnabled(True)
        
        self.edit_parcel.setText(parsed_data.get('parcel', ''))
        self.edit_precinct.setText(parsed_data.get('precinct', ''))

    def _on_ocr_error(self, err_msg):
        self.progress_bar.hide()
        self.lbl_drag_info.show()
        self.btn_snap.setEnabled(True)
        QMessageBox.critical(self, "Błąd OCR", f"Wystąpił błąd podczas OCR:\n{err_msg}")

    def _add_parcel_to_list(self, category: str, button_widget):
        number = self.edit_parcel.text().strip()
        precinct = self.edit_precinct.text().strip()
        
        if not number:
            QMessageBox.warning(self, "Błąd", "Najpierw odczytaj/wpisz numer działki.")
            return

        parcel_data = {
            'number': number,
            'precinct': precinct,
            'category': category
        }
        
        self.parcel_captured.emit(parcel_data)
        
        # Oznacz przycisk na krótko, by dać znać że zarejestrowano kliknięcie
        old_text = button_widget.text()
        button_widget.setText("✓ Zapisano")
        QTimer.singleShot(1000, lambda: button_widget.setText(old_text))