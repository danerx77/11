"""Testy konfiguracji modeli OCR w wydaniu PyInstaller."""

import os
import unittest
from unittest.mock import patch

from utils.ocr_utils import _easyocr_reader_options


class EasyOcrBundleOptionsTests(unittest.TestCase):
    def test_source_run_keeps_easyocr_default_download_location(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENERGODOK_EASYOCR_MODEL_DIR", None)
            os.environ.pop("PYSILDE6_EASYOCR_MODEL_DIR", None)
            self.assertEqual(_easyocr_reader_options(), {})

    def test_bundled_model_path_is_explicit_and_offline(self):
        bundled_path = r"C:\Program Files\EnergoDok\_internal\easyocr-data\model"
        with patch.dict(
            os.environ,
            {"ENERGODOK_EASYOCR_MODEL_DIR": bundled_path},
            clear=False,
        ):
            self.assertEqual(
                _easyocr_reader_options(),
                {
                    "model_storage_directory": bundled_path,
                    "download_enabled": False,
                },
            )


if __name__ == "__main__":
    unittest.main()
