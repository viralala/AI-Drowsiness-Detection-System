"""
drowsiness_detector.py
─────────────────────────────────────────────
Core detection engine — runs on a dedicated background thread.

Responsibilities
────────────────
• Open / manage the webcam
• Run MediaPipe Face Mesh every frame
• Compute EAR, Mouth Aspect Ratio (MAR), head-pose angles
• Detect drowsiness / yawn / head-nod events
• Publish DetectionResult objects to listeners (UI, logger, alerts)
• Support calibration sample injection
• Honour thread-safe start / stop lifecycle
"""

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

import config
from calibration import CalibrationEngine, load_calibration

_log = logging.getLogger("Detector")

try:
    import mediapipe as mp
    _mp_face  = mp.solutions.face_mesh
    _mp_draw  = mp.solutions.drawing_utils
    _mp_style = mp.solutions.drawing_styles
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    _log.critical("MediaPipe NOT installed — detection disabled")


# ── result dataclass ──────────────────────────────────────────────────────

@dataclass
class DetectionResult:
    """Snapshot published each frame."""
    frame:          np.ndarray = field(default_factory=lambda: np.zeros((480,640,3), np.uint8))
    ear:            float  = 0.0
    mar:            float  = 0.0          # mouth aspect ratio
    fps:            float  = 0.0
    face_detected:  bool   = False
    drowsy:         bool   = False
    yawning:        bool   = False
    head_pitch:     float  = 0.0          # degrees
    head_yaw:       float  = 0.0
    eye_closed_sec: float  = 0.0          # continuous closed duration
    alert_active:   bool   = False
    driver_name:    str    = ""
    ear_threshold:  float  = config.DEFAULT_EAR_THRESHOLD
    cam_ok:         bool   = True


# ── EAR / MAR math ────────────────────────────────────────────────────────

def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def compute_ear(eye_pts: List[Tuple[float, float]]) -> float:
    """
    Eye Aspect Ratio from 6 landmark points:
      P1(0) — P6(5) : horizontal corners
      P2(1)-P3(2)   : upper vertical pair
      P4(3)-P5(4)   : lower vertical pair

    EAR = (||P2-P6|| + ||P3-P5||) / (2 * ||P1-P4||)
    """
    if len(eye_pts) < 6:
        return 0.0
    v1 = _dist(eye_pts[1], eye_pts[5])
    v2 = _dist(eye_pts[2], eye_pts[4])
    h  = _dist(eye_pts[0], eye_pts[3])
    if h < 1e-6:
        return 0.0
    return (v1 + v2) / (2.0 * h)


def compute_mar(top: Tuple, bottom: Tuple, left: Tuple, right: Tuple) -> float:
    """Mouth Aspect Ratio — vertical / horizontal mouth span."""
    v = _dist(top, bottom)
    h = _dist(left, right)
    if h < 1e-6:
        return 0.0
    return v / h


# ── head pose (simplified PnP-free) ──────────────────────────────────────

def compute_head_angles(
    landmarks, img_w: int, img_h: int
) -> Tuple[float, float]:
    """
    Estimate pitch (nod) and yaw (turn) in degrees using the
    nose-tip → chin vector and left→right ear vector.
    No camera intrinsics required — approximate but consistent.
    """
    def lm(idx: int) -> Tuple[float, float]:
        l = landmarks[idx]
        return l.x * img_w, l.y * img_h

    nose    = lm(config.NOSE_TIP)
    chin    = lm(config.CHIN)
    l_ear   = lm(config.LEFT_EAR_PT)
    r_ear   = lm(config.RIGHT_EAR_PT)

    # pitch: angle of nose→chin vector from vertical
    nc_vec   = (chin[0] - nose[0], chin[1] - nose[1])
    pitch    = math.degrees(math.atan2(nc_vec[0], nc_vec[1]))

    # yaw: asymmetry of nose along ear axis
    ear_mid  = ((l_ear[0] + r_ear[0]) / 2, (l_ear[1] + r_ear[1]) / 2)
    ear_span = _dist(l_ear, r_ear) + 1e-6
    yaw      = math.degrees(math.atan2(nose[0] - ear_mid[0], ear_span / 2))

    return pitch, yaw


# ── landmark pixel helper ─────────────────────────────────────────────────

def _lm_px(landmarks, idx: int, w: int, h: int) -> Tuple[float, float]:
    lm = landmarks[idx]
    return lm.x * w, lm.y * h


# ── main detector thread ──────────────────────────────────────────────────

class DrowsinessDetector:
    """
    Owns the camera + MediaPipe pipeline, runs on a daemon thread.

    Usage
    ─────
    det = DrowsinessDetector()
    det.add_listener(my_callback)   # fn(DetectionResult) called each frame
    det.start()
    ...
    det.stop()
    """

    def __init__(self) -> None:
        self._listeners: List[Callable[[DetectionResult], None]] = []
        self._lock = threading.Lock()

        # State
        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture]    = None

        # Thresholds (may be updated at runtime)
        self._ear_threshold = load_calibration() or config.DEFAULT_EAR_THRESHOLD
        self._driver_name   = ""

        # Consecutive-frame counters
        self._closed_frames = 0
        self._yawn_frames   = 0

        # Timing
        self._eye_closed_start: Optional[float] = None
        self._alert_active  = False

        # Calibration
        self._calib_engine: Optional[CalibrationEngine] = None

        # FPS tracking
        self._fps_times: List[float] = []
        self._fps       = 0.0

    # ── public API ────────────────────────────────────────────────────────
    def add_listener(self, fn: Callable[[DetectionResult], None]) -> None:
        with self._lock:
            self._listeners.append(fn)

    def set_driver(self, name: str) -> None:
        self._driver_name = name

    def set_threshold(self, threshold: float) -> None:
        self._ear_threshold = threshold
        _log.info("EAR threshold updated to %.4f", threshold)

    def get_threshold(self) -> float:
        return self._ear_threshold

    def start_calibration(
        self,
        on_complete: Optional[Callable[[float], None]] = None,
        on_tick: Optional[Callable[[int], None]] = None,
    ) -> None:
        def _complete(t: float) -> None:
            self._ear_threshold = t
            if on_complete:
                on_complete(t)

        self._calib_engine = CalibrationEngine(
            on_complete=_complete, on_tick=on_tick
        )
        self._calib_engine.start()

    def stop_calibration(self) -> None:
        if self._calib_engine:
            self._calib_engine.stop()
            self._calib_engine = None

    @property
    def is_calibrating(self) -> bool:
        return self._calib_engine is not None and self._calib_engine.is_running

    @property
    def calibration_progress(self) -> float:
        return self._calib_engine.progress if self._calib_engine else 0.0

    # ── lifecycle ─────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._run_loop, daemon=True, name="DetectorThread"
        )
        self._thread.start()
        _log.info("Detector started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        self._release_camera()
        _log.info("Detector stopped")

    # ── internal: camera ──────────────────────────────────────────────────
    def _open_camera(self) -> bool:
        cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW
                               if hasattr(cv2, "CAP_DSHOW") else 0)
        if not cap.isOpened():
            # Try without CAP_DSHOW flag
            cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if not cap.isOpened():
            _log.error("Cannot open camera index %d", config.CAMERA_INDEX)
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
        self._cap = cap
        _log.info("Camera opened (index=%d)", config.CAMERA_INDEX)
        return True

    def _release_camera(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    # ── internal: FPS ─────────────────────────────────────────────────────
    def _update_fps(self) -> float:
        now = time.monotonic()
        self._fps_times.append(now)
        cutoff = now - 1.0
        self._fps_times = [t for t in self._fps_times if t > cutoff]
        self._fps = float(len(self._fps_times))
        return self._fps

    # ── internal: draw helpers ────────────────────────────────────────────
    def _draw_eye_contour(
        self,
        frame: np.ndarray,
        pts: List[Tuple[float, float]],
        color: Tuple[int, int, int],
    ) -> None:
        poly = np.array([(int(x), int(y)) for x, y in pts], np.int32)
        cv2.polylines(frame, [poly], isClosed=True, color=color, thickness=1)

    def _draw_hud(
        self,
        frame: np.ndarray,
        result: DetectionResult,
    ) -> None:
        h, w = frame.shape[:2]
        # Semi-transparent top bar
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 34), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

        status_text = (
            f"EAR:{result.ear:.3f}  "
            f"MAR:{result.mar:.3f}  "
            f"FPS:{result.fps:.1f}  "
            f"THR:{result.ear_threshold:.3f}"
        )
        cv2.putText(frame, status_text, (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 212, 255), 1)

        if result.alert_active:
            # Flashing red border
            t = time.time()
            if int(t * 4) % 2 == 0:
                cv2.rectangle(frame, (0, 0), (w - 1, h - 1),
                              (0, 0, 220), 6)
            cv2.putText(frame, "! DROWSINESS ALERT !",
                        (w // 2 - 145, h // 2),
                        cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 255), 2)

        if result.yawning:
            cv2.putText(frame, "YAWN DETECTED",
                        (w // 2 - 90, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 180, 255), 2)

        if result.driver_name:
            cv2.putText(frame, f"Driver: {result.driver_name}",
                        (8, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 255, 100), 1)

        if self.is_calibrating:
            pct = int(self.calibration_progress * 100)
            cv2.putText(frame, f"CALIBRATING … {pct}%",
                        (8, h - 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
            cv2.rectangle(frame, (8, h - 20), (8 + int((w - 16) * self.calibration_progress), h - 10),
                          (255, 200, 0), -1)

    # ── internal: publish ─────────────────────────────────────────────────
    def _publish(self, result: DetectionResult) -> None:
        with self._lock:
            cbs = list(self._listeners)
        for fn in cbs:
            try:
                fn(result)
            except Exception as exc:               # noqa: BLE001
                _log.debug("Listener error: %s", exc)

    # ── main loop ─────────────────────────────────────────────────────────
    def _run_loop(self) -> None:
        if not MEDIAPIPE_AVAILABLE:
            _log.critical("MediaPipe unavailable — detector loop not running")
            return

        cam_ok = self._open_camera()
        if not cam_ok:
            # Publish error frames so UI doesn't hang
            while self._running:
                err_frame = np.zeros((config.CAMERA_HEIGHT, config.CAMERA_WIDTH, 3), np.uint8)
                cv2.putText(err_frame, "Camera not found", (60, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 200), 2)
                r = DetectionResult(frame=err_frame, cam_ok=False,
                                    ear_threshold=self._ear_threshold)
                self._publish(r)
                time.sleep(0.1)
            return

        with _mp_face.FaceMesh(
            max_num_faces=config.MAX_NUM_FACES,
            refine_landmarks=config.REFINE_LANDMARKS,
            min_detection_confidence=config.MIN_DETECTION_CONF,
            min_tracking_confidence=config.MIN_TRACKING_CONF,
        ) as face_mesh:

            while self._running:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    _log.warning("Frame capture failed")
                    time.sleep(0.05)
                    continue

                fps = self._update_fps()
                h, w = frame.shape[:2]
                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                mesh_result = face_mesh.process(rgb)
                rgb.flags.writeable = True

                result = DetectionResult(
                    fps=fps,
                    driver_name=self._driver_name,
                    ear_threshold=self._ear_threshold,
                )

                if mesh_result.multi_face_landmarks:
                    result.face_detected = True
                    face_lm = mesh_result.multi_face_landmarks[0].landmark

                    # ── EAR ──────────────────────────────────────────────
                    l_pts = [_lm_px(face_lm, i, w, h) for i in config.LEFT_EAR_POINTS]
                    r_pts = [_lm_px(face_lm, i, w, h) for i in config.RIGHT_EAR_POINTS]
                    l_ear = compute_ear(l_pts)
                    r_ear = compute_ear(r_pts)
                    ear   = (l_ear + r_ear) / 2.0
                    result.ear = round(ear, 4)

                    # ── draw eye contours ─────────────────────────────────
                    l_contour = [_lm_px(face_lm, i, w, h) for i in config.LEFT_EYE_INDICES]
                    r_contour = [_lm_px(face_lm, i, w, h) for i in config.RIGHT_EYE_INDICES]
                    eye_color = (0, 212, 255) if ear > self._ear_threshold else (0, 0, 255)
                    self._draw_eye_contour(frame, l_contour, eye_color)
                    self._draw_eye_contour(frame, r_contour, eye_color)

                    # ── MAR / Yawn ────────────────────────────────────────
                    top   = _lm_px(face_lm, config.UPPER_LIP,   w, h)
                    bot   = _lm_px(face_lm, config.LOWER_LIP,   w, h)
                    lm_   = _lm_px(face_lm, config.LEFT_MOUTH,  w, h)
                    rm_   = _lm_px(face_lm, config.RIGHT_MOUTH, w, h)
                    mar   = compute_mar(top, bot, lm_, rm_)
                    result.mar = round(mar, 4)

                    if mar > config.YAWN_THRESHOLD:
                        self._yawn_frames += 1
                    else:
                        self._yawn_frames = max(0, self._yawn_frames - 1)
                    result.yawning = self._yawn_frames >= config.YAWN_CONSEC_FRAMES

                    # ── Head pose ─────────────────────────────────────────
                    pitch, yaw = compute_head_angles(face_lm, w, h)
                    result.head_pitch = round(pitch, 1)
                    result.head_yaw   = round(yaw,   1)

                    # ── Drowsiness logic ──────────────────────────────────
                    if ear < self._ear_threshold:
                        self._closed_frames += 1
                        if self._eye_closed_start is None:
                            self._eye_closed_start = time.monotonic()
                    else:
                        self._closed_frames = 0
                        self._eye_closed_start = None

                    closed_sec = 0.0
                    if self._eye_closed_start is not None:
                        closed_sec = time.monotonic() - self._eye_closed_start
                    result.eye_closed_sec = round(closed_sec, 2)

                    drowsy = self._closed_frames >= config.EAR_CONSEC_FRAMES
                    result.drowsy      = drowsy
                    result.alert_active = drowsy

                    # Calibration feed
                    if self._calib_engine and self._calib_engine.is_running:
                        self._calib_engine.add_sample(ear)

                else:
                    result.face_detected = False
                    self._closed_frames  = 0
                    self._yawn_frames    = 0
                    self._eye_closed_start = None

                # ── Annotate frame & publish ──────────────────────────────
                self._draw_hud(frame, result)
                result.frame = frame
                self._publish(result)

        self._release_camera()
