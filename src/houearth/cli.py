from __future__ import annotations

import argparse
from pathlib import Path

from .io import download_tess_lightcurve, save_lightcurve_csv
from .report import write_diagnostic_plot, write_html_report, write_json
from .search import search_periodic_transits, search_single_transits
from .synthetic import make_synthetic_lightcurve


def _run_pipeline(lc, output: Path, min_period: float, max_period: float | None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    periodic = search_periodic_transits(
        lc,
        min_period=min_period,
        max_period=max_period,
    )
    events = search_single_transits(lc)

    save_lightcurve_csv(lc, output / "lightcurve.csv")
    write_json(periodic.to_dict(), output / "periodic_candidate.json")
    write_json([event.to_dict() for event in events], output / "single_events.json")
    write_json(lc.to_dict(), output / "lightcurve_metadata.json")
    write_html_report(lc, periodic, events, output / "report.html")
    plotted = write_diagnostic_plot(lc, periodic, events, output / "diagnostic.png")

    print(f"Target: {lc.target}")
    print(f"Best period: {periodic.period_days:.6f} days")
    print(f"Depth: {periodic.depth:.6f}; SNR: {periodic.snr:.2f}; score: {periodic.score:.2f}")
    print(f"Single-event candidates: {len(events)}")
    print(f"Report: {output / 'report.html'}")
    if not plotted:
        print("Plot skipped (install matplotlib or the tess extra).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="houearth")
    sub = parser.add_subparsers(dest="command", required=True)

    synthetic = sub.add_parser("synthetic", help="run injection-recovery demo")
    synthetic.add_argument("--period", type=float, default=7.25)
    synthetic.add_argument("--duration", type=float, default=0.22)
    synthetic.add_argument("--depth", type=float, default=0.012)
    synthetic.add_argument("--baseline", type=float, default=54.0)
    synthetic.add_argument("--output", type=Path, default=Path("outputs/synthetic-demo"))
    synthetic.add_argument("--min-period", type=float, default=2.0)
    synthetic.add_argument("--max-period", type=float, default=15.0)

    tess = sub.add_parser("tess", help="download and search public TESS data")
    tess.add_argument("target")
    tess.add_argument("--author", default="SPOC")
    tess.add_argument("--sector", type=int, action="append")
    tess.add_argument("--output", type=Path, default=Path("outputs/tess-target"))
    tess.add_argument("--min-period", type=float, default=1.0)
    tess.add_argument("--max-period", type=float, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "synthetic":
        lc = make_synthetic_lightcurve(
            period=args.period,
            duration=args.duration,
            depth=args.depth,
            baseline=args.baseline,
        )
        _run_pipeline(lc, args.output, args.min_period, args.max_period)
        return

    sector = args.sector
    if sector is not None and len(sector) == 1:
        sector = sector[0]
    lc = download_tess_lightcurve(args.target, author=args.author, sector=sector)
    _run_pipeline(lc, args.output, args.min_period, args.max_period)


if __name__ == "__main__":
    main()
