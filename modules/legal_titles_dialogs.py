"""
legal_titles_dialogs.py – Okna dialogowe i delegaty dla zakładki Tytułów Prawnych
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QDialog, QListWidget, QComboBox, QStyledItemDelegate, QInputDialog
)
from PySide6.QtCore import Qt

class OddzialEditorDialog(QDialog):
    def __init__(self, current_options: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zarządzaj opcjami: Nazwa Oddziału")
        self.setMinimumSize(400, 450)

        layout = QVBoxLayout(self)

        lbl = QLabel("Wprowadź i zarządzaj nazwami oddziałów:")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("font-size: 13px; padding: 5px;")
        self.list_widget.addItems(current_options)
        layout.addWidget(self.list_widget)

        add_layout = QHBoxLayout()
        self.input_new = QLineEdit()
        self.input_new.setPlaceholderText("Wpisz nową nazwę oddziału...")
        self.input_new.setStyleSheet("font-size: 13px; padding: 5px;")
        btn_add = QPushButton("➕ Dodaj")
        btn_add.setStyleSheet("background-color: #2a9d8f; color: white; font-weight: bold; padding: 5px;")
        btn_add.clicked.connect(self._add)
        add_layout.addWidget(self.input_new)
        add_layout.addWidget(btn_add)
        layout.addLayout(add_layout)

        btn_actions = QHBoxLayout()
        btn_edit = QPushButton("✏️ Edytuj zaznaczone")
        btn_edit.setStyleSheet("background-color: #e9c46a; color: black; font-weight: bold; padding: 5px;")
        btn_edit.clicked.connect(self._edit)
        btn_actions.addWidget(btn_edit)

        btn_del = QPushButton("🗑️ Usuń zaznaczone")
        btn_del.setStyleSheet("background-color: #e76f51; color: white; font-weight: bold; padding: 5px;")
        btn_del.clicked.connect(self._del)
        btn_actions.addWidget(btn_del)
        layout.addLayout(btn_actions)

        btn_close = QPushButton("Zakończ i Zapisz")
        btn_close.setStyleSheet("background-color: #264653; color: white; font-weight: bold; padding: 8px;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _add(self):
        text = self.input_new.text().strip()
        if text:
            self.list_widget.addItem(text)
            self.input_new.clear()

    def _edit(self):
        item = self.list_widget.currentItem()
        if not item: return
        text, ok = QInputDialog.getText(self, "Edytuj", "Zmień nazwę:", text=item.text())
        if ok and text.strip():
            item.setText(text.strip())

    def _del(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_options(self):
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]

class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, get_items_callback, parent=None):
        super().__init__(parent)
        self.get_items_callback = get_items_callback

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.setEditable(True)
        items = self.get_items_callback(index.column())
        cb.addItems(items)
        return cb

    def setEditorData(self, editor, index):
        val = index.model().data(index, Qt.ItemDataRole.EditRole)
        if val: editor.setCurrentText(str(val))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)