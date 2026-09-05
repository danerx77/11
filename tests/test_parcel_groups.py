"""Testy filtrowania działek po grupach w Oświadczeniach i Pismach.

Zgłoszone problemy:
* przy wybranej grupie widać było także działki z innych grup,
* seryjne generowanie obejmowało wszystkie grupy naraz,
* postać urządzeń ustawiona przy grupie nie trafiała do dokumentu,
* trzeba było zaznaczyć dwa pola, żeby zobaczyć działki jednej grupy.

Testy sprawdzają samą logikę filtrowania na lekkich atrapach, więc działają
bez uruchamiania okien.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODULES = Path(__file__).resolve().parent.parent / "modules"


class FakeCheckBox:
    def __init__(self, checked=False):
        self._checked = checked

    def isChecked(self):
        return self._checked

    def setChecked(self, value):
        self._checked = bool(value)


class FakeCombo:
    def __init__(self, text=""):
        self._text = text

    def currentText(self):
        return self._text

    def setCurrentText(self, text):
        self._text = text


class GroupFilterMixinHarness:
    """Odtwarza metody filtrujące dokładnie tak, jak w modułach."""

    def __init__(self, groups, parcels, owners):
        self.parcel_groups = groups
        self.parcels = parcels
        self.owners = owners
        self.group_combo = FakeCombo("Wszystkie działki")
        self.chk_show_only_group = FakeCheckBox(False)

    # ── kopie metod z modułów ──
    def _all_project_parcels(self):
        nums = set()
        for p in self.parcels:
            if isinstance(p, dict) and p.get("number"):
                nums.add(str(p["number"]))
        for owner in self.owners:
            for parcel in owner.get("parcels", []):
                nums.add(self._parcel_number(parcel))
        return nums

    def _selected_group_parcels(self):
        name = self.group_combo.currentText()
        if name == "Wszystkie działki":
            all_nums = set(self._all_project_parcels())
            if self.chk_show_only_group.isChecked():
                used = set()
                for group in self.parcel_groups.values():
                    used.update(group.get("parcels", []))
                all_nums -= used
            return all_nums
        return set(self.parcel_groups.get(name, {}).get("parcels", []))

    def _group_parcel_filter(self):
        if not self.chk_show_only_group.isChecked():
            return None
        return self._selected_group_parcels()

    @staticmethod
    def _parcel_number(parcel):
        return str(parcel.get("number", parcel)) if isinstance(parcel, dict) else str(parcel)

    def _filter_parcels_to_group(self, parcels):
        allowed = self._group_parcel_filter()
        if allowed is None:
            return list(parcels or [])
        return [p for p in (parcels or []) if self._parcel_number(p) in allowed]

    def _group_for_parcels(self, parcels):
        numbers = {self._parcel_number(p) for p in (parcels or [])}
        if not numbers:
            return None
        best_group, best_hits = None, 0
        for group in self.parcel_groups.values():
            hits = len(numbers & set(group.get("parcels", [])))
            if hits > best_hits:
                best_group, best_hits = group, hits
        return best_group

    def _device_descriptions_for(self, parcels, fallback_budowa, fallback_demontaz):
        group = self._group_for_parcels(parcels)
        if not group:
            return fallback_budowa, fallback_demontaz
        return (
            (group.get("budowa") or "").strip() or fallback_budowa,
            (group.get("demontaz") or "").strip() or fallback_demontaz,
        )


def make_harness():
    return GroupFilterMixinHarness(
        groups={
            "Grupa A": {
                "parcels": ["1/1", "1/2"],
                "budowa": "linia kablowa SN 15 kV",
                "demontaz": "",
            },
            "Grupa B": {"parcels": ["2/1"], "budowa": "słup ŻN", "demontaz": ""},
        },
        parcels=[{"number": n} for n in ("1/1", "1/2", "2/1", "9/9")],
        owners=[
            {"full_name": "Jan Kowalski", "parcels": [{"number": "1/1"}, {"number": "9/9"}]},
            {"full_name": "Anna Nowak", "parcels": [{"number": "2/1"}]},
            {"full_name": "Piotr Wiśniewski", "parcels": [{"number": "9/9"}]},
        ],
    )


class FilterDisabledTests(unittest.TestCase):
    def test_without_filter_nothing_is_hidden(self):
        h = make_harness()
        self.assertIsNone(h._group_parcel_filter())
        parcels = [{"number": "1/1"}, {"number": "9/9"}]
        self.assertEqual(h._filter_parcels_to_group(parcels), parcels)


class SelectedGroupTests(unittest.TestCase):
    """Wybrana grupa pokazuje wyłącznie swoje działki."""

    def setUp(self):
        self.h = make_harness()
        self.h.group_combo.setCurrentText("Grupa A")
        self.h.chk_show_only_group.setChecked(True)

    def test_other_group_parcels_are_hidden(self):
        parcels = [{"number": "1/1"}, {"number": "2/1"}, {"number": "9/9"}]
        result = [p["number"] for p in self.h._filter_parcels_to_group(parcels)]
        self.assertEqual(result, ["1/1"])

    def test_owner_outside_the_group_has_nothing_left(self):
        owner = {"parcels": [{"number": "2/1"}]}
        self.assertEqual(self.h._filter_parcels_to_group(owner["parcels"]), [])

    def test_owners_for_generation_are_limited_to_the_group(self):
        selected = [
            o["full_name"]
            for o in self.h.owners
            if self.h._filter_parcels_to_group(o.get("parcels", []))
        ]
        self.assertEqual(selected, ["Jan Kowalski"])


class AllParcelsTests(unittest.TestCase):
    """„Wszystkie działki” z filtrem ukrywa działki należące do grup."""

    def setUp(self):
        self.h = make_harness()
        self.h.group_combo.setCurrentText("Wszystkie działki")
        self.h.chk_show_only_group.setChecked(True)

    def test_grouped_parcels_are_excluded(self):
        allowed = self.h._group_parcel_filter()
        self.assertNotIn("1/1", allowed)
        self.assertNotIn("1/2", allowed)
        self.assertNotIn("2/1", allowed)
        self.assertIn("9/9", allowed)

    def test_owner_keeps_only_ungrouped_parcels(self):
        parcels = [{"number": "1/1"}, {"number": "9/9"}]
        result = [p["number"] for p in self.h._filter_parcels_to_group(parcels)]
        self.assertEqual(result, ["9/9"])

    def test_without_filter_all_parcels_stay_visible(self):
        self.h.chk_show_only_group.setChecked(False)
        parcels = [{"number": "1/1"}, {"number": "9/9"}]
        self.assertEqual(len(self.h._filter_parcels_to_group(parcels)), 2)


class DeviceDescriptionTests(unittest.TestCase):
    """Postać urządzeń z grupy ma trafiać do generowanego dokumentu."""

    def setUp(self):
        self.h = make_harness()

    def test_group_description_wins_over_the_form(self):
        budowa, _ = self.h._device_descriptions_for(
            [{"number": "1/1"}], "z formularza", ""
        )
        self.assertEqual(budowa, "linia kablowa SN 15 kV")

    def test_second_group_has_its_own_description(self):
        budowa, _ = self.h._device_descriptions_for([{"number": "2/1"}], "", "")
        self.assertEqual(budowa, "słup ŻN")

    def test_parcel_without_group_uses_the_form(self):
        budowa, _ = self.h._device_descriptions_for(
            [{"number": "9/9"}], "z formularza", ""
        )
        self.assertEqual(budowa, "z formularza")

    def test_empty_group_field_falls_back_to_the_form(self):
        _, demontaz = self.h._device_descriptions_for(
            [{"number": "1/1"}], "", "demontaż z formularza"
        )
        self.assertEqual(demontaz, "demontaż z formularza")

    def test_owner_spanning_two_groups_uses_the_dominant_one(self):
        budowa, _ = self.h._device_descriptions_for(
            [{"number": "1/1"}, {"number": "1/2"}, {"number": "2/1"}], "", ""
        )
        self.assertEqual(budowa, "linia kablowa SN 15 kV")


class SourceWiringTests(unittest.TestCase):
    """Oba moduły mają mieć jedno pole wyboru i te same metody."""

    @classmethod
    def setUpClass(cls):
        cls.decl = (MODULES / "oswiadczenia_woli.py").read_text(encoding="utf-8")
        cls.cover = (MODULES / "pisma_przewodnie.py").read_text(encoding="utf-8")

    def test_old_second_checkbox_is_gone(self):
        for name, source in (("Oświadczenia", self.decl), ("Pisma", self.cover)):
            with self.subTest(module=name):
                self.assertNotIn("chk_exclude_grouped_from_all", source)

    def test_single_checkbox_has_the_new_label(self):
        for name, source in (("Oświadczenia", self.decl), ("Pisma", self.cover)):
            with self.subTest(module=name):
                self.assertIn("Pokaż i generuj tylko wybraną grupę", source)

    def test_both_modules_share_the_filter_helpers(self):
        for name, source in (("Oświadczenia", self.decl), ("Pisma", self.cover)):
            with self.subTest(module=name):
                self.assertIn("def _group_parcel_filter", source)
                self.assertIn("def _filter_parcels_to_group", source)

    def test_generation_respects_the_group(self):
        for name, source in (("Oświadczenia", self.decl), ("Pisma", self.cover)):
            with self.subTest(module=name):
                self.assertIn("owners_for_generation", source)

    def test_declaration_uses_group_device_description(self):
        self.assertIn("_device_descriptions_for", self.decl)

    def test_both_buttons_have_the_same_name(self):
        self.assertIn("GENERUJ AUTOMATYCZNIE WSZYSTKIE", self.decl)
        self.assertIn("GENERUJ AUTOMATYCZNIE WSZYSTKIE", self.cover)
        self.assertNotIn("BEZ PTASZKA", self.cover)


if __name__ == "__main__":
    unittest.main()
