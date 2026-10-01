import sys
import types
from datetime import datetime, timezone

import numpy as np
import pytest
from PIL import Image

from src.detector import HumanDetector
from src.store import MotionEvent


EXPECTED_OUTPUTS = [
    "detection_boxes",
    "detection_classes",
    "detection_scores",
    "num_detections",
]


def _fake_onnxruntime(detections):
    """Fake onnxruntime returning the given (class_id, score) detections.

    Mirrors the real SSD MobileNet signature: a uint8 NHWC input and four
    named outputs, with COCO class ids 1-based (1 = person).
    """
    classes = np.array([[c for c, _ in detections]], dtype=np.float32)
    scores = np.array([[s for _, s in detections]], dtype=np.float32)
    boxes = np.zeros((1, len(detections), 4), dtype=np.float32)
    num = np.array([len(detections)], dtype=np.float32)
    by_name = {
        "detection_boxes": boxes,
        "detection_classes": classes,
        "detection_scores": scores,
        "num_detections": num,
    }

    class FakeInput:
        name = "inputs"

    class FakeSession:
        def __init__(self, path, providers=None):
            self.path = path
            self.providers = providers

        def get_inputs(self):
            return [FakeInput()]

        def run(self, output_names, feed):
            # Outputs must be requested by name — the graph's positional order
            # is not boxes/classes/scores/num.
            assert output_names == EXPECTED_OUTPUTS, output_names
            tensor = feed["inputs"]
            assert tensor.dtype == np.uint8, tensor.dtype
            assert tensor.ndim == 4 and tensor.shape[0] == 1, tensor.shape
            assert tensor.shape[3] == 3, tensor.shape
            assert max(tensor.shape[1:3]) <= 1920, tensor.shape
            return [by_name[n] for n in output_names]

    mod = types.ModuleType("onnxruntime")
    mod.InferenceSession = FakeSession
    return mod


def _persons(*scores):
    return [(1, s) for s in scores]


@pytest.fixture
def jpg(tmp_path):
    path = tmp_path / "snap.jpg"
    Image.new("RGB", (1280, 720), (40, 40, 40)).save(path)
    return str(path)


@pytest.fixture
def model(tmp_path):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"not-a-real-model")
    return str(path)


def _install(monkeypatch, scores):
    """Install a fake runtime reporting `scores` as person detections."""
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_onnxruntime(_persons(*scores)))


def _install_raw(monkeypatch, detections):
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_onnxruntime(detections))


def _event(path, ts=None):
    return MotionEvent(
        timestamp=ts or datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc),
        camera_name="Front",
        camera_entity="camera.front",
        screenshot_path=path,
    )


def test_detect_reports_person_above_threshold(monkeypatch, jpg, model):
    _install(monkeypatch, [0.01, 0.87, 0.2])
    detector = HumanDetector(model, confidence=0.4)

    assert detector.detect(jpg) == (True, pytest.approx(0.87, abs=1e-6))
    assert detector.available


def test_detect_reports_clear_below_threshold(monkeypatch, jpg, model):
    _install(monkeypatch, [0.01, 0.39, 0.2])
    detector = HumanDetector(model, confidence=0.4)

    present, confidence = detector.detect(jpg)
    assert present is False
    assert confidence == pytest.approx(0.39, abs=1e-6)


def test_detect_threshold_is_inclusive(monkeypatch, jpg, model):
    _install(monkeypatch, [0.4])

    present, _ = HumanDetector(model, confidence=0.4).detect(jpg)
    assert present is True


def test_detect_takes_peak_score_across_detections(monkeypatch, jpg, model):
    """One confident person among many weak detections must still register."""
    _install(monkeypatch, [0.01, 0.02, 0.95, 0.03])

    present, confidence = HumanDetector(model, confidence=0.4).detect(jpg)
    assert present is True
    assert confidence == pytest.approx(0.95, abs=1e-6)


def test_detect_returns_none_for_missing_file(monkeypatch, tmp_path, model):
    _install(monkeypatch, [0.9])

    assert HumanDetector(model).detect(str(tmp_path / "gone.jpg")) is None


def test_detect_returns_none_when_inference_raises(monkeypatch, jpg, model):
    mod = _fake_onnxruntime(_persons(0.9))

    def boom(self, output_names, feed):
        raise RuntimeError("corrupt graph")

    mod.InferenceSession.run = boom
    monkeypatch.setitem(sys.modules, "onnxruntime", mod)

    assert HumanDetector(model).detect(jpg) is None


def test_unavailable_when_onnxruntime_missing(monkeypatch, jpg, model):
    """32-bit architectures have no onnxruntime wheel — degrade, never crash."""
    # A None entry in sys.modules makes `import onnxruntime` raise ImportError.
    monkeypatch.setitem(sys.modules, "onnxruntime", None)

    detector = HumanDetector(model)
    assert detector.detect(jpg) is None
    assert detector.available is False


def test_unavailable_when_model_file_missing(monkeypatch, jpg, tmp_path):
    _install(monkeypatch, [0.9])

    detector = HumanDetector(str(tmp_path / "absent.onnx"))
    assert detector.detect(jpg) is None
    assert detector.available is False


async def test_analyze_is_noop_when_unavailable(monkeypatch, jpg, tmp_path):
    _install(monkeypatch, [0.9])
    events = [_event(jpg)]

    count = await HumanDetector(str(tmp_path / "absent.onnx")).analyze(events)

    assert count == 0
    assert events[0].human_detected is None
    assert events[0].human_confidence is None


async def test_analyze_fills_verdicts_and_counts(monkeypatch, tmp_path, model):
    _install(monkeypatch, [0.8])
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    for p in (a, b):
        Image.new("RGB", (640, 480), (10, 10, 10)).save(p)
    events = [_event(str(a)), _event(str(b))]

    count = await HumanDetector(model, confidence=0.4).analyze(events)

    assert count == 2
    assert all(e.human_detected is True for e in events)
    assert all(e.human_confidence == pytest.approx(0.8, abs=1e-6) for e in events)


async def test_analyze_skips_events_without_snapshot(monkeypatch, jpg, model):
    _install(monkeypatch, [0.9])
    events = [_event(None), _event(jpg)]

    count = await HumanDetector(model).analyze(events)

    assert count == 1
    assert events[0].human_detected is None
    assert events[1].human_detected is True


async def test_analyze_survives_one_unreadable_frame(monkeypatch, tmp_path, model):
    """A single corrupt JPEG must not cost us the whole report."""
    _install(monkeypatch, [0.9])
    good = tmp_path / "good.jpg"
    Image.new("RGB", (320, 240), (5, 5, 5)).save(good)
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"this is not a jpeg")
    events = [_event(str(bad)), _event(str(good))]

    count = await HumanDetector(model).analyze(events)

    assert count == 1
    assert events[0].human_detected is None  # unreadable stays "not analysed"
    assert events[1].human_detected is True


async def test_analyze_marks_clear_frames_false_not_none(monkeypatch, jpg, model):
    """False (looked, nobody there) must be distinguishable from None (never looked)."""
    _install(monkeypatch, [0.05])
    events = [_event(jpg)]

    count = await HumanDetector(model, confidence=0.4).analyze(events)

    assert count == 0
    assert events[0].human_detected is False


def test_detect_ignores_non_person_classes(monkeypatch, jpg, model):
    """A confident cat or car must not be reported as a human."""
    _install_raw(monkeypatch, [(17, 0.97), (3, 0.93), (1, 0.08)])

    present, confidence = HumanDetector(model, confidence=0.4).detect(jpg)
    assert present is False
    assert confidence == pytest.approx(0.08, abs=1e-6)


def test_detect_handles_frame_with_no_detections(monkeypatch, jpg, model):
    _install_raw(monkeypatch, [])

    assert HumanDetector(model, confidence=0.4).detect(jpg) == (False, 0.0)


def test_detect_handles_frame_with_only_non_person_detections(monkeypatch, jpg, model):
    _install_raw(monkeypatch, [(3, 0.99)])

    assert HumanDetector(model, confidence=0.4).detect(jpg) == (False, 0.0)


def test_detect_downscales_oversized_frames(monkeypatch, tmp_path, model):
    """4K snapshots are scaled down — the fake session asserts the 1920 cap."""
    _install(monkeypatch, [0.9])
    big = tmp_path / "4k.jpg"
    Image.new("RGB", (3840, 2160), (20, 20, 20)).save(big)

    assert HumanDetector(model).detect(str(big)) == (True, pytest.approx(0.9, abs=1e-6))


def test_detect_passes_small_frames_through_unscaled(monkeypatch, tmp_path, model):
    _install(monkeypatch, [0.9])
    small = tmp_path / "small.jpg"
    Image.new("RGB", (640, 480), (20, 20, 20)).save(small)

    captured = {}
    real_preprocess = HumanDetector._preprocess

    def spy(self, path):
        arr = real_preprocess(self, path)
        captured["shape"] = arr.shape
        return arr

    monkeypatch.setattr(HumanDetector, "_preprocess", spy)
    HumanDetector(model).detect(str(small))

    assert captured["shape"] == (1, 480, 640, 3)
