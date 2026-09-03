"""Testy dokładnego odczytu statusów Poczty Polskiej bez połączenia sieciowego."""

import unittest

from utils.shipment_tracking import (
    DEFAULT_TRACKING_COLOR,
    TRACKING_STATUS_COLORS,
    format_tracking_event,
    format_tracking_history,
    format_tracking_history_lines,
    latest_tracking_event,
    normalize_tracking_code,
    parse_tracking_response,
    sort_tracking_events,
    summarize_tracking_statuses,
    tracking_status_category,
    tracking_status_color,
)


SOAP_RESPONSE = """<?xml version='1.0' encoding='UTF-8'?>
<soapenv:Envelope xmlns:soapenv='http://schemas.xmlsoap.org/soap/envelope/'
                  xmlns:tt='http://sledzenie.pocztapolska.pl'>
  <soapenv:Body>
    <tt:sprawdzPrzesylkePlResponse>
      <return>
        <przesylka>
          <danePrzesylki>
            <zdarzenia>
              <zdarzenie>
                <czas>2026-08-28 08:15</czas>
                <kod>NAD</kod>
                <nazwa>Nadano przesyłkę</nazwa>
                <jednostka><nazwa>UP Gdańsk 1</nazwa></jednostka>
              </zdarzenie>
              <zdarzenie>
                <czas>2026-08-29 11:45</czas>
                <kod>TR</kod>
                <nazwa>W transporcie</nazwa>
                <jednostka><nazwa>Sortownia Gdańsk</nazwa></jednostka>
              </zdarzenie>
            </zdarzenia>
          </danePrzesylki>
        </przesylka>
      </return>
    </tt:sprawdzPrzesylkePlResponse>
  </soapenv:Body>
</soapenv:Envelope>"""


class ShipmentTrackingTests(unittest.TestCase):
    def test_normalizes_barcode_for_official_tracking_service(self):
        self.assertEqual(
            normalize_tracking_code("(00) 1590-0773 3123 4567 8"),
            "0015900773312345678",
        )

    def test_parser_ignores_events_container_and_keeps_every_real_event(self):
        # Aplikacja przekazuje surowe bajty odebrane z usługi SOAP.
        result = parse_tracking_response(SOAP_RESPONSE.encode("utf-8"))

        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(result["events"][0]["name"], "Nadano przesyłkę")
        self.assertEqual(result["events"][1]["unit"], "Sortownia Gdańsk")

    def test_latest_event_uses_event_time_not_first_or_parent_container(self):
        result = parse_tracking_response(SOAP_RESPONSE)
        latest = latest_tracking_event(result["events"])

        self.assertIsNotNone(latest)
        self.assertEqual(latest["name"], "W transporcie")
        self.assertEqual(latest["time"], "2026-08-29 11:45")
        self.assertEqual(tracking_status_category(latest), "W transporcie")

    def test_latest_event_supports_iso_timestamp_with_timezone(self):
        latest = latest_tracking_event(
            [
                {"name": "Nadano", "time": "2026-08-29T10:30:00+02:00"},
                {"name": "W transporcie", "time": "2026-08-29T09:00:00Z"},
            ]
        )

        self.assertEqual(latest["name"], "W transporcie")

    def test_latest_status_keeps_raw_status_and_adds_time_and_postal_unit(self):
        latest = latest_tracking_event(parse_tracking_response(SOAP_RESPONSE)["events"])
        formatted = format_tracking_event(latest)

        self.assertTrue(formatted.startswith("W transporcie"))
        self.assertIn("Data i czas: 2026-08-29 11:45", formatted)
        self.assertIn("Placówka: Sortownia Gdańsk", formatted)

    def test_operational_categories_do_not_treat_awizo_or_dispatch_to_courier_as_delivery(self):
        self.assertEqual(
            tracking_status_category("Awizowano przesyłkę po próbie doręczenia"),
            "Awizowana",
        )
        self.assertEqual(
            tracking_status_category("Wysłano przesyłkę do doręczenia"),
            "W doręczeniu",
        )
        self.assertEqual(
            tracking_status_category("Doręczono przesyłkę"),
            "Doręczona / odebrana",
        )
        self.assertEqual(
            tracking_status_category("Nie pobrano statusu: błąd pobrania"),
            "Problem z pobraniem",
        )

    def test_summary_groups_envelopes_by_current_status(self):
        latest = latest_tracking_event(parse_tracking_response(SOAP_RESPONSE)["events"])
        shipments = [
            {"addressee": "Jan Kowalski", "tracking_latest_event": latest},
            {"addressee": "Anna Nowak", "tracking_status": "Nadano przesyłkę"},
            {"addressee": "Piotr Zieliński", "tracking_status": "Nie pobrano"},
        ]

        groups = summarize_tracking_statuses(shipments)
        self.assertEqual([s["addressee"] for s in groups["W transporcie"]], ["Jan Kowalski"])
        self.assertEqual([s["addressee"] for s in groups["Nadana"]], ["Anna Nowak"])
        self.assertEqual([s["addressee"] for s in groups["Nie pobrano"]], ["Piotr Zieliński"])


    def test_signature_release_event_counts_as_delivered(self):
        # Poczta Polska po doręczeniu udostępnia podpis odbiorcy.
        for status in (
            "Udostępniono podpis odbioru",
            "Udostępnienie podpisu odbioru przesyłki",
            "udostepniono podpis odbiory",
        ):
            self.assertEqual(
                tracking_status_category(status),
                "Doręczona / odebrana",
                msg=status,
            )

    def test_delivery_confirmation_wordings_are_also_delivered(self):
        for status in (
            "Wydano przesyłkę adresatowi",
            "Potwierdzenie odbioru",
            "Doręczono przesyłkę",
        ):
            self.assertEqual(
                tracking_status_category(status),
                "Doręczona / odebrana",
                msg=status,
            )


class TrackingHistoryOrderTests(unittest.TestCase):
    EVENTS = [
        {"name": "W transporcie", "time": "2026-08-29 11:45"},
        {"name": "Nadano przesyłkę", "time": "2026-08-28 08:15"},
        {"name": "Doręczono przesyłkę", "time": "2026-08-30 09:05"},
    ]

    def test_history_is_ordered_from_the_earliest_to_the_newest_event(self):
        ordered = sort_tracking_events(self.EVENTS)
        self.assertEqual(
            [event["name"] for event in ordered],
            ["Nadano przesyłkę", "W transporcie", "Doręczono przesyłkę"],
        )

    def test_history_text_starts_with_the_first_event(self):
        lines = format_tracking_history(self.EVENTS).splitlines()
        self.assertTrue(lines[0].startswith("Nadano przesyłkę"))
        self.assertTrue(lines[-1].startswith("Doręczono przesyłkę"))

    def test_newest_first_is_still_available_for_compact_views(self):
        ordered = sort_tracking_events(self.EVENTS, newest_first=True)
        self.assertEqual(ordered[0]["name"], "Doręczono przesyłkę")

    def test_events_without_a_date_are_kept_at_the_end(self):
        ordered = sort_tracking_events(
            [{"name": "Bez daty"}, {"name": "Nadano", "time": "2026-08-28 08:15"}]
        )
        self.assertEqual([event["name"] for event in ordered], ["Nadano", "Bez daty"])

    def test_history_rows_expose_step_number_category_and_colour(self):
        rows = format_tracking_history_lines(self.EVENTS)
        self.assertEqual([row["step"] for row in rows], ["1", "2", "3"])
        self.assertEqual(rows[0]["name"], "Nadano przesyłkę")
        self.assertEqual(rows[-1]["category"], "Doręczona / odebrana")
        self.assertEqual(
            rows[-1]["color"], TRACKING_STATUS_COLORS["Doręczona / odebrana"]
        )
        self.assertTrue(rows[-1]["icon"])

    def test_every_category_has_its_own_readable_colour(self):
        self.assertEqual(
            tracking_status_color("Doręczono przesyłkę"),
            TRACKING_STATUS_COLORS["Doręczona / odebrana"],
        )
        # Status nieznany dostaje kolor zapasowy, nigdy pusty tekst.
        self.assertEqual(
            tracking_status_color("Zupełnie nowy status operatora"),
            DEFAULT_TRACKING_COLOR,
        )

    def test_not_fetched_status_is_no_longer_shown_as_plain_grey_text(self):
        # Kolor jest celowo inny niż kolor zwykłego tekstu tabeli.
        self.assertTrue(tracking_status_color("Nie pobrano").startswith("#"))


if __name__ == "__main__":
    unittest.main()
