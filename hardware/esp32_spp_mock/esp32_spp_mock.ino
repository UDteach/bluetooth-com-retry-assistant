// Hardware-backed Bluetooth SPP mock for BluetoothAssistant.
// Flash this to a Bluetooth Classic capable ESP32 board.

#include <Arduino.h>
#include "BluetoothSerial.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled.
#endif

#if !defined(CONFIG_BT_SPP_ENABLED)
#error Bluetooth SPP is not available. Use a Bluetooth Classic capable ESP32 target.
#endif

BluetoothSerial SerialBT;

const char *DEVICE_NAME = "BT-COM-MOCK";

void setup() {
  Serial.begin(115200);
  SerialBT.begin(DEVICE_NAME);

  Serial.println();
  Serial.print("Bluetooth SPP mock started as ");
  Serial.println(DEVICE_NAME);
  Serial.println("Pair this device from Windows Bluetooth settings.");
}

void loop() {
  if (Serial.available()) {
    SerialBT.write(Serial.read());
  }
  if (SerialBT.available()) {
    Serial.write(SerialBT.read());
  }
  delay(20);
}
