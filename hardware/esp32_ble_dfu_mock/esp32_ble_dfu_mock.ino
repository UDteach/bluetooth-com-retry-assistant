// BLE DFU-shaped mock for BluetoothAssistant profile testing.
// This sketch advertises Nordic Secure DFU-like UUIDs but never performs DFU.
// It does not expose Classic Bluetooth SPP, so Windows should not create a COM port.

#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>

const char *DEVICE_NAME = "BT-BLE-DFU-MOCK";
const char *SECURE_DFU_SERVICE_UUID = "0000FE59-0000-1000-8000-00805F9B34FB";
const char *DFU_CONTROL_POINT_UUID = "8EC90001-F315-4F60-9FB8-838830DAEA50";
const char *DFU_PACKET_UUID = "8EC90002-F315-4F60-9FB8-838830DAEA50";
const char *BUTTONLESS_DFU_UUID = "8EC90003-F315-4F60-9FB8-838830DAEA50";

class DfuWriteCallbacks : public BLECharacteristicCallbacks {
 public:
  explicit DfuWriteCallbacks(const char *label) : label_(label) {}

  void onWrite(BLECharacteristic *characteristic) {
    Serial.print("DFU mock write received on ");
    Serial.println(label_);

    // Nordic-style response frame shape: response code, op code, result.
    // Result 0x0B is operation failed. This keeps the mock non-destructive.
    const uint8_t response[] = {0x60, 0x01, 0x0B};
    characteristic->setValue(response, sizeof(response));
    characteristic->notify();
  }

 private:
  const char *label_;
};

void setup() {
  Serial.begin(115200);
  delay(500);

  BLEDevice::init(DEVICE_NAME);
  BLEServer *server = BLEDevice::createServer();
  BLEService *service = server->createService(SECURE_DFU_SERVICE_UUID);

  BLECharacteristic *controlPoint = service->createCharacteristic(
      DFU_CONTROL_POINT_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_NOTIFY);
  controlPoint->addDescriptor(new BLE2902());
  controlPoint->setCallbacks(new DfuWriteCallbacks("DFU control point"));

  BLECharacteristic *packet = service->createCharacteristic(
      DFU_PACKET_UUID,
      BLECharacteristic::PROPERTY_WRITE);
  packet->setCallbacks(new DfuWriteCallbacks("DFU packet"));

  BLECharacteristic *buttonless = service->createCharacteristic(
      BUTTONLESS_DFU_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_INDICATE);
  buttonless->addDescriptor(new BLE2902());
  buttonless->setCallbacks(new DfuWriteCallbacks("buttonless DFU"));

  service->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SECURE_DFU_SERVICE_UUID);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println();
  Serial.print("BLE DFU-shaped mock started as ");
  Serial.println(DEVICE_NAME);
  Serial.print("Advertising Secure DFU service UUID ");
  Serial.println(SECURE_DFU_SERVICE_UUID);
  Serial.println("This mock intentionally does not expose Classic Bluetooth SPP.");
  Serial.println("Windows should not create a COM port for this device.");
}

void loop() {
  delay(1000);
}
