"""Real SAM2 segmentation + trained TempCNN with on-demand Sentinel-2 inputs."""

import base64
import importlib.util
import io
import json
import logging
import os
from collections import Counter
from pathlib import Path
from threading import Lock
from time import monotonic
from uuid import uuid4

logger = logging.getLogger(__name__)
BACKEND = Path(__file__).resolve().parents[2]
ML = BACKEND.parent / "ml"


class AnalysisUnavailable(Exception):
    pass


class AnalysisCancelled(Exception):
    pass


class SectionAnalyzer:
    """One cached model pair per process; serialize the mutable SAM2 image predictor."""

    def __init__(self):
        self.lock = Lock()
        self.loaded = False

    def load(self):
        if self.loaded:
            return
        try:
            import rasterio  # noqa: F401
            import requests  # noqa: F401
            import torch
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
            self.device = os.getenv("ML_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
            checkpoint = Path(
                os.getenv("SAM2_CHECKPOINT", str(BACKEND / ".cache/models/sam2_hiera_tiny.pt"))
            )
            crop_weights = Path(
                os.getenv(
                    "TEMPCNN_CHECKPOINT",
                    str(ML / "field-crop-detection-model/weights/tempcnn_best.pth"),
                )
            )
            if not checkpoint.is_file() or not crop_weights.is_file():
                raise AnalysisUnavailable(
                    "ML weights missing. Follow backend/docs/section-analysis.md."
                )
            self.segmenter = SAM2ImagePredictor(
                build_sam2(
                    "configs/sam2/sam2_hiera_t.yaml",
                    str(checkpoint),
                    device=self.device,
                )
            )
            spec = importlib.util.spec_from_file_location(
                "fieldshift_tempcnn", ML / "field-crop-detection-model/model.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            weights = torch.load(crop_weights, map_location="cpu", weights_only=True)
            self.class_count = weights["fc.weight"].shape[0]
            self.crop_model = module.TempCNN(
                input_channels=3, num_classes=self.class_count, sequence_length=16
            )
            self.crop_model.load_state_dict(weights)
            self.crop_model.to(self.device).eval()
            mapping_path = Path(
                os.getenv(
                    "TEMPCNN_CLASSES_PATH",
                    str(ML / "field-crop-detection-model/weights/classes.json"),
                )
            )
            mapping = json.loads(mapping_path.read_text())
            if isinstance(mapping, dict):
                indices = [str(index) for index in range(self.class_count)]
                if set(mapping) == set(indices):
                    mapping = [
                        mapping[index].get("name") if isinstance(mapping[index], dict) else None
                        for index in indices
                    ]
                else:
                    if sorted(mapping.values()) != list(range(self.class_count)):
                        raise ValueError(
                            "Crop mapping must contain each zero-based class index exactly once"
                        )
                    mapping = sorted(mapping, key=mapping.get)
            if (
                not isinstance(mapping, list)
                or len(mapping) != self.class_count
                or not all(isinstance(label, str) and label for label in mapping)
            ):
                raise ValueError("Crop mapping must match trained output classes")
            self.labels = mapping
            self.label_source = "training_class_mapping"
            self.loaded = True
        except AnalysisUnavailable:
            raise
        except Exception as error:
            logger.exception("ML runtime initialization failed")
            raise AnalysisUnavailable(
                "ML runtime unavailable. Check backend model installation and configuration."
            ) from error

    def analyze(self, payload, cancelled=None, on_progress=None):
        # Avoid accumulating hundreds of full-resolution requests behind a busy model.
        if not self.lock.acquire(blocking=False):
            raise AnalysisUnavailable(
                "Analysis is busy. Please retry after the current section completes."
            )
        try:
            self.load()
            return self._analyze(payload, cancelled, on_progress)
        finally:
            if self.loaded:
                self.segmenter.reset_predictor()
            self.lock.release()

    def _analyze(self, payload, cancelled, on_progress):
        import numpy as np
        import torch
        from PIL import Image, UnidentifiedImageError

        from app.services.ml.crop_zones import merge_crop_zones
        from app.services.ml.geometry import ImageProjection, field_geometry
        from app.services.ml.greenness import SEQUENCE_LENGTH, greenness_sequences

        def check_cancelled():
            if cancelled is not None and cancelled.is_set():
                raise AnalysisCancelled()

        def report(stage, completed, total):
            if on_progress is not None:
                on_progress(dict(stage=stage, completed=completed, total=total))

        check_cancelled()
        request_id = uuid4()
        deadline = monotonic() + 240
        try:
            with Image.open(
                io.BytesIO(base64.b64decode(payload.image.dataUrl.split(",", 1)[1]))
            ) as image:
                if image.format != "PNG" or image.size != (
                    payload.image.width,
                    payload.image.height,
                ):
                    raise ValueError("Invalid map PNG dimensions")
                rgb = np.array(image.convert("RGB"), copy=True)
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("Map PNG could not be decoded") from error
        projection = ImageProjection(payload.image)
        pixels = [projection.pixel(point.coordinates) for point in payload.points]
        fields, skipped = [], []
        candidates = []
        report("segmentation", 0, len(pixels))
        with torch.inference_mode():
            self.segmenter.set_image(rgb)
            for start in range(0, len(pixels), 4):
                check_cancelled()
                chunk = pixels[start : start + 4]
                masks, scores, _ = self.segmenter.predict(
                    point_coords=np.array(chunk, dtype=np.float32)[:, None, :],
                    point_labels=np.ones((len(chunk), 1), dtype=np.int32),
                    multimask_output=False,
                )
                masks = masks.reshape(len(chunk), -1, payload.image.height, payload.image.width)[
                    :, 0
                ]
                for offset, mask in enumerate(masks):
                    index = start + offset
                    point = payload.points[index]
                    geometry = field_geometry(mask, pixels[index], projection)
                    if geometry is None:
                        skipped.append(
                            dict(pointId=point.id, reason="No valid mask containing the prompt")
                        )
                        continue
                    candidates.append(
                        (point, float(np.asarray(scores).reshape(-1)[offset]), geometry)
                    )

                report("segmentation", start + len(chunk), len(pixels))

        coordinates = Counter(point.coordinates for point, _, _ in candidates)
        target = len(candidates) * SEQUENCE_LENGTH
        finished = 0
        progress_lock = Lock()
        report("satellite", 0, target)

        def advance(coordinate, steps):
            nonlocal finished
            with progress_lock:
                finished += steps * coordinates[coordinate]
                report("satellite", finished, target)

        observations = greenness_sequences(coordinates, deadline, check_cancelled, advance)

        batch = []
        for point, score, geometry in candidates:
            result = observations[point.coordinates]
            if isinstance(result, str):
                skipped.append(dict(pointId=point.id, reason=result))
                continue
            dates, sequence = result
            batch.append((point, score, geometry, dates, sequence))

        report("classification", 0, len(batch))
        if batch:
            check_cancelled()
            with torch.inference_mode():
                sequences = torch.as_tensor(
                    np.stack([item[4] for item in batch]), dtype=torch.float32, device=self.device
                )
                probabilities = (
                    self.crop_model(sequences.transpose(1, 2)).softmax(dim=1).cpu().tolist()
                )
            for (point, score, geometry, dates, _), probs in zip(batch, probabilities):
                class_index = int(np.argmax(probs))
                fields.append(
                    dict(
                        id=uuid4(),
                        pointId=point.id,
                        crop=self.labels[class_index],
                        classIndex=class_index,
                        cropConfidence=probs[class_index],
                        cropProbabilities=probs,
                        segmentationConfidence=score,
                        cropObservationDates=dates,
                        **geometry,
                    )
                )
        return dict(
            requestId=request_id,
            mock=False,
            model="sam2-tiny+tempcnn",
            fields=fields,
            cropZones=merge_crop_zones(fields, projection),
            skippedPoints=skipped,
            provenance=dict(
                segmentationInputs="submitted_map_image_and_points",
                cropInputs="sentinel-2-l2a",
                syntheticCropInputs=False,
                sequenceShape=[16, 3],
                channels=["NDVI", "EVI", "NDWI"],
                cropLabelSource=self.label_source,
                classLabels=self.labels,
                device=self.device,
            ),
        )
