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


def _header_above(page: PageData, cell: list["Word"]) -> list["Word"]:
    """Szuka nagłówka kolumny stojącego nad wskazaną komórką.

    W wypisach dane bywają w tabeli w kratkę, bez dwukropków — nazwa
    kolumny („Pow. [ha]”) stoi wtedy w wierszu nagłówka nad wartością.
    Idziemy w górę kolumny aż do jej pierwszego wiersza, bo pod nagłówkiem
    może stać kilka wierszy z danymi.
    """

    if not cell:
        return []

    gap = _column_gap(page.words)
    biezaca = cell
    ostatnia: list[Word] = []

    for _ in range(12):                     # zabezpieczenie przed pętlą
        left = min(w.rect.left() for w in biezaca)
        right = max(w.rect.right() for w in biezaca)
        top = min(w.rect.top() for w in biezaca)
        height = max(w.rect.height() for w in biezaca)

        kandydaci = []
        for word in page.words:
            if word.rect.bottom() > top - 1:
                continue                    # nie leży wyżej
            if word.rect.right() <= left or word.rect.left() >= right:
                continue                    # inna kolumna
            odleglosc = top - word.rect.bottom()
            if odleglosc > height * 6:
                continue                    # za daleko, to już nie nagłówek
            kandydaci.append((odleglosc, word))

        if not kandydaci:
            break

        najblizszy = min(kandydaci, key=lambda para: para[0])[1]

        # Cały wiersz nagłówka dzielimy na komórki i bierzemy tę, w której
        # leży znalezione słowo — dzięki temu „Opis użytku” zostaje w całości.
        wiersz = [
            w
            for w in page.words
            if w.block == najblizszy.block and w.line == najblizszy.line
        ]
        wiersz.sort(key=lambda w: w.rect.left())

        komorki: list[list[Word]] = [[wiersz[0]]]
        for poprzednie, slowo in zip(wiersz, wiersz[1:]):
            if slowo.rect.left() - poprzednie.rect.right() >= gap:
                komorki.append([slowo])
            else:
                komorki[-1].append(slowo)

        komorka = next(k for k in komorki if najblizszy in k)

        # Wiersz z dwukropkiem to opis „etykieta: wartość”, nie nagłówek.
        if any(w.text.endswith(":") for w in komorka):
            break

        ostatnia = komorka
        biezaca = komorka

    return ostatnia


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

    # ── Wiersz dzielimy na komórki ────────────────────────────────────
    # Wypis bywa tabelką: „Powiat: kartuski     Gmina: Żukowo”. Szeroka
    # przerwa rozdziela kolumny, więc każdą obsługujemy osobno. Dzięki
    # temu klik w „kartuski” nie ucieka do sąsiedniej pary.
    gap = _column_gap(same_line)
    cells: list[list[Word]] = [[same_line[0]]]
    for previous, word in zip(same_line, same_line[1:]):
        if word.rect.left() - previous.rect.right() >= gap:
            cells.append([word])
        else:
            cells[-1].append(word)

    cell_index = next(i for i, cell in enumerate(cells) if hit in cell)
    cell = cells[cell_index]

    def _text(words: list[Word]) -> str:
        return " ".join(w.text for w in words).strip()

    # ── W komórce szukamy dwukropka: przed nim etykieta, za nim wartość ──
    colon = next(
        (i for i, w in enumerate(cell) if w.text.endswith(":")),
        None,
    )

    if colon is not None:
        label_chunk = cell[: colon + 1]
        value_chunk = cell[colon + 1:]
        # Układ kolumnowy: „Powiat:” w jednej komórce, wartość w drugiej.
        if not value_chunk and cell_index + 1 < len(cells):
            nastepna = cells[cell_index + 1]
            if not any(w.text.endswith(":") for w in nastepna):
                value_chunk = nastepna
    else:
        # Komórka bez dwukropka. Jeśli poprzednia kończy się dwukropkiem,
        # to kliknięto w wartość — etykieta stoi w tamtej komórce.
        poprzednia = cells[cell_index - 1] if cell_index else []
        if poprzednia and poprzednia[-1].text.endswith(":"):
            label_chunk = poprzednia
            value_chunk = cell
        else:
            # Tabela w kratkę: nagłówek stoi NAD komórką, nie obok niej.
            naglowek = _header_above(page, cell)
            if naglowek:
                label_chunk = naglowek
                value_chunk = cell
            else:
                label_chunk = cell
                value_chunk = []

    label = _text(label_chunk).rstrip(":").strip()
    value = _text(value_chunk).strip(" :,;-")

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
