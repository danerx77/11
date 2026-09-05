"""Testy folderów docelowych dla generowanych dokumentów."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.output_paths import (  # noqa: E402
    DEFAULT_FOLDERS,
    DEFAULT_PROJECTS_SUBFOLDER,
    OUTPUT_TARGETS,
    PROJECTS_ROOT_KEY,
    USE_PROJECTS_SUBFOLDER_KEY,
    auto_key,
    folder_key,
    folder_name,
    is_auto_enabled,
    output_defaults,
    project_output_dir,
    projects_root,
)


class DefaultsTests(unittest.TestCase):
    def test_every_module_is_automatic_by_default(self):
        defaults = output_defaults()
        for key, _label, _folder in OUTPUT_TARGETS:
            with self.subTest(target=key):
                self.assertTrue(defaults[auto_key(key)])

    def test_folder_names_match_the_request(self):
        self.assertEqual(DEFAULT_FOLDERS["declarations"], "Oswiadczenia")
        self.assertEqual(DEFAULT_FOLDERS["cover_letters"], "Pisma")
        self.assertEqual(DEFAULT_FOLDERS["druczki"], "Druczki")
        self.assertEqual(DEFAULT_FOLDERS["split_pdf"], "Wydzielone dzialki")
        self.assertEqual(DEFAULT_FOLDERS["legal_titles"], "Tytuly prawne")

    def test_defaults_contain_folder_names(self):
        defaults = output_defaults()
        for key, _label, folder in OUTPUT_TARGETS:
            with self.subTest(target=key):
                self.assertEqual(defaults[folder_key(key)], folder)


class AutoSwitchTests(unittest.TestCase):
    def test_enabled_when_config_is_empty(self):
        self.assertTrue(is_auto_enabled({}, "declarations"))

    def test_can_be_switched_off(self):
        config = {auto_key("declarations"): False}
        self.assertFalse(is_auto_enabled(config, "declarations"))

    def test_switch_is_per_module(self):
        config = {auto_key("declarations"): False}
        self.assertTrue(is_auto_enabled(config, "cover_letters"))

    def test_missing_config_is_treated_as_enabled(self):
        self.assertTrue(is_auto_enabled(None, "druczki"))


class FolderNameTests(unittest.TestCase):
    def test_custom_folder_is_used(self):
        config = {folder_key("declarations"): "Moje oswiadczenia"}
        self.assertEqual(folder_name(config, "declarations"), "Moje oswiadczenia")

    def test_blank_falls_back_to_default(self):
        config = {folder_key("declarations"): "   "}
        self.assertEqual(folder_name(config, "declarations"), "Oswiadczenia")

    def test_path_traversal_is_rejected(self):
        config = {folder_key("declarations"): "../../gdzie indziej"}
        self.assertEqual(folder_name(config, "declarations"), "Oswiadczenia")

    def test_leading_slash_is_stripped(self):
        config = {folder_key("druczki"): "/Druczki/2026"}
        self.assertEqual(folder_name(config, "druczki"), "Druczki/2026")


class ProjectOutputDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_folder_is_created_inside_the_project(self):
        result = project_output_dir({}, "declarations", self.project)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Oswiadczenia")
        self.assertTrue(result.is_dir())
        self.assertEqual(result.parent, self.project)

    def test_disabled_switch_returns_none(self):
        config = {auto_key("declarations"): False}
        self.assertIsNone(
            project_output_dir(config, "declarations", self.project)
        )

    def test_missing_project_returns_none(self):
        self.assertIsNone(project_output_dir({}, "declarations", ""))

    def test_nonexistent_project_returns_none(self):
        self.assertIsNone(
            project_output_dir({}, "declarations", "/nie/ma/takiego/folderu")
        )

    def test_each_module_gets_its_own_folder(self):
        names = set()
        for key, _label, _folder in OUTPUT_TARGETS:
            result = project_output_dir({}, key, self.project)
            self.assertIsNotNone(result)
            names.add(result.name)
        self.assertEqual(len(names), len(OUTPUT_TARGETS))

    def test_existing_folder_is_reused(self):
        first = project_output_dir({}, "druczki", self.project)
        second = project_output_dir({}, "druczki", self.project)
        self.assertEqual(first, second)

    def test_create_false_does_not_make_the_folder(self):
        result = project_output_dir(
            {}, "legal_titles", self.project, create=False
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.exists())


class ProjectsRootTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.app_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_defaults_to_the_projects_subfolder(self):
        result = projects_root({}, self.app_dir)
        self.assertEqual(result.name, DEFAULT_PROJECTS_SUBFOLDER)
        self.assertEqual(result.parent, self.app_dir)

    def test_configured_folder_wins(self):
        chosen = self.app_dir / "gdzie indziej"
        config = {PROJECTS_ROOT_KEY: str(chosen)}
        self.assertEqual(projects_root(config, self.app_dir), chosen)

    def test_subfolder_can_be_switched_off(self):
        config = {USE_PROJECTS_SUBFOLDER_KEY: False}
        self.assertEqual(projects_root(config, self.app_dir), self.app_dir)

    def test_folder_is_created_on_request(self):
        result = projects_root({}, self.app_dir, create=True)
        self.assertTrue(result.is_dir())

    def test_blank_configured_root_falls_back(self):
        config = {PROJECTS_ROOT_KEY: "   "}
        self.assertEqual(
            projects_root(config, self.app_dir).name, DEFAULT_PROJECTS_SUBFOLDER
        )


if __name__ == "__main__":
    unittest.main()
