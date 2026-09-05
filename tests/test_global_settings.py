"""Testy globalnych profili C5/C6 i druczków zapisanych w folderze dane."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from utils.global_settings import (
    DRUCZEK_PROFILE_FILE,
    ENVELOPE_PREFERENCES_FILE,
    STAMP_SETTINGS_FILE,
    WYPIS_PROFILES_FILE,
    get_global_data_dir,
    wypis_profiles_path,
    load_global_druczek_profile,
    load_global_envelope_preferences,
    load_global_stamp_settings,
    save_global_druczek_profile,
    save_global_envelope_preferences,
    save_global_stamp_settings,
)


class GlobalSettingsTests(unittest.TestCase):
    def test_data_directory_is_global_under_application_directory(self):
        with TemporaryDirectory() as temp_dir:
            self.assertEqual(
                get_global_data_dir(temp_dir),
                Path(temp_dir) / "dane",
            )

    def test_wypis_profiles_have_their_own_file_in_data_directory(self):
        """Wzory odczytu wypisów są osobnym plikiem, nie częścią ustawień."""
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "dane"
            self.assertEqual(
                wypis_profiles_path(data_dir),
                data_dir / WYPIS_PROFILES_FILE,
            )
            self.assertNotIn("app_config", WYPIS_PROFILES_FILE)
            self.assertNotEqual(WYPIS_PROFILES_FILE, STAMP_SETTINGS_FILE)
            self.assertNotEqual(WYPIS_PROFILES_FILE, DRUCZEK_PROFILE_FILE)

    def test_c5_and_c6_crop_profiles_round_trip_in_data_directory(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "dane"
            config = {
                "stamp_profile_c5": {
                    "crop_left": 91,
                    "crop_right": 92,
                    "crop_up": 93,
                    "crop_down": 94,
                },
                "stamp_profile_c6": {
                    "crop_left": -1,
                    "crop_right": 2,
                    "crop_up": -3,
                    "crop_down": 4,
                },
                "stamp_window_geom_C5": "c5-geometry",
                "stamp_window_geom_C6": "c6-geometry",
            }

            self.assertTrue(save_global_stamp_settings(config, data_dir))
            self.assertTrue((data_dir / STAMP_SETTINGS_FILE).is_file())
            self.assertEqual(load_global_stamp_settings(data_dir), config)

    def test_druczek_profile_round_trips_in_data_directory(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "dane"
            profile = {
                "cols": 2,
                "rows": 3,
                "s_font": "Calibri",
                "an_x": 180,
                "an_size": 12,
            }

            self.assertTrue(save_global_druczek_profile(profile, data_dir))
            self.assertTrue((data_dir / DRUCZEK_PROFILE_FILE).is_file())
            self.assertEqual(load_global_druczek_profile(data_dir), profile)

    def test_envelope_sorting_and_view_choices_round_trip_globally(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "dane"
            config = {
                "envelope_view_sort": 1,
                "envelope_generation_sort": 1,
                "envelope_hide_generated": True,
                "envelope_show_only_generated": False,
                "envelope_single_files": True,
                "envelope_stamps_tab": 1,
                "envelope_table_state": "00ab12",
                # Dane projektu nie mogą dostać się do profilu globalnego.
                "envelope_output_dir": "C:/projekt/koperty",
            }

            self.assertTrue(save_global_envelope_preferences(config, data_dir))
            self.assertTrue((data_dir / ENVELOPE_PREFERENCES_FILE).is_file())
            self.assertEqual(
                load_global_envelope_preferences(data_dir),
                {
                    "envelope_view_sort": 1,
                    "envelope_generation_sort": 1,
                    "envelope_hide_generated": True,
                    "envelope_show_only_generated": False,
                    "envelope_single_files": True,
                    "envelope_stamps_tab": 1,
                    "envelope_table_state": "00ab12",
                },
            )

    def test_missing_or_invalid_files_do_not_break_startup(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "dane"
            self.assertEqual(load_global_stamp_settings(data_dir), {})
            self.assertEqual(load_global_druczek_profile(data_dir), {})

            data_dir.mkdir()
            (data_dir / STAMP_SETTINGS_FILE).write_text("not json", encoding="utf-8")
            (data_dir / DRUCZEK_PROFILE_FILE).write_text("[]", encoding="utf-8")
            self.assertEqual(load_global_stamp_settings(data_dir), {})
            self.assertEqual(load_global_druczek_profile(data_dir), {})


if __name__ == "__main__":
    unittest.main()
