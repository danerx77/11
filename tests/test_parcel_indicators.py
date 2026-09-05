"""Testy logiki modułu Wskaźnik: działki i identyfikatory ewidencyjne."""

import unittest
from pathlib import Path

from utils.parcel_indicators import (
    filter_indicator_rows,
    format_indicator_export,
    indicator_rows_from_owners,
    indicator_rows_from_parcels,
    indicator_summary,
    make_indicator_row,
    merge_indicator_rows,
    parcel_number_from_identifier,
    parse_indicator_line,
    parse_indicator_text,
    sort_indicator_rows,
)


class IdentifierParsingTests(unittest.TestCase):
    def test_parcel_number_is_read_from_full_identifier(self):
        self.assertEqual(
            parcel_number_from_identifier("221001_1.0001.123/4"),
            "123/4",
        )
        self.assertEqual(
            parcel_number_from_identifier("226101_1.0007.55"),
            "55",
        )

    def test_row_completes_number_and_precinct_number_from_identifier(self):
        row = make_indicator_row(identifier="221001_1.0001.123/4")
        self.assertEqual(row["number"], "123/4")
        self.assertEqual(row["precinct_number"], "0001")

    def test_line_with_number_and_identifier_separated_by_semicolon(self):
        row = parse_indicator_line("123/4;221001_1.0001.123/4")
        self.assertEqual(row["number"], "123/4")
        self.assertEqual(row["identifier"], "221001_1.0001.123/4")

    def test_line_with_arrow_and_extra_description(self):
        row = parse_indicator_line("12/3 => 221001_1.0001.12/3 | Obręb Polki")
        self.assertEqual(row["number"], "12/3")
        self.assertEqual(row["identifier"], "221001_1.0001.12/3")
        self.assertIn("Polki", row["note"])

    def test_line_with_only_parcel_number_keeps_identifier_empty(self):
        row = parse_indicator_line("456/7")
        self.assertEqual(row["number"], "456/7")
        self.assertEqual(row["identifier"], "")

    def test_comment_and_blank_lines_are_skipped(self):
        self.assertIsNone(parse_indicator_line("# komentarz"))
        self.assertIsNone(parse_indicator_line("   "))

    def test_text_with_comma_separated_numbers_creates_one_row_each(self):
        rows = parse_indicator_text("1/1, 1/2, 1/3")
        self.assertEqual([row["number"] for row in rows], ["1/1", "1/2", "1/3"])

    def test_text_mixes_plain_numbers_and_identifier_lines(self):
        rows = parse_indicator_text(
            "\n".join(
                [
                    "# lista",
                    "1/1 1/2",
                    "2/5;221001_1.0002.2/5",
                    "221001_1.0002.9",
                ]
            )
        )
        self.assertEqual(
            [(row["number"], row["identifier"]) for row in rows],
            [
                ("1/1", ""),
                ("1/2", ""),
                ("2/5", "221001_1.0002.2/5"),
                ("9", "221001_1.0002.9"),
            ],
        )


class MergeAndSourceTests(unittest.TestCase):
    def test_merge_fills_missing_identifier_without_touching_manual_edits(self):
        existing = [
            make_indicator_row(number="1/1", identifier="221001_1.0001.1/1", note="ręcznie"),
            make_indicator_row(number="1/2"),
        ]
        incoming = [
            make_indicator_row(number="1/1", identifier="999999_9.9999.1/1"),
            make_indicator_row(number="1/2", identifier="221001_1.0001.1/2"),
            make_indicator_row(number="1/3", identifier="221001_1.0001.1/3"),
        ]

        rows, added, updated = merge_indicator_rows(existing, incoming)

        self.assertEqual(added, 1)
        self.assertEqual(updated, 1)
        self.assertEqual(rows[0]["identifier"], "221001_1.0001.1/1")
        self.assertEqual(rows[0]["note"], "ręcznie")
        self.assertEqual(rows[1]["identifier"], "221001_1.0001.1/2")
        self.assertEqual(rows[2]["number"], "1/3")

    def test_merge_with_overwrite_replaces_identifier(self):
        rows, _added, updated = merge_indicator_rows(
            [make_indicator_row(number="1/1", identifier="stary")],
            [make_indicator_row(number="1/1", identifier="221001_1.0001.1/1")],
            overwrite=True,
        )
        self.assertEqual(updated, 1)
        self.assertEqual(rows[0]["identifier"], "221001_1.0001.1/1")

    def test_rows_from_owners_merge_shared_parcels_of_co_owners(self):
        owners = [
            {
                "parcels": [
                    {"number": "10/1", "identifier": "221001_1.0001.10/1"},
                    {"number": "10/2"},
                ],
                "precinct": "Polki",
            },
            {
                "parcels": [{"number": "10/2", "identifier": "221001_1.0001.10/2"}],
                "precinct": "Polki",
            },
        ]

        rows = indicator_rows_from_owners(owners)

        self.assertEqual([row["number"] for row in rows], ["10/1", "10/2"])
        self.assertEqual(rows[1]["identifier"], "221001_1.0001.10/2")
        self.assertEqual(rows[0]["precinct"], "Polki")

    def test_rows_from_parcel_list_module(self):
        rows = indicator_rows_from_parcels(
            [{"number": "5/1", "precinct": "Polki"}, "5/2", {"number": "5/1"}]
        )
        self.assertEqual([row["number"] for row in rows], ["5/1", "5/2"])


class FilterAndSummaryTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            make_indicator_row(number="1/1", identifier="221001_1.0001.1/1"),
            make_indicator_row(number="1/2", identifier="221001_1.0001.1/2"),
            make_indicator_row(number="2/10"),
            make_indicator_row(number="2/3", identifier="221001_1.0001.2/3"),
        ]

    def test_filter_by_pasted_parcel_list_with_commas(self):
        selected, missing = filter_indicator_rows(self.rows, "1/1, 1/2")
        self.assertEqual([row["number"] for row in selected], ["1/1", "1/2"])
        self.assertEqual(missing, [])

    def test_filter_accepts_spaces_newlines_and_semicolons(self):
        selected, missing = filter_indicator_rows(self.rows, "1/1\n2/3;2/10")
        self.assertEqual([row["number"] for row in selected], ["1/1", "2/3", "2/10"])
        self.assertEqual(missing, [])

    def test_filter_reports_parcels_absent_from_the_list(self):
        selected, missing = filter_indicator_rows(self.rows, "1/1, 99/9")
        self.assertEqual([row["number"] for row in selected], ["1/1"])
        self.assertEqual(missing, ["99/9"])

    def test_empty_filter_returns_everything(self):
        selected, missing = filter_indicator_rows(self.rows, "   ")
        self.assertEqual(len(selected), 4)
        self.assertEqual(missing, [])

    def test_search_narrows_the_filtered_rows(self):
        selected, _missing = filter_indicator_rows(self.rows, "", search_text="0001.2/3")
        self.assertEqual([row["number"] for row in selected], ["2/3"])

    def test_natural_sorting_puts_2_3_before_2_10(self):
        ordered = sort_indicator_rows(self.rows)
        self.assertEqual(
            [row["number"] for row in ordered], ["1/1", "1/2", "2/3", "2/10"]
        )

    def test_summary_counts_identifiers_and_missing_parcels(self):
        summary = indicator_summary(self.rows, missing=["99/9"])
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["with_identifier"], 3)
        self.assertEqual(summary["without_identifier"], ["2/10"])
        self.assertEqual(summary["missing"], ["99/9"])

    def test_summary_reports_duplicate_identifiers(self):
        rows = [
            make_indicator_row(number="1/1", identifier="221001_1.0001.1/1"),
            make_indicator_row(number="1/2", identifier="221001_1.0001.1/1"),
        ]
        self.assertEqual(
            indicator_summary(rows)["duplicate_identifiers"],
            ["221001_1.0001.1/1"],
        )

    def test_export_builds_two_column_text(self):
        text = format_indicator_export(self.rows[:2], header=True)
        self.assertEqual(
            text.splitlines(),
            [
                "Nr działki;Identyfikator działki",
                "1/1;221001_1.0001.1/1",
                "1/2;221001_1.0001.1/2",
            ],
        )


if __name__ == "__main__":
    unittest.main()


class ExportDialogWiringTests(unittest.TestCase):
    """Eksport TXT ma pozwalać wybrać kolumny (zgłoszenie użytkownika)."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.source = (root / "modules" / "wskaznik.py").read_text(encoding="utf-8")

    def test_export_dialog_exists(self):
        self.assertIn("class IndicatorExportDialog", self.source)

    def test_presets_cover_the_requested_variants(self):
        self.assertIn("Nr działki i identyfikator", self.source)
        self.assertIn("Same numery działek", self.source)
        self.assertIn("Same identyfikatory", self.source)
        self.assertIn("Wszystkie kolumny (jak w tabeli)", self.source)

    def test_export_uses_the_selected_columns(self):
        self.assertIn("columns=columns", self.source)

    def test_choice_is_remembered(self):
        self.assertIn("wskaznik_export_columns", self.source)


class ExportColumnLabelTests(unittest.TestCase):
    def test_labels_are_shared_in_one_place(self):
        from utils.parcel_indicators import EXPORT_COLUMN_LABELS, INDICATOR_FIELDS

        for field in INDICATOR_FIELDS:
            self.assertIn(field, EXPORT_COLUMN_LABELS)

    def test_export_can_select_a_single_column(self):
        rows = [{"number": "1/1", "identifier": "221001_1.0001.1/1"}]
        self.assertEqual(
            format_indicator_export(rows, columns=("identifier",)),
            "221001_1.0001.1/1",
        )
