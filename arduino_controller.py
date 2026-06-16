"""
arduino_controller.py
─────────────────────────────────────────────
Manages serial communication with an Arduino UNO for the buzzer / LED alert.

• Auto-detects the Arduino port across Windows / Linux / macOS
• Gracefully degrades when Arduino is absent — the rest of the app keeps running
• Background reconnect loop re-attaches if Arduino is plugged in later
• Thread-safe command queue so callers never block
"""

import logging
import queue
import threading
import time
from typing import Callable, List, Optional

import config

_log = logging.getLogger("Arduino")

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    _log.warning("pyserial not installed — Arduino support disabled")


# ── helper: find Arduino port ─────────────────────────────────────────────

def find_arduino_port() -> Optional[str]:
    """
    Scan available serial ports and return the most likely Arduino port.
    Matches USB VID/PID for common Arduino boards, then falls back to
    description string matching.
    """
    if not SERIAL_AVAILABLE:
        return None

    ARDUINO_VIDS = {0x2341, 0x1A86, 0x0403, 0x10C4}   # official + CH340 + FTDI + CP210x

    for port in serial.tools.list_ports.comports():
        if port.vid in ARDUINO_VIDS:
            _log.info("Found Arduino by VID %04X on %s", port.vid, port.device)
            return port.device
        desc = (port.description or "").lower()
        if any(k in desc for k in ("arduino", "ch340", "ch341", "cp210", "ftdi")):
            _log.info("Found Arduino by description '%s' on %s",
                      port.description, port.device)
            return port.device
    return None


# ── main controller ───────────────────────────────────────────────────────

class ArduinoController:
    """
    Thread-safe controller for the Arduino alert unit.

    Public API
    ──────────
    connect()          — attempt initial connection
    disconnect()       — cleanly close port
    send_alert_on()    — tell Arduino to activate buzzer + LED
    send_alert_off()   — tell Arduino to deactivate
    is_connected       — property
    port_name          — property (empty string if disconnected)
    """

    def __init__(
        self,
        on_connect: Optional[Callable[[str], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_connect    = on_connect
        self._on_disconnect = on_disconnect

        self._ser: Optional["serial.Serial"] = None
        self._lock          = threading.Lock()
        self._cmd_queue: queue.Queue[str] = queue.Queue()
        self._connected     = False
        self._port_name     = ""
        self._alert_active  = False

        # Background threads
        self._writer_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running       = False

    # ── properties ───────────────────────────────────────────────────────
    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port_name(self) -> str:
        return self._port_name

    @property
    def alert_active(self) -> bool:
        return self._alert_active

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        """Start background threads; call once at app startup."""
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="ArduinoWriter"
        )
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="ArduinoMonitor"
        )
        self._writer_thread.start()
        self._monitor_thread.start()
        _log.info("ArduinoController started")

    def stop(self) -> None:
        self._running = False
        self.send_alert_off()
        time.sleep(0.3)
        self.disconnect()

    def connect(self, port: str = "") -> bool:
        """
        Try to connect to Arduino on `port`.
        If port is empty, auto-detect.
        Returns True on success.
        """
        if not SERIAL_AVAILABLE:
            _log.warning("Cannot connect — pyserial not available")
            return False

        target_port = port or config.ARDUINO_PORT or find_arduino_port()
        if not target_port:
            _log.debug("No Arduino port found")
            return False

        with self._lock:
            if self._connected:
                return True
            try:
                ser = serial.Serial(
                    port=target_port,
                    baudrate=config.ARDUINO_BAUD_RATE,
                    timeout=config.ARDUINO_TIMEOUT,
                )
                time.sleep(2)           # allow Arduino bootloader to settle
                self._ser        = ser
                self._connected  = True
                self._port_name  = target_port
                _log.info("Arduino connected on %s @ %d baud",
                          target_port, config.ARDUINO_BAUD_RATE)
                if self._on_connect:
                    threading.Thread(
                        target=self._on_connect, args=(target_port,),
                        daemon=True
                    ).start()
                return True
            except serial.SerialException as exc:
                _log.debug("Serial connect failed (%s): %s", target_port, exc)
                return False

    def disconnect(self) -> None:
        with self._lock:
            if self._ser:
                try:
                    self._ser.close()
                except Exception:                   # noqa: BLE001
                    pass
                self._ser = None
            if self._connected:
                self._connected = False
                self._port_name = ""
                _log.info("Arduino disconnected")
                if self._on_disconnect:
                    threading.Thread(
                        target=self._on_disconnect, daemon=True
                    ).start()

    # ── alert commands ────────────────────────────────────────────────────
    def send_alert_on(self) -> None:
        if not self._alert_active:
            self._alert_active = True
            self._cmd_queue.put(config.CMD_ALERT_ON)
            _log.info("ALERT ON queued")

    def send_alert_off(self) -> None:
        if self._alert_active:
            self._alert_active = False
            self._cmd_queue.put(config.CMD_ALERT_OFF)
            _log.info("ALERT OFF queued")

    def send_raw(self, cmd: str) -> None:
        self._cmd_queue.put(cmd)

    # ── background loops ─────────────────────────────────────────────────
    def _writer_loop(self) -> None:
        """Drain the command queue and write to serial."""
        while self._running:
            try:
                cmd = self._cmd_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._lock:
                if not self._connected or not self._ser:
                    continue
                try:
                    self._ser.write(cmd.encode())
                    self._ser.flush()
                except serial.SerialException as exc:
                    _log.warning("Serial write error: %s — disconnecting", exc)
                    self._connected = False     # monitor will re-connect

    def _monitor_loop(self) -> None:
        """Periodically check connection; auto-reconnect if unplugged."""
        while self._running:
            time.sleep(config.ARDUINO_RETRY_INTERVAL)
            if self._connected:
                # Verify port still alive
                with self._lock:
                    if self._ser and not self._ser.is_open:
                        _log.warning("Arduino port closed unexpectedly — reconnecting")
                        self._connected = False
                        self._port_name = ""
                        if self._on_disconnect:
                            threading.Thread(
                                target=self._on_disconnect, daemon=True
                            ).start()
            else:
                # Try to reconnect
                if config.ARDUINO_AUTO_DETECT or config.ARDUINO_PORT:
                    _log.debug("Attempting Arduino reconnect …")
                    self.connect()


# ── module-level singleton ─────────────────────────────────────────────────
arduino = ArduinoController()
