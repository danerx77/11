"""Testy nazw kart modułów.

Karta modułu wróciła z nazwy „eKW” na „KW2”. Zapisana kolejność zakładek
przechowuje nazwy tekstem, więc program musi rozpoznać także poprzednie
warianty, aby użytkownik nie stracił swojego układu.
"""

import ast
import unittest
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parent.parent / 'main.py'


def _load_tab_helpers():
    """Wyciąga z main.py stałe i funkcję nazw kart bez importowania Qt."""
    tree = ast.parse(MAIN_PY.read_text(encoding='utf-8'))
    wanted_assign = {
        'KW2_TAB_NAME',
        'LEGACY_KW2_TAB_NAMES',
        'EKW_TAB_NAME',
        'LEGACY_EKW_TAB_NAMES',
    }
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & wanted_assign:
                body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == 'tab_name_matches_saved_name':
            body.append(node)
    namespace: dict = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), 'main.py', 'exec'), namespace)
    return namespace


class TabNamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _load_tab_helpers()

    def test_module_is_named_kw2_again(self):
        self.assertEqual(self.ns['KW2_TAB_NAME'], 'KW2')

    def test_old_alias_still_points_at_new_name(self):
        self.assertEqual(self.ns['EKW_TAB_NAME'], 'KW2')

    def test_saved_layout_with_ekw_name_is_recognized(self):
        matches = self.ns['tab_name_matches_saved_name']
        self.assertTrue(matches('KW2', 'eKW'))

    def test_saved_layout_with_original_kw_2_name_is_recognized(self):
        matches = self.ns['tab_name_matches_saved_name']
        self.assertTrue(matches('KW2', '📖 KW 2 — ręcznie'))
        self.assertTrue(matches('KW2', '📖 KW 2 — ręczne przeglądanie'))
        self.assertTrue(matches('KW2', 'KW 2'))

    def test_identical_names_match(self):
        matches = self.ns['tab_name_matches_saved_name']
        self.assertTrue(matches('KW2', 'KW2'))
        self.assertTrue(matches('📁 Projekty', '📁 Projekty'))

    def test_unrelated_names_do_not_match(self):
        matches = self.ns['tab_name_matches_saved_name']
        self.assertFalse(matches('KW2', '📚 Księgi wieczyste KW'))
        self.assertFalse(matches('📁 Projekty', 'eKW'))

    def test_no_stale_ekw_tab_label_left_in_main(self):
        """Nazwa karty w main.py nie może już brzmieć „eKW”."""
        source = MAIN_PY.read_text(encoding='utf-8')
        self.assertNotIn('EKW_TAB_NAME = "eKW"', source)
        self.assertIn('KW2_TAB_NAME = "KW2"', source)


if __name__ == '__main__':
    unittest.main()
