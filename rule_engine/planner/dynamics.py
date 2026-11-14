"""State, actions and the deterministic part of the transition (history shift, soil carbon)."""

import math
from dataclasses import dataclass

from rule_engine.catalog import Crop
from rule_engine.facts import HISTORY_WINDOW
from rule_engine.planner.tables import CarbonInput

T_C_PER_HA_PER_OM_PCT = 0.58 / 100 * 1.3 * 0.30 * 10000  # 58 % C in OM, 1.3 t/m3, top 30 cm
CARBON_FRACTION = 0.45  # of dry matter


@dataclass(frozen=True)
class Action:
    crop: str
    tillage: str
    cover: str  # cover crop grown before this crop

    def label(self) -> str:
        return f"{self.crop}/{self.tillage}/{self.cover}"


@dataclass(frozen=True)
class State:
    t: int  # years already planned
    history: tuple[str, ...]  # last HISTORY_WINDOW crops, oldest first
    young: float | None  # t C/ha, fresh inputs expressed as the stable carbon they will leave
    old: float | None  # t C/ha, stable pool
    prev: int | None = None  # index of the year just experienced; None = not tracked

    @property
    def stable_carbon(self) -> float | None:
        return None if self.old is None else self.young + self.old


def shift(history: tuple[str, ...], crop: str) -> tuple[str, ...]:
    return (history + (crop,))[-HISTORY_WINDOW:]


@dataclass(frozen=True)
class SoilCarbon:
    """Two-pool ICBM (Andrén and Kätterer 1997) stepped once a year.

    The young pool is tracked in stable-carbon equivalents (input x humification coefficient), so
    shoot and root inputs with different coefficients share one pool. All parameters are recalled
    literature defaults, not calibrated for the field: treat the result as a direction and an
    order of magnitude, not a prediction.
    """

    k_young: float = 0.8  # 1/yr
    k_old: float = 0.006  # 1/yr
    h_shoot: float = 0.125  # Andrén and Kätterer 1997, crop residues
    h_root: float = 0.35  # Kätterer et al. 2011, root-derived carbon
    climate: float = 1.0  # ICBM r_e; 1.0 is the Uppsala reference site
    cover_stable_c: float = 0.32  # t C/ha/yr, Poeplau and Don 2015 meta-analysis mean
    initial_young: float = 0.3  # t C/ha, about one year of stable-equivalent input
    verified: bool = False

    def initial(self, soil: dict) -> tuple[float | None, float | None]:
        om = soil.get("om_pct")
        if om is None:
            return None, None
        stock = float(om) * T_C_PER_HA_PER_OM_PCT
        return self.initial_young, max(0.0, stock - self.initial_young)

    def stable_input(
        self, crop: Crop, yield_t_ha: float, cover: str, table: dict[str, CarbonInput]
    ) -> float:
        """Stable-equivalent carbon (t C/ha) one season adds, from the harvested yield."""
        row = table.get(crop.group.id)
        added = self.cover_stable_c if cover != "none" else 0.0
        if row is None:
            return added
        harvest_c = yield_t_ha * row.dry_matter * CARBON_FRACTION
        return added + harvest_c * (
            row.shoot_per_harvest_c * self.h_shoot + row.root_per_harvest_c * self.h_root
        )

    def step(self, young: float, old: float, stable_input: float) -> tuple[float, float]:
        keep_young = math.exp(-self.k_young * self.climate)
        pool = young + stable_input
        return pool * keep_young, old * math.exp(-self.k_old * self.climate) + pool * (
            1.0 - keep_young
        )
