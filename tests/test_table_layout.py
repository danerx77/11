"""Testy pomocników utrzymujących kolumny tabel widoczne."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.table_layout import (  # noqa: E402
    FALLBACK_COLUMN_WIDTH,
    apply_minimum_widths,
    column_count_key,
    ensure_columns_visible,
    remember_column_count,
    state_matches_columns,
)


class FakeTable:
    """Najprostsza atrapa QTableWidget na potrzeby testów."""

    def __init__(self, widths, hidden=()):
        self._widths = list(widths)
        self._hidden = set(hidden)

    def columnCount(self):
        return len(self._widths)

    def isColumnHidden(self, column):
        return column in self._hidden

    def setColumnHidden(self, column, hidden):
        if hidden:
            self._hidden.add(column)
        else:
            self._hidden.discard(column)

    def columnWidth(self, column):
        return self._widths[column]

    def setColumnWidth(self, column, width):
        self._widths[column] = width


class StateMatchesColumnsTests(unittest.TestCase):
    def test_missing_entry_is_not_a_match(self):
        self.assertFalse(state_matches_columns({}, "table_state_owners", 24))

    def test_matching_count_is_accepted(self):
        config = {column_count_key("table_state_owners"): 24}
        self.assertTrue(state_matches_columns(config, "table_state_owners", 24))

    def test_old_layout_with_fewer_columns_is_rejected(self):
        # Zapis sprzed dodania kolumny „Identyfikator działki”.
        config = {column_count_key("table_state_owners"): 23}
        self.assertFalse(state_matches_columns(config, "table_state_owners", 24))

    def test_broken_value_is_rejected(self):
        config = {column_count_key("table_state_owners"): "iles tam"}
        self.assertFalse(state_matches_columns(config, "table_state_owners", 24))

    def test_remember_writes_the_count(self):
        config = {}
        remember_column_count(config, "table_state_owners", 24)
        self.assertTrue(state_matches_columns(config, "table_state_owners", 24))


class EnsureColumnsVisibleTests(unittest.TestCase):
    def test_hidden_column_is_revealed(self):
        table = FakeTable([100] * 5, hidden={3})
        repaired = ensure_columns_visible(table)
        self.assertEqual(repaired, [3])
        self.assertFalse(table.isColumnHidden(3))

    def test_zero_width_column_gets_a_usable_width(self):
        table = FakeTable([100, 0, 100])
        ensure_columns_visible(table)
        self.assertEqual(table.columnWidth(1), FALLBACK_COLUMN_WIDTH)

    def test_identifier_column_gets_extra_room(self):
        # Kolumna 23 to „Identyfikator działki” — bywała niewidoczna.
        table = FakeTable([100] * 24, hidden={23})
        ensure_columns_visible(table, wide_columns={23: 220})
        self.assertFalse(table.isColumnHidden(23))
        self.assertEqual(table.columnWidth(23), 220)

    def test_healthy_table_is_left_alone(self):
        table = FakeTable([120] * 6)
        self.assertEqual(ensure_columns_visible(table), [])

    def test_many_narrow_columns_are_all_repaired(self):
        table = FakeTable([0] * 24)
        repaired = ensure_columns_visible(table)
        self.assertEqual(repaired, list(range(24)))
        self.assertTrue(all(table.columnWidth(i) >= 40 for i in range(24)))


class ApplyMinimumWidthsTests(unittest.TestCase):
    def test_narrow_columns_are_widened(self):
        table = FakeTable([50, 50, 300])
        widened = apply_minimum_widths(table, {0: 200, 2: 200})
        self.assertEqual(widened, [0])
        self.assertEqual(table.columnWidth(0), 200)
        self.assertEqual(table.columnWidth(2), 300)

    def test_out_of_range_columns_are_ignored(self):
        table = FakeTable([50, 50])
        self.assertEqual(apply_minimum_widths(table, {9: 200}), [])


if __name__ == "__main__":
    unittest.main()
