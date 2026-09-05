"""Czysta logika odczytu i prezentacji statusów Poczty Polskiej.

Usługa SOAP Poczty Polskiej zwraca pełną listę zdarzeń. Ten moduł zachowuje
oryginalne nazwy zdarzeń, daty oraz placówki; kategorie służą wyłącznie do
wizualnego podsumowania w historii przesyłek.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import re
import unicodedata
from typing import Any
from xml.etree import ElementTree as ET


TRACKING_CATEGORY_ORDER = (
    "Doręczona / odebrana",
    "W doręczeniu",
    "W transporcie",
    "Nadana",
    "Awizowana",
    "Zwrot / niedoręczona",
    "Nie pobrano",
    "Problem z pobraniem",
    "Inny status",
)

# Kolory statusów są wspólne dla tabeli, kart podsumowania i pełnej historii.
# Dobrano je tak, aby były czytelne w motywie ciemnym i jasnym.
TRACKING_STATUS_COLORS = {
    "Doręczona / odebrana": "#2ecc71",
    "W doręczeniu": "#40c4ff",
    "W transporcie": "#00b4d8",
    "Nadana": "#f1c40f",
    "Awizowana": "#ff9800",
    "Zwrot / niedoręczona": "#e74c3c",
    "Nie pobrano": "#9e9e9e",
    "Problem z pobraniem": "#e74c3c",
    "Inny status": "#b39ddb",
}
DEFAULT_TRACKING_COLOR = "#b39ddb"

# Ikona ułatwia rozpoznanie statusu również przy wydruku i kopiowaniu tekstu.
TRACKING_STATUS_ICONS = {
    "Doręczona / odebrana": "✅",
    "W doręczeniu": "🚚",
    "W transporcie": "📦",
    "Nadana": "📮",
    "Awizowana": "📭",
    "Zwrot / niedoręczona": "↩️",
    "Nie pobrano": "⏳",
    "Problem z pobraniem": "⚠️",
    "Inny status": "ℹ️",
}


def tracking_status_color(status_or_event: object) -> str:
    """Zwraca kolor HTML dla statusu albo zdarzenia Poczty Polskiej."""

    category = (
        status_or_event
        if isinstance(status_or_event, str) and status_or_event in TRACKING_STATUS_COLORS
        else tracking_status_category(status_or_event)
    )
    return TRACKING_STATUS_COLORS.get(category, DEFAULT_TRACKING_COLOR)


def tracking_status_icon(status_or_event: object) -> str:
    """Zwraca ikonę statusu używaną w tabeli i w oknie pełnej historii."""

    category = (
        status_or_event
        if isinstance(status_or_event, str) and status_or_event in TRACKING_STATUS_ICONS
        else tracking_status_category(status_or_event)
    )
    return TRACKING_STATUS_ICONS.get(category, "ℹ️")


def normalize_tracking_code(code: object) -> str:
    """Usuwa spacje, nawiasy i separatory z kodu przesyłki."""
    value = str(code or "").strip().replace("(00)", "00")
    return re.sub(r"[^0-9A-Za-z]", "", value)


def _local_name(tag: str) -> str:
    return str(tag).split("}", 1)[-1].lower()


def _direct_child(element: ET.Element, names: tuple[str, ...]) -> ET.Element | None:
    wanted = set(names)
    return next(
        (child for child in list(element) if _local_name(child.tag) in wanted),
        None,
    )


def _direct_text(element: ET.Element, names: tuple[str, ...]) -> str:
    child = _direct_child(element, names)
    return (child.text or "").strip() if child is not None else ""


def _nested_text(element: ET.Element | None, names: tuple[str, ...]) -> str:
    if element is None:
        return ""
    value = _direct_text(element, names)
    if value:
        return value
    for child in element.iter():
        if _local_name(child.tag) in names and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def parse_tracking_response(xml: str | bytes) -> dict[str, Any]:
    """Parsuje odpowiedź SOAP do niezależnej od Qt struktury.

    W szczególności pomija kontener ``zdarzenia/events``. Wcześniejsze
    parsowanie traktowało kontener jak zdarzenie i nadpisywało pola wszystkich
    jego dzieci, przez co aplikacja mogła pokazać stary status „Nadano” zamiast
    nowszego „W transporcie”.
    """
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, TypeError, ValueError) as error:
        return {"events": [], "message": f"Nieprawidłowa odpowiedź usługi: {error}"}

    events: list[dict[str, str]] = []
    for element in root.iter():
        # Tylko pojedyncze zdarzenie, nigdy lista zdarzeń.
        if _local_name(element.tag) not in {"zdarzenie", "event"}:
            continue
        if any(_local_name(child.tag) in {"zdarzenie", "event"} for child in list(element)):
            continue

        unit = _direct_child(element, ("jednostka", "unit", "placowka", "placówka"))
        cause = _direct_child(element, ("przyczyna", "cause"))
        event = {
            "time": _direct_text(
                element,
                ("czas", "time", "dataiczas", "data_i_czas", "data"),
            ),
            "name": _direct_text(
                element,
                ("nazwa", "name", "nazwa_zdarzenia", "status", "rodzaj"),
            ),
            "code": _direct_text(element, ("kod", "code")),
            "unit": _nested_text(unit, ("nazwa", "name"))
            or _direct_text(element, ("nazwa_jednostki", "unit_name")),
            "cause": _nested_text(cause, ("nazwa", "name", "opis", "description")),
            "terminated": _direct_text(
                element,
                ("koniecobslugi", "zakonczenieobslugi", "terminated", "terminace"),
            ),
        }
        if any(event.values()):
            events.append(event)

    message = ""
    for element in root.iter():
        if _local_name(element.tag) not in {
            "faultstring",
            "opis",
            "komunikat",
            "message",
            "description",
        }:
            continue
        value = (element.text or "").strip()
        if value:
            message = re.sub(r"\s+", " ", value)
            break

    return {"events": events, "message": message}


def _parsed_event_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    # fromisoformat obsługuje również ewentualny offset strefy czasowej.
    # Normalizujemy offset do UTC i zdejmujemy strefę tylko po to, aby nie
    # mieszać obiektów aware i naive podczas porównywania zdarzeń.
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def latest_tracking_event(events: Iterable[Mapping[str, Any]]) -> dict[str, str] | None:
    """Zwraca najnowsze zdarzenie według daty, zachowując kolejność przy remisie."""
    best_event: dict[str, str] | None = None
    best_key: tuple[int, datetime, int] | None = None
    for index, source_event in enumerate(events):
        event = {str(key): str(value or "") for key, value in source_event.items()}
        parsed_time = _parsed_event_time(event.get("time"))
        key = (
            1 if parsed_time is not None else 0,
            parsed_time or datetime.min,
            index,
        )
        if best_key is None or key > best_key:
            best_event = event
            best_key = key
    return best_event


def format_tracking_event(event: Mapping[str, Any] | None) -> str:
    """Tworzy czytelny opis bez zmieniania treści statusu od operatora."""
    if not event:
        return "Nie pobrano"

    name = str(event.get("name") or event.get("status") or "").strip()
    if not name:
        name = "Zdarzenie bez nazwy"
    parts = [name]

    time = str(event.get("time") or "").strip()
    if time:
        parts.append(f"Data i czas: {time}")
    unit = str(event.get("unit") or "").strip()
    if unit:
        parts.append(f"Placówka: {unit}")
    cause = str(event.get("cause") or "").strip()
    if cause:
        parts.append(f"Przyczyna: {cause}")
    code = str(event.get("code") or "").strip()
    if code:
        parts.append(f"Kod zdarzenia: {code}")
    return " | ".join(parts)[:500]


def sort_tracking_events(
    events: Iterable[Mapping[str, Any]], *, newest_first: bool = False
) -> list[dict[str, str]]:
    """Porządkuje zdarzenia chronologicznie.

    Domyślnie od najwcześniejszego do najnowszego — tak, jak przesyłka
    faktycznie wędrowała: nadanie, transport, doręczenie. Zdarzenia bez
    czytelnej daty trafiają na koniec listy w oryginalnej kolejności, aby nic
    z odpowiedzi Poczty Polskiej nie zniknęło.
    """

    indexed = [
        (index, {str(key): str(value or "") for key, value in event.items()})
        for index, event in enumerate(events)
        if isinstance(event, Mapping)
    ]
    indexed.sort(
        key=lambda item: (
            _parsed_event_time(item[1].get("time")) is None,
            _parsed_event_time(item[1].get("time")) or datetime.max,
            item[0],
        )
    )
    ordered = [event for _index, event in indexed]
    if newest_first:
        ordered.reverse()
    return ordered


def format_tracking_history(
    events: Iterable[Mapping[str, Any]], *, newest_first: bool = False
) -> str:
    """Zwraca pełną historię zdarzeń, domyślnie od najwcześniejszego.

    Kolejność odpowiada rzeczywistej drodze przesyłki, dzięki czemu pierwsza
    linia to nadanie, a ostatnia — najnowszy status.
    """

    ordered = sort_tracking_events(events, newest_first=newest_first)
    return "\n".join(format_tracking_event(event) for event in ordered)


def format_tracking_history_lines(
    events: Iterable[Mapping[str, Any]], *, newest_first: bool = False
) -> list[dict[str, str]]:
    """Buduje gotowe wiersze pełnej historii dla widoku Qt.

    Każdy wiersz zawiera numer kroku, oryginalną nazwę zdarzenia, datę,
    placówkę, przyczynę, kod, a także kategorię, kolor i ikonę, aby historia
    była kolorowa i czytelna zamiast jednolicie szarej.
    """

    ordered = sort_tracking_events(events, newest_first=newest_first)
    total = len(ordered)
    rows: list[dict[str, str]] = []
    for position, event in enumerate(ordered):
        category = tracking_status_category(event)
        step = total - position if newest_first else position + 1
        rows.append(
            {
                "step": str(step),
                "time": str(event.get("time") or ""),
                "name": str(event.get("name") or event.get("status") or "Zdarzenie bez nazwy"),
                "unit": str(event.get("unit") or ""),
                "cause": str(event.get("cause") or ""),
                "code": str(event.get("code") or ""),
                "category": category,
                "color": tracking_status_color(category),
                "icon": tracking_status_icon(category),
                "summary": format_tracking_event(event),
            }
        )
    return rows


def _fold_polish(value: object) -> str:
    text = str(value or "").lower().translate(
        str.maketrans({"ł": "l", "đ": "d", "ß": "ss"})
    )
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def tracking_status_category(status_or_event: object) -> str:
    """Przypisuje status do grupy wyłącznie na potrzeby podsumowania UI."""
    if isinstance(status_or_event, Mapping):
        source = status_or_event.get("name") or status_or_event.get("status") or ""
    else:
        source = status_or_event
    text = _fold_polish(source)

    # Poczta Polska po doręczeniu udostępnia skan podpisu odbiorcy. To zdarzenie
    # jest potwierdzeniem odbioru, dlatego nie może trafiać do "Innego statusu".
    if "podpis" in text and any(
        phrase in text for phrase in ("udostepnion", "udostepni", "odbior", "odbioru")
    ):
        return "Doręczona / odebrana"

    if not text or text.strip() == "nie pobrano" or "brak kodu" in text:
        return "Nie pobrano"
    if any(
        phrase in text
        for phrase in (
            "blad pobrania",
            "nie udalo",
            "brak zdarzen",
            "nie ma przesylki",
            "bledny numer",
            "nieprawidlowa odpowiedz",
            "nie pobrano statusu",
        )
    ):
        return "Problem z pobraniem"
    if "nie pobrano" in text:
        return "Nie pobrano"
    if any(phrase in text for phrase in ("zwrot", "niedorecz", "odmow")):
        return "Zwrot / niedoręczona"
    # "Awizowano po próbie doręczenia" nie jest doręczeniem. Podobnie
    # "wydano/przekazano do doręczenia" oznacza dopiero etap u doręczyciela.
    if "awiz" in text:
        return "Awizowana"
    if any(
        phrase in text
        for phrase in (
            "do doreczenia",
            "doreczyciel",
            "w doreczeniu",
            "przekazano do doreczenia",
        )
    ):
        return "W doręczeniu"
    if any(
        phrase in text
        for phrase in (
            "doreczono",
            "doreczona",
            "doreczenie",
            "odebran",
            "wydano odbiorcy",
            "wydano adresatowi",
            "wydano przesylke adresatowi",
            "potwierdzenie odbioru",
        )
    ):
        return "Doręczona / odebrana"
    if any(
        phrase in text
        for phrase in (
            "transporcie",
            "transportu",
            "sortown",
            "przekazano",
            "wyslano",
            "w drodze",
        )
    ):
        return "W transporcie"
    if any(phrase in text for phrase in ("nadano", "nadanie", "przyjeto")):
        return "Nadana"
    return "Inny status"


def summarize_tracking_statuses(
    shipments: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Grupuje przesyłki według ich najnowszego zapisanego statusu."""
    groups: dict[str, list[Mapping[str, Any]]] = {
        category: [] for category in TRACKING_CATEGORY_ORDER
    }
    for shipment in shipments:
        latest_event = shipment.get("tracking_latest_event")
        status_source = (
            latest_event
            if isinstance(latest_event, Mapping)
            else shipment.get("tracking_status", "")
        )
        category = tracking_status_category(status_source)
        groups.setdefault(category, []).append(shipment)
    return {category: entries for category, entries in groups.items() if entries}
