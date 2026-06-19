# Windows に見える Bluetooth mock の作り方

## 結論

アプリ内の `--mock` は Windows 設定の Bluetooth 一覧には表示されません。Python アプリだけで「ペアリング済み Bluetooth デバイス」を Windows に安全に偽装する標準 API はありません。

Windows の Bluetooth 一覧、ペアリング、COM ポート作成まで再現するには、実際に Classic Bluetooth SPP を出すテスト機器を用意するのが現実的です。このリポジトリでは ESP32 用のサンプルを用意しています。

## ESP32 SPP mock

必要なもの:

- Bluetooth Classic 対応の ESP32 ボード
  - 推奨: `ESP32-DevKitC` / `ESP-WROOM-32` / `ESP32-WROOM-32E`
  - 避ける: `ESP32-S3` / `ESP32-C3` / `ESP32-C6` / `ESP32-S2`
- Arduino IDE または Arduino CLI
- Arduino ESP32 core

手順:

1. `hardware/esp32_spp_mock/esp32_spp_mock.ino` を ESP32 に書き込みます。
2. Windows の Bluetooth 設定で `BT-COM-MOCK` を探してペアリングします。
3. Bluetooth の詳細設定、またはデバイスマネージャーで COM ポートが作られることを確認します。
4. BluetoothAssistant でスキャンし、表示された MAC をチェックして接続処理を実行します。

この方法は実Bluetooth機器なので、Windows 側のペアリング済みデバイスにも表示されます。アプリの `--mock` とは違い、Windows の状態やペアリング UI の影響を受けます。

## 仮想 COM だけを使う場合

COM ポート検出だけを Windows に見せたい場合は、com0com などの仮想 COM ドライバが選択肢になります。ただし Bluetooth のペアリング一覧や Bluetooth MAC との紐づきは再現しません。

このアプリは COM ポートの `PNPDeviceID` / `hwid` 内に対象 MAC が含まれるかを見ます。一般的な仮想 COM は Bluetooth MAC を持たないため、Bluetooth の完全な再現には向きません。

## なぜ PC だけで Bluetooth ペアリング一覧を偽装しないか

Microsoft の Bluetooth driver stack では、リモート機器やサービスは Bluetooth スタック、BthEnum、BthModem などのドライバ/PnP 層で扱われます。カーネルモードドライバは署名が必要で、配布やインストールの負担も大きくなります。

そのため、このプロジェクトでは次の分担にしています。

- 自動テスト: アプリ内 mock backend でリトライ順序、複数 MAC、COM 出現タイミング、失敗を検証する。
- Windows 統合テスト: ESP32 SPP mock で Windows の Bluetooth 一覧、ペアリング、COM 作成を確認する。

## 参考

- Microsoft Learn: Bluetooth driver stack
  https://learn.microsoft.com/en-us/windows-hardware/drivers/bluetooth/bluetooth-driver-stack
- Microsoft Learn: Windows driver signing tutorial
  https://learn.microsoft.com/en-us/windows-hardware/drivers/install/windows-driver-signing-tutorial
- Microsoft Learn: Serial driver samples
  https://learn.microsoft.com/en-us/windows-hardware/drivers/samples/serial-driver-samples
- Microsoft Learn: GUID_DEVINTERFACE_COMPORT
  https://learn.microsoft.com/en-us/windows-hardware/drivers/install/guid-devinterface-comport
- Espressif Arduino ESP32 BluetoothSerial
  https://docs.espressif.com/projects/arduino-esp32/en/latest/api/bluetooth.html
- Espressif ESP-IDF Bluetooth SPP API
  https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/bluetooth/esp_spp.html
