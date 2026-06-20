# ESP32 実機テストチェックリスト

## 0. 前提

対象ボード:

- 推奨: `ESP32-DevKitC` / `ESP-WROOM-32` / `ESP32-WROOM-32E`
- 避ける: `ESP32-S3` / `ESP32-C3` / `ESP32-C6` / `ESP32-S2`

理由: Windows の Bluetooth COM ポート再現には Classic Bluetooth SPP が必要です。

## 1. ESP32 に COM が出るスケッチを書き込む

1. Arduino IDE で `hardware/esp32_spp_mock/esp32_spp_mock.ino` を開く。
2. Board は `ESP32 Dev Module` または購入ボードに合う ESP32 系を選ぶ。
3. Upload する。
4. Serial Monitor を `115200` baud で開く。
5. 次の表示を確認する。

```text
Bluetooth SPP mock started as BT-COM-MOCK
SSP no-PIN mode is enabled.
Pair this device from Windows Bluetooth settings or BluetoothAssistant.
```

Arduino CLIで全ESP32スケッチを先にビルド確認する場合:

```powershell
.\scripts\setup_esp32_arduino_cli.ps1
.\scripts\compile_esp32_sketches.ps1
```

PlatformIOやArduino CLIでビルドする場合、日本語を含むパスでESP32ツールチェーンが失敗することがあります。その場合は `C:\ba_esp32\...` のような英数字だけの一時フォルダへスケッチを置いてビルドしてください。

## 2. Windows の Bluetooth 一覧で見えるか確認する

ESP32をPCの近くに置いて、次を実行します。

```powershell
.\scripts\run_esp32_hardware_check.ps1 -WaitSeconds 90
```

成功条件:

- `hardware_wait.ok` が `true`
- `expect_device_name.ok` が `true`
- `BT-COM-MOCK` が `matches` に出る

失敗したら:

- ESP32のRSTボタンを押す
- WindowsのBluetoothを一度オフ/オンする
- ESP32をPCに近づける
- 以前の `BT-COM-MOCK` ペアリングをWindows設定から削除する

## 3. MAC アドレスを控える

診断JSONの `expect_device_name.data.matches[0].address` を控えます。

例:

```text
AA:BB:CC:DD:EE:FF
```

このMACはアプリの `MAC指定` 欄にも使えます。

## 4. Windows でペアリングして COM を確認する

通常のBluetoothペアリングは、まず管理者権限なしで試します。企業PCのポリシーやドライバ操作が絡む場合だけ管理者権限が必要になることがあります。

手動確認をする場合は、COM差分監視を開始してから、Windowsで `BT-COM-MOCK` をペアリングします。

```powershell
.\scripts\watch_com_delta.ps1 -ExpectNew -WaitSeconds 90 -OutputPath .\esp32-com-positive.json
```

この監視は `Win32_SerialPort` と Windows の PnP Ports の両方を見ます。USB書き込み用の `COM3` などが既にある状態をベースラインにして、Bluetoothペアリング後に増えたCOMだけを `new_ports` に出します。

別の操作:

1. Windowsの Bluetooth 設定を開く。
2. `BT-COM-MOCK` をペアリングする。
3. `watch_com_delta.ps1` が `new_ports` を出すことを確認する。

すでにペアリング済みの場合は、Windows設定で一度 `BT-COM-MOCK` を削除してからやり直します。

デバイスマネージャー、または次のコマンドでも COM を確認できます。

```powershell
.\scripts\check_virtual_com.ps1
```

COMが `COM12` などとして見えたら、その名前を控えます。

## 5. アプリ経由でペアリング、Windows登録、COM出現をまとめて確認する

このコマンドはWindowsのBluetoothペアリング状態を変更します。`BT-COM-MOCK` が1台だけ見えている状態で実行します。

```powershell
.\scripts\run_esp32_pairing_test.ps1 -TargetName BT-COM-MOCK -ComWaitSeconds 60 -IUnderstandThisChangesBluetoothPairing
```

PIN不要の SSP 機器では、アプリが Windows の認証コールバックに自動応答します。成功時のログには `numeric comparison accepted` が出ます。

Windows がユーザー承認を要求する環境では、右下に「デバイスの追加」通知が出たり、CLIだけのペアリングが `1244 (ユーザーが認証されていない...)` で拒否されたりすることがあります。その場合は Windows 側の同意確認です。Windows設定画面またはアプリ本体で確認しながら、手順4のCOM差分監視で確認してください。

成功条件:

- `hardware_pairing_resolve_target.ok` が `true`
- `hardware_pairing_event_*` に `numeric comparison accepted` が出る
- `hardware_pairing_outcome.ok` が `true`
- `hardware_pairing_windows_registered.ok` が `true`
- `hardware_pairing_com_after.ok` が `true`

同じ名前が複数出る場合は、先にMACを控えてから `-TargetAddress` を使います。

```powershell
.\scripts\run_esp32_pairing_test.ps1 -TargetAddress AA:BB:CC:DD:EE:FF -ComWaitSeconds 60 -IUnderstandThisChangesBluetoothPairing
```

## 6. MAC と COM を指定して再確認する

控えた値に置き換えて実行します。

```powershell
.\scripts\run_esp32_hardware_check.ps1 -Address AA:BB:CC:DD:EE:FF -ComPort COM12 -WaitSeconds 60
```

成功条件:

- `expect_device_name.ok` が `true`
- `expect_device_address.ok` が `true`
- `expect_com_port.ok` が `true`

## 7. 3台連続で確認する

ESP32 A/B/NO-COM をまとめて確認する場合:

```powershell
.\scripts\run_esp32_sequence_test.ps1 -ResetPairing -IUnderstandThisChangesBluetoothPairing
```

デフォルトの期待値:

- `BT-COM-MOCK-A`: COM が出る
- `BT-COM-MOCK-B`: COM が出る
- `BT-NO-COM-MOCK`: COM が出ない

`BT-NO-COM-MOCK` は通常のペアリングテストとしては失敗終了しますが、この連続テストでは「COM が出ないこと」が期待値なので PASS 扱いです。

## 8. アプリ本体で確認する

```powershell
py -m bluetooth_assistant
```

確認すること:

- スキャンで `BT-COM-MOCK-A` / `BT-COM-MOCK-B` / `BT-NO-COM-MOCK` が見える
- `COM候補` 列が `✓ COMあり` または `▲ COM候補 高` になる
- `プロファイル候補` 列で、COMが出る機器は `✓ SPP/COM` または `↔ SPP/COM候補` になる
- `点数` 列でCOMが出そうな候補ほど高く表示される
- 同じMACが複数行に出た場合、それぞれ別行として表示される
- `MAC指定` に控えたMACを入れて追加できる
- チェックして `接続してCOMを探す` を押す
- ログに `解除 -> ペアリング -> COM待ち` の流れが出る
- COMが出たら成功になり、次の機器へ進む

## 9. 結果を残す

診断結果はデフォルトで次に保存されます。

```text
esp32-hardware-check.json
```

うまくいかない時は、このJSONとアプリのログ欄の内容を見れば原因を追いやすくなります。

## 10. COM が出ないパターンを明示的に作る

COMが出ないテストは、別スケッチを使います。

1. Arduino IDE で `hardware/esp32_no_com_mock/esp32_no_com_mock.ino` を開く。
2. ESP32へUploadする。
3. Serial Monitor `115200` baudで次を確認する。

```text
Bluetooth no-COM mock started as BT-NO-COM-MOCK
This sketch intentionally does not start SPP.
```

4. Bluetooth一覧に見えるか確認する。

```powershell
.\scripts\run_esp32_hardware_check.ps1 -DeviceName BT-NO-COM-MOCK -WaitSeconds 90 -OutputPath .\esp32-no-com-device.json
```

5. COMが増えないことを確認する。次を実行してから、Windowsで `BT-NO-COM-MOCK` をペアリングします。

```powershell
.\scripts\watch_com_delta.ps1 -ExpectNoNew -WaitSeconds 90 -OutputPath .\esp32-no-com-negative.json
```

成功条件:

- `esp32-no-com-device.json` で `expect_device_name.ok` が `true`
- `esp32-no-com-negative.json` で `ok` が `true`
- `new_ports` が空

これで「Bluetoothには見えるがCOMは出ない」ケースを明示的に再現できます。

アプリ経由で negative case を確認する場合:

```powershell
.\scripts\run_esp32_pairing_test.ps1 -TargetName BT-NO-COM-MOCK -ComWaitSeconds 45 -IUnderstandThisChangesBluetoothPairing
```

このケースは `対象機器は Serial Port Profile を返していません` と出て、`hardware_pairing_outcome.ok` / `hardware_pairing_com_after.ok` が `false` なら期待通りです。
