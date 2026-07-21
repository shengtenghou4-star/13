from __future__ import annotations

import html
import json
from pathlib import Path

from .core import LightCurve, PeriodicCandidate, SingleTransitEvent


def write_json(data: object, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_html_report(
    lc: LightCurve,
    periodic: PeriodicCandidate,
    events: list[SingleTransitEvent],
    path: str | Path,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        "<tr>"
        f"<td>{event.center_time_days:.5f}</td>"
        f"<td>{event.duration_days:.3f}</td>"
        f"<td>{event.depth:.5f}</td>"
        f"<td>{event.snr:.2f}</td>"
        "</tr>"
        for event in events[:10]
    ) or '<tr><td colspan="4">No event passed the threshold.</td></tr>'

    target = html.escape(lc.target)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HOU-EARTH report — {target}</title>
<style>
body {{ max-width: 940px; margin: 40px auto; padding: 0 20px; font-family: Inter, system-ui, sans-serif; line-height: 1.55; background: #07111f; color: #eaf2ff; }}
.card {{ background: #101e33; border: 1px solid #27415f; border-radius: 16px; padding: 22px; margin: 18px 0; }}
h1, h2 {{ color: #ffffff; }}
.metric {{ display: inline-block; min-width: 150px; margin: 8px 20px 8px 0; }}
.metric b {{ display: block; font-size: 1.35rem; color: #8fd3ff; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ border-bottom: 1px solid #27415f; padding: 9px; text-align: left; }}
.warning {{ color: #ffd17d; }}
code {{ color: #a6e3a1; }}
</style>
</head>
<body>
<h1>HOU-EARTH / 侯星计划</h1>
<p>Calibrated transit-search report for <strong>{target}</strong>.</p>
<div class="card">
<h2>Periodic signal</h2>
<div class="metric"><span>Period</span><b>{periodic.period_days:.6f} d</b></div>
<div class="metric"><span>Duration</span><b>{periodic.duration_days:.4f} d</b></div>
<div class="metric"><span>Depth</span><b>{periodic.depth:.5f}</b></div>
<div class="metric"><span>SNR</span><b>{periodic.snr:.2f}</b></div>
<div class="metric"><span>Transparent score</span><b>{periodic.score:.2f}</b></div>
<p>Estimated observed transits: {periodic.estimated_transits}. Odd/even ratio: {periodic.odd_even_depth_ratio}. Secondary SNR: {periodic.secondary_snr:.2f}.</p>
</div>
<div class="card">
<h2>Isolated-event search</h2>
<table><thead><tr><th>Center (day)</th><th>Duration (day)</th><th>Depth</th><th>SNR</th></tr></thead><tbody>{rows}</tbody></table>
</div>
<div class="card warning">
<strong>Scientific status:</strong> an automated dip is not a planet. Pixel-level vetting, catalog cross-matches, independent review, and follow-up are required before any discovery claim.
</div>
</body>
</html>"""
    path.write_text(page, encoding="utf-8")


def write_diagnostic_plot(
    lc: LightCurve,
    periodic: PeriodicCandidate,
    events: list[SingleTransitEvent],
    path: str | Path,
) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - optional dependency
        return False

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.scatter(lc.time, lc.flux, s=2, alpha=0.55)
    for event in events[:8]:
        ax.axvline(event.center_time_days, alpha=0.35)
    ax.set_title(f"HOU-EARTH diagnostic — {lc.target} | P={periodic.period_days:.4f} d")
    ax.set_xlabel("Time [days]")
    ax.set_ylabel("Normalized flux")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return True
