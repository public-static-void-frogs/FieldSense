"""Calibrate the repeat-crop yield factors of the rules from measured yields.

Each rule's prior is its yield_factor range, read as midpoint +- 2 sd. The prior is blended with
the measured loss by inverse variance, and the blend is reported as midpoint +- 2 sd, i.e. the
range to write back into the rule.

Measurements:
  corn after corn: the same-field MODIS greenness panel (ndvi_field_panel.py). Its loss is
    scaled up by the attenuation found on soybeans after soybeans, whose real loss is taken from
    Seifert et al. 2017 (satellite-estimated field yields, 10.3 %). MODIS 250 m pixels mix
    neighbouring fields, and greenness saturates.
  rotation benefit: the same-field greenness panel's corn and soybeans after a small grain or
    hay against after the partner crop (small_grain_field_panel.py), scaled the same way.
  soybeans after soybeans: Seifert et al. 2017, blended with the county panel
    (repeat_yield_panel.py). The greenness panel cannot be used here: it was scaled on this
    very number.
The county panel's corn rows are left out. A corn-after-corn share also "raises" soybean yield
(its placebo), so the county design confounds corn intensity with land quality.

    python rule_engine/planner/scripts/calibrate_yield_factors.py \
        --ndvi-panel ndvi_panel.json --county-panel panel.json --small-grain-panel small_grain.json
"""

import argparse
import json
import math
from pathlib import Path

SEIFERT_SOY_LOSS = 10.3  # %, Seifert et al. 2017, soybeans after soybeans
SEIFERT_SD = 1.0  # %, assumed: the paper's field count makes the sampling error small
PRIORS = {  # rule id: yield_factor range in the rule file before calibration
    "continuous_corn_yield_penalty": (0.85, 0.96),
    "rotation_yield_benefit": (1.00, 1.09),
}


def blend(estimates: list[tuple[float, float]]) -> tuple[float, float]:
    """Inverse-variance mean and sd of (value, sd) pairs."""
    weights = [1 / sd**2 for _, sd in estimates]
    mean = sum(w * v for w, (v, _) in zip(weights, estimates)) / sum(weights)
    return mean, math.sqrt(1 / sum(weights))


def prior(low: float, high: float) -> tuple[float, float]:
    """Loss in % from a yield_factor range: midpoint, a quarter of the width as sd."""
    return 100 * (1 - (low + high) / 2), 100 * (high - low) / 4


def scaled(change: float, sd: float, scale: float, scale_rel_sd: float) -> tuple[float, float]:
    """A greenness-implied change times the attenuation scale, with both errors."""
    value = change * scale
    return value, abs(value) * math.sqrt((sd / change) ** 2 + scale_rel_sd**2)


def as_range(loss: float, sd: float) -> list[float]:
    return [round(1 - (loss + 2 * sd) / 100, 2), round(1 - (loss - 2 * sd) / 100, 2)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ndvi-panel", required=True, type=Path)
    parser.add_argument("--county-panel", required=True, type=Path)
    parser.add_argument("--small-grain-panel", required=True, type=Path)
    parser.add_argument("--subset", default="all", choices=("all", "40ac+"))
    args = parser.parse_args()
    ndvi = json.loads(args.ndvi_panel.read_text())
    county = json.loads(args.county_panel.read_text())

    def greenness(crop: str) -> tuple[float, float]:
        row = ndvi[crop][f"{args.subset}/{ndvi[crop]['best_proxy']}"]
        return -row["yield_change_pct"], row["yield_change_se"]

    soy_green, soy_green_sd = greenness("soybeans")
    corn_green, corn_green_sd = greenness("corn")
    scale = SEIFERT_SOY_LOSS / soy_green
    scale_rel_sd = math.hypot(soy_green_sd / soy_green, SEIFERT_SD / SEIFERT_SOY_LOSS)
    corn_measured = scaled(corn_green, corn_green_sd, scale, scale_rel_sd)
    corn = blend([prior(*PRIORS["continuous_corn_yield_penalty"]), corn_measured])

    # rotation benefit: a gain, so the prior's "loss" is negated
    small_grain = json.loads(args.small_grain_panel.read_text())
    gains = {
        crop: scaled(
            small_grain[crop][args.subset]["after_small_grain"]["yield_change_pct"],
            small_grain[crop][args.subset]["after_small_grain"]["se"],
            scale,
            scale_rel_sd,
        )
        for crop in ("corn", "soybeans")
    }
    loss, sd = prior(*PRIORS["rotation_yield_benefit"])
    gain = blend([(-loss, sd), *gains.values()])

    panel = county["soy_yield"]["soy_after_soy_share"]
    soy_county = (-100 * panel["coef"], 100 * panel["se"])
    soy = blend([(SEIFERT_SOY_LOSS, SEIFERT_SD), soy_county])

    out = {
        "attenuation": round(scale, 2),
        "continuous_corn_yield_penalty": {
            "prior_loss_pct": [
                round(v, 2) for v in prior(*PRIORS["continuous_corn_yield_penalty"])
            ],
            "measured_loss_pct": [round(v, 2) for v in corn_measured],
            "calibrated_loss_pct": [round(v, 2) for v in corn],
            "yield_factor": as_range(*corn),
        },
        "rotation_yield_benefit": {
            "prior_gain_pct": [round(-loss, 2), round(sd, 2)],
            **{f"{c}_measured_gain_pct": [round(v, 2) for v in g] for c, g in gains.items()},
            "calibrated_gain_pct": [round(v, 2) for v in gain],
            "yield_factor": as_range(-gain[0], gain[1]),
        },
        "soy_after_soy_yield_penalty": {
            "seifert_loss_pct": [SEIFERT_SOY_LOSS, SEIFERT_SD],
            "county_panel_loss_pct": [round(v, 2) for v in soy_county],
            "calibrated_loss_pct": [round(v, 2) for v in soy],
            "yield_factor": as_range(*soy),
        },
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
