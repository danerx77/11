"""Testy formatowania pól z wypisów: jednostka, identyfikator, forma władania."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.wypis_fields import (  # noqa: E402
    DEFAULT_MUNICIPALITY_MODE,
    MODE_CITY_ONLY,
    MODE_FULL,
    MODE_KEEP_CITY,
    MUNICIPALITY_MODE_CHOICES,
    MUNICIPALITY_MODE_KEY,
    extract_ownership_form,
    format_municipality,
    format_municipality_for_config,
    format_ownership,
    identifier_matches_parcel,
    municipality_mode,
    normalize_parcel_identifier,
    normalize_share,
    parse_ownership_line,
    split_municipality,
)


class MunicipalitySplitTests(unittest.TestCase):
    def test_splits_gmina(self):
        self.assertEqual(split_municipality("Maki - G"), ("Maki", "G"))

    def test_splits_miasto(self):
        self.assertEqual(split_municipality("Maki - M"), ("Maki", "M"))

    def test_handles_missing_spaces(self):
        self.assertEqual(split_municipality("Maki-M"), ("Maki", "M"))

    def test_handles_en_dash(self):
        self.assertEqual(split_municipality("Maki – G"), ("Maki", "G"))

    def test_without_suffix(self):
        self.assertEqual(split_municipality("Kartuzy"), ("Kartuzy", ""))

    def test_two_word_city_keeps_its_name(self):
        self.assertEqual(
            split_municipality("Nowy Dwór Gdański - M"), ("Nowy Dwór Gdański", "M")
        )

    def test_empty(self):
        self.assertEqual(split_municipality(""), ("", ""))
        self.assertEqual(split_municipality(None), ("", ""))


class MunicipalityModeTests(unittest.TestCase):
    """Trzy warianty zamówione przez użytkownika."""

    def test_full_mode_keeps_original(self):
        self.assertEqual(format_municipality("Maki - G", MODE_FULL), "Maki - G")
        self.assertEqual(format_municipality("Maki - M", MODE_FULL), "Maki - M")

    def test_city_only_drops_every_suffix(self):
        self.assertEqual(format_municipality("Maki - G", MODE_CITY_ONLY), "Maki")
        self.assertEqual(format_municipality("Maki - M", MODE_CITY_ONLY), "Maki")

    def test_keep_city_marks_only_towns(self):
        self.assertEqual(format_municipality("Maki - G", MODE_KEEP_CITY), "Maki")
        self.assertEqual(format_municipality("Maki - M", MODE_KEEP_CITY), "Maki - M")

    def test_value_without_suffix_is_untouched_in_every_mode(self):
        for _, mode in MUNICIPALITY_MODE_CHOICES:
            with self.subTest(mode=mode):
                self.assertEqual(format_municipality("Kartuzy", mode), "Kartuzy")

    def test_multiple_units_are_formatted_one_by_one(self):
        self.assertEqual(
            format_municipality("Maki - G, Reda - M", MODE_CITY_ONLY),
            "Maki, Reda",
        )

    def test_multiple_units_deduplicate_after_formatting(self):
        self.assertEqual(
            format_municipality("Maki - G, Maki - M", MODE_CITY_ONLY), "Maki"
        )

    def test_default_mode_is_the_current_behaviour(self):
        self.assertEqual(DEFAULT_MUNICIPALITY_MODE, MODE_FULL)

    def test_mode_read_from_config(self):
        self.assertEqual(
            municipality_mode({MUNICIPALITY_MODE_KEY: MODE_CITY_ONLY}),
            MODE_CITY_ONLY,
        )

    def test_unknown_mode_falls_back(self):
        self.assertEqual(
            municipality_mode({MUNICIPALITY_MODE_KEY: "bzdura"}),
            DEFAULT_MUNICIPALITY_MODE,
        )

    def test_missing_config_falls_back(self):
        self.assertEqual(municipality_mode(None), DEFAULT_MUNICIPALITY_MODE)

    def test_config_helper(self):
        config = {MUNICIPALITY_MODE_KEY: MODE_KEEP_CITY}
        self.assertEqual(format_municipality_for_config("Maki - M", config), "Maki - M")
        self.assertEqual(format_municipality_for_config("Maki - G", config), "Maki")


class IdentifierTests(unittest.TestCase):
    """Przykłady podane wprost przez użytkownika."""

    def test_user_example_simple(self):
        self.assertEqual(
            normalize_parcel_identifier("110101 2 0010 202"),
            "110101_2.0010.202",
        )

    def test_user_example_with_slash_parcel(self):
        self.assertEqual(
            normalize_parcel_identifier("110101 2 0010 22 21"),
            "110101_2.0010.22/21",
        )

    def test_already_correct_value_is_untouched(self):
        self.assertEqual(
            normalize_parcel_identifier("110101_2.0010.202"),
            "110101_2.0010.202",
        )

    def test_already_correct_with_slash(self):
        self.assertEqual(
            normalize_parcel_identifier("110101_2.0010.22/21"),
            "110101_2.0010.22/21",
        )

    def test_mixed_separators(self):
        self.assertEqual(
            normalize_parcel_identifier("110101_2 0010.202"),
            "110101_2.0010.202",
        )

    def test_existing_slash_is_preserved(self):
        self.assertEqual(
            normalize_parcel_identifier("110101 2 0010 22/21"),
            "110101_2.0010.22/21",
        )

    def test_too_short_value_is_returned_unchanged(self):
        self.assertEqual(normalize_parcel_identifier("110101 2"), "110101 2")

    def test_non_numeric_head_is_left_alone(self):
        self.assertEqual(
            normalize_parcel_identifier("Obreb Maki dzialka 5"),
            "Obreb Maki dzialka 5",
        )

    def test_empty(self):
        self.assertEqual(normalize_parcel_identifier(""), "")
        self.assertEqual(normalize_parcel_identifier(None), "")

    def test_matching_parcel_number(self):
        self.assertTrue(identifier_matches_parcel("110101 2 0010 202", "202"))
        self.assertTrue(identifier_matches_parcel("110101 2 0010 22 21", "22/21"))

    def test_not_matching_parcel_number(self):
        self.assertFalse(identifier_matches_parcel("110101 2 0010 202", "203"))


class OwnershipTests(unittest.TestCase):
    def test_share_is_normalized(self):
        self.assertEqual(normalize_share("14 / 48"), "14/48")
        self.assertEqual(normalize_share("1/24"), "1/24")

    def test_share_without_fraction_is_kept(self):
        self.assertEqual(normalize_share("całość"), "całość")

    def test_forms_from_user_examples(self):
        self.assertEqual(extract_ownership_form("współwłasność"), "współwłasność")
        self.assertEqual(
            extract_ownership_form("wspólnosc ustawowa"), "wspólność ustawowa"
        )
        self.assertEqual(extract_ownership_form("udział łączny"), "udział łączny")

    def test_form_is_found_inside_a_longer_line(self):
        self.assertEqual(
            extract_ownership_form("Forma władania: użytkowanie wieczyste"),
            "użytkowanie wieczyste",
        )

    def test_unknown_form_gives_empty(self):
        self.assertEqual(extract_ownership_form("brak danych"), "")

    def test_parse_line_with_share_and_form(self):
        self.assertEqual(
            parse_ownership_line("14/48 współwłasność"),
            {"share": "14/48", "form": "współwłasność"},
        )

    def test_parse_empty_line(self):
        self.assertEqual(parse_ownership_line(""), {"share": "", "form": ""})

    def test_format_joins_share_and_form(self):
        self.assertEqual(format_ownership("14/48", "współwłasność"), "14/48 współwłasność")

    def test_format_with_only_one_value(self):
        self.assertEqual(format_ownership("14/48", ""), "14/48")
        self.assertEqual(format_ownership("", "współwłasność"), "współwłasność")
        self.assertEqual(format_ownership("", ""), "")


if __name__ == "__main__":
    unittest.main()


class WypisTableWiringTests(unittest.TestCase):
    """Kolumna „Forma władania” i użycie ustawień w module Wypisy."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.source = (root / "modules" / "wypisy.py").read_text(encoding="utf-8")
        cls.pdf_source = (root / "utils" / "pdf_utils.py").read_text(encoding="utf-8")

    def test_table_has_the_ownership_column(self):
        self.assertIn("'Forma władania'", self.source)

    def test_table_has_24_columns(self):
        self.assertIn("QTableWidget(0, 24)", self.source)

    def test_municipality_uses_the_configured_mode(self):
        self.assertIn("format_municipality_for_config", self.source)

    def test_identifier_is_normalized_in_the_table(self):
        self.assertIn("normalize_parcel_identifier", self.source)

    def test_parser_reads_the_ownership_form(self):
        self.assertIn("ownership_form", self.pdf_source)
        self.assertIn("extract_ownership_form", self.pdf_source)

    def test_edit_map_skips_the_new_column(self):
        """Po dodaniu kolumny edycja nie może zapisywać do złego pola."""
        self.assertIn("13: 'ownership_form'", self.source)
        self.assertIn("22: 'precinct_number'", self.source)
