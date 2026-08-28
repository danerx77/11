"""
settings_tab.py – Zakładka ustawień aplikacji Pysilde 6.

Obsługuje również wybór wyglądu głównej nawigacji:
- modern: dwa rzędy przeciąganych zakładek,
- classic: pierwotny QTabWidget.
"""

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.parent.resolve()


DECL_TAGS = [
    ("owner_name", "Imię i nazwisko właściciela", "<Imie Nazwisko>"),
    ("nip", "NIP", "<Nip>"),
    ("pesel", "PESEL", "<Pesel>"),
    ("voivodeship", "Województwo", "<Województwo:>"),
    ("county", "Powiat", "<Powiat:>"),
    ("municipality", "Jednostka ewidencyjna (gmina)", "<Jednostka ewidencyjna:>"),
    ("location", "Miejscowość działki", "<Miejscowość działki:>"),
    ("address_street", "Ulica", "<Ulica>"),
    ("parcel_numbers_budowa", "Działki budowa", "<działki budowa:>"),
    ("parcel_numbers_demontaz", "Działki demontaż", "<działki demontaż:>"),
    ("area_ha", "Powierzchnia [ha]", "<Powierzchnia [ha]>"),
    ("area_ha_budowa", "Pow. Budowa [ha]", "<Powierzchnia Budowa>"),
    ("area_ha_demontaz", "Pow. Demontaż [ha]", "<Powierzchnia Demontaż>"),
    ("kw_numbers_budowa", "Nr KW Budowa", "<KW Budowa>"),
    ("kw_numbers_demontaz", "Nr KW Demontaż", "<KW Demontaż>"),
    ("parcel_numbers", "Działki Wszystkie", "<działki wszystkie>"),
    ("kw_numbers", "Nr KW", "<<Nr KW>>"),
    (
        "device_description",
        "Postać urządzenia (wybór/opis)",
        "<wybór przykładów lub wpisać ręcznie>",
    ),
    ("place", "Miejscowość złożenia (podpis)", "<Miejscowość>"),
    ("date", "Data", "<Data>"),
    ("precinct", "Obręb ewidencyjny", "<Obręb ewidencyjny: wielka litery>"),
]


COVER_TAGS = [
    ("location", "Miejscowość działki", "<Miejscowość działki>"),
    ("street", "Ulica działki z wypisu", "<Ulica>"),
    ("subject", "Temat", "<Temat>"),
    ("task_construction", "Zadanie budowa", "<Zadanie budowa>"),
    ("task_demolition", "Zadanie demontaż", "<Zadanie demontaż>"),
    (
        "parcel_numbers_construction",
        "Działki budowa",
        "<działki budowa>",
    ),
    (
        "parcel_numbers_demolition",
        "Działki demontaż",
        "<działki demontaż>",
    ),
    ("parcel_type", "Odmiana działki", "<odmiana działki>"),
    ("parcel_numbers", "Numer działki (pismo)", "<Numer działki>"),
    (
        "ownership_phrase",
        "Wybór tekstu do kogo",
        "<wybór tekstu do kogo jest skierowany>",
    ),
    ("sender_name", "Imię Nazwisko nadawcy", "<Imię Nazwisko nadawcy>"),
    ("sender_street", "Ulica nadawca", "<ul. nadawca>"),
    (
        "sender_city",
        "Kod pocz., Miejscowość nad.",
        "<kod pocztowy Miejscowość nadawcy>",
    ),
    ("place", "Miejscowość druku", "<Miejscowość druku>"),
    ("date", "Data sporządzenia", "<data sporządzenia>"),
    ("addressee_name", "Imię Nazwisko adresat", "<Imię Nazwisko adresat>"),
    ("addressee_street", "Ulica adresat", "<ul. adresat>"),
    (
        "addressee_city",
        "Kod pocz., Miejscowość adr.",
        "<kod pocztowy Miejscowość adresat>",
    ),
]


class SettingsTabWidget(QWidget):
    def __init__(
        self,
        config: dict,
        save_callback: Callable,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.save_callback = save_callback
        self._build_ui()
        self._load_values()

    def _make_browse_row(
        self,
        line_edit: QLineEdit,
        browse_func: Callable,
    ) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)

        button = QPushButton("📂")
        button.setFixedWidth(40)
        button.clicked.connect(lambda: browse_func(line_edit))
        layout.addWidget(button)
        return widget

    def _browse_docx_template(self, line_edit: QLineEdit):
        start_dir = line_edit.text().strip()
        if start_dir and Path(start_dir).is_file():
            start_dir = str(Path(start_dir).parent)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz szablon Word",
            start_dir,
            "Word (*.docx)",
        )
        if path:
            line_edit.setText(path)

    def _browse_excel_template(self, line_edit: QLineEdit):
        start_dir = line_edit.text().strip()
        if start_dir and Path(start_dir).is_file():
            start_dir = str(Path(start_dir).parent)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz szablon Excel",
            start_dir,
            "Excel (*.xlsx *.xlsm)",
        )
        if path:
            line_edit.setText(path)

    def _browse_pdf_template(self, line_edit: QLineEdit):
        start_dir = line_edit.text().strip()
        if start_dir and Path(start_dir).is_file():
            start_dir = str(Path(start_dir).parent)

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik PDF",
            start_dir,
            "PDF (*.pdf)",
        )
        if path:
            line_edit.setText(path)

    def _browse_folder(self, line_edit: QLineEdit):
        start_dir = line_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(
            self,
            "Wybierz folder",
            start_dir,
        )
        if folder:
            line_edit.setText(folder)

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        inner = QWidget()
        main_layout = QVBoxLayout(inner)
        main_layout.setSpacing(12)

        header = QLabel("⚙️ Ustawienia Aplikacji")
        header.setStyleSheet("font-size: 16px; font-weight: 700;")
        main_layout.addWidget(header)

        # WYGLĄD GŁÓWNYCH ZAKŁADEK
        appearance_box = QGroupBox("Wygląd zakładek modułów")
        appearance_form = QFormLayout(appearance_box)

        self.tab_layout_combo = QComboBox()
        self.tab_layout_combo.addItem(
            "Nowy – dwa rzędy zakładek z przeciąganiem",
            "modern",
        )
        self.tab_layout_combo.addItem(
            "Klasyczny – pierwotny pasek zakładek",
            "classic",
        )
        appearance_form.addRow(
            "Sposób wyświetlania modułów:",
            self.tab_layout_combo,
        )

        appearance_note = QLabel(
            "Zmiana wyglądu zostanie zastosowana po ponownym uruchomieniu "
            "aplikacji. Każdy wygląd zachowuje własną kolejność zakładek."
        )
        appearance_note.setWordWrap(True)
        appearance_note.setStyleSheet("color: #888888; font-style: italic;")
        appearance_form.addRow("", appearance_note)
        main_layout.addWidget(appearance_box)

        browser_box = QGroupBox("Domyślna przeglądarka dla KW/KRS")
        browser_form = QFormLayout(browser_box)
        self.default_browser_combo = QComboBox()
        self.default_browser_combo.addItem("Domyślna z programu", "auto")
        self.default_browser_combo.addItem("Chrome", "chrome")
        self.default_browser_combo.addItem("Edge", "msedge")
        self.default_browser_combo.addItem("Opera", "opera")
        self.default_browser_combo.addItem("Firefox", "firefox")
        browser_form.addRow("Przeglądarka domyślna:", self.default_browser_combo)
        main_layout.addWidget(browser_box)

        self.single_click_cb = QCheckBox(
            "Aktywuj projekt pojedynczym kliknięciem na liście"
        )
        main_layout.addWidget(self.single_click_cb)

        self.chk_extract_parcel_address = QCheckBox(
            "Zaciągaj ulicę działki z wypisu "
            "(dla Oświadczeń Woli i Tabeli 5)"
        )
        main_layout.addWidget(self.chk_extract_parcel_address)

        self.chk_sort_alpha_default = QCheckBox(
            "Domyślnie sortuj adresatów alfabetycznie "
            "(w Pismach przewodnich, Kopertach)"
        )
        main_layout.addWidget(self.chk_sort_alpha_default)

        # FORMATOWANIE PAR MAŁŻEŃSKICH
        couple_box = QGroupBox(
            "Niezależne formatowanie nazwisk par małżeńskich"
        )
        couple_layout = QFormLayout(couple_box)
        couple_options = [
            "Odmienione / Razem (np. Agata i Eryk Paradowscy)",
            "Osobno (np. Agata Paradowska i Eryk Paradowski)",
        ]

        self.couple_fmt_decl = QComboBox()
        self.couple_fmt_decl.addItems(couple_options)
        couple_layout.addRow(
            "W oświadczeniach woli:",
            self.couple_fmt_decl,
        )

        self.couple_fmt_cover = QComboBox()
        self.couple_fmt_cover.addItems(couple_options)
        couple_layout.addRow(
            "W pismach przewodnich:",
            self.couple_fmt_cover,
        )

        self.couple_fmt_env = QComboBox()
        self.couple_fmt_env.addItems(couple_options)
        couple_layout.addRow(
            "Na kopertach i druczkach:",
            self.couple_fmt_env,
        )

        self.couple_fmt_legal = QComboBox()
        self.couple_fmt_legal.addItems(couple_options)
        couple_layout.addRow(
            "W Tytułach Prawnych (Excel):",
            self.couple_fmt_legal,
        )
        main_layout.addWidget(couple_box)

        # NADAWCA
        sender_box = QGroupBox("Dane nadawcy (Twoje / firmy)")
        sender_form = QFormLayout(sender_box)

        self.sender_name_edit = QLineEdit()
        sender_form.addRow("Imię i nazwisko:", self.sender_name_edit)

        self.sender_company_edit = QLineEdit()
        sender_form.addRow("Firma:", self.sender_company_edit)

        self.sender_street_edit = QLineEdit()
        sender_form.addRow("Ulica:", self.sender_street_edit)

        self.sender_city_edit = QLineEdit()
        sender_form.addRow(
            "Kod pocztowy i miasto:",
            self.sender_city_edit,
        )
        main_layout.addWidget(sender_box)

        # GŁÓWNE FOLDERY
        paths_box = QGroupBox(
            "Ścieżki do głównych folderów na zewnątrz programu"
        )
        paths_form = QFormLayout(paths_box)

        self.default_proj_edit = QLineEdit()
        paths_form.addRow(
            "Folder Główny dla NOWYCH projektów:",
            self._make_browse_row(
                self.default_proj_edit,
                self._browse_folder,
            ),
        )

        self.path_przyklady_edit = QLineEdit()
        paths_form.addRow(
            "Folder szablony dokumentów (przykłady):",
            self._make_browse_row(
                self.path_przyklady_edit,
                self._browse_folder,
            ),
        )

        self.path_znaczki_edit = QLineEdit()
        paths_form.addRow(
            "Folder z plikami znaczków (znaczki):",
            self._make_browse_row(
                self.path_znaczki_edit,
                self._browse_folder,
            ),
        )

        self.path_tytuly_edit = QLineEdit()
        paths_form.addRow(
            "Folder szablony (tytuły prawne):",
            self._make_browse_row(
                self.path_tytuly_edit,
                self._browse_folder,
            ),
        )

        button_default_paths = QPushButton(
            "↩ Szukaj domyślnych folderów obok programu"
        )
        button_default_paths.clicked.connect(self._set_default_paths)
        paths_form.addRow("", button_default_paths)

        button_parent_paths = QPushButton(
            "↩ Szukaj domyślnych folderów w folderze nadrzędnym programu"
        )
        button_parent_paths.clicked.connect(self._set_parent_default_paths)
        paths_form.addRow("", button_parent_paths)
        main_layout.addWidget(paths_box)

        # SZABLONY DOCX
        decl_box = QGroupBox("Szablony dokumentów (.docx)")
        decl_form = QFormLayout(decl_box)

        self.chk_unlock_docs = QCheckBox(
            "Odblokuj wygenerowane pliki (usuń ochronę formularza)"
        )
        decl_form.addRow("", self.chk_unlock_docs)

        self.chk_decl_precinct_upper = QCheckBox(
            "Oświadczenia woli: Wymuś WIELKIE LITERY dla nazwy obrębu "
            "(np. POPO)"
        )
        decl_form.addRow("", self.chk_decl_precinct_upper)

        self.chk_decl_location_locative = QCheckBox(
            "Odmieniaj miejscowości działki "
            "(np. Gdynia → Gdyni, Warszawa → Warszawie)"
        )
        decl_form.addRow("", self.chk_decl_location_locative)

        self.chk_decl_streets = QCheckBox(
            "Odmieniaj ulice (np. ulica Miła → ul. Miłej)"
        )
        decl_form.addRow("", self.chk_decl_streets)

        self.chk_decl_powiat = QCheckBox(
            "Zamieniaj miejscowości na właściwe nazwy powiatów "
            "(np. Kościerzyna → kościerski, Wejherowo → wejherowski)"
        )
        decl_form.addRow("", self.chk_decl_powiat)

        self.decl_budowa_edit = QLineEdit()
        decl_form.addRow(
            "Oświadczenie BUDOWA:",
            self._make_browse_row(
                self.decl_budowa_edit,
                self._browse_docx_template,
            ),
        )

        self.decl_demontaz_edit = QLineEdit()
        decl_form.addRow(
            "Oświadczenie DEMONTAŻ:",
            self._make_browse_row(
                self.decl_demontaz_edit,
                self._browse_docx_template,
            ),
        )

        self.cover_letter_edit = QLineEdit()
        decl_form.addRow(
            "Pismo Przewodnie:",
            self._make_browse_row(
                self.cover_letter_edit,
                self._browse_docx_template,
            ),
        )

        self.env_c5_edit = QLineEdit()
        decl_form.addRow(
            "Koperta C5:",
            self._make_browse_row(
                self.env_c5_edit,
                self._browse_docx_template,
            ),
        )

        self.env_c6_edit = QLineEdit()
        decl_form.addRow(
            "Koperta C6:",
            self._make_browse_row(
                self.env_c6_edit,
                self._browse_docx_template,
            ),
        )

        button_default_decl = QPushButton(
            "↩ Automatycznie wczytaj szablony z folderu Przykłady"
        )
        button_default_decl.clicked.connect(
            self._set_default_decl_templates
        )
        decl_form.addRow("", button_default_decl)
        main_layout.addWidget(decl_box)

        # USTAWIENIA WYCINANIA ZNACZKÓW
        crop_box = QGroupBox(
            "Ustawienia wycinania znaczków C5 i C6 (Globalne)"
        )
        crop_layout = QHBoxLayout(crop_box)

        c5_crop_layout = QFormLayout()
        self.c5_crop_l = QSpinBox()
        self.c5_crop_l.setRange(0, 300)
        self.c5_crop_r = QSpinBox()
        self.c5_crop_r.setRange(0, 300)
        self.c5_crop_t = QSpinBox()
        self.c5_crop_t.setRange(-50, 300)
        self.c5_crop_b = QSpinBox()
        self.c5_crop_b.setRange(-50, 300)

        c5_crop_layout.addRow(QLabel("<b>Znaczki C5 (Rozciąganie)</b>"))
        c5_crop_layout.addRow("Lewa [px]:", self.c5_crop_l)
        c5_crop_layout.addRow("Prawa [px]:", self.c5_crop_r)
        c5_crop_layout.addRow("Górna [px]:", self.c5_crop_t)
        c5_crop_layout.addRow("Dolna [px]:", self.c5_crop_b)

        c6_crop_layout = QFormLayout()
        self.c6_crop_l = QSpinBox()
        self.c6_crop_l.setRange(-100, 100)
        self.c6_crop_r = QSpinBox()
        self.c6_crop_r.setRange(-100, 100)
        self.c6_crop_t = QSpinBox()
        self.c6_crop_t.setRange(-100, 100)
        self.c6_crop_b = QSpinBox()
        self.c6_crop_b.setRange(-100, 100)

        c6_crop_layout.addRow(QLabel("<b>Znaczki C6 (Docinanie)</b>"))
        c6_crop_layout.addRow("Lewa [px]:", self.c6_crop_l)
        c6_crop_layout.addRow("Prawa [px]:", self.c6_crop_r)
        c6_crop_layout.addRow("Górna [px]:", self.c6_crop_t)
        c6_crop_layout.addRow("Dolna [px]:", self.c6_crop_b)

        crop_layout.addLayout(c5_crop_layout)
        crop_layout.addLayout(c6_crop_layout)
        main_layout.addWidget(crop_box)

        # SZABLONY EXCEL
        excel_box = QGroupBox(
            "Szablony Tytułów Prawnych (.xlsx / .xlsm)"
        )
        excel_form = QFormLayout(excel_box)

        self.chk_legal_exclude = QCheckBox(
            "Pomiń osoby zmarłe oraz bez pełnego adresu (Tytuły Prawne)"
        )
        excel_form.addRow("", self.chk_legal_exclude)

        self.legal_tmpl_1_edit = QLineEdit()
        excel_form.addRow(
            "Szablon 1 (Działki):",
            self._make_browse_row(
                self.legal_tmpl_1_edit,
                self._browse_excel_template,
            ),
        )

        self.legal_tmpl_2_edit = QLineEdit()
        excel_form.addRow(
            "Szablon 2 (Wykaz właścicieli):",
            self._make_browse_row(
                self.legal_tmpl_2_edit,
                self._browse_excel_template,
            ),
        )

        self.legal_tmpl_3_edit = QLineEdit()
        excel_form.addRow(
            "Szablon 3 (Końcowy):",
            self._make_browse_row(
                self.legal_tmpl_3_edit,
                self._browse_excel_template,
            ),
        )

        self.legal_name_1_edit = QLineEdit()
        excel_form.addRow(
            "Wzór nazwy dla Szablonu 1:",
            self.legal_name_1_edit,
        )

        self.legal_name_2_edit = QLineEdit()
        excel_form.addRow(
            "Wzór nazwy dla Szablonu 2:",
            self.legal_name_2_edit,
        )

        self.legal_name_3_edit = QLineEdit()
        excel_form.addRow(
            "Wzór nazwy dla Szablonu 3:",
            self.legal_name_3_edit,
        )

        self.legal_group_combo = QComboBox()
        self.legal_group_combo.addItems(
            [
                "Każdy właściciel osobno [Opcja 1]",
                "Grupuj współwłaścicieli w 1 wierszu (wg działki) [Opcja 2]",
                "Grupuj działki wg właściciela [Opcja 3]",
                "Grupuj identyczne pakiety działek i współwłaścicieli [Opcja 4]",
                "Grupuj wg działki (Tabela 1, 2 i 5) ze scalaniem "
                "właścicieli w jednej komórce [Opcja 5]",
            ]
        )
        excel_form.addRow(
            "Domyślne grupowanie Tabela 1 i 2:",
            self.legal_group_combo,
        )

        self.t5_street_combo = QComboBox()
        self.t5_street_combo.addItems(
            [
                "Z adresu: sama ulica",
                "Z adresu: ulica + nr domu",
                "Ulica przypisana do działki (z wypisu)",
            ]
        )
        excel_form.addRow(
            "Źródło ulicy dla Tabeli 5 (jeśli zaznaczono w Tytułach):",
            self.t5_street_combo,
        )

        suffix_widget = QWidget()
        suffix_layout = QHBoxLayout(suffix_widget)
        suffix_layout.setContentsMargins(0, 0, 0, 0)

        self.legal_suffix_combo = QComboBox()
        self.legal_suffix_combo.addItems(
            [
                "Pełny numer projektu (np. OBI/123/2026)",
                "Ostatnie X znaków z numeru projektu",
                "Miejscowość (np. Gdańsk)",
            ]
        )
        suffix_layout.addWidget(self.legal_suffix_combo)

        suffix_chars_label = QLabel("Ile znaków (dla opcji 2):")
        suffix_chars_label.setContentsMargins(15, 0, 5, 0)
        suffix_layout.addWidget(suffix_chars_label)

        self.legal_suffix_chars_spin = QSpinBox()
        self.legal_suffix_chars_spin.setRange(1, 20)
        self.legal_suffix_chars_spin.setFixedWidth(80)
        self.legal_suffix_chars_spin.setMinimumHeight(28)
        self.legal_suffix_chars_spin.setStyleSheet(
            "QSpinBox { padding-right: 20px; padding-left: 5px; }"
        )
        suffix_layout.addWidget(self.legal_suffix_chars_spin)
        suffix_layout.addStretch()

        self.legal_suffix_combo.currentIndexChanged.connect(
            lambda index: self.legal_suffix_chars_spin.setEnabled(index == 1)
        )
        excel_form.addRow(
            "Sufiks dla nazw plików Excel:",
            suffix_widget,
        )

        self.legal_odd_edit = QLineEdit()
        self.legal_odd_edit.setPlaceholderText(
            "Oddziel przecinkami, np. Gdańsk, Starogard Gdański"
        )
        excel_form.addRow(
            "Tabela 5 - Opcje Nazwy Oddziału:",
            self.legal_odd_edit,
        )

        button_default_excel = QPushButton(
            "↩ Automatycznie wczytaj szablony z folderu Tytuły Prawne "
            "(zdefiniowanego wyżej)"
        )
        button_default_excel.clicked.connect(
            self._set_default_excel_templates
        )
        excel_form.addRow("", button_default_excel)
        main_layout.addWidget(excel_box)

        # PLIKI PDF
        stamps_box = QGroupBox("Pliki ze znaczkami i druczkami (PDF)")
        stamps_form = QFormLayout(stamps_box)

        self.druczek_tmpl_edit = QLineEdit()
        stamps_form.addRow(
            "Szablon Druczku:",
            self._make_browse_row(
                self.druczek_tmpl_edit,
                self._browse_pdf_template,
            ),
        )

        self.stamp_c5_edit = QLineEdit()
        stamps_form.addRow(
            "Znaczki C5:",
            self._make_browse_row(
                self.stamp_c5_edit,
                self._browse_pdf_template,
            ),
        )

        self.stamp_c6_edit = QLineEdit()
        stamps_form.addRow(
            "Znaczki C6:",
            self._make_browse_row(
                self.stamp_c6_edit,
                self._browse_pdf_template,
            ),
        )

        button_default_pdf = QPushButton(
            "↩ Automatycznie wczytaj pliki z folderu Znaczki"
        )
        button_default_pdf.clicked.connect(
            self._set_default_pdf_templates
        )
        stamps_form.addRow("", button_default_pdf)
        main_layout.addWidget(stamps_box)

        # TAGI OŚWIADCZEŃ
        tags_box = QGroupBox("Tagi: Oświadczenia woli")
        tags_layout = QVBoxLayout(tags_box)
        tags_buttons_layout = QHBoxLayout()

        button_add_tag = QPushButton("+ Dodaj Tag")
        button_add_tag.clicked.connect(
            lambda: self._add_tag_row(self.tags_table)
        )
        tags_buttons_layout.addWidget(button_add_tag)

        button_delete_tag = QPushButton("- Usuń Tag")
        button_delete_tag.clicked.connect(
            lambda: self._del_tag_row(self.tags_table)
        )
        tags_buttons_layout.addWidget(button_delete_tag)
        tags_layout.addLayout(tags_buttons_layout)

        self.tags_table = QTableWidget(0, 3)
        self.tags_table.setMinimumHeight(480)
        self._setup_tags_table(self.tags_table)
        tags_layout.addWidget(self.tags_table)

        button_reset_tags = QPushButton("↩ Przywróć domyślne tagi")
        button_reset_tags.clicked.connect(
            lambda: self._reset_tags(self.tags_table, DECL_TAGS)
        )
        tags_layout.addWidget(button_reset_tags)
        main_layout.addWidget(tags_box)

        # TAGI PISM PRZEWODNICH
        cover_tags_box = QGroupBox("Tagi: Pisma przewodnie")
        cover_tags_layout = QVBoxLayout(cover_tags_box)
        cover_tags_buttons_layout = QHBoxLayout()

        button_add_cover_tag = QPushButton("+ Dodaj Tag")
        button_add_cover_tag.clicked.connect(
            lambda: self._add_tag_row(self.cl_tags_table)
        )
        cover_tags_buttons_layout.addWidget(button_add_cover_tag)

        button_delete_cover_tag = QPushButton("- Usuń Tag")
        button_delete_cover_tag.clicked.connect(
            lambda: self._del_tag_row(self.cl_tags_table)
        )
        cover_tags_buttons_layout.addWidget(button_delete_cover_tag)
        cover_tags_layout.addLayout(cover_tags_buttons_layout)

        self.cl_tags_table = QTableWidget(0, 3)
        self.cl_tags_table.setMinimumHeight(400)
        self._setup_tags_table(self.cl_tags_table)
        cover_tags_layout.addWidget(self.cl_tags_table)

        button_reset_cover_tags = QPushButton(
            "↩ Przywróć domyślne tagi"
        )
        button_reset_cover_tags.clicked.connect(
            lambda: self._reset_tags(self.cl_tags_table, COVER_TAGS)
        )
        cover_tags_layout.addWidget(button_reset_cover_tags)
        main_layout.addWidget(cover_tags_box)

        button_save = QPushButton("💾 Zapisz ustawienia")
        button_save.setObjectName("btn_primary")
        button_save.clicked.connect(self._save)
        main_layout.addWidget(button_save)
        main_layout.addStretch()

        scroll.setWidget(inner)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(6)
        outer_layout.addWidget(scroll, 1)

        # Stały pasek pod obszarem przewijania. Dzięki temu przycisk zapisu
        # jest widoczny niezależnie od aktualnej pozycji przewijania strony.
        floating_save_bar = QWidget()
        floating_save_bar.setObjectName("floating_save_bar")
        floating_save_layout = QHBoxLayout(floating_save_bar)
        floating_save_layout.setContentsMargins(8, 6, 8, 6)

        floating_save_info = QLabel(
            "Po zmianie ustawień kliknij przycisk, aby zapisać konfigurację."
        )
        floating_save_info.setObjectName("floating_save_info")
        floating_save_layout.addWidget(floating_save_info)
        floating_save_layout.addStretch()

        self.button_save_floating = QPushButton("💾 Zapisz ustawienia")
        self.button_save_floating.setObjectName("btn_primary")
        self.button_save_floating.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button_save_floating.setMinimumWidth(210)
        self.button_save_floating.setMinimumHeight(38)
        self.button_save_floating.clicked.connect(self._save)
        floating_save_layout.addWidget(self.button_save_floating)

        outer_layout.addWidget(floating_save_bar, 0)

    def _setup_tags_table(self, table: QTableWidget):
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(
            [
                "Klucz (system)",
                "Opis (pomocniczo)",
                "Twój znacznik w pliku Word",
            ]
        )

        header = table.horizontalHeader()
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Stretch,
        )

        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

    def _add_tag_row(self, table: QTableWidget):
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem("nowy_klucz"))
        table.setItem(row, 1, QTableWidgetItem("Nowy Opis"))
        table.setItem(row, 2, QTableWidgetItem("<Nowy_Tag>"))

    def _del_tag_row(self, table: QTableWidget):
        row = table.currentRow()
        if row >= 0:
            table.removeRow(row)

    def _load_values(self):
        # Wygląd zakładek.
        tab_layout_mode = self.config.get("tab_layout_mode", "modern")
        tab_layout_index = self.tab_layout_combo.findData(tab_layout_mode)
        if tab_layout_index < 0:
            tab_layout_index = 0
        self.tab_layout_combo.setCurrentIndex(tab_layout_index)
        self._loaded_tab_layout_mode = tab_layout_mode
        if hasattr(self, 'default_browser_combo'):
            bidx = self.default_browser_combo.findData(self.config.get('default_browser', 'auto'))
            self.default_browser_combo.setCurrentIndex(bidx if bidx >= 0 else 0)

        sender = self.config.get("sender", {})
        self.sender_name_edit.setText(sender.get("name", ""))
        self.sender_company_edit.setText(sender.get("company", ""))
        self.sender_street_edit.setText(sender.get("street", ""))
        self.sender_city_edit.setText(sender.get("city", ""))

        self.couple_fmt_decl.setCurrentIndex(
            self.config.get("couple_format_decl", 0)
        )
        self.couple_fmt_cover.setCurrentIndex(
            self.config.get("couple_format_cover", 0)
        )
        self.couple_fmt_env.setCurrentIndex(
            self.config.get("couple_format_env", 0)
        )
        self.couple_fmt_legal.setCurrentIndex(
            self.config.get("couple_format_legal", 0)
        )

        self.default_proj_edit.setText(
            self.config.get("default_project_root", "")
        )
        self.path_przyklady_edit.setText(
            self.config.get("path_przyklady", "")
        )
        self.path_znaczki_edit.setText(
            self.config.get("path_znaczki", "")
        )
        self.path_tytuly_edit.setText(
            self.config.get("path_tytuly", "")
        )

        self.druczek_tmpl_edit.setText(
            self.config.get("druczek_template_path", "")
        )
        self.decl_budowa_edit.setText(
            self.config.get("decl_template_budowa", "")
        )
        self.decl_demontaz_edit.setText(
            self.config.get("decl_template_demontaz", "")
        )
        self.cover_letter_edit.setText(
            self.config.get("cover_letter_template", "")
        )
        self.env_c5_edit.setText(
            self.config.get("env_c5_template", "")
        )
        self.env_c6_edit.setText(
            self.config.get("env_c6_template", "")
        )
        self.stamp_c5_edit.setText(
            self.config.get("stamp_c5_pdf", "")
        )
        self.stamp_c6_edit.setText(
            self.config.get("stamp_c6_pdf", "")
        )

        self.chk_legal_exclude.setChecked(
            self.config.get("legal_exclude_dead_missing", True)
        )
        self.legal_group_combo.setCurrentIndex(
            self.config.get("legal_group_owners", 1)
        )
        self.t5_street_combo.setCurrentIndex(
            self.config.get("legal_t5_street_source", 0)
        )

        self.legal_tmpl_1_edit.setText(
            self.config.get("legal_tmpl_1", "")
        )
        self.legal_tmpl_2_edit.setText(
            self.config.get("legal_tmpl_2", "")
        )
        self.legal_tmpl_3_edit.setText(
            self.config.get("legal_tmpl_3", "")
        )
        self.legal_name_1_edit.setText(
            self.config.get(
                "legal_name_1",
                "Wykaz_dzialek_podmiotow_{symbol}.xlsx",
            )
        )
        self.legal_name_2_edit.setText(
            self.config.get(
                "legal_name_2",
                "Wykaz_szczegolowy_{symbol}.xlsx",
            )
        )
        self.legal_name_3_edit.setText(
            self.config.get(
                "legal_name_3",
                "Tabela_koncowa_{symbol}.xlsx",
            )
        )

        self.legal_suffix_combo.setCurrentIndex(
            self.config.get("legal_filename_suffix", 0)
        )
        self.legal_suffix_chars_spin.setValue(
            self.config.get("legal_suffix_chars", 4)
        )
        self.legal_suffix_chars_spin.setEnabled(
            self.legal_suffix_combo.currentIndex() == 1
        )
        self.legal_odd_edit.setText(
            self.config.get(
                "legal_odd_opcje",
                "Gdańsk, Starogard Gdański",
            )
        )

        self.single_click_cb.setChecked(
            self.config.get("single_click_activation", False)
        )
        self.chk_unlock_docs.setChecked(
            self.config.get("unlock_generated_docs", False)
        )
        self.chk_extract_parcel_address.setChecked(
            self.config.get("extract_parcel_address", True)
        )
        self.chk_sort_alpha_default.setChecked(
            self.config.get("sort_alpha_default", False)
        )
        self.chk_decl_precinct_upper.setChecked(
            self.config.get("decl_precinct_uppercase", False)
        )
        self.chk_decl_location_locative.setChecked(
            self.config.get("decl_location_locative", False)
        )
        self.chk_decl_streets.setChecked(
            self.config.get("decl_decline_streets", False)
        )
        self.chk_decl_powiat.setChecked(
            self.config.get("decl_powiat_zamiana", False)
        )

        c5_crop = self.config.get(
            "stamp_profile_c5",
            {
                "crop_left": 90,
                "crop_right": 90,
                "crop_up": 136,
                "crop_down": 2,
            },
        )
        self.c5_crop_l.setValue(c5_crop.get("crop_left", 90))
        self.c5_crop_r.setValue(c5_crop.get("crop_right", 90))
        self.c5_crop_t.setValue(c5_crop.get("crop_up", 136))
        self.c5_crop_b.setValue(c5_crop.get("crop_down", 2))

        c6_crop = self.config.get(
            "stamp_profile_c6",
            {
                "crop_left": 0,
                "crop_right": 0,
                "crop_up": 0,
                "crop_down": 0,
            },
        )
        self.c6_crop_l.setValue(c6_crop.get("crop_left", 0))
        self.c6_crop_r.setValue(c6_crop.get("crop_right", 0))
        self.c6_crop_t.setValue(c6_crop.get("crop_up", 0))
        self.c6_crop_b.setValue(c6_crop.get("crop_down", 0))

        saved_decl_tags = self.config.get("declaration_tag_map", {})
        self._load_tags_to_table(
            self.tags_table,
            DECL_TAGS,
            saved_decl_tags,
        )

        saved_cover_tags = self.config.get("cover_letter_tag_map", {})
        self._load_tags_to_table(
            self.cl_tags_table,
            COVER_TAGS,
            saved_cover_tags,
        )

    def _load_tags_to_table(
        self,
        table: QTableWidget,
        definitions: list,
        saved_map: dict,
    ):
        table.setRowCount(0)
        row = 0
        added_keys = set()

        for key, value in saved_map.items():
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(key))

            label = ""
            for default_key, default_label, _default_tag in definitions:
                if default_key == key:
                    label = default_label
                    break

            table.setItem(row, 1, QTableWidgetItem(label))
            table.setItem(row, 2, QTableWidgetItem(value))
            added_keys.add(key)
            row += 1

        for key, label, default_tag in definitions:
            if key in added_keys:
                continue

            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(key))
            table.setItem(row, 1, QTableWidgetItem(label))
            table.setItem(row, 2, QTableWidgetItem(default_tag))
            row += 1

    def _get_tags_from_table(self, table: QTableWidget) -> dict:
        result = {}

        for row in range(table.rowCount()):
            key_item = table.item(row, 0)
            value_item = table.item(row, 2)

            if not key_item or not key_item.text().strip():
                continue

            key = key_item.text().strip()
            value = value_item.text().strip() if value_item else ""
            result[key] = value

        return result

    def _save(self):
        selected_tab_layout = self.tab_layout_combo.currentData() or "modern"
        tab_layout_changed = selected_tab_layout != getattr(
            self,
            "_loaded_tab_layout_mode",
            "modern",
        )
        self.config["tab_layout_mode"] = selected_tab_layout

        self.config["sender"] = {
            "name": self.sender_name_edit.text().strip(),
            "company": self.sender_company_edit.text().strip(),
            "street": self.sender_street_edit.text().strip(),
            "city": self.sender_city_edit.text().strip(),
        }

        self.config["couple_format_decl"] = (
            self.couple_fmt_decl.currentIndex()
        )
        self.config["couple_format_cover"] = (
            self.couple_fmt_cover.currentIndex()
        )
        self.config["couple_format_env"] = (
            self.couple_fmt_env.currentIndex()
        )
        self.config["couple_format_legal"] = (
            self.couple_fmt_legal.currentIndex()
        )

        self.config["default_project_root"] = (
            self.default_proj_edit.text().strip()
        )
        self.config["path_przyklady"] = (
            self.path_przyklady_edit.text().strip()
        )
        self.config["path_znaczki"] = (
            self.path_znaczki_edit.text().strip()
        )
        self.config["path_tytuly"] = (
            self.path_tytuly_edit.text().strip()
        )

        self.config["druczek_template_path"] = (
            self.druczek_tmpl_edit.text().strip()
        )
        self.config["decl_template_budowa"] = (
            self.decl_budowa_edit.text().strip()
        )
        self.config["decl_template_demontaz"] = (
            self.decl_demontaz_edit.text().strip()
        )
        self.config["cover_letter_template"] = (
            self.cover_letter_edit.text().strip()
        )
        self.config["env_c5_template"] = self.env_c5_edit.text().strip()
        self.config["env_c6_template"] = self.env_c6_edit.text().strip()
        self.config["stamp_c5_pdf"] = self.stamp_c5_edit.text().strip()
        self.config["stamp_c6_pdf"] = self.stamp_c6_edit.text().strip()

        self.config["legal_exclude_dead_missing"] = (
            self.chk_legal_exclude.isChecked()
        )
        self.config["legal_group_owners"] = (
            self.legal_group_combo.currentIndex()
        )
        self.config["legal_t5_street_source"] = (
            self.t5_street_combo.currentIndex()
        )

        self.config["legal_tmpl_1"] = (
            self.legal_tmpl_1_edit.text().strip()
        )
        self.config["legal_tmpl_2"] = (
            self.legal_tmpl_2_edit.text().strip()
        )
        self.config["legal_tmpl_3"] = (
            self.legal_tmpl_3_edit.text().strip()
        )
        self.config["legal_name_1"] = (
            self.legal_name_1_edit.text().strip()
        )
        self.config["legal_name_2"] = (
            self.legal_name_2_edit.text().strip()
        )
        self.config["legal_name_3"] = (
            self.legal_name_3_edit.text().strip()
        )

        self.config["legal_filename_suffix"] = (
            self.legal_suffix_combo.currentIndex()
        )
        self.config["legal_suffix_chars"] = (
            self.legal_suffix_chars_spin.value()
        )
        self.config["legal_odd_opcje"] = (
            self.legal_odd_edit.text().strip()
        )

        self.config["single_click_activation"] = (
            self.single_click_cb.isChecked()
        )
        self.config["unlock_generated_docs"] = (
            self.chk_unlock_docs.isChecked()
        )
        self.config["extract_parcel_address"] = (
            self.chk_extract_parcel_address.isChecked()
        )
        self.config["sort_alpha_default"] = (
            self.chk_sort_alpha_default.isChecked()
        )
        self.config["decl_precinct_uppercase"] = (
            self.chk_decl_precinct_upper.isChecked()
        )
        self.config["decl_location_locative"] = (
            self.chk_decl_location_locative.isChecked()
        )
        self.config["decl_decline_streets"] = (
            self.chk_decl_streets.isChecked()
        )
        self.config["decl_powiat_zamiana"] = (
            self.chk_decl_powiat.isChecked()
        )

        self.config["stamp_profile_c5"] = {
            "crop_left": self.c5_crop_l.value(),
            "crop_right": self.c5_crop_r.value(),
            "crop_up": self.c5_crop_t.value(),
            "crop_down": self.c5_crop_b.value(),
        }
        self.config["stamp_profile_c6"] = {
            "crop_left": self.c6_crop_l.value(),
            "crop_right": self.c6_crop_r.value(),
            "crop_up": self.c6_crop_t.value(),
            "crop_down": self.c6_crop_b.value(),
        }

        self.config["declaration_tag_map"] = self._get_tags_from_table(
            self.tags_table
        )
        self.config["cover_letter_tag_map"] = self._get_tags_from_table(
            self.cl_tags_table
        )

        self.save_callback()

        if tab_layout_changed:
            self._loaded_tab_layout_mode = selected_tab_layout
            QMessageBox.information(
                self,
                "Zapisano – wymagane ponowne uruchomienie",
                "Ustawienia zostały zapisane.\n\n"
                "Aby zastosować wybrany wygląd zakładek, zamknij "
                "i uruchom aplikację ponownie.",
            )
        else:
            QMessageBox.information(
                self,
                "Zapisano",
                "Ustawienia zostały zapisane.",
            )

    def _reset_tags(self, table: QTableWidget, definitions: list):
        table.setRowCount(0)

        for row, (key, label, default_tag) in enumerate(definitions):
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(key))
            table.setItem(row, 1, QTableWidgetItem(label))
            table.setItem(row, 2, QTableWidgetItem(default_tag))

    def _set_default_paths(self):
        base_dir = get_app_dir()
        self.path_przyklady_edit.setText(str(base_dir / "przykłady"))
        self.path_znaczki_edit.setText(str(base_dir / "znaczki"))
        self.path_tytuly_edit.setText(str(base_dir / "tytuły prawne"))
        self.default_proj_edit.setText(str(base_dir / "Projekty"))

        QMessageBox.information(
            self,
            "Zaktualizowano",
            "Wczytano domyślne ścieżki obok aplikacji.",
        )

    def _set_parent_default_paths(self):
        base_dir = get_app_dir().parent
        self.path_przyklady_edit.setText(str(base_dir / "przykłady"))
        self.path_znaczki_edit.setText(str(base_dir / "znaczki"))
        self.path_tytuly_edit.setText(str(base_dir / "tytuły prawne"))
        self.default_proj_edit.setText(str(base_dir / "Projekty"))

        QMessageBox.information(
            self,
            "Zaktualizowano",
            "Wczytano domyślne ścieżki z folderu nadrzędnego programu.",
        )

    def _set_default_decl_templates(self):
        from utils.templates import find_latest_file

        examples_path = Path(self.path_przyklady_edit.text().strip())

        if not examples_path.exists():
            QMessageBox.warning(
                self,
                "Błąd",
                "Folder ze ścieżki „Folder szablony dokumentów "
                "(przykłady)” nie istnieje!",
            )
            return

        # Nazwy bazowe bez numeru wersji – program sam dobiera najnowszą wersję.
        specs = [
            (
                self.decl_budowa_edit,
                ["Oświadczenie woli budowa kabla", "Oświadczenie woli budowa",
                 "oswiadczenie woli budowa kabla", "oswiadczenie woli budowa"],
                "Oświadczenie woli budowa kabla",
            ),
            (
                self.decl_demontaz_edit,
                ["Oświadczenie woli demontaż linii", "Oświadczenie woli demontaz linii",
                 "Oświadczenie woli demontaż", "Oświadczenie woli demontaz"],
                "Oświadczenie woli demontaż linii",
            ),
            (
                self.cover_letter_edit,
                ["Pismo przewodnie", "pismo przewodnie"],
                "Pismo przewodnie",
            ),
            (
                self.env_c5_edit,
                ["koperty C5 wysyłka", "koperta C5 wysyłka",
                 "koperty C5", "koperta C5"],
                "koperty C5 wysyłka",
            ),
            (
                self.env_c6_edit,
                ["c6 nowy", "koperta C6 nowy", "koperty C6 nowy",
                 "c6", "koperta C6", "koperty C6"],
                "c6 nowy",
            ),
        ]

        found = []
        missing = []
        for edit, bases, label in specs:
            latest = find_latest_file(examples_path, bases, (".docx",))
            if latest is not None:
                edit.setText(str(latest))
                found.append(label)
            else:
                missing.append(label)

        if found:
            QMessageBox.information(
                self,
                "Zaktualizowano",
                "Automatycznie wczytano najnowsze wersje szablonów "
                f"z folderu Przykłady:\n\n• " + "\n• ".join(found),
            )
        if missing:
            QMessageBox.warning(
                self,
                "Nie znaleziono",
                "Nie znaleziono żadnego pliku dla szablonów:\n\n• "
                + "\n• ".join(missing)
                + "\n\nSprawdź, czy w folderze Przykłady znajdują się "
                "pliki .docx o podanych nazwach.",
            )

    def _set_default_excel_templates(self):
        from utils.templates import find_file_newest

        legal_path = Path(self.path_tytuly_edit.text().strip())

        if not legal_path.exists():
            QMessageBox.warning(
                self,
                "Błąd",
                "Folder ze ścieżki „Folder szablony "
                "(tytuły prawne)” nie istnieje!",
            )
            return

        specs = [
            (self.legal_tmpl_1_edit, ["szablon1", "szablon 1"]),
            (self.legal_tmpl_2_edit, ["szablon2", "szablon 2"]),
            (self.legal_tmpl_3_edit, ["szablon3", "szablon 3"]),
        ]

        found = []
        missing = []
        for edit, bases in specs:
            latest = find_file_newest(
                legal_path, bases, (".xlsx", ".xlsm")
            )
            if latest is not None:
                edit.setText(str(latest))
                found.append(latest.name)
            else:
                missing.append(bases[0])

        if found:
            QMessageBox.information(
                self,
                "Zaktualizowano",
                "Automatycznie wczytano szablony Excel z folderu "
                "Tytuły prawne:\n\n• " + "\n• ".join(found),
            )
        if missing:
            QMessageBox.warning(
                self,
                "Nie znaleziono",
                "Nie znaleziono plików dla szablonów Excel:\n\n• "
                + "\n• ".join(missing)
                + "\n\nSprawdź pliki w folderze Tytuły prawne.",
            )

    def _set_default_pdf_templates(self):
        from utils.templates import find_latest_file, find_file_newest

        stamps_path = Path(self.path_znaczki_edit.text().strip())

        if not stamps_path.exists():
            QMessageBox.warning(
                self,
                "Błąd",
                "Folder ze ścieżki „Folder z plikami znaczków” "
                "nie istnieje!",
            )
            return

        found = []
        missing = []

        druczek = find_file_newest(stamps_path, ["druczek"], (".pdf",))
        if druczek is not None:
            self.druczek_tmpl_edit.setText(str(druczek))
            found.append(druczek.name)
        else:
            missing.append("druczek.pdf")

        c5 = find_latest_file(
            stamps_path, ["znaczki_c5", "znaczki c5", "znaczek_c5"], (".pdf",)
        )
        if c5 is not None:
            self.stamp_c5_edit.setText(str(c5))
            found.append(c5.name)
        else:
            missing.append("znaczki_c5.pdf")

        c6 = find_latest_file(
            stamps_path, ["znaczki_c6", "znaczki c6", "znaczek_c6"], (".pdf",)
        )
        if c6 is not None:
            self.stamp_c6_edit.setText(str(c6))
            found.append(c6.name)
        else:
            missing.append("znaczki_c6.pdf")

        if found:
            QMessageBox.information(
                self,
                "Zaktualizowano",
                "Automatycznie wczytano pliki PDF z folderu Znaczki:\n\n• "
                + "\n• ".join(found),
            )
        if missing:
            QMessageBox.warning(
                self,
                "Nie znaleziono",
                "Nie znaleziono plików PDF:\n\n• "
                + "\n• ".join(missing)
                + "\n\nSprawdź pliki w folderze Znaczki.",
            )
