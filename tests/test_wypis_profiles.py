"""Testy profili odczytu wypisów z PDF."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.wypis_profiles import (  # noqa: E402
    ACTIVE_KEY,
    AUTO_KEY,
    CONFIG_KEY,
    FIELD_KEYS,
    FIELD_LABELS,
    analyze_text,
    default_profiles,
    detect_profile,
    extract_field,
    find_profile,
    labels_for,
    load_profiles,
    normalize_profile,
    save_profiles,
    score_profile,
    summarize,
)

# Typowy wypis — etykieta i wartość w tej samej linii.
WYPIS_STANDARDOWY = """
WYPIS Z REJESTRU GRUNTÓW
Województwo: POMORSKIE
Powiat: kartuski
Jednostka ewidencyjna: Żukowo - G
Obręb ewidencyjny: 0010, MAKI
Oznaczenie działki: 12/3
Identyfikator działki: 220405_2.0010.12/3
Bliższe określenie położenia: MAKI, WYBICKIEGO J. 50
Powierzchnia działki: 0,1234 ha
Numer księgi wieczystej: GD1G/00012345/6
Właściciel: Kowalski Jan
Udział: 1/2
Forma władania: współwłasność
"""

# Inny urząd — inne nazwy pól, wartości w kolejnej linii.
WYPIS_INNY_URZAD = """
WYPIS UPROSZCZONY Z REJESTRU GRUNTÓW
Województwo
MAZOWIECKIE
Powiat
piaseczyński
Gmina
Lesznowola
Działka nr
44/2
Adres nieruchomości
Nowa Wola, ul. Górna 12
Pow. [ha]
0,4500
Nr KW
WA1I/00098765/1
"""


class NormalizeTests(unittest.TestCase):
    def test_pusty_profil_dostaje_wszystkie_pola(self):
        profile = normalize_profile(None)
        for key in FIELD_KEYS:
            with self.subTest(field=key):
                self.assertIn(key, profile["fields"])

    def test_pojedynczy_napis_staje_sie_lista(self):
        profile = normalize_profile({"fields": {"county": "Powiat"}})
        self.assertEqual(profile["fields"]["county"], ["Powiat"])

    def test_puste_etykiety_sa_usuwane(self):
        profile = normalize_profile({"fields": {"county": ["Powiat", "", "  "]}})
        self.assertEqual(profile["fields"]["county"], ["Powiat"])

    def test_powtorzenia_sa_usuwane(self):
        profile = normalize_profile({"fields": {"county": ["Powiat", "Powiat"]}})
        self.assertEqual(profile["fields"]["county"], ["Powiat"])

    def test_brak_nazwy_dostaje_zastepcza(self):
        self.assertEqual(normalize_profile({})["name"], "Nowy profil")


class LoadSaveTests(unittest.TestCase):
    def test_pusta_konfiguracja_daje_profile_wbudowane(self):
        profiles = load_profiles({})
        self.assertGreaterEqual(len(profiles), 2)
        self.assertTrue(all(p["builtin"] for p in profiles))

    def test_zapis_i_odczyt(self):
        config = {}
        wlasny = normalize_profile({"name": "Mój urząd", "fields": {"county": ["Powiat"]}})
        save_profiles(config, [wlasny])
        self.assertIn(CONFIG_KEY, config)
        wczytane = load_profiles(config)
        self.assertIsNotNone(find_profile(wczytane, "Mój urząd"))

    def test_wbudowane_sa_dopisywane_gdy_ich_brak(self):
        config = {CONFIG_KEY: [{"name": "Tylko mój", "fields": {}}]}
        profiles = load_profiles(config)
        self.assertIsNotNone(find_profile(profiles, "Standardowy (EGiB)"))

    def test_szukanie_ignoruje_wielkosc_liter_i_ogonki(self):
        profiles = default_profiles()
        self.assertIsNotNone(find_profile(profiles, "STANDARDOWY (EGIB)"))

    def test_klucze_konfiguracji_sa_rozne(self):
        self.assertNotEqual(CONFIG_KEY, ACTIVE_KEY)
        self.assertNotEqual(ACTIVE_KEY, AUTO_KEY)


class ExtractFieldTests(unittest.TestCase):
    def setUp(self):
        self.profile = find_profile(default_profiles(), "Standardowy (EGiB)")

    def test_wartosc_w_tej_samej_linii(self):
        self.assertEqual(
            extract_field(WYPIS_STANDARDOWY, self.profile, "county"), "kartuski"
        )

    def test_polozenie_dzialki(self):
        self.assertEqual(
            extract_field(WYPIS_STANDARDOWY, self.profile, "parcel_address"),
            "MAKI, WYBICKIEGO J. 50",
        )

    def test_identyfikator(self):
        self.assertEqual(
            extract_field(WYPIS_STANDARDOWY, self.profile, "identifier"),
            "220405_2.0010.12/3",
        )

    def test_forma_wladania(self):
        self.assertEqual(
            extract_field(WYPIS_STANDARDOWY, self.profile, "ownership_form"),
            "współwłasność",
        )

    def test_wartosc_w_nastepnej_linii(self):
        profile = find_profile(default_profiles(), "Wypis uproszczony")
        self.assertEqual(
            extract_field(WYPIS_INNY_URZAD, profile, "county"), "piaseczyński"
        )

    def test_brak_etykiety_daje_pusty_wynik(self):
        pusty = normalize_profile({"name": "Pusty"})
        self.assertEqual(extract_field(WYPIS_STANDARDOWY, pusty, "county"), "")

    def test_pusty_tekst(self):
        self.assertEqual(extract_field("", self.profile, "county"), "")

    def test_etykieta_bez_ogonkow_tez_dziala(self):
        tekst = "Wojewodztwo: POMORSKIE"
        self.assertEqual(
            extract_field(tekst, self.profile, "voivodeship"), "POMORSKIE"
        )

    def test_kolejna_linia_nie_bierze_innej_etykiety(self):
        tekst = "Powiat:\nGmina: Żukowo"
        # Po „Powiat:” stoi od razu inna etykieta — nie wolno jej wciągnąć.
        self.assertEqual(extract_field(tekst, self.profile, "county"), "")


class DetectProfileTests(unittest.TestCase):
    def test_rozpoznaje_wypis_standardowy(self):
        profile, score = detect_profile(default_profiles(), WYPIS_STANDARDOWY)
        self.assertIsNotNone(profile)
        self.assertGreater(score, 0)

    def test_rozpoznaje_wypis_uproszczony(self):
        profile, _score = detect_profile(default_profiles(), WYPIS_INNY_URZAD)
        self.assertEqual(profile["name"], "Wypis uproszczony")

    def test_pusty_tekst_nie_pasuje(self):
        profile, score = detect_profile(default_profiles(), "")
        self.assertIsNone(profile)
        self.assertEqual(score, 0)

    def test_znacznik_podnosi_ocene(self):
        z_markerem = score_profile(
            {"name": "x", "markers": ["wypis uproszczony"], "fields": {}},
            WYPIS_INNY_URZAD,
        )
        bez_markera = score_profile({"name": "x", "markers": [], "fields": {}}, WYPIS_INNY_URZAD)
        self.assertGreater(z_markerem, bez_markera)

    def test_wlasny_profil_moze_wygrac(self):
        wlasny = normalize_profile({
            "name": "Mój urząd",
            "markers": ["wypis uproszczony z rejestru"],
            "fields": {"county": ["Powiat"], "municipality": ["Gmina"]},
        })
        profile, _ = detect_profile([wlasny] + default_profiles(), WYPIS_INNY_URZAD)
        self.assertEqual(profile["name"], "Mój urząd")


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.profile = find_profile(default_profiles(), "Standardowy (EGiB)")

    def test_kazde_pole_ma_wiersz(self):
        rows = analyze_text(WYPIS_STANDARDOWY, self.profile)
        self.assertEqual(len(rows), len(FIELD_KEYS))

    def test_rozpoznane_pola_maja_wartosci(self):
        rows = {r["field"]: r for r in analyze_text(WYPIS_STANDARDOWY, self.profile)}
        self.assertEqual(rows["county"]["status"], "ok")
        self.assertEqual(rows["county"]["value"], "kartuski")

    def test_pole_nieobecne_w_dokumencie(self):
        rows = {r["field"]: r for r in analyze_text("Zupełnie inny tekst", self.profile)}
        self.assertEqual(rows["county"]["status"], "missing")

    def test_wiersz_zawiera_czytelna_etykiete(self):
        rows = analyze_text(WYPIS_STANDARDOWY, self.profile)
        for row in rows:
            with self.subTest(field=row["field"]):
                self.assertEqual(row["label"], FIELD_LABELS[row["field"]])

    def test_podsumowanie_liczy_pola(self):
        rows = analyze_text(WYPIS_STANDARDOWY, self.profile)
        text = summarize(rows)
        self.assertIn("Odczytano", text)
        self.assertIn(str(len(FIELD_KEYS)), text)


class LabelsForTests(unittest.TestCase):
    def test_zwraca_liste_etykiet(self):
        profile = find_profile(default_profiles(), "Standardowy (EGiB)")
        self.assertIn("Bliższe określenie położenia", labels_for(profile, "parcel_address"))

    def test_nieznane_pole_daje_pusta_liste(self):
        self.assertEqual(labels_for(default_profiles()[0], "nie_ma_takiego"), [])


if __name__ == "__main__":
    unittest.main()


class OverrideTests(unittest.TestCase):
    """Wzór własny poprawia błędny odczyt, wbudowany tylko uzupełnia."""

    def test_wbudowany_nie_nadpisuje(self):
        from utils.wypis_profiles import should_override

        self.assertFalse(should_override(default_profiles()[0]))

    def test_wlasny_nadpisuje(self):
        from utils.wypis_profiles import should_override

        wlasny = normalize_profile({"name": "Mój urząd"})
        self.assertTrue(should_override(wlasny))

    def test_mozna_wylaczyc_nadpisywanie(self):
        from utils.wypis_profiles import should_override

        wlasny = normalize_profile({"name": "Mój urząd", "override": False})
        self.assertFalse(should_override(wlasny))


class LabelBoundaryTests(unittest.TestCase):
    """Etykiety z nawiasami i kropkami też muszą działać."""

    def test_etykieta_z_nawiasem(self):
        profile = normalize_profile({"name": "x", "fields": {"area": ["Pow. [ha]"]}})
        self.assertEqual(
            extract_field("Pow. [ha]\n0,4500", profile, "area"), "0,4500"
        )

    def test_etykieta_z_kropka(self):
        profile = normalize_profile({"name": "x", "fields": {"area": ["Pow."]}})
        self.assertEqual(extract_field("Pow.: 1,2345", profile, "area"), "1,2345")

    def test_etykieta_ze_skrotem(self):
        profile = normalize_profile({"name": "x", "fields": {"kw": ["Nr KW"]}})
        self.assertEqual(
            extract_field("Nr KW: GD1G/00098765/1", profile, "kw"),
            "GD1G/00098765/1",
        )
