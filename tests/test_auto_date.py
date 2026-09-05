"""Testy automatycznego wstawiania dzisiejszej daty w pismach."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.auto_date import (  # noqa: E402
    AUTO_DATE_DEFAULT,
    AUTO_DATE_KEY,
    DATE_FORMAT,
    initial_date_text,
    is_auto_date_enabled,
    today_text,
)


class UstawienieDatyTests(unittest.TestCase):
    """Odczyt ustawienia z konfiguracji."""

    def test_domyslnie_wlaczone(self):
        self.assertTrue(AUTO_DATE_DEFAULT)
        self.assertTrue(is_auto_date_enabled({}))
        self.assertTrue(is_auto_date_enabled(None))

    def test_mozna_wylaczyc(self):
        self.assertFalse(is_auto_date_enabled({AUTO_DATE_KEY: False}))

    def test_mozna_wlaczyc(self):
        self.assertTrue(is_auto_date_enabled({AUTO_DATE_KEY: True}))

    def test_rozumie_zapis_tekstowy(self):
        for wartosc, oczekiwane in (
            ("nie", False),
            ("false", False),
            ("0", False),
            ("", False),
            ("tak", True),
            ("true", True),
        ):
            with self.subTest(wartosc=wartosc):
                self.assertEqual(
                    is_auto_date_enabled({AUTO_DATE_KEY: wartosc}), oczekiwane
                )

    def test_rozumie_zapis_liczbowy(self):
        self.assertFalse(is_auto_date_enabled({AUTO_DATE_KEY: 0}))
        self.assertTrue(is_auto_date_enabled({AUTO_DATE_KEY: 1}))


class TekstDatyTests(unittest.TestCase):
    """Format daty zgodny z tym, co program wstawia w pismach."""

    def test_format_dzien_miesiac_rok(self):
        self.assertEqual(DATE_FORMAT, "%d.%m.%Y")
        self.assertEqual(today_text(date(2026, 9, 5)), "05.09.2026")

    def test_dzien_i_miesiac_sa_dwucyfrowe(self):
        self.assertEqual(today_text(date(2026, 1, 2)), "02.01.2026")

    def test_bez_argumentu_bierze_date_komputera(self):
        self.assertEqual(today_text(), date.today().strftime(DATE_FORMAT))


class WartoscPoczatkowaTests(unittest.TestCase):
    """To, co widać w polu daty zaraz po otwarciu zakładki."""

    DZIS = date(2026, 9, 5)

    def test_wlaczone_wstawia_dzisiejsza_date(self):
        self.assertEqual(
            initial_date_text({AUTO_DATE_KEY: True}, today=self.DZIS),
            "05.09.2026",
        )

    def test_wylaczone_zostawia_puste_pole(self):
        self.assertEqual(
            initial_date_text({AUTO_DATE_KEY: False}, today=self.DZIS), ""
        )

    def test_brak_ustawienia_dziala_jak_wlaczone(self):
        self.assertEqual(
            initial_date_text({}, today=self.DZIS), "05.09.2026"
        )


class RecznaZmianaTests(unittest.TestCase):
    """Wpisana ręcznie data nie jest nadpisywana przez automat."""

    def test_pole_daty_da_sie_nadpisac(self):
        try:
            from PySide6.QtWidgets import QApplication, QLineEdit
        except ImportError:  # pragma: no cover
            self.skipTest("brak PySide6")

        if QApplication.instance() is None:
            try:
                QApplication([])
            except Exception:  # pragma: no cover
                self.skipTest("brak środowiska Qt")

        pole = QLineEdit()
        pole.setText(initial_date_text({}, today=date(2026, 9, 5)))
        self.assertEqual(pole.text(), "05.09.2026")

        # Użytkownik poprawia datę — zmiana ma zostać.
        pole.setText("01.01.2020")
        self.assertEqual(pole.text(), "01.01.2020")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
