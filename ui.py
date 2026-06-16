"""
ui.py
─────────────────────────────────────────────
Modern dark-theme dashboard built with CustomTkinter.

Layout
──────
┌─────────────────────────────────────────────────────────┐
│  TOP BAR   Project title | Date & Time | Version        │
├──────────────────────┬──────────────────────────────────┤
│                      │  STATUS CARDS                    │
│  LIVE CAMERA FEED    │  (Driver, EAR, FPS, Arduino …)   │
│   (left panel)       │  EAR GRAPH                       │
│                      │  ACTION BUTTONS                  │
├──────────────────────┴──────────────────────────────────┤
│  EVENT LOG / STATISTICS TABS                            │
└─────────────────────────────────────────────────────────┘
"""

import queue
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable, Deque, List, Optional, Tuple

import cv2
import numpy as np

import config
from arduino_controller import arduino
from calibration import delete_calibration, load_calibration, save_calibration
from drowsiness_detector import DetectionResult, DrowsinessDetector
from face_recognition_module import face_recognizer
from logger import event_logger

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False
    import tkinter as ctk  # type: ignore[assignment]

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False

try:
    import pyttsx3
    _tts = pyttsx3.init()
    _tts.setProperty("rate", config.AUDIO_RATE)
    TTS_AVAILABLE = True
except Exception:   # noqa: BLE001
    TTS_AVAILABLE = False


# ── colour / style constants ──────────────────────────────────────────────

C = config   # alias

CARD_STYLE = dict(
    fg_color=C.COLOR_CARD,
    corner_radius=10,
)
LABEL_MUTED = dict(text_color=C.COLOR_TEXT_MUTED, font=(C.FONT_FAMILY, 11))
LABEL_MONO  = dict(text_color=C.COLOR_TEXT, font=(C.FONT_MONO, 13, "bold"))


# ── helper: convert OpenCV frame to PhotoImage ────────────────────────────

def _frame_to_photoimage(frame: np.ndarray, target_w: int, target_h: int):
    resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
    rgb     = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    if PIL_AVAILABLE:
        img = Image.fromarray(rgb)
        return ImageTk.PhotoImage(image=img)
    # fallback: raw tk PhotoImage via PPM
    import tkinter as tk
    data = f"P6 {target_w} {target_h} 255 ".encode() + rgb.tobytes()
    photo = tk.PhotoImage(width=target_w, height=target_h)
    photo.put(data, to=(0, 0, target_w, target_h))
    return photo


# ── status card widget ────────────────────────────────────────────────────

class StatusCard(ctk.CTkFrame):
    """A labelled value card for the right panel."""

    def __init__(self, parent, label: str, value: str = "—", unit: str = "", **kwargs):
        super().__init__(parent, **CARD_STYLE, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self._lbl = ctk.CTkLabel(self, text=label, **LABEL_MUTED)
        self._lbl.grid(row=0, column=0, padx=10, pady=(8, 0), sticky="w")

        self._val = ctk.CTkLabel(self, text=value, font=(C.FONT_MONO, 20, "bold"),
                                 text_color=C.COLOR_ACCENT)
        self._val.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="w")

        self._unit = ctk.CTkLabel(self, text=unit, **LABEL_MUTED)
        self._unit.grid(row=1, column=1, padx=(0, 10), pady=(0, 8), sticky="e")

    def set(self, value: str, color: str = C.COLOR_ACCENT) -> None:
        self._val.configure(text=value, text_color=color)


# ── EAR graph ─────────────────────────────────────────────────────────────

class EARGraph(ctk.CTkFrame):
    """Rolling EAR / threshold graph using matplotlib."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C.COLOR_GRAPH_BG, corner_radius=10, **kwargs)
        self._ear_buf:  Deque[float] = deque(maxlen=int(config.GRAPH_WINDOW_SEC * config.TARGET_FPS))
        self._mar_buf:  Deque[float] = deque(maxlen=int(config.GRAPH_WINDOW_SEC * config.TARGET_FPS))
        self._threshold = config.DEFAULT_EAR_THRESHOLD
        self._canvas = None
        self._ax     = None
        self._fig    = None
        self._build_chart()

    def _build_chart(self) -> None:
        if not MPL_AVAILABLE:
            lbl = ctk.CTkLabel(self, text="matplotlib not installed\n(pip install matplotlib)",
                               text_color=C.COLOR_TEXT_MUTED)
            lbl.pack(expand=True)
            return

        self._fig = Figure(figsize=(4, 2.2), dpi=90,
                           facecolor=C.COLOR_GRAPH_BG)
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor(C.COLOR_GRAPH_BG)
        self._ax.tick_params(colors=C.COLOR_TEXT_MUTED, labelsize=8)
        for spine in self._ax.spines.values():
            spine.set_edgecolor(C.COLOR_BORDER)
        self._fig.tight_layout(pad=1.2)

        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

    def update(self, ear: float, mar: float, threshold: float) -> None:
        self._ear_buf.append(ear)
        self._mar_buf.append(mar)
        self._threshold = threshold

    def redraw(self) -> None:
        if not MPL_AVAILABLE or self._ax is None:
            return
        ax = self._ax
        ax.clear()
        ax.set_facecolor(C.COLOR_GRAPH_BG)

        y_ear = list(self._ear_buf)
        y_mar = list(self._mar_buf)
        x     = list(range(len(y_ear)))

        if y_ear:
            ax.plot(x, y_ear, color=C.COLOR_GRAPH_EAR, linewidth=1.2,
                    label="EAR")
        if y_mar:
            ax.plot(x, y_mar, color=C.COLOR_GRAPH_YAWN, linewidth=1.0,
                    alpha=0.7, label="MAR")
        ax.axhline(self._threshold, color=C.COLOR_DANGER,
                   linestyle="--", linewidth=1, label=f"Thr {self._threshold:.2f}")

        ax.set_ylim(0, 0.5)
        ax.set_xlim(0, max(len(y_ear), 10))
        ax.tick_params(colors=C.COLOR_TEXT_MUTED, labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor(C.COLOR_BORDER)
        ax.legend(fontsize=7, facecolor=C.COLOR_CARD,
                  edgecolor=C.COLOR_BORDER, labelcolor=C.COLOR_TEXT)

        try:
            self._canvas.draw_idle()
        except Exception:    # noqa: BLE001
            pass


# ── log panel ─────────────────────────────────────────────────────────────

class LogPanel(ctk.CTkFrame):
    """Scrollable text log with colour coding."""

    _TYPE_COLORS = {
        "ALERT":       config.COLOR_DANGER,
        "DROWSY":      config.COLOR_DANGER,
        "YAWN":        config.COLOR_WARNING,
        "DRIVER_IN":   config.COLOR_SUCCESS,
        "CALIBRATION": config.COLOR_ACCENT,
        "SYSTEM":      config.COLOR_TEXT_MUTED,
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **CARD_STYLE, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkLabel(self, text="EVENT LOG",
                            font=(C.FONT_FAMILY, 12, "bold"),
                            text_color=C.COLOR_ACCENT)
        hdr.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        self._text = ctk.CTkTextbox(
            self, font=(C.FONT_MONO, 11),
            fg_color=C.COLOR_BG, text_color=C.COLOR_TEXT,
            wrap="none", state="disabled",
        )
        self._text.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

    def append(self, line: str, event_type: str = "") -> None:
        color = self._TYPE_COLORS.get(event_type.upper(), C.COLOR_TEXT)
        self._text.configure(state="normal")
        self._text.insert("end", line + "\n")
        # CTkTextbox doesn't support per-line colouring natively;
        # colour coding is handled by the overall text colour default.
        self._text.configure(state="disabled")
        self._text.see("end")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")


# ── driver registration dialog ────────────────────────────────────────────

class DriverRegDialog(ctk.CTkToplevel):
    """Modal for registering a new driver."""

    def __init__(self, parent, detector: DrowsinessDetector):
        super().__init__(parent)
        self.title("Register Driver")
        self.geometry("400x340")
        self.resizable(False, False)
        self.configure(fg_color=C.COLOR_PANEL)
        self._detector = detector
        self._last_frame: Optional[np.ndarray] = None
        self._result: Optional[str] = None
        self._build()
        self.grab_set()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Register New Driver",
                     font=(C.FONT_FAMILY, 16, "bold"),
                     text_color=C.COLOR_ACCENT).pack(pady=(18, 4))

        ctk.CTkLabel(self, text="Driver Name:", **LABEL_MUTED).pack(anchor="w", padx=24, pady=(10, 2))
        self._name_var = ctk.StringVar()
        ctk.CTkEntry(self, textvariable=self._name_var, width=320,
                     fg_color=C.COLOR_BG, border_color=C.COLOR_BORDER).pack(padx=24)

        ctk.CTkLabel(self, text="Position your face in the camera, then click Capture.",
                     text_color=C.COLOR_TEXT_MUTED, font=(C.FONT_FAMILY, 11),
                     wraplength=340).pack(padx=24, pady=(12, 4))

        self._status = ctk.CTkLabel(self, text="Waiting …",
                                    text_color=C.COLOR_TEXT_MUTED,
                                    font=(C.FONT_FAMILY, 12))
        self._status.pack(pady=4)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=12)
        ctk.CTkButton(btn_frame, text="📷 Capture & Register",
                      command=self._capture,
                      fg_color=C.COLOR_ACCENT2, hover_color="#6d28d9",
                      width=180).grid(row=0, column=0, padx=8)
        ctk.CTkButton(btn_frame, text="Cancel",
                      command=self.destroy,
                      fg_color=C.COLOR_CARD, hover_color=C.COLOR_BORDER,
                      width=100).grid(row=0, column=1, padx=8)

        # Subscribe to detector frames
        self._detector.add_listener(self._on_frame)

    def _on_frame(self, res: DetectionResult) -> None:
        self._last_frame = res.frame.copy()

    def _capture(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            self._status.configure(text="Please enter a driver name.",
                                   text_color=C.COLOR_WARNING)
            return
        if self._last_frame is None:
            self._status.configure(text="No camera frame — check camera.",
                                   text_color=C.COLOR_DANGER)
            return
        ok, msg = face_recognizer.register(name, self._last_frame)
        if ok:
            self._status.configure(text=f"✓ {msg}", text_color=C.COLOR_SUCCESS)
            self._result = name
            event_logger.log("DRIVER_REGISTER", driver=name, detail="New registration")
            self.after(1500, self.destroy)
        else:
            self._status.configure(text=f"✗ {msg}", text_color=C.COLOR_DANGER)


# ── main application window ───────────────────────────────────────────────

class MainApp(ctk.CTk):
    """
    Root application window.
    Orchestrates detector, Arduino, face-rec, calibration, and UI panels.
    """

    _FEED_W = 580
    _FEED_H = 436

    def __init__(self) -> None:
        super().__init__()
        self.title(C.APP_TITLE)
        self.geometry("1300x820")
        self.minsize(1100, 700)
        self.configure(fg_color=C.COLOR_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Core objects
        self._detector = DrowsinessDetector()
        self._alert_cooldown  = 0.0
        self._alert_active    = False
        self._current_driver  = ""
        self._recognition_cooldown = 0.0
        self._frame_queue: queue.Queue = queue.Queue(maxsize=2)
        self._calib_tick: int = 0

        # TTS worker
        self._tts_queue: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._tts_worker, daemon=True, name="TTS").start()

        self._build_ui()
        self._connect_arduino()
        self._detector.add_listener(self._on_detection)
        event_logger.register_callback(self._on_log_event)
        self._detector.start()

        # Periodic UI refresh
        self._refresh_loop()
        self._graph_loop()
        self._clock_loop()

    # ── UI build ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        self._build_top()
        self._build_left()
        self._build_right()
        self._build_bottom()

    def _build_top(self) -> None:
        top = ctk.CTkFrame(self, fg_color=C.COLOR_PANEL,
                           corner_radius=0, height=52)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top,
            text=f"🚗  {C.APP_TITLE}",
            font=(C.FONT_FAMILY, 16, "bold"),
            text_color=C.COLOR_ACCENT,
        ).grid(row=0, column=0, padx=20, pady=12, sticky="w")

        self._clock_lbl = ctk.CTkLabel(
            top, text="", font=(C.FONT_MONO, 13),
            text_color=C.COLOR_TEXT_MUTED,
        )
        self._clock_lbl.grid(row=0, column=1, padx=20, pady=12, sticky="e")

        ctk.CTkLabel(
            top, text=f"v{C.APP_VERSION}",
            font=(C.FONT_FAMILY, 11), text_color=C.COLOR_TEXT_MUTED,
        ).grid(row=0, column=2, padx=16, pady=12, sticky="e")

    def _build_left(self) -> None:
        left = ctk.CTkFrame(self, fg_color=C.COLOR_PANEL, corner_radius=0)
        left.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=8)

        import tkinter as tk
        self._cam_canvas = tk.Canvas(
            left,
            width=self._FEED_W, height=self._FEED_H,
            bg=C.COLOR_BG, highlightthickness=0,
        )
        self._cam_canvas.pack(padx=8, pady=8)
        self._photo_ref = None     # keep reference

        # Calibration progress bar
        self._calib_bar_frame = ctk.CTkFrame(left, fg_color="transparent")
        self._calib_bar_frame.pack(fill="x", padx=8, pady=(0, 4))
        self._calib_label = ctk.CTkLabel(
            self._calib_bar_frame, text="",
            font=(C.FONT_FAMILY, 11), text_color=C.COLOR_WARNING,
        )
        self._calib_label.pack(anchor="w")
        self._calib_bar = ctk.CTkProgressBar(
            self._calib_bar_frame, fg_color=C.COLOR_BORDER,
            progress_color=C.COLOR_WARNING, height=6,
        )
        self._calib_bar.set(0)

    def _build_right(self) -> None:
        right = ctk.CTkScrollableFrame(self, fg_color=C.COLOR_PANEL,
                                       corner_radius=0, width=320)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.grid_columnconfigure(0, weight=1)
        self._right = right
        row = 0

        # ─ Status cards ──────────────────────────────────────────────────
        def card(label, val="—", unit=""):
            c = StatusCard(right, label, val, unit)
            c.grid(row=row, column=0, padx=8, pady=(4, 2), sticky="ew")
            return c

        self._card_driver   = card("Driver");         row += 1
        self._card_ear      = card("EAR Value",  unit="ratio"); row += 1
        self._card_mar      = card("MAR Value",  unit="ratio"); row += 1
        self._card_thresh   = card("EAR Threshold"); row += 1
        self._card_status   = card("System Status"); row += 1
        self._card_fps      = card("FPS");           row += 1
        self._card_cam      = card("Camera");        row += 1
        self._card_arduino  = card("Arduino");       row += 1
        self._card_closed   = card("Eyes Closed",  unit="sec"); row += 1
        self._card_head     = card("Head Pose");     row += 1

        # Update initial values
        thresh = load_calibration() or C.DEFAULT_EAR_THRESHOLD
        self._card_thresh.set(f"{thresh:.3f}")
        self._card_status.set("Starting …", C.COLOR_WARNING)
        self._card_cam.set("Connecting", C.COLOR_WARNING)
        self._card_arduino.set("No Arduino", C.COLOR_TEXT_MUTED)

        # ─ EAR graph ─────────────────────────────────────────────────────
        graph_hdr = ctk.CTkLabel(right, text="EAR / MAR TREND",
                                 font=(C.FONT_FAMILY, 12, "bold"),
                                 text_color=C.COLOR_ACCENT)
        graph_hdr.grid(row=row, column=0, padx=8, pady=(10, 2), sticky="w"); row += 1

        self._graph = EARGraph(right)
        self._graph.grid(row=row, column=0, padx=8, pady=(0, 6),
                         sticky="ew"); row += 1

        # ─ Action buttons ────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        btn_frame.grid(row=row, column=0, padx=8, pady=4, sticky="ew"); row += 1
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        BTN = dict(height=32, corner_radius=8)
        ctk.CTkButton(btn_frame, text="🎯 Calibrate",
                      command=self._start_calibration,
                      fg_color=C.COLOR_ACCENT2, hover_color="#6d28d9",
                      **BTN).grid(row=0, column=0, padx=4, pady=3, sticky="ew")
        ctk.CTkButton(btn_frame, text="👤 Register Driver",
                      command=self._open_register,
                      fg_color="#0f766e", hover_color="#0d9488",
                      **BTN).grid(row=0, column=1, padx=4, pady=3, sticky="ew")
        ctk.CTkButton(btn_frame, text="🔍 Identify Driver",
                      command=self._identify_driver,
                      fg_color="#1e40af", hover_color="#1d4ed8",
                      **BTN).grid(row=1, column=0, padx=4, pady=3, sticky="ew")
        ctk.CTkButton(btn_frame, text="🔌 Connect Arduino",
                      command=self._reconnect_arduino,
                      fg_color="#374151", hover_color="#4b5563",
                      **BTN).grid(row=1, column=1, padx=4, pady=3, sticky="ew")
        ctk.CTkButton(btn_frame, text="📊 Export CSV",
                      command=self._export_csv,
                      fg_color="#374151", hover_color="#4b5563",
                      **BTN).grid(row=2, column=0, padx=4, pady=3, sticky="ew")
        ctk.CTkButton(btn_frame, text="📈 Export Excel",
                      command=self._export_excel,
                      fg_color="#374151", hover_color="#4b5563",
                      **BTN).grid(row=2, column=1, padx=4, pady=3, sticky="ew")
        ctk.CTkButton(btn_frame, text="🗑 Clear Calibration",
                      command=self._clear_calibration,
                      fg_color="#7f1d1d", hover_color="#991b1b",
                      **BTN).grid(row=3, column=0, columnspan=2,
                                  padx=4, pady=3, sticky="ew")

    def _build_bottom(self) -> None:
        self._log_panel = LogPanel(self)
        self._log_panel.grid(
            row=2, column=0, columnspan=2,
            sticky="nsew", padx=8, pady=(0, 8),
        )
        self.grid_rowconfigure(2, minsize=160)

    # ── detector callback (non-UI thread) ─────────────────────────────────
    def _on_detection(self, res: DetectionResult) -> None:
        # Drop if queue full (keeps UI responsive)
        try:
            self._frame_queue.put_nowait(res)
        except queue.Full:
            pass

    # ── UI refresh loop ───────────────────────────────────────────────────
    def _refresh_loop(self) -> None:
        try:
            result: Optional[DetectionResult] = None
            while not self._frame_queue.empty():
                result = self._frame_queue.get_nowait()

            if result is not None:
                self._update_video(result)
                self._update_cards(result)
                self._graph.update(result.ear, result.mar, result.ear_threshold)
                self._handle_alerts(result)
                self._handle_recognition(result)
                # Calibration bar
                if self._detector.is_calibrating:
                    p = self._detector.calibration_progress
                    self._calib_bar.set(p)
                    self._calib_bar.pack(fill="x")
                    self._calib_label.configure(
                        text=f"Calibrating … {int(p*100)}%  |  tick={self._calib_tick}"
                    )
                else:
                    self._calib_bar.pack_forget()
                    self._calib_label.configure(text="")

        except Exception:    # noqa: BLE001
            pass
        self.after(30, self._refresh_loop)

    def _update_video(self, res: DetectionResult) -> None:
        try:
            photo = _frame_to_photoimage(res.frame, self._FEED_W, self._FEED_H)
            self._cam_canvas.create_image(0, 0, anchor="nw", image=photo)
            self._photo_ref = photo   # prevent GC
        except Exception:    # noqa: BLE001
            pass

    def _update_cards(self, res: DetectionResult) -> None:
        # EAR colour
        ear_color = (C.COLOR_DANGER if res.ear < res.ear_threshold
                     else C.COLOR_SUCCESS)
        self._card_ear.set(f"{res.ear:.3f}", ear_color)
        self._card_mar.set(f"{res.mar:.3f}",
                           C.COLOR_WARNING if res.yawning else C.COLOR_TEXT)
        self._card_thresh.set(f"{res.ear_threshold:.3f}")
        self._card_fps.set(f"{res.fps:.1f}",
                           C.COLOR_SUCCESS if res.fps >= 20 else C.COLOR_WARNING)
        self._card_cam.set(
            "OK ✓" if res.cam_ok else "ERROR ✗",
            C.COLOR_SUCCESS if res.cam_ok else C.COLOR_DANGER,
        )
        self._card_closed.set(f"{res.eye_closed_sec:.1f}")
        self._card_head.set(f"P:{res.head_pitch:+.0f}°  Y:{res.head_yaw:+.0f}°")

        if res.face_detected:
            status = ("⚠ DROWSY" if res.drowsy else
                      "😮 YAWN"  if res.yawning else
                      "✓ AWAKE")
            color  = (C.COLOR_DANGER if res.drowsy else
                      C.COLOR_WARNING if res.yawning else
                      C.COLOR_SUCCESS)
        else:
            status, color = "No Face", C.COLOR_TEXT_MUTED
        self._card_status.set(status, color)

        drv = res.driver_name or "Unknown"
        self._card_driver.set(drv,
                              C.COLOR_SUCCESS if res.driver_name else C.COLOR_WARNING)

        ard_ok = arduino.is_connected
        self._card_arduino.set(
            f"✓ {arduino.port_name}" if ard_ok else "Not Connected",
            C.COLOR_SUCCESS if ard_ok else C.COLOR_TEXT_MUTED,
        )

    # ── alert handling ────────────────────────────────────────────────────
    def _handle_alerts(self, res: DetectionResult) -> None:
        now = time.time()
        if res.alert_active and not self._alert_active:
            self._alert_active = True
            arduino.send_alert_on()
            event_logger.log("DROWSY_ALERT", driver=self._current_driver,
                             ear=res.ear, detail="Drowsiness detected")
            if TTS_AVAILABLE and now - self._alert_cooldown > 8:
                self._alert_cooldown = now
                self._tts_queue.put(C.AUDIO_ALERT_TEXT)
        elif not res.alert_active and self._alert_active:
            self._alert_active = False
            arduino.send_alert_off()

        if res.yawning:
            event_logger.log("YAWN", driver=self._current_driver,
                             ear=res.mar, detail="Yawn detected")

    # ── driver recognition ────────────────────────────────────────────────
    def _handle_recognition(self, res: DetectionResult) -> None:
        now = time.time()
        if now - self._recognition_cooldown < 10:
            return
        if not res.face_detected:
            return
        if face_recognizer.driver_count() == 0:
            return
        self._recognition_cooldown = now
        frame = res.frame.copy()

        def _run() -> None:
            name, conf = face_recognizer.identify(frame)
            def _ui() -> None:
                if name:
                    if name != self._current_driver:
                        self._current_driver = name
                        self._detector.set_driver(name)
                        event_logger.log("DRIVER_IN", driver=name,
                                         detail=f"Conf={conf:.3f}")
                        self._log_panel.append(
                            f"Driver recognised: {name}  (conf={conf:.3f})",
                            "DRIVER_IN",
                        )
                else:
                    event_logger.log("UNKNOWN_DRIVER", detail=f"Conf={conf:.3f}")
            self.after(0, _ui)

        threading.Thread(target=_run, daemon=True).start()

    # ── logger callback ───────────────────────────────────────────────────
    def _on_log_event(self, rec) -> None:
        def _ui():
            self._log_panel.append(rec.to_display(), rec.event_type)
        self.after(0, _ui)

    # ── periodic timers ───────────────────────────────────────────────────
    def _graph_loop(self) -> None:
        self._graph.redraw()
        self.after(C.GRAPH_UPDATE_MS, self._graph_loop)

    def _clock_loop(self) -> None:
        self._clock_lbl.configure(
            text=datetime.now().strftime("%A, %d %B %Y   %H:%M:%S")
        )
        self.after(1000, self._clock_loop)

    # ── button actions ────────────────────────────────────────────────────
    def _start_calibration(self) -> None:
        if self._detector.is_calibrating:
            messagebox.showinfo("Calibration", "Calibration already in progress.")
            return

        def _tick(secs_left: int) -> None:
            self._calib_tick = secs_left

        def _done(threshold: float) -> None:
            def _ui():
                self._card_thresh.set(f"{threshold:.3f}")
                messagebox.showinfo(
                    "Calibration Complete",
                    f"Personalised EAR threshold set to {threshold:.4f}\n"
                    "Saved to disk.",
                )
                event_logger.log("CALIBRATION", detail=f"threshold={threshold:.4f}")
            self.after(0, _ui)

        messagebox.showinfo(
            "Calibration",
            f"Look at the camera normally for {C.CALIBRATION_DURATION_SEC} seconds.\n"
            "Do not blink excessively. Click OK to start.",
        )
        self._detector.start_calibration(on_complete=_done, on_tick=_tick)

    def _open_register(self) -> None:
        DriverRegDialog(self, self._detector)

    def _identify_driver(self) -> None:
        if face_recognizer.driver_count() == 0:
            messagebox.showwarning(
                "No Drivers", "No drivers registered yet.\nClick 'Register Driver' first."
            )
            return
        self._recognition_cooldown = 0.0   # force immediate recognition

    def _reconnect_arduino(self) -> None:
        threading.Thread(target=arduino.connect, daemon=True).start()
        self.after(3000, lambda: self._card_arduino.set(
            f"✓ {arduino.port_name}" if arduino.is_connected else "Not Connected",
            C.COLOR_SUCCESS if arduino.is_connected else C.COLOR_TEXT_MUTED,
        ))

    def _export_csv(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="drowsiness_log.csv",
        )
        if p:
            out = event_logger.export_csv(Path(p))
            messagebox.showinfo("Export", f"CSV saved:\n{out}")

    def _export_excel(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="drowsiness_log.xlsx",
        )
        if p:
            out = event_logger.export_excel(Path(p))
            messagebox.showinfo("Export", f"Excel saved:\n{out}")

    def _clear_calibration(self) -> None:
        if messagebox.askyesno("Clear Calibration",
                               "Delete saved calibration data?"):
            delete_calibration()
            self._detector.set_threshold(C.DEFAULT_EAR_THRESHOLD)
            self._card_thresh.set(f"{C.DEFAULT_EAR_THRESHOLD:.3f}")
            messagebox.showinfo("Calibration", "Calibration data cleared.")

    # ── Arduino ───────────────────────────────────────────────────────────
    def _connect_arduino(self) -> None:
        arduino.start()
        threading.Thread(target=arduino.connect, daemon=True).start()

    # ── TTS worker ────────────────────────────────────────────────────────
    def _tts_worker(self) -> None:
        while True:
            text = self._tts_queue.get()
            if not TTS_AVAILABLE:
                continue
            try:
                _tts.say(text)
                _tts.runAndWait()
            except Exception:    # noqa: BLE001
                pass

    # ── close ─────────────────────────────────────────────────────────────
    def _on_close(self) -> None:
        self._detector.stop()
        arduino.stop()
        event_logger.close()
        face_recognizer.close()
        self.destroy()
