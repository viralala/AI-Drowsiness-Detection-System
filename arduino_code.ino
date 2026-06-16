/*
 * arduino_code.ino
 * ─────────────────────────────────────────────────────────────
 * AI Driver Drowsiness Detection System — Arduino Firmware
 *
 * Hardware
 * ────────
 *  • Buzzer  →  Digital Pin 8
 *  • LED     →  Digital Pin 13 (onboard LED also activates)
 *
 * Serial Protocol (9600 baud, newline-terminated)
 * ───────────────────────────────────────────────
 *  PC → Arduino  :  "ALERT_ON\n"   → buzzer ON  + LED ON
 *                   "ALERT_OFF\n"  → buzzer OFF + LED OFF
 *                   "PING\n"       → responds "PONG\n" (health-check)
 *
 * Wiring
 * ──────
 *  Buzzer  (+) → Pin 8   |  Buzzer  (-) → GND
 *  LED     (+) → Pin 13 via 220Ω resistor  |  LED (-) → GND
 *
 *  (For active buzzer: directly to pin 8 and GND)
 *  (For passive buzzer: tone() is used instead of digitalWrite)
 *
 * ─────────────────────────────────────────────────────────────
 */

// ── Pin definitions ──────────────────────────────────────────
const int BUZZER_PIN = 8;
const int LED_PIN    = 13;

// ── Buzzer tone (Hz) — only used for passive buzzers ─────────
const int ALERT_TONE_HZ = 2400;

// ── State ────────────────────────────────────────────────────
bool alertActive = false;

// ── Serial buffer ─────────────────────────────────────────────
String inputBuffer = "";

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  Serial.setTimeout(100);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN,    OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN,    LOW);

  // Brief startup blink so we know the board is alive
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(120);
    digitalWrite(LED_PIN, LOW);
    delay(120);
  }

  Serial.println("READY");   // tell Python we are up
}

// ─────────────────────────────────────────────────────────────
void loop() {
  // ── Read serial commands ────────────────────────────────────
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else {
      inputBuffer += c;
      if (inputBuffer.length() > 32) inputBuffer = "";  // overflow guard
    }
  }

  // ── Alert pattern ───────────────────────────────────────────
  if (alertActive) {
    // Pulse LED + buzzer at ~4 Hz
    unsigned long t = millis();
    if ((t / 125) % 2 == 0) {
      digitalWrite(LED_PIN, HIGH);
      // Uncomment for PASSIVE buzzer:
      // tone(BUZZER_PIN, ALERT_TONE_HZ);
      // For ACTIVE buzzer:
      digitalWrite(BUZZER_PIN, HIGH);
    } else {
      digitalWrite(LED_PIN, LOW);
      // noTone(BUZZER_PIN);   // passive buzzer
      digitalWrite(BUZZER_PIN, LOW);
    }
  }
}

// ─────────────────────────────────────────────────────────────
void processCommand(String cmd) {
  cmd.trim();

  if (cmd == "ALERT_ON") {
    alertActive = true;
    Serial.println("ACK_ALERT_ON");

  } else if (cmd == "ALERT_OFF") {
    alertActive = false;
    digitalWrite(BUZZER_PIN, LOW);
    // noTone(BUZZER_PIN);   // passive buzzer
    digitalWrite(LED_PIN, LOW);
    Serial.println("ACK_ALERT_OFF");

  } else if (cmd == "PING") {
    Serial.println("PONG");

  } else if (cmd.length() > 0) {
    Serial.print("UNKNOWN:");
    Serial.println(cmd);
  }
}
