# ESP32 を買う場合の選び方

BluetoothAssistant の Windows 統合テストに使うなら、Classic Bluetooth SPP が必要です。

## 買ってよい候補

商品名や説明に次のどれかがあるものを選びます。

- `ESP32-DevKitC`
- `ESP-WROOM-32`
- `ESP32-WROOM-32`
- `ESP32-WROOM-32E`
- `ESP32-D0WDQ6`

Amazon.co.jp 検索:

- https://www.amazon.co.jp/esp32-wroom-32/s?k=esp32-wroom-32
- https://www.amazon.co.jp/esp32-devkitc/s?k=esp32+devkitc

## 避ける候補

次の名前が入っているものは、この用途では避けます。

- `ESP32-S3`
- `ESP32-C3`
- `ESP32-C6`
- `ESP32-S2`
- `ESP32-H2`

これらは BLE 用途なら便利ですが、Windows の Bluetooth COM ポート再現に必要な Classic Bluetooth SPP には向きません。

## 動かし方

購入後は `hardware/esp32_spp_mock/esp32_spp_mock.ino` を書き込むと、Windows から `BT-COM-MOCK` という Bluetooth 機器として見えます。

Windowsでペアリングできれば、BluetoothAssistant の実機テストに使えます。
