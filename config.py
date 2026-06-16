"""
config.py
─────────────────────────────────────────────
Central configuration for the AI Driver Drowsiness Detection System.
All tuneable constants live here so every module imports from one place.
"""

import os
from pathlib import Path

# ── Project paths ──────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
DATA_DIR       = BASE_DIR / "data"
LOGS_DIR       = BASE_DIR / "logs"
ASSETS_DIR     = BASE_DIR / "assets"
MODELS_DIR     = BASE_DIR / "models"

CALIBRATION_FILE   = DATA_DIR / "calibration.json"
DRIVER_DB_FILE     = DATA_DIR / "drivers.db"
LOG_CSV_FILE       = LOGS_DIR / "events.csv"
LOG_EXCEL_FILE     = LOGS_DIR / "events.xlsx"

# Create dirs on import
for _d in (DATA_DIR, LOGS_DIR, ASSETS_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Camera ─────────────────────────────────────────────────────────────────
CAMERA_INDEX       = 0          # 0 = default webcam
CAMERA_WIDTH       = 640
CAMERA_HEIGHT      = 480
TARGET_FPS         = 30

# ── MediaPipe Face Mesh ────────────────────────────────────────────────────
MAX_NUM_FACES          = 1
REFINE_LANDMARKS       = True
MIN_DETECTION_CONF     = 0.5
MIN_TRACKING_CONF      = 0.5

# ── Eye landmark indices (MediaPipe 478-point model) ──────────────────────
# Left eye
LEFT_EYE_INDICES  = [362, 382, 381, 380, 374, 373, 390, 249,
                     263, 466, 388, 387, 386, 385, 384, 398]
# Right eye
RIGHT_EYE_INDICES = [33,  7,   163, 144, 145, 153, 154, 155,
                     133, 173, 157, 158, 159, 160, 161, 246]

# 6-point EAR landmarks (vertical / horizontal pairs)
LEFT_EAR_POINTS  = [362, 385, 387, 263, 373, 380]   # P1..P6
RIGHT_EAR_POINTS = [33,  160, 158, 133, 153, 144]   # P1..P6

# Mouth / yawn landmarks
MOUTH_INDICES    = [61, 291, 0, 17, 269, 405, 17, 181]
UPPER_LIP        = 13
LOWER_LIP        = 14
LEFT_MOUTH       = 61
RIGHT_MOUTH      = 291

# Head-pose nose/chin/ear landmarks
NOSE_TIP         = 1
CHIN             = 152
LEFT_EAR_PT      = 234
RIGHT_EAR_PT     = 454
LEFT_MOUTH_PT    = 397
RIGHT_MOUTH_PT   = 13

# ── EAR / Drowsiness thresholds ───────────────────────────────────────────
DEFAULT_EAR_THRESHOLD      = 0.21   # used if calibration not done
EAR_CONSEC_FRAMES          = 20     # ~0.67 s at 30 fps → closed-eye trigger
CALIBRATION_DURATION_SEC   = 10     # seconds of data for auto-threshold
EAR_THRESHOLD_FACTOR       = 0.75   # threshold = mean_ear * factor

# ── Yawn detection ────────────────────────────────────────────────────────
YAWN_THRESHOLD             = 0.6    # Mouth Aspect Ratio
YAWN_CONSEC_FRAMES         = 15

# ── Head pose ─────────────────────────────────────────────────────────────
HEAD_PITCH_THRESHOLD       = 20     # degrees — nodding down
HEAD_YAW_THRESHOLD         = 30     # degrees — looking away

# ── Arduino / Serial ──────────────────────────────────────────────────────
ARDUINO_BAUD_RATE          = 9600
ARDUINO_TIMEOUT            = 1      # seconds
ARDUINO_AUTO_DETECT        = True   # scan all COM ports
ARDUINO_PORT               = ""     # leave blank for auto-detect
ARDUINO_RETRY_INTERVAL     = 5      # seconds between reconnect attempts
CMD_ALERT_ON               = "ALERT_ON\n"
CMD_ALERT_OFF              = "ALERT_OFF\n"

# ── Audio alert ───────────────────────────────────────────────────────────
AUDIO_ALERT_TEXT           = "Wake up driver!"
AUDIO_LANG                 = "en"
AUDIO_RATE                 = 150

# ── UI / Theme ────────────────────────────────────────────────────────────
APP_TITLE                  = "AI Driver Drowsiness Detection System"
APP_VERSION                = "1.0.0"

# Dark theme palette
COLOR_BG           = "#0d0d0d"
COLOR_PANEL        = "#141414"
COLOR_CARD         = "#1c1c1c"
COLOR_BORDER       = "#2a2a2a"
COLOR_ACCENT       = "#00d4ff"        # cyan
COLOR_ACCENT2      = "#7c3aed"        # purple
COLOR_SUCCESS      = "#22c55e"
COLOR_WARNING      = "#f59e0b"
COLOR_DANGER       = "#ef4444"
COLOR_TEXT         = "#e2e8f0"
COLOR_TEXT_MUTED   = "#64748b"
COLOR_GRAPH_EAR    = "#00d4ff"
COLOR_GRAPH_YAWN   = "#f59e0b"
COLOR_GRAPH_BG     = "#0a0a0a"

FONT_FAMILY        = "Segoe UI"
FONT_MONO          = "Consolas"

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL          = "INFO"
MAX_LOG_ENTRIES    = 500    # keep in-memory log bounded

# ── Statistics graph ──────────────────────────────────────────────────────
GRAPH_WINDOW_SEC   = 30    # rolling window seconds shown in EAR graph
GRAPH_UPDATE_MS    = 100   # redraw interval ms
