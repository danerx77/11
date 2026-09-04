"""Testy rozpoznawania dokumentów w Menedżerze Drukowania."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from PySide6.QtWidgets import QApplication  # noqa: F401

    from modules.drukuj import PrintManagerWidget

    QT_AVAILABLE = True
except Exception:  # pragma: no cover - brak Qt w środowisku
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "PySide6 nie jest dostępne")
class FileKindTests(unittest.TestCase):
    """Rodzaj dokumentu rozpoznawany po nazwie pliku."""

    def test_budowa(self):
        self.assertEqual(
            PrintManagerWidget._file_kind("Kowalski Jan - Budowa.docx"),
            PrintManagerWidget.KIND_BUDOWA,
        )

    def test_demontaz_bez_ogonkow(self):
        self.assertEqual(
            PrintManagerWidget._file_kind("Kowalski - Demontaz.docx"),
            PrintManagerWidget.KIND_DEMONTAZ,
        )

    def test_demontaz_z_ogonkami(self):
        self.assertEqual(
            PrintManagerWidget._file_kind("Kowalski - Demontaż.docx"),
            PrintManagerWidget.KIND_DEMONTAZ,
        )

    def test_pismo(self):
        self.assertEqual(
            PrintManagerWidget._file_kind("Pismo przewodnie.docx"),
            PrintManagerWidget.KIND_PISMO,
        )

    def test_koperta(self):
        self.assertEqual(
            PrintManagerWidget._file_kind("Koperty zbiorcze.pdf"),
            PrintManagerWidget.KIND_KOPERTA,
        )

    def test_inne(self):
        self.assertEqual(
            PrintManagerWidget._file_kind("Zestawienie.xlsx"),
            PrintManagerWidget.KIND_INNE,
        )

    def test_wielkosc_liter_nie_ma_znaczenia(self):
        self.assertEqual(
            PrintManagerWidget._file_kind("KOWALSKI - BUDOWA.DOCX"),
            PrintManagerWidget.KIND_BUDOWA,
        )

    def test_kazdy_rodzaj_ma_etykiete(self):
        for kind in (
            PrintManagerWidget.KIND_BUDOWA,
            PrintManagerWidget.KIND_DEMONTAZ,
            PrintManagerWidget.KIND_PISMO,
            PrintManagerWidget.KIND_KOPERTA,
            PrintManagerWidget.KIND_INNE,
        ):
            with self.subTest(kind=kind):
                self.assertTrue(PrintManagerWidget.KIND_LABELS[kind])


@unittest.skipUnless(QT_AVAILABLE, "PySide6 nie jest dostępne")
class HumanSizeTests(unittest.TestCase):
    def test_brakujacy_plik_nie_wywraca_programu(self):
        self.assertEqual(
            PrintManagerWidget._human_size("/nie/ma/takiego/pliku.docx"), ""
        )

    def test_bajty(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as handle:
            handle.write(b"x" * 100)
            path = handle.name
        try:
            self.assertEqual(PrintManagerWidget._human_size(path), "100 B")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_kilobajty(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as handle:
            handle.write(b"x" * 4096)
            path = handle.name
        try:
            self.assertEqual(PrintManagerWidget._human_size(path), "4 KB")
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
