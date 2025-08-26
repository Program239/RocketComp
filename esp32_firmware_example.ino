
// ESP32 example firmware for the dashboard
// Works with Arduino IDE / Arduino-ESP32 core.
// Protocol examples the app understands:
//   CSV:   27.53,63.1
//   LBL:   TEMP:27.53,HUM:63.1
//   JSON:  {"temp":27.53,"hum":63.1}
// App will also send:
//   READ\n  -> respond with one sensor line
//   PWM:<0-255>\n  -> set PWM duty (example pin)

#include <Arduino.h>

// Fake sensors (replace with your real sensors)
float readTempC() {
  // TODO: return actual temperature
  return 25.0 + (millis() % 1000) / 100.0; // varies 25.00 - 34.99
}
float readHum() {
  // TODO: return actual humidity
  return 50.0 + (millis() % 500) / 10.0; // varies a bit
}

const int PWM_PIN = 5; // change as needed
int pwmValue = 0;

void setup() {
  Serial.begin(115200);
  // Configure PWM pin (ledc on ESP32)
  ledcSetup(0, 5000 /*Hz*/, 8 /*bits*/);
  ledcAttachPin(PWM_PIN, 0);
  ledcWrite(0, pwmValue);
}

void loop() {
  // Respond to host polling
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.equalsIgnoreCase("READ")) {
      float t = readTempC();
      float h = readHum();
      // Choose ONE format; here we use labeled:
      Serial.print("TEMP:");
      Serial.print(t, 2);
      Serial.print(",HUM:");
      Serial.println(h, 2);
    } else if (line.startsWith("PWM:")) {
      int val = line.substring(4).toInt();
      val = constrain(val, 0, 255);
      pwmValue = val;
      ledcWrite(0, pwmValue);
      Serial.print("ACK PWM:");
      Serial.println(pwmValue);
    } else {
      Serial.print("ECHO:");
      Serial.println(line);
    }
  }

  // Optional: periodic push updates (uncomment to stream at 1 Hz)
  // static uint32_t last = 0;
  // if (millis() - last > 1000) {
  //   last = millis();
  //   float t = readTempC();
  //   float h = readHum();
  //   Serial.print("TEMP:");
  //   Serial.print(t, 2);
  //   Serial.print(",HUM:");
  //   Serial.println(h, 2);
  // }
}
