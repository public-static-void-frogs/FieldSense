"""Carry-over between years: which historical year is likely to come next.

With independent draws nothing observed this year says anything about the next one, so the best
plan is a fixed sequence. Two things do carry over and are known before planting:

- drought: the Drought Monitor class at the field at the end of one season against its class at
  the start of the next. Across the national sample (102,570 field-year pairs, 2015-2025) the
  two correlate at 0.45, and a season that starts in drought stays drier (0.50 with midseason).
- price: the marketing-year price level of one year against the level of the year before the
  candidate year.

The next year is drawn from the historical years, weighted by how closely each year's starting
conditions resemble the conditions the plan has just reached (a nearest-neighbour bootstrap, the
resampling scheme of Lall and Sharma 1996 for hydrologic series, recalled, not re-read):

    weight(i -> j) = exp(-1/2 * sum_k ((end_i[k] - start_j[k]) / (bandwidth * sd_k))^2)
    P(i -> j)      = (1 - strength) / n + strength * weight / sum(weight)

`strength` 0 gives independent years again. With about ten years the conditional odds rest on a
handful of analog years: they show direction, not calibrated probabilities.
"""

import math
from dataclasses import dataclass
from statistics import mean, pstdev

EDGE_WEEKS = 4  # weeks at each end of the summarised season (April; late October)
MIN_YEARS = 5
SIGNALS = ("drought", "price")


@dataclass(frozen=True)
class Persistence:
    strength: float = 1.0  # 0 = independent years, 1 = analog weights only
    bandwidth: float = 1.0  # kernel width in standard deviations of each signal


def _edge(series, part: slice) -> float | None:
    if not series:
        return None
    values = [v for v in series[part] if v is not None and not math.isnan(v)]
    return mean(values) if values else None


def year_signals(years, seasons, basis) -> tuple[dict, dict]:
    """({year: start signals}, {year: end signals}) for the drawable years."""
    priced = [c for c, b in basis.items() if b.price_years > 0]
    level = {
        y.year: mean(y.crops[c].price / basis[c].price for c in priced) if priced else None
        for y in years
    }
    start, end = {}, {}
    for y in years:
        season = seasons.get(y.year)
        drought = season.weekly.get("dm_max") if season is not None else None
        start[y.year] = {
            "drought": _edge(drought, slice(0, EDGE_WEEKS)),
            "price": level.get(y.year - 1),
        }
        end[y.year] = {
            "drought": _edge(drought, slice(-EDGE_WEEKS, None)),
            "price": level[y.year],
        }
    return start, end


class YearChain:
    """Transition odds between the drawable years; `latest` is the year the plan starts after."""

    def __init__(self, labels: list[int], start: dict, end: dict, persistence: Persistence):
        self.labels, self.start, self.end = labels, start, end
        self.persistence = persistence
        n = len(labels)
        self.latest = n - 1
        scale = {}
        for k in SIGNALS:
            values = [s[y][k] for s in (start, end) for y in labels if s[y][k] is not None]
            spread = pstdev(values) if len(values) > 1 else 0.0
            if spread > 1e-9:
                scale[k] = spread * persistence.bandwidth
        self.signals = tuple(scale)
        self.matrix: list[list[float]] = []
        for i in labels:
            distance = [0.0] * n
            for k, width in scale.items():
                here = end[i][k]
                if here is None:
                    continue
                parts = [
                    None if start[j][k] is None else ((here - start[j][k]) / width) ** 2
                    for j in labels
                ]
                known = [p for p in parts if p is not None]
                neutral = mean(known) if known else 0.0  # an unknown start is neither near nor far
                distance = [d + (neutral if p is None else p) for d, p in zip(distance, parts)]
            weights = [math.exp(-0.5 * d) for d in distance]
            total = sum(weights)
            s = persistence.strength
            self.matrix.append([(1.0 - s) / n + s * w / total for w in weights])
        self._marginal = [self.matrix[self.latest]]

    def marginal(self, t: int) -> list[float]:
        """Odds of each year at plan step t, seen from the start of the plan."""
        while len(self._marginal) <= t:
            last = self._marginal[-1]
            n = len(last)
            self._marginal.append(
                [sum(last[i] * self.matrix[i][j] for i in range(n)) for j in range(n)]
            )
        return self._marginal[t]

    def describe(self) -> dict:
        first = self.matrix[self.latest]
        return {
            "strength": self.persistence.strength,
            "bandwidthSd": self.persistence.bandwidth,
            "signals": list(self.signals),
            "planStartsAfter": self.labels[self.latest],
            "firstYearOdds": {str(y): round(p, 3) for y, p in zip(self.labels, first)},
            "effectiveAnalogYears": round(1.0 / sum(p * p for p in first), 1),
            "endOfYear": {
                str(y): {k: _rounded(self.end[y][k]) for k in self.signals} for y in self.labels
            },
        }


def _rounded(value):
    return None if value is None else round(value, 2)


def build_chain(years, seasons, basis, persistence: Persistence) -> YearChain | None:
    if persistence.strength <= 0 or len(years) < MIN_YEARS:
        return None
    start, end = year_signals(years, seasons, basis)
    chain = YearChain([y.year for y in years], start, end, persistence)
    return chain if chain.signals else None
