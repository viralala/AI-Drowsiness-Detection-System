<div align="center">

# 🚗💤 AI Driver Drowsiness Detection System

### *Because your steering wheel shouldn't double as a pillow.*

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Powered-5C3EE8?logo=opencv&logoColor=white)
![MediaPipe](https://img.shields.io/badge/MediaPipe-Face%20Mesh-orange?logo=google&logoColor=white)
![Arduino](https://img.shields.io/badge/Arduino-UNO-00979D?logo=arduino&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-1c1c1c)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Active-success)

**Real-time eye-tracking · EAR calculation · Face recognition · Arduino-controlled alerts**

```
   👁️ ──── 👁️
      \    /
       \  /
        🤔   "Are you... falling asleep?"
       /  \
      /    \
   🚨BUZZ  💡LED
```

</div>

---

## 📚 Table of Contents

| | | | |
|---|---|---|---|
| [✨ Features](#-features) | [📁 Folder Structure](#-folder-structure) | [🧰 Requirements](#-requirements) | [⚙️ Installation](#️-installation-guide) |
| [▶️ Running It](#️-execution-instructions) | [🎯 Calibration](#-calibration-guide) | [🪪 Driver Recognition](#-driver-registration--recognition) | [🔌 Arduino Wiring](#-arduino-wiring-diagram) |
| [📤 Upload to Arduino](#-arduino-upload-instructions) | [🙅 No Arduino? No Problem](#-running-without-arduino) | [⌨️ UI Guide](#️-keyboard--ui-guide) | [🗂️ Logs](#️-log--export-files) |
| [🛠️ Troubleshooting](#️-troubleshooting) | [🚀 Roadmap](#-future-enhancements) | | |

---

## ✨ Features

> *"It watches your eyes more closely than your group chat watches your read receipts."*

| Feature | Details |
|---|---|
| 👀 Face Detection | MediaPipe Face Mesh (478 landmarks — handles angles + glasses) |
| 😴 Eye Tracking | EAR (Eye Aspect Ratio) formula on 6-point eye landmarks |
| 🥱 Yawn Detection | MAR (Mouth Aspect Ratio) threshold |
| 🧭 Head Pose | Pitch & yaw estimation — no camera calibration needed |
| 🎯 Personalized Threshold | 10-second calibration → saved to `data/calibration.json` |
| 🪪 Face Recognition | Landmark descriptor matching (no dlib needed!) |
| 🚨 Arduino Alert | Buzzer + LED via serial `ALERT_ON` / `ALERT_OFF` |
| 🔊 Audio Alert | `pyttsx3` TTS shouting *"Wake up driver!"* |
| 🌙 Modern Dark UI | CustomTkinter dashboard with live EAR/MAR graph |
| 🧾 Logging | SQLite + CSV + Excel export |
| 🛟 Graceful Degradation | Runs fully even without Arduino connected |

---

## 📁 Folder Structure

```
drowsiness_detection/
├── main.py                     ← 🎬 Entry point
├── ui.py                       ← 🖥️  CustomTkinter dashboard
├── drowsiness_detector.py      ← 🧠 MediaPipe + EAR engine (background thread)
├── face_recognition_module.py  ← 🪪 Driver registration & ID
├── arduino_controller.py       ← 🔌 Serial port manager (auto-reconnect)
├── calibration.py              ← 🎯 EAR threshold calibration engine
├── logger.py                   ← 🧾 Event logger (DB + CSV + Excel)
├── config.py                   ← ⚙️  All tuneable constants
├── requirements.txt            ← 📦 Dependencies
├── arduino_code.ino            ← 🤖 Arduino UNO sketch
├── README.md                   ← 📖 You are here
├── data/
│   ├── calibration.json        ← Auto-created after calibration
│   └── drivers.db              ← SQLite: driver faces + event log
├── logs/
│   ├── events.csv               ← Appended on every event
│   └── events.xlsx              ← Manual export
├── assets/                     ← 🎨 (icons, sounds — optional)
└── models/                     ← 🧩 (reserved for future ONNX models)
```

---

## 🧰 Requirements

### 💻 Software
- Python 3.9 or higher (3.11+ recommended — like coffee, the fresher the better)
- pip 23+

### 🔧 Hardware *(optional but recommended)*
- 📷 Webcam (USB or built-in)
- 🔲 Arduino UNO
- 🔊 Active buzzer
- 🔴 Red LED + 220 Ω resistor
- 🧵 Jumper wires + breadboard

---

## ⚙️ Installation Guide

### Step 1 — Clone / copy project
```bash
cd drowsiness_detection
```

### Step 2 — Create a virtual environment *(recommended, not a suggestion your IDE is nagging you about for fun)*
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

> 🪟 **Windows note:** If `pyttsx3` fails, install the Visual C++ redistributable or use:
> `pip install pyttsx3 pywin32`

> 🍎 **macOS note:** Replace `opencv-python` with `opencv-python-headless` if you get display errors.

### Step 4 — Verify MediaPipe
```bash
python -c "import mediapipe; print('MediaPipe OK:', mediapipe.__version__)"
```

✅ If that prints a version number, you're golden. ❌ If it doesn't... welcome to [Troubleshooting](#️-troubleshooting).

---

## ▶️ Execution Instructions

```bash
# From the project folder with venv active:
python main.py
```

The app will:
1. 🔍 Check dependencies — missing optional ones are warned, not fatal.
2. 📷 Open the camera.
3. 🧠 Start MediaPipe Face Mesh.
4. 🔌 Try to auto-detect Arduino (gracefully continues if absent).
5. 🖥️ Display the dashboard.

*No drowsiness detected yet — that's just your code waking up.*

---

## 🎯 Calibration Guide

Calibration personalizes the EAR threshold for **your** eyes (glasses, lighting, and camera distance all affect raw EAR values — everyone blinks like nobody's watching, except now somebody is).

1. Click **🎯 Calibrate** in the dashboard.
2. When prompted, click **OK** and look at the camera naturally for **10 seconds**.
3. The threshold is computed as `mean_EAR × 0.75` and saved to `data/calibration.json`.
4. On next startup, the saved value loads automatically.

To reset: click **🗑 Clear Calibration**.

---

## 🪪 Driver Registration & Recognition

### Register a new driver
1. Click **👤 Register Driver**.
2. Type the driver's full name.
3. Position your face in the camera frame (good lighting, eyes visible).
4. Click **📷 Capture & Register**.
5. The descriptor is saved to `data/drivers.db`.

### Identify driver on startup
Click **🔍 Identify Driver** — the system compares the live frame against all stored descriptors and displays the closest match (if confidence ≥ 0.94).

Recognition also runs automatically every 10 seconds in the background — silently judging who's behind the wheel, like a very polite bouncer.

---

## 🔌 Arduino Wiring Diagram

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

### 🧷 Component connections

| Component | Arduino Pin | Notes |
|---|---|---|
| 🔊 Buzzer (+) | D8 | Active buzzer — direct connection |
| 🔊 Buzzer (−) | GND | |
| 🔴 LED anode (+) | D13 | Via 220 Ω resistor |
| 🔴 LED cathode (−) | GND | |
| 🔌 USB | PC | Supplies 5V power + serial |

> For a **passive buzzer**, uncomment the `tone()` / `noTone()` lines in `arduino_code.ino`.

---

## 📤 Arduino Upload Instructions

1. Open **Arduino IDE** (1.8.x or 2.x).
2. Open `arduino_code.ino`.
3. Select **Board**: Tools → Board → Arduino UNO.
4. Select **Port**: Tools → Port → (your COM port, e.g. `COM3` or `/dev/ttyUSB0`).
5. Click **Upload** ( → ).
6. Open Serial Monitor at **9600 baud** — you should see `READY`.

🎉 If you see `READY`, your Arduino is now officially more alert than most humans on a Monday morning.

---

## 🙅 Running Without Arduino

**The system runs completely without Arduino.** No hardware, no problem.

- If no Arduino is detected at startup, the app continues normally.
- All eye tracking, EAR, calibration, face recognition, TTS audio alert, and logging work as usual.
- The Arduino status card shows **"Not Connected"** in grey.
- Clicking **🔌 Connect Arduino** at any time will attempt to find and connect.
- If you plug in an Arduino while the app is running, it auto-reconnects within ~5 seconds.

*Think of Arduino as the system's hype man — great to have, not strictly required for the show to go on.*

---

## ⌨️ Keyboard & UI Guide

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

## 🗂️ Log & Export Files

| File | Contents |
|---|---|
| `logs/events.csv` | Appended on every event (always up to date) |
| `logs/events.xlsx` | Manual export via UI button |
| `data/drivers.db` | SQLite: driver descriptors + full event history |
| `data/calibration.json` | EAR threshold + calibration timestamp |

### 🏷️ Event types logged

| Code | Meaning |
|---|---|
| `DROWSY_ALERT` | 😴 Eye closure exceeded threshold |
| `YAWN` | 🥱 Yawn detected |
| `DRIVER_IN` | 🪪 Driver recognised |
| `DRIVER_REGISTER` | ✍️ New driver enrolled |
| `UNKNOWN_DRIVER` | ❓ Face not matched |
| `CALIBRATION` | 🎯 Threshold saved |
| `SYSTEM` | ⚙️ Start / stop / errors |

---

## 🛠️ Troubleshooting

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

*99 little bugs in the code, 99 little bugs... take one down, patch it around, 127 little bugs in the code.* 🐛

---

## 🚀 Future Enhancements

- [ ] 🧩 **ONNX model integration** — replace MediaPipe with a lightweight custom model for 60+ FPS on CPU.
- [ ] 🌃 **Night-vision mode** — IR camera support + adaptive brightness enhancement.
- [ ] ☁️ **Cloud dashboard** — stream events to Firebase / AWS IoT for fleet monitoring.
- [ ] 👥 **Multi-face support** — alert when any passenger is drowsy.
- [ ] 📊 **Fatigue score** — weighted combination of EAR, MAR, head pose, and blink rate.
- [ ] 📲 **SMS / push alerts** — notify fleet manager via Twilio or Firebase Cloud Messaging.
- [ ] 🍓 **Raspberry Pi port** — deploy on embedded hardware in the vehicle.
- [ ] 📈 **Statistics page** — daily/weekly drowsiness trend charts.
- [ ] 🎙️ **Voice commands** — "dismiss alert", "calibrate" via speech recognition.
- [ ] 🚙 **OBD-II integration** — correlate fatigue with vehicle speed / lane deviation.

---

<div align="center">

### 💡 Pro tip
**The only acceptable place to fall asleep while running this project is in bed, after testing it.**

*Built with ❤️ (and a slightly judgmental webcam) using Python, OpenCV, MediaPipe, CustomTkinter, and Arduino.*

⭐ Stay awake. Stay safe. Star the repo if it kept you from a nap-induced fender bender.

</div>
