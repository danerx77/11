"""Testy odmiany miejscowości stosowanej wyłącznie podczas podmiany tagów."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

try:
    from docx import Document
    from utils.docx_utils import apply_declension_preferences, generate_declaration
except ModuleNotFoundError:
    # Minimalne testy reguł nie wymagają python-docx. Testy integracyjne są
    # wykonywane automatycznie tam, gdzie zależność aplikacji jest dostępna.
    Document = None
    apply_declension_preferences = None
    generate_declaration = None

from utils.polish_declension import (
    decline_city,
    format_city_declension_overrides,
    parse_city_declension_overrides,
)


class CityDeclensionTests(unittest.TestCase):
    def test_regular_endings_cover_common_city_types(self):
        cases = {
            # -owo / -ewo, -ino / -yno, -ko / -no
            "Żukowo": "Żukowie",
            "Grabowo": "Grabowie",
            "Luzino": "Luzinie",
            "Chwaszczyno": "Chwaszczynie",
            "Kielno": "Kielnie",
            "Wicko": "Wicku",
            # liczba mnoga
            "Sierakowice": "Sierakowicach",
            "Kartuzy": "Kartuzach",
            "Czaple": "Czaplach",
            "Trąbki": "Trąbkach",
            # żeńskie
            "Stężyca": "Stężycy",
            "Kobylnica": "Kobylnicy",
            "Gdynia": "Gdyni",
            "Wieliczka": "Wieliczce",
            "Czerska": "Czerskiej",
            # męskie zakończone spółgłoską
            "Czersk": "Czersku",
            "Tczew": "Tczewie",
            "Przywidz": "Przywidzu",
            "Karsin": "Karsinie",
            "Żywiec": "Żywcu",
        }
        for source, expected in cases.items():
            with self.subTest(city=source):
                self.assertEqual(decline_city(source), expected)

    def test_regular_compound_and_hyphenated_city_names(self):
        cases = {
            "Stara Wieś": "Starej Wsi",
            "Tomaszów Mazowiecki": "Tomaszowie Mazowieckim",
            "Biała Podlaska": "Białej Podlaskiej",
            "Krynica-Zdrój": "Krynicy-Zdroju",
            "Skarżysko-Kamienna": "Skarżysku-Kamiennej",
            "Nowy Dwór Gdański": "Nowym Dworze Gdańskim",
            "Góra Kalwaria": "Górze Kalwarii",
            "Kostrzyn nad Odrą": "Kostrzynie nad Odrą",
            "Nowe Miasto nad Pilicą": "Nowym Mieście nad Pilicą",
        }
        for source, expected in cases.items():
            with self.subTest(city=source):
                self.assertEqual(decline_city(source), expected)

    def test_dictionary_precedes_county_check_and_preserves_case(self):
        self.assertEqual(
            decline_city("Pruszcz Gdański"), "Pruszczu Gdańskim"
        )
        self.assertEqual(decline_city("Nowa Wieś"), "Nowej Wsi")
        self.assertEqual(decline_city("Kwidzyn"), "Kwidzynie")
        self.assertEqual(decline_city("RUDA ŚLĄSKA"), "RUDZIE ŚLĄSKIEJ")
        self.assertEqual(decline_city("ŻUKOWO"), "ŻUKOWIE")
        self.assertEqual(decline_city("gdański"), "gdański")

    def test_custom_forms_are_parsed_and_take_precedence(self):
        text = """
            # forma nieregularna
            Stara Wieś = Starej Wsi
            Testowo => Testowie
            Inne Miasto → Innym Mieście
        """
        overrides = parse_city_declension_overrides(text)
        self.assertEqual(overrides["Stara Wieś"], "Starej Wsi")
        self.assertEqual(overrides["Testowo"], "Testowie")
        self.assertEqual(overrides["Inne Miasto"], "Innym Mieście")
        self.assertEqual(
            decline_city("80-000 Stara Wieś", overrides),
            "80-000 Starej Wsi",
        )
        self.assertEqual(
            decline_city("STARA WIEŚ", overrides), "STAREJ WSI"
        )
        self.assertEqual(
            format_city_declension_overrides(overrides),
            "Inne Miasto = Innym Mieście\n"
            "Stara Wieś = Starej Wsi\n"
            "Testowo = Testowie",
        )

    @unittest.skipUnless(Document, "python-docx is not installed")
    def test_preferences_only_transform_tag_values(self):
        location = "Nowa Wieś"
        street = "ul. Testowa"
        preferences = {
            "decl_location_locative": True,
            "decl_city_overrides": {"Nowa Wieś": "Nowej Wsi"},
        }

        tag_location, tag_street, tag_county = apply_declension_preferences(
            location, street, "", preferences
        )

        self.assertEqual(tag_location, "Nowej Wsi")
        self.assertEqual(tag_street, street)
        self.assertEqual(tag_county, "")
        self.assertEqual(location, "Nowa Wieś")
        self.assertEqual(street, "ul. Testowa")

    @unittest.skipUnless(Document, "python-docx is not installed")
    def test_docx_keeps_raw_address_and_declines_only_location_tag(self):
        with TemporaryDirectory() as temp_dir:
            template = Path(temp_dir) / "template.docx"
            output = Path(temp_dir) / "output.docx"
            document = Document()
            document.add_paragraph("Tag: <Miejscowość działki:>")
            document.add_paragraph("Adres: <Adres>")
            document.save(template)

            source_location = "Nowa Wieś"
            source_street = "ul. Testowa"
            success = generate_declaration(
                str(template),
                str(output),
                location=source_location,
                street=source_street,
                declension_options={
                    "decl_location_locative": True,
                    "decl_city_overrides": {"Nowa Wieś": "Nowej Wsi"},
                },
            )

            self.assertTrue(success)
            self.assertEqual(source_location, "Nowa Wieś")
            self.assertEqual(source_street, "ul. Testowa")
            output_text = "\n".join(
                paragraph.text for paragraph in Document(output).paragraphs
            )
            self.assertIn("Tag: Nowej Wsi", output_text)
            self.assertIn("Adres: ul. Testowa, Nowa Wieś", output_text)


if __name__ == "__main__":
    unittest.main()
