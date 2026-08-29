"""Testy czystych reguł zapisu PDF modułu KW."""

import unittest

from utils.kw_utils import should_use_native_pdf_export


class KWUtilsTests(unittest.TestCase):
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
