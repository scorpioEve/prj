from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from freight_watch import __version__
from freight_watch.analysis import OUTPUT_COLUMNS, analyze, output_csv, read_notes, read_shipments


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _inputs(args: argparse.Namespace) -> tuple[list, list, tuple[str, ...]]:
    shipments = read_shipments(args.shipments)
    notes = read_notes(args.notes)
    with args.schema.open(newline="", encoding="utf-8-sig") as source:
        columns = tuple(next(csv.reader(source), ()))
    if columns != OUTPUT_COLUMNS:
        raise ValueError(f"{args.schema}: output columns do not match the required contract")
    return shipments, notes, columns


def _run(args: argparse.Namespace) -> int:
    shipments, notes, columns = _inputs(args)
    rows = analyze(shipments, notes, args.threshold_pct)
    report = output_csv(rows, columns)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8", newline="")

    counts = {
        "shipment_records": len(shipments),
        "route_weeks": len(rows),
        "flagged_unexplained": sum(row["flagged"] == "Yes" for row in rows),
        "cost_increases_justified": sum(row["flagged"] == "No (justified)" for row in rows),
    }
    log = {
        "project_version": __version__,
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_model_cost_usd": 0.0,
        "model": None,
        "note": "All calculations and explanations are deterministic local code; no model was called.",
        "threshold_pct": args.threshold_pct,
        **counts,
    }
    args.cost_log.parent.mkdir(parents=True, exist_ok=True)
    args.cost_log.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(rows)} route-weeks to {args.output}; "
        f"{counts['flagged_unexplained']} unexplained flags, "
        f"{counts['cost_increases_justified']} justified increases."
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    shipments, notes, columns = _inputs(args)
    outputs = [output_csv(analyze(shipments, notes, args.threshold_pct), columns) for _ in range(3)]
    hashes = [hashlib.sha256(value.encode("utf-8")).hexdigest() for value in outputs]
    if len(set(outputs)) != 1:
        raise RuntimeError("Three consecutive runs produced different CSV output.")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "Reproducibility check\n"
        "Runs: 3\n"
        "Result: byte-identical CSV outputs\n"
        f"Route-weeks: {outputs[0].count(chr(10)) - 1}\n"
        f"SHA-256: {hashes[0]}\n"
        f"Threshold: {args.threshold_pct:.1f}%\n"
        "Randomness: none; no LLM calls or external services.\n"
    )
    args.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def _add_input_options(parser: argparse.ArgumentParser) -> None:
    root = _project_root()
    parser.add_argument("--shipments", type=Path, default=root / "data" / "shipment_records.csv")
    parser.add_argument("--notes", type=Path, default=root / "data" / "context_notes.csv")
    parser.add_argument(
        "--schema",
        type=Path,
        default=root / "data" / "sample_output_format_v2.csv",
        help="CSV whose header defines the exact output columns and order",
    )
    parser.add_argument("--threshold-pct", type=float, default=20.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find and explain anomalous freight route costs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Analyze shipments and write the required CSV")
    _add_input_options(run_parser)
    root = _project_root()
    run_parser.add_argument("--output", type=Path, default=root / "output" / "anomaly_report.csv")
    run_parser.add_argument("--cost-log", type=Path, default=root / "reports" / "run_cost_log.json")
    run_parser.set_defaults(handler=_run)

    verify_parser = subparsers.add_parser("verify", help="Check three runs for byte-identical results")
    _add_input_options(verify_parser)
    verify_parser.add_argument("--report", type=Path, default=root / "reports" / "reproducibility.txt")
    verify_parser.set_defaults(handler=_verify)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"freight-watch: {error}", file=sys.stderr)
        return 2
