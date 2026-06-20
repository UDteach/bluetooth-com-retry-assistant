// Classic Bluetooth visible mock with DFU/no-COM naming hints.
// This sketch is useful when Windows/app discovery must see a Bluetooth row,
// but no Serial Port Profile should be exposed and no COM port should appear.

#include <Arduino.h>
#include "esp_bt.h"
#include "esp_bt_device.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"
#include "esp32-hal-bt.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled.
#endif

const char *DEVICE_NAME = "BT-DFU-NO-COM-MOCK";

void gapCallback(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param) {
  (void)event;
  (void)param;
}

void setupClassicBluetoothWithoutSpp() {
  if (!btStarted() && !btStart()) {
    Serial.println("Bluetooth controller start failed");
    return;
  }

  esp_bluedroid_status_t btState = esp_bluedroid_get_status();
  if (btState == ESP_BLUEDROID_STATUS_UNINITIALIZED) {
    esp_err_t result = esp_bluedroid_init();
    if (result != ESP_OK) {
      Serial.printf("Bluedroid init failed: %s\n", esp_err_to_name(result));
      return;
    }
  }

  if (btState != ESP_BLUEDROID_STATUS_ENABLED) {
    esp_err_t result = esp_bluedroid_enable();
    if (result != ESP_OK) {
      Serial.printf("Bluedroid enable failed: %s\n", esp_err_to_name(result));
      return;
    }
  }

  esp_err_t result = esp_bt_gap_register_callback(gapCallback);
  if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
    Serial.printf("Bluetooth GAP callback register failed: %s\n", esp_err_to_name(result));
    return;
  }

  esp_bt_dev_set_device_name(DEVICE_NAME);

  esp_bt_cod_t cod = {};
  cod.major = 0b00001;
  cod.minor = 0b000100;
  cod.service = 0b00000010110;
  result = esp_bt_gap_set_cod(cod, ESP_BT_INIT_COD);
  if (result != ESP_OK) {
    Serial.printf("Bluetooth class of device set failed: %s\n", esp_err_to_name(result));
  }

  result = esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
  if (result != ESP_OK) {
    Serial.printf("Bluetooth scan mode set failed: %s\n", esp_err_to_name(result));
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.print("Classic DFU/no-COM hint mock started as ");
  Serial.println(DEVICE_NAME);
  Serial.println("This sketch intentionally does not start SPP.");
  Serial.println("It only uses the name to simulate a firmware/DFU-looking no-COM device.");

  setupClassicBluetoothWithoutSpp();
}

void loop() {
  delay(1000);
}
