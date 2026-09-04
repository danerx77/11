"""
project_manager.py – Zakładka zarządzania projektami    Projekty
"""
import json
import os
import shutil
import re

from utils.output_paths import projects_root
from utils.project_naming import (
    DATE_FORMAT_KEY,
    SYMBOL_SEPARATOR_CHOICES,
    SYMBOL_SEPARATOR_KEY,
    DEFAULT_SYMBOL_SEPARATOR,
    PROJECT_FOLDER_DEFAULTS,
    TEMPLATE_KEY as PROJECT_TEMPLATE_KEY,
    TEMPLATE_PRESETS as PROJECT_TEMPLATE_PRESETS,
    build_project_folder_name,
)
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QGroupBox, QSplitter, QFrame,
    QDateEdit, QAbstractItemView, QComboBox
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QIcon, QFont, QShortcut, QKeySequence

PROJECT_SUBFOLDER_STRUCTURE = [
    'lista',
    'wypisy',
    'dokumenty',
    'koperty',
    'przesylki',
]

class NewProjectDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle('Nowy Projekt')
        self.setMinimumWidth(500)
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('np. Przebudowa linii SN Polki')
        layout.addRow('Nazwa projektu:', self.name_edit)

        self.symbol_edit = QLineEdit()
        self.symbol_edit.setPlaceholderText('np. OBI/2026/001')
        layout.addRow('Nr projektu:', self.symbol_edit)

        self.city_edit = QLineEdit()
        self.city_edit.setPlaceholderText('np. Gdańsk')
        layout.addRow('Miejscowość:', self.city_edit)

        self.deadline_edit = QDateEdit()
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setDate(QDate.currentDate().addMonths(3))
        layout.addRow('Termin realizacji:', self.deadline_edit)

        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        
        default_dir = self.config.get('default_project_root', '')
        if not default_dir or not Path(default_dir).exists():
            import sys
            if getattr(sys, 'frozen', False):
                app_dir = str(Path(sys.executable).parent.resolve())
            else:
                app_dir = str(Path(__file__).parent.parent.resolve())
            # Nowe projekty trafiają do podfolderu „Projekty”, a nie do
            # katalogu głównego programu.
            default_dir = str(projects_root(self.config, app_dir, create=True))
        self.folder_edit.setText(default_dir)
        
        btn_browse = QPushButton('📂 Przeglądaj...')
        btn_browse.clicked.connect(self._browse)
        h = QHBoxLayout()
        h.addWidget(self.folder_edit)
        h.addWidget(btn_browse)
        layout.addRow('Folder nadrzędny:', h)

        self.format_combo = QComboBox()
        self.format_combo.setEditable(True)
        # Wzory z Ustawień; pierwszy jest ten wybrany jako domyślny.
        preferred = str(
            self.config.get(
                PROJECT_TEMPLATE_KEY, PROJECT_FOLDER_DEFAULTS[PROJECT_TEMPLATE_KEY]
            )
            or PROJECT_FOLDER_DEFAULTS[PROJECT_TEMPLATE_KEY]
        )
        templates = [preferred]
        for _label, template in PROJECT_TEMPLATE_PRESETS:
            if template not in templates:
                templates.append(template)
        self.format_combo.addItems(templates)
        self.format_combo.setCurrentText(preferred)
        self.format_combo.currentTextChanged.connect(self._update_folder_preview)
        for widget in (self.name_edit, self.symbol_edit, self.city_edit):
            widget.textChanged.connect(self._update_folder_preview)
        self.deadline_edit.dateChanged.connect(self._update_folder_preview)

        help_label = QLabel("Wpisz własny schemat. Zmienne: {nazwa}, {symbol}, {miasto}, {termin}")
        help_label.setObjectName('naming_fields')
        layout.addRow('Format folderu:', self.format_combo)
        layout.addRow('', help_label)

        # Ukośnik w numerze projektu trzeba czymś zastąpić — Windows go nie
        # dopuszcza w nazwie folderu. Wybór jest też w Ustawieniach, ale ma
        # być pod ręką przy zakładaniu projektu.
        self.separator_combo = QComboBox()
        for label, value in SYMBOL_SEPARATOR_CHOICES:
            self.separator_combo.addItem(label, value)
        saved_separator = str(
            self.config.get(SYMBOL_SEPARATOR_KEY, DEFAULT_SYMBOL_SEPARATOR)
        )
        sep_index = self.separator_combo.findData(saved_separator)
        self.separator_combo.setCurrentIndex(sep_index if sep_index >= 0 else 0)
        self.separator_combo.currentIndexChanged.connect(self._update_folder_preview)
        layout.addRow('Ukośnik w numerze zamień na:', self.separator_combo)

        self.lbl_folder_preview = QLabel()
        self.lbl_folder_preview.setObjectName('naming_preview')
        self.lbl_folder_preview.setWordWrap(True)
        layout.addRow('Nazwa folderu:', self.lbl_folder_preview)
        self._update_folder_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _folder_config(self) -> dict:
        """Ustawienia nazwy z uwzględnieniem wyboru zrobionego w tym oknie."""
        config = dict(self.config)
        if hasattr(self, 'separator_combo'):
            config[SYMBOL_SEPARATOR_KEY] = self.separator_combo.currentData()
        return config

    def _current_folder_name(self) -> str:
        return build_project_folder_name(
            self._folder_config(),
            name=self.name_edit.text(),
            symbol=self.symbol_edit.text(),
            city=self.city_edit.text(),
            deadline=self.deadline_edit.date().toString(
                str(
                    self.config.get(
                        DATE_FORMAT_KEY, PROJECT_FOLDER_DEFAULTS[DATE_FORMAT_KEY]
                    )
                )
            ),
            template=self.format_combo.currentText(),
        )

    def _update_folder_preview(self, *_args):
        if not hasattr(self, 'lbl_folder_preview'):
            return
        name = self._current_folder_name()
        self.lbl_folder_preview.setText(name or '(podaj dane projektu)')

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, 'Wybierz folder nadrzędny', self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, 'Błąd', 'Podaj nazwę projektu!')
            return
        if not self.folder_edit.text().strip():
            QMessageBox.warning(self, 'Błąd', 'Wybierz folder nadrzędny!')
            return
        super().accept()

    def get_values(self):
        return {
            'name': self.name_edit.text().strip(),
            'symbol': self.symbol_edit.text().strip(),
            'city': self.city_edit.text().strip(),
            'deadline': self.deadline_edit.date().toString(
                str(
                    self.config.get(
                        DATE_FORMAT_KEY,
                        PROJECT_FOLDER_DEFAULTS[DATE_FORMAT_KEY],
                    )
                )
            ),
            'parent_folder': self.folder_edit.text().strip(),
            'folder_format_text': self.format_combo.currentText(),
            'folder_symbol_separator': self.separator_combo.currentData(),
            'folder_name': self._current_folder_name()
        }


class RenameProjectDialog(QDialog):
    def __init__(self, current_name: str, current_symbol: str, current_city: str, current_deadline: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle('Zmień nazwę / Nr projektu / Termin')
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.name_edit = QLineEdit(current_name)
        layout.addRow('Nowa nazwa projektu:', self.name_edit)

        self.symbol_edit = QLineEdit(current_symbol)
        layout.addRow('Nowy Nr projektu:', self.symbol_edit)
        
        self.city_edit = QLineEdit(current_city)
        layout.addRow('Nowa miejscowość:', self.city_edit)

        self.deadline_edit = QDateEdit()
        self.deadline_edit.setCalendarPopup(True)
        d = QDate.fromString(current_deadline or '', 'dd-MM-yyyy')
        self.deadline_edit.setDate(d if d.isValid() else QDate.currentDate())
        layout.addRow('Nowy termin:', self.deadline_edit)

        info = QLabel('Nazwa folderu po zmianie: Miejscowość NrProjektu Termin')
        info.setStyleSheet('color: gray; font-size: 11px;')
        layout.addRow('', info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, 'Błąd', 'Podaj nazwę projektu!')
            return
        super().accept()

    def get_values(self):
        return (
            self.name_edit.text().strip(),
            self.symbol_edit.text().strip(),
            self.city_edit.text().strip(),
            self.deadline_edit.date().toString('dd-MM-yyyy'),
        )


class ProjectManagerWidget(QWidget):
    project_selected = Signal(dict)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.projects = []
        self.current_project = None
        self._build_ui()
        self._load_projects()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 4, 8)

        header = QLabel('📁 Projekty')
        header.setStyleSheet('font-size:15px; font-weight:700;')
        left_layout.addWidget(header)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton('+ Nowy projekt')
        self.btn_new.setObjectName('btn_primary')
        self.btn_new.clicked.connect(self._new_project)
        btn_row.addWidget(self.btn_new)

        self.btn_open_root = QPushButton('📂 Wyszukaj (folder projektu lub ogólny)')
        self.btn_open_root.clicked.connect(self._open_root_folder)
        btn_row.addWidget(self.btn_open_root)
        left_layout.addLayout(btn_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Projekt', 'Nr projektu', 'Miejscowość', 'Termin'])
        self.tree.setColumnWidth(0, 150)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 100)
        self.tree.setAlternatingRowColors(True)
        # ZMIANA: Zmiana trybu zaznaczania na wielokrotny
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.currentItemChanged.connect(self._on_project_selected)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        QShortcut(QKeySequence("Delete"), self.tree).activated.connect(self._remove_project)
        
        left_layout.addWidget(self.tree)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 8, 8, 8)

        self.detail_box = QGroupBox('Szczegóły projektu')
        detail_form = QFormLayout(self.detail_box)
        detail_form.setSpacing(8)

        self.lbl_name = QLabel('—')
        self.lbl_name.setStyleSheet('font-weight:600; font-size:14px;')
        detail_form.addRow('Nazwa:', self.lbl_name)

        self.lbl_symbol = QLabel('—')
        detail_form.addRow('Nr projektu:', self.lbl_symbol)
        
        self.lbl_city = QLabel('—')
        detail_form.addRow('Miejscowość:', self.lbl_city)

        self.lbl_deadline = QLabel('—')
        detail_form.addRow('Termin:', self.lbl_deadline)

        self.lbl_path = QLabel('—')
        self.lbl_path.setWordWrap(True)
        detail_form.addRow('Ścieżka:', self.lbl_path)

        self.lbl_status = QLabel('—')
        detail_form.addRow('Status:', self.lbl_status)

        right_layout.addWidget(self.detail_box)

        actions_box = QGroupBox('Akcje')
        actions_layout = QVBoxLayout(actions_box)

        self.btn_select = QPushButton('✅ Ustaw jako aktywny projekt')
        self.btn_select.setObjectName('btn_primary')
        self.btn_select.clicked.connect(self._select_project)
        self.btn_select.setEnabled(False)
        actions_layout.addWidget(self.btn_select)

        self.btn_rename = QPushButton('✏️ Zmień nazwę / Nr projektu')
        self.btn_rename.clicked.connect(self._rename_project)
        self.btn_rename.setEnabled(False)
        actions_layout.addWidget(self.btn_rename)

        self.btn_open_folder = QPushButton('📂 Otwórz folder projektu')
        self.btn_open_folder.clicked.connect(self._open_project_folder)
        self.btn_open_folder.setEnabled(False)
        actions_layout.addWidget(self.btn_open_folder)

        self.btn_delete = QPushButton('🗑️ Usuń projekt z listy (Delete)')
        self.btn_delete.setToolTip(
            'Usuwa projekt tylko z listy w programie.\n'
            'Folder z dokumentami zostaje nietknięty na dysku.'
        )
        self.btn_delete.clicked.connect(self._remove_project)
        self.btn_delete.setEnabled(False)
        actions_layout.addWidget(self.btn_delete)

        self.btn_delete_with_files = QPushButton('💣 Usuń projekt z listy i dysku')
        self.btn_delete_with_files.setObjectName('btn_danger')
        self.btn_delete_with_files.setToolTip(
            'Usuwa projekt z listy ORAZ kasuje jego folder wraz z całą\n'
            'zawartością. Tej operacji nie można cofnąć.'
        )
        self.btn_delete_with_files.clicked.connect(self._remove_project_with_files)
        self.btn_delete_with_files.setEnabled(False)
        actions_layout.addWidget(self.btn_delete_with_files)

        right_layout.addWidget(actions_box)
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([350, 300])

    def _load_projects(self):
        self.projects = self.config.get('projects', [])
        self._refresh_tree()

    def _refresh_tree(self):
        self.tree.clear()
        for p in self.projects:
            item = QTreeWidgetItem([
                p.get('name', ''),
                p.get('symbol', ''),
                p.get('city', ''),
                p.get('deadline', ''),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, p)
            if p.get('path') == self.config.get('last_project_path'):
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setForeground(0, Qt.GlobalColor.green)
            self.tree.addTopLevelItem(item)

    def _on_project_selected(self, current, _previous):
        if not current: return
        p = current.data(0, Qt.ItemDataRole.UserRole)
        self.current_project = p
        self.lbl_name.setText(p.get('name', '—'))
        self.lbl_symbol.setText(p.get('symbol', '—'))
        self.lbl_city.setText(p.get('city', '—'))
        self.lbl_deadline.setText(p.get('deadline', '—'))
        self.lbl_path.setText(p.get('path', '—'))

        path = Path(p.get('path', ''))
        if path.exists(): self.lbl_status.setText('✅ Folder istnieje')
        else: self.lbl_status.setText('⚠️ Folder nie istnieje')

        for btn in [self.btn_select, self.btn_rename, self.btn_open_folder,
                    self.btn_delete, self.btn_delete_with_files]:
            btn.setEnabled(True)

    def _on_item_clicked(self, item, column):
        if self.config.get('single_click_activation', False):
            self._select_project(silent=True)

    def _on_item_double_clicked(self, item, column):
        if not self.config.get('single_click_activation', False):
            self._select_project(silent=True)

    def _new_project(self):
        dlg = NewProjectDialog(self.config, self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        vals = dlg.get_values()

        # Nazwa folderu jest dokładnie taka, jaką pokazał podgląd w oknie.
        folder_name = vals.get('folder_name') or build_project_folder_name(
            {**self.config,
             SYMBOL_SEPARATOR_KEY: vals.get(
                 'folder_symbol_separator', DEFAULT_SYMBOL_SEPARATOR
             )},
            name=vals['name'],
            symbol=vals['symbol'],
            city=vals['city'],
            deadline=vals['deadline'],
            template=vals['folder_format_text'],
        )
        
        project_path = Path(vals['parent_folder']) / folder_name

        try:
            project_path.mkdir(parents=True, exist_ok=True)
            for subfolder in PROJECT_SUBFOLDER_STRUCTURE:
                (project_path / subfolder).mkdir(exist_ok=True)
                
            meta = {
                'name': vals['name'],
                'symbol': vals['symbol'],
                'city': vals['city'],
                'deadline': vals['deadline'],
                'created': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            with open(project_path / 'project_meta.json', 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=4)
                
        except Exception as e:
            QMessageBox.critical(self, 'Błąd', f'Nie można utworzyć folderu:\n{e}')
            return

        project = {
            'name': vals['name'],
            'symbol': vals['symbol'],
            'city': vals['city'],
            'deadline': vals['deadline'],
            'path': str(project_path),
            'created': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        self.projects.append(project)
        self.config['projects'] = self.projects
        self._refresh_tree()
        
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            p_data = item.data(0, Qt.ItemDataRole.UserRole)
            if p_data and p_data.get('path') == project['path']:
                self.tree.setCurrentItem(item)
                break
                
        self._select_project(silent=True)
        QMessageBox.information(self, 'Projekt utworzony', f'Utworzono i ustawiono jako AKTYWNY:\n{project_path}')

    def _remove_dir_retry(self, path: Path) -> bool:
        """Usuwa katalog wraz z zawartością, z ponowieniami.

        Windows potrafi chwilowo trzymać uchwyty (Explorer, antywirus),
        dlatego próbujemy kilka razy i wymuszamy uprawnienia zapisu.
        """
        import stat
        import time

        def onerror(func, p, exc_info):
            try:
                os.chmod(p, stat.S_IWRITE)
                func(p)
            except Exception:
                pass

        if not path.exists():
            return True

        for _ in range(5):
            try:
                shutil.rmtree(path, onerror=onerror)
                return not path.exists()
            except FileNotFoundError:
                return True
            except Exception:
                time.sleep(0.4)

        # Ostatnia deska ratunku: zmień nazwę i usuń.
        trash = path.with_name(path.name + '_DO_USUNIECIA')
        try:
            if trash.exists():
                shutil.rmtree(trash, onerror=onerror)
            path.rename(trash)
            for _ in range(5):
                try:
                    shutil.rmtree(trash, onerror=onerror)
                    return not trash.exists()
                except Exception:
                    time.sleep(0.4)
        except Exception:
            pass

        return not path.exists()


    def _move_project_folder(self, old_path: Path, new_path: Path) -> Path:
        """Zmienia nazwę folderu projektu (atomowe przeniesienie, bez kopiowania).

        Dzięki temu stary folder po prostu znika – nie powstaje drugi folder.
        """
        import time

        if not old_path.exists():
            return new_path

        old_norm = os.path.normcase(str(old_path))
        new_norm = os.path.normcase(str(new_path))

        if old_norm == new_norm:
            # Zmiana tylko wielkości liter – przejdź przez folder tymczasowy.
            tmp_path = old_path.parent / f".__tmp_rename_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            old_path.rename(tmp_path)
            try:
                tmp_path.rename(new_path)
            except Exception:
                try:
                    tmp_path.rename(old_path)
                except Exception:
                    pass
                raise
            return new_path

        if new_path.exists():
            try:
                if os.path.samefile(old_path, new_path):
                    return new_path
            except OSError:
                pass
            raise FileExistsError(f'Folder docelowy już istnieje: {new_path}')

        # Atomowe przeniesienie z ponowieniami (transient lock w Windows).
        last_err = None
        for _ in range(5):
            try:
                old_path.rename(new_path)
                return new_path
            except OSError as e:
                last_err = e
                time.sleep(0.3)

        raise OSError(
            'Nie udało się zmienić nazwy folderu. Sprawdź, czy folder nie jest '
            f'otwarty w Eksploratorze Windows lub nie używa go inny program.\n{last_err}'
        )

    def _rename_project(self):
        if not self.current_project: return
        dlg = RenameProjectDialog(
            self.current_project.get('name', ''),
            self.current_project.get('symbol', ''),
            self.current_project.get('city', ''),
            self.current_project.get('deadline', ''),
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        new_name, new_symbol, new_city, new_deadline = dlg.get_values()

        old_path = Path(self.current_project.get('path', '')).resolve()
        folder_symbol = new_symbol.replace('/', '.').replace('\\', '.')
        new_folder_name = " ".join(x for x in [new_city, folder_symbol, new_deadline] if x).strip()
        new_folder_name = re.sub(r'[\\/*?:"<>|]', '_', new_folder_name).strip()

        try:
            if new_folder_name and old_path.name != new_folder_name:
                new_path = (old_path.parent / new_folder_name).resolve()
                final_path = self._move_project_folder(old_path, new_path)
            else:
                final_path = old_path
        except FileExistsError as e:
            QMessageBox.critical(self, 'Folder już istnieje', str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, 'Błąd', f'Nie można zmienić nazwy folderu projektu:\n{e}')
            return

        old_path_str = str(old_path)
        final_path_str = str(final_path)

        # Zaktualizuj metadane projektu w (nowym) folderze.
        try:
            meta_file = final_path / 'project_meta.json'
            meta = {}
            if meta_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                except Exception:
                    meta = {}
            meta.update({'name': new_name, 'symbol': new_symbol, 'city': new_city, 'deadline': new_deadline})
            meta_file.parent.mkdir(parents=True, exist_ok=True)
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.critical(self, 'Błąd', f'Folder zmieniono, ale nie udało się zapisać metadanych:\n{e}')
            return

        self.current_project.update({
            'name': new_name,
            'symbol': new_symbol,
            'city': new_city,
            'deadline': new_deadline,
            'path': final_path_str,
        })
        if self.config.get('last_project_path') in (old_path_str, str(Path(old_path_str))):
            self.config['last_project_path'] = final_path_str
        self.config['last_project_symbol'] = new_symbol

        # Usuń stare lub zdublowane wpisy z listy, zostaw jeden bieżący projekt.
        cleaned = []
        for project in self.projects:
            pth = str(Path(project.get('path', '')).resolve()) if project.get('path') else ''
            if project is self.current_project:
                if self.current_project not in cleaned:
                    cleaned.append(self.current_project)
            elif pth in (old_path_str, final_path_str):
                continue
            else:
                cleaned.append(project)
        if self.current_project not in cleaned:
            cleaned.append(self.current_project)
        self.projects = cleaned
        self.config['projects'] = self.projects

        self._refresh_tree()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            p_data = item.data(0, Qt.ItemDataRole.UserRole)
            if p_data and str(Path(p_data.get('path', '')).resolve()) == final_path_str:
                self.tree.setCurrentItem(item)
                self._on_project_selected(item, None)
                break
        self.project_selected.emit(self.current_project)

        # Po zmianie projektu wszystkie zakładki znają już nową ścieżkę.
        # Dopiero teraz usuń ewentualne pozostałości starego folderu (np. gdyby
        # jakiś moduł zdążył zapisać plik stanu do starej ścieżki).
        self._schedule_old_folder_cleanup(old_path, final_path)

        QMessageBox.information(self, 'Zmieniono projekt', f'Zmieniono nazwę folderu projektu na:\n{final_path}')

    def _schedule_old_folder_cleanup(self, old_path: Path, final_path: Path):
        """Usuwa stary folder projektu (także odroczono, gdyby został odtworzony)."""
        if str(old_path) == str(final_path):
            return

        def cleanup():
            removed = self._remove_dir_retry(old_path)
            if not removed:
                QMessageBox.warning(
                    self,
                    'Stary folder pozostał',
                    f'Projekt używa już nowego folderu:\n{final_path}\n\n'
                    f'Nie udało się automatycznie usunąć starego folderu:\n{old_path}\n\n'
                    'Zamknij programy korzystające z tego folderu i usuń go ręcznie.',
                )

        # Spróbuj natychmiast, a potem jeszcze dwukrotnie z opóźnieniem –
        # na wypadek, gdyby system Windows chwilowo trzymał uchwyty.
        cleanup()
        QTimer.singleShot(1500, cleanup)
        QTimer.singleShot(4000, cleanup)

    def _select_project(self, silent=False):
        if not self.current_project: return
        self.config['last_project_path'] = self.current_project['path']
        self._refresh_tree()
        self.project_selected.emit(self.current_project)
        if not silent: QMessageBox.information(self, 'Aktywny projekt', f"Aktywny projekt: {self.current_project['name']}")

    def _open_project_folder(self):
        if not self.current_project: return
        path = self.current_project.get('path', '')
        if path and Path(path).exists(): os.startfile(path)

    def _open_root_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Wybierz folder (pojedynczy projekt lub folder główny)')
        if not folder: return
        root = Path(folder)
        found = 0
        existing_paths = [Path(p['path']).resolve() for p in self.projects if p.get('path') and Path(p['path']).exists()]
        
        def add_project_from_folder(proj_dir):
            if proj_dir.resolve() in existing_paths: return False
            
            meta_file = proj_dir / 'project_meta.json'
            if meta_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    self.projects.append({
                        'name': meta.get('name', proj_dir.name),
                        'symbol': meta.get('symbol', ''),
                        'city': meta.get('city', ''),
                        'deadline': meta.get('deadline', ''),
                        'path': str(proj_dir.resolve()),
                        'created': meta.get('created', '')
                    })
                    return True
                except: pass

            name = proj_dir.name
            symbol = ''
            if '[' in name and name.endswith(']'):
                idx = name.rfind('[')
                symbol = name[idx+1:-1]
                name = name[:idx].strip()
            if name.startswith('P.'): name = name[2:].strip()
            
            self.projects.append({'name': name, 'symbol': symbol, 'deadline': '', 'city': '', 'path': str(proj_dir.resolve()), 'created': ''})
            return True

        if (root / 'project_meta.json').exists() or (root / 'wypisy').exists() or (root / 'lista').exists():
            if add_project_from_folder(root):
                found += 1
        else:
            for subfolder in root.iterdir():
                if subfolder.is_dir():
                    if (subfolder / 'project_meta.json').exists() or (subfolder / 'wypisy').exists() or (subfolder / 'lista').exists():
                        if add_project_from_folder(subfolder):
                            found += 1
                        
        self.config['projects'] = self.projects
        self._refresh_tree()
        if found: QMessageBox.information(self, 'Znaleziono projekty', f'Dodano {found} nowych projektów do listy.')
        else: QMessageBox.information(self, 'Brak projektów', 'Nie znaleziono nowych projektów w tym folderze (lub już są na liście).')

    def _remove_project(self):
        selected_items = self.tree.selectedItems()
        if not selected_items: return
        
        # ZMIANA: Usuwanie wielu zaznaczonych projektów
        msg = (f"Usunąć zaznaczone projekty ({len(selected_items)}) z listy?\n"
               "Foldery i pliki na dysku pozostaną nietknięte.\n"
               "Aby skasować także pliki, użyj przycisku „Usuń projekt z listy i dysku”.")
        reply = QMessageBox.question(self, 'Usuń projekt(y)', msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            for item in selected_items:
                p = item.data(0, Qt.ItemDataRole.UserRole)
                if p in self.projects:
                    self.projects.remove(p)
                    
            self.current_project = None
            self.config['projects'] = self.projects
            self._refresh_tree()

    def _remove_project_with_files(self):
        """Usuwa projekty z listy i kasuje ich foldery z dysku."""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return

        entries = []
        for item in selected_items:
            project = item.data(0, Qt.ItemDataRole.UserRole)
            if project is None:
                continue
            raw_path = str(project.get('path', '') or '').strip()
            entries.append((project, Path(raw_path) if raw_path else None))

        if not entries:
            return

        listing = '\n'.join(
            f"• {project.get('name', 'Projekt')} — "
            + (str(folder) if folder else 'brak zapisanej ścieżki')
            for project, folder in entries[:10]
        )
        if len(entries) > 10:
            listing += f"\n… i {len(entries) - 10} kolejnych"

        msg = (
            f'Usunąć zaznaczone projekty ({len(entries)}) z listy '
            'ORAZ skasować ich foldery z dysku?\n\n'
            f'{listing}\n\n'
            'UWAGA: wszystkie pliki w tych folderach zostaną trwale usunięte. '
            'Tej operacji nie można cofnąć.'
        )
        reply = QMessageBox.warning(
            self,
            'Usuń projekt(y) z dysku',
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        removed, failed, missing = [], [], []
        for project, folder in entries:
            name = project.get('name', 'Projekt')
            if folder is None:
                missing.append(name)
            elif not folder.exists():
                missing.append(name)
            elif self._remove_dir_retry(folder):
                removed.append(name)
            else:
                failed.append(f'{name} ({folder})')

            if project in self.projects:
                self.projects.remove(project)

        self.current_project = None
        self.config['projects'] = self.projects
        self._refresh_tree()

        report = [f'Usunięto z listy: {len(entries)}.']
        if removed:
            report.append(f'Skasowano foldery: {len(removed)}.')
        if missing:
            report.append(
                'Folder nie istniał (usunięto tylko wpis): ' + ', '.join(missing) + '.'
            )
        if failed:
            report.append(
                'NIE udało się skasować folderu (plik może być otwarty): '
                + ', '.join(failed) + '.'
            )

        if failed:
            QMessageBox.warning(self, 'Usuwanie zakończone', '\n'.join(report))
        else:
            QMessageBox.information(self, 'Usuwanie zakończone', '\n'.join(report))