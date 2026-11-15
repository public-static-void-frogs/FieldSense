"""Reader for the precomputed M2 "neighbour evidence" output (no network, no model run).

The batch job ``ml/field-prediction-model/neighbour-evidence-engine/m2_neighbour_evidence.py``
writes the tables below. This module reads them once (cached, thread-safe) and answers
"what does the evidence say here" for a coordinate. Call ``reload()`` after a new batch run.

Matching: the nearest analysed field within FIELD_RADIUS_KM gives level "field". Otherwise the
analysed fields within a radius that is widened 30 -> 60 -> 120 km until MIN_NEIGHBOURS are inside;
at least MIN_NEIGHBOURS_SOFT of them give "neighbourhood" (with a warning when widened). Farther
than COVERAGE_KM from every analysed field gives ok=False. Without field_effects.parquet, or with
too few fields nearby, the answer is "region" (study-wide only).

Thin data: the batch job labels weak evidence instead of abstaining (evidence_tier: full > limited >
one season type > pooled > descriptive, plus confidence and tier_note). Anything below "full" has no
drought-specific gamma; ``headline_effect`` and ``headline_basis`` say what the number is. An older
effects.csv without these columns is read as all full tier.

Files read from the output folder (a missing optional file is listed in meta["missing_files"]):
  effects.csv              required  crop x treatment x outcome: gamma, thetas, intervals, checks
  field_effects.parquet    optional  per-field what-if for drought seasons
  outcome_diagnostics.csv  optional  whether each outcome responds to drought at all
  county_check_<crop>.csv  optional  aggregate NASS yield check

The evidence label of every answer is an adjusted association from observational satellite
data, not a guaranteed effect. Treatments: T1 continuous crop vs rotated, T2 diverse rotation,
T3 small grain / hay, T4 winter cover, T5 host-crop return interval. The first arm is treated.
"""

import math
import threading
from pathlib import Path

import numpy as np
import pandas as pd

FIELD_RADIUS_KM = 1.0  # a point this close to an analysed field centroid is treated as "that field"
NEIGHBOUR_RADIUS_KM = 30.0  # first radius of the neighbourhood search, same as the comparable-field count of the batch job
NEIGHBOUR_MAX_KM = 120.0  # the radius is doubled (30 -> 60 -> 120 km) until MIN_NEIGHBOURS analysed fields are inside
MIN_NEIGHBOURS = 20  # this many analysed fields: normal neighbourhood summary
MIN_NEIGHBOURS_SOFT = 5  # 5-19 fields: summary with a "few fields, indicative" caveat; fewer -> study-wide result only
COVERAGE_KM = 120.0  # farther than this from every analysed field = outside coverage
VERDICT_RANK = {
    "supported (all checks pass)": 0,
    "supported by the DML model; matched baseline not fully balanced": 1,
    "interval excludes 0, but placebo or negative control fails": 2,
    "no detectable drought-specific effect": 3,
    "arm gap only (drought effect not identified)": 4,
    "abstain": 5,
}
TIER_RANK = {
    "full": 0,
    "limited": 1,
    "one season type": 2,
    "pooled": 3,
    "descriptive": 4,
    "none": 5,
}
TIER_TEXT = {
    "full": "full evidence",
    "limited": "small sample",
    "one season type": "one season type only",
    "pooled": "all seasons pooled",
    "descriptive": "descriptive only",
}
SUPPORTED = (
    "supported (all checks pass)",
    "supported by the DML model; matched baseline not fully balanced",
)
TREATMENT_NAME = {
    "T1": "continuous crop",
    "T2": "diverse rotation (>=3 crop groups in 5 y)",
    "T3": "small grain / hay in the last 3 y",
    "T4": "winter cover crop",
    "T5": "host-crop return interval >= 2 y",
}
EVIDENCE_LABEL = "Adjusted association from observational satellite data"
CHECK_KEYS = (
    "gamma_placebo_p",
    "neg_control_pass",
    "balance_pass",
    "sensitivity_same_sign",
    "sign_agrees_with_expected",
    "overlap_share_drought",
    "overlap_share_normal",
    "few_clusters",
    "max_smd_after",
    "gamma_identified",
)
OUT_KEYS = (
    "evidence_tier",
    "confidence",
    "tier_note",
    "method",
    "headline_basis",
    "headline_effect",
    "headline_lo",
    "headline_hi",
    "headline_sign_agrees",
    "theta_pooled",
    "lo_pooled",
    "hi_pooled",
    "n_pooled",
    "outcome_label",
    "gamma",
    "gamma_lo",
    "gamma_hi",
    "theta_normal",
    "lo_normal",
    "hi_normal",
    "theta_drought",
    "lo_drought",
    "hi_drought",
    "verdict",
    "outcome_sees_drought",
    "abstain",
    "abstain_reason",
    "n_drought",
    "n_normal",
    "squares",
)


def _py(v):
    """numpy / pandas scalar -> JSON-safe python (NaN, NaT, inf -> None)."""
    if v is None or v is pd.NA:
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        return None if v in ("nan", "") else v
    return v


def _vrank(v):
    """rank of a verdict; the 'small sample: ' prefix of the limited tier is ignored"""
    v = str(v or "").replace("small sample: ", "")
    if v in VERDICT_RANK:
        return VERDICT_RANK[v]
    return (
        4
        if v.startswith("drought-specific effect not identified")
        else 6
        if v.startswith("descriptive")
        else 9
    )


def _hav_km(lat, lon, lats, lons):
    p = np.pi / 180
    a = (
        np.sin((lats - lat) * p / 2) ** 2
        + np.cos(lat * p) * np.cos(lats * p) * np.sin((lons - lon) * p / 2) ** 2
    )
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def _fmt(x, nd=3):
    return "n/a" if x is None else f"{x:+.{nd}f}"


class M2Evidence:
    def __init__(self, out_dir):
        self.out = Path(out_dir)
        self._lock = threading.Lock()
        self._loaded = False

    def reload(self):
        with self._lock:
            self._loaded = False
        self._ensure()

    def _read(self, rel, required=False, **kw):
        f = self.out / rel
        if not f.exists():
            if required:
                raise FileNotFoundError(f"M2 output missing: {f}")
            self.missing.append(rel)
            return None
        return pd.read_csv(f, **kw) if f.suffix == ".csv" else pd.read_parquet(f)

    def _ensure(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self.missing = []
            eff = self._read("effects.csv", True)
            eff["abstain"] = eff["abstain"].astype(bool)
            if (
                "evidence_tier" not in eff
            ):  # effects.csv of an older batch run: every estimate was a full-tier one
                eff["evidence_tier"] = np.where(eff["abstain"], "none", "full")
            for c in (
                "confidence",
                "tier_note",
                "method",
                "headline_basis",
                "headline_sign_agrees",
            ):
                if c not in eff:
                    eff[c] = pd.Series([None] * len(eff), dtype=object, index=eff.index)
            for c in (
                "headline_effect",
                "headline_lo",
                "headline_hi",
                "theta_pooled",
                "lo_pooled",
                "hi_pooled",
                "n_pooled",
            ):
                if c not in eff:
                    eff[c] = np.nan
            eff["headline_basis"] = eff["headline_basis"].astype(object)
            old = eff["headline_effect"].isna() & ~eff["abstain"]
            if old.any():  # older table: headline = the drought-season effect
                eff.loc[old, ["headline_effect", "headline_lo", "headline_hi"]] = eff.loc[
                    old, ["theta_drought", "lo_drought", "hi_drought"]
                ].to_numpy()
                eff.loc[old, "headline_basis"] = "effect in drought seasons"
            self.eff = eff
            self.limits = (
                [x.strip() for x in str(eff["limits"].iloc[0]).split("|")]
                if "limits" in eff and len(eff)
                else []
            )
            self.expected = {
                (r.crop, r.treatment): int(r.expected_sign)
                for r in eff.drop_duplicates(["crop", "treatment"]).itertuples()
            }
            diag = self._read("outcome_diagnostics.csv")
            self.diag = (
                {}
                if diag is None
                else {
                    (r.crop, r.outcome): dict(
                        drought_coef=_py(r.drought_coef),
                        sd_units=_py(r.sd_units),
                        sees_drought=bool(r.sees_drought),
                    )
                    for r in diag.itertuples()
                }
            )
            fe = self._read("field_effects.parquet")
            self.fe = None
            if fe is not None and len(fe):
                self.fe = fe.reset_index(drop=True)
                self.fe["CSBID"] = self.fe["CSBID"].astype(str)
                u = self.fe.drop_duplicates("CSBID")
                self.fld_id = u["CSBID"].to_numpy()
                self.fld_lat, self.fld_lon = (
                    u["centroid_lat"].to_numpy(float),
                    u["centroid_lon"].to_numpy(float),
                )
                self.fe_by_id = {k: g for k, g in self.fe.groupby("CSBID")}
            self.county = {}
            for crop in sorted(eff["crop"].unique()):
                cc = self._read(f"county_check_{crop}.csv")
                if cc is not None:
                    self.county[crop] = [
                        {k: _py(v) for k, v in r.items()} for r in cc.to_dict("records")
                    ]
            self._loaded = True

    # -------------------------------------------------------------- blocks
    def _outcome_row(self, r):
        d = {k: _py(r.get(k)) for k in OUT_KEYS if k in r}
        d["checks"] = {k: _py(r.get(k)) for k in CHECK_KEYS if k in r}
        d["adjusted_for"] = _py(r.get("adjusted_for"))
        d["adjustment_note"] = _py(r.get("adjustment_note"))
        return d

    def _headline(self, g):
        ok = g[~g["abstain"]]
        if ok.empty:
            return None
        snr_g = ok["gamma"].abs() / (ok["gamma_hi"] - ok["gamma_lo"]).replace(0, np.nan)
        snr_h = ok["headline_effect"].abs() / (ok["headline_hi"] - ok["headline_lo"]).replace(
            0, np.nan
        )
        ok = ok.assign(
            _tier=ok["evidence_tier"].map(TIER_RANK).fillna(5),
            _rank=ok["verdict"].map(_vrank),
            _sees=~ok["outcome_sees_drought"].fillna(False).astype(bool),
            _snr=snr_g.fillna(snr_h).fillna(0),
        )
        r = ok.sort_values(
            ["_tier", "_rank", "_sees", "_snr"], ascending=[True, True, True, False]
        ).iloc[0]
        return dict(outcome=r["outcome"], **self._outcome_row(r))

    def _region(self, crops, treatments):
        out = {}
        for (crop, tr), g in self.eff.groupby(["crop", "treatment"]):
            if (crops and crop not in crops) or (treatments and tr not in treatments):
                continue
            first = g.iloc[0]
            ab = g["abstain"].all()
            blk = dict(
                treated=first["treated"],
                control=first["control"],
                expected_sign=int(first["expected_sign"]),
                abstain=bool(ab),
                abstain_reason=_py(first.get("abstain_reason")) if ab else None,
                n_treated_drought=_py(first["n_treated_drought"]),
                n_control_drought=_py(first["n_control_drought"]),
                overlap_share_drought=_py(first["overlap_share_drought"]),
                verdict="abstain" if ab else min(g.loc[~g["abstain"], "verdict"], key=_vrank),
                evidence_tier=None
                if ab
                else min(g.loc[~g["abstain"], "evidence_tier"], key=lambda t: TIER_RANK.get(t, 5)),
                confidence=None if ab else _py(self._headline(g).get("confidence")),
                headline=self._headline(g),
                outcomes={
                    r["outcome"]: self._outcome_row(r) for _, r in g[~g["abstain"]].iterrows()
                },
            )
            out.setdefault(crop, {})[tr] = blk
        return out

    def _field_rows(self, rows):
        out = {}
        for r in rows.itertuples():
            exp = self.expected.get((r.crop, r.treatment))
            st = r.status
            usable = st in ("ok", "limited evidence")
            e, lo, hi = _py(r.effect_drought), _py(r.lo95), _py(r.hi95)
            nt = _py(
                getattr(r, "n_comparable_treated_used", None)
                if hasattr(r, "n_comparable_treated_used")
                else r.n_comparable_treated_30km
            )
            nc = _py(
                getattr(r, "n_comparable_control_used", None)
                if hasattr(r, "n_comparable_control_used")
                else r.n_comparable_control_30km
            )
            d = dict(
                usable=usable,
                status=st,
                note=_py(r.note) if st != "ok" else None,
                n_comparable_treated=nt,
                n_comparable_control=nc,
                radius_km=_py(getattr(r, "radius_used_km", None)) or NEIGHBOUR_RADIUS_KM,
                scenario_d2_weeks=_py(r.scenario_d2_weeks),
                forest_mean_effect=_py(r.forest_mean_effect),
                heterogeneity_vars=_py(r.heterogeneity_vars),
            )
            vals = dict(
                effect=e,
                lo95=lo,
                hi95=hi,
                effect_agrees=bool(
                    exp
                    and e is not None
                    and lo is not None
                    and hi is not None
                    and np.sign(e) == exp
                    and (lo > 0 or hi < 0)
                ),
                vs_study_mean=None
                if d["forest_mean_effect"] is None or e is None
                else round(e - d["forest_mean_effect"], 6),
            )
            if usable:
                d.update(vals)
                d["caveat"] = (
                    None
                    if st == "ok"
                    else "limited evidence: fewer comparable fields than the full threshold, read as indicative"
                )
            else:
                d["indicative"] = (
                    vals  # shown only as an indicative value with the note, never as a finding
                )
                d["caveat"] = "insufficient evidence: indicative only"
            out.setdefault(r.crop, {}).setdefault(r.treatment, {})[r.outcome] = d
        return out

    def _neighbourhood(self, ids, radius):
        rows = pd.concat([self.fe_by_id[i] for i in ids], ignore_index=True)
        out = {}
        for (crop, tr, oc), g in rows.groupby(["crop", "treatment", "outcome"]):
            ok = g[g["status"].isin(["ok", "limited evidence"])]
            exp = self.expected.get((crop, tr))
            d = dict(
                n_fields=int(len(g)),
                n_usable=int(len(ok)),
                n_full_evidence=int((g["status"] == "ok").sum()),
                radius_km=radius,
            )
            if len(ok) >= MIN_NEIGHBOURS_SOFT:
                e = ok["effect_drought"].to_numpy(float)
                d.update(
                    median=_py(float(np.median(e))),
                    p10=_py(float(np.percentile(e, 10))),
                    p90=_py(float(np.percentile(e, 90))),
                    median_lo95=_py(float(np.median(ok["lo95"]))),
                    median_hi95=_py(float(np.median(ok["hi95"]))),
                    share_expected_sign=_py(float((np.sign(e) == exp).mean())) if exp else None,
                    scenario_d2_weeks=_py(ok["scenario_d2_weeks"].iloc[0]),
                )
                if len(ok) < MIN_NEIGHBOURS:
                    d["note"] = (
                        f"only {len(ok)} fields with a usable estimate (< {MIN_NEIGHBOURS}): indicative"
                    )
                elif d["n_full_evidence"] < len(ok) / 2:
                    d["note"] = (
                        "most of these estimates are 'limited evidence' (few comparable fields each): read as indicative"
                    )
            else:
                d["note"] = (
                    f"fewer than {MIN_NEIGHBOURS_SOFT} fields with a usable estimate: no summary"
                )
            out.setdefault(crop, {}).setdefault(tr, {})[oc] = d
        return out

    # -------------------------------------------------------------- text
    def _summary_and_warnings(self, region, field, hood, level, radius):
        S, W = [], []
        for crop, trs in region.items():
            for tr, b in trs.items():
                nm = f"{crop} {tr} ({TREATMENT_NAME.get(tr, tr)} vs {b['control']})"
                if b["abstain"]:
                    W.append(f"{nm}: no estimate - {b['abstain_reason']}")
                    continue
                h = b["headline"]
                tier = h.get("evidence_tier") or "full"
                exp = {-1: "negative", 1: "positive"}.get(b["expected_sign"], "?")
                if h.get("gamma") is not None:
                    s = (
                        f"{nm}: in drought seasons the practice changed {h['outcome']} by {_fmt(h['gamma'])} [{_fmt(h['gamma_lo'])}, {_fmt(h['gamma_hi'])}] "
                        f"beyond its normal-season gap of {_fmt(h['theta_normal'])} (expected sign {exp}); verdict: {b['verdict']}."
                    )
                else:  # lower tiers: no drought-specific effect, only the arm gap that the data support
                    ci = (
                        ""
                        if h.get("headline_lo") is None or h.get("headline_hi") is None
                        else f" [{_fmt(h['headline_lo'])}, {_fmt(h['headline_hi'])}]"
                    )
                    s = (
                        f"{nm}: {h.get('headline_basis') or 'arm gap'} on {h['outcome']}: {_fmt(h.get('headline_effect'))}{ci} (treated minus control, "
                        f"expected sign {exp}); {TIER_TEXT.get(tier, tier)}, {h.get('confidence') or 'low'} confidence. Not a drought-specific effect."
                    )
                loc = None
                if level == "field":
                    f = field.get(crop, {}).get(tr, {}).get(h["outcome"])
                    if f:
                        if f["usable"]:
                            loc = (
                                f"At this field: drought-season gap {_fmt(f['effect'])} [{_fmt(f['lo95'])}, {_fmt(f['hi95'])}] "
                                f"({f['n_comparable_treated']} treated / {f['n_comparable_control']} control comparable fields within {f['radius_km']:.0f} km"
                                + ("" if f["status"] == "ok" else "; limited evidence, indicative")
                                + ")"
                            )
                        else:
                            ind = f["indicative"]
                            loc = (
                                f"At this field: insufficient comparable fields; indicative drought-season gap {_fmt(ind['effect'])} "
                                f"[{_fmt(ind['lo95'])}, {_fmt(ind['hi95'])}], not a finding"
                            )
                elif level == "neighbourhood":
                    f = hood.get(crop, {}).get(tr, {}).get(h["outcome"])
                    if f and "median" in f:
                        loc = (
                            f"Fields within {radius:.0f} km: median drought-season gap {_fmt(f['median'])} (p10 {_fmt(f['p10'])}, p90 {_fmt(f['p90'])}, "
                            f"{f['n_usable']} fields"
                            + ("; indicative" if f.get("note") else "")
                            + ")"
                        )
                if loc:
                    s += " " + loc + "."
                S.append(s)
                if tier != "full":
                    W.append(
                        f"{nm}: evidence tier '{tier}' ({h.get('confidence') or 'low'} confidence): {h.get('tier_note') or 'thin data'}"
                    )
                if tier in ("full", "limited"):
                    v = str(b["verdict"]).replace("small sample: ", "")
                    if v not in SUPPORTED:
                        W.append(f"{nm}: {v} - do not present as a finding")
                    elif v.startswith("supported by the DML"):
                        sm = h["checks"].get("max_smd_after")
                        W.append(
                            f"{nm}: matched baseline not fully balanced"
                            + ("" if sm is None else f" (max |SMD| {sm:.2f})")
                            + "; read it as supported by the model only"
                        )
                if h["outcome_sees_drought"] is False:
                    W.append(
                        f"{nm}: outcome {h['outcome']} does not respond to drought in this data; it cannot show a drought effect"
                    )
                if h["checks"].get("few_clusters"):
                    W.append(
                        f"{nm}: fewer than 10 squares, rely on the interval not the standard error"
                    )
                if h.get("adjustment_note"):
                    W.append(f"{nm}: {h['adjustment_note']}")
        return S, W

    # -------------------------------------------------------------- public
    def lookup(self, lat, lng, crop=None, treatments=None):
        self._ensure()
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return dict(ok=False, error=dict(code="bad_input", detail="lat/lng must be numbers"))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return dict(ok=False, error=dict(code="bad_input", detail="lat/lng out of range"))
        crops = None if crop is None else ([crop] if isinstance(crop, str) else list(crop))
        trs = (
            None
            if treatments is None
            else ([treatments] if isinstance(treatments, str) else list(treatments))
        )
        res = dict(ok=True, query=dict(lat=lat, lng=lng), evidence_label=EVIDENCE_LABEL)
        field = hood = None
        match = dict(level="region", csbid=None, distance_km=None, n_neighbour_fields=None)
        if self.fe is not None:
            d = _hav_km(lat, lng, self.fld_lat, self.fld_lon)
            i = int(np.argmin(d))
            if d[i] > COVERAGE_KM:
                return dict(
                    ok=False,
                    query=res["query"],
                    error=dict(code="outside_coverage", nearest_field_km=round(float(d[i]), 1)),
                )
            if d[i] <= FIELD_RADIUS_KM:
                match = dict(
                    level="field",
                    csbid=str(self.fld_id[i]),
                    distance_km=round(float(d[i]), 3),
                    n_neighbour_fields=None,
                )
                rows = self.fe_by_id[self.fld_id[i]]
                field = self._field_rows(rows[rows["crop"].isin(crops)] if crops else rows)
            else:
                radius = NEIGHBOUR_RADIUS_KM  # widen 30 -> 60 -> 120 km until enough analysed fields are inside
                while radius < NEIGHBOUR_MAX_KM and (d <= radius).sum() < MIN_NEIGHBOURS:
                    radius = min(radius * 2, NEIGHBOUR_MAX_KM)
                ids = self.fld_id[d <= radius]
                if len(ids) >= MIN_NEIGHBOURS_SOFT:
                    match = dict(
                        level="neighbourhood",
                        csbid=None,
                        distance_km=round(float(d[i]), 3),
                        n_neighbour_fields=int(len(ids)),
                        radius_km=radius,
                    )
                    hood = self._neighbourhood(ids, radius)
                else:
                    match = dict(
                        level="region",
                        csbid=None,
                        distance_km=round(float(d[i]), 3),
                        n_neighbour_fields=int(len(ids)),
                        radius_km=radius,
                    )
        region = self._region(crops, trs)
        if hood is not None and crops:
            hood = {c: v for c, v in hood.items() if c in crops}
        if hood is not None and trs:
            hood = {c: {t: v for t, v in tt.items() if t in trs} for c, tt in hood.items()}
        if field is not None and trs:
            field = {c: {t: v for t, v in tt.items() if t in trs} for c, tt in field.items()}
        summary, warnings = self._summary_and_warnings(
            region,
            field or {},
            hood or {},
            match["level"],
            match.get("radius_km") or NEIGHBOUR_RADIUS_KM,
        )
        if match["level"] == "neighbourhood" and match["radius_km"] > NEIGHBOUR_RADIUS_KM:
            warnings.insert(
                0,
                f"fewer than {MIN_NEIGHBOURS} analysed fields within {NEIGHBOUR_RADIUS_KM:.0f} km: neighbourhood widened to {match['radius_km']:.0f} km",
            )
        if match["level"] == "region":
            warnings.insert(
                0,
                "no field-level or neighbourhood evidence for this point (field_effects.parquet missing, or too few analysed fields nearby): study-wide result only",
            )
        res.update(
            match=match,
            region=region,
            field=field,
            neighbourhood=hood,
            summary=summary,
            warnings=warnings,
        )
        res["meta"] = dict(
            source_dir=str(self.out),
            missing_files=list(self.missing),
            county_check=self.county or None,
            outcome_diagnostics={f"{c}:{o}": v for (c, o), v in self.diag.items()} or None,
            limits=self.limits,
            units="index points of the outcome (ndvi_area: NDVI x days); first treatment arm is the treated arm",
        )
        return res
