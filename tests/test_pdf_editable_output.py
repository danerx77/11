"""Testy zapisu druczków: gotowy PDF musi dać się edytować w innych programach.

Druczki pobierane z Poczty Polskiej bywają zabezpieczone hasłem właściciela
i ograniczonymi uprawnieniami. Jeżeli te ograniczenia trafią do pliku
wynikowego, użytkownik nie może poprawić adresu w Acrobacie ani w innym
edytorze PDF. Tu sprawdzamy, że nasz zapis takich blokad nie przenosi.
"""

import tempfile
import unittest
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - brak biblioteki w środowisku CI
    fitz = None

if fitz is not None:
    from utils.pdf_utils import _all_pdf_permissions, _save_editable_pdf
else:  # pragma: no cover
    _all_pdf_permissions = _save_editable_pdf = None


@unittest.skipIf(fitz is None, 'PyMuPDF nie jest zainstalowany')
class EditablePdfSaveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_document(self, text='Druczek testowy'):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), text)
        return doc

    def test_permissions_mask_is_not_empty(self):
        self.assertNotEqual(_all_pdf_permissions(), 0)

    def test_saved_pdf_is_not_encrypted(self):
        doc = self._make_document()
        out = self.tmp_path / 'plain.pdf'
        _save_editable_pdf(doc, str(out))
        doc.close()

        saved = fitz.open(str(out))
        self.assertFalse(saved.is_encrypted)
        self.assertFalse(saved.needs_pass)
        saved.close()

    def test_saved_pdf_allows_modification_and_copying(self):
        doc = self._make_document()
        out = self.tmp_path / 'perms.pdf'
        _save_editable_pdf(doc, str(out))
        doc.close()

        saved = fitz.open(str(out))
        self.assertTrue(saved.permissions & fitz.PDF_PERM_MODIFY)
        self.assertTrue(saved.permissions & fitz.PDF_PERM_COPY)
        self.assertTrue(saved.permissions & fitz.PDF_PERM_PRINT)
        self.assertTrue(saved.permissions & fitz.PDF_PERM_ANNOTATE)
        saved.close()

    def test_restrictions_from_protected_template_are_dropped(self):
        """Szablon z hasłem właściciela nie może zablokować pliku wynikowego."""
        protected = self.tmp_path / 'protected.pdf'
        doc = self._make_document('Szablon Poczty')
        doc.save(
            str(protected),
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw='sekret',
            permissions=fitz.PDF_PERM_PRINT,  # tylko druk, bez edycji
        )
        doc.close()

        template = fitz.open(str(protected))
        # PyMuPDF otwiera taki plik pustym hasłem użytkownika, ale zachowuje
        # ograniczenia właściciela — dokładnie jak druczek z Poczty.
        self.assertFalse(
            template.permissions & fitz.PDF_PERM_MODIFY,
            'Szablon testowy powinien mieć zablokowaną edycję',
        )
        template.authenticate('')

        out = self.tmp_path / 'wynik.pdf'
        _save_editable_pdf(template, str(out))
        template.close()

        saved = fitz.open(str(out))
        self.assertFalse(saved.is_encrypted, 'Wynik nie może być zaszyfrowany')
        self.assertTrue(
            saved.permissions & fitz.PDF_PERM_MODIFY,
            'Gotowy druczek musi pozwalać na edycję w innych programach',
        )
        saved.close()

    def test_saved_pdf_keeps_its_content(self):
        doc = self._make_document('Jan Kowalski')
        out = self.tmp_path / 'tresc.pdf'
        _save_editable_pdf(doc, str(out))
        doc.close()

        saved = fitz.open(str(out))
        self.assertIn('Jan Kowalski', saved[0].get_text())
        saved.close()

    def test_saved_pdf_can_be_edited_afterwards(self):
        """Po zapisie da się dopisać tekst i ponownie zapisać plik."""
        doc = self._make_document()
        out = self.tmp_path / 'edytowalny.pdf'
        _save_editable_pdf(doc, str(out))
        doc.close()

        reopened = fitz.open(str(out))
        reopened[0].insert_text((72, 120), 'Dopisane pole')
        edited = self.tmp_path / 'po_edycji.pdf'
        reopened.save(str(edited))
        reopened.close()

        check = fitz.open(str(edited))
        self.assertIn('Dopisane pole', check[0].get_text())
        check.close()


if __name__ == '__main__':
    unittest.main()
