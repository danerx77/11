"""Testy rozdzielania położenia działki na miejscowość i ulicę."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.parcel_location import (  # noqa: E402
    ends_with_house_number,
    has_street_prefix,
    looks_like_street,
    split_many,
    split_parcel_location,
)


class ExamplesFromTheRequestTests(unittest.TestCase):
    """Przypadki podane wprost przez użytkownika."""

    def test_wersaliki_z_przecinkiem(self):
        result = split_parcel_location("MAKI, WYBICKIEGO J. 50")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "Wybickiego J. 50")

    def test_sama_ulica_z_przedrostkiem(self):
        result = split_parcel_location("ul. Górna 42")
        self.assertEqual(result.city, "")
        self.assertEqual(result.street, "ul. Górna 42")

    def test_miejscowosc_i_ulica_z_przedrostkiem(self):
        result = split_parcel_location("Maki, ul. Górna 42")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "ul. Górna 42")


class CityOnlyTests(unittest.TestCase):
    def test_sama_nazwa(self):
        result = split_parcel_location("Maki")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "")

    def test_wersaliki(self):
        self.assertEqual(split_parcel_location("ŻUKOWO").city, "Żukowo")

    def test_nazwa_dwuczlonowa(self):
        result = split_parcel_location("STARA KISZEWA")
        self.assertEqual(result.city, "Stara Kiszewa")
        self.assertEqual(result.street, "")

    def test_nazwa_z_mysnikiem(self):
        self.assertEqual(
            split_parcel_location("BIELSKO-BIALA").city, "Bielsko-Biala"
        )

    def test_gmina_nie_trafia_do_ulicy(self):
        result = split_parcel_location("Maki, gmina Żukowo")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "")


class StreetVariantsTests(unittest.TestCase):
    def test_bez_przedrostka_z_numerem(self):
        result = split_parcel_location("Górna 42")
        self.assertEqual(result.city, "")
        self.assertEqual(result.street, "Górna 42")

    def test_aleja(self):
        result = split_parcel_location("Maki, al. Jana Pawła II 15")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "al. Jana Pawła II 15")

    def test_osiedle(self):
        result = split_parcel_location("Maki, os. Słoneczne 3")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "os. Słoneczne 3")

    def test_plac(self):
        result = split_parcel_location("Gdańsk, plac Solidarności 1")
        self.assertEqual(result.city, "Gdańsk")
        self.assertEqual(result.street, "plac Solidarności 1")

    def test_bez_przecinka_z_przedrostkiem(self):
        result = split_parcel_location("Maki ul. Górna 42")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "ul. Górna 42")

    def test_numer_z_litera(self):
        result = split_parcel_location("MAKI, WYBICKIEGO 12A")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "Wybickiego 12A")

    def test_numer_z_ukosnikiem(self):
        result = split_parcel_location("MAKI, GÓRNA 12/3")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "Górna 12/3")

    def test_wielkie_litery_w_ulicy_sa_poprawiane(self):
        result = split_parcel_location("MAKI, UL. GÓRNA 42")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "ul. Górna 42")

    def test_inicjal_zostaje_wielka_litera(self):
        result = split_parcel_location("MAKI, WYBICKIEGO J. 50")
        self.assertIn("J.", result.street)


class EdgeCaseTests(unittest.TestCase):
    def test_pusty_tekst(self):
        result = split_parcel_location("")
        self.assertTrue(result.is_empty)

    def test_none(self):
        self.assertTrue(split_parcel_location(None).is_empty)

    def test_smieci_sa_pomijane(self):
        for value in ("brak", "-", "nie dotyczy", "B/D"):
            with self.subTest(value=value):
                self.assertTrue(split_parcel_location(value).is_empty)

    def test_nadmiarowe_spacje_i_przecinki(self):
        result = split_parcel_location("  MAKI ,   UL. GÓRNA 42 , ")
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "ul. Górna 42")

    def test_tekst_pisany_normalnie_nie_jest_zmieniany(self):
        result = split_parcel_location("Maki, ul. Świętego Wojciecha 5")
        self.assertEqual(result.street, "ul. Świętego Wojciecha 5")

    def test_sam_numer_nie_jest_ulica(self):
        result = split_parcel_location("42")
        self.assertEqual(result.street, "")


class HelperTests(unittest.TestCase):
    def test_has_street_prefix(self):
        self.assertTrue(has_street_prefix("ul. Górna"))
        self.assertTrue(has_street_prefix("AL. Jana Pawła"))
        self.assertFalse(has_street_prefix("Maki"))

    def test_ends_with_house_number(self):
        self.assertTrue(ends_with_house_number("Górna 42"))
        self.assertTrue(ends_with_house_number("Górna 12/3"))
        self.assertFalse(ends_with_house_number("Maki"))

    def test_looks_like_street(self):
        self.assertTrue(looks_like_street("ul. Górna"))
        self.assertTrue(looks_like_street("Wybickiego 50"))
        self.assertFalse(looks_like_street("Maki"))


class SplitManyTests(unittest.TestCase):
    def test_kilka_dzialek_w_jednej_miejscowosci(self):
        result = split_many([
            "MAKI, WYBICKIEGO J. 50",
            "MAKI, GÓRNA 12",
        ])
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "Wybickiego J. 50, Górna 12")

    def test_powtorzenia_sa_pomijane(self):
        result = split_many(["Maki, ul. Górna 42", "Maki, ul. Górna 42"])
        self.assertEqual(result.city, "Maki")
        self.assertEqual(result.street, "ul. Górna 42")

    def test_rozne_miejscowosci(self):
        result = split_many(["Maki, Górna 1", "Żukowo, Leśna 2"])
        self.assertEqual(result.city, "Maki, Żukowo")

    def test_pusta_lista(self):
        self.assertTrue(split_many([]).is_empty)


if __name__ == "__main__":
    unittest.main()
