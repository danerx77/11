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


def _column_gap(words: list["Word"]) -> float:
    """Od jakiej przerwy między słowami zaczyna się nowa kolumna.

    Zwykły odstęp międzywyrazowy jest wąski; kolumny w tabelce wypisu
    dzieli kilka spacji. Próg liczymy z wysokości tekstu, więc działa
    niezależnie od powiększenia strony.
    """

    if not words:
        return 24.0
    height = max(w.rect.height() for w in words)
    return max(height * 1.6, 14.0)


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

    # Jeden wiersz wypisu bywa tabelką: „Powiat: kartuski   Gmina: Zukowo”.
    # Etykietę liczymy więc **wokół klikniętego słowa**, a nie od początku
    # linii — inaczej klik w „Gmina” zwracałby „Powiat”.

    # Koniec etykiety: najbliższy dwukropek od miejsca kliknięcia w prawo.
    end_index = None
    for position in range(index, len(same_line)):
        if same_line[position].text.endswith(":"):
            end_index = position
            break

    if end_index is None:
        # Kliknięto w wartość — cofamy się do dwukropka po lewej.
        for position in range(index, -1, -1):
            if same_line[position].text.endswith(":"):
                end_index = position
                break
    if end_index is None:
        end_index = index

    # Początek etykiety: za poprzednim dwukropkiem…
    start_index = 0
    for position in range(end_index - 1, -1, -1):
        if same_line[position].text.endswith(":"):
            start_index = position + 1
            break

    # …a jeśli między słowami jest szeroka przerwa, to znaczy, że zaczyna
    # się nowa kolumna tabeli — etykieta nie sięga przed tę przerwę.
    # („Obreb: 0010 MAKI      Nr obrebu: 0010” → etykieta to „Nr obrebu”.)
    gap = _column_gap(same_line)
    for position in range(end_index, start_index, -1):
        odstep = same_line[position].rect.left() - same_line[position - 1].rect.right()
        if odstep >= gap:
            start_index = position
            break

    label_chunk = same_line[start_index: end_index + 1]
    label = " ".join(w.text for w in label_chunk).strip().rstrip(":").strip()

    # Wartość: słowa za etykietą aż do następnej etykiety w tym wierszu.
    value_chunk: list[Word] = []
    previous = same_line[end_index]
    for position in range(end_index + 1, len(same_line)):
        word = same_line[position]
        if word.text.endswith(":"):
            # Zaczyna się kolejna etykieta. Jej pierwsze słowo leży za
            # ostatnią szeroką przerwą — wszystko od tego miejsca nie
            # należy już do naszej wartości.
            next_start = position
            for back in range(position, end_index + 1, -1):
                odstep = (
                    same_line[back].rect.left() - same_line[back - 1].rect.right()
                )
                if odstep >= gap:
                    next_start = back
                    break
            while value_chunk and same_line.index(value_chunk[-1]) >= next_start:
                value_chunk.pop()
            break
        if word.rect.left() - previous.rect.right() >= gap:
            break            # nowa kolumna tabeli
        value_chunk.append(word)
        previous = word
    value = " ".join(w.text for w in value_chunk).strip(" :,;-")

    left = min(w.rect.left() for w in label_chunk)
    top = min(w.rect.top() for w in label_chunk)
    right = max(w.rect.right() for w in label_chunk)
    bottom = max(w.rect.bottom() for w in label_chunk)

    value_rect = None
    if value_chunk:
        value_rect = QRectF(
            min(w.rect.left() for w in value_chunk),
            min(w.rect.top() for w in value_chunk),
            max(w.rect.right() for w in value_chunk)
            - min(w.rect.left() for w in value_chunk),
            max(w.rect.bottom() for w in value_chunk)
            - min(w.rect.top() for w in value_chunk),
        )

    return {
        "word": hit.text,
        "label": label,
        "value": value,
        "rect": QRectF(left, top, right - left, bottom - top),
        "value_rect": value_rect,
    }


class WypisPdfView(QWidget):
    """Obrazek strony wypisu, po którym można klikać.

    Sygnał :attr:`label_clicked` niesie słownik z kluczami ``word``,
    ``label`` i ``value`` — okno wzorów przypisuje to do wybranego pola.
    """

    label_clicked = Signal(dict)
    zoom_requested = Signal(int)   # +1 / -1 przy Ctrl + kółko myszy

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page: PageData | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover: QRectF | None = None
        self._hover_label = ""
        #: Pas po lewej na nazwy pól — dzięki niemu podpisy nie zasłaniają
        #: treści wypisu.
        self.margin_left = 190
        #: pole -> prostokąt etykiety (rysowane na zielono)
        self.marks: dict[str, QRectF] = {}
        #: pole -> prostokąt wartości (rysowany na niebiesko)
        self.value_marks: dict[str, QRectF] = {}
        self.setMinimumSize(200, 200)

    # ── Dane ─────────────────────────────────────────────────────────

    def set_page(self, page: PageData | None) -> None:
        self.page = page
        self._hover = None
        self._hover_label = ""
        if page is not None:
            # Przesuwamy słowa o margines, aby współrzędne kliknięć i ramek
            # zgadzały się z tym, co widać na ekranie.
            for word in page.words:
                word.rect.moveLeft(word.rect.left() + self.margin_left)
            self.setFixedSize(
                page.image.width() + self.margin_left, page.image.height()
            )
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

    def label_and_value_rects(
        self, labels: list[str]
    ) -> tuple[QRectF | None, QRectF | None]:
        """Prostokąt etykiety i stojącej obok wartości."""

        rect = self.label_rects(labels)
        if rect is None or self.page is None:
            return None, None
        hit = label_at(
            self.page,
            QPoint(int(rect.center().x()), int(rect.center().y())),
        )
        return rect, (hit.get("value_rect") if hit else None)

    # ── Rysowanie ────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802 - nazwa narzucona przez Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.page is None:
            painter.fillRect(self.rect(), QColor("#1b2a36"))
            painter.setPen(QColor("#9fb3c5"))
            painter.setFont(QFont("", 11))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Wczytaj wypis PDF, aby wskazywać pola myszą.",
            )
            return

        painter.fillRect(self.rect(), QColor("#16242f"))
        painter.drawImage(self.margin_left, 0, self.page.image)

        # Wartości odczytane — niebieska ramka przerywana.
        for rect in self.value_marks.values():
            self._draw_box(painter, rect, VALUE_COLOR, dashed=True)

        # Etykiety przypisane — zielona ramka. Podpisy rysujemy dopiero
        # na końcu, żeby nie zasłaniały ramek innych pól.
        for rect in self.marks.values():
            self._draw_box(painter, rect, FIELD_COLOR)

        self._draw_tags(painter)

        # Słowo pod kursorem — na samym wierzchu.
        if self._hover is not None:
            self._draw_box(painter, self._hover, HOVER_COLOR, strong=True)

    def _draw_box(
        self,
        painter: QPainter,
        rect: QRectF,
        color: QColor,
        *,
        dashed: bool = False,
        strong: bool = False,
    ) -> None:
        """Rysuje samą ramkę pola (bez podpisu)."""

        box = rect.adjusted(-2, -2, 2, 2)
        pen = QPen(color)
        pen.setWidth(3 if strong else 2)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)

        wash = QColor(color)
        wash.setAlpha(70 if strong else 40)
        painter.fillRect(box, wash)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 3, 3)

    def _draw_tags(self, painter: QPainter) -> None:
        """Rysuje nazwy pól na marginesie, z linią do ramki.

        Podpisy stawiamy obok dokumentu, a nie na nim — inaczej zasłaniałyby
        treść wypisu, którą użytkownik właśnie chce przeczytać.
        """

        if not self.marks:
            return

        painter.setFont(QFont("", 9, QFont.Weight.Bold))
        metrics = painter.fontMetrics()
        height = metrics.height() + 4

        # Układamy podpisy z góry na dół, bez nachodzenia na siebie.
        items = sorted(self.marks.items(), key=lambda kv: kv[1].top())
        last_bottom = -1.0
        usable = self.margin_left - 12
        for name, rect in items:
            # Nazwa musi zmieścić się na marginesie — dłuższe skracamy.
            text = f" {name} "
            if metrics.horizontalAdvance(text) + 8 > usable:
                text = " " + metrics.elidedText(
                    name, Qt.TextElideMode.ElideRight, usable - 16
                ) + " "
            width = metrics.horizontalAdvance(text) + 8

            top = max(rect.top() - 1, last_bottom + 3)
            left = self.margin_left - width - 8
            if left < 2:                      # brak marginesu: podpis nad ramką
                left = min(rect.left(), max(self.width() - width - 2, 2))
                top = max(rect.top() - height - 3, last_bottom + 3)

            tag = QRectF(left, top, width, height)

            # Linia łącząca podpis z polem na dokumencie.
            pen = QPen(QColor(FIELD_COLOR))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(
                int(tag.right()), int(tag.center().y()),
                int(rect.left() - 2), int(rect.center().y()),
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(FIELD_COLOR)
            painter.drawRoundedRect(tag, 4, 4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#10222e"))
            painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, text)
            last_bottom = tag.bottom()

    def mouseMoveEvent(self, event):  # noqa: N802
        hit = label_at(self.page, event.position().toPoint())
        rect = hit["rect"] if hit else None
        if rect != self._hover:
            self._hover = rect
            self._hover_label = hit["label"] if hit else ""
            if hit:
                value = hit.get("value") or "—"
                self.setToolTip(
                    f"Kliknij, aby przypisać etykietę „{hit['label']}”\n"
                    f"Odczytana wartość: {value}"
                )
            else:
                self.setToolTip("")
            self.update()

    def leaveEvent(self, event):  # noqa: N802
        self._hover = None
        self._hover_label = ""
        self.update()

    def wheelEvent(self, event):  # noqa: N802
        """Ctrl + kółko myszy powiększa i pomniejsza podgląd."""

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_requested.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = label_at(self.page, event.position().toPoint())
        if hit:
            self.label_clicked.emit(hit)
