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
        item = self.dialog.table.item(row, 3)
        self.assertTrue(item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_kolumna_stanu_nie_jest_edytowalna(self):
        row = self._wiersz("Powiat")
        item = self.dialog.table.item(row, 2)
        self.assertFalse(item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_wpisana_wartosc_zostaje_zapamietana(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 3).setText("wejherowski")
        self.assertEqual(self.dialog._manual_values.get("county"), "wejherowski")

    def test_wpisana_wartosc_zmienia_stan(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 3).setText("wejherowski")
        self.assertIn("ręcznie", self.dialog.table.item(row, 2).text())

    def test_ponowna_analiza_nie_kasuje_recznej_wartosci(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 3).setText("wejherowski")
        self.dialog._analyze()
        self.assertEqual(self.dialog.table.item(row, 3).text(), "wejherowski")

    def test_skasowanie_wraca_do_odczytu(self):
        row = self._wiersz("Powiat")
        odczyt = self.dialog.table.item(row, 3).text()
        self.dialog.table.item(row, 3).setText("wejherowski")
        self.dialog.table.item(row, 3).setText("")
        self.assertEqual(self.dialog.table.item(row, 3).text(), odczyt)
        self.assertNotIn("county", self.dialog._manual_values)

    def test_wartosc_trafia_do_wzoru(self):
        row = self._wiersz("Powiat")
        self.dialog.table.item(row, 3).setText("wejherowski")
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

    def test_tryb_wartosci_nie_rusza_etykiet(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        przed = self.dialog.table.item(row, 1).text()
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.assertEqual(self.dialog.table.item(row, 1).text(), przed)

    def test_tryb_wartosci_wpisuje_do_kolumny_wartosci(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.assertEqual(self.dialog.table.item(row, 3).text(), "0,4500")

    def test_tryb_wartosci_ustawia_stan_reczny(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.assertIn("ręcznie", self.dialog.table.item(row, 2).text())

    def test_wskazana_wartosc_da_sie_cofnac(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        przed = self.dialog.table.item(row, 3).text()
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        self.dialog._undo_change()
        self.assertEqual(self.dialog.table.item(row, 3).text(), przed)

    def test_wskazana_wartosc_trafia_do_wzoru(self):
        row = self._wiersz("Numer księgi wieczystej")
        self.dialog.table.setCurrentCell(row, 0)
        self.dialog.btn_mode_value.setChecked(True)
        self._klik("0,4500")
        index = self.dialog._current_index()
        self.assertEqual(
            self.dialog.profiles[index]["manual_values"].get("kw"), "0,4500"
        )


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


@unittest.skipIf(QApplication is None, "PySide6 nie jest dostępne")
class SkladanieTekstuTests(unittest.TestCase):
    def test_fold_usuwa_ogonki(self):
        self.assertEqual(_fold("Województwo"), "wojewodztwo")

    def test_fold_scala_spacje(self):
        self.assertEqual(_fold("  Adres   nieruchomości "), "adres nieruchomosci")


if __name__ == "__main__":
    unittest.main()
