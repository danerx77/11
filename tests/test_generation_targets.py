"""Testy wyboru adresów do seryjnego generowania bez zależności od Qt."""

import unittest

from utils.generation_targets import (
    cover_generation_exclusion_reason,
    cover_generation_rule_defaults,
    owner_addresses,
    select_address_targets,
)


class GenerationTargetTests(unittest.TestCase):
    def setUp(self):
        self.owner = {
            "full_name": "Jan Kowalski",
            "address": "ul. Pierwsza 1, 00-001 Miasto",
            "address_2": "ul. Druga 2, 00-002 Miasto",
        }

    def test_owner_addresses_includes_primary_and_secondary_address(self):
        self.assertEqual(
            owner_addresses(self.owner),
            [
                "ul. Pierwsza 1, 00-001 Miasto",
                "ul. Druga 2, 00-002 Miasto",
            ],
        )

    def test_done_status_is_checked_separately_for_each_address(self):
        checked_addresses = []

        def is_done(owner, address):
            self.assertIs(owner, self.owner)
            checked_addresses.append(address)
            return address == self.owner["address"]

        targets = select_address_targets(
            [self.owner],
            hide_done=True,
            is_done=is_done,
        )

        self.assertEqual(checked_addresses, owner_addresses(self.owner))
        self.assertEqual(targets, [(self.owner, self.owner["address_2"])])

    def test_filter_is_also_applied_to_the_specific_address(self):
        targets = select_address_targets(
            [self.owner],
            matches_filter=lambda _owner, address: "Druga" in address,
        )
        self.assertEqual(targets, [(self.owner, self.owner["address_2"])])

    def test_blank_primary_address_is_kept_for_the_validation_layer(self):
        owner = {"address": "", "address_2": "ul. Druga 2"}
        self.assertEqual(owner_addresses(owner), ["", "ul. Druga 2"])

    def test_cover_letter_defaults_keep_current_institution_and_parish_exclusions(self):
        defaults = cover_generation_rule_defaults()
        self.assertTrue(defaults["cover_skip_institution"])
        self.assertTrue(defaults["cover_skip_church"])
        self.assertFalse(defaults["cover_skip_company"])
        self.assertFalse(defaults["cover_skip_spolka"])

        allowed, reason = cover_generation_exclusion_reason(
            {"is_institution": True},
            "ul. Urzędowa 1, 00-001 Miasto",
            {},
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "Instytucja / gmina")

    def test_cover_letter_rules_can_enable_or_disable_each_owner_type(self):
        company = {"is_company": True}
        address = "ul. Firmowa 1, 00-001 Miasto"

        self.assertEqual(
            cover_generation_exclusion_reason(company, address, {}),
            (True, "OK"),
        )
        self.assertEqual(
            cover_generation_exclusion_reason(
                company,
                address,
                {"cover_skip_company": True},
            ),
            (False, "Firma"),
        )
        self.assertEqual(
            cover_generation_exclusion_reason(
                {"is_church": True},
                address,
                {"cover_skip_church": False},
            ),
            (True, "OK"),
        )

    def test_cover_letter_address_rules_are_configurable(self):
        self.assertEqual(
            cover_generation_exclusion_reason({}, "", {}),
            (False, "Brak adresu"),
        )
        self.assertEqual(
            cover_generation_exclusion_reason(
                {},
                "bez kodu",
                {
                    "cover_skip_missing_address": False,
                    "cover_skip_invalid_postal_code": False,
                },
            ),
            (True, "OK"),
        )


if __name__ == "__main__":
    unittest.main()
