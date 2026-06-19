// Hardware-backed Bluetooth mock that should not expose an SPP COM port.
// Flash this to a Bluetooth Classic capable ESP32 board.

#include <Arduino.h>
#include "esp_bt.h"
#include "esp_bt_device.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled.
#endif

const char *DEVICE_NAME = "BT-NO-COM-MOCK";

void setupClassicBluetoothWithoutSpp() {
  esp_err_t result = esp_bt_controller_mem_release(ESP_BT_MODE_BLE);
  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
    Serial.printf("BLE memory release failed: %s\n", esp_err_to_name(result));
  }

  esp_bt_controller_config_t btConfig = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  result = esp_bt_controller_init(&btConfig);
  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
    Serial.printf("Bluetooth controller init failed: %s\n", esp_err_to_name(result));
    return;
  }

  result = esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT);
  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
    Serial.printf("Bluetooth controller enable failed: %s\n", esp_err_to_name(result));
    return;
  }

  result = esp_bluedroid_init();
  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
    Serial.printf("Bluedroid init failed: %s\n", esp_err_to_name(result));
    return;
  }

  result = esp_bluedroid_enable();
  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
    Serial.printf("Bluedroid enable failed: %s\n", esp_err_to_name(result));
    return;
  }

  esp_bt_gap_set_device_name(DEVICE_NAME);
  esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
}

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.print("Bluetooth no-COM mock started as ");
  Serial.println(DEVICE_NAME);
  Serial.println("This sketch intentionally does not start SPP.");
  Serial.println("Windows may show the Bluetooth device, but it should not create a COM port.");

  setupClassicBluetoothWithoutSpp();
}

void loop() {
  delay(1000);
}
