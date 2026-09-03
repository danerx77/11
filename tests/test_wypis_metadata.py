"""Testy odczytu wypisu obejmującego kilka obrębów, gmin i powiatów."""

import unittest

from utils.wypis_metadata import (
    combine_meta_values,
    extract_meta_values,
    extract_wypis_metadata,
    merge_meta_into_parcels,
    parcel_meta_map,
    split_precinct_value,
)


TWO_PRECINCTS = """
Województwo: pomorskie
Powiat: kartuski
Jednostka ewidencyjna: Żukowo
Obręb ewidencyjny: 0001, Polki
Oznaczenie działki
12/3
Identyfikator działki: 221001_1.0001.12/3

Województwo: pomorskie
Powiat: kartuski
Jednostka ewidencyjna: Żukowo
Obręb ewidencyjny: 0002, Borkowo
Oznaczenie działki
44/1
Identyfikator działki: 221001_1.0002.44/1
"""

TWO_COUNTIES = """
Województwo: pomorskie
Powiat: kartuski
Jednostka ewidencyjna: Żukowo
Obręb ewidencyjny: 0001, Polki
15/2

Województwo: pomorskie
Powiat: wejherowski
Jednostka ewidencyjna: Szemud
Obręb ewidencyjny: 0007, Kielno
16/4
"""


class MultiValueExtractionTests(unittest.TestCase):
    def test_every_precinct_is_read_not_only_the_first_one(self):
        values = extract_meta_values(TWO_PRECINCTS)
        self.assertEqual(values["precinct"], ["Polki", "Borkowo"])
        self.assertEqual(values["precinct_number"], ["1", "2"])

    def test_repeated_identical_values_are_not_duplicated(self):
        values = extract_meta_values(TWO_PRECINCTS)
        self.assertEqual(values["voivodeship"], ["pomorskie"])
        self.assertEqual(values["county"], ["kartuski"])
        self.assertEqual(values["municipality"], ["Żukowo"])

    def test_every_county_and_municipality_is_read(self):
        values = extract_meta_values(TWO_COUNTIES)
        self.assertEqual(values["county"], ["kartuski", "wejherowski"])
        self.assertEqual(values["municipality"], ["Żukowo", "Szemud"])
        self.assertEqual(values["precinct"], ["Polki", "Kielno"])

    def test_combined_text_lists_all_values_for_form_fields(self):
        combined = combine_meta_values(extract_meta_values(TWO_COUNTIES))
        self.assertEqual(combined["county"], "kartuski, wejherowski")
        self.assertEqual(combined["precinct"], "Polki, Kielno")

    def test_metadata_result_exposes_both_combined_text_and_value_lists(self):
        meta = extract_wypis_metadata(TWO_PRECINCTS)
        self.assertEqual(meta["precinct"], "Polki, Borkowo")
        self.assertEqual(meta["precinct_values"], ["Polki", "Borkowo"])
        self.assertTrue(meta["has_multiple"])

    def test_single_precinct_document_is_not_marked_as_multiple(self):
        meta = extract_wypis_metadata(
            "Województwo: pomorskie\nPowiat: kartuski\n"
            "Jednostka ewidencyjna: Żukowo\nObręb ewidencyjny: 0001, Polki\n"
        )
        self.assertFalse(meta["has_multiple"])
        self.assertEqual(meta["precinct"], "Polki")
        self.assertEqual(meta["precinct_number"], "1")

    def test_broken_county_value_is_ignored(self):
        values = extract_meta_values("Powiat: owe w\nObręb: Polki")
        self.assertEqual(values["county"], [])
        self.assertEqual(values["precinct"], ["Polki"])


class PrecinctSplitTests(unittest.TestCase):
    def test_number_and_name_separated_by_comma(self):
        self.assertEqual(split_precinct_value("0001, Polki"), ("Polki", "1"))

    def test_name_first_then_number(self):
        self.assertEqual(split_precinct_value("Polki - 0001"), ("Polki", "1"))

    def test_name_only_and_number_only(self):
        self.assertEqual(split_precinct_value("Polki"), ("Polki", ""))
        self.assertEqual(split_precinct_value("0012"), ("", "12"))

    def test_office_suffix_is_cut_off(self):
        self.assertEqual(
            split_precinct_value("0001, Polki Nr Kancelaryjny EG.6621"),
            ("Polki", "1"),
        )


class PerParcelMetadataTests(unittest.TestCase):
    def test_each_parcel_gets_the_precinct_from_its_own_section(self):
        mapping = parcel_meta_map(TWO_PRECINCTS)
        self.assertEqual(mapping["12/3"]["precinct"], "Polki")
        self.assertEqual(mapping["44/1"]["precinct"], "Borkowo")
        self.assertEqual(mapping["12/3"]["precinct_number"], "1")
        self.assertEqual(mapping["44/1"]["precinct_number"], "2")

    def test_parcels_get_their_own_county_and_municipality(self):
        mapping = parcel_meta_map(TWO_COUNTIES)
        self.assertEqual(mapping["15/2"]["county"], "kartuski")
        self.assertEqual(mapping["16/4"]["county"], "wejherowski")
        self.assertEqual(mapping["16/4"]["municipality"], "Szemud")

    def test_merge_fills_each_parcel_with_its_matching_section(self):
        parcels = [{"number": "12/3"}, {"number": "44/1"}]
        merged = merge_meta_into_parcels(parcels, TWO_PRECINCTS)
        self.assertEqual(merged[0]["precinct"], "Polki")
        self.assertEqual(merged[1]["precinct"], "Borkowo")

    def test_merge_keeps_existing_values_and_uses_fallback_for_unknown_parcels(self):
        parcels = [{"number": "99/9"}, {"number": "12/3", "precinct": "Ręcznie"}]
        merged = merge_meta_into_parcels(
            parcels, TWO_PRECINCTS, fallback={"precinct": "Zapasowy"}
        )
        self.assertEqual(merged[0]["precinct"], "Zapasowy")
        self.assertEqual(merged[1]["precinct"], "Ręcznie")


if __name__ == "__main__":
    unittest.main()
