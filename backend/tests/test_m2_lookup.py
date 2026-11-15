import tempfile
import unittest
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from support import create_field, isolated_app, register

from app.services.m2_lookup import EVIDENCE_LABEL, M2Evidence

LON, LAT = -93.6, 42.0
SUPPORTED = "supported (all checks pass)"


def write_m2(root: Path, fields: int = 25, with_fields: bool = True):
    """The smallest M2 output folder m2_lookup.py accepts: corn T1 (supported) and T2 (abstain)."""

    def effect(treatment, outcome, abstain, verdict, gamma):
        return dict(
            crop="corn", treatment=treatment, outcome=outcome, treated="continuous corn",
            control="rotated", expected_sign=-1 if treatment == "T1" else 1, abstain=abstain,
            abstain_reason="too few drought-season fields" if abstain else None,
            n_treated_drought=300, n_control_drought=900, overlap_share_drought=0.8,
            verdict=verdict, outcome_label=outcome, gamma=gamma, gamma_lo=gamma - 0.02,
            gamma_hi=gamma + 0.01, theta_normal=-0.01, lo_normal=-0.02, hi_normal=0.0,
            theta_drought=gamma - 0.01, lo_drought=gamma - 0.03, hi_drought=gamma,
            outcome_sees_drought=True, n_drought=1200, n_normal=5000, squares=14,
            gamma_placebo_p=0.02, neg_control_pass=True, balance_pass=True,
            sensitivity_same_sign=True, sign_agrees_with_expected=True,
            overlap_share_normal=0.9, few_clusters=False, max_smd_after=0.04,
            gamma_identified=True, adjusted_for="soil, size", adjustment_note=None,
            limits="observational | association only",
        )  # fmt: skip

    rows = [
        effect("T1", "ndwi_jul_aug", False, SUPPORTED, -0.05),
        effect("T1", "peak_ndvi", False, "no detectable drought-specific effect", -0.01),
        effect("T2", "ndwi_jul_aug", True, "abstain", float("nan")),
    ]
    pd.DataFrame(rows).to_csv(root / "effects.csv", index=False)
    pd.DataFrame(
        [dict(crop="corn", outcome="ndwi_jul_aug", drought_coef=-1.4, sd_units=1.4,
              sees_drought=True)]
    ).to_csv(root / "outcome_diagnostics.csv", index=False)  # fmt: skip
    if not with_fields:
        return

    def field_row(index, status="ok"):
        ok = status == "ok"
        return dict(
            CSBID=str(1000 + index), centroid_lat=LAT + index * 0.001, centroid_lon=LON,
            crop="corn", treatment="T1", outcome="ndwi_jul_aug",
            effect_drought=-0.04 - index * 0.001 if ok else None, lo95=-0.07 if ok else None,
            hi95=-0.01 if ok else None, status=status,
            note=None if ok else "insufficient evidence", n_comparable_treated_30km=40,
            n_comparable_control_30km=90, scenario_d2_weeks=6, forest_mean_effect=-0.03,
            heterogeneity_vars="awc",
        )  # fmt: skip

    table = [field_row(i) for i in range(fields)]
    table[1]["effect_drought"] = None
    table[1]["status"] = "insufficient evidence"
    pd.DataFrame(table).to_parquet(root / "field_effects.parquet")


class M2EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        write_m2(self.root)
        self.m2 = M2Evidence(self.root)

    def test_point_on_a_field_gets_its_what_if(self):
        result = self.m2.lookup(LAT, LON)
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence_label"], EVIDENCE_LABEL)
        self.assertEqual(result["match"]["level"], "field")
        self.assertEqual(result["match"]["csbid"], "1000")
        what_if = result["field"]["corn"]["T1"]["ndwi_jul_aug"]
        self.assertTrue(what_if["usable"])
        self.assertTrue(what_if["effect_agrees"])
        self.assertEqual(what_if["n_comparable_treated"], 40)
        self.assertTrue(any("At this field" in line for line in result["summary"]))

    def test_headline_prefers_the_best_verdict_and_abstention_gives_no_number(self):
        region = self.m2.lookup(LAT, LON)["region"]["corn"]
        self.assertEqual(region["T1"]["verdict"], SUPPORTED)
        self.assertEqual(region["T1"]["headline"]["outcome"], "ndwi_jul_aug")
        self.assertAlmostEqual(region["T1"]["headline"]["gamma"], -0.05)
        self.assertTrue(region["T2"]["abstain"])
        self.assertIsNone(region["T2"]["headline"])
        self.assertEqual(region["T2"]["outcomes"], {})

    def test_neighbourhood_when_not_on_a_field_and_unusable_fields_are_dropped(self):
        result = self.m2.lookup(LAT + 0.1, LON)  # about 11 km north of the 25 field centroids
        self.assertEqual(result["match"]["level"], "neighbourhood")
        self.assertEqual(result["match"]["n_neighbour_fields"], 25)
        summary = result["neighbourhood"]["corn"]["T1"]["ndwi_jul_aug"]
        self.assertEqual((summary["n_fields"], summary["n_usable"]), (25, 24))
        self.assertEqual(summary["share_expected_sign"], 1.0)
        self.assertIsNone(result["field"])

    def test_filters_by_crop_and_treatment(self):
        result = self.m2.lookup(LAT, LON, crop="soybeans")
        self.assertEqual(result["region"], {})
        result = self.m2.lookup(LAT, LON, treatments="T2")
        self.assertEqual(list(result["region"]["corn"]), ["T2"])
        self.assertTrue(any("no estimate" in line for line in result["warnings"]))

    def test_outside_coverage_and_bad_input(self):
        far = self.m2.lookup(LAT + 2, LON)
        self.assertFalse(far["ok"])
        self.assertEqual(far["error"]["code"], "outside_coverage")
        self.assertEqual(self.m2.lookup(95, 0)["error"]["code"], "bad_input")
        self.assertEqual(self.m2.lookup("x", 0)["error"]["code"], "bad_input")

    def test_without_field_table_the_answer_is_study_wide(self):
        with tempfile.TemporaryDirectory() as other:
            write_m2(Path(other), with_fields=False)
            result = M2Evidence(other).lookup(LAT, LON)
        self.assertEqual(result["match"]["level"], "region")
        self.assertIn("field_effects.parquet", result["meta"]["missing_files"])
        self.assertIn("study-wide", result["warnings"][0])

    def test_very_few_neighbours_fall_back_to_region(self):
        with tempfile.TemporaryDirectory() as other:
            write_m2(Path(other), fields=4)
            result = M2Evidence(other).lookup(LAT + 0.1, LON)
        self.assertEqual(result["match"]["level"], "region")
        self.assertEqual(result["match"]["n_neighbour_fields"], 4)

    def test_neighbourhood_radius_is_widened_until_enough_fields_are_inside(self):
        result = self.m2.lookup(LAT + 0.6, LON)  # about 67 km from the field centroids
        self.assertEqual(result["match"]["level"], "neighbourhood")
        self.assertEqual(result["match"]["radius_km"], 120.0)
        self.assertIn("widened to 120 km", result["warnings"][0])
        with tempfile.TemporaryDirectory() as other:
            write_m2(Path(other), fields=8)  # few fields: still a neighbourhood, but indicative
            few = M2Evidence(other).lookup(LAT + 0.1, LON)
        self.assertEqual(few["match"]["level"], "neighbourhood")
        summary = few["neighbourhood"]["corn"]["T1"]["ndwi_jul_aug"]
        self.assertIn("indicative", summary["note"])

    def test_unusable_field_estimate_is_only_indicative(self):
        result = self.m2.lookup(LAT + 0.001, LON)  # the field whose estimate has no evidence
        self.assertEqual(result["match"]["csbid"], "1001")
        what_if = result["field"]["corn"]["T1"]["ndwi_jul_aug"]
        self.assertFalse(what_if["usable"])
        self.assertNotIn("effect", what_if)
        self.assertIn("indicative", what_if)
        self.assertTrue(any("not a finding" in line for line in result["summary"]))

    def test_lower_evidence_tier_has_no_drought_specific_number(self):
        table = pd.read_csv(self.root / "effects.csv")
        table["evidence_tier"] = "pooled"
        table["confidence"] = "low"
        table["headline_basis"] = "effect over all seasons"
        table["headline_effect"] = -0.02
        table["headline_lo"] = -0.04
        table["headline_hi"] = 0.0
        table["gamma"] = None
        table.to_csv(self.root / "effects.csv", index=False)
        result = M2Evidence(self.root).lookup(LAT, LON)
        region = result["region"]["corn"]["T1"]
        self.assertEqual(region["evidence_tier"], "pooled")
        self.assertEqual(region["confidence"], "low")
        self.assertIsNone(region["headline"]["gamma"])
        self.assertAlmostEqual(region["headline"]["headline_effect"], -0.02)
        self.assertTrue(any("Not a drought-specific effect" in line for line in result["summary"]))
        self.assertTrue(any("evidence tier 'pooled'" in line for line in result["warnings"]))

    def test_older_effects_table_is_read_as_full_tier(self):
        region = self.m2.lookup(LAT, LON)["region"]["corn"]
        self.assertEqual(region["T1"]["evidence_tier"], "full")
        self.assertAlmostEqual(region["T1"]["headline"]["headline_effect"], -0.06)

    def test_missing_output_raises(self):
        with self.assertRaises(FileNotFoundError):
            M2Evidence(self.root / "absent").lookup(LAT, LON)

    def test_output_is_json_safe(self):
        import json

        json.dumps(self.m2.lookup(LAT, LON), allow_nan=False)


class M2EndpointTests(unittest.TestCase):
    def setUp(self):
        self.output = tempfile.TemporaryDirectory()
        self.addCleanup(self.output.cleanup)
        write_m2(Path(self.output.name))
        directory, self.app = isolated_app(m2_out=Path(self.output.name))
        self.addCleanup(directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.addCleanup(self.app.state.soil_assessments.close)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.assertEqual(register(self.client).status_code, 201)
        self.other = TestClient(self.app)
        self.addCleanup(self.other.close)
        self.assertEqual(register(self.other, "other@example.com").status_code, 201)

    def get(self, field):
        return self.client.get(f"/api/v1/fields/{field['id']}/m2-insights")

    def test_uses_saved_coordinates_and_the_owner_only(self):
        field = create_field(self.client, geometry={"type": "Point", "coordinates": [LON, LAT]})
        self.assertEqual(
            self.other.get(f"/api/v1/fields/{field['id']}/m2-insights").status_code, 404
        )
        response = self.get(field)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["query"], {"lat": LAT, "lng": LON})
        self.assertEqual(result["match"]["level"], "field")
        self.assertEqual(result["region"]["corn"]["T1"]["verdict"], SUPPORTED)
        self.assertTrue(result["field"]["corn"]["T1"]["ndwi_jul_aug"]["usable"])

        outside = create_field(self.client, geometry={"type": "Point", "coordinates": [30.5, 50.4]})
        response = self.get(outside)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], "outside_coverage")

    def test_missing_output_is_service_unavailable(self):
        self.app.state.m2_evidence = M2Evidence(Path(self.output.name) / "absent")
        field = create_field(self.client, geometry={"type": "Point", "coordinates": [LON, LAT]})
        self.assertEqual(self.get(field).status_code, 503)


if __name__ == "__main__":
    unittest.main()
