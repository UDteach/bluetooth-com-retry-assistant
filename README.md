# BluetoothAssistant

Windows で Bluetooth 機器を一覧表示し、選択した機器をペアリングして、対象 MAC アドレスに紐づく COM ポートが出るまで「ペアリング -> COM 待ち -> 解除」を繰り返す Tkinter アプリです。

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
- COM ポートは `Win32_SerialPort` / pySerial の `hwid` / `PNPDeviceID` から MAC アドレスを照合します。
- ペアリング後に Serial Port Profile のサービス有効化を試み、COM ポート作成を促します。
- 実機 Bluetooth は Windows の状態やペアリング UI に依存するため、自動テストでは mock backend でリトライ制御を検証します。

## 画面の設定

- `選択`: クリックしてチェックを付けた機器を、上から順番に処理します。チェックがない場合は、現在選んでいる1台だけを処理します。
- `全選択` / `選択クリア`: 表示中の機器をまとめてチェック、またはチェック解除します。
- `状態`: Windows側のペアリング状態に加えて、連続処理中は `待機中` / `処理中` / `成功` / `失敗` / `停止` を表示します。
- `ログ`: 何台目を処理しているか、ペアリング中か、COMポート待ちか、成功/失敗したかを時系列で表示します。
- `スキャン秒`: Bluetooth機器を探す目安時間です。Windowsがすぐに結果を返した場合も、この秒数までは再スキャンします。
- `最初に接続情報を消す`: 1回目のペアリング前に、Windows側に残っている対象機器の登録情報を消します。同じ機器が何度も失敗する時向けです。迷う場合はオフで大丈夫です。
- `COM作成を促す`: ペアリング後に、Windowsへ「この機器のCOMポートを作って」と依頼します。COMポートが必要なBluetooth機器ではオン推奨です。

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
```

実機に変更を加えない読み取り診断:

```powershell
py -m bluetooth_assistant.diagnostics --json --scan-bluetooth
```

`--scan-bluetooth` は一覧取得だけを行い、ペアリングや解除は実行しません。

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
- Microsoft Learn: `Win32_SerialPort`
- pySerial documentation: `serial.tools.list_ports`
