from __future__ import annotations

from houearth.evaluation import run_single_transit_campaign, write_campaign_outputs

trials, cells = run_single_transit_campaign()
write_campaign_outputs(trials, cells, "outputs/single-transit-completeness")
for cell in cells:
    print(
        f"depth={cell.depth:.4f} duration={cell.duration_days:.3f} "
        f"completeness={cell.completeness:.1%} false_events={cell.mean_false_events:.2f}"
    )
