// Hardware-backed Bluetooth SPP mock for BluetoothAssistant.
// Flash this to a Bluetooth Classic capable ESP32 board.

#include <Arduino.h>
#include "BluetoothSerial.h"
#include "esp_gap_bt_api.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled.
#endif

#if !defined(CONFIG_BT_SPP_ENABLED)
#error Bluetooth SPP is not available. Use a Bluetooth Classic capable ESP32 target.
#endif

BluetoothSerial SerialBT;

#ifndef BT_DEVICE_NAME
#define BT_DEVICE_NAME "BT-COM-MOCK"
#endif

const char *DEVICE_NAME = BT_DEVICE_NAME;

void setup() {
  Serial.begin(115200);
  SerialBT.enableSSP();
  SerialBT.begin(DEVICE_NAME);
  esp_bt_io_cap_t ioCapability = ESP_BT_IO_CAP_NONE;
  esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &ioCapability, sizeof(ioCapability));

  Serial.println();
  Serial.print("Bluetooth SPP mock started as ");
  Serial.println(DEVICE_NAME);
  Serial.println("SSP no-PIN mode is enabled.");
  Serial.println("Pair this device from Windows Bluetooth settings or BluetoothAssistant.");
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
