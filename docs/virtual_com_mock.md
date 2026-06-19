# 仮想 COM でテストモードを Windows に近づける

## できること

仮想 COM ドライバで Windows に `COM98` などのポートを表示させ、その COM 名を BluetoothAssistant のテストモード成功ポートとして使えます。

これで確認できること:

- アプリの一覧、選択、ログ、状態表示
- 指定 MAC に対する `解除 -> ペアリング -> COM待ち` の繰り返し
- COM が出た扱いになった時に、対象機器の処理が成功で止まること
- exe 版でも同じテストモード指定で起動できること

できないこと:

- Windows 設定の Bluetooth ペアリング済みデバイス一覧に、仮想 Bluetooth 機器を表示すること
- Windows Bluetooth スタックの実ペアリング UI を完全再現すること

## 使い方

1. 任意の仮想 COM ドライバで `COM98` などのポートを作ります。
   - 例: com0com などの null-modem virtual COM driver
   - ドライバ導入は管理者権限や署名要件が絡むため、このアプリから自動インストールしません。
2. Windows から COM が見えるか確認します。

```powershell
.\scripts\check_virtual_com.ps1 -PortName COM98
```

3. アプリをテストモード + 仮想 COM 名で起動します。

```powershell
py -m bluetooth_assistant --mock --mock-target-address AA:BB:CC:DD:EE:FF --mock-com-port COM98
```

exe 版では次のように起動します。

```powershell
.\dist\BluetoothAssistant.exe --mock --mock-target-address AA:BB:CC:DD:EE:FF --mock-com-port COM98
```

4. 一覧に出る `テスト用 COM 機器` をチェックして、`接続してCOMを探す` を押します。

デフォルトでは2回目のペアリング後に `COM98` が出た扱いになります。タイミングを変えたい場合:

```powershell
py -m bluetooth_assistant --mock --mock-com-port COM98 --mock-appear-after 5
```

## 診断だけ実行する

```powershell
py -m bluetooth_assistant.diagnostics --json --mock-retry --mock-com-port COM98
```

この診断は実Bluetoothのペアリングや解除を行いません。テスト用バックエンドの中で `解除 -> ペアリング -> COM待ち` の順序を検証します。

## なぜ Bluetooth ペアリング一覧までは仮想化しないか

Windows の Bluetooth 一覧に表示されるリモート機器やサービスは、Windows Bluetooth driver stack と PnP/ドライバ層で扱われます。Python アプリだけで安全に偽のペアリング済み Bluetooth 機器を登録する標準 API はありません。

完全に仮想化するには、仮想 Bluetooth アダプタ、仮想リモートデバイス、または独自ドライバが必要になります。これは署名済みカーネルドライバ、管理者権限、テスト署名、配布時のセキュリティ確認が必要になるため、このアプリの通常機能には含めません。
