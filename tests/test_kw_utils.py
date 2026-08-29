"""Testy czystych reguł diagnostyki i zapisu PDF modułu KW."""

import unittest

from utils.kw_utils import ekw_access_denied_reason, should_use_native_pdf_export


class KWUtilsTests(unittest.TestCase):
    def test_access_denied_error_15_is_reported_as_service_block(self):
        reason = ekw_access_denied_reason(
            "Access Denied\nError 15\nYour BOT support ID is: 123456789"
        )

        self.assertIn("Access Denied / Error 15", reason)
        self.assertIn("123456789", reason)

    def test_unrelated_page_text_is_not_reported_as_access_denied(self):
        self.assertEqual(
            ekw_access_denied_reason("EUKW - Prezentacja Księgi Wieczystej"),
            "",
        )

    def test_direct_pdf_export_is_used_only_for_chromium_browsers(self):
        self.assertTrue(
            should_use_native_pdf_export(False, "Save as PDF", "chromium")
        )
        self.assertTrue(
            should_use_native_pdf_export(True, "Microsoft Print to PDF", "chromium")
        )
        self.assertFalse(
            should_use_native_pdf_export(True, "Save as PDF", "firefox")
        )
        self.assertFalse(
            should_use_native_pdf_export(False, "Adobe PDF", "chromium")
        )


if __name__ == "__main__":
    unittest.main()
