"""Test odczytu wypisu obejmującego kilka obrębów i gmin.

Zgłoszony błąd: program brał tylko pierwszą wartość pól „Obręb ewidencyjny”,
„Jednostka ewidencyjna”, „Powiat” i „Województwo”, choć jeden wypis może
zawierać działki z różnych obrębów. Tu sprawdzamy pełną ścieżkę: tekst PDF →
odczyt metadanych → przypisanie wartości do konkretnych działek.
"""

import tempfile
import unittest
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - brak biblioteki w środowisku CI
    fitz = None

if fitz is not None:
    from utils.pdf_utils import (
        extract_wypis_metadata_file,
        extract_wypis_parcel_metadata_file,
    )

WYPIS_TEXT = """WYPIS Z REJESTRU GRUNTOW
Województwo: pomorskie
Powiat: kartuski
Jednostka ewidencyjna: Żukowo
Obręb ewidencyjny: 0001, Polki
Numer działki: 12/3
Powierzchnia: 0,1500 ha

Województwo: pomorskie
Powiat: wejherowski
Jednostka ewidencyjna: Szemud
Obręb ewidencyjny: 0007, Borkowo
Numer działki: 45/2
Powierzchnia: 0,2300 ha
"""


@unittest.skipIf(fitz is None, 'PyMuPDF nie jest zainstalowany')
class WypisMultiMetadataPdfTests(unittest.TestCase):
    #: Czcionka z polskimi znakami — bez niej PDF gubi ogonki.
    POLISH_FONTS = (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'C:/Windows/Fonts/arial.ttf',
    )

    def _polish_font(self) -> str | None:
        for candidate in self.POLISH_FONTS:
            if Path(candidate).is_file():
                return candidate
        return None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = Path(self._tmp.name) / 'wypis.pdf'
        doc = fitz.open()
        page = doc.new_page()
        font_file = self._polish_font()
        if font_file:
            page.insert_font(fontname='pol', fontfile=font_file)
            font_name = 'pol'
        else:  # pragma: no cover - awaryjnie, gdy brak czcionki systemowej
            font_name = 'helv'
        # Każda linia osobno — insert_text nie łamie tekstu samodzielnie.
        y = 60
        for line in WYPIS_TEXT.splitlines():
            if line.strip():
                page.insert_text((50, y), line, fontsize=9, fontname=font_name)
            y += 14
        doc.save(str(path))
        doc.close()
        self.pdf_path = str(path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_precincts_are_reported_not_just_the_first(self):
        meta = extract_wypis_metadata_file(self.pdf_path)
        self.assertIn('Polki', meta['precinct_values'])
        self.assertIn('Borkowo', meta['precinct_values'])
        self.assertTrue(meta['has_multiple'])

    def test_all_counties_are_reported(self):
        meta = extract_wypis_metadata_file(self.pdf_path)
        self.assertIn('kartuski', meta['county_values'])
        self.assertIn('wejherowski', meta['county_values'])

    def test_all_municipalities_are_reported(self):
        meta = extract_wypis_metadata_file(self.pdf_path)
        self.assertIn('Żukowo', meta['municipality_values'])
        self.assertIn('Szemud', meta['municipality_values'])

    def test_single_voivodeship_is_not_duplicated(self):
        meta = extract_wypis_metadata_file(self.pdf_path)
        self.assertEqual(meta['voivodeship_values'], ['pomorskie'])
        self.assertEqual(meta['voivodeship'], 'pomorskie')

    def test_each_parcel_keeps_its_own_precinct(self):
        parcel_meta = extract_wypis_parcel_metadata_file(self.pdf_path)
        self.assertEqual(parcel_meta['12/3']['precinct'], 'Polki')
        self.assertEqual(parcel_meta['45/2']['precinct'], 'Borkowo')

    def test_each_parcel_keeps_its_own_county_and_municipality(self):
        parcel_meta = extract_wypis_parcel_metadata_file(self.pdf_path)
        self.assertEqual(parcel_meta['12/3']['county'], 'kartuski')
        self.assertEqual(parcel_meta['12/3']['municipality'], 'Żukowo')
        self.assertEqual(parcel_meta['45/2']['county'], 'wejherowski')
        self.assertEqual(parcel_meta['45/2']['municipality'], 'Szemud')

    def test_precinct_numbers_are_split_from_names(self):
        parcel_meta = extract_wypis_parcel_metadata_file(self.pdf_path)
        self.assertEqual(parcel_meta['12/3']['precinct_number'], '1')
        self.assertEqual(parcel_meta['45/2']['precinct_number'], '7')

    def test_unreadable_file_returns_empty_metadata(self):
        empty = extract_wypis_metadata_file('/nie/ma/takiego/pliku.pdf')
        self.assertEqual(empty['precinct'], '')
        self.assertEqual(empty['precinct_values'], [])
        self.assertFalse(empty['has_multiple'])
        self.assertEqual(extract_wypis_parcel_metadata_file('/brak.pdf'), {})


if __name__ == '__main__':
    unittest.main()
