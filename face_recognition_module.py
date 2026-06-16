"""
face_recognition_module.py
─────────────────────────────────────────────
Driver registration and recognition using MediaPipe Face Mesh + a simple
128-dim landmark descriptor.  We avoid the heavy `face_recognition` library
so the system works without dlib / CMake build tools.

Algorithm
─────────
1. Extract 468 normalised face-mesh landmarks from a reference frame.
2. Reduce to a compact pose-invariant feature vector.
3. Compare against stored profiles using cosine similarity.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

import config

_log = logging.getLogger("FaceRec")

try:
    import mediapipe as mp
    _mp_face_mesh = mp.solutions.face_mesh
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    _log.warning("MediaPipe not installed")


# ── feature extraction ────────────────────────────────────────────────────

def _extract_descriptor(landmarks, img_w: int, img_h: int) -> np.ndarray:
    """
    Convert 468 face-mesh landmarks into a compact, pose-normalised descriptor.

    Steps
    ─────
    1. Collect (x, y) for all 468 points.
    2. Centre on nose tip (landmark 1).
    3. Scale by inter-ocular distance (left eye #33 → right eye #263).
    4. Flatten to 1-D and L2-normalise.
    """
    pts = np.array(
        [(lm.x * img_w, lm.y * img_h) for lm in landmarks], dtype=np.float32
    )
    # Centre
    nose = pts[1]
    pts  = pts - nose
    # Scale by inter-ocular distance
    iod = np.linalg.norm(pts[263] - pts[33]) + 1e-6
    pts = pts / iod
    # Flatten & normalise
    desc = pts.flatten()
    norm = np.linalg.norm(desc) + 1e-9
    return (desc / norm).astype(np.float32)


# ── database helpers ──────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(config.DRIVER_DB_FILE), check_same_thread=False)
    db.execute(
        """CREATE TABLE IF NOT EXISTS drivers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            descriptor  BLOB NOT NULL,
            registered  TEXT
        )"""
    )
    db.commit()
    return db


# ── recognition engine ────────────────────────────────────────────────────

class FaceRecognizer:
    """
    Register and identify drivers.

    Public API
    ──────────
    register(name, frame) → bool
    identify(frame)       → (name | None, confidence 0-1)
    list_drivers()        → [{"name": ..., "registered": ...}, ...]
    delete_driver(name)   → bool
    """

    SIMILARITY_THRESHOLD = 0.94      # cosine similarity threshold

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._db: Optional[sqlite3.Connection] = None
        self._profiles: Dict[str, np.ndarray] = {}   # name → descriptor
        self._mesh: Optional[object] = None           # mp FaceMesh

        if MEDIAPIPE_AVAILABLE:
            self._mesh = _mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
            )
        self._init_db()

    # ── init ─────────────────────────────────────────────────────────────
    def _init_db(self) -> None:
        try:
            self._db = _get_db()
            self._load_profiles()
        except sqlite3.Error as exc:
            _log.error("DB init failed: %s", exc)

    def _load_profiles(self) -> None:
        if not self._db:
            return
        cur = self._db.execute("SELECT name, descriptor FROM drivers")
        with self._lock:
            self._profiles.clear()
            for name, blob in cur.fetchall():
                arr = np.frombuffer(blob, dtype=np.float32)
                self._profiles[name] = arr
        _log.info("Loaded %d driver profile(s)", len(self._profiles))

    # ── helper: get descriptor from frame ────────────────────────────────
    def _get_descriptor(self, frame: np.ndarray) -> Optional[np.ndarray]:
        if not MEDIAPIPE_AVAILABLE or self._mesh is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]
        result = self._mesh.process(rgb)
        if not result.multi_face_landmarks:
            return None
        landmarks = result.multi_face_landmarks[0].landmark
        return _extract_descriptor(landmarks, w, h)

    # ── public API ────────────────────────────────────────────────────────
    def register(self, name: str, frame: np.ndarray) -> Tuple[bool, str]:
        """
        Register a new driver using a captured frame.
        Returns (success, message).
        """
        name = name.strip()
        if not name:
            return False, "Driver name cannot be empty"

        desc = self._get_descriptor(frame)
        if desc is None:
            return False, "No face detected in frame — try better lighting"

        if not self._db:
            return False, "Database not available"

        try:
            blob = desc.tobytes()
            import time as _time
            ts   = _time.strftime("%Y-%m-%d %H:%M:%S")
            self._db.execute(
                "INSERT OR REPLACE INTO drivers(name,descriptor,registered)"
                " VALUES(?,?,?)",
                (name, blob, ts),
            )
            self._db.commit()
            with self._lock:
                self._profiles[name] = desc
            _log.info("Driver '%s' registered", name)
            return True, f"Driver '{name}' registered successfully"
        except sqlite3.Error as exc:
            _log.error("Register failed: %s", exc)
            return False, str(exc)

    def identify(self, frame: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Identify driver in frame.
        Returns (name_or_None, confidence).
        """
        desc = self._get_descriptor(frame)
        if desc is None:
            return None, 0.0

        with self._lock:
            profiles = dict(self._profiles)

        if not profiles:
            return None, 0.0

        best_name  = None
        best_score = -1.0
        for name, stored in profiles.items():
            if stored.shape != desc.shape:
                continue
            # cosine similarity
            score = float(np.dot(desc, stored))   # already L2-normalised
            if score > best_score:
                best_score = score
                best_name  = name

        if best_score >= self.SIMILARITY_THRESHOLD:
            return best_name, best_score
        return None, best_score

    def list_drivers(self) -> List[Dict[str, str]]:
        if not self._db:
            return []
        cur = self._db.execute(
            "SELECT name, registered FROM drivers ORDER BY name"
        )
        return [{"name": r[0], "registered": r[1] or ""} for r in cur.fetchall()]

    def delete_driver(self, name: str) -> bool:
        if not self._db:
            return False
        try:
            self._db.execute("DELETE FROM drivers WHERE name=?", (name,))
            self._db.commit()
            with self._lock:
                self._profiles.pop(name, None)
            _log.info("Driver '%s' deleted", name)
            return True
        except sqlite3.Error as exc:
            _log.error("Delete failed: %s", exc)
            return False

    def driver_count(self) -> int:
        with self._lock:
            return len(self._profiles)

    def close(self) -> None:
        if self._db:
            try:
                self._db.close()
            except Exception:              # noqa: BLE001
                pass


# ── module-level singleton ─────────────────────────────────────────────────
face_recognizer = FaceRecognizer()
