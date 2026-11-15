"""A field outside the national sample: summaries of its weather cell, soil from the tables."""

import tempfile
import unittest
from pathlib import Path

import duckdb

from app.services.rotation_advice import RotationAdvice

UNITS = (
    "mukey,muname,iacornsr,aws0100wta,slope_r,drainagecl,hydgrp,nirrcapcl,nirrcapscl,tfact,"
    "sandtotal_r,claytotal_r,om_r,ph1to1h2o_r,caco3_r,kwfact\n"
    "411,Clarion loam,88,18.5,3,Well drained,B,2,e,5,38,22,4,6.4,0,.24\n"
)


def field(source_id: str, longitude: float = -93.6, latitude: float = 42.0) -> dict:
    return {
        "id": "f1",
        "area": 30.0,
        "sourceId": source_id,
        "stateFips": "19",
        "countyFips": "169",
        "geometry": {"coordinates": [longitude, latitude]},
    }


class CoverageTests(unittest.TestCase):
    def setUp(self):
        from rule_engine.cells import cell

        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        ix, iy = cell(-93.6, 42.0)
        duckdb.connect().execute(
            f"COPY (SELECT 'A' AS CSBID, '19169' AS county_fips, {ix} AS ix, {iy} AS iy) "
            f"TO '{root / 'summary_index.parquet'}' (FORMAT PARQUET)"
        )
        (root / "soil_units.csv").write_text(UNITS)
        (root / "soil_points.csv").write_text("CSBID,mukey\nA,411\nZ,999\n")
        (root / "soil_extra.csv").write_text("mukey,nccpi_corn\n411,0.82\n")
        self.advice = RotationAdvice(root, soil_lookup=False)

    def tearDown(self):
        self.dir.cleanup()

    def test_sampled_field_reads_itself_and_its_soil(self):
        record = self.advice.engine_field(field("A"))
        self.assertEqual(record["summaryTwin"]["source"], "own")
        soil = record["soil"]
        self.assertEqual(
            (soil["map_unit"], soil["aws_100cm_mm"], soil["nirr_class"], soil["nccpi_corn"]),
            ("Clarion loam", 185.0, 2, 0.82),
        )
        self.assertEqual(self.advice._reference_aws("19"), None)  # ids here carry no state code

    def test_other_field_reads_the_cell_but_not_its_soil(self):
        record = self.advice.engine_field(field("X"))
        self.assertEqual(record["sourceId"], "X")
        self.assertEqual(
            record["summaryTwin"],
            {"sourceId": "A", "countyFips": "19169", "source": "weather_cell", "distanceKm": 0.0},
        )
        self.assertNotIn("soil", record)

    def test_field_far_from_any_sampled_cell(self):
        record = self.advice.engine_field(field("X", longitude=-91.0))
        self.assertNotIn("summaryTwin", record)
