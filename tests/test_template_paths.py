"""Testy wyboru katalogu szablonów i nazw wzorów Tytułów Prawnych."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from utils.templates import (
    EXAMPLES_FOLDER_NAMES,
    LEGAL_TITLES_TEMPLATE_SPECS,
    STAMP_FOLDER_NAMES,
    find_file_newest,
    resolve_template_start_directory,
)


class TemplateStartDirectoryTests(unittest.TestCase):
    def test_configured_examples_directory_has_priority_over_current_file(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            examples = root / "przykłady"
            current_dir = root / "other"
            examples.mkdir()
            current_dir.mkdir()
            current_template = current_dir / "template.docx"
            current_template.touch()

            result = resolve_template_start_directory(
                {"path_przyklady": str(examples)},
                config_key="path_przyklady",
                folder_names=EXAMPLES_FOLDER_NAMES,
                current_path=current_template,
            )

            self.assertEqual(result, examples)

    def test_configured_stamps_directory_is_used_for_stamp_pdf_picker(self):
        with TemporaryDirectory() as temp_dir:
            stamps = Path(temp_dir) / "znaczki"
            stamps.mkdir()

            result = resolve_template_start_directory(
                {"path_znaczki": str(stamps)},
                config_key="path_znaczki",
                folder_names=STAMP_FOLDER_NAMES,
            )

            self.assertEqual(result, stamps)

    def test_unsaved_preferred_directory_has_priority_in_settings(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saved_examples = root / "saved"
            edited_examples = root / "edited"
            saved_examples.mkdir()
            edited_examples.mkdir()

            result = resolve_template_start_directory(
                {"path_przyklady": str(saved_examples)},
                config_key="path_przyklady",
                folder_names=EXAMPLES_FOLDER_NAMES,
                preferred_folder=edited_examples,
            )

            self.assertEqual(result, edited_examples)

    def test_current_template_parent_is_used_without_configured_folder(self):
        with TemporaryDirectory() as temp_dir:
            template = Path(temp_dir) / "templates" / "pismo.docx"
            template.parent.mkdir()
            template.touch()

            result = resolve_template_start_directory(
                {},
                config_key="path_przyklady",
                folder_names=("not-present",),
                current_path=template,
            )

            self.assertEqual(result, template.parent)


class LegalTitlesTemplateNamesTests(unittest.TestCase):
    def test_template_positions_have_the_expected_names(self):
        self.assertEqual(
            tuple(label for label, _bases in LEGAL_TITLES_TEMPLATE_SPECS),
            (
                "Wykaz działek podmiotów pozostałych",
                "Wykaz właścicieli nieruchomości szczegółowy",
                "Nowa tabela końcowa",
            ),
        )

    def test_each_named_legal_template_is_found_by_its_new_name(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for label, _bases in LEGAL_TITLES_TEMPLATE_SPECS:
                (folder / f"{label}.xlsx").touch()

            for label, bases in LEGAL_TITLES_TEMPLATE_SPECS:
                with self.subTest(template=label):
                    found = find_file_newest(folder, bases)
                    self.assertIsNotNone(found)
                    self.assertEqual(found.name, f"{label}.xlsx")

    def test_legacy_generic_template_names_remain_supported(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for index, (_label, bases) in enumerate(LEGAL_TITLES_TEMPLATE_SPECS, start=1):
                legacy = folder / f"szablon {index}.xlsm"
                legacy.touch()
                found = find_file_newest(folder, bases)
                self.assertEqual(found, legacy)


if __name__ == "__main__":
    unittest.main()
