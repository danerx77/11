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


def format_tracking_history(events: Iterable[Mapping[str, Any]]) -> str:
    """Zwraca pełną, chronologiczną historię zdarzeń do podpowiedzi w tabeli."""
    indexed_events = list(enumerate(events))
    indexed_events.sort(
        key=lambda item: (
            _parsed_event_time(item[1].get("time")) is not None,
            _parsed_event_time(item[1].get("time")) or datetime.min,
            item[0],
        ),
        reverse=True,
    )
    return "\n".join(format_tracking_event(event) for _index, event in indexed_events)


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
        for phrase in ("doreczono", "doreczona", "doreczenie", "odebran", "wydano odbiorcy")
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
