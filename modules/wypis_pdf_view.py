"""Graficzny podgląd wypisu PDF — wskazywanie pól myszą.

Zamiast przepisywać nazwy pól z dokumentu do tabeli, użytkownik widzi
prawdziwą stronę wypisu i **klika w etykietę na obrazku**. Widok zna
położenie każdego słowa na stronie, więc potrafi:

* podświetlić słowo pod kursorem (podpowiedź, w co można kliknąć),
* zwrócić klikniętą etykietę razem z wartością stojącą po jej prawej,
* narysować kolorowe ramki na polach już przypisanych.

Dzięki temu „co jest czym” ustawia się wzrokowo, tak jak na papierze.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

#: Kolory ramek pól przypisanych — te same, co statusy w tabeli.
FIELD_COLOR = QColor("#2ecc71")
VALUE_COLOR = QColor("#3498db")
HOVER_COLOR = QColor("#f1c40f")


def _fold(value: str) -> str:
    """Tekst bez ogonków i wielkich liter — do porównań etykiet.

    Wypisy bywają drukowane bez polskich znaków („Wojewodztwo”), więc
    dopasowanie musi je traktować tak samo jak zapis z ogonkami.
    """

    table = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return " ".join(str(value or "").translate(table).lower().split())


@dataclass
class Word:
    """Pojedyncze słowo na stronie razem z jego prostokątem."""

    text: str
    rect: QRectF
    line: int
    block: int


@dataclass
class PageData:
    """Wyrenderowana strona i jej słowa."""

    image: QImage
    words: list[Word] = field(default_factory=list)
    scale: float = 1.0


def load_page(pdf_path: str, page_number: int = 0, dpi: int = 96) -> PageData | None:
    """Renderuje stronę PDF i odczytuje położenie wszystkich słów."""

    try:
        import fitz
    except Exception:
        return None

    try:
        with fitz.open(pdf_path) as doc:
            if page_number >= doc.page_count:
                return None
            page = doc[page_number]
            pix = page.get_pixmap(dpi=dpi)
            image = QImage(
                pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888
            ).copy()
            scale = dpi / 72.0
            words = [
                Word(
                    text=w[4],
                    rect=QRectF(
                        w[0] * scale, w[1] * scale,
                        (w[2] - w[0]) * scale, (w[3] - w[1]) * scale,
                    ),
                    block=int(w[5]),
                    line=int(w[6]),
                )
                for w in page.get_text("words")
            ]
        return PageData(image=image, words=words, scale=scale)
    except Exception:
        return None


def page_count(pdf_path: str) -> int:
    """Liczba stron dokumentu (0, gdy pliku nie da się otworzyć)."""

    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except Exception:
        return 0


def label_at(page: PageData, point: QPoint) -> dict[str, Any] | None:
    """Zwraca słowo (lub grupę słów) wskazane kursorem.

    Etykiety w wypisach bywają kilkuwyrazowe („Adres nieruchomości”),
    dlatego zwracamy też całą frazę od początku linii do klikniętego
    słowa oraz tekst stojący dalej w tej samej linii — czyli wartość.
    """

    if page is None:
        return None

    hit = None
    for word in page.words:
        if word.rect.contains(point):
            hit = word
            break
    if hit is None:
        # Kursor mógł trafić w odstęp między słowami — bierzemy słowo
        # z tej samej wysokości, leżące najbliżej w poziomie.
        best = None
        for word in page.words:
            if word.rect.top() <= point.y() <= word.rect.bottom():
                if word.rect.left() - 12 <= point.x() <= word.rect.right() + 12:
                    distance = min(
                        abs(word.rect.left() - point.x()),
                        abs(word.rect.right() - point.x()),
                    )
                    if best is None or distance < best[0]:
                        best = (distance, word)
        hit = best[1] if best else None
    if hit is None:
        return None

    same_line = [
        w for w in page.words if w.block == hit.block and w.line == hit.line
    ]
    same_line.sort(key=lambda w: w.rect.left())

    index = same_line.index(hit)

    # Etykieta kończy się na dwukropku — „Dzialka nr: 145/7” to etykieta
    # „Dzialka nr”, nie samo słowo, w które akurat trafił kursor. Jeśli
    # w linii jest dwukropek, bierzemy wszystko do niego.
    end = index
    for position, word in enumerate(same_line):
        if word.text.endswith(":"):
            end = position
            break
    else:
        end = index

    # Kliknięcie za dwukropkiem (czyli w wartość) nie zmienia etykiety.
    if index > end:
        end = end
    label_words = [w.text for w in same_line[: end + 1]]
    label = " ".join(label_words).strip().rstrip(":").strip()
    # Wartość: reszta linii za etykietą.
    value = " ".join(w.text for w in same_line[end + 1:]).strip(" :,;-")
    index = end

    left = min(w.rect.left() for w in same_line[: index + 1])
    top = min(w.rect.top() for w in same_line[: index + 1])
    right = max(w.rect.right() for w in same_line[: index + 1])
    bottom = max(w.rect.bottom() for w in same_line[: index + 1])

    return {
        "word": hit.text,
        "label": label,
        "value": value,
        "rect": QRectF(left, top, right - left, bottom - top),
    }


class WypisPdfView(QWidget):
    """Obrazek strony wypisu, po którym można klikać.

    Sygnał :attr:`label_clicked` niesie słownik z kluczami ``word``,
    ``label`` i ``value`` — okno wzorów przypisuje to do wybranego pola.
    """

    label_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page: PageData | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover: QRectF | None = None
        #: pole -> prostokąt etykiety (rysowane na zielono)
        self.marks: dict[str, QRectF] = {}
        #: pole -> prostokąt wartości (rysowany na niebiesko)
        self.value_marks: dict[str, QRectF] = {}
        self.setMinimumSize(200, 200)

    # ── Dane ─────────────────────────────────────────────────────────

    def set_page(self, page: PageData | None) -> None:
        self.page = page
        self._hover = None
        if page is not None:
            self.setFixedSize(page.image.width(), page.image.height())
        self.update()

    def set_marks(
        self,
        marks: dict[str, QRectF] | None,
        value_marks: dict[str, QRectF] | None = None,
    ) -> None:
        """Ustawia ramki pól już przypisanych."""

        self.marks = dict(marks or {})
        self.value_marks = dict(value_marks or {})
        self.update()

    def find_label_rect(self, label: str) -> QRectF | None:
        """Szuka na stronie prostokąta podanej etykiety."""

        if self.page is None or not str(label or "").strip():
            return None

        needle = _fold(label)
        by_line: dict[tuple[int, int], list[Word]] = {}
        for word in self.page.words:
            by_line.setdefault((word.block, word.line), []).append(word)

        for words in by_line.values():
            words.sort(key=lambda w: w.rect.left())
            for start in range(len(words)):
                phrase = ""
                for end in range(start, len(words)):
                    phrase = (phrase + " " + words[end].text).strip()
                    cleaned = _fold(phrase.rstrip(":"))
                    if cleaned == needle:
                        chunk = words[start: end + 1]
                        left = min(w.rect.left() for w in chunk)
                        top = min(w.rect.top() for w in chunk)
                        right = max(w.rect.right() for w in chunk)
                        bottom = max(w.rect.bottom() for w in chunk)
                        return QRectF(left, top, right - left, bottom - top)
                    if len(cleaned) > len(needle):
                        break
        return None

    def label_rects(self, labels: list[str]) -> QRectF | None:
        """Pierwszy pasujący prostokąt z listy etykiet.

        Etykiety sprawdzamy od najdłuższej, żeby „Pow. [ha]” wygrało
        z krótszym „Pow.” stojącym w tej samej linii.
        """

        for label in sorted(labels or [], key=len, reverse=True):
            rect = self.find_label_rect(label)
            if rect is not None:
                return rect
        return None

    # ── Rysowanie ────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802 - nazwa narzucona przez Qt
        painter = QPainter(self)
        if self.page is None:
            painter.fillRect(self.rect(), QColor("#20303d"))
            painter.setPen(QColor("#9fb3c5"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Wczytaj wypis PDF, aby wskazywać pola myszą.",
            )
            return

        painter.drawImage(0, 0, self.page.image)

        # Pola już przypisane — etykieta na zielono, wartość na niebiesko.
        for key, rect in self.value_marks.items():
            self._draw_box(painter, rect, VALUE_COLOR, fill=True)
        for key, rect in self.marks.items():
            self._draw_box(painter, rect, FIELD_COLOR, fill=True, label=key)

        # Słowo pod kursorem.
        if self._hover is not None:
            self._draw_box(painter, self._hover, HOVER_COLOR, fill=True)

    def _draw_box(
        self,
        painter: QPainter,
        rect: QRectF,
        color: QColor,
        *,
        fill: bool = False,
        label: str = "",
    ) -> None:
        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        if fill:
            wash = QColor(color)
            wash.setAlpha(60)
            painter.fillRect(rect, wash)
        painter.drawRect(rect)

        if label:
            font = QFont("", 8, QFont.Weight.Bold)
            painter.setFont(font)
            # Szerokość podpisu liczymy z tekstu, żeby nazwa pola nie była ucięta.
            text = f" {label} "
            width = painter.fontMetrics().horizontalAdvance(text) + 2
            top = rect.top() - 14
            if top < 0:                     # etykieta przy górnej krawędzi strony
                top = rect.bottom() + 1
            tag = QRectF(rect.left(), top, width, 13)
            painter.fillRect(tag, color)
            painter.setPen(QColor("#10222e"))
            painter.drawText(tag, Qt.AlignmentFlag.AlignVCenter, text)

    # ── Mysz ─────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):  # noqa: N802
        hit = label_at(self.page, event.position().toPoint())
        rect = hit["rect"] if hit else None
        if rect != self._hover:
            self._hover = rect
            self.setToolTip(
                f"Kliknij, aby przypisać: „{hit['label']}”" if hit else ""
            )
            self.update()

    def leaveEvent(self, event):  # noqa: N802
        self._hover = None
        self.update()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = label_at(self.page, event.position().toPoint())
        if hit:
            self.label_clicked.emit(hit)
