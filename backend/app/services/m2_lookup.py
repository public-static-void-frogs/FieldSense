"""Reader for the precomputed M2 "neighbour evidence" output (no network, no model run).

The batch job ``ml/field-prediction-model/neighbour-evidence-engine/m2_neighbour_evidence.py``
writes the tables below. This module reads them once (cached, thread-safe) and answers
"what does the evidence say here" for a coordinate. Call ``reload()`` after a new batch run.

Matching: nearest analysed field within FIELD_RADIUS_KM gives level "field"; else at least
MIN_NEIGHBOURS fields within NEIGHBOUR_RADIUS_KM give "neighbourhood"; farther than COVERAGE_KM
from every analysed field gives ok=False. Without field_effects.parquet the answer is "region"
(study-wide only).

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
NEIGHBOUR_RADIUS_KM = 30.0  # same radius as the comparable-field count of the batch job
MIN_NEIGHBOURS = 20  # fewer fields than this -> no neighbourhood summary
COVERAGE_KM = 50.0  # farther than this from every analysed field = outside coverage
VERDICT_RANK = {
    "supported (all checks pass)": 0,
    "supported by the DML model; matched baseline not fully balanced": 1,
    "interval excludes 0, but placebo or negative control fails": 2,
    "no detectable drought-specific effect": 3,
    "arm gap only (drought effect not identified)": 4,
    "abstain": 5,
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
        ok = ok.assign(
            _rank=ok["verdict"].map(VERDICT_RANK).fillna(9),
            _sees=~ok["outcome_sees_drought"].fillna(False).astype(bool),
            _snr=(ok["gamma"].abs() / (ok["gamma_hi"] - ok["gamma_lo"]).replace(0, np.nan)).fillna(
                0
            ),
        )
        r = ok.sort_values(["_rank", "_sees", "_snr"], ascending=[True, True, False]).iloc[0]
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
                verdict="abstain"
                if ab
                else min(g.loc[~g["abstain"], "verdict"], key=lambda v: VERDICT_RANK.get(v, 9)),
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
            ok = r.status == "ok"
            e, lo, hi = _py(r.effect_drought), _py(r.lo95), _py(r.hi95)
            d = dict(
                usable=ok,
                status=r.status,
                note=_py(r.note) if not ok else None,
                n_comparable_treated=_py(r.n_comparable_treated_30km),
                n_comparable_control=_py(r.n_comparable_control_30km),
                scenario_d2_weeks=_py(r.scenario_d2_weeks),
                forest_mean_effect=_py(r.forest_mean_effect),
                heterogeneity_vars=_py(r.heterogeneity_vars),
            )
            if ok:
                d.update(
                    effect=e,
                    lo95=lo,
                    hi95=hi,
                    effect_agrees=bool(
                        exp and e is not None and np.sign(e) == exp and (lo > 0 or hi < 0)
                    ),
                    vs_study_mean=None
                    if d["forest_mean_effect"] is None
                    else round(e - d["forest_mean_effect"], 6),
                )
            out.setdefault(r.crop, {}).setdefault(r.treatment, {})[r.outcome] = d
        return out

    def _neighbourhood(self, ids):
        rows = pd.concat([self.fe_by_id[i] for i in ids], ignore_index=True)
        out = {}
        for (crop, tr, oc), g in rows.groupby(["crop", "treatment", "outcome"]):
            ok = g[g["status"] == "ok"]
            exp = self.expected.get((crop, tr))
            d = dict(n_fields=int(len(g)), n_usable=int(len(ok)))
            if len(ok) >= MIN_NEIGHBOURS:
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
            else:
                d["note"] = (
                    f"fewer than {MIN_NEIGHBOURS} fields with enough comparable fields: no summary"
                )
            out.setdefault(crop, {}).setdefault(tr, {})[oc] = d
        return out

    # -------------------------------------------------------------- text
    def _summary_and_warnings(self, region, field, hood, level):
        S, W = [], []
        for crop, trs in region.items():
            for tr, b in trs.items():
                nm = f"{crop} {tr} ({TREATMENT_NAME.get(tr, tr)} vs {b['control']})"
                if b["abstain"]:
                    W.append(f"{nm}: no estimate - {b['abstain_reason']}")
                    continue
                h = b["headline"]
                exp = {-1: "negative", 1: "positive"}.get(b["expected_sign"], "?")
                s = (
                    f"{nm}: in drought seasons the practice changed {h['outcome']} by {_fmt(h['gamma'])} [{_fmt(h['gamma_lo'])}, {_fmt(h['gamma_hi'])}] "
                    f"beyond its normal-season gap of {_fmt(h['theta_normal'])} (expected sign {exp}); verdict: {b['verdict']}."
                )
                loc = None
                if level == "field":
                    f = field.get(crop, {}).get(tr, {}).get(h["outcome"])
                    if f:
                        loc = (
                            (
                                f"At this field: drought-season gap {_fmt(f['effect'])} [{_fmt(f['lo95'])}, {_fmt(f['hi95'])}] "
                                f"({f['n_comparable_treated']} treated / {f['n_comparable_control']} control comparable fields within 30 km)"
                            )
                            if f["usable"]
                            else "At this field: insufficient evidence (too few comparable fields), no number given"
                        )
                elif level == "neighbourhood":
                    f = hood.get(crop, {}).get(tr, {}).get(h["outcome"])
                    if f and "median" in f:
                        loc = (
                            f"Fields within {NEIGHBOUR_RADIUS_KM:.0f} km: median drought-season gap {_fmt(f['median'])} (p10 {_fmt(f['p10'])}, p90 {_fmt(f['p90'])}, "
                            f"{f['n_usable']} fields)"
                        )
                if loc:
                    s += " " + loc + "."
                S.append(s)
                if b["verdict"] not in SUPPORTED:
                    W.append(f"{nm}: {b['verdict']} - do not present as a finding")
                elif b["verdict"].startswith("supported by the DML"):
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
                ids = self.fld_id[d <= NEIGHBOUR_RADIUS_KM]
                if len(ids) >= MIN_NEIGHBOURS:
                    match = dict(
                        level="neighbourhood",
                        csbid=None,
                        distance_km=round(float(d[i]), 3),
                        n_neighbour_fields=int(len(ids)),
                    )
                    hood = self._neighbourhood(ids)
                else:
                    match = dict(
                        level="region",
                        csbid=None,
                        distance_km=round(float(d[i]), 3),
                        n_neighbour_fields=int(len(ids)),
                    )
        region = self._region(crops, trs)
        if hood is not None and crops:
            hood = {c: v for c, v in hood.items() if c in crops}
        if hood is not None and trs:
            hood = {c: {t: v for t, v in tt.items() if t in trs} for c, tt in hood.items()}
        if field is not None and trs:
            field = {c: {t: v for t, v in tt.items() if t in trs} for c, tt in field.items()}
        summary, warnings = self._summary_and_warnings(
            region, field or {}, hood or {}, match["level"]
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
