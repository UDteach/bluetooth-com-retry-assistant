# ESP32 validation - 2026-06-20

Windows 11 host with three ESP32 boards connected over USB.

## Boards

| USB COM | Bluetooth name | Bluetooth MAC | Expected result |
| --- | --- | --- | --- |
| COM3 | BT-COM-MOCK-A | B4:BF:E9:D4:51:FA | SPP COM appears |
| COM4 | BT-COM-MOCK-B | 70:4B:CA:7C:B1:76 | SPP COM appears |
| COM5 | BT-NO-COM-MOCK | 30:76:F5:B0:31:4E | No Bluetooth COM |

COM3/COM4/COM5 are USB flashing/log ports. They are not the Bluetooth COM ports.

## Firmware

- `BT-COM-MOCK-A` and `BT-COM-MOCK-B`: `hardware/esp32_spp_mock/esp32_spp_mock.ino`
- `BT-NO-COM-MOCK`: `hardware/esp32_no_com_mock/esp32_no_com_mock.ino`
- SPP mock uses SSP no-PIN mode. BluetoothAssistant answers Windows numeric comparison through `BluetoothRegisterForAuthenticationEx` / `BluetoothSendAuthenticationResponseEx`.

## Results

### BT-COM-MOCK-A

Command:

```powershell
.\scripts\run_esp32_pairing_test.ps1 -TargetName BT-COM-MOCK-A -ComWaitSeconds 45 -PollSeconds 3 -PairAttempts 1 -OutputPath .\esp32-pairing-a-auth-callback.json -IUnderstandThisChangesBluetoothPairing
```

Result:

- Pairing succeeded with `numeric comparison accepted`.
- Serial Port service enablement succeeded.
- Bluetooth COM detected: `COM6`.
- Matching PnP id contained `B4BFE9D451FA`.

### BT-COM-MOCK-B

Command:

```powershell
.\scripts\run_esp32_pairing_test.ps1 -TargetName BT-COM-MOCK-B -ComWaitSeconds 45 -PollSeconds 3 -PairAttempts 1 -OutputPath .\esp32-pairing-b-auth-callback.json -IUnderstandThisChangesBluetoothPairing
```

Result:

- Pairing succeeded with `numeric comparison accepted`.
- Serial Port service enablement succeeded.
- Bluetooth COM detected: `COM7`.
- Matching PnP id contained `704BCA7CB176`.

### BT-NO-COM-MOCK

Command:

```powershell
.\scripts\run_esp32_pairing_test.ps1 -TargetName BT-NO-COM-MOCK -ComWaitSeconds 45 -PollSeconds 3 -PairAttempts 1 -OutputPath .\esp32-pairing-no-com-auth-callback.json -IUnderstandThisChangesBluetoothPairing
```

Expected failure:

- Pairing succeeded with `numeric comparison accepted`.
- Serial Port service enablement returned `対象機器は Serial Port Profile を返していません`.
- No matching Bluetooth COM port appeared.
- `hardware_pairing_outcome.ok` and `hardware_pairing_com_after.ok` were `false`, as expected for this firmware.

## Three-device sequence

Before the sequence, all three target Bluetooth addresses were unpaired from Windows:

- `B4:BF:E9:D4:51:FA`
- `70:4B:CA:7C:B1:76`
- `30:76:F5:B0:31:4E`

Then the active pairing test was run in order with one attempt per target.

Command:

```powershell
.\scripts\run_esp32_sequence_test.ps1 -ResetPairing -ComWaitSeconds 45 -PollSeconds 3 -PairAttempts 1 -IUnderstandThisChangesBluetoothPairing
```

| Order | Target | Expected COM | Result | Detail |
| --- | --- | --- | --- | --- |
| 1 | BT-COM-MOCK-A | Yes | PASS | COM6 detected |
| 2 | BT-COM-MOCK-B | Yes | PASS | COM7 detected |
| 3 | BT-NO-COM-MOCK | No | PASS | Stopped after the configured max attempt with no matching COM |

The no-COM step returns a non-zero script exit code because the normal active pairing command defines "COM found" as success. For the sequence test, that non-zero exit is expected and is treated as PASS only because `BT-NO-COM-MOCK` is the explicit negative fixture.
