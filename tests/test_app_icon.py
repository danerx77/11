"""Testy ikony programu.

Program ma mieć własną ikonę aplikacji (plik .ico dla EXE), a nie tylko ikonkę
na zakładce. Sprawdzamy, że plik istnieje, ma rozmiary wymagane przez Windows
i że jest podpięty w kodzie oraz w skrypcie budującym.
"""

import unittest
from pathlib import Path

try:
    from PIL import Image
except Exception:  # pragma: no cover - Pillow zawsze jest w wymaganiach
    Image = None

ROOT = Path(__file__).resolve().parent.parent
ICON_ICO = ROOT / 'assets' / 'energodok.ico'
ICON_PNG = ROOT / 'assets' / 'energodok.png'


class AppIconFileTests(unittest.TestCase):
    def test_icon_file_exists(self):
        self.assertTrue(ICON_ICO.is_file(), 'Brak pliku assets/energodok.ico')

    def test_png_preview_exists(self):
        self.assertTrue(ICON_PNG.is_file(), 'Brak podglądu assets/energodok.png')

    def test_generator_script_exists(self):
        self.assertTrue((ROOT / 'tools' / 'make_app_icon.py').is_file())

    @unittest.skipIf(Image is None, 'Pillow nie jest zainstalowany')
    def test_icon_contains_sizes_required_by_windows(self):
        with Image.open(ICON_ICO) as icon:
            sizes = {size for size in icon.info.get('sizes', set())}
        for required in ((16, 16), (32, 32), (48, 48), (256, 256)):
            self.assertIn(required, sizes, f'Brak rozmiaru {required} w ikonie')

    @unittest.skipIf(Image is None, 'Pillow nie jest zainstalowany')
    def test_icon_is_not_blank(self):
        """Ikona musi mieć widoczną treść, a nie być przezroczystym kwadratem."""
        with Image.open(ICON_PNG) as preview:
            rgba = preview.convert('RGBA')
            alpha = rgba.getchannel('A')
        self.assertGreater(alpha.getextrema()[1], 0, 'Ikona jest pusta')


class AppIconWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_source = (ROOT / 'main.py').read_text(encoding='utf-8')
        cls.build_source = (ROOT / 'build_windows.ps1').read_text(
            encoding='utf-8-sig'
        )

    def test_application_sets_its_window_icon(self):
        self.assertIn('app.setWindowIcon(load_app_icon())', self.main_source)

    def test_main_window_sets_its_icon(self):
        self.assertIn('self.setWindowIcon(load_app_icon())', self.main_source)

    def test_windows_taskbar_identity_is_set(self):
        """Bez AppUserModelID pasek zadań pokazuje ikonę Pythona."""
        self.assertIn(
            'SetCurrentProcessExplicitAppUserModelID', self.main_source
        )

    def test_build_script_passes_the_icon_to_pyinstaller(self):
        self.assertIn('"--icon", $AppIconPath', self.build_source)

    def test_build_script_bundles_the_assets_folder(self):
        self.assertIn('$AssetsDir;assets', self.build_source)

    def test_build_script_is_plain_ascii_with_bom(self):
        """Skrypt budujący musi zostać zgodny z Windows PowerShell 5.1."""
        raw = (ROOT / 'build_windows.ps1').read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'), 'Brak znacznika BOM')
        self.assertTrue(all(byte < 128 for byte in raw[3:]))


class AppNameTests(unittest.TestCase):
    """Nazwa programu ma być krótka i spójna w oknie, w EXE i w ikonie."""

    @classmethod
    def setUpClass(cls):
        cls.main_source = (ROOT / 'main.py').read_text(encoding='utf-8')
        cls.build_source = (ROOT / 'build_windows.ps1').read_text(
            encoding='utf-8-sig'
        )

    def test_app_name_constant_exists(self):
        self.assertIn('APP_NAME = "EnergoDok"', self.main_source)

    def test_window_title_uses_the_constant(self):
        self.assertIn('self.setWindowTitle(APP_NAME)', self.main_source)

    def test_old_name_is_gone_from_the_app(self):
        """Stara nazwa nie może zostać nigdzie w interfejsie."""
        lowered = self.main_source.lower()
        self.assertNotIn('pysilde 6', lowered)
        self.assertNotIn('zarządzanie inwestycjami', lowered)

    def test_old_name_only_survives_as_icon_fallback(self):
        """Jedyne dopuszczalne wystąpienie to zgodność ze starą ikoną."""
        for line in self.main_source.splitlines():
            if 'pysilde6' in line.lower():
                self.assertIn('LEGACY_ICON_NAMES', line)

    def test_exe_is_built_under_the_new_name(self):
        self.assertIn('$AppName = "EnergoDok"', self.build_source)
        self.assertNotIn('Pysilde6', self.build_source)

    def test_project_title_keeps_the_new_name(self):
        self.assertIn(
            'f"{APP_NAME} – [Projekt: {project_name}]"', self.main_source
        )


if __name__ == '__main__':
    unittest.main()
