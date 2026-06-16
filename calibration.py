"""
calibration.py
─────────────────────────────────────────────
Personalized EAR threshold calibration.

Collects EAR samples for CALIBRATION_DURATION_SEC seconds while the driver
keeps eyes open normally, then sets threshold = mean_ear * EAR_THRESHOLD_FACTOR.
Results are persisted in JSON so the value survives restarts.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import config

_log = logging.getLogger("Calibration")


class CalibrationEngine:
    """
    Collects EAR samples in a background thread and computes a personalised
    threshold when done.

    Usage
    ─────
    engine = CalibrationEngine(on_complete=my_callback)
    engine.start()
    # feed samples from the detector loop:
    engine.add_sample(ear_value)
    # callback fires automatically when duration elapses.
    """

    def __init__(
        self,
        on_complete: Optional[Callable[[float], None]] = None,
        on_tick: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._on_complete   = on_complete
        self._on_tick       = on_tick          # called every second with secs_left
        self._samples: List[float] = []
        self._lock          = threading.Lock()
        self._running       = False
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0

    # ── state ────────────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time if self._running else 0.0

    @property
    def progress(self) -> float:
        """0.0 → 1.0"""
        if not self._running:
            return 0.0
        return min(self.elapsed / config.CALIBRATION_DURATION_SEC, 1.0)

    # ── control ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._samples.clear()
        self._running   = True
        self._start_time = time.time()
        self._thread = threading.Thread(
            target=self._timer_loop, daemon=True, name="CalibThread"
        )
        self._thread.start()
        _log.info("Calibration started — keep eyes open for %d s",
                  config.CALIBRATION_DURATION_SEC)

    def stop(self) -> None:
        self._running = False

    def add_sample(self, ear: float) -> None:
        """Call this from the detector loop while calibration is running."""
        if self._running and ear > 0.05:
            with self._lock:
                self._samples.append(ear)

    # ── internal ─────────────────────────────────────────────────────────
    def _timer_loop(self) -> None:
        duration = config.CALIBRATION_DURATION_SEC
        end_time = self._start_time + duration
        last_tick = int(duration)

        while self._running and time.time() < end_time:
            remaining = int(end_time - time.time())
            if remaining != last_tick:
                last_tick = remaining
                if self._on_tick:
                    self._on_tick(remaining)
            time.sleep(0.1)

        if self._running:            # natural completion (not cancelled)
            self._running = False
            threshold = self._compute_threshold()
            _log.info("Calibration complete — threshold=%.4f  samples=%d",
                      threshold, len(self._samples))
            save_calibration(threshold)
            if self._on_complete:
                self._on_complete(threshold)

    def _compute_threshold(self) -> float:
        with self._lock:
            samples = list(self._samples)
        if not samples:
            _log.warning("No samples collected — using default threshold")
            return config.DEFAULT_EAR_THRESHOLD
        mean_ear = sum(samples) / len(samples)
        threshold = mean_ear * config.EAR_THRESHOLD_FACTOR
        # clamp to sane range
        threshold = max(0.12, min(threshold, 0.30))
        _log.info("Mean EAR=%.4f  factor=%.2f  threshold=%.4f",
                  mean_ear, config.EAR_THRESHOLD_FACTOR, threshold)
        return threshold


# ── persistence helpers ────────────────────────────────────────────────────

def save_calibration(threshold: float) -> None:
    data = {
        "threshold": round(threshold, 5),
        "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(config.CALIBRATION_FILE, "w") as f:
            json.dump(data, f, indent=2)
        _log.info("Calibration saved → %s", config.CALIBRATION_FILE)
    except OSError as exc:
        _log.error("Failed to save calibration: %s", exc)


def load_calibration() -> Optional[float]:
    """Load saved threshold; returns None if file absent or corrupt."""
    path = Path(config.CALIBRATION_FILE)
    if not path.exists():
        _log.info("No calibration file found — will use default EAR threshold")
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        threshold = float(data["threshold"])
        _log.info("Loaded calibration threshold=%.4f (from %s)",
                  threshold, data.get("calibrated_at", "?"))
        return threshold
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        _log.warning("Invalid calibration file: %s — using default", exc)
        return None


def delete_calibration() -> None:
    try:
        config.CALIBRATION_FILE.unlink(missing_ok=True)
        _log.info("Calibration data deleted")
    except OSError as exc:
        _log.error("Failed to delete calibration: %s", exc)
