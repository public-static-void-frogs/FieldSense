import unittest
from datetime import date
from types import SimpleNamespace

from app.services import crop_production, crop_revenue
from app.services.assistant_tools import ChatContext, default_registry
from app.services.nass import Nass, NassUnavailable, mass

COUNTY = {"state": "19", "county": "169", "fips": "19169", "name": "Story", "stateCode": "IA"}


class FakeNass(Nass):
    """Quick Stats, FCC and CropScape answered from memory."""

    def __init__(self, api_key="key", county=COUNTY, cdl=(1, "Corn")):
        super().__init__(api_key)
        self._county, self._cdl = county, cdl
        self.calls = []

    def county(self, lat, lng):
        return self._county

    def cdl_class(self, year, lat, lng):
        return self._cdl

    def query(self, **params):
        self.require_key()
        self.calls.append(params)
        desc, level = params["short_desc"], params["agg_level_desc"]
        if "YIELD" in desc and level == "COUNTY":
            if "year" in params:
                return [] if params["year"] == 2030 else [row(params, 200.0)]
            return [row(params, 150.0 + 3 * i, 2010 + i) for i in range(12)]
        if "YIELD" in desc and level == "STATE":
            return [row(params, 190.0)] if "year" in params else []
        if "PRODUCTION" in desc:
            return [row(params, 1_000_000.0)]
        if "ACRES" in desc:
            return [row(params, 5000.0)]
        if "PRICE" in desc and level == "STATE":
            return [
                price(2018 + i, month, 3.5 + 0.1 * i)
                for i in range(7)
                for month in ("OCT", "NOV", "DEC")
            ]
        return []


def row(params, value, year=None):
    return {
        "Value": f"{value:,}",
        "year": str(year or params.get("year", 2023)),
        "reference_period_desc": "YEAR",
        "state_fips_code": "19",
        "county_code": "169",
        "county_name": "STORY",
    }


def price(year, month, value):
    return {"Value": str(value), "year": str(year), "reference_period_desc": month}


class CropProductionTest(unittest.TestCase):
    def test_field_production_uses_county_yield_and_area(self):
        result = crop_production.field_production(FakeNass(), 2023, 42.0, -93.6, area_ha=10)
        self.assertEqual(result["crop"], "corn")
        self.assertEqual(result["yieldUsed"], {
            "value": 200.0, "unit": "bu/acre", "level": "county", "source": "NASS survey yield",
        })  # fmt: skip
        self.assertAlmostEqual(result["production"]["amount"], 200 * 10 * 2.471054, delta=0.1)
        self.assertEqual(result["production"]["unit"], "bu")
        self.assertTrue(any("county-average" in note for note in result["notes"]))

    def test_defaults_to_one_acre_and_falls_back_to_state_yield(self):
        result = crop_production.field_production(FakeNass(), 2030, 42, -93, crop="soy")
        self.assertEqual((result["crop"], result["cropSource"]), ("soybeans", "user"))
        self.assertTrue(result["areaDefaulted"])
        self.assertEqual(result["areaAcres"], 1.0)
        self.assertEqual(result["yieldUsed"]["level"], "state")

    def test_unsupported_crop_pixel_asks_for_a_crop(self):
        nass = FakeNass(cdl=(121, "Developed/Open Space"))
        with self.assertRaisesRegex(NassUnavailable, "name the crop"):
            crop_production.field_production(nass, 2023, 42, -93)
        nass.cdl_class = lambda year, lat, lng: (
            (5, "Soybeans") if (round(lat, 4), round(lng, 4)) != (42, -93) else (121, "Developed")
        )
        result = crop_production.field_production(nass, 2023, 42, -93, snap_m=100)
        self.assertEqual(result["crop"], "soybeans")
        self.assertIn("m from the point", result["cropSource"])

    def test_outside_the_us_and_missing_key(self):
        with self.assertRaisesRegex(NassUnavailable, "U.S."):
            crop_production.field_production(FakeNass(county=None), 2023, 50, 10, crop="corn")
        with self.assertRaisesRegex(NassUnavailable, "NASS_API_KEY"):
            crop_production.field_production(FakeNass(api_key=""), 2023, 42, -93, crop="corn")
        with self.assertRaisesRegex(ValueError, "Unknown crop"):
            crop_production.field_production(FakeNass(), 2023, 42, -93, crop="potatoes")

    def test_region_totals(self):
        result = crop_production.region_production(
            FakeNass(), 2023, counties=["19169"], crops=["corn"]
        )
        (corn,) = result["crops"]
        self.assertEqual(corn["counties"], 1)
        self.assertEqual(corn["countiesByBasis"]["reported"], 1)
        self.assertEqual(corn["totalBest"]["amount"], 1_000_000.0)
        self.assertEqual(corn["harvestedAcres"], 5000.0)
        with self.assertRaises(ValueError):
            crop_production.region_production(FakeNass(), 2023)

    def test_mass_conversion(self):
        self.assertEqual(mass(1000, "corn")["shortTons"], 28.0)
        self.assertEqual(mass(10, "alfalfa hay")["shortTons"], 10.0)
        self.assertIsNone(mass(None, "corn"))


class CropRevenueTest(unittest.TestCase):
    def forecast(self, nass=None, **extra):
        return crop_revenue.forecast(
            nass or FakeNass(),
            42.0,
            -93.6,
            {"2027-04-25": "corn", "2028-05-05": "soy"},
            today=date(2026, 11, 15),
            **extra,
        )

    def test_gross_revenue_scenarios_and_totals(self):
        result = self.forecast(area_ha=10)
        self.assertEqual([c["status"] for c in result["crops"]], ["ok", "ok"])
        corn = result["crops"][0]
        self.assertEqual(corn["yieldPerAcre"]["method"], "trend")
        self.assertLessEqual(corn["grossRevenue"]["low"], corn["grossRevenue"]["base"])
        self.assertLessEqual(corn["grossRevenue"]["base"], corn["grossRevenue"]["high"])
        total = sum(c["grossRevenue"]["base"] for c in result["crops"])
        self.assertAlmostEqual(result["totalGrossRevenue"]["base"], total, delta=0.05)
        self.assertEqual(result["location"]["state"], "IA")

    def test_roi_total_and_per_year_with_overrides(self):
        result = self.forecast(
            area_ha=10,
            investment={"2027": 20000, "2028": 10000},
            price_override={"corn": 5.0},
            yield_override={"corn": 200},
        )
        corn = result["crops"][0]
        self.assertEqual(corn["price"]["source"], "user override")
        self.assertAlmostEqual(corn["grossRevenuePerAcre"]["base"], 1000.0)
        self.assertEqual(result["roi"]["investmentTotal"], 30000.0)
        years = {row["year"]: row for row in result["roi"]["perYear"]}
        self.assertEqual(set(years), {2027, 2028})
        self.assertAlmostEqual(years[2027]["grossRevenue"]["base"], 1000 * 10 * 2.471054, delta=0.1)

    def test_never_raises_and_reports_warnings(self):
        result = crop_revenue.forecast(FakeNass(api_key=""), 42, -93, {"2027-04-25": "corn"})
        self.assertIsNone(result["totalGrossRevenue"])
        self.assertTrue(any("NASS_API_KEY" in w for w in result["warnings"]))
        result = self.forecast(investment="lots")
        self.assertNotIn("roi", result)
        self.assertTrue(any("Investment" in w for w in result["warnings"]))
        bad = crop_revenue.forecast(
            FakeNass(), 42, -93, {"2027-13-45": "corn", "2028-04-15": "potatoes"}
        )
        self.assertEqual(bad["crops"], [])
        self.assertTrue(any("No valid crop" in w for w in bad["warnings"]))

    def test_overlapping_plan_and_missing_series_warn(self):
        class NoPrices(FakeNass):
            def query(self, **params):
                return [] if "PRICE" in params["short_desc"] else super().query(**params)

        result = crop_revenue.forecast(
            NoPrices(),
            42,
            -93,
            {"2027-04-25": "corn", "2027-06-01": "soybeans"},
            today=date(2026, 11, 15),
        )
        self.assertEqual({c["status"] for c in result["crops"]}, {"no estimate"})
        self.assertIsNone(result["totalGrossRevenue"])
        self.assertTrue(any("overlaps" in w for w in result["warnings"]))


class CropToolsTest(unittest.TestCase):
    def ctx(self, field=True, nass=None):
        state = SimpleNamespace(nass=nass or FakeNass())
        field = (
            {"id": "f", "name": "North", "area": 10.0, "geometry": {"coordinates": [-93.6, 42.0]}}
            if field
            else None
        )
        return ChatContext(state, SimpleNamespace(), field, "en")

    def call(self, name, ctx, **args):
        return default_registry().call(name, ctx, args)

    def test_production_for_the_field_and_for_a_region(self):
        result = self.call("get_crop_production", self.ctx(), year=2023)
        self.assertEqual((result["status"], result["crop"]), ("ready", "corn"))
        self.assertEqual(result["areaHa"], 10.0)
        region = self.call(
            "get_crop_production", self.ctx(False), year=2023, state="19", crop="corn"
        )
        self.assertEqual(region["status"], "ready")
        self.assertEqual(region["crops"][0]["crop"], "corn")

    def test_production_errors_are_results(self):
        self.assertEqual(
            self.call("get_crop_production", self.ctx(False), year=2023)["status"], "unavailable"
        )
        self.assertEqual(self.call("get_crop_production", self.ctx())["status"], "unavailable")
        result = self.call("get_crop_production", self.ctx(), year=2023, crop="potatoes")
        self.assertIn("Unknown crop", result["reason"])
        result = self.call("get_crop_production", self.ctx(nass=FakeNass(api_key="")), year=2023)
        self.assertIn("NASS_API_KEY", result["reason"])

    def test_revenue_plan_investment_and_prices(self):
        result = self.call(
            "get_crop_revenue",
            self.ctx(),
            plan=[{"startDate": "2027-04-25", "crop": "corn"}],
            investment=[{"year": 2027, "amount": 20000}],
            prices=[{"crop": "corn", "value": 5}],
            yields=[{"crop": "corn", "value": 200}],
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["roi"]["perYear"][0]["year"], 2027)
        self.assertEqual(result["crops"][0]["price"]["source"], "user override")

    def test_revenue_needs_a_field_and_a_plan(self):
        plan = [{"startDate": "2027-04-25", "crop": "corn"}]
        self.assertEqual(
            self.call("get_crop_revenue", self.ctx(False), plan=plan)["status"], "unavailable"
        )
        self.assertEqual(self.call("get_crop_revenue", self.ctx())["status"], "unavailable")
        result = self.call("get_crop_revenue", self.ctx(nass=FakeNass(api_key="")), plan=plan)
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
