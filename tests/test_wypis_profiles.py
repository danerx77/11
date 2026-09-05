"""Testy profili odczytu wypisów z PDF."""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.global_settings import WYPIS_PROFILES_FILE  # noqa: E402
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
    _value_until_next_column,
    load_profiles,
    load_settings,
    migrate_from_config,
    normalize_profile,
    read_profiles_file,
    save_profiles,
    save_settings,
    score_profile,
    summarize,
    write_profiles_file,
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
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "dane"

    def tearDown(self):
        self._tmp.cleanup()

    def test_pusta_konfiguracja_daje_profile_wbudowane(self):
        profiles = load_profiles({}, self.data_dir)
        self.assertGreaterEqual(len(profiles), 2)
        self.assertTrue(all(p["builtin"] for p in profiles))

    def test_zapis_i_odczyt(self):
        wlasny = normalize_profile({"name": "Mój urząd", "fields": {"county": ["Powiat"]}})
        save_settings([wlasny], data_dir=self.data_dir)
        wczytane = load_profiles({}, self.data_dir)
        self.assertIsNotNone(find_profile(wczytane, "Mój urząd"))

    def test_wbudowane_sa_dopisywane_gdy_ich_brak(self):
        write_profiles_file(
            [normalize_profile({"name": "Tylko mój"})], data_dir=self.data_dir
        )
        profiles = load_profiles({}, self.data_dir)
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



class OsobnyPlikTests(unittest.TestCase):
    """Wzory mają mieszkać w dane/wypis_profiles.json, nie w app_config.json."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "dane"

    def tearDown(self):
        self._tmp.cleanup()

    def _plik(self) -> Path:
        return self.data_dir / WYPIS_PROFILES_FILE

    def test_zapis_tworzy_wlasny_plik(self):
        save_settings(default_profiles(), data_dir=self.data_dir)
        self.assertTrue(self._plik().is_file())

    def test_plik_ma_czytelna_budowe(self):
        wlasny = normalize_profile({"name": "Starostwo Kartuzy"})
        save_settings(
            [wlasny], active="Starostwo Kartuzy", auto=False, data_dir=self.data_dir
        )
        dane = json.loads(self._plik().read_text(encoding="utf-8"))
        self.assertEqual(dane["version"], 1)
        self.assertEqual(dane["active"], "Starostwo Kartuzy")
        self.assertFalse(dane["auto"])
        self.assertEqual(dane["profiles"][0]["name"], "Starostwo Kartuzy")

    def test_tryb_i_aktywny_wzor_wracaja_po_odczycie(self):
        save_settings(
            [normalize_profile({"name": "Mój"})],
            active="Mój",
            auto=False,
            data_dir=self.data_dir,
        )
        ustawienia = load_settings({}, self.data_dir)
        self.assertEqual(ustawienia["active"], "Mój")
        self.assertFalse(ustawienia["auto"])

    def test_brak_pliku_daje_ustawienia_domyslne(self):
        ustawienia = load_settings({}, self.data_dir)
        self.assertTrue(ustawienia["auto"])
        self.assertEqual(ustawienia["active"], "")
        self.assertGreaterEqual(len(ustawienia["profiles"]), 2)

    def test_uszkodzony_plik_nie_wywraca_programu(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._plik().write_text("{to nie jest JSON", encoding="utf-8")
        profile = load_profiles({}, self.data_dir)
        self.assertGreaterEqual(len(profile), 2)

    def test_zapis_nie_dopisuje_wzorow_do_konfiguracji(self):
        config = {}
        save_profiles(config, default_profiles(), self.data_dir)
        self.assertNotIn(CONFIG_KEY, config)


class MigracjaTests(unittest.TestCase):
    """Stare wzory z app_config.json mają trafić do osobnego pliku."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "dane"

    def tearDown(self):
        self._tmp.cleanup()

    def _stara_konfiguracja(self) -> dict:
        return {
            "theme": "dark",
            CONFIG_KEY: [{"name": "Stary urząd", "fields": {"county": ["Powiat"]}}],
            ACTIVE_KEY: "Stary urząd",
            AUTO_KEY: False,
        }

    def test_wzory_trafiaja_do_pliku(self):
        config = self._stara_konfiguracja()
        self.assertTrue(migrate_from_config(config, self.data_dir))
        profile = load_profiles({}, self.data_dir)
        self.assertIsNotNone(find_profile(profile, "Stary urząd"))

    def test_stare_klucze_znikaja_z_konfiguracji(self):
        config = self._stara_konfiguracja()
        migrate_from_config(config, self.data_dir)
        for key in (CONFIG_KEY, ACTIVE_KEY, AUTO_KEY):
            self.assertNotIn(key, config)

    def test_pozostale_ustawienia_zostaja_nietkniete(self):
        config = self._stara_konfiguracja()
        migrate_from_config(config, self.data_dir)
        self.assertEqual(config["theme"], "dark")

    def test_tryb_reczny_jest_zachowany(self):
        config = self._stara_konfiguracja()
        migrate_from_config(config, self.data_dir)
        ustawienia = load_settings({}, self.data_dir)
        self.assertFalse(ustawienia["auto"])
        self.assertEqual(ustawienia["active"], "Stary urząd")

    def test_brak_starych_kluczy_nic_nie_robi(self):
        config = {"theme": "dark"}
        self.assertFalse(migrate_from_config(config, self.data_dir))
        self.assertFalse((self.data_dir / WYPIS_PROFILES_FILE).exists())

    def test_istniejacy_plik_ma_pierwszenstwo(self):
        save_settings(
            [normalize_profile({"name": "Nowy zapis"})], data_dir=self.data_dir
        )
        config = self._stara_konfiguracja()
        migrate_from_config(config, self.data_dir)
        profile = load_profiles({}, self.data_dir)
        self.assertIsNotNone(find_profile(profile, "Nowy zapis"))
        self.assertIsNone(find_profile(profile, "Stary urząd"))

    def test_migracja_dziala_gdy_wzorow_nie_bylo(self):
        config = {ACTIVE_KEY: "", AUTO_KEY: True}
        self.assertTrue(migrate_from_config(config, self.data_dir))
        self.assertGreaterEqual(len(load_profiles({}, self.data_dir)), 2)


class ZgodnoscWsteczTests(unittest.TestCase):
    """Do czasu migracji program ma czytać wzory ze starej konfiguracji."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "dane"

    def tearDown(self):
        self._tmp.cleanup()

    def test_wzory_ze_starej_konfiguracji_sa_widoczne(self):
        config = {CONFIG_KEY: [{"name": "Z konfiguracji", "fields": {}}]}
        profile = load_profiles(config, self.data_dir)
        self.assertIsNotNone(find_profile(profile, "Z konfiguracji"))

    def test_plik_wygrywa_ze_stara_konfiguracja(self):
        save_settings([normalize_profile({"name": "Z pliku"})], data_dir=self.data_dir)
        config = {CONFIG_KEY: [{"name": "Z konfiguracji", "fields": {}}]}
        profile = load_profiles(config, self.data_dir)
        self.assertIsNotNone(find_profile(profile, "Z pliku"))
        self.assertIsNone(find_profile(profile, "Z konfiguracji"))

    def test_odczyt_pliku_zwraca_informacje_o_istnieniu(self):
        self.assertFalse(read_profiles_file(self.data_dir)["exists"])
        save_settings(default_profiles(), data_dir=self.data_dir)
        self.assertTrue(read_profiles_file(self.data_dir)["exists"])


class WartoscBezSasiedniejKolumnyTests(unittest.TestCase):
    """Wiersz bywa tabelką: „Powiat: X   Gmina: Y” — bierzemy tylko swoje."""

    def test_odstep_konczy_wartosc(self):
        self.assertEqual(_value_until_next_column("kartuski    Gmina: Zukowo"), "kartuski")

    def test_pojedyncza_spacja_przed_znana_etykieta(self):
        # Tniemy tylko przed etykietą, którą wzór zna.
        self.assertEqual(
            _value_until_next_column("kartuski Gmina: Zukowo", ["Gmina"]), "kartuski"
        )

    def test_nie_tnie_etykiety_wielowyrazowej(self):
        # Regresja: „Nr obrębu: 0019” dawało wcześniej wartość „Nr”.
        self.assertEqual(
            _value_until_next_column("Nr obrębu: 0019", ["Nr obrębu"]),
            "Nr obrębu: 0019",
        )

    def test_bez_znanych_etykiet_nic_nie_ucina(self):
        self.assertEqual(
            _value_until_next_column("kartuski Gmina: Zukowo"), "kartuski Gmina: Zukowo"
        )

    def test_dluzsza_etykieta_ma_pierwszenstwo(self):
        self.assertEqual(
            _value_until_next_column("0019 Nr obrębu: 22", ["Nr", "Nr obrębu"]), "0019"
        )

    def test_wartosc_wielowyrazowa_zostaje_cala(self):
        self.assertEqual(
            _value_until_next_column("Borkowo, ul. Polna 3"), "Borkowo, ul. Polna 3"
        )

    def test_wartosc_z_odstepem_i_druga_kolumna(self):
        self.assertEqual(
            _value_until_next_column("0010 MAKI     Nr obrebu: 0010"), "0010 MAKI"
        )

    def test_puste_wejscie(self):
        self.assertEqual(_value_until_next_column("   "), "")

    def test_extract_field_nie_bierze_sasiedniej_kolumny(self):
        tekst = "Powiat: kartuski    Gmina: Zukowo\n"
        profil = normalize_profile(
            {"name": "T", "fields": {"county": ["Powiat"], "municipality": ["Gmina"]}}
        )
        self.assertEqual(extract_field(tekst, profil, "county"), "kartuski")
        self.assertEqual(extract_field(tekst, profil, "municipality"), "Zukowo")


class OdczytZTabeliWKratkeTests(unittest.TestCase):
    """Nagłówek kolumny jako etykieta, wartość w wierszu poniżej."""

    TEKST = (
        "Obreb   Nr dzialki   Pow. [ha]   Opis uzytku\n"
        "0019, BOJANO   145/7   0.0235   dr\n"
        "0019, BOJANO   145/8   0.1120   RIVa\n"
    )

    def _profil(self):
        return normalize_profile(
            {
                "name": "Kratka",
                "fields": {
                    "precinct": ["Obreb"],
                    "parcel_number": ["Nr dzialki"],
                    "area": ["Pow. [ha]", "Pow."],
                    "ownership_form": ["Opis uzytku"],
                },
            }
        )

    def test_odczyt_powierzchni_z_kolumny(self):
        self.assertEqual(extract_field(self.TEKST, self._profil(), "area"), "0.0235")

    def test_odczyt_numeru_dzialki_z_kolumny(self):
        self.assertEqual(
            extract_field(self.TEKST, self._profil(), "parcel_number"), "145/7"
        )

    def test_odczyt_obrebu_z_przecinkiem(self):
        self.assertEqual(
            extract_field(self.TEKST, self._profil(), "precinct"), "0019, BOJANO"
        )

    def test_ostatnia_kolumna(self):
        self.assertEqual(
            extract_field(self.TEKST, self._profil(), "ownership_form"), "dr"
        )

    def test_nie_zwraca_sasiedniego_naglowka(self):
        for key in ("precinct", "parcel_number", "area", "ownership_form"):
            wartosc = extract_field(self.TEKST, self._profil(), key)
            self.assertNotIn("Nr dzialki", wartosc)
            self.assertNotIn("Opis uzytku", wartosc)

    def test_krotka_etykieta_nie_lapie_sie_w_dluzszej(self):
        # „Pow.” nie może dopasować się wewnątrz „Pow. [ha]” i zwrócić „[ha]”.
        profil = normalize_profile(
            {"name": "P", "fields": {"area": ["Powierzchnia", "Pow."]}}
        )
        self.assertNotEqual(extract_field(self.TEKST, profil, "area"), "[ha]")

    def test_uklad_z_dwukropkami_dziala_dalej(self):
        tekst = "Powiat: kartuski   Gmina: Zukowo\n"
        profil = normalize_profile(
            {"name": "D", "fields": {"county": ["Powiat"], "municipality": ["Gmina"]}}
        )
        self.assertEqual(extract_field(tekst, profil, "county"), "kartuski")
        self.assertEqual(extract_field(tekst, profil, "municipality"), "Zukowo")

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


class PionowaListaOdczytTests(unittest.TestCase):
    """Runda 19: odczyt z listy pól „etykieta   wartość” bez dwukropków."""

    TEKST = (
        "Wojewodztwo   POMORSKIE\n"
        "Powiat   kartuski\n"
        "Gmina   Zukowo\n"
        "Jednostka ewidencyjna   221509_2, Szemud\n"
        "Obreb   0019, BOJANO\n"
    )

    def setUp(self):
        self.profil = normalize_profile(
            {
                "name": "pionowy",
                "fields": {
                    "voivodeship": ["Województwo"],
                    "county": ["Powiat"],
                    "municipality": ["Gmina"],
                    "identifier": ["Jednostka ewidencyjna"],
                    "precinct": ["Obręb"],
                },
            }
        )

    def test_kazde_pole_czyta_wartosc_ze_swojego_wiersza(self):
        for pole, oczekiwane in (
            ("voivodeship", "POMORSKIE"),
            ("county", "kartuski"),
            ("municipality", "Zukowo"),
            ("identifier", "221509_2, Szemud"),
            ("precinct", "0019, BOJANO"),
        ):
            with self.subTest(pole=pole):
                self.assertEqual(
                    extract_field(self.TEKST, self.profil, pole), oczekiwane
                )

    def test_nie_bierze_nazwy_kolejnego_pola_jako_wartosci(self):
        # „Gmina” ma pod sobą „Jednostka ewidencyjna” — to nie jest wartość.
        self.assertNotEqual(
            extract_field(self.TEKST, self.profil, "municipality"),
            "Jednostka ewidencyjna",
        )


class KratkaNieMylonaZListaTests(unittest.TestCase):
    """Tabela w kratkę nadal czyta wartości z wiersza pod nagłówkiem."""

    TEKST = (
        "Obreb   Nr dzialki   Pow. [ha]   Opis uzytku\n"
        "0019, BOJANO   145/7   0.0235   dr\n"
        "0019, BOJANO   145/8   0.1120   RIVa\n"
    )

    def setUp(self):
        self.profil = normalize_profile(
            {
                "name": "kratka",
                "fields": {
                    "precinct": ["Obręb"],
                    "parcel_number": ["Nr działki"],
                    "area": ["Pow. [ha]"],
                },
            }
        )

    def test_wartosci_spod_naglowkow(self):
        for pole, oczekiwane in (
            ("precinct", "0019, BOJANO"),
            ("parcel_number", "145/7"),
            ("area", "0.0235"),
        ):
            with self.subTest(pole=pole):
                self.assertEqual(
                    extract_field(self.TEKST, self.profil, pole), oczekiwane
                )

    def test_nie_bierze_sasiedniego_naglowka_jako_wartosci(self):
        self.assertNotEqual(
            extract_field(self.TEKST, self.profil, "area"), "Opis uzytku"
        )
