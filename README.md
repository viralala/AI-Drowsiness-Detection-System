# 🚗 AI Driver Drowsiness Detection System

> Real-time eye-tracking, EAR calculation, face recognition, and Arduino-controlled alert system.

---

## Table of Contents
1. [Features](#features)  
2. [Folder Structure](#folder-structure)  
3. [Requirements](#requirements)  
4. [Installation Guide](#installation-guide)  
5. [Execution Instructions](#execution-instructions)  
6. [Calibration Guide](#calibration-guide)  
7. [Driver Registration & Recognition](#driver-registration--recognition)  
8. [Arduino Wiring Diagram](#arduino-wiring-diagram)  
9. [Arduino Upload Instructions](#arduino-upload-instructions)  
10. [Running Without Arduino](#running-without-arduino)  
11. [Keyboard & UI Guide](#keyboard--ui-guide)  
12. [Log & Export Files](#log--export-files)  
13. [Troubleshooting](#troubleshooting)  
14. [Future Enhancements](#future-enhancements)

---

## Features

| Feature | Details |
|---|---|
| Face Detection | MediaPipe Face Mesh (478 landmarks, handles angles + glasses) |
| Eye Tracking | EAR formula on 6-point eye landmarks |
| Yawn Detection | MAR (Mouth Aspect Ratio) threshold |
| Head Pose | Pitch & yaw estimation (no camera calibration needed) |
| Personalized Threshold | 10-second calibration → saved to `data/calibration.json` |
| Face Recognition | Landmark descriptor matching (no dlib needed) |
| Arduino Alert | Buzzer + LED via serial `ALERT_ON` / `ALERT_OFF` |
| Audio Alert | `pyttsx3` TTS "Wake up driver!" |
| Modern Dark UI | CustomTkinter dashboard with live EAR/MAR graph |
| Logging | SQLite + CSV + Excel export |
| Graceful degradation | Runs fully without Arduino connected |

---

## Folder Structure

```
drowsiness_detection/
├── main.py                  ← Entry point
├── ui.py                    ← CustomTkinter dashboard
├── drowsiness_detector.py   ← MediaPipe + EAR engine (background thread)
├── face_recognition_module.py ← Driver registration & ID
├── arduino_controller.py    ← Serial port manager (auto-reconnect)
├── calibration.py           ← EAR threshold calibration engine
├── logger.py                ← Event logger (DB + CSV + Excel)
├── config.py                ← All tuneable constants
├── requirements.txt
├── arduino_code.ino         ← Arduino UNO sketch
├── README.md
├── data/
│   ├── calibration.json     ← Auto-created after calibration
│   └── drivers.db           ← SQLite: driver faces + event log
├── logs/
│   ├── events.csv           ← Appended on every event
│   └── events.xlsx          ← Manual export
├── assets/                  ← (icons, sounds — optional)
└── models/                  ← (reserved for future ONNX models)
```

---

## Requirements

### Software
- Python 3.9 or higher (3.11+ recommended)
- pip 23+

### Hardware (optional but recommended)
- Webcam (USB or built-in)
- Arduino UNO
- Active buzzer
- Red LED + 220 Ω resistor
- Jumper wires + breadboard

---

## Installation Guide

### Step 1 — Clone / copy project
```bash
# Place all .py files in a folder, e.g.:
cd drowsiness_detection
```

### Step 2 — Create virtual environment (recommended)
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### Step 3 — Install Python dependencies
```bash
pip install -r requirements.txt
```

> **Windows note:** If `pyttsx3` fails, install the Visual C++ redistributable or use:
> `pip install pyttsx3 pywin32`

> **macOS note:** Replace `opencv-python` with `opencv-python-headless` if you get display errors.

### Step 4 — Verify MediaPipe
```bash
python -c "import mediapipe; print('MediaPipe OK:', mediapipe.__version__)"
```

---

## Execution Instructions

```bash
# From the project folder with venv active:
python main.py
```

The app will:
1. Check dependencies — missing optional ones are warned, not fatal.
2. Open the camera.
3. Start MediaPipe Face Mesh.
4. Try to auto-detect Arduino (gracefully continues if absent).
5. Display the dashboard.

---

## Calibration Guide

Calibration personalises the EAR threshold for **your** eyes (glasses, lighting, camera distance all affect raw EAR values).

1. Click **🎯 Calibrate** in the dashboard.
2. When prompted, click **OK** and look at the camera naturally for **10 seconds**.
3. The threshold is computed as `mean_EAR × 0.75` and saved to `data/calibration.json`.
4. On next startup the saved value is loaded automatically.

To reset: click **🗑 Clear Calibration**.

---

## Driver Registration & Recognition

### Register a new driver
1. Click **👤 Register Driver**.
2. Type the driver's full name.
3. Position your face in the camera frame (good lighting, eyes visible).
4. Click **📷 Capture & Register**.
5. The descriptor is saved to `data/drivers.db`.

### Identify driver on startup
Click **🔍 Identify Driver** — the system compares the live frame against all stored descriptors and displays the closest match (if confidence ≥ 0.94).

Recognition also runs automatically every 10 seconds in the background.

---

## Arduino Wiring Diagram

```
Arduino UNO
┌───────────────────────────────────────────┐
│                                           │
│  5V ────────────────────────── (not used) │
│  GND ──┬─────────────────────────────── GND
│        │                                  │
│  D8 ───┤──[ Buzzer (+) ]──[ Buzzer (-) ]──┤GND
│        │                                  │
│  D13 ──┤──[220Ω]──[ LED anode ]           │
│        └──────────────────[ LED cathode ]──┤GND
│                                           │
│  USB ──────────────────────── PC (COM port)
└───────────────────────────────────────────┘
```

### Component connections:

| Component | Arduino Pin | Notes |
|---|---|---|
| Buzzer (+) | D8 | Active buzzer — direct connection |
| Buzzer (-) | GND | |
| LED anode (+) | D13 | Via 220 Ω resistor |
| LED cathode (-) | GND | |
| USB | PC | Supplies 5V power + serial |

> For a **passive buzzer**, uncomment the `tone()`/`noTone()` lines in `arduino_code.ino`.

---

## Arduino Upload Instructions

1. Open **Arduino IDE** (1.8.x or 2.x).
2. Open `arduino_code.ino`.
3. Select **Board**: Tools → Board → Arduino UNO.
4. Select **Port**: Tools → Port → (your COM port, e.g. `COM3` or `/dev/ttyUSB0`).
5. Click **Upload** (→).
6. Open Serial Monitor at **9600 baud** — you should see `READY`.

---

## Running Without Arduino

**The system runs completely without Arduino.**

- If no Arduino is detected at startup, the app continues normally.
- All eye tracking, EAR, calibration, face recognition, TTS audio alert, and logging work as usual.
- The Arduino status card shows "Not Connected" in grey.
- Clicking **🔌 Connect Arduino** at any time will attempt to find and connect.
- If you plug in an Arduino while the app is running, it auto-reconnects within ~5 seconds.

---

## Keyboard & UI Guide

| Element | Action |
|---|---|
| 🎯 Calibrate | Start 10-sec EAR calibration |
| 👤 Register Driver | Open driver registration dialog |
| 🔍 Identify Driver | Force immediate face identification |
| 🔌 Connect Arduino | Manually trigger Arduino (re)connect |
| 📊 Export CSV | Save event log to CSV |
| 📈 Export Excel | Save event log to .xlsx |
| 🗑 Clear Calibration | Delete saved calibration data |

---

## Log & Export Files

| File | Contents |
|---|---|
| `logs/events.csv` | Appended on every event (always up to date) |
| `logs/events.xlsx` | Manual export via UI button |
| `data/drivers.db` | SQLite: driver descriptors + full event history |
| `data/calibration.json` | EAR threshold + calibration timestamp |

### Event types logged:
- `DROWSY_ALERT` — eye closure exceeded threshold
- `YAWN` — yawn detected
- `DRIVER_IN` — driver recognised
- `DRIVER_REGISTER` — new driver enrolled
- `UNKNOWN_DRIVER` — face not matched
- `CALIBRATION` — threshold saved
- `SYSTEM` — start/stop/errors

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Camera not found` | Check USB connection; try `CAMERA_INDEX = 1` in `config.py` |
| Low FPS (< 20) | Reduce `CAMERA_WIDTH/HEIGHT` in `config.py`; close other apps |
| False drowsiness alerts | Run calibration; adjust `EAR_THRESHOLD_FACTOR` in `config.py` |
| No face detected | Improve lighting; sit closer; check `MIN_DETECTION_CONF` |
| Arduino not found | Check COM port in Device Manager; install CH340 driver |
| `pyttsx3` crash on Linux | `sudo apt install espeak` |
| Glasses reducing EAR | Calibrate **with** your glasses on |
| `customtkinter` not found | `pip install customtkinter` |

---

## Future Enhancements

1. **ONNX model integration** — replace MediaPipe with a lightweight custom model for 60+ FPS on CPU.
2. **Night-vision mode** — IR camera support + adaptive brightness enhancement.
3. **Cloud dashboard** — stream events to Firebase / AWS IoT for fleet monitoring.
4. **Multi-face support** — alert when any passenger is drowsy.
5. **Fatigue score** — weighted combination of EAR, MAR, head pose, and blink rate.
6. **SMS / push alerts** — notify fleet manager via Twilio or Firebase Cloud Messaging.
7. **Raspberry Pi port** — deploy on embedded hardware in the vehicle.
8. **Statistics page** — daily/weekly drowsiness trend charts.
9. **Voice commands** — "dismiss alert", "calibrate" via speech recognition.
10. **OBD-II integration** — correlate fatigue with vehicle speed / lane deviation.

---

*Built with ❤️ using Python, OpenCV, MediaPipe, CustomTkinter, and Arduino.*
