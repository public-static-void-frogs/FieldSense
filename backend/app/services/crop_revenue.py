"""Expected gross revenue (and optional ROI) of a crop plan, from USDA NASS yields and prices.

Yield: the county survey series of the last 15 years (state series when the county has fewer than
6 years). With 6+ years a straight-line trend is projected to the harvest year; low and high are
the 25th and 75th percentile of actual / trend. Price: "Prices Received" averaged over the crop's
usual sale months, one value per year over the last 7 years; base is the median, low and high
the quartiles. Nominal dollars. Low is low yield x low price and high is high yield x high price
for every crop at once: a range from past years, not a confidence interval.

``forecast`` never raises: problems become warnings and the affected crop gets "no estimate".
Costs other than the investment passed in, seed, insurance, payments and basis are not modelled.
"""

import datetime as dt
import logging
import math

import numpy as np

from app.services.nass import (
    CROPS,
    HA_TO_ACRE,
    Nass,
    NassUnavailable,
    normalize_crop,
    number,
)

logger = logging.getLogger(__name__)

MONTHS = {
    name: index
    for index, name in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1
    )
}
YIELD_YEARS, PRICE_YEARS = 15, 7
PREFER_YIELD, MIN_YIELD = 6, 3  # series length wanted for a trend / shortest one still used
PREFER_PRICE, MIN_PRICE = 3, 1
SCENARIOS = ("low", "base", "high")
MAX_PLAN = 10


def _money(value) -> float | None:
    return None if value is None else round(float(value), 2)


def _scenarios(values: dict) -> dict:
    return {key: _money(values[key]) for key in SCENARIOS}


def _gather(sources, prefer, minimum, what, warnings):
    """The first source with enough years; else the longest usable one (with a warning)."""
    best = None
    for label, basis, load in sources:
        try:
            series = load()
        except NassUnavailable as error:
            warnings.append(f"{what}: {label} failed ({error})")
            continue
        if not series:
            continue
        if len(series) >= prefer:
            return series, label, basis
        if len(series) >= minimum and (best is None or len(series) > len(best[0])):
            best = (series, label, basis)
    if best:
        warnings.append(f"{what}: only {len(best[0])} year(s) from {best[1]}, so it is rough")
    return best


def _yield_series(nass: Nass, crop: str, location: dict, first_year: int, level: str) -> dict:
    spec = CROPS[crop]
    params = {
        "source_desc": "SURVEY",
        "commodity_desc": spec.commodity,
        "short_desc": spec.yield_desc,
        "state_fips_code": location["state"],
        "agg_level_desc": level,
        "year__GE": first_year,
    }
    if level == "COUNTY":
        params["county_code"] = location["county"]
    series = {}
    for row in nass.query(**params):
        if str(row.get("reference_period_desc", "YEAR")).upper() != "YEAR":
            continue  # forecasts such as "YEAR - AUG FCST"
        value = number(row.get("Value"))
        if value:
            series[int(row["year"])] = value
    return series


def _price_series(nass: Nass, crop: str, location, first_year: int, freq: str, level: str):
    spec = CROPS[crop]
    if level == "STATE" and not location:
        return {}
    params = {
        "source_desc": "SURVEY",
        "commodity_desc": spec.commodity,
        "short_desc": spec.price_desc,
        "agg_level_desc": level,
        "freq_desc": freq,
        "year__GE": first_year,
    }
    if level == "STATE":
        params["state_fips_code"] = location["state"]
    per_year: dict[int, list[float]] = {}
    for row in nass.query(**params):
        value = number(row.get("Value"))
        period = str(row.get("reference_period_desc", "")).upper()
        if not value:
            continue
        if freq == "MONTHLY":
            if MONTHS.get(period[:3]) in spec.sale_months:
                per_year.setdefault(int(row["year"]), []).append(value)
        elif period == "MARKETING YEAR":
            per_year.setdefault(int(row["year"]), []).append(value)
    needed = math.ceil(len(spec.sale_months) / 2) if freq == "MONTHLY" else 1
    return {y: float(np.mean(v)) for y, v in per_year.items() if len(v) >= needed}


def yield_forecast(series: dict, target_year: int) -> dict:
    years = sorted(series)[-YIELD_YEARS:]
    values = np.array([series[y] for y in years], float)
    axis = np.array(years, float)
    if len(years) >= PREFER_YIELD:
        slope, intercept = np.polyfit(axis, values, 1)
        fit = slope * axis + intercept
        ok = fit > 0
        ratio = values[ok] / fit[ok]
        base = float(
            np.clip(slope * target_year + intercept, values.min() * 0.9, values.max() * 1.1)
        )
        method = "trend"
    else:
        slope, base, method = 0.0, float(values.mean()), "mean"
        ratio = values / base if len(years) >= 3 else np.array([1.0])
    low, high = np.percentile(ratio, [25, 75])
    return {
        "base": base,
        "low": base * float(low),
        "high": base * float(high),
        "years": len(years),
        "span": f"{years[0]}-{years[-1]}",
        "trendPerYear": float(slope),
        "method": method,
    }


def price_forecast(series: dict) -> dict:
    years = sorted(series)[-PRICE_YEARS:]
    values = np.array([series[y] for y in years], float)
    if len(values) >= 3:
        low, median, high = np.percentile(values, [25, 50, 75])
    else:
        low, median, high = values.min(), values.mean(), values.max()
    return {
        "base": float(median),
        "low": float(low),
        "high": float(high),
        "years": len(years),
        "span": f"{years[0]}-{years[-1]}",
    }


def _overrides(values: dict | None, what: str, warnings: list) -> dict:
    found = {}
    for key, value in (values or {}).items():
        try:
            found[normalize_crop(key)] = float(value)
        except (ValueError, TypeError):
            warnings.append(f"{what} {key!r}={value!r} ignored (unknown crop or not a number)")
    return found


def _parse_plan(crops: dict | None, warnings: list) -> list[tuple[dt.date, str]]:
    plan = []
    for start, crop in (crops or {}).items():
        try:
            plan.append((dt.date.fromisoformat(str(start).strip()), normalize_crop(crop)))
        except ValueError as error:
            warnings.append(f"Plan entry {start!r}: {crop!r} skipped ({error})")
    plan.sort()
    if len(plan) > MAX_PLAN:
        warnings.append(f"Only the first {MAX_PLAN} plan entries are used")
        plan = plan[:MAX_PLAN]
    return plan


def forecast(
    nass: Nass,
    lat: float,
    lng: float,
    crops: dict,
    area_ha: float | None = None,
    investment=None,
    attribute: str = "start",
    price_override: dict | None = None,
    yield_override: dict | None = None,
    today: dt.date | None = None,
) -> dict:
    warnings: list[str] = []
    out = {
        "location": None,
        "areaHa": None,
        "revenueAttributedTo": attribute,
        "crops": [],
        "totalGrossRevenue": None,
        "scenarioNote": (
            "low = low yield x low price, high = high yield x high price for every crop; "
            "base = trend (or mean) yield x median price. A range from past years, not a "
            "confidence interval."
        ),
        "notes": [],
        "warnings": warnings,
    }
    try:
        _forecast(
            nass,
            out,
            warnings,
            lat,
            lng,
            crops,
            area_ha,
            investment,
            attribute,
            price_override,
            yield_override,
            today or dt.date.today(),
        )
    except NassUnavailable as error:
        warnings.append(str(error))
    except Exception as error:  # the contract is "never raises"
        logger.warning("Crop revenue failed: %s", type(error).__name__)
        warnings.append(f"Unexpected {type(error).__name__}")
    return out


def _investment(investment, warnings):
    """(total, {year: amount} or None); (None, None) when absent or invalid."""
    if investment is None:
        return None, None
    try:
        if isinstance(investment, dict):
            per_year = {int(k): float(v) for k, v in investment.items()}
            total = sum(per_year.values())
            bad = any(v < 0 for v in per_year.values())
        else:
            per_year, total = None, float(investment)
            bad = total < 0
        if bad:
            raise ValueError("negative")
    except (ValueError, TypeError):
        warnings.append("Investment is not a non-negative number or {year: number}; no ROI")
        return None, None
    return total, per_year


def _forecast(
    nass,
    out,
    warnings,
    lat,
    lng,
    crops,
    area_ha,
    investment,
    attribute,
    price_override,
    yield_override,
    today,
):
    nass.require_key()
    if attribute not in ("start", "harvest"):
        warnings.append(f"attribute {attribute!r} is not 'start' or 'harvest'; 'start' used")
        attribute = out["revenueAttributedTo"] = "start"
    area = float(area_ha) if area_ha and area_ha > 0 else 1 / HA_TO_ACRE
    acres = area * HA_TO_ACRE
    out["areaHa"] = round(area, 3)
    out["notes"] = [
        f"Field area {area:.2f} ha ({acres:.2f} acres); every crop is assumed to cover the "
        "whole field" + ("; values are per acre" if abs(acres - 1) < 1e-6 else ""),
        "Prices are nominal dollars; yields are county averages, not field-level",
        "Gross revenue only: no costs other than the investment passed in, no seed, insurance "
        "or government payments",
    ]
    total_investment, per_year_investment = _investment(investment, warnings)
    prices = _overrides(price_override, "price_override", warnings)
    yields = _overrides(yield_override, "yield_override", warnings)
    plan = _parse_plan(crops, warnings)
    if not plan:
        warnings.append("No valid crop in the plan")
        return
    location = nass.county(lat, lng)
    if location is None:
        warnings.append("The field is not in a U.S. county; NASS data covers the U.S. only")
        return
    out["location"] = {
        "county": location["name"],
        "countyFips": location["fips"],
        "state": location["stateCode"],
    }
    first_year = today.year - YIELD_YEARS - 1
    series: dict[str, tuple] = {}
    items, previous = [], None
    for start, crop in plan:
        spec = CROPS[crop]
        harvest = start + dt.timedelta(days=spec.days_to_harvest)
        if previous and start < previous[0]:
            warnings.append(
                f"{start} {crop} starts before {previous[1]} is harvested ({previous[0]}): "
                "the plan overlaps on the same area"
            )
        previous = (harvest, crop)
        if crop not in series:
            series[crop] = _load(
                nass, crop, location, first_year, crop in yields, crop in prices, warnings
            )
        yield_series, price_series = series[crop]
        item = {
            "startDate": start.isoformat(),
            "harvestDateEstimate": harvest.isoformat(),
            "crop": crop,
            "revenueYear": start.year if attribute == "start" else harvest.year,
        }
        reasons = []
        if yield_series is None and crop not in yields:
            reasons.append("no yield data")
        if price_series is None and crop not in prices:
            reasons.append("no price data")
        if reasons:
            items.append({**item, "status": "no estimate", "reasons": reasons})
            continue
        if crop in yields:
            yf = {k: yields[crop] for k in SCENARIOS} | {
                "years": 0,
                "span": None,
                "trendPerYear": 0.0,
                "method": "user override",
            }
            ysource = "user override"
        else:
            yf, ysource = yield_forecast(yield_series[0], harvest.year), yield_series[1]
        if crop in prices:
            pf = {k: prices[crop] for k in SCENARIOS} | {"years": 0, "span": None}
            psource, pbasis = "user override", "price_override"
        else:
            pf, psource, pbasis = price_forecast(price_series[0]), price_series[1], price_series[2]
        per_acre = {k: yf[k] * pf[k] * spec.factor for k in SCENARIOS}
        items.append(
            {
                **item,
                "status": "ok",
                "yieldPerAcre": {
                    "unit": f"{spec.unit}/acre",
                    **{k: round(yf[k], 2) for k in SCENARIOS},
                    "source": ysource,
                    "method": yf["method"],
                    "years": yf["years"],
                    "span": yf["span"],
                },
                "price": {
                    "unit": spec.price_unit,
                    **{k: round(pf[k], 3) for k in SCENARIOS},
                    "source": psource,
                    "basis": pbasis,
                    "years": pf["years"],
                    "span": pf["span"],
                },
                "grossRevenuePerAcre": _scenarios(per_acre),
                "grossRevenue": _scenarios({k: v * acres for k, v in per_acre.items()}),
            }
        )
    out["crops"] = items
    good = [i for i in items if i["status"] == "ok"]
    missing = [f"{i['startDate']} {i['crop']}" for i in items if i["status"] != "ok"]
    if not good:
        warnings.append("No crop has an estimate, so there are no totals")
        return
    if missing:
        warnings.append(f"The totals exclude the crops without an estimate: {', '.join(missing)}")
    total = {k: sum(i["grossRevenue"][k] for i in good) for k in SCENARIOS}
    out["totalGrossRevenue"] = _scenarios(total)
    if total_investment is not None:
        _roi(out, warnings, good, total, total_investment, per_year_investment, bool(missing))


def _load(nass, crop, location, first_year, has_yield, has_price, warnings):
    """(yield series or None, price series or None) as (data, label, basis) triples."""
    spec = CROPS[crop]
    yield_series = None
    if not has_yield:
        sources = [
            (
                "NASS county",
                "county",
                lambda: _yield_series(nass, crop, location, first_year, "COUNTY"),
            ),
            (
                "NASS state",
                "state",
                lambda: _yield_series(nass, crop, location, first_year, "STATE"),
            ),
        ]
        yield_series = _gather(sources, PREFER_YIELD, MIN_YIELD, f"{crop} yield", warnings)
        if yield_series is None:
            warnings.append(f"{crop}: no yield series (short_desc '{spec.yield_desc}')")
    price_series = None
    if not has_price:
        months = "average of months " + ",".join(str(m) for m in spec.sale_months)
        sources = []
        for freq, basis in (("MONTHLY", months), ("ANNUAL", "annual marketing-year price")):
            for level, label in (("STATE", "state"), ("NATIONAL", "US")):
                sources.append(
                    (
                        f"NASS {label} {freq.lower()}",
                        basis,
                        lambda f=freq, lv=level: _price_series(
                            nass, crop, location, first_year, f, lv
                        ),
                    )
                )
        price_series = _gather(sources, PREFER_PRICE, MIN_PRICE, f"{crop} price", warnings)
        if price_series is None:
            warnings.append(f"{crop}: no price series (short_desc '{spec.price_desc}')")
    return yield_series, price_series


def _roi(out, warnings, good, total, investment, per_year, incomplete):
    def ratio(revenue, spent):
        return None if spent <= 0 else (revenue - spent) / spent

    def percent(values):
        return {k: None if v is None else round(100 * v, 1) for k, v in values.items()}

    shares = {k: ratio(total[k], investment) for k in SCENARIOS}
    out["roi"] = {
        "investmentTotal": _money(investment),
        "netProfit": {k: _money(total[k] - investment) for k in SCENARIOS},
        "roiTotalPct": percent(shares),
    }
    if investment <= 0:
        warnings.append("Investment is 0, so ROI is undefined")
    if incomplete:
        warnings.append("ROI compares all investment with only the crops that have an estimate")
    if per_year is None:
        return
    revenue: dict[int, dict] = {}
    for item in good:
        row = revenue.setdefault(item["revenueYear"], dict.fromkeys(SCENARIOS, 0.0))
        for key in SCENARIOS:
            row[key] += item["grossRevenue"][key]
    rows = []
    for year in sorted(set(revenue) | set(per_year)):
        gross = revenue.get(year, dict.fromkeys(SCENARIOS, 0.0))
        spent = per_year.get(year, 0.0)
        rows.append(
            {
                "year": year,
                "investment": _money(spent),
                "grossRevenue": _scenarios(gross),
                "netProfit": {k: _money(gross[k] - spent) for k in SCENARIOS},
                "roiPct": percent({k: ratio(gross[k], spent) for k in SCENARIOS}),
            }
        )
    out["roi"]["perYear"] = rows
    no_investment = [y for y in revenue if y not in per_year]
    if no_investment:
        warnings.append(f"Revenue in {no_investment} has no investment, so its ROI is undefined")
