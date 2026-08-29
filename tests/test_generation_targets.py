"""Testy wyboru adresów do seryjnego generowania bez zależności od Qt."""

import unittest

from utils.generation_targets import owner_addresses, select_address_targets


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


if __name__ == "__main__":
    unittest.main()
