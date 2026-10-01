"""Human presence detection in saved snapshots.

Runs SSD MobileNet V1 (COCO) as ONNX, locally — no network, no API keys. The
runtime is optional: `onnxruntime` publishes no wheels for the armhf/armv7/i386
architectures this add-on declares, so a missing import degrades to "detection
unavailable" rather than breaking the add-on.
"""
from __future__ import annotations

import asyncio
import logging
import os

from src.store import MotionEvent

logger = logging.getLogger(__name__)

# COCO class ids in the TensorFlow Object Detection API are 1-based; 1 = person.
_PERSON_CLASS = 1
# The model rescales internally to 300x300, so feeding more than this buys no
# accuracy (measured flat from 640px to 4K) and only costs CPU and memory.
_MAX_EDGE = 1920
_OUTPUTS = ("detection_boxes", "detection_classes", "detection_scores", "num_detections")


class HumanDetector:
    """Classifies snapshots as containing a person or not.

    `available` is False when the ONNX runtime or the model file is missing;
    in that state every call is a logged no-op and reports render unchanged.
    """

    def __init__(self, model_path: str, confidence: float = 0.4):
        self._model_path = model_path
        self._confidence = confidence
        self._session = None
        self._np = None
        self._image = None
        self._input_name: str | None = None
        self._loaded = False
        self.available = False

    def _load(self) -> None:
        """Import dependencies and open the model. Safe to call repeatedly."""
        if self._loaded:
            return
        self._loaded = True

        try:
            import numpy
            import onnxruntime
            from PIL import Image
        except ImportError as exc:
            logger.warning(
                "Human detection disabled — missing dependency (%s). "
                "onnxruntime has no wheels for 32-bit architectures.", exc
            )
            return

        if not os.path.exists(self._model_path):
            logger.warning(
                "Human detection disabled — model not found at %s", self._model_path
            )
            return

        try:
            self._session = onnxruntime.InferenceSession(
                self._model_path, providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
        except Exception as exc:
            logger.warning("Human detection disabled — could not load model: %s", exc)
            return

        self._np = numpy
        self._image = Image
        self.available = True
        logger.info("Human detection ready (model=%s)", self._model_path)

    def _preprocess(self, path: str):
        """Return the image as a uint8 NHWC batch, as the model expects.

        No normalisation or letterboxing: this graph takes raw uint8 pixels and
        does its own resize. Oversized frames are scaled down to bound CPU and
        memory on 4K cameras.
        """
        with self._image.open(path) as img:
            img = img.convert("RGB")
            longest = max(img.size)
            if longest > _MAX_EDGE:
                scale = _MAX_EDGE / longest
                img = img.resize(
                    (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                    self._image.BILINEAR,
                )
            return self._np.asarray(img, dtype=self._np.uint8)[None, ...]

    def detect(self, path: str) -> tuple[bool, float] | None:
        """Return (human_present, confidence) for one snapshot, or None on failure.

        The verdict is the highest score among detections classified as person.
        """
        self._load()
        if not self.available:
            return None
        if not os.path.exists(path):
            logger.warning("Cannot analyse missing snapshot: %s", path)
            return None

        try:
            tensor = self._preprocess(path)
            _, classes, scores, _ = self._session.run(
                list(_OUTPUTS), {self._input_name: tensor}
            )
            person_scores = scores[0][classes[0] == _PERSON_CLASS]
            best = float(person_scores.max()) if person_scores.size else 0.0
        except Exception as exc:
            logger.warning("Detection failed for %s: %s", path, exc)
            return None

        return best >= self._confidence, best

    async def analyze(self, events: list[MotionEvent]) -> int:
        """Fill detection verdicts on `events` in place; return the human count.

        Inference is CPU-bound and runs in a thread so the aiohttp and
        WebSocket loops keep serving while a session is being analysed.
        """
        self._load()
        if not self.available:
            return 0

        loop = asyncio.get_running_loop()
        count = 0
        for event in events:
            if not event.screenshot_path:
                continue
            try:
                result = await loop.run_in_executor(
                    None, self.detect, event.screenshot_path
                )
            except Exception as exc:
                # One unreadable frame must never cost us the whole report.
                logger.warning(
                    "Skipping detection for %s: %s", event.screenshot_path, exc
                )
                continue
            if result is None:
                continue
            event.human_detected, event.human_confidence = result
            if event.human_detected:
                count += 1

        logger.info("Analysed %d snapshot(s) — humans in %d", len(events), count)
        return count
