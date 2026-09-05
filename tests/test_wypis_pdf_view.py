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
    from PySide6.QtCore import QPoint
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


@unittest.skipIf(QApplication is None, "PySide6 nie jest dostępne")
class SkladanieTekstuTests(unittest.TestCase):
    def test_fold_usuwa_ogonki(self):
        self.assertEqual(_fold("Województwo"), "wojewodztwo")

    def test_fold_scala_spacje(self):
        self.assertEqual(_fold("  Adres   nieruchomości "), "adres nieruchomosci")


if __name__ == "__main__":
    unittest.main()
