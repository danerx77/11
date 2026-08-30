"""Testy normalizacji danych lokalnego, ręcznego modułu KW 2."""

import unittest

from utils.kw2_utils import collect_owner_kw_parcels, extract_kw_numbers, is_valid_kw


class KW2UtilsTests(unittest.TestCase):
    def test_extracts_supported_pasted_kw_formats_once(self):
        values = extract_kw_numbers(
            "GD1G/00012345/6, gd1g 00012345 6; PO1P.00000001.2\n"
            "GD1G / 00012345 / 6"
        )

        self.assertEqual(
            values,
            ["GD1G/00012345/6", "PO1P/00000001/2"],
        )

    def test_ignores_incomplete_or_invalid_numbers(self):
        values = extract_kw_numbers("GD1G/12345, GD1G/123456789/0, abc")

        self.assertEqual(values, [])
        self.assertTrue(is_valid_kw(" gd1g / 00012345 / 6 "))
        self.assertFalse(is_valid_kw("GD1G/00012345"))

    def test_preserves_text_order_for_state_lists_and_mixed_separators(self):
        values = extract_kw_numbers(
            ["PO1P.00000001.2", "GD1G/00012345/6", "PO1P.00000001.2"]
        )

        self.assertEqual(values, ["PO1P/00000001/2", "GD1G/00012345/6"])

    def test_collects_each_owner_parcel_only_once(self):
        records = collect_owner_kw_parcels(
            [
                {
                    "parcels": [
                        {"number": "12/1", "kw": "GD1G/00012345/6"},
                        {"number": "12/2", "kw": "GD1G/00012345/6"},
                    ]
                },
                {
                    "parcels": [
                        {"number": "12/1", "kw": "GD1G/00012345/6"},
                        {"number": "8", "kw": "PO1P/00000001/2"},
                    ]
                },
            ]
        )

        self.assertEqual(
            records,
            {
                "GD1G/00012345/6": ["12/1", "12/2"],
                "PO1P/00000001/2": ["8"],
            },
        )


if __name__ == "__main__":
    unittest.main()
