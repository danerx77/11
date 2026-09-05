"""Testy wydzielonej sekcji „Wypisy” w Ustawieniach.

Sekcja mieszka w osobnym pliku ``modules/ustawienia_wypisy.py``. Sprawdzamy,
że sama wczytuje ustawienia, sama je zapisuje i że nadal obsługuje te same
klucze konfiguracji, co przed wydzieleniem — czyli że nic nie zginęło.
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - brak GUI w środowisku
    QApplication = None

if QApplication is not None:
    try:
        from modules.ustawienia_wypisy import (
            DEFAULTS,
            FIX_IDENTIFIER_KEY,
            READ_OWNERSHIP_KEY,
            WypisSettingsSection,
        )
        from utils.wypis_fields import (
            DEFAULT_MUNICIPALITY_MODE,
            MUNICIPALITY_MODE_KEY,
        )
    except Exception:  # pragma: no cover - brak bibliotek Qt
        QApplication = None


_app = None


def setUpModule():  # noqa: N802 - nazwa wymagana przez unittest
    global _app
    if QApplication is not None:
        _app = QApplication.instance() or QApplication([])


@unittest.skipIf(QApplication is None, "PySide6 nie jest dostępne")
class SekcjaWypisyTests(unittest.TestCase):
    def setUp(self):
        self.section = WypisSettingsSection()

    def test_sekcja_ma_wlasny_tytul(self):
        self.assertIn("Wypisy", self.section.title())

    def test_pola_sa_dostepne(self):
        self.assertIsNotNone(self.section.municipality_mode)
        self.assertIsNotNone(self.section.chk_fix_identifier)
        self.assertIsNotNone(self.section.chk_read_ownership)
        self.assertIsNotNone(self.section.btn_profiles)

    def test_przycisk_wzorow_ma_czytelna_nazwe(self):
        self.assertIn("Wzory odczytu wypisów", self.section.btn_profiles.text())

    def test_domyslne_wartosci_gdy_konfiguracja_pusta(self):
        self.section.load_from_config({})
        self.assertTrue(self.section.chk_fix_identifier.isChecked())
        self.assertTrue(self.section.chk_read_ownership.isChecked())

    def test_wczytanie_wylaczonych_opcji(self):
        self.section.load_from_config(
            {FIX_IDENTIFIER_KEY: False, READ_OWNERSHIP_KEY: False}
        )
        self.assertFalse(self.section.chk_fix_identifier.isChecked())
        self.assertFalse(self.section.chk_read_ownership.isChecked())

    def test_zapis_zwraca_komplet_kluczy(self):
        values = self.section.settings()
        for key in (MUNICIPALITY_MODE_KEY, FIX_IDENTIFIER_KEY, READ_OWNERSHIP_KEY):
            self.assertIn(key, values)

    def test_zapis_trafia_do_konfiguracji(self):
        config = {}
        self.section.chk_fix_identifier.setChecked(False)
        self.section.save_to_config(config)
        self.assertFalse(config[FIX_IDENTIFIER_KEY])

    def test_pelny_obieg_odczyt_zapis(self):
        config = {FIX_IDENTIFIER_KEY: False, READ_OWNERSHIP_KEY: True}
        self.section.load_from_config(config)
        wynik = {}
        self.section.save_to_config(wynik)
        self.assertFalse(wynik[FIX_IDENTIFIER_KEY])
        self.assertTrue(wynik[READ_OWNERSHIP_KEY])

    def test_zapis_nie_wywala_sie_bez_konfiguracji(self):
        self.assertIsInstance(self.section.save_to_config(None), dict)

    def test_tryb_jednostki_ma_wartosc_domyslna(self):
        self.section.load_from_config({})
        self.assertEqual(
            self.section.municipality_mode.currentData(),
            DEFAULT_MUNICIPALITY_MODE,
        )

    def test_domyslne_sa_opisane_w_module(self):
        self.assertEqual(DEFAULTS[FIX_IDENTIFIER_KEY], True)
        self.assertEqual(DEFAULTS[READ_OWNERSHIP_KEY], True)

    def test_etykieta_wzorow_opisuje_plik(self):
        with TemporaryDirectory() as tmp:
            from utils.wypis_profiles import save_settings, default_profiles

            data_dir = Path(tmp) / "dane"
            save_settings(default_profiles(), data_dir=data_dir)
            text = self.section.refresh_profiles_label({})
        self.assertIn("Zapisanych wzorów", text)
        self.assertIn("wypis_profiles.json", text)


@unittest.skipIf(QApplication is None, "PySide6 nie jest dostępne")
class RozdzieleniePlikowTests(unittest.TestCase):
    """Kod sekcji ma być poza plikiem ogólnych ustawień."""

    def _read(self, name: str) -> str:
        root = Path(__file__).resolve().parent.parent
        return (root / "modules" / name).read_text(encoding="utf-8")

    def test_ustawienia_nie_buduja_juz_pol_wypisow(self):
        text = self._read("ustawienia.py")
        self.assertNotIn("chk_wypis_fix_identifier", text)
        self.assertNotIn("chk_wypis_read_ownership", text)
        self.assertNotIn("wypis_municipality_mode", text)

    def test_ustawienia_korzystaja_z_osobnej_sekcji(self):
        text = self._read("ustawienia.py")
        self.assertIn("from modules.ustawienia_wypisy import", text)
        self.assertIn("WypisSettingsSection", text)

    def test_okno_wzorow_podpiete_w_osobnym_pliku(self):
        text = self._read("ustawienia_wypisy.py")
        self.assertIn("WypisProfileDialog", text)


if __name__ == "__main__":
    unittest.main()
