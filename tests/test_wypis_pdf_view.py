"""Testy graficznego wskazywania pól na wypisie PDF.

Sprawdzamy warstwę, która zamienia stronę PDF na obrazek ze znanym
położeniem każdego słowa — czyli to, dzięki czemu użytkownik przypisuje
pola klikaniem, a nie przepisywaniem nazw.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - brak biblioteki
    fitz = None

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - brak Qt
    QApplication = None

if QApplication is not None and fitz is not None:
    try:
        from modules.wypis_pdf_view import (
            WypisPdfView,
            _fold,
            label_at,
            load_page,
            page_count,
            read_area_value,
            text_in_rect,
        )
    except Exception:  # pragma: no cover - brak bibliotek graficznych
        QApplication = None


WIERSZE = [
    "STAROSTWO POWIATOWE W KARTUZACH",
    "Wojewodztwo: POMORSKIE",
    "Powiat: kartuski",
    "Adres nieruchomosci: Borkowo, ul. Polna 3",
    "Pow. [ha]: 0,4500",
]

_app = None


def setUpModule():  # noqa: N802 - nazwa wymagana przez unittest
    global _app
    if QApplication is not None:
        _app = QApplication.instance() or QApplication([])


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)

def _pionowy_wypis():
    """Wypis z polami jeden pod drugim (jak na zrzucie użytkownika)."""

    try:
        import fitz
    except ImportError:
        return None

    wiersze = [
        ("Wojewodztwo", "POMORSKIE"),
        ("Powiat", "kartuski"),
        ("Gmina", "Zukowo"),
        ("Jednostka ewidencyjna", "221509_2, Szemud"),
        ("Obreb", "0019, BOJANO"),
    ]
    doc = fitz.open()
    strona = doc.new_page()
    y = 90
    for etykieta, wartosc in wiersze:
        strona.insert_text((50, y), etykieta, fontsize=11)
        strona.insert_text((230, y), wartosc, fontsize=11)
        y += 34
    katalog = tempfile.mkdtemp()
    sciezka = str(Path(katalog) / "pion.pdf")
    doc.save(sciezka)
    doc.close()
    return sciezka

class PodgladStronyTests(unittest.TestCase):
    FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pdf = str(Path(cls._tmp.name) / "wypis.pdf")
        doc = fitz.open()
        page = doc.new_page()
        font = cls.FONT if Path(cls.FONT).is_file() else None
        y = 60
        for line in WIERSZE:
            if font:
                page.insert_text((50, y), line, fontsize=11, fontfile=font, fontname="DJ")
            else:  # pragma: no cover - zapas, gdy brak czcionki
                page.insert_text((50, y), line, fontsize=11)
            y += 24
        doc.save(cls.pdf)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_liczba_stron(self):
        self.assertEqual(page_count(self.pdf), 1)

    def test_brak_pliku_daje_zero_stron(self):
        self.assertEqual(page_count("/nie/ma/pliku.pdf"), 0)

    def test_strona_renderuje_sie_do_obrazka(self):
        page = load_page(self.pdf)
        self.assertIsNotNone(page)
        self.assertGreater(page.image.width(), 100)
        self.assertGreater(page.image.height(), 100)

    def test_slowa_maja_polozenie(self):
        page = load_page(self.pdf)
        self.assertGreater(len(page.words), 5)
        for word in page.words:
            self.assertGreater(word.rect.width(), 0)

    def test_nieistniejaca_strona_daje_none(self):
        self.assertIsNone(load_page(self.pdf, page_number=7))

    def test_uszkodzony_plik_nie_wywala_programu(self):
        self.assertIsNone(load_page("/nie/ma/pliku.pdf"))


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class KlikanieTests(unittest.TestCase):
    FONT = PodgladStronyTests.FONT

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf
        cls.page = load_page(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def _klik_w(self, tekst: str):
        view = WypisPdfView()
        view.set_page(self.page)
        rect = view.find_label_rect(tekst)
        self.assertIsNotNone(rect, f"nie znaleziono etykiety {tekst!r}")
        point = QPoint(int(rect.center().x()), int(rect.center().y()))
        return label_at(self.page, point)

    def test_klikniecie_zwraca_etykiete(self):
        hit = self._klik_w("Powiat")
        self.assertEqual(hit["label"], "Powiat")

    def test_klikniecie_zwraca_wartosc_obok(self):
        hit = self._klik_w("Powiat")
        self.assertEqual(hit["value"], "kartuski")

    def test_etykieta_dwuwyrazowa(self):
        hit = self._klik_w("Adres nieruchomosci")
        self.assertEqual(hit["label"], "Adres nieruchomosci")
        self.assertIn("Borkowo", hit["value"])

    def test_klikniecie_w_pustke_nic_nie_daje(self):
        self.assertIsNone(label_at(self.page, QPoint(5, 5)))

    def test_szukanie_etykiety_ignoruje_ogonki(self):
        view = WypisPdfView()
        view.set_page(self.page)
        # W dokumencie jest „Wojewodztwo”, użytkownik wpisuje z ogonkiem.
        self.assertIsNotNone(view.find_label_rect("Województwo"))

    def test_szukanie_ignoruje_wielkosc_liter(self):
        view = WypisPdfView()
        view.set_page(self.page)
        self.assertIsNotNone(view.find_label_rect("POWIAT"))

    def test_nieznana_etykieta_daje_none(self):
        view = WypisPdfView()
        view.set_page(self.page)
        self.assertIsNone(view.find_label_rect("Nie ma takiego pola"))

    def test_najdluzsza_etykieta_wygrywa(self):
        view = WypisPdfView()
        view.set_page(self.page)
        dluga = view.label_rects(["Pow.", "Pow. [ha]"])
        krotka = view.find_label_rect("Pow.")
        self.assertIsNotNone(dluga)
        self.assertGreater(dluga.width(), krotka.width())

    def test_etykieta_konczy_sie_na_dwukropku(self):
        """„Pow. [ha]: 0,4500” to etykieta „Pow. [ha]”, nie samo „Pow.”."""
        hit = self._klik_w("Pow. [ha]")
        self.assertEqual(hit["label"], "Pow. [ha]")
        self.assertEqual(hit["value"], "0,4500")

    def test_klikniecie_w_wartosc_tez_daje_etykiete(self):
        view = WypisPdfView()
        view.set_page(self.page)
        rect = view.find_label_rect("Powiat")
        # Punkt na prawo od etykiety, czyli w obszarze wartości.
        point = QPoint(int(rect.right() + 30), int(rect.center().y()))
        hit = label_at(self.page, point)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["label"], "Powiat")

    def test_trafienie_w_odstep_miedzy_slowami(self):
        """Kursor w przerwie między słowami też ma działać."""
        view = WypisPdfView()
        view.set_page(self.page)
        rect = view.find_label_rect("Adres nieruchomosci")
        point = QPoint(int(rect.center().x()), int(rect.center().y()))
        self.assertIsNotNone(label_at(self.page, point))

    def test_widok_bez_strony_nie_wywala_sie(self):
        view = WypisPdfView()
        view.set_page(None)
        self.assertIsNone(view.find_label_rect("Powiat"))
        self.assertIsNone(label_at(None, QPoint(1, 1)))

    def test_ramki_mozna_ustawic_i_wyczyscic(self):
        view = WypisPdfView()
        view.set_page(self.page)
        rect = view.find_label_rect("Powiat")
        view.set_marks({"Powiat": rect})
        self.assertEqual(len(view.marks), 1)
        view.set_marks({})
        self.assertEqual(len(view.marks), 0)


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class MarginesIOznaczeniaTests(unittest.TestCase):
    """Podpisy pól stoją na marginesie i nie zasłaniają treści wypisu."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def _widok(self):
        view = WypisPdfView()
        view.set_page(load_page(self.pdf))
        return view

    def test_widok_jest_szerszy_o_margines(self):
        page = load_page(self.pdf)
        szerokosc_obrazu = page.image.width()
        view = WypisPdfView()
        view.set_page(page)
        self.assertEqual(view.width(), szerokosc_obrazu + view.margin_left)

    def test_slowa_sa_przesuniete_o_margines(self):
        view = self._widok()
        rect = view.find_label_rect("Powiat")
        self.assertGreaterEqual(rect.left(), view.margin_left)

    def test_klikanie_dziala_po_przesunieciu(self):
        view = self._widok()
        rect = view.find_label_rect("Powiat")
        hit = label_at(view.page, QPoint(int(rect.center().x()), int(rect.center().y())))
        self.assertEqual(hit["label"], "Powiat")
        self.assertEqual(hit["value"], "kartuski")

    def test_klikniecie_zwraca_prostokat_wartosci(self):
        view = self._widok()
        rect = view.find_label_rect("Powiat")
        hit = label_at(view.page, QPoint(int(rect.center().x()), int(rect.center().y())))
        self.assertIsNotNone(hit["value_rect"])
        # Wartość stoi na prawo od etykiety.
        self.assertGreater(hit["value_rect"].left(), rect.left())

    def test_etykieta_i_wartosc_naraz(self):
        view = self._widok()
        etykieta, wartosc = view.label_and_value_rects(["Powiat"])
        self.assertIsNotNone(etykieta)
        self.assertIsNotNone(wartosc)

    def test_brak_etykiety_daje_dwa_none(self):
        view = self._widok()
        etykieta, wartosc = view.label_and_value_rects(["Nie ma takiego pola"])
        self.assertIsNone(etykieta)
        self.assertIsNone(wartosc)

    def test_ramki_wartosci_mozna_ustawic(self):
        view = self._widok()
        etykieta, wartosc = view.label_and_value_rects(["Powiat"])
        view.set_marks({"Powiat": etykieta}, {"Powiat": wartosc})
        self.assertEqual(len(view.marks), 1)
        self.assertEqual(len(view.value_marks), 1)

    def test_rysowanie_nie_zglasza_bledu(self):
        """Sam paintEvent musi przejść — z ramkami i podpisami."""
        from PySide6.QtGui import QPixmap

        view = self._widok()
        etykieta, wartosc = view.label_and_value_rects(["Powiat"])
        view.set_marks({"Powiat": etykieta}, {"Powiat": wartosc})
        pixmap = QPixmap(view.size())
        view.render(pixmap)
        self.assertFalse(pixmap.isNull())

    def test_dluga_nazwa_nie_wywala_rysowania(self):
        from PySide6.QtGui import QPixmap

        view = self._widok()
        etykieta = view.find_label_rect("Powiat")
        view.set_marks({"Bardzo długa nazwa pola w programie": etykieta})
        pixmap = QPixmap(view.size())
        view.render(pixmap)
        self.assertFalse(pixmap.isNull())

@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class PowiekszenieTests(unittest.TestCase):
    """Suwak powiększenia, przyciski +/− i „Dopasuj”."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def _okno(self):
        from modules.wypis_profil_dialog import WypisProfileDialog

        dialog = WypisProfileDialog({})
        dialog.resize(1300, 850)
        dialog.show()
        dialog.load_pdf_path(self.pdf)
        return dialog

    def test_domyslne_powiekszenie_to_sto_procent(self):
        dialog = self._okno()
        self.assertEqual(dialog.zoom_slider.value(), 100)
        self.assertEqual(dialog.lbl_zoom.text(), "100%")

    def test_powiekszanie_zwieksza_podglad(self):
        dialog = self._okno()
        przed = dialog.page_view.width()
        dialog.zoom_slider.setValue(200)
        self.assertGreater(dialog.page_view.width(), przed)
        self.assertEqual(dialog.lbl_zoom.text(), "200%")

    def test_pomniejszanie_zmniejsza_podglad(self):
        dialog = self._okno()
        dialog.zoom_slider.setValue(200)
        duzy = dialog.page_view.width()
        dialog.zoom_slider.setValue(75)
        self.assertLess(dialog.page_view.width(), duzy)

    def test_przycisk_plus_dodaje_krok(self):
        dialog = self._okno()
        dialog._zoom_step(1)
        self.assertEqual(dialog.zoom_slider.value(), 125)

    def test_przycisk_minus_odejmuje_krok(self):
        dialog = self._okno()
        dialog._zoom_step(-1)
        self.assertEqual(dialog.zoom_slider.value(), 75)

    def test_powiekszenie_nie_wychodzi_poza_zakres(self):
        dialog = self._okno()
        for _ in range(20):
            dialog._zoom_step(1)
        self.assertLessEqual(dialog.zoom_slider.value(), 300)
        for _ in range(40):
            dialog._zoom_step(-1)
        self.assertGreaterEqual(dialog.zoom_slider.value(), 50)

    def test_dopasuj_wraca_do_stu_procent(self):
        dialog = self._okno()
        dialog.zoom_slider.setValue(250)
        dialog._zoom_fit()
        self.assertEqual(dialog.zoom_slider.value(), 100)

    def test_strona_miesci_sie_w_oknie_przy_dopasowaniu(self):
        dialog = self._okno()
        dialog._zoom_fit()
        self.assertLessEqual(
            dialog.page_view.width(),
            dialog.page_scroll.viewport().width() + 4,
        )

    def test_oznaczenia_mozna_ukryc(self):
        dialog = self._okno()
        dialog.chk_show_marks.setChecked(False)
        self.assertEqual(len(dialog.page_view.marks), 0)
        dialog.chk_show_marks.setChecked(True)
        self.assertGreater(len(dialog.page_view.marks), 0)


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class TabelaWWierszuTests(unittest.TestCase):
    """Jeden wiersz z dwiema parami: klik ma trafiać dokładnie w swoje pole."""

    WIERSZE = [
        "Powiat: kartuski          Gmina: Zukowo",
        "Obreb: 0010 MAKI          Nr obrebu: 0010",
        "Dzialka nr: 145/7         Pow. [ha]: 0,4500",
    ]

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pdf = str(Path(cls._tmp.name) / "tabela.pdf")
        doc = fitz.open()
        page = doc.new_page()
        font = PodgladStronyTests.FONT
        font = font if Path(font).is_file() else None
        y = 60
        for line in cls.WIERSZE:
            if font:
                page.insert_text((50, y), line, fontsize=11, fontfile=font, fontname="DJ")
            else:  # pragma: no cover
                page.insert_text((50, y), line, fontsize=11)
            y += 26
        doc.save(cls.pdf)
        doc.close()
        cls.page = load_page(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _klik(self, etykieta: str) -> dict:
        view = WypisPdfView()
        view.set_page(self.page)
        rect = view.find_label_rect(etykieta)
        self.assertIsNotNone(rect, f"nie znaleziono {etykieta!r}")
        return label_at(
            self.page, QPoint(int(rect.center().x()), int(rect.center().y()))
        )

    def test_druga_kolumna_zwraca_swoja_etykiete(self):
        hit = self._klik("Gmina")
        self.assertEqual(hit["label"], "Gmina")

    def test_druga_kolumna_zwraca_swoja_wartosc(self):
        self.assertEqual(self._klik("Gmina")["value"], "Zukowo")

    def test_pierwsza_kolumna_nie_wciaga_drugiej(self):
        hit = self._klik("Powiat")
        self.assertEqual(hit["label"], "Powiat")
        self.assertEqual(hit["value"], "kartuski")

    def test_etykieta_dwuwyrazowa_w_drugiej_kolumnie(self):
        hit = self._klik("Nr obrebu")
        self.assertEqual(hit["label"], "Nr obrebu")
        self.assertEqual(hit["value"], "0010")

    def test_wartosc_wielowyrazowa_w_pierwszej_kolumnie(self):
        hit = self._klik("Obreb")
        self.assertEqual(hit["value"], "0010 MAKI")

    def test_etykieta_z_nawiasem_w_drugiej_kolumnie(self):
        hit = self._klik("Pow. [ha]")
        self.assertEqual(hit["label"], "Pow. [ha]")
        self.assertEqual(hit["value"], "0,4500")

    def test_dzialka_nr_nie_wciaga_powierzchni(self):
        hit = self._klik("Dzialka nr")
        self.assertEqual(hit["value"], "145/7")


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class CofanieIUsuwanieTests(unittest.TestCase):
    """Cofanie, ponawianie i usuwanie przypisań."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        self._question = QMessageBox.question
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes
        )

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.resize(1200, 800)
        self.dialog.show()
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info
        QMessageBox.question = self._question

    def _wiersz(self, nazwa: str) -> int:
        for row in range(self.dialog.table.rowCount()):
            if self.dialog.table.item(row, 0).text() == nazwa:
                return row
        raise AssertionError(f"brak wiersza {nazwa!r}")

    def _przypisz(self, etykieta: str, pole: str) -> int:
        row = self._wiersz(pole)
        self.dialog.table.setCurrentCell(row, 0)
        view = self.dialog.page_view
        rect = view.find_label_rect(etykieta)
        hit = label_at(view.page, QPoint(int(rect.center().x()), int(rect.center().y())))
        self.dialog._on_label_clicked(hit)
        return row

    def test_na_starcie_nie_ma_czego_cofac(self):
        self.assertFalse(self.dialog.btn_undo.isEnabled())
        self.assertFalse(self.dialog.btn_redo.isEnabled())

    def test_przypisanie_wlacza_cofanie(self):
        self._przypisz("Powiat", "Powiat")
        self.assertTrue(self.dialog.btn_undo.isEnabled())

    def test_cofniecie_przywraca_poprzedni_stan(self):
        row = self._wiersz("Powiat")
        przed = self.dialog.table.item(row, 1).text()
        self._przypisz("Powiat", "Powiat")
        self.dialog._undo_change()
        self.assertEqual(self.dialog.table.item(row, 1).text(), przed)

    def test_ponowienie_wraca_do_zmiany(self):
        row = self._przypisz("Powiat", "Powiat")
        po_zmianie = self.dialog.table.item(row, 1).text()
        self.dialog._undo_change()
        self.dialog._redo_change()
        self.assertEqual(self.dialog.table.item(row, 1).text(), po_zmianie)

    def test_usuwanie_pola_czysci_etykiety(self):
        row = self._wiersz("Powiat")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog._clear_row()
        self.assertEqual(self.dialog.table.item(row, 1).text(), "")

    def test_usuwanie_mozna_cofnac(self):
        row = self._wiersz("Powiat")
        przed = self.dialog.table.item(row, 1).text()
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog._clear_row()
        self.dialog._undo_change()
        self.assertEqual(self.dialog.table.item(row, 1).text(), przed)

    def test_czyszczenie_wszystkich_we_wlasnym_wzorze(self):
        from PySide6.QtWidgets import QInputDialog

        oryginal = QInputDialog.getText
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Mój wzór", True))
        try:
            self.dialog._copy_profile()
        finally:
            QInputDialog.getText = oryginal

        self.dialog._clear_all_rows()
        puste = [
            self.dialog.table.item(r, 1).text()
            for r in range(self.dialog.table.rowCount())
        ]
        self.assertTrue(all(not t for t in puste))

    def test_czyszczenie_wszystkich_mozna_cofnac(self):
        from PySide6.QtWidgets import QInputDialog

        oryginal = QInputDialog.getText
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Mój wzór 2", True))
        try:
            self.dialog._copy_profile()
        finally:
            QInputDialog.getText = oryginal

        ile_przed = sum(
            1
            for r in range(self.dialog.table.rowCount())
            if self.dialog.table.item(r, 1).text()
        )
        self.dialog._clear_all_rows()
        self.dialog._undo_change()
        ile_po = sum(
            1
            for r in range(self.dialog.table.rowCount())
            if self.dialog.table.item(r, 1).text()
        )
        self.assertEqual(ile_po, ile_przed)

    def test_wzoru_wbudowanego_nie_da_sie_wyczyscic(self):
        self.assertTrue(self.dialog._current_profile().get("builtin"))
        ile_przed = sum(
            1
            for r in range(self.dialog.table.rowCount())
            if self.dialog.table.item(r, 1).text()
        )
        self.dialog._clear_all_rows()
        ile_po = sum(
            1
            for r in range(self.dialog.table.rowCount())
            if self.dialog.table.item(r, 1).text()
        )
        self.assertEqual(ile_po, ile_przed)

    def test_historia_ma_ograniczona_dlugosc(self):
        for _ in range(60):
            self.dialog._remember()
        self.assertLessEqual(len(self.dialog._undo), 40)

    def test_przyciski_maja_skroty(self):
        self.assertEqual(self.dialog.btn_undo.shortcut().toString(), "Ctrl+Z")
        self.assertEqual(self.dialog.btn_redo.shortcut().toString(), "Ctrl+Y")
        self.assertEqual(self.dialog.btn_clear_row.shortcut().toString(), "Del")


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class KlikWWartoscTests(unittest.TestCase):
    """Klik w samą wartość ma zwracać jej etykietę, a nie sąsiednią kolumnę."""

    @classmethod
    def setUpClass(cls):
        TabelaWWierszuTests.setUpClass()
        cls.page = TabelaWWierszuTests.page

    @classmethod
    def tearDownClass(cls):
        TabelaWWierszuTests.tearDownClass()

    def _klik_w_wartosc(self, tekst: str) -> dict:
        slowo = next(w for w in self.page.words if w.text.strip() == tekst)
        return label_at(
            self.page,
            QPoint(int(slowo.rect.center().x()), int(slowo.rect.center().y())),
        )

    def test_wartosc_pierwszej_kolumny(self):
        hit = self._klik_w_wartosc("kartuski")
        self.assertEqual(hit["label"], "Powiat")
        self.assertEqual(hit["value"], "kartuski")

    def test_wartosc_drugiej_kolumny(self):
        hit = self._klik_w_wartosc("Zukowo")
        self.assertEqual(hit["label"], "Gmina")

    def test_wartosc_z_nawiasem_w_etykiecie(self):
        self.assertEqual(self._klik_w_wartosc("0,4500")["label"], "Pow. [ha]")

    def test_wartosc_z_ukosnikiem(self):
        self.assertEqual(self._klik_w_wartosc("145/7")["label"], "Dzialka nr")

    def test_drugie_slowo_wartosci_wielowyrazowej(self):
        hit = self._klik_w_wartosc("MAKI")
        self.assertEqual(hit["label"], "Obreb")
        self.assertEqual(hit["value"], "0010 MAKI")


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class RecznaWartoscTests(unittest.TestCase):
    """Kolumna „Odczytana wartość” daje się poprawić ręcznie."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def _wiersz(self, nazwa: str) -> int:
        for row in range(self.dialog.table.rowCount()):
            if self.dialog.table.item(row, 0).text() == nazwa:
                return row
        raise AssertionError(f"brak wiersza {nazwa!r}")

    def test_kolumna_wartosci_jest_edytowalna(self):
        row = self._wiersz("Powiat")
        item = self.dialog.table.item(row, 4)
        self.assertTrue(item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_kolumna_stanu_nie_jest_edytowalna(self):
        row = self._wiersz("Powiat")
        item = self.dialog.table.item(row, 3)
        self.assertFalse(item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_wpisana_wartosc_zostaje_zapamietana(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 4).setText("wejherowski")
        self.assertEqual(self.dialog._manual_values.get("county"), "wejherowski")

    def test_wpisana_wartosc_zmienia_stan(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 4).setText("wejherowski")
        self.assertIn("ręcznie", self.dialog.table.item(row, 3).text())

    def test_ponowna_analiza_nie_kasuje_recznej_wartosci(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 4).setText("wejherowski")
        self.dialog._analyze()
        self.assertEqual(self.dialog.table.item(row, 4).text(), "wejherowski")

    def test_skasowanie_wraca_do_odczytu(self):
        row = self._wiersz("Powiat")
        odczyt = self.dialog.table.item(row, 4).text()
        self.dialog.table.item(row, 4).setText("wejherowski")
        self.dialog.table.item(row, 4).setText("")
        self.assertEqual(self.dialog.table.item(row, 4).text(), odczyt)
        self.assertNotIn("county", self.dialog._manual_values)

    def test_wartosc_trafia_do_wzoru(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 4).setText("wejherowski")
        index = self.dialog._current_index()
        zapisane = self.dialog.profiles[index].get("manual_values", {})
        self.assertEqual(zapisane.get("county"), "wejherowski")


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class TrybKlikaniaTests(unittest.TestCase):
    """Przełącznik: kliknięcie uczy etykiety albo wpisuje wartość."""

    @classmethod
    def setUpClass(cls):
        TabelaWWierszuTests.setUpClass()
        cls.pdf = TabelaWWierszuTests.pdf

    @classmethod
    def tearDownClass(cls):
        TabelaWWierszuTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def _wiersz(self, nazwa: str) -> int:
        for row in range(self.dialog.table.rowCount()):
            if self.dialog.table.item(row, 0).text() == nazwa:
                return row
        raise AssertionError(f"brak wiersza {nazwa!r}")

    def _klik(self, tekst: str) -> None:
        slowo = next(
            w
            for w in self.dialog.page_view.page.words
            if w.text.strip().rstrip(":") == tekst
        )
        hit = label_at(
            self.dialog.page_view.page,
            QPoint(int(slowo.rect.center().x()), int(slowo.rect.center().y())),
        )
        self.dialog._on_label_clicked(hit)

    def test_domyslnie_tryb_etykiety(self):
        self.assertEqual(self.dialog._click_mode(), "label")

    def test_tryb_etykiety_dopisuje_do_kolumny_etykiet(self):
        row = self._wiersz("Powiat")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_label.setChecked(True)
        self._klik("Powiat")
        self.assertIn("Powiat", self.dialog.table.item(row, 1).text())

    def test_tryb_wartosci_uczy_etykiety_zeby_odczytac(self):
        # Wskazanie wartości uczy program nazwy pola, dzięki czemu
        # wartość jest ODCZYTANA, a nie wpisana na sztywno.
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.assertIn("Pow. [ha]", self.dialog.table.item(row, 1).text())

    def test_tryb_wartosci_wpisuje_do_kolumny_wartosci(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.assertEqual(self.dialog.table.item(row, 4).text(), "0,4500")

    def test_tryb_wartosci_daje_stan_odczytano(self):
        # Kluczowe: ma być „odczytano”, nie „wpisano ręcznie”.
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.assertIn("odczytano", self.dialog.table.item(row, 3).text())
        self.assertNotIn("ręcznie", self.dialog.table.item(row, 3).text())

    def test_wskazana_wartosc_da_sie_cofnac(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        przed = self.dialog.table.item(row, 4).text()
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.dialog._undo_change()
        self.assertEqual(self.dialog.table.item(row, 4).text(), przed)

    def test_wskazana_wartosc_zapisuje_etykiete_we_wzorze(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        index = self.dialog._current_index()
        self.assertIn("Pow. [ha]", self.dialog.profiles[index]["fields"]["kw"])

    def test_wskazana_wartosc_jest_odczytana_z_dokumentu(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.assertEqual(self.dialog.table.item(row, 4).text(), "0,4500")


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class TabelaWKratkeTests(unittest.TestCase):
    """Wypis w kratkę: nazwa kolumny stoi NAD wartością, bez dwukropka."""

    NAGLOWKI = ["Obreb", "Nr dzialki", "Pow. [ha]", "Opis uzytku"]
    WIERSZE = [
        ["0019, BOJANO", "145/7", "0.0235", "dr"],
        ["0019, BOJANO", "145/8", "0.1120", "RIVa"],
    ]

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pdf = str(Path(cls._tmp.name) / "kratka.pdf")
        font = PodgladStronyTests.FONT
        font = font if Path(font).is_file() else None

        doc = fitz.open()
        page = doc.new_page()
        x0, y0, szer, wys = 40, 60, 120, 22

        def komorka(kolumna, wiersz, tekst):
            rect = fitz.Rect(
                x0 + kolumna * szer,
                y0 + wiersz * wys,
                x0 + (kolumna + 1) * szer,
                y0 + (wiersz + 1) * wys,
            )
            page.draw_rect(rect)
            if font:
                page.insert_text(
                    (rect.x0 + 4, rect.y0 + 15),
                    tekst,
                    fontsize=9,
                    fontfile=font,
                    fontname="DJ",
                )
            else:  # pragma: no cover
                page.insert_text((rect.x0 + 4, rect.y0 + 15), tekst, fontsize=9)

        for kolumna, tekst in enumerate(cls.NAGLOWKI):
            komorka(kolumna, 0, tekst)
        for numer, wiersz in enumerate(cls.WIERSZE, start=1):
            for kolumna, tekst in enumerate(wiersz):
                komorka(kolumna, numer, tekst)

        doc.save(cls.pdf)
        doc.close()
        cls.page = load_page(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _klik(self, tekst: str) -> dict:
        slowo = next(w for w in self.page.words if tekst in w.text)
        return label_at(
            self.page,
            QPoint(int(slowo.rect.center().x()), int(slowo.rect.center().y())),
        )

    def test_wartosc_dostaje_naglowek_kolumny(self):
        hit = self._klik("0.0235")
        self.assertEqual(hit["label"], "Pow. [ha]")
        self.assertEqual(hit["value"], "0.0235")

    def test_drugi_wiersz_tez_wskazuje_naglowek(self):
        # Regresja: brał wiersz bezpośrednio nad sobą, czyli dane.
        hit = self._klik("0.1120")
        self.assertEqual(hit["label"], "Pow. [ha]")
        self.assertEqual(hit["value"], "0.1120")

    def test_naglowek_wielowyrazowy_w_calosci(self):
        # Regresja: „Opis uzytku” ucinane do „Opis”.
        self.assertEqual(self._klik("RIVa")["label"], "Opis uzytku")

    def test_numer_dzialki_z_kratki(self):
        hit = self._klik("145/8")
        self.assertEqual(hit["label"], "Nr dzialki")
        self.assertEqual(hit["value"], "145/8")

    def test_wartosc_z_przecinkiem(self):
        hit = self._klik("BOJANO")
        self.assertEqual(hit["label"], "Obreb")
        self.assertEqual(hit["value"], "0019, BOJANO")

    def test_klik_w_sam_naglowek_zwraca_naglowek(self):
        # „dzialki” to drugie słowo nagłówka „Nr dzialki”.
        self.assertEqual(self._klik("dzialki")["label"], "Nr dzialki")


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class ObszarOdczytuTests(unittest.TestCase):
    """Rysowanie prostokąta, z którego czytana jest wartość."""

    @classmethod
    def setUpClass(cls):
        TabelaWKratkeTests.setUpClass()
        cls.pdf = TabelaWKratkeTests.pdf
        cls.page = TabelaWKratkeTests.page

    @classmethod
    def tearDownClass(cls):
        TabelaWKratkeTests.tearDownClass()

    def _rect_slowa(self, tekst):
        from PySide6.QtCore import QRectF

        slowo = next(w for w in self.page.words if tekst in w.text)
        return QRectF(
            slowo.rect.left() - 6,
            slowo.rect.top() - 4,
            slowo.rect.width() + 12,
            slowo.rect.height() + 8,
        )

    def test_odczyt_jednej_wartosci(self):
        self.assertEqual(text_in_rect(self.page, self._rect_slowa("0.0235")), "0.0235")

    def test_odczyt_slowa_z_przecinkiem(self):
        self.assertIn("BOJANO", text_in_rect(self.page, self._rect_slowa("BOJANO")))

    def test_pusty_obszar_daje_pusty_tekst(self):
        from PySide6.QtCore import QRectF

        self.assertEqual(text_in_rect(self.page, QRectF(5, 700, 40, 20)), "")

    def test_szerszy_obszar_laczy_slowa(self):
        from PySide6.QtCore import QRectF

        slowo = next(w for w in self.page.words if "0.0235" in w.text)
        szeroki = QRectF(
            slowo.rect.left() - 200, slowo.rect.top() - 4, 320, slowo.rect.height() + 8
        )
        wynik = text_in_rect(self.page, szeroki)
        self.assertIn("0.0235", wynik)
        self.assertIn("145/7", wynik)

    def test_read_area_value_z_procentow(self):
        obraz = self.page.image
        rect = self._rect_slowa("0.0235")
        area = {
            "x": rect.left() / obraz.width() * 100.0,
            "y": rect.top() / obraz.height() * 100.0,
            "w": rect.width() / obraz.width() * 100.0,
            "h": rect.height() / obraz.height() * 100.0,
            "page": 0,
        }
        self.assertEqual(read_area_value(self.pdf, area), "0.0235")

    def test_brak_obszaru_daje_pusty_tekst(self):
        self.assertEqual(read_area_value(self.pdf, {}), "")

    def test_tryb_rysowania_zmienia_kursor(self):
        widok = WypisPdfView()
        widok.set_page(self.page)
        widok.set_draw_mode(True)
        self.assertTrue(widok._draw_mode)
        widok.set_draw_mode(False)
        self.assertFalse(widok._draw_mode)


@unittest.skipIf(
    QApplication is None or fitz is None, "PySide6 lub PyMuPDF nie jest dostępne"
)
class ObszarWOknieTests(unittest.TestCase):
    """Obszar zapisany we wzorze i użyty przy odczycie."""

    @classmethod
    def setUpClass(cls):
        TabelaWKratkeTests.setUpClass()
        cls.pdf = TabelaWKratkeTests.pdf

    @classmethod
    def tearDownClass(cls):
        TabelaWKratkeTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def _wiersz(self, nazwa):
        for row in range(self.dialog.table.rowCount()):
            if self.dialog.table.item(row, 0).text() == nazwa:
                return row
        raise AssertionError(f"brak wiersza {nazwa!r}")

    def _narysuj(self, nazwa_pola, tekst_slowa):
        from PySide6.QtCore import QRectF

        row = self._wiersz(nazwa_pola)
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_area.setChecked(True)
        slowo = next(
            w for w in self.dialog.page_view.page.words if tekst_slowa in w.text
        )
        rect = QRectF(
            slowo.rect.left() - 6,
            slowo.rect.top() - 4,
            slowo.rect.width() + 12,
            slowo.rect.height() + 8,
        )
        self.dialog._on_area_selected(
            {"rect": rect, "text": text_in_rect(self.dialog.page_view.page, rect)}
        )
        return row

    def test_tryb_obszaru_wlacza_rysowanie(self):
        self.dialog.btn_mode_area.setChecked(True)
        self.assertEqual(self.dialog._click_mode(), "area")
        self.assertTrue(self.dialog.page_view._draw_mode)

    def test_narysowany_obszar_daje_wartosc(self):
        row = self._narysuj("Numer księgi wieczystej", "0.0235")
        self.assertEqual(self.dialog.table.item(row, 4).text(), "0.0235")

    def test_stan_pokazuje_obszar(self):
        row = self._narysuj("Numer księgi wieczystej", "0.0235")
        self.assertIn("obszar", self.dialog.table.item(row, 3).text())

    def test_obszar_zapisany_we_wzorze(self):
        self._narysuj("Numer księgi wieczystej", "0.0235")
        index = self.dialog._current_index()
        self.assertIn("kw", self.dialog.profiles[index]["areas"])

    def test_obszar_da_sie_cofnac(self):
        row = self._narysuj("Numer księgi wieczystej", "0.0235")
        self.dialog._undo_change()
        self.assertNotIn("kw", self.dialog._areas)
        self.assertNotEqual(self.dialog.table.item(row, 4).text(), "0.0235")

    def test_usuniecie_pola_kasuje_obszar(self):
        row = self._narysuj("Numer księgi wieczystej", "0.0235")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog._clear_row()
        self.assertNotIn("kw", self.dialog._areas)

    def test_obszar_wygrywa_z_dopasowaniem_tekstu(self):
        # Pole „Obręb” czyta się samo, ale obszar ma pierwszeństwo.
        row = self._narysuj("Obręb", "0.0235")
        self.assertEqual(self.dialog.table.item(row, 4).text(), "0.0235")


@unittest.skipIf(QApplication is None, "PySide6 nie jest dostępne")
class SkladanieTekstuTests(unittest.TestCase):
    def test_fold_usuwa_ogonki(self):
        self.assertEqual(_fold("Województwo"), "wojewodztwo")

    def test_fold_scala_spacje(self):
        self.assertEqual(_fold("  Adres   nieruchomości "), "adres nieruchomosci")


if __name__ == "__main__":
    unittest.main()


class PionowaListaPolTests(unittest.TestCase):
    """Runda 19: pionowa lista pól — klik nie może trafiać w pole wyżej."""

    @classmethod
    def setUpClass(cls):
        cls.pdf = _pionowy_wypis()
        cls.page = load_page(cls.pdf) if cls.pdf else None

    def _klik(self, tekst):
        slowo = next(w for w in self.page.words if tekst in w.text)
        punkt = QPoint(
            int(slowo.rect.center().x()), int(slowo.rect.center().y())
        )
        return label_at(self.page, punkt)

    def test_kazde_pole_zwraca_siebie_a_nie_pole_wyzej(self):
        if self.page is None:
            self.skipTest("brak PyMuPDF")
        for nazwa in ("Wojewodztwo", "Powiat", "Gmina", "Obreb"):
            with self.subTest(pole=nazwa):
                self.assertEqual(self._klik(nazwa)["label"], nazwa)

    def test_klik_w_wartosc_zwraca_etykiete_z_tego_samego_wiersza(self):
        if self.page is None:
            self.skipTest("brak PyMuPDF")
        for wartosc, etykieta in (
            ("POMORSKIE", "Wojewodztwo"),
            ("kartuski", "Powiat"),
            ("BOJANO", "Obreb"),
        ):
            with self.subTest(wartosc=wartosc):
                trafienie = self._klik(wartosc)
                self.assertEqual(trafienie["label"], etykieta)
                self.assertIn(wartosc, trafienie["value"])

    def test_naglowek_nie_jest_brany_z_gory_listy(self):
        if self.page is None:
            self.skipTest("brak PyMuPDF")
        self.assertNotEqual(self._klik("Obreb")["label"], "Wojewodztwo")


class NaglowekKolumnyTests(TabelaWKratkeTests):
    """Klik w sam nagłówek tabeli zwraca ten nagłówek, nie sąsiedni."""

    def test_naglowki_zwracaja_same_siebie(self):
        if self.page is None:
            self.skipTest("brak PyMuPDF")
        for tekst, oczekiwany in (
            ("dzialki", "Nr dzialki"),
            ("uzytku", "Opis uzytku"),
        ):
            with self.subTest(naglowek=tekst):
                self.assertEqual(self._klik(tekst)["label"], oczekiwany)

    def test_dane_wciaz_znajduja_naglowek_nad_soba(self):
        if self.page is None:
            self.skipTest("brak PyMuPDF")
        for tekst, oczekiwany in (
            ("0.0235", "Pow. [ha]"),
            ("145/8", "Nr dzialki"),
            ("RIVa", "Opis uzytku"),
        ):
            with self.subTest(wartosc=tekst):
                self.assertEqual(self._klik(tekst)["label"], oczekiwany)


class ZakladkaTekstowaTests(unittest.TestCase):
    """Runda 20: w zakładce „Tekst dokumentu” wskazujemy wartość."""

    TEKST = (
        "Wojewodztwo   POMORSKIE\n"
        "Powiat   kartuski\n"
        "Obreb   0019, BOJANO\n"
    )

    def _dialog(self):
        from modules.wypis_profil_dialog import WypisProfileDialog

        okno = WypisProfileDialog({})
        okno.pdf_text = self.TEKST
        return okno

    def test_znajduje_nazwe_pola_stojaca_przy_wartosci(self):
        if QApplication.instance() is None:
            self.skipTest("brak Qt")
        okno = self._dialog()
        try:
            self.assertEqual(okno._label_for_value("POMORSKIE"), "Wojewodztwo")
            self.assertEqual(okno._label_for_value("kartuski"), "Powiat")
        finally:
            okno.deleteLater()

    def test_nie_zwraca_nazwy_gdy_wartosci_nie_ma_w_tekscie(self):
        if QApplication.instance() is None:
            self.skipTest("brak Qt")
        okno = self._dialog()
        try:
            self.assertEqual(okno._label_for_value("CZEGO NIE MA"), "")
        finally:
            okno.deleteLater()

    def test_pomija_dane_i_bierze_nazwe_pola(self):
        if QApplication.instance() is None:
            self.skipTest("brak Qt")
        okno = self._dialog()
        try:
            # „0019,” stoi tuż przed „BOJANO”, ale to dana, nie nazwa.
            # Nazwą jest „Obreb” z lewej strony tego samego wiersza.
            self.assertEqual(okno._label_for_value("BOJANO"), "Obreb")
        finally:
            okno.deleteLater()

    def test_znajduje_nazwe_kolumny_z_wiersza_wyzej(self):
        if QApplication.instance() is None:
            self.skipTest("brak Qt")
        okno = self._dialog()
        okno.pdf_text = (
            "Obreb   Nr dzialki   Pow. [ha]   Opis uzytku\n"
            "0019, BOJANO   145/7   0.0235   dr\n"
        )
        try:
            for wartosc, oczekiwane in (
                ("145/7", "Nr dzialki"),
                ("0.0235", "Pow. [ha]"),
                ("dr", "Opis uzytku"),
            ):
                with self.subTest(wartosc=wartosc):
                    self.assertEqual(
                        okno._label_for_value(wartosc), oczekiwane
                    )
        finally:
            okno.deleteLater()

    def test_zaznaczenie_wielu_wierszy_nie_gubi_nazwy(self):
        if QApplication.instance() is None:
            self.skipTest("brak Qt")
        okno = self._dialog()
        try:
            # Qt oddziela wiersze znakiem separatora akapitu.
            self.assertEqual(
                okno._label_for_value("POMORSKIE\nPowiat"), "Wojewodztwo"
            )
        finally:
            okno.deleteLater()


class UsuwanieZPolaTests(unittest.TestCase):
    """Runda 23: „Usuń z pola” czyści też etykiety z trybu ETYKIETA (rysuj)."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.chk_auto.setChecked(False)
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def _wiersz(self, nazwa: str) -> int:
        for row in range(self.dialog.table.rowCount()):
            if self.dialog.table.item(row, 0).text() == nazwa:
                return row
        raise AssertionError(f"brak wiersza {nazwa!r}")

    def _etykieta_rysowana(self, row: int, tekst: str) -> None:
        """Udaje prostokąt narysowany w trybie „ETYKIETA (rysuj)”."""

        from PySide6.QtCore import QRect

        self.dialog.table.setCurrentCell(row, 1)
        self.dialog.btn_mode_area_label.setChecked(True)
        self.dialog._on_area_selected(
            {"rect": QRect(200, 150, 120, 20), "text": tekst}
        )

    def test_usuwa_etykiete_dodana_rysowaniem(self):
        row = self._wiersz("Powiat")
        self._etykieta_rysowana(row, "Powiat")
        self.assertTrue(self.dialog.table.item(row, 1).text().strip())

        self.dialog.table.setCurrentCell(row, 1)
        self.dialog._clear_row()
        self.assertEqual(self.dialog.table.item(row, 1).text(), "")

    def test_po_usunieciu_nie_ma_tez_wartosci(self):
        row = self._wiersz("Powiat")
        self._etykieta_rysowana(row, "Powiat")
        self.dialog.table.setCurrentCell(row, 1)
        self.dialog._clear_row()
        self.assertEqual(self.dialog.table.item(row, 4).text(), "")

    def test_usuwa_takze_wymuszony_kierunek(self):
        row = self._wiersz("Powiat")
        self._etykieta_rysowana(row, "Powiat")
        widget = self.dialog.table.cellWidget(row, 2)
        widget.setCurrentIndex(widget.findData("below"))

        self.dialog.table.setCurrentCell(row, 1)
        self.dialog._clear_row()
        profil = self.dialog._current_profile()
        self.assertNotIn("county", profil.get("directions", {}))
        self.assertEqual(widget.currentData(), "auto")

    def test_cofnij_przywraca_usunieta_etykiete(self):
        row = self._wiersz("Powiat")
        self._etykieta_rysowana(row, "Powiat")
        przed = self.dialog.table.item(row, 1).text()

        self.dialog.table.setCurrentCell(row, 1)
        self.dialog._clear_row()
        self.dialog._undo_change()
        self.assertEqual(self.dialog.table.item(row, 1).text(), przed)


class KierunekWTabeliTests(unittest.TestCase):
    """Runda 23: kolumna „Skąd czytać” i „Wypełnij automatycznie”."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.chk_auto.setChecked(False)
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def _wiersz(self, nazwa: str) -> int:
        for row in range(self.dialog.table.rowCount()):
            if self.dialog.table.item(row, 0).text() == nazwa:
                return row
        raise AssertionError(f"brak wiersza {nazwa!r}")

    def test_kazdy_wiersz_ma_wybor_kierunku(self):
        row = self._wiersz("Powiat")
        widget = self.dialog.table.cellWidget(row, 2)
        self.assertIsNotNone(widget)
        self.assertEqual(widget.count(), 7)
        self.assertEqual(
            [widget.itemData(i) for i in range(widget.count())],
            ["auto", "right", "left", "below", "below2", "above", "pick"],
        )

    def test_domyslnie_wybrany_jest_tryb_automatyczny(self):
        row = self._wiersz("Powiat")
        self.assertEqual(
            self.dialog.table.cellWidget(row, 2).currentData(), "auto"
        )

    def test_wybor_kierunku_zapisuje_sie_we_wzorze(self):
        row = self._wiersz("Powiat")
        widget = self.dialog.table.cellWidget(row, 2)
        widget.setCurrentIndex(widget.findData("below"))
        profil = self.dialog._current_profile()
        self.assertEqual(profil["directions"].get("county"), "below")

    def test_jest_przycisk_wypelnij_automatycznie(self):
        self.assertTrue(self.dialog.btn_autofill.isEnabled())
        self.assertIn("ypełnij", self.dialog.btn_autofill.text())

    def test_wypelnij_automatycznie_nie_psuje_odczytanych_pol(self):
        row = self._wiersz("Powiat")
        przed = self.dialog.table.item(row, 4).text()
        self.dialog._autofill()
        self.assertEqual(self.dialog.table.item(row, 4).text(), przed)


class UkladTabeliTests(unittest.TestCase):
    """Runda 25: tabela nie ma sama przestawiać kolumn ani wierszy."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.chk_auto.setChecked(False)
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def _szerokosci(self):
        return [self.dialog.table.columnWidth(c) for c in range(5)]

    def test_szerokosci_kolumn_nie_zmieniaja_sie_po_odczycie(self):
        przed = self._szerokosci()
        for _ in range(3):
            self.dialog._analyze()
        self.assertEqual(self._szerokosci(), przed)

    def test_wiersze_maja_rowna_wysokosc(self):
        wysokosci = {
            self.dialog.table.rowHeight(r)
            for r in range(min(10, self.dialog.table.rowCount()))
        }
        self.assertEqual(len(wysokosci), 1)

    def test_zmiana_kierunku_nie_rusza_kolumn(self):
        przed = self._szerokosci()
        widget = self.dialog.table.cellWidget(1, 2)
        widget.setCurrentIndex(widget.findData("below"))
        self.assertEqual(self._szerokosci(), przed)

    def test_zmiana_kierunku_zmienia_odczytana_wartosc(self):
        row = next(
            r
            for r in range(self.dialog.table.rowCount())
            if self.dialog.table.item(r, 0).text() == "Powiat"
        )
        widget = self.dialog.table.cellWidget(row, 2)
        przed = self.dialog.table.item(row, 4).text()
        self.assertTrue(przed)

        widget.setCurrentIndex(widget.findData("left"))
        self.assertEqual(self.dialog.table.item(row, 4).text(), "")

        widget.setCurrentIndex(widget.findData("auto"))
        self.assertEqual(self.dialog.table.item(row, 4).text(), przed)


class NaglowekTabeliTests(unittest.TestCase):
    """Runda 26: kliknięcie w nagłówek nie zaznacza całej kolumny."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.chk_auto.setChecked(False)
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def test_naglowek_nie_jest_klikalny(self):
        self.assertFalse(
            self.dialog.table.horizontalHeader().sectionsClickable()
        )

    def test_kolumn_nie_da_sie_przestawic(self):
        self.assertFalse(
            self.dialog.table.horizontalHeader().sectionsMovable()
        )

    def test_naglowek_nie_podswietla_sekcji(self):
        self.assertFalse(
            self.dialog.table.horizontalHeader().highlightSections()
        )

    def test_zaznaczenie_obejmuje_caly_wiersz(self):
        from PySide6.QtWidgets import QAbstractItemView

        self.assertEqual(
            self.dialog.table.selectionBehavior(),
            QAbstractItemView.SelectionBehavior.SelectRows,
        )

    def test_pierwsze_cztery_kolumny_nie_zmieniaja_szerokosci(self):
        przed = [self.dialog.table.columnWidth(c) for c in range(4)]
        self.dialog.resize(1200, 700)
        self.dialog.resize(1480, 940)
        self.dialog._analyze()
        self.assertEqual(
            [self.dialog.table.columnWidth(c) for c in range(4)], przed
        )


class PodswietlanieNaglowkaTests(unittest.TestCase):
    """Runda 27: nagłówek nie ma się podświetlać po najechaniu myszą."""

    @classmethod
    def setUpClass(cls):
        PodgladStronyTests.setUpClass()
        cls.pdf = PodgladStronyTests.pdf

    @classmethod
    def tearDownClass(cls):
        PodgladStronyTests.tearDownClass()

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog

        self.dialog = WypisProfileDialog({})
        self.dialog.show()

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def test_naglowek_nie_sledzi_kursora(self):
        # Sedno sprawy: sama obecność reguły „:hover” w arkuszu każe Qt
        # włączyć WA_Hover i wtedy kolumna rozjaśnia się pod myszą.
        from PySide6.QtCore import Qt

        naglowek = self.dialog.table.horizontalHeader()
        self.assertFalse(naglowek.testAttribute(Qt.WidgetAttribute.WA_Hover))

    def test_komorki_nie_sledza_kursora(self):
        from PySide6.QtCore import Qt

        widok = self.dialog.table.viewport()
        self.assertFalse(widok.testAttribute(Qt.WidgetAttribute.WA_Hover))

    def test_arkusz_nie_ma_regul_hover_dla_tabeli(self):
        styl = self.dialog.styleSheet()
        self.assertNotIn("QHeaderView::section:hover", styl)
        self.assertNotIn("QTableWidget::item:hover", styl)

    def test_naglowek_nie_sledzi_myszy(self):
        self.assertFalse(
            self.dialog.table.horizontalHeader().sectionsClickable()
        )


class WieleStronITabelaTests(unittest.TestCase):
    """Runda 28: ciasne kolumny i wypisy na kilku stronach."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        import fitz

        cls._dir = tempfile.mkdtemp()
        cls.pdf = str(Path(cls._dir) / "dwie_strony.pdf")
        doc = fitz.open()
        strona1 = [
            "G R U N T Y",
            "",
            "Numer          POWIERZCHNIA w ha        Numer",
            "dzialki        Uzytkow i klas  Dzialki  KW",
            "27/176         0.0235          0.0235   GD1R/00012345/6",
        ]
        strona2 = [
            "B U D Y N K I",
            "",
            "Numer dzialki      Powierzchnia zabudowy",
            "99/12              0.0450",
            "Wlasciciel   Anna Nowak",
        ]
        for tresc in (strona1, strona2):
            page = doc.new_page()
            y = 60
            for linia in tresc:
                page.insert_text((40, y), linia, fontsize=8)
                y += 18
        doc.save(cls.pdf)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls._dir, ignore_errors=True)

    def _linie(self):
        from modules.wypis_pdf_view import read_pdf_text

        return read_pdf_text(self.pdf).split("\n")

    def _kolumny(self, fragment: str):
        from utils.wypis_profiles import _split_columns

        for linia in self._linie():
            if fragment in linia:
                return [tekst for _start, tekst in _split_columns(linia)]
        raise AssertionError(f"brak linii z {fragment!r}")

    def test_ciasne_kolumny_nie_sklejaja_sie(self):
        # „0.0235” i numer KW dzieli wąska przerwa — wcześniej program
        # widział to jako jedną wartość „0.0235 GD1R/00012345/6”.
        kolumny = self._kolumny("27/176")
        self.assertIn("GD1R/00012345/6", kolumny)
        self.assertNotIn("0.0235 GD1R/00012345/6", kolumny)

    def test_numer_dzialki_jest_osobna_kolumna(self):
        self.assertEqual(self._kolumny("27/176")[0], "27/176")

    def test_slowa_jednej_nazwy_zostaja_razem(self):
        # Kontrola w drugą stronę: „Anna Nowak” to jedna wartość.
        self.assertIn("Anna Nowak", self._kolumny("Wlasciciel"))

    def test_tekst_ma_oznaczenia_stron(self):
        from modules.wypis_pdf_view import PAGE_MARK

        tresc = "\n".join(self._linie())
        self.assertIn(f"{PAGE_MARK} 1", tresc)
        self.assertIn(f"{PAGE_MARK} 2", tresc)

    def test_tekst_zawiera_dane_z_obu_stron(self):
        tresc = "\n".join(self._linie())
        self.assertIn("27/176", tresc)
        self.assertIn("99/12", tresc)

    def test_zmiana_strony_przewija_tekst(self):
        from PySide6.QtWidgets import QMessageBox

        stary = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        try:
            from modules.wypis_pdf_view import PAGE_MARK
            from modules.wypis_profil_dialog import WypisProfileDialog

            dialog = WypisProfileDialog({})
            dialog.show()
            dialog.load_pdf_path(self.pdf)
            dialog._change_page(1)

            self.assertEqual(dialog._page_index, 1)
            pozycja = dialog.text_view.textCursor().position()
            self.assertTrue(
                dialog.pdf_text[pozycja:].startswith(f"{PAGE_MARK} 2")
            )
        finally:
            QMessageBox.information = stary

    def test_obie_strony_daja_sie_wyswietlic(self):
        from modules.wypis_pdf_view import page_count

        self.assertEqual(page_count(self.pdf), 2)


class ZmianaStronyOdczytTests(unittest.TestCase):
    """Runda 30: zmiana strony ma zmieniać odczytane wartości."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        import fitz

        cls._dir = tempfile.mkdtemp()
        cls.pdf = str(Path(cls._dir) / "dwie.pdf")
        doc = fitz.open()
        for tytul, numer, powierzchnia in (
            ("S T R O N A 1", "27/176", "0.0235"),
            ("S T R O N A 2", "99/12", "0.9999"),
        ):
            page = doc.new_page()
            y = 60
            for linia in (
                tytul,
                "",
                "Numer dzialki     Powierzchnia",
                f"{numer}            {powierzchnia}",
            ):
                page.insert_text((40, y), linia, fontsize=9)
                y += 20
        doc.save(cls.pdf)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls._dir, ignore_errors=True)

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox

        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        from modules.wypis_profil_dialog import WypisProfileDialog
        from utils.wypis_profiles import normalize_profile

        self.dialog = WypisProfileDialog({})
        self.dialog.show()
        self.dialog.chk_auto.setChecked(False)
        self.dialog.profiles.append(
            normalize_profile(
                {
                    "name": "T",
                    "fields": {
                        "parcel_number": ["Numer dzialki"],
                        "area": ["Powierzchnia"],
                    },
                }
            )
        )
        self.dialog._reload_profile_combo("T")
        self.dialog.load_pdf_path(self.pdf)

    def tearDown(self):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information = self._info

    def _wartosc(self, nazwa):
        for row in range(self.dialog.table.rowCount()):
            if self.dialog.table.item(row, 0).text() == nazwa:
                return self.dialog.table.item(row, 4).text()
        raise AssertionError(f"brak wiersza {nazwa!r}")

    def test_pierwsza_strona_pokazuje_swoje_dane(self):
        self.assertEqual(self._wartosc("Numer działki"), "27/176")

    def test_zmiana_strony_zmienia_wartosci(self):
        self.dialog._change_page(1)
        self.assertEqual(self._wartosc("Numer działki"), "99/12")
        self.assertEqual(self._wartosc("Powierzchnia"), "0.9999")

    def test_powrot_na_pierwsza_strone_przywraca_dane(self):
        self.dialog._change_page(1)
        self.dialog._change_page(-1)
        self.assertEqual(self._wartosc("Numer działki"), "27/176")

    def test_sprawdz_ponownie_zachowuje_biezaca_strone(self):
        self.dialog._change_page(1)
        self.dialog._reread_and_analyze()
        self.assertEqual(self._wartosc("Numer działki"), "99/12")


class ObszarNaKazdejStronieTests(unittest.TestCase):
    """Runda 31: narysowany obszar może obowiązywać na wszystkich stronach."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        import fitz

        cls._dir = tempfile.mkdtemp()
        cls.pdf = str(Path(cls._dir) / "dwie.pdf")
        doc = fitz.open()
        for numer, powierzchnia in (("27/176", "0.0235"), ("99/12", "0.9999")):
            page = doc.new_page()
            y = 60
            for linia in (
                "W Y P I S",
                "",
                "Numer dzialki     Powierzchnia",
                f"{numer}            {powierzchnia}",
            ):
                page.insert_text((40, y), linia, fontsize=9)
                y += 20
        doc.save(cls.pdf)
        doc.close()

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls._dir, ignore_errors=True)

    def _obszar(self, all_pages: bool) -> dict:
        from modules.wypis_pdf_view import load_page

        strona = load_page(self.pdf, 0, dpi=96)
        slowo = next(w for w in strona.words if "27/176" in w.text)
        rect = slowo.rect
        szerokosc = strona.image.width()
        wysokosc = strona.image.height()
        return {
            "x": rect.left() / szerokosc * 100.0,
            "y": rect.top() / wysokosc * 100.0,
            "w": rect.width() / szerokosc * 100.0,
            "h": rect.height() / wysokosc * 100.0,
            "page": 0,
            "all_pages": all_pages,
        }

    def test_obszar_tylko_dla_swojej_strony(self):
        from modules.wypis_pdf_view import read_area_value

        obszar = self._obszar(False)
        # Mimo prośby o stronę 2 czytamy stronę zapisaną w obszarze.
        self.assertEqual(
            read_area_value(self.pdf, obszar, page_override=1), "27/176"
        )

    def test_obszar_na_kazdej_stronie_czyta_biezaca(self):
        from modules.wypis_pdf_view import read_area_value

        obszar = self._obszar(True)
        self.assertEqual(
            read_area_value(self.pdf, obszar, page_override=0), "27/176"
        )
        self.assertEqual(
            read_area_value(self.pdf, obszar, page_override=1), "99/12"
        )

    def test_profil_pamieta_ustawienie(self):
        from utils.wypis_profiles import normalize_profile

        profil = normalize_profile(
            {"name": "t", "areas": {"area": self._obszar(True)}}
        )
        self.assertTrue(profil["areas"]["area"]["all_pages"])

    def test_domyslnie_obszar_dotyczy_jednej_strony(self):
        from utils.wypis_profiles import normalize_profile

        profil = normalize_profile(
            {
                "name": "t",
                "areas": {"area": {"x": 1, "y": 2, "w": 3, "h": 4, "page": 0}},
            }
        )
        self.assertFalse(profil["areas"]["area"]["all_pages"])

