import tempfile
import unittest
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from support import create_field, field_input, isolated_app, register

from app.services.season_timing import SeasonTiming, local_calendar

CELL = "+42.0_-93.750"


def write_m3(root: Path, longitude: float, latitude: float):
    """The smallest M3 output folder m3_lookup.py accepts: one field, one cell, two crops."""
    (root / "chronoshift").mkdir()
    pd.DataFrame(
        [dict(CSBID="191825000000001", cell_id=CELL, county_fips="19015", lat=latitude,
              lon=longitude, state="19", aws_filled=200.0, awc_bin_mm=200.0, unit_id=f"{CELL}|200")]
    ).to_parquet(root / "field_index.parquet")  # fmt: skip

    def window(event, q10, q50, q90, period="now", scenario="obs", model="obs"):
        return dict(
            cell_id=CELL, q10=q10, q50=q50, q90=q90, method="trend", event=event, selected=True,
            date_q10="04-20", date_q50="05-02", date_q90="05-18", period=period,
            scenario=scenario, model=model, target_year=2026.0, n_years_fit=45.0,
            censored_share=0.0, calibrated=True,
        )  # fmt: skip

    events = ["last_spring_frost", "first_autumn_frost"] + [
        f"{crop}:{stage}"
        for crop in ("corn", "soybeans")
        for stage in ("first_ready", "sow", "flower", "mature")
    ]
    rows = [window(event, 110.0, 122.0, 138.0) for event in events]
    rows += [
        window("corn:sow", 105.0, sow, 130.0, "2040", "ssp585", model)
        for model, sow in (("A", 112.0), ("B", 118.0))
    ]
    pd.DataFrame(rows).to_parquet(root / "chronoshift" / "windows_cell.parquet")

    def risk(crop, heat, margin):
        return dict(
            cell_id=CELL, crop=crop, period="now", scenario="obs", model="obs", n_years=30,
            p_heat_overlap=heat, p_heat_lo80=heat - 0.1, p_heat_hi80=heat + 0.1,
            mean_heat_days_in_window=2.5, p_frost_before_maturity=0.05,
            adaptation_margin_days=margin, flag_vulnerable_m5=heat >= 0.4,
            workable_days_q10=14.0, workable_days_q50=21.0, workable_days_q90=30.0,
        )  # fmt: skip

    pd.DataFrame([risk("corn", 0.45, 10.0), risk("soybeans", 0.2, None)]).to_parquet(
        root / "chronoshift" / "risk_cell.parquet"
    )
    pd.DataFrame(
        [dict(cell_id=CELL, crop="corn", scenario="ssp585", p_heat_min=0.5, p_heat_max=0.8,
              p_heat_median=0.6, margin_min=0.0, margin_max=5.0, n_models=2)]
    ).to_parquet(root / "chronoshift" / "risk_2040_across_models.parquet")  # fmt: skip
    pd.DataFrame(
        [dict(crop="corn", stage="planted", year=2024, error_days=-8.0),
         dict(crop="corn", stage="planted", year=2025, error_days=6.0)]
    ).to_csv(root / "chronoshift" / "validation_nass.csv", index=False)  # fmt: skip


def write_fallow(root: Path):
    """The Fallow-Zero unit tables for the same soil unit: cover crop after corn costs water."""
    (root / "fallow_zero").mkdir()
    unit = f"{CELL}|200"

    def row(after, branch, shortfall, safe):
        return dict(
            unit_id=unit, cell_id=CELL, awc_mm=200.0, n_fields=1, after_crop=after,
            next_crop="soybeans" if after == "corn" else "corn", branch=branch, n_years=42,
            paw_sow_q10_mm=100.0, paw_sow_q50_mm=140.4, paw_sow_q90_mm=170.0,
            paw_sow_frac_q50=0.7, p_shortfall=shortfall, p_shortfall_lo80=shortfall / 2,
            p_shortfall_hi80=shortfall * 2, p_shortfall_ledger_wet=0.0, p_shortfall_ledger_dry=0.0,
            shortfall_threshold_mm=100.0, ledger_band_mm=11.5, safe_autumn_rain_mm=safe,
            autumn_rain_q10_mm=30.0, autumn_rain_q50_mm=60.2, autumn_rain_q90_mm=120.0,
            harvest_doy=293, residual_model=True,
        )  # fmt: skip

    pd.DataFrame(
        [row("corn", "bare", 0.05, None), row("corn", "cover", 0.4, 85.0),
         row("soybeans", "bare", 0.02, None), row("soybeans", "cover", 0.1, 0.0)]
    ).to_parquet(root / "fallow_zero" / "fallow_zero_units.parquet")  # fmt: skip
    pd.DataFrame(
        [dict(unit_id=unit, after_crop="corn", p_shortfall_bare=0.05, m9_cover_water_risk=0.4,
              delta_p_cover_minus_bare=0.35, flag_cover_ok_m9=False),
         dict(unit_id=unit, after_crop="soybeans", p_shortfall_bare=0.02, m9_cover_water_risk=0.1,
              delta_p_cover_minus_bare=0.08, flag_cover_ok_m9=True)]
    ).to_parquet(root / "fallow_zero" / "fallow_zero_m9_units.parquet")  # fmt: skip


def stored(longitude, latitude):
    return {"geometry": {"type": "Point", "coordinates": [longitude, latitude]}}


class SeasonTimingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        write_m3(self.root, -93.6, 42.0)
        self.timing = SeasonTiming(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def test_field_inside_coverage(self):
        block = self.timing.for_field(stored(-93.6, 42.0))
        self.assertEqual(block["matchLevel"], "field")
        self.assertEqual(block["lastSpringFrost"]["typical"], "05-02")
        corn = block["crops"]["corn"]
        self.assertEqual(
            corn["stages"]["sow"],
            dict(early="04-20", typical="05-02", late="05-18", method="trend", yearsFit=45,
                 censoredShare=0.0),
        )  # fmt: skip
        self.assertEqual(set(corn["stages"]), {"firstWorkable", "sow", "flower", "mature"})
        self.assertTrue(corn["heatAtFlowering"]["vulnerable"])
        self.assertEqual(corn["sowingDelayMarginDays"], 10.0)
        self.assertEqual(corn["dateErrorDays"], {"sow": 7.0})
        self.assertEqual(corn["outlook2040"][0]["scenario"], "ssp585")
        self.assertEqual(corn["outlook2040"][0]["heatMedian"], 0.6)
        self.assertEqual(corn["outlook2040"][0]["sowTypical"], "04-25")  # median of days 112, 118

    def test_no_safe_delay_stays_null(self):
        soybeans = self.timing.for_field(stored(-93.6, 42.0))["crops"]["soybeans"]
        self.assertIsNone(soybeans["sowingDelayMarginDays"])
        self.assertFalse(soybeans["heatAtFlowering"]["vulnerable"])
        self.assertEqual(soybeans["outlook2040"], [])

    def test_point_without_a_near_field_uses_the_weather_cell(self):
        self.assertEqual(self.timing.for_field(stored(-93.9, 42.1))["matchLevel"], "cell")

    def test_outside_coverage_or_without_data(self):
        self.assertIsNone(self.timing.for_field(stored(-100.0, 35.0)))
        self.assertIsNone(SeasonTiming("").for_field(stored(-93.6, 42.0)))
        self.assertIsNone(SeasonTiming(self.root / "absent").for_field(stored(-93.6, 42.0)))

    def test_water_at_sowing_with_and_without_a_cover_crop(self):
        self.assertEqual(self.timing.for_field(stored(-93.6, 42.0))["waterAtSowing"], {})
        write_fallow(self.root)
        water = SeasonTiming(self.root).for_field(stored(-93.6, 42.0))["waterAtSowing"]
        self.assertEqual(set(water), {"corn", "soybeans"})
        corn = water["corn"]
        self.assertEqual(corn["nextCrop"], "soybeans")
        self.assertEqual(corn["cover"], dict(shortfall=0.4, low80=0.2, high80=0.8, typicalMm=140.0))
        self.assertEqual(corn["bare"]["shortfall"], 0.05)
        self.assertFalse(corn["coverOk"])
        self.assertEqual(corn["safeAutumnRainMm"], 85.0)
        self.assertEqual((corn["years"], corn["thresholdMm"]), (42, 100.0))
        self.assertTrue(water["soybeans"]["coverOk"])
        self.assertEqual(water["soybeans"]["safeAutumnRainMm"], 0.0)

    def test_only_the_sowing_date_goes_to_the_engine(self):
        calendar = local_calendar(self.timing.for_field(stored(-93.6, 42.0)))
        self.assertEqual(set(calendar), {"corn", "soybeans"})
        self.assertEqual(calendar["corn"]["stages"], {"planted": 122})  # 2 May
        self.assertTrue(calendar["corn"]["source"])
        self.assertEqual(local_calendar(None), {})


class SeasonTimingApiTests(unittest.TestCase):
    def advice(self, **settings):
        directory, app = isolated_app(**settings)
        self.addCleanup(directory.cleanup)
        with TestClient(app) as client:
            register(client)
            field = create_field(client)
            response = client.get(f"/api/v1/fields/{field['id']}/rotation-advice")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_advice_carries_timing_and_keeps_the_ranking(self):
        longitude, latitude = field_input()["geometry"]["coordinates"]
        with tempfile.TemporaryDirectory() as root:
            write_m3(Path(root), longitude, latitude)
            with_timing = self.advice(m3_out=root)
        with tempfile.TemporaryDirectory() as empty:
            without = self.advice(m3_out=empty)
        self.assertIsNone(without["seasonTiming"])
        self.assertEqual(with_timing["seasonTiming"]["matchLevel"], "field")
        self.assertIn("corn", with_timing["seasonTiming"]["crops"])
        ranking = [(c["crop"], c["rank"], c["score"]) for c in without["candidates"]]
        self.assertEqual(
            ranking, [(c["crop"], c["rank"], c["score"]) for c in with_timing["candidates"]]
        )


if __name__ == "__main__":
    unittest.main()
