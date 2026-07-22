from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .benchmarks import BENCHMARKS, run_known_planet_benchmark
from .evaluation import run_single_transit_campaign, write_campaign_outputs
from .io import download_tess_lightcurve, save_lightcurve_csv
from .real_evaluation import run_real_lightcurve_campaign, write_real_campaign_outputs
from .report import write_diagnostic_plot, write_html_report, write_json
from .search import search_periodic_transits, search_single_transits
from .synthetic import make_synthetic_lightcurve


def _run_pipeline(
    lc,
    output: Path,
    min_period: float,
    max_period: float | None,
    period_steps: int,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    periodic = search_periodic_transits(
        lc,
        min_period=min_period,
        max_period=max_period,
        period_steps=period_steps,
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


def _parse_float_list(value: str) -> tuple[float, ...]:
    parsed = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not parsed:
        raise argparse.ArgumentTypeError("provide at least one comma-separated number")
    return parsed


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "target"


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
    synthetic.add_argument("--period-steps", type=int, default=700)

    tess = sub.add_parser("tess", help="download and search public TESS data")
    tess.add_argument("target")
    tess.add_argument("--author", default="SPOC")
    tess.add_argument("--sector", type=int, action="append")
    tess.add_argument("--max-products", type=int)
    tess.add_argument("--output", type=Path, default=Path("outputs/tess-target"))
    tess.add_argument("--min-period", type=float, default=1.0)
    tess.add_argument("--max-period", type=float, default=None)
    tess.add_argument("--period-steps", type=int, default=700)

    benchmark = sub.add_parser("benchmark", help="recover a versioned known TESS planet")
    benchmark.add_argument("key", choices=sorted(BENCHMARKS))
    benchmark.add_argument("--output", type=Path)
    benchmark.add_argument("--author", default="SPOC")

    calibrate = sub.add_parser(
        "calibrate-single",
        help="measure isolated-transit completeness on a synthetic depth-duration grid",
    )
    calibrate.add_argument("--depths", type=_parse_float_list, default=(0.002, 0.004, 0.008, 0.012))
    calibrate.add_argument("--durations", type=_parse_float_list, default=(0.08, 0.16, 0.32))
    calibrate.add_argument("--trials", type=int, default=8)
    calibrate.add_argument("--baseline", type=float, default=27.0)
    calibrate.add_argument("--cadence-minutes", type=float, default=30.0)
    calibrate.add_argument("--noise", type=float, default=0.0018)
    calibrate.add_argument("--min-snr", type=float, default=5.0)
    calibrate.add_argument(
        "--output", type=Path, default=Path("outputs/single-transit-completeness")
    )

    real = sub.add_parser(
        "calibrate-real",
        help="inject isolated events into an observed TESS light curve",
    )
    real.add_argument("target")
    real.add_argument("--author", default="SPOC")
    real.add_argument("--sector", type=int, action="append")
    real.add_argument("--max-products", type=int, default=1)
    real.add_argument("--depths", type=_parse_float_list, default=(0.004, 0.008))
    real.add_argument("--durations", type=_parse_float_list, default=(0.08, 0.16))
    real.add_argument("--trials", type=int, default=4)
    real.add_argument("--min-snr", type=float, default=5.0)
    real.add_argument("--flatten-window", type=float, default=1.5)
    real.add_argument("--output", type=Path)
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
        _run_pipeline(
            lc,
            args.output,
            args.min_period,
            args.max_period,
            args.period_steps,
        )
        return

    if args.command == "benchmark":
        output = args.output or Path("outputs/benchmarks") / args.key
        result = run_known_planet_benchmark(
            args.key,
            output_dir=output,
            author=args.author,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "calibrate-single":
        if args.trials < 1:
            raise SystemExit("--trials must be positive")
        trials, cells = run_single_transit_campaign(
            depths=args.depths,
            durations_days=args.durations,
            seeds=range(args.trials),
            baseline_days=args.baseline,
            cadence_minutes=args.cadence_minutes,
            noise=args.noise,
            min_snr=args.min_snr,
        )
        write_campaign_outputs(trials, cells, args.output)
        print(json.dumps([cell.to_dict() for cell in cells], indent=2))
        return

    if args.command == "calibrate-real":
        if args.trials < 1:
            raise SystemExit("--trials must be positive")
        sector = args.sector
        if sector is not None and len(sector) == 1:
            sector = sector[0]
        lc = download_tess_lightcurve(
            args.target,
            author=args.author,
            sector=sector,
            max_products=args.max_products,
        )
        null_screen, background, brightening_controls, trials, cells = (
            run_real_lightcurve_campaign(
                lc,
                depths=args.depths,
                durations_days=args.durations,
                seeds=range(args.trials),
                min_snr=args.min_snr,
                flatten_window_days=args.flatten_window,
            )
        )
        output = args.output or Path("outputs/real-calibration") / _slug(args.target)
        write_real_campaign_outputs(
            lc,
            null_screen,
            background,
            brightening_controls,
            trials,
            cells,
            output,
        )
        print(json.dumps([cell.to_dict() for cell in cells], indent=2))
        return

    sector = args.sector
    if sector is not None and len(sector) == 1:
        sector = sector[0]
    lc = download_tess_lightcurve(
        args.target,
        author=args.author,
        sector=sector,
        max_products=args.max_products,
    )
    _run_pipeline(
        lc,
        args.output,
        args.min_period,
        args.max_period,
        args.period_steps,
    )


if __name__ == "__main__":
    main()
