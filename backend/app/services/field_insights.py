"""Field insights that may outlive one HTTP request."""

import logging
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from time import monotonic, time

import httpx

from app.schemas.field_insights import SoilAssessment, SoilDepletion

logger = logging.getLogger(__name__)
SOIL_WORKERS = 2
SOIL_CACHE_SIZE = 128
SOIL_CACHE_SECONDS = 12 * 60 * 60
PARTIAL_CACHE_SECONDS = 15 * 60
SOIL_ANALYSIS_SECONDS = 100


class SoilAssessments:
    def __init__(self, nass_key: str):
        self.nass_key = nass_key
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=SOIL_WORKERS)
        self.pending: dict[tuple[float, float], Future] = {}
        self.cache: OrderedDict[tuple[float, float], tuple[float, SoilAssessment]] = OrderedDict()

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    def get(self, coordinates: tuple[float, float]) -> SoilDepletion:
        with self.lock:
            cached = self.cache.get(coordinates)
            if cached is not None:
                expires, assessment = cached
                if expires > monotonic():
                    self.cache.move_to_end(coordinates)
                    return SoilDepletion(
                        status="ready", coordinates=coordinates, assessment=assessment
                    )
                del self.cache[coordinates]
            if coordinates in self.pending:
                return SoilDepletion(status="pending", coordinates=coordinates)
            if len(self.pending) >= SOIL_WORKERS:
                return SoilDepletion(status="busy", coordinates=coordinates)
            job = self.pool.submit(self._analyze, coordinates)
            self.pending[coordinates] = job

        job.add_done_callback(lambda future: self._finish(coordinates, future))
        return SoilDepletion(status="pending", coordinates=coordinates)

    def _analyze(self, coordinates) -> SoilAssessment:
        from app.services.crop_history import identify
        from app.services.soil_depletion import depletion

        deadline = monotonic() + SOIL_ANALYSIS_SECONDS
        notes = []
        try:
            years = identify(*coordinates, int(time() // 3600))
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            years = []
            notes.append("crop_history_unavailable")
        crops = {item.year: item.crop.label for item in years if item.crop is not None}
        lon, lat = coordinates
        result = depletion(lat, lon, crops, nass_key=self.nass_key, deadline=deadline)
        if notes:
            result["notes"] = [
                note
                for note in result["notes"]
                if note not in ("rotation_insufficient_history", "greenness_insufficient_years")
            ] + notes
        return SoilAssessment.model_validate(result)

    def _finish(self, coordinates, future):
        with self.lock:
            self.pending.pop(coordinates, None)
            if future.cancelled():
                return
            try:
                assessment = future.result()
            except Exception:
                logger.exception("Soil depletion calculation failed")
                # Return a settled result instead of repeatedly scheduling the same failed job.
                assessment = SoilAssessment(
                    score=None,
                    level="unknown",
                    coverage=0,
                    components=dict(rotation=None, greenness=None, soil=None, county=None),
                    drivers=[],
                    metrics={},
                    notes=["analysis_unavailable"],
                )
            partial = any(note.endswith(("_unavailable", "_partial")) for note in assessment.notes)
            ttl = PARTIAL_CACHE_SECONDS if partial else SOIL_CACHE_SECONDS
            self.cache[coordinates] = (monotonic() + ttl, assessment)
            if len(self.cache) > SOIL_CACHE_SIZE:
                self.cache.popitem(last=False)
