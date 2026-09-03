"""Testy konfigurowalnych nazw plików Oświadczeń woli i Pism przewodnich."""

import unittest

from utils.document_naming import (
    DECLARATION_PARCEL_MODE_KEY,
    DECLARATION_TEMPLATE_KEY,
    COVER_PARCEL_MODE_KEY,
    COVER_TEMPLATE_KEY,
    ASCII_KEY,
    NAME_STYLE_KEY,
    SPACE_KEY,
    cover_letter_filename,
    declaration_filename,
    document_naming_defaults,
    format_owner_name,
    format_parcel_suffix,
    preview_cover_filename,
    preview_declaration_filename,
    sanitize_filename,
)


class DefaultNamingTests(unittest.TestCase):
    def test_defaults_reproduce_current_declaration_name_for_many_parcels(self):
        name = declaration_filename(
            {},
            declaration_type="budowa",
            first_name="Jan",
            last_name="Kowalski",
            parcels=["12/3", "12/4"],
        )
        self.assertEqual(name, "Oświadczenie woli budowa J.Kowalski.docx")

    def test_defaults_do_not_add_the_parcel_number(self):
        """Domyślnie nazwa jest identyczna jak przed zmianą — bez działki."""
        name = declaration_filename(
            {},
            declaration_type="budowa",
            first_name="Jan",
            last_name="Kowalski",
            parcels=["12/3"],
        )
        self.assertEqual(name, "Oświadczenie woli budowa J.Kowalski.docx")

    def test_single_mode_adds_parcel_number_only_for_one_parcel(self):
        """Opcja włączona ręcznie: dopisek tylko przy jednej działce."""
        settings = {DECLARATION_PARCEL_MODE_KEY: "single"}
        one = declaration_filename(
            settings,
            declaration_type="budowa",
            first_name="Jan",
            last_name="Kowalski",
            parcels=["12/3"],
        )
        many = declaration_filename(
            settings,
            declaration_type="budowa",
            first_name="Jan",
            last_name="Kowalski",
            parcels=["12/3", "12/4"],
        )
        self.assertEqual(one, "Oświadczenie woli budowa J.Kowalski 12-3.docx")
        self.assertEqual(many, "Oświadczenie woli budowa J.Kowalski.docx")

    def test_defaults_reproduce_current_cover_letter_name(self):
        name = cover_letter_filename(
            {},
            first_name="Jan",
            last_name="Kowalski",
            parcels=["12/3", "12/4"],
        )
        self.assertEqual(name, "Pismo przewodnie J.Kowalski.docx")

    def test_second_address_suffix_is_preserved(self):
        name = cover_letter_filename(
            {},
            first_name="Jan",
            last_name="Kowalski",
            address_suffix="K",
            parcels=["12/3", "12/4"],
        )
        self.assertEqual(name, "Pismo przewodnie J.Kowalski K.docx")

    def test_defaults_dictionary_keeps_current_naming_untouched(self):
        """Bez ingerencji użytkownika nazwy plików się nie zmieniają."""
        defaults = document_naming_defaults()
        self.assertEqual(defaults[DECLARATION_PARCEL_MODE_KEY], "none")
        self.assertEqual(defaults[COVER_PARCEL_MODE_KEY], "none")


class ParcelSuffixTests(unittest.TestCase):
    def test_single_mode_returns_nothing_for_multiple_parcels(self):
        self.assertEqual(format_parcel_suffix(["1/1", "1/2"], mode="single"), "")
        self.assertEqual(format_parcel_suffix(["1/1"], mode="single"), "1/1")

    def test_always_mode_lists_every_parcel_sorted_naturally(self):
        self.assertEqual(
            format_parcel_suffix(["2/10", "2/3"], mode="always"),
            "2/3, 2/10",
        )

    def test_limit_mode_shortens_long_lists(self):
        self.assertEqual(
            format_parcel_suffix(["1", "2", "3", "4"], mode="limit", limit=2),
            "1, 2 i inne",
        )

    def test_none_mode_never_adds_parcels(self):
        self.assertEqual(format_parcel_suffix(["1/1"], mode="none"), "")

    def test_duplicates_are_removed_before_building_the_suffix(self):
        self.assertEqual(format_parcel_suffix(["1/1", "1/1"], mode="single"), "1/1")

    def test_parcel_dictionaries_from_wypisy_are_supported(self):
        self.assertEqual(
            format_parcel_suffix([{"number": "7/1"}], mode="single"),
            "7/1",
        )


class TemplateTests(unittest.TestCase):
    def test_custom_template_with_project_number_and_parcel_list(self):
        settings = {
            DECLARATION_TEMPLATE_KEY: "{projekt} {typ_wielkimi} {nazwisko} dz. {dzialki_lista}",
            DECLARATION_PARCEL_MODE_KEY: "always",
        }
        name = declaration_filename(
            settings,
            declaration_type="budowa",
            first_name="Jan",
            last_name="Kowalski",
            parcels=["12/3", "12/4"],
            project_number="OBI/1/2026",
        )
        self.assertEqual(name, "OBI-1-2026 BUDOWA J.Kowalski dz. 12-3, 12-4.docx")

    def test_always_mode_appends_all_parcels_with_default_template(self):
        name = declaration_filename(
            {DECLARATION_PARCEL_MODE_KEY: "always"},
            declaration_type="demontaz",
            first_name="Anna",
            last_name="Nowak",
            parcels=["5/1", "5/2"],
        )
        self.assertEqual(name, "Oświadczenie woli demontaz A.Nowak 5-1, 5-2.docx")

    def test_unknown_placeholder_is_ignored_instead_of_breaking_generation(self):
        name = cover_letter_filename(
            {COVER_TEMPLATE_KEY: "Pismo {nieistniejace} {nazwisko}"},
            first_name="Jan",
            last_name="Kowalski",
        )
        self.assertEqual(name, "Pismo J.Kowalski.docx")

    def test_empty_template_falls_back_to_the_default_one(self):
        name = cover_letter_filename(
            {COVER_TEMPLATE_KEY: "   "},
            first_name="Jan",
            last_name="Kowalski",
        )
        self.assertEqual(name, "Pismo przewodnie J.Kowalski.docx")

    def test_ascii_only_and_underscore_options(self):
        name = declaration_filename(
            {ASCII_KEY: True, SPACE_KEY: "_"},
            declaration_type="budowa",
            first_name="Łukasz",
            last_name="Żółć",
            parcels=["1/1"],
        )
        self.assertEqual(name, "Oswiadczenie_woli_budowa_L.Zolc.docx")

    def test_precinct_and_location_placeholders(self):
        name = cover_letter_filename(
            {COVER_TEMPLATE_KEY: "{obreb} {miejscowosc} {nazwisko}"},
            first_name="Jan",
            last_name="Kowalski",
            location="Gdynia",
            precinct="Polki",
        )
        self.assertEqual(name, "Polki Gdynia J.Kowalski.docx")


class NameStyleTests(unittest.TestCase):
    def test_initials_style_matches_previous_behaviour_including_couples(self):
        self.assertEqual(format_owner_name("Jan", "Kowalski"), "J.Kowalski")
        self.assertEqual(
            format_owner_name("Agata i Eryk", "Paradowscy"),
            "A.E.Paradowscy",
        )

    def test_alternative_name_styles(self):
        self.assertEqual(format_owner_name("Jan", "Kowalski", "full"), "Jan Kowalski")
        self.assertEqual(
            format_owner_name("Jan", "Kowalski", "last_first"), "Kowalski Jan"
        )
        self.assertEqual(format_owner_name("Jan", "Kowalski", "last_only"), "Kowalski")

    def test_missing_name_produces_readable_placeholder(self):
        self.assertEqual(format_owner_name("", ""), "BrakNazwiska")

    def test_name_style_setting_is_used_by_the_generator(self):
        name = declaration_filename(
            {NAME_STYLE_KEY: "full"},
            declaration_type="budowa",
            first_name="Jan",
            last_name="Kowalski",
        )
        self.assertEqual(name, "Oświadczenie woli budowa Jan Kowalski.docx")


class SanitizeTests(unittest.TestCase):
    def test_windows_forbidden_characters_are_removed(self):
        self.assertEqual(sanitize_filename('a<b>c:d"e|f?g*h'), "abcdefgh")

    def test_slashes_become_dashes_so_parcel_numbers_stay_readable(self):
        self.assertEqual(sanitize_filename("dz. 12/3"), "dz. 12-3")
        self.assertEqual(sanitize_filename("OBI/1/2026"), "OBI-1-2026")

    def test_repeated_spaces_are_collapsed(self):
        self.assertEqual(sanitize_filename("Pismo    przewodnie"), "Pismo przewodnie")

    def test_empty_name_never_produces_an_empty_file_name(self):
        self.assertEqual(sanitize_filename("   "), "dokument")


class PreviewTests(unittest.TestCase):
    def test_previews_use_the_current_settings(self):
        self.assertEqual(
            preview_declaration_filename({}),
            "Oświadczenie woli budowa J.Kowalski.docx",
        )
        self.assertEqual(
            preview_cover_filename({}),
            "Pismo przewodnie J.Kowalski.docx",
        )

    def test_preview_shows_the_parcel_option_when_enabled(self):
        self.assertEqual(
            preview_declaration_filename({DECLARATION_PARCEL_MODE_KEY: "single"}),
            "Oświadczenie woli budowa J.Kowalski 123-4.docx",
        )


if __name__ == "__main__":
    unittest.main()
