"""Testy schematów nazw folderów projektów."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.project_naming import (  # noqa: E402
    DEFAULT_TEMPLATE,
    PROJECT_FOLDER_DEFAULTS,
    SYMBOL_SEPARATOR_KEY,
    SPACE_REPLACEMENT_KEY,
    TEMPLATE_KEY,
    TEMPLATE_PRESETS,
    build_project_folder_name,
    format_symbol,
    project_folder_preview,
    sanitize_folder_name,
)

DATA = dict(
    name="Modernizacja linii",
    symbol="OBI/23/23220",
    city="Maki",
    deadline="04-12-2026",
)


class DefaultBehaviourTests(unittest.TestCase):
    """Bez zmiany ustawień nazwa folderu ma zostać taka jak dotąd."""

    def test_default_reproduces_current_name(self):
        self.assertEqual(
            build_project_folder_name(dict(PROJECT_FOLDER_DEFAULTS), **DATA),
            "Maki OBI.23.23220 04-12-2026",
        )

    def test_empty_config_uses_defaults(self):
        self.assertEqual(
            build_project_folder_name({}, **DATA),
            "Maki OBI.23.23220 04-12-2026",
        )

    def test_none_config_does_not_crash(self):
        self.assertEqual(
            build_project_folder_name(None, **DATA),
            "Maki OBI.23.23220 04-12-2026",
        )


class SymbolSeparatorTests(unittest.TestCase):
    def test_dash_separator(self):
        config = {SYMBOL_SEPARATOR_KEY: "-"}
        self.assertEqual(
            build_project_folder_name(config, **DATA),
            "Maki OBI-23-23220 04-12-2026",
        )

    def test_underscore_separator(self):
        self.assertEqual(format_symbol("OBI/23/23220", "_"), "OBI_23_23220")

    def test_empty_separator_joins_parts(self):
        self.assertEqual(format_symbol("OBI/23/23220", ""), "OBI2323220")

    def test_backslash_is_treated_like_slash(self):
        self.assertEqual(format_symbol(r"OBI\23\23220", "."), "OBI.23.23220")

    def test_symbol_without_slash_is_unchanged(self):
        self.assertEqual(format_symbol("OBI23", "-"), "OBI23")


class TemplateTests(unittest.TestCase):
    def test_date_first_variant(self):
        config = {
            TEMPLATE_KEY: "{termin} {miasto} {symbol}",
            SYMBOL_SEPARATOR_KEY: "-",
        }
        self.assertEqual(
            build_project_folder_name(config, **DATA),
            "04-12-2026 Maki OBI-23-23220",
        )

    def test_every_preset_produces_a_name(self):
        for label, template in TEMPLATE_PRESETS:
            with self.subTest(preset=label):
                name = build_project_folder_name(
                    {TEMPLATE_KEY: template}, **DATA
                )
                self.assertTrue(name, f"pusty wynik dla wzoru {template}")

    def test_missing_data_leaves_no_double_spaces(self):
        config = {TEMPLATE_KEY: "{miasto} {symbol} {termin}"}
        name = build_project_folder_name(
            config, name="Projekt", symbol="", city="Maki", deadline="04-12-2026"
        )
        self.assertEqual(name, "Maki 04-12-2026")

    def test_unknown_placeholder_is_removed(self):
        config = {TEMPLATE_KEY: "{miasto} {nieistnieje}"}
        self.assertEqual(build_project_folder_name(config, **DATA), "Maki")

    def test_empty_brackets_are_removed(self):
        config = {TEMPLATE_KEY: "{nazwa} [{symbol}]"}
        name = build_project_folder_name(
            config, name="Projekt", symbol="", city="", deadline=""
        )
        self.assertEqual(name, "Projekt")

    def test_blank_template_falls_back_to_default(self):
        self.assertEqual(
            build_project_folder_name({TEMPLATE_KEY: "   "}, **DATA),
            build_project_folder_name({TEMPLATE_KEY: DEFAULT_TEMPLATE}, **DATA),
        )

    def test_template_producing_nothing_falls_back_to_name(self):
        config = {TEMPLATE_KEY: "{symbol}"}
        name = build_project_folder_name(
            config, name="Projekt awaryjny", symbol="", city="", deadline=""
        )
        self.assertEqual(name, "Projekt awaryjny")


class SpaceReplacementTests(unittest.TestCase):
    def test_spaces_can_become_underscores(self):
        config = {SPACE_REPLACEMENT_KEY: "_"}
        self.assertEqual(
            build_project_folder_name(config, **DATA),
            "Maki_OBI.23.23220_04-12-2026",
        )

    def test_replacement_does_not_double_up(self):
        config = {SPACE_REPLACEMENT_KEY: "-", TEMPLATE_KEY: "{miasto}  {termin}"}
        self.assertEqual(
            build_project_folder_name(config, **DATA), "Maki-04-12-2026"
        )


class SanitizeTests(unittest.TestCase):
    def test_forbidden_characters_are_replaced(self):
        self.assertEqual(sanitize_folder_name('a:b*c?d"e<f>g|h'), "a_b_c_d_e_f_g_h")

    def test_trailing_dot_and_space_are_stripped(self):
        self.assertEqual(sanitize_folder_name("Projekt . "), "Projekt")

    def test_slash_never_survives_in_folder_name(self):
        name = build_project_folder_name(
            {TEMPLATE_KEY: "{nazwa}"}, name="A/B", symbol="", city="", deadline=""
        )
        self.assertNotIn("/", name)


class PreviewTests(unittest.TestCase):
    def test_preview_matches_build(self):
        config = {SYMBOL_SEPARATOR_KEY: "-"}
        self.assertEqual(
            project_folder_preview(config),
            build_project_folder_name(
                config,
                name="Modernizacja linii",
                symbol="OBI/23/23220",
                city="Maki",
                deadline="04-12-2026",
            ),
        )

    def test_preview_can_override_template(self):
        self.assertEqual(
            project_folder_preview({}, template="{miasto}"),
            "Maki",
        )


if __name__ == "__main__":
    unittest.main()


class NewProjectDialogWiringTests(unittest.TestCase):
    """Okno „Nowy projekt” ma mieć wybór separatora pod ręką."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.source = (root / "modules" / "projekty.py").read_text(encoding="utf-8")

    def test_dialog_offers_the_separator_choice(self):
        self.assertIn("separator_combo", self.source)
        self.assertIn("SYMBOL_SEPARATOR_CHOICES", self.source)

    def test_dash_and_underscore_are_available(self):
        from utils.project_naming import SYMBOL_SEPARATOR_CHOICES

        values = {value for _label, value in SYMBOL_SEPARATOR_CHOICES}
        self.assertIn("-", values)
        self.assertIn("_", values)
        self.assertIn(".", values)

    def test_preview_uses_the_choice_from_the_dialog(self):
        self.assertIn("_folder_config", self.source)

    def test_created_folder_matches_the_preview(self):
        self.assertIn("vals.get('folder_name')", self.source)
