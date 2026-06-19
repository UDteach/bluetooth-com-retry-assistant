# BluetoothAssistant

Windows で Bluetooth 機器を一覧表示し、選択した機器をペアリングして、対象 MAC アドレスに紐づく COM ポートが出るまで「解除 -> ペアリング -> COM 待ち」を繰り返す Tkinter アプリです。

## 使い方

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py -m bluetooth_assistant
```

実機なしで画面の流れを確認する場合:

```powershell
py -m bluetooth_assistant --mock
```

## 方針

- Bluetooth 一覧で同じ MAC アドレスが複数見える場合は、UI 上で 1 台に統合します。
- スキャンに出ない機器でも、MAC アドレスが分かっていれば `MAC指定` から処理対象に追加できます。
- COM ポートは `Win32_SerialPort` / pySerial の `hwid` / `PNPDeviceID` から MAC アドレスを照合します。
- ペアリング後に Serial Port Profile のサービス有効化を試み、COM ポート作成を促します。
- 実機 Bluetooth は Windows の状態やペアリング UI に依存するため、自動テストでは mock backend でリトライ制御を検証します。

## 画面の設定

- `選択`: クリックしてチェックを付けた機器を、上から順番に処理します。チェックがない場合は、現在選んでいる1台だけを処理します。
- `全選択` / `選択クリア`: 表示中の機器をまとめてチェック、またはチェック解除します。
- `MAC指定`: `AA:BB:CC:DD:EE:FF` 形式で入力した機器を一覧に追加し、チェックを付けます。スキャンに出ないが MAC アドレスは分かる機器向けです。
- `状態`: Windows側のペアリング状態に加えて、連続処理中は `待機中` / `処理中` / `成功` / `失敗` / `停止` を表示します。
- `COM候補`: `COMあり` / `COM候補 高` / `COM候補 中` / `COM候補 低` を表示します。行を選ぶと理由も下部に表示します。
- `ログ`: 何台目を処理しているか、ペアリング中か、COMポート待ちか、成功/失敗したかを時系列で表示します。
- `スキャン秒`: Bluetooth機器を探す目安時間です。Windowsがすぐに結果を返した場合も、この秒数までは再スキャンします。
- `COM作成を促す`: ペアリング後に、Windowsへ「この機器のCOMポートを作って」と依頼します。COMポートが必要なBluetooth機器ではオン推奨です。

接続処理中は、各試行で必ず対象 MAC の接続情報を解除してからペアリングします。古いペアリング情報が残って COM が出ないケースを避けるためです。

## Mock と仮想再現

`--mock` はアプリ内と自動テスト用の mock です。Windows 設定の Bluetooth ペアリング済みデバイスには表示されません。

Windows 側にも見える形で再現したい場合は、次のどちらかを使います。

- `docs/virtual_com_mock.md`: 仮想 COM ドライバで Windows に COM ポートを表示し、その COM 名を `--mock-com-port` でアプリ内 mock に割り当てます。Bluetooth ペアリング一覧は再現しませんが、COM 検出の動きは仮想で確認できます。
- `docs/windows_visible_mock.md`: ESP32 を Classic Bluetooth SPP 機器として動かし、Windows の Bluetooth 一覧、ペアリング、COM ポート生成を再現します。
- `docs/esp32_hardware_test_checklist.md`: ESP32 到着後に実行する順番、成功条件、失敗時の確認点です。
- `docs/research_oss_improvements.md`: OSS/一次情報を調べた結果と、採用/不採用の理由です。

ESP32 実機では `BT-COM-MOCK` で COM が出るパターン、`BT-NO-COM-MOCK` で COM が出ないパターンを分けて確認できます。

mock の MAC や COM 名は起動時に指定できます。

```powershell
py -m bluetooth_assistant --mock --mock-target-address AA:BB:CC:DD:EE:FF --mock-com-port COM98
```

## 注意

- COM ポートが出るのは、機器側が Classic Bluetooth の Serial Port Profile (SPP/RFCOMM) を提供している場合です。BLE 専用デバイスでは通常 COM ポートは出ません。
- ペアリング時は Windows の確認ダイアログや機器側の操作が必要になることがあります。
- 解除は Windows 側のペアリング情報を消す操作です。アプリ内の「解除」またはリトライ中の自動解除を実行する前に対象機器を確認してください。

## テスト

```powershell
pip install -r requirements-dev.txt
py -m ruff check .
py -m unittest discover -s tests
py -m compileall bluetooth_assistant tests
py -m bluetooth_assistant.diagnostics --json --mock-retry
py -m bluetooth_assistant.diagnostics --json --mock-retry --mock-com-port COM98
py -m bluetooth_assistant.diagnostics --json --esp32-check --wait-seconds 90
```

実機に変更を加えない読み取り診断:

```powershell
py -m bluetooth_assistant.diagnostics --json --scan-bluetooth
```

`--scan-bluetooth` は一覧取得だけを行い、ペアリングや解除は実行しません。

ESP32実機で、ペアリング、Windows登録、COM出現まで確認する場合:

```powershell
.\scripts\run_esp32_pairing_test.ps1 -TargetName BT-COM-MOCK -ComWaitSeconds 60 -IUnderstandThisChangesBluetoothPairing
```

このコマンドはWindowsのBluetoothペアリング状態を変更します。通常は管理者権限なしで試し、企業PCポリシーやドライバ操作で拒否される場合だけ管理者権限を検討してください。

## exe ビルド

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
.\scripts\build_exe.ps1
.\dist\BluetoothAssistant.exe --help
```

ビルド成果物は `dist\BluetoothAssistant.exe` です。実機なしの画面確認は次でできます。

```powershell
.\dist\BluetoothAssistant.exe --mock
```

## 参照した一次情報

- Microsoft Learn: Win32 Bluetooth APIs
- Microsoft Learn: `BluetoothAuthenticateDeviceEx`
- Microsoft Learn: `BluetoothRemoveDevice`
- Microsoft Learn: `BluetoothSetServiceState`
- Microsoft Learn: Bluetooth driver stack
- Microsoft Learn: Windows driver signing
- Microsoft Learn: Serial driver samples
- Microsoft Learn: `Win32_SerialPort`
- pySerial documentation: `serial.tools.list_ports`
- Espressif Arduino ESP32 BluetoothSerial
- Espressif ESP-IDF Bluetooth SPP API
