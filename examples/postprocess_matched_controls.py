from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from houearth.control_significance import (
    annotate_trial_rows,
    summarize_annotated_rows,
)


def read_csv(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path("outputs/real-ppm-batch"),
    )
    args = parser.parse_args()
    root: Path = args.root

    target_dirs = sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and (path / "trials.csv").exists()
        and (path / "brightening_control_events.json").exists()
    )
    all_rows: list[dict[str, object]] = []
    for target_dir in target_dirs:
        trials = read_csv(target_dir / "trials.csv")
        controls = json.loads(
            (target_dir / "brightening_control_events.json").read_text(encoding="utf-8")
        )
        annotated = annotate_trial_rows(trials, controls)
        for row in annotated:
            row["target_id"] = target_dir.name
        write_csv(target_dir / "trials_matched_controls.csv", annotated)
        all_rows.extend(annotated)

    pooled = summarize_annotated_rows(all_rows, pool_targets=True)
    per_target = summarize_annotated_rows(all_rows, pool_targets=False)
    write_csv(root / "pooled_matched_control_completeness.csv", pooled)
    write_csv(root / "target_matched_control_completeness.csv", per_target)
    (root / "matched_control_summary.json").write_text(
        json.dumps(
            {
                "method": "duration-matched brightening controls with add-one empirical upper-tail probability",
                "targets": [path.name for path in target_dirs],
                "annotated_trials": len(all_rows),
                "pooled_cells": pooled,
                "target_cells": per_target,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(pooled, indent=2))


if __name__ == "__main__":
    main()
