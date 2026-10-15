from datetime import date, timedelta
import unittest

from freight_watch.analysis import (
    Note,
    Shipment,
    aggregate_weekly_costs,
    analyze,
)


def shipment(
    origin: str,
    destination: str,
    day: date,
    freight_cost: float,
    route_type: str = "Short",
) -> Shipment:
    return Shipment(
        origin=origin,
        destination=destination,
        route_type=route_type,
        quantity_tonnes=1,
        distance_km=1,
        freight_cost_inr=freight_cost,
        shipment_date=day,
    )


class WeeklyAggregationTests(unittest.TestCase):
    def test_groups_by_monday_and_uses_ratio_of_totals(self) -> None:
        records = [
            Shipment("A", "B", "Short", 2, 10, 100, date(2024, 1, 1)),
            Shipment("A", "B", "Short", 1, 10, 100, date(2024, 1, 7)),
            Shipment("A", "B", "Short", 1, 10, 50, date(2024, 1, 8)),
        ]

        weekly = aggregate_weekly_costs(records)

        self.assertEqual([row.week_of for row in weekly], [date(2024, 1, 1), date(2024, 1, 8)])
        self.assertAlmostEqual(weekly[0].cost_per_tonne_km, 200 / 30)
        self.assertAlmostEqual(weekly[1].cost_per_tonne_km, 5)

    def test_own_history_uses_only_the_previous_eight_calendar_weeks(self) -> None:
        start = date(2024, 1, 1)
        records = [shipment("A", "B", start + timedelta(weeks=week), 100) for week in range(10)]
        records.append(shipment("A", "B", start + timedelta(weeks=10), 125))

        rows = analyze(records, [], threshold_pct=20)

        self.assertEqual(rows[-1]["vs_own_history"], "+25.0% vs this route's past average")
        self.assertEqual(rows[-1]["flagged"], "Yes")
        self.assertEqual(rows[-1]["matched_note_id"], "")

    def test_own_history_excludes_observations_older_than_eight_calendar_weeks(self) -> None:
        start = date(2024, 1, 1)
        records = [
            shipment("A", "B", start, 300),
            shipment("A", "B", start + timedelta(weeks=9), 100),
            shipment("A", "B", start + timedelta(weeks=10), 125),
        ]

        rows = analyze(records, [], threshold_pct=20)

        self.assertEqual(rows[-1]["vs_own_history"], "+25.0% vs this route's past average")
        self.assertEqual(rows[-1]["flagged"], "Yes")

    def test_peer_average_excludes_current_route(self) -> None:
        current_week = date(2024, 1, 1)
        records = [
            shipment("A", "B", current_week, 150),
            shipment("C", "D", current_week, 100),
        ]

        rows = analyze(records, [], threshold_pct=20)

        self.assertEqual(rows[0]["vs_similar_routes"], "+50.0% vs similar-length routes this week")
        self.assertEqual(rows[0]["flagged"], "Yes")
        self.assertEqual(rows[1]["vs_similar_routes"], "-33.3% vs similar-length routes this week")
        self.assertEqual(rows[1]["flagged"], "No")

    def test_invalid_threshold_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze([], [], threshold_pct=float("nan"))


class EvidenceMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = date(2024, 1, 1)
        self.records = [
            *[shipment("A", "B", self.start + timedelta(weeks=week), 100) for week in range(8)],
            shipment("A", "B", self.start + timedelta(weeks=8), 125),
        ]

    def test_exact_route_and_active_week_can_justify_flag(self) -> None:
        note = Note("N1", self.start + timedelta(weeks=8), "A-B", "Flood disruption caused higher trip costs.")

        row = analyze(self.records, [note])[-1]

        self.assertEqual(row["flagged"], "No (justified)")
        self.assertEqual(row["matched_note_id"], "N1")

    def test_wrong_route_or_time_does_not_justify_flag(self) -> None:
        wrong_route = Note("N1", self.start + timedelta(weeks=8), "C-D", "Flood disruption caused higher trip costs.")
        old_note = Note("N2", self.start, "A-B", "Flood disruption caused higher trip costs.")

        row = analyze(self.records, [wrong_route, old_note])[-1]

        self.assertEqual(row["flagged"], "Yes")
        self.assertEqual(row["matched_note_id"], "")

    def test_quantified_note_cannot_explain_a_larger_increase(self) -> None:
        note = Note("N3", self.start + timedelta(weeks=8), "All Routes", "Fuel costs rose by 5-7%, pushing up transportation costs.")

        row = analyze(self.records, [note])[-1]

        self.assertEqual(row["flagged"], "Yes")
        self.assertEqual(row["matched_note_id"], "")

    def test_explicit_non_impact_note_is_not_justification(self) -> None:
        note = Note(
            "N4",
            self.start + timedelta(weeks=8),
            "A-B",
            "Highway maintenance caused minor delays; costs were not significantly affected.",
        )

        row = analyze(self.records, [note])[-1]

        self.assertEqual(row["flagged"], "Yes")
        self.assertEqual(row["matched_note_id"], "")


if __name__ == "__main__":
    unittest.main()
