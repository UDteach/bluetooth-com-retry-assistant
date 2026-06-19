# BluetoothAssistant

Windows で Bluetooth 機器を一覧表示し、選択した機器をペアリングして、対象 MAC アドレスに紐づく COM ポートが出るまで「ペアリング -> COM 待ち -> 解除」を繰り返す Tkinter アプリです。

## 使い方

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py -m bluetooth_assistant
```

## 方針

- Bluetooth 一覧で同じ MAC アドレスが複数見える場合は、UI 上で 1 台に統合します。
- COM ポートは `Win32_SerialPort` / pySerial の `hwid` / `PNPDeviceID` から MAC アドレスを照合します。
- ペアリング後に Serial Port Profile のサービス有効化を試み、COM ポート作成を促します。
- 実機 Bluetooth は Windows の状態やペアリング UI に依存するため、自動テストでは mock backend でリトライ制御を検証します。

## 注意

- COM ポートが出るのは、機器側が Classic Bluetooth の Serial Port Profile (SPP/RFCOMM) を提供している場合です。BLE 専用デバイスでは通常 COM ポートは出ません。
- ペアリング時は Windows の確認ダイアログや機器側の操作が必要になることがあります。
- 解除は Windows 側のペアリング情報を消す操作です。アプリ内の「解除」またはリトライ中の自動解除を実行する前に対象機器を確認してください。

## テスト

```powershell
py -m unittest discover -s tests
py -m compileall bluetooth_assistant tests
```

## 参照した一次情報

- Microsoft Learn: Win32 Bluetooth APIs
- Microsoft Learn: `BluetoothAuthenticateDeviceEx`
- Microsoft Learn: `BluetoothRemoveDevice`
- Microsoft Learn: `BluetoothSetServiceState`
- Microsoft Learn: `Win32_SerialPort`
- pySerial documentation: `serial.tools.list_ports`
