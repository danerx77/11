"""Testy naturalnego sortowania i poziomego formatu list działek."""

import unittest

from utils.parcel_sorting import (
    find_duplicate_parcel_numbers,
    format_parcel_list,
    parse_parcel_list,
    remove_duplicate_parcel_numbers,
    sort_parcel_numbers,
)


class ParcelSortingTests(unittest.TestCase):
    def test_parser_accepts_all_supported_pasted_separators(self):
        pasted = "1/10\n1 / 2; 1,\t2\r\n10"
        self.assertEqual(
            parse_parcel_list(pasted),
            ["1/10", "1/2", "1", "2", "10"],
        )

    def test_natural_sort_is_written_as_one_comma_separated_line(self):
        values = parse_parcel_list("1/10\n1/2; 1, 2\t1/1")
        result = sort_parcel_numbers(values)
        self.assertEqual(result, ["1", "1/1", "1/2", "1/10", "2"])
        self.assertEqual(
            format_parcel_list(result), "1, 1/1, 1/2, 1/10, 2"
        )

    def test_old_vertical_format_can_be_restored_to_horizontal_format(self):
        old_saved_value = "12/10\n2\n12 / 3\n1"
        self.assertEqual(
            format_parcel_list(parse_parcel_list(old_saved_value)),
            "12/10, 2, 12/3, 1",
        )

    def test_unique_sort_keeps_first_spelling(self):
        result = sort_parcel_numbers(["1 / 2", "1/2", "1/10"], unique=True)
        self.assertEqual(result, ["1/2", "1/10"])
        self.assertEqual(format_parcel_list(result), "1/2, 1/10")

    def test_duplicate_cleaner_keeps_input_order_without_sorting(self):
        values = parse_parcel_list("1/2, 1/3, 1 / 2, 1/4")

        self.assertEqual(
            remove_duplicate_parcel_numbers(values),
            ["1/2", "1/3", "1/4"],
        )
        self.assertEqual(
            find_duplicate_parcel_numbers(values),
            [("1/2", 2)],
        )

    def test_space_separated_numbers_work_for_sorting_and_duplicates(self):
        values = parse_parcel_list("1/2 1/2 1/3")

        self.assertEqual(values, ["1/2", "1/2", "1/3"])
        self.assertEqual(remove_duplicate_parcel_numbers(values), ["1/2", "1/3"])
        self.assertEqual(
            sort_parcel_numbers(parse_parcel_list("5 2 3")), ["2", "3", "5"]
        )

    def test_duplicate_cleaner_keeps_space_separated_list_order(self):
        values = parse_parcel_list("5 2 3")

        self.assertEqual(remove_duplicate_parcel_numbers(values), ["5", "2", "3"])


if __name__ == "__main__":
    unittest.main()
