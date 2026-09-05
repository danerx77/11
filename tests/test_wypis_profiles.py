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
    DIRECTION_ABOVE,
    DIRECTION_BELOW,
    DIRECTION_LEFT,
    DIRECTION_RIGHT,
    custom_field_key,
    field_direction,
    is_custom_field,
    profile_field_defs,
    profile_field_keys,
    detect_profile,
    extract_field,
    find_profile,
    default_profiles,
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


class NowePolaWypisuTests(unittest.TestCase):
    """Runda 20: wypis ma więcej pól niż 13 — m.in. ulicę i PESEL."""

    def test_sa_pola_ulicy_i_miejscowosci(self):
        for key in ("parcel_city", "parcel_street"):
            with self.subTest(pole=key):
                self.assertIn(key, FIELD_KEYS)

    def test_sa_pola_wlasciciela(self):
        for key in ("owner_address", "owner_city", "pesel", "nip", "regon"):
            with self.subTest(pole=key):
                self.assertIn(key, FIELD_KEYS)

    def test_sa_pola_dokumentu(self):
        for key in ("document_date", "document_number", "office", "land_use"):
            with self.subTest(pole=key):
                self.assertIn(key, FIELD_KEYS)

    def test_kazde_pole_ma_nazwe_po_polsku(self):
        for key in FIELD_KEYS:
            with self.subTest(pole=key):
                self.assertTrue(FIELD_LABELS.get(key))

    def test_wbudowane_wzory_znaja_nowe_pola(self):
        for profil in default_profiles():
            for key in ("parcel_street", "pesel", "land_use"):
                with self.subTest(wzor=profil["name"], pole=key):
                    self.assertTrue(labels_for(profil, key))


class OdczytNowychPolTests(unittest.TestCase):
    """Nowe pola dają się odczytać z typowego wypisu."""

    TEKST = (
        "Starostwo Powiatowe w Kartuzach\n"
        "Znak sprawy: GN.6621.145.2026\n"
        "Data wypisu: 05.09.2026\n"
        "Miejscowosc: Borkowo\n"
        "Ulica: ul. Polna 3\n"
        "Opis uzytku: RIVa\n"
        "Wlasciciel: Kowalski Jan\n"
        "Adres wlasciciela: ul. Lesna 7, 83-330 Zukowo\n"
        "PESEL: 65042012345\n"
        "NIP: 5891234567\n"
    )

    def test_czyta_ulice_uzytek_i_dane_wlasciciela(self):
        profil = default_profiles()[0]
        for pole, oczekiwane in (
            ("parcel_city", "Borkowo"),
            ("parcel_street", "ul. Polna 3"),
            ("land_use", "RIVa"),
            ("pesel", "65042012345"),
            ("nip", "5891234567"),
            ("document_date", "05.09.2026"),
            ("document_number", "GN.6621.145.2026"),
        ):
            with self.subTest(pole=pole):
                self.assertEqual(
                    extract_field(self.TEKST, profil, pole), oczekiwane
                )


class WlasnePolaTests(unittest.TestCase):
    """Runda 22: użytkownik dodaje i usuwa pola, bo urzędy mają różne rubryki."""

    def test_klucz_pola_wlasnego_ma_przedrostek(self):
        klucz = custom_field_key("Numer arkusza")
        self.assertTrue(is_custom_field(klucz))
        self.assertNotIn(klucz, FIELD_KEYS)

    def test_klucze_sie_nie_powtarzaja(self):
        pierwszy = custom_field_key("Arkusz")
        drugi = custom_field_key("Arkusz", [pierwszy])
        self.assertNotEqual(pierwszy, drugi)

    def test_polskie_znaki_w_nazwie_dzialaja(self):
        klucz = custom_field_key("Księga wieczysta działki")
        self.assertTrue(is_custom_field(klucz))
        self.assertTrue(klucz.replace("_", "").isalnum())

    def test_pola_wbudowane_nie_sa_wlasne(self):
        for key in FIELD_KEYS:
            with self.subTest(pole=key):
                self.assertFalse(is_custom_field(key))

    def test_wlasne_pole_widac_w_tabeli(self):
        profil = normalize_profile(
            {"name": "t", "custom_fields": {"custom_arkusz": "Arkusz mapy"}}
        )
        klucze = profile_field_keys(profil)
        self.assertIn("custom_arkusz", klucze)
        self.assertEqual(len(klucze), len(FIELD_KEYS) + 1)

    def test_ukryte_pole_znika_z_tabeli(self):
        profil = normalize_profile({"name": "t", "hidden_fields": ["regon"]})
        self.assertNotIn("regon", profile_field_keys(profil))

    def test_zapis_zachowuje_wlasne_pola(self):
        profil = normalize_profile(
            {
                "name": "t",
                "custom_fields": {"custom_arkusz": "Arkusz"},
                "fields": {"custom_arkusz": ["Nr arkusza"]},
                "manual_values": {"custom_arkusz": "12"},
            }
        )
        self.assertEqual(profil["custom_fields"], {"custom_arkusz": "Arkusz"})
        self.assertEqual(profil["fields"]["custom_arkusz"], ["Nr arkusza"])
        self.assertEqual(profil["manual_values"]["custom_arkusz"], "12")

    def test_odrzuca_wlasne_pole_bez_przedrostka(self):
        profil = normalize_profile(
            {"name": "t", "custom_fields": {"zle": "Bez przedrostka"}}
        )
        self.assertEqual(profil["custom_fields"], {})

    def test_wlasne_pole_da_sie_odczytac_z_tekstu(self):
        profil = normalize_profile(
            {
                "name": "t",
                "custom_fields": {"custom_arkusz": "Arkusz mapy"},
                "fields": {"custom_arkusz": ["Arkusz mapy"]},
            }
        )
        wiersze = {
            r["field"]: r for r in analyze_text("Arkusz mapy: 12\n", profil)
        }
        self.assertIn("custom_arkusz", wiersze)
        self.assertEqual(wiersze["custom_arkusz"]["value"], "12")
        self.assertEqual(wiersze["custom_arkusz"]["label"], "Arkusz mapy")


class SkasowaneWartosciTests(unittest.TestCase):
    """Wartość skasowaną przyciskiem program ma zostawić pustą."""

    def test_profil_pamieta_skasowane_pola(self):
        profil = normalize_profile(
            {"name": "t", "skipped_values": ["area", "kw"]}
        )
        self.assertEqual(profil["skipped_values"], ["area", "kw"])

    def test_domyslnie_nic_nie_jest_skasowane(self):
        self.assertEqual(normalize_profile({"name": "t"})["skipped_values"], [])


class KierunekOdczytuTests(unittest.TestCase):
    """Runda 23: wartość bywa POD nazwą pola, nie tylko obok niej."""

    POD = (
        "Numer dzialki   Blizsze okreslenie polozenia\n"
        "27/176   Borkowo, ul. Polna\n"
    )
    OBOK = "Wojewodztwo   POMORSKIE\nPowiat   kartuski\n"

    def _profil(self, pole, etykieta, kierunek=None):
        dane = {"name": "t", "fields": {pole: [etykieta]}}
        if kierunek:
            dane["directions"] = {pole: kierunek}
        return normalize_profile(dane)

    def test_domyslnie_czyta_wartosc_pod_spodem(self):
        profil = self._profil("parcel_number", "Numer dzialki")
        self.assertEqual(
            extract_field(self.POD, profil, "parcel_number"), "27/176"
        )

    def test_domyslnie_czyta_tez_wartosc_obok(self):
        profil = self._profil("voivodeship", "Wojewodztwo")
        self.assertEqual(
            extract_field(self.OBOK, profil, "voivodeship"), "POMORSKIE"
        )

    def test_wymuszony_kierunek_w_dol(self):
        profil = self._profil(
            "parcel_number", "Numer dzialki", DIRECTION_BELOW
        )
        self.assertEqual(
            extract_field(self.POD, profil, "parcel_number"), "27/176"
        )

    def test_wymuszony_kierunek_obok_nie_bierze_z_dolu(self):
        profil = self._profil(
            "parcel_number", "Numer dzialki", DIRECTION_RIGHT
        )
        self.assertNotEqual(
            extract_field(self.POD, profil, "parcel_number"), "27/176"
        )

    def test_profil_pamieta_kierunek(self):
        profil = self._profil("area", "Pow.", DIRECTION_BELOW)
        self.assertEqual(field_direction(profil, "area"), DIRECTION_BELOW)

    def test_bez_ustawienia_kierunek_jest_automatyczny(self):
        profil = self._profil("area", "Pow.")
        self.assertEqual(field_direction(profil, "area"), "auto")

    def test_odrzuca_nieznany_kierunek(self):
        profil = normalize_profile(
            {"name": "t", "directions": {"area": "byle co"}}
        )
        self.assertEqual(profil["directions"], {})

    def test_lista_pol_nie_myli_sie_z_tabela(self):
        # „Powiat  kartuski” nad „Gmina  Zukowo” to lista, nie tabela —
        # wartością Powiatu jest „kartuski”, a nie „Gmina”.
        profil = self._profil("county", "Powiat")
        self.assertEqual(extract_field(self.OBOK, profil, "county"), "kartuski")


class KierunekZLewejINadTests(unittest.TestCase):
    """Runda 24: wartość bywa też po lewej stronie nazwy albo nad nią."""

    LEWO = "27/176   Numer dzialki\n0,4500   Powierzchnia\n"
    GORA = "27/176      Borkowo\nNumer dzialki   Polozenie\n"
    PRAWO = "Powiat   kartuski\n"

    def _profil(self, pole, etykieta, kierunek):
        return normalize_profile(
            {
                "name": "t",
                "fields": {pole: [etykieta]},
                "directions": {pole: kierunek},
            }
        )

    def test_czyta_wartosc_z_lewej_strony(self):
        profil = self._profil("parcel_number", "Numer dzialki", DIRECTION_LEFT)
        self.assertEqual(
            extract_field(self.LEWO, profil, "parcel_number"), "27/176"
        )

    def test_czyta_z_lewej_takze_dalsze_pole(self):
        profil = self._profil("area", "Powierzchnia", DIRECTION_LEFT)
        self.assertEqual(extract_field(self.LEWO, profil, "area"), "0,4500")

    def test_czyta_wartosc_znad_nazwy(self):
        profil = self._profil("parcel_number", "Numer dzialki", DIRECTION_ABOVE)
        self.assertEqual(
            extract_field(self.GORA, profil, "parcel_number"), "27/176"
        )

    def test_z_lewej_nie_bierze_tego_co_stoi_z_prawej(self):
        profil = self._profil("county", "Powiat", DIRECTION_LEFT)
        self.assertEqual(extract_field(self.PRAWO, profil, "county"), "")

    def test_znad_nie_bierze_tego_co_stoi_z_prawej(self):
        profil = self._profil("county", "Powiat", DIRECTION_ABOVE)
        self.assertEqual(extract_field(self.PRAWO, profil, "county"), "")

    def test_profil_pamieta_kierunek_z_lewej(self):
        profil = self._profil("area", "Pow.", DIRECTION_LEFT)
        self.assertEqual(field_direction(profil, "area"), DIRECTION_LEFT)

    def test_profil_pamieta_kierunek_znad(self):
        profil = self._profil("area", "Pow.", DIRECTION_ABOVE)
        self.assertEqual(field_direction(profil, "area"), DIRECTION_ABOVE)

    def test_sa_wszystkie_cztery_kierunki_plus_automat(self):
        from utils.wypis_profiles import DIRECTIONS

        self.assertEqual(
            [wartosc for wartosc, _opis in DIRECTIONS],
            ["auto", "right", "left", "below", "above"],
        )


class ZmianaKierunkuDzialaTests(unittest.TestCase):
    """Runda 25: zmiana „Skąd czytać” ma naprawdę zmieniać odczyt."""

    Z_DWUKROPKIEM = "Powiat: kartuski\nGmina: Zukowo\n"
    BEZ_DWUKROPKA = "Powiat   kartuski\nGmina   Zukowo\n"

    def _czytaj(self, tekst, kierunek):
        profil = normalize_profile(
            {
                "name": "t",
                "fields": {"county": ["Powiat"]},
                "directions": {"county": kierunek},
            }
        )
        return extract_field(tekst, profil, "county")

    def test_kierunki_daja_rozne_wyniki_mimo_dwukropka(self):
        # Wcześniej „Powiat: kartuski” zwracało to samo dla każdego
        # ustawienia, bo zwykłe dopasowanie wyprzedzało wybór kierunku.
        wyniki = {
            kierunek: self._czytaj(self.Z_DWUKROPKIEM, kierunek)
            for kierunek in ("right", "left", "below", "above")
        }
        self.assertEqual(wyniki["right"], "kartuski")
        self.assertEqual(wyniki["left"], "")
        self.assertEqual(wyniki["below"], "")
        self.assertEqual(wyniki["above"], "")

    def test_z_dwukropkiem_kierunek_w_prawo_nadal_czyta(self):
        self.assertEqual(
            self._czytaj(self.Z_DWUKROPKIEM, DIRECTION_RIGHT), "kartuski"
        )

    def test_bez_dwukropka_kierunki_tez_sie_roznia(self):
        self.assertEqual(
            self._czytaj(self.BEZ_DWUKROPKA, DIRECTION_RIGHT), "kartuski"
        )
        self.assertEqual(self._czytaj(self.BEZ_DWUKROPKA, DIRECTION_LEFT), "")

    def test_tryb_automatyczny_dalej_znajduje_wartosc(self):
        for tekst in (self.Z_DWUKROPKIEM, self.BEZ_DWUKROPKA):
            self.assertEqual(self._czytaj(tekst, "auto"), "kartuski")

    def test_powrot_do_automatu_przywraca_odczyt(self):
        self.assertEqual(self._czytaj(self.Z_DWUKROPKIEM, DIRECTION_LEFT), "")
        self.assertEqual(self._czytaj(self.Z_DWUKROPKIEM, "auto"), "kartuski")


class KierunekWKazdymUkladzieTests(unittest.TestCase):
    """Runda 26: kierunek ma działać też, gdy nazwa stoi sama w linii."""

    def _czytaj(self, tekst, kierunek):
        profil = normalize_profile(
            {
                "name": "t",
                "fields": {"parcel_number": ["Numer dzialki"]},
                "directions": {"parcel_number": kierunek},
            }
        )
        return extract_field(tekst, profil, "parcel_number")

    def test_pod_spodem_gdy_nazwa_stoi_sama_w_linii(self):
        # Najczęstszy układ w wypisach — wcześniej zwracało pustą wartość,
        # bo linia z jedną kolumną była odrzucana jako „nie tabela”.
        self.assertEqual(
            self._czytaj("Numer dzialki\n27/176\n", DIRECTION_BELOW), "27/176"
        )

    def test_pod_spodem_gdy_nazwa_ma_dwukropek(self):
        self.assertEqual(
            self._czytaj("Numer dzialki:\n27/176\n", DIRECTION_BELOW), "27/176"
        )

    def test_pod_spodem_mimo_pustej_linii(self):
        self.assertEqual(
            self._czytaj("Numer dzialki\n\n27/176\n", DIRECTION_BELOW),
            "27/176",
        )

    def test_pod_spodem_w_naglowkach_tabeli(self):
        self.assertEqual(
            self._czytaj(
                "Numer dzialki   Polozenie\n27/176   Borkowo\n", DIRECTION_BELOW
            ),
            "27/176",
        )

    def test_nad_nazwa_gdy_nazwa_stoi_sama(self):
        self.assertEqual(
            self._czytaj("27/176\nNumer dzialki\n", DIRECTION_ABOVE), "27/176"
        )

    def test_nad_nazwa_gdy_nazwa_ma_dwukropek(self):
        self.assertEqual(
            self._czytaj("27/176\nNumer dzialki:\n", DIRECTION_ABOVE), "27/176"
        )

    def test_z_lewej_gdy_nazwa_ma_dwukropek(self):
        self.assertEqual(
            self._czytaj("27/176   Numer dzialki:\n", DIRECTION_LEFT), "27/176"
        )

    def test_z_prawej_gdy_nazwa_ma_dwukropek(self):
        self.assertEqual(
            self._czytaj("Numer dzialki: 27/176\n", DIRECTION_RIGHT), "27/176"
        )

