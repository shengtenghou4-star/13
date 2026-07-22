from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .io import download_tess_lightcurve
from .search import search_periodic_transits


@dataclass(frozen=True)
class BenchmarkTarget:
    key: str
    target: str
    planet: str
    expected_period_days: float
    sectors: tuple[int, ...]
    min_period_days: float
    max_period_days: float
    durations_days: tuple[float, ...]
    period_steps: int
    flatten_window_days: float
    max_relative_error: float = 0.02


BENCHMARKS: dict[str, BenchmarkTarget] = {
    "lhs3844b": BenchmarkTarget(
        key="lhs3844b",
        target="LHS 3844",
        planet="LHS 3844 b",
        expected_period_days=0.462929709,
        sectors=(1,),
        min_period_days=0.42,
        max_period_days=0.51,
        durations_days=(0.012, 0.018, 0.025, 0.035),
        period_steps=260,
        flatten_window_days=0.45,
    ),
    "pimenc": BenchmarkTarget(
        key="pimenc",
        target="Pi Mensae",
        planet="pi Mensae c",
        expected_period_days=6.26784,
        sectors=(1,),
        min_period_days=5.7,
        max_period_days=6.8,
        durations_days=(0.08, 0.12, 0.16, 0.20),
        period_steps=320,
        flatten_window_days=1.5,
    ),
    "toi700d": BenchmarkTarget(
        key="toi700d",
        target="TOI 700",
        planet="TOI-700 d",
        expected_period_days=37.42396,
        sectors=(1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13),
        min_period_days=34.0,
        max_period_days=41.0,
        durations_days=(0.10, 0.14, 0.18, 0.22),
        period_steps=420,
        flatten_window_days=2.0,
        max_relative_error=0.03,
    ),
}


def run_known_planet_benchmark(
    key: str,
    *,
    output_dir: str | Path,
    author: str | None = "SPOC",
) -> dict[str, object]:
    try:
        benchmark = BENCHMARKS[key]
    except KeyError as exc:
        available = ", ".join(sorted(BENCHMARKS))
        raise ValueError(f"unknown benchmark {key!r}; available: {available}") from exc

    sector: int | list[int]
    sector = benchmark.sectors[0] if len(benchmark.sectors) == 1 else list(benchmark.sectors)
    lc = download_tess_lightcurve(benchmark.target, author=author, sector=sector)
    candidate = search_periodic_transits(
        lc,
        min_period=benchmark.min_period_days,
        max_period=benchmark.max_period_days,
        durations=benchmark.durations_days,
        period_steps=benchmark.period_steps,
        flatten_window_days=benchmark.flatten_window_days,
    )
    relative_error = abs(candidate.period_days - benchmark.expected_period_days) / benchmark.expected_period_days
    result: dict[str, object] = {
        "benchmark": asdict(benchmark),
        "recovered": candidate.to_dict(),
        "relative_period_error": relative_error,
        "passed": relative_error <= benchmark.max_relative_error,
        "lightcurve": lc.to_dict(),
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["passed"]:
        raise RuntimeError(
            f"{benchmark.planet} benchmark failed: period error {relative_error:.3%}"
        )
    return result
