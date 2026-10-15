from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

OUTPUT_COLUMNS = (
    "route",
    "week_of",
    "cost_per_tonne_km",
    "vs_own_history",
    "vs_similar_routes",
    "flagged",
    "matched_note_id",
    "reason",
)


@dataclass(frozen=True)
class Shipment:
    origin: str
    destination: str
    route_type: str
    quantity_tonnes: float
    distance_km: float
    freight_cost_inr: float
    shipment_date: date


@dataclass(frozen=True)
class Note:
    note_id: str
    note_date: date
    applies_to: str
    text: str


@dataclass(frozen=True)
class WeeklyCost:
    origin: str
    destination: str
    route_type: str
    week_of: date
    cost_per_tonne_km: float

    @property
    def route(self) -> str:
        return f"{self.origin}-{self.destination}"

    @property
    def key(self) -> tuple[str, str, str]:
        return self.origin.casefold(), self.destination.casefold(), self.route_type.casefold()


def read_shipments(path: Path) -> list[Shipment]:
    required = {
        "origin",
        "destination",
        "route_type",
        "quantity_tonnes",
        "distance_km",
        "freight_cost_inr",
        "shipment_date",
    }
    shipments: list[Shipment] = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing shipment columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            try:
                quantity = float(row["quantity_tonnes"])
                distance = float(row["distance_km"])
                freight_cost = float(row["freight_cost_inr"])
                shipment_date = date.fromisoformat(row["shipment_date"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: invalid numeric value or shipment_date") from error
            if (
                not all(math.isfinite(value) for value in (quantity, distance, freight_cost))
                or quantity <= 0
                or distance <= 0
                or freight_cost < 0
            ):
                raise ValueError(f"{path}:{line_number}: quantity and distance must be positive; cost cannot be negative")
            if not row["origin"] or not row["destination"] or not row["route_type"]:
                raise ValueError(f"{path}:{line_number}: origin, destination, and route_type are required")
            shipments.append(
                Shipment(
                    origin=row["origin"].strip(),
                    destination=row["destination"].strip(),
                    route_type=row["route_type"].strip(),
                    quantity_tonnes=quantity,
                    distance_km=distance,
                    freight_cost_inr=freight_cost,
                    shipment_date=shipment_date,
                )
            )
    return shipments


def read_notes(path: Path) -> list[Note]:
    required = {"note_id", "date", "applies_to", "note"}
    notes: list[Note] = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing context-note columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            try:
                note_date = date.fromisoformat(row["date"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: invalid note date") from error
            notes.append(
                Note(
                    note_id=row["note_id"].strip(),
                    note_date=note_date,
                    applies_to=row["applies_to"].strip(),
                    text=" ".join(row["note"].split()),
                )
            )
    return notes


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def aggregate_weekly_costs(shipments: list[Shipment]) -> list[WeeklyCost]:
    totals: dict[tuple[str, str, str, date], list[float]] = defaultdict(lambda: [0.0, 0.0])
    route_names: dict[tuple[str, str, str, date], tuple[str, str, str]] = {}
    for shipment in shipments:
        week = _week_start(shipment.shipment_date)
        key = (
            shipment.origin.casefold(),
            shipment.destination.casefold(),
            shipment.route_type.casefold(),
            week,
        )
        totals[key][0] += shipment.freight_cost_inr
        totals[key][1] += shipment.quantity_tonnes * shipment.distance_km
        route_names[key] = (shipment.origin, shipment.destination, shipment.route_type)

    weekly: list[WeeklyCost] = []
    for key, (freight_total, tonne_km_total) in totals.items():
        origin, destination, route_type = route_names[key]
        weekly.append(
            WeeklyCost(
                origin=origin,
                destination=destination,
                route_type=route_type,
                week_of=key[3],
                cost_per_tonne_km=freight_total / tonne_km_total,
            )
        )
    return sorted(weekly, key=lambda item: (item.week_of, item.route_type.casefold(), item.route.casefold()))


def _note_window(note: Note) -> tuple[date, date]:
    range_match = re.search(
        r"\bfrom\s+([A-Za-z]{3,9}\s+\d{1,2})\s+to\s+([A-Za-z]{3,9}\s+\d{1,2})\b",
        note.text,
        flags=re.IGNORECASE,
    )
    if range_match:
        def parse_month_day(value: str) -> date:
            for month_format in ("%b %d %Y", "%B %d %Y"):
                try:
                    return datetime.strptime(f"{value} {note.note_date.year}", month_format).date()
                except ValueError:
                    continue
            raise ValueError(f"Could not parse date range in note {note.note_id}")

        start = parse_month_day(range_match.group(1))
        end = parse_month_day(range_match.group(2))
        if end < start:
            end = end.replace(year=end.year + 1)
        return start, end

    lower = note.text.casefold()
    if "starting this week" in lower:
        return note.note_date, date.max
    if "week" in lower:
        return note.note_date, note.note_date + timedelta(days=6)
    return note.note_date, note.note_date


def _note_route_matches(note: Note, route: WeeklyCost) -> bool:
    applies_to = re.sub(r"\s+", "", note.applies_to).casefold()
    route_name = re.sub(r"\s+", "", route.route).casefold()
    return applies_to in {"allroutes", "all"} or applies_to == route_name


def _is_explicit_cost_support(note: Note) -> bool:
    text = note.text.casefold()
    if any(phrase in text for phrase in ("costs were not significantly affected", "without a rate change")):
        return False
    return any(
        phrase in text
        for phrase in ("higher trip costs", "surcharge applied", "pushing up transportation costs")
    )


def _supports_anomaly(note: Note, weekly: WeeklyCost, uplift_pct: float) -> bool:
    if not _is_explicit_cost_support(note) or not _note_route_matches(note, weekly):
        return False
    start, end = _note_window(note)
    week_end = weekly.week_of + timedelta(days=6)
    if start > week_end or end < weekly.week_of:
        return False
    impact = re.search(r"\b(\d{1,3})\s*-\s*(\d{1,3})\s*%", note.text)
    if impact and uplift_pct > float(impact.group(2)):
        return False
    return True


def _comparison(current: float, baseline: float | None, description: str) -> tuple[str, float | None]:
    if baseline is None or baseline <= 0:
        return "N/A (insufficient comparison data)", None
    uplift_pct = (current / baseline - 1) * 100
    return f"{uplift_pct:+.1f}% {description}", uplift_pct


def analyze(
    shipments: list[Shipment],
    notes: list[Note],
    threshold_pct: float = 20.0,
) -> list[dict[str, str]]:
    if not math.isfinite(threshold_pct) or threshold_pct < 0:
        raise ValueError("threshold_pct must be a finite, non-negative number")

    weekly = aggregate_weekly_costs(shipments)
    by_week_type: dict[tuple[date, str], list[WeeklyCost]] = defaultdict(list)
    for item in weekly:
        by_week_type[(item.week_of, item.route_type.casefold())].append(item)

    rows: list[dict[str, str]] = []
    history: dict[tuple[str, str, str], list[tuple[date, float]]] = defaultdict(list)
    for item in weekly:
        window_start = item.week_of - timedelta(weeks=8)
        prior_costs = [
            cost
            for week, cost in history[item.key]
            if window_start <= week < item.week_of
        ]
        own_baseline = sum(prior_costs) / len(prior_costs) if prior_costs else None
        peer_costs = [
            peer.cost_per_tonne_km
            for peer in by_week_type[(item.week_of, item.route_type.casefold())]
            if peer.key != item.key
        ]
        peer_baseline = sum(peer_costs) / len(peer_costs) if peer_costs else None
        own_text, own_uplift = _comparison(
            item.cost_per_tonne_km,
            own_baseline,
            "vs this route's past average",
        )
        peer_text, peer_uplift = _comparison(
            item.cost_per_tonne_km,
            peer_baseline,
            "vs similar-length routes this week",
        )
        uplifts = [value for value in (own_uplift, peer_uplift) if value is not None]
        is_anomaly = any(value >= threshold_pct for value in uplifts)
        matched_note = next(
            (
                note
                for note in sorted(
                    notes,
                    key=lambda candidate: (
                        candidate.applies_to.casefold() == "all routes",
                        -candidate.note_date.toordinal(),
                        candidate.note_id,
                    ),
                )
                if is_anomaly and _supports_anomaly(note, item, max(uplifts))
            ),
            None,
        )

        if not is_anomaly:
            flagged = "No"
            note_id = ""
            reason = "No qualifying cost increase was identified."
        elif matched_note:
            flagged = "No (justified)"
            note_id = matched_note.note_id
            reason = f"Matches note {matched_note.note_id} dated {matched_note.note_date.isoformat()}: {matched_note.text}"
        else:
            flagged = "Yes"
            note_id = ""
            reason = "No time- and route-matched note sufficiently explains the increase; flagged for human review."

        rows.append(
            {
                "route": item.route,
                "week_of": item.week_of.isoformat(),
                "cost_per_tonne_km": f"{item.cost_per_tonne_km:.2f}",
                "vs_own_history": own_text,
                "vs_similar_routes": peer_text,
                "flagged": flagged,
                "matched_note_id": note_id,
                "reason": reason,
            }
        )
        history[item.key].append((item.week_of, item.cost_per_tonne_km))
    return rows


def output_csv(rows: list[dict[str, str]], columns: tuple[str, ...] = OUTPUT_COLUMNS) -> str:
    from io import StringIO

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()
