from __future__ import annotations

import argparse
import math
import queue
import threading
import time
import tkinter as tk
from collections import Counter, defaultdict
from dataclasses import dataclass
from tkinter import messagebox, ttk

from .com_candidate import assess_com_candidate
from .mock_backend import MockBluetoothBackend
from .models import BluetoothDevice, ComPortInfo, find_matching_ports, normalize_address
from .profile_candidate import assess_profile_candidate
from .retry import BluetoothBackend, PairingRetrier, RetryConfig, RetryEvent
from .windows_bluetooth import BluetoothError, UnsupportedPlatformError, WindowsBluetoothBackend

BLUETOOTH_INQUIRY_UNIT_SECONDS = 1.28
DEFAULT_SCAN_SECONDS = 10


def timeout_multiplier_from_seconds(seconds: int) -> int:
    return max(1, min(48, math.ceil(max(1, seconds) / BLUETOOTH_INQUIRY_UNIT_SECONDS)))


def window_title_for_mode(mock_mode: bool) -> str:
    if mock_mode:
        return "BluetoothAssistant - テストモード"
    return "BluetoothAssistant"


def format_status_text(message: str, *, mock_mode: bool = False) -> str:
    prefix = "テストモード / " if mock_mode else ""
    return f"状態: {prefix}{message}"


def manual_device_from_address(address: str) -> BluetoothDevice:
    return BluetoothDevice(normalize_address(address), name="手入力", remembered=True, last_seen="手入力")


@dataclass(frozen=True, slots=True)
class DeviceDisplayRow:
    row_id: str
    device: BluetoothDevice
    same_address_count: int


def devices_with_manual_devices(
    devices: list[BluetoothDevice],
    manual_devices: dict[str, BluetoothDevice],
) -> list[BluetoothDevice]:
    return sorted(
        [*devices, *manual_devices.values()],
        key=lambda device: (device.address, device.name.lower(), device.last_seen, device.last_used),
    )


def build_device_display_rows(
    devices: list[BluetoothDevice],
    ports: list[ComPortInfo],
) -> list[DeviceDisplayRow]:
    counts = Counter(device.address for device in devices)
    occurrence_by_address: defaultdict[str, int] = defaultdict(int)
    rows: list[DeviceDisplayRow] = []
    for device in devices:
        occurrence_by_address[device.address] += 1
        row_id = f"{device.address}#{occurrence_by_address[device.address]}"
        rows.append(DeviceDisplayRow(row_id, device, counts[device.address]))

    return sorted(
        rows,
        key=lambda row: (
            -assess_com_candidate(
                row.device,
                ports,
                same_address_count=row.same_address_count,
            ).score,
            -assess_profile_candidate(row.device, ports).score,
            row.device.address,
            row.device.name.lower(),
            row.row_id,
        ),
    )


def _dedupe_devices_by_address(devices: list[BluetoothDevice]) -> list[BluetoothDevice]:
    selected: dict[str, BluetoothDevice] = {}
    for device in devices:
        selected.setdefault(device.address, device)
    return list(selected.values())


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _show(self, _event: tk.Event) -> None:
        if self._window is not None:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            self._window,
            text=self.text,
            justify=tk.LEFT,
            relief=tk.SOLID,
            borderwidth=1,
            padding=(8, 6),
            background="#ffffe8",
            wraplength=360,
        )
        label.pack()

    def _hide(self, _event: tk.Event | None = None) -> None:
        if self._window is not None:
            self._window.destroy()
            self._window = None


class BluetoothAssistantApp(tk.Tk):
    def __init__(
        self,
        backend: BluetoothBackend | None = None,
        *,
        auto_scan: bool = True,
        mock_mode: bool = False,
    ) -> None:
        super().__init__()
        self._mock_mode = mock_mode
        self.title(window_title_for_mode(mock_mode))
        self.geometry("1180x700")
        self.minsize(980, 580)

        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._retrying = False
        self._devices: dict[str, BluetoothDevice] = {}
        self._same_address_count_by_row: dict[str, int] = {}
        self._last_scanned_devices: list[BluetoothDevice] = []
        self._ports: list[ComPortInfo] = []
        self._checked_rows: set[str] = set()
        self._run_status_by_address: dict[str, str] = {}
        self._manual_devices: dict[str, BluetoothDevice] = {}
        self.manual_mac_var = tk.StringVar()
        self.status_var = tk.StringVar(value=format_status_text("待機中", mock_mode=self._mock_mode))

        if backend is None:
            try:
                self._backend = WindowsBluetoothBackend(parent_hwnd=self.winfo_id())
            except UnsupportedPlatformError as exc:
                messagebox.showerror("未対応", str(exc))
                raise
            except BluetoothError as exc:
                messagebox.showerror("Bluetooth 初期化エラー", str(exc))
                raise
        else:
            self._backend = backend

        self._build_ui()
        if self._mock_mode:
            self._append_log("テストモードです。WindowsのBluetooth一覧ではなく、アプリ内のテスト用データを使います。")
        self.after(100, self._pump_queue)
        if auto_scan:
            self._scan_devices()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(14, weight=1)

        self.scan_button = ttk.Button(toolbar, text="スキャン", command=self._scan_devices)
        self.scan_button.grid(row=0, column=0, padx=(0, 6))

        self.retry_button = ttk.Button(toolbar, text="接続してCOMを探す", command=self._start_retry)
        self.retry_button.grid(row=0, column=1, padx=6)
        Tooltip(
            self.retry_button,
            "チェックした機器を上から順番に処理します。\n\n"
            "各機器ごとに「解除 -> ペアリング -> COM待ち」を繰り返し、"
            "COMポートが見つかったら次の機器へ進みます。\n\n"
            "PIN不要の機器では、Windowsからの確認要求にアプリが自動で応答します。"
            "右下に「デバイスの追加」が出る場合は、Windows側の許可確認です。",
        )

        self.check_all_button = ttk.Button(toolbar, text="全選択", command=self._check_all_visible)
        self.check_all_button.grid(row=0, column=2, padx=6)
        Tooltip(self.check_all_button, "現在表示されている機器をすべてチェックします。")

        self.clear_checks_button = ttk.Button(toolbar, text="選択クリア", command=self._clear_checks)
        self.clear_checks_button.grid(row=0, column=3, padx=6)
        Tooltip(self.clear_checks_button, "チェックをすべて外します。")

        self.unpair_button = ttk.Button(toolbar, text="選択機器の登録を解除", command=self._unpair_selected)
        self.unpair_button.grid(row=0, column=4, padx=6)
        Tooltip(
            self.unpair_button,
            "選択している機器のWindowsペアリング情報を消します。\n\n"
            "間違った機器を選んでいないか確認してから使います。",
        )

        self.stop_button = ttk.Button(toolbar, text="停止", command=self._stop_retry, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=5, padx=6)

        ttk.Label(toolbar, textvariable=self.status_var, anchor=tk.W).grid(
            row=0,
            column=6,
            columnspan=8,
            sticky="ew",
            padx=(12, 0),
        )

        max_attempts_label = ttk.Label(toolbar, text="1台あたり試行上限")
        max_attempts_label.grid(row=1, column=0, padx=(0, 4), pady=(8, 0))
        self.max_attempts = tk.IntVar(value=5)
        max_attempts_box = ttk.Spinbox(toolbar, from_=1, to=50, width=6, textvariable=self.max_attempts)
        max_attempts_box.grid(row=1, column=1, pady=(8, 0))
        max_attempts_help = (
            "1台の機器に対して、解除 -> ペアリング -> COM待ちを最大何回まで繰り返すかです。"
            "COMが出ない機器でも、この回数で必ず止まります。"
        )
        Tooltip(max_attempts_label, max_attempts_help)
        Tooltip(max_attempts_box, max_attempts_help)

        wait_seconds_label = ttk.Label(toolbar, text="1回のCOM待ち秒")
        wait_seconds_label.grid(row=1, column=2, padx=(12, 4), pady=(8, 0))
        self.wait_seconds = tk.IntVar(value=20)
        wait_seconds_box = ttk.Spinbox(toolbar, from_=3, to=300, width=6, textvariable=self.wait_seconds)
        wait_seconds_box.grid(
            row=1,
            column=3,
            pady=(8, 0),
        )
        wait_seconds_help = (
            "ペアリング後にCOMポートが出るまで待つ秒数です。"
            "この秒数で出なければ、次の試行へ進みます。"
        )
        Tooltip(wait_seconds_label, wait_seconds_help)
        Tooltip(wait_seconds_box, wait_seconds_help)

        scan_seconds_label = ttk.Label(toolbar, text="スキャン時間（秒）")
        scan_seconds_label.grid(row=1, column=4, padx=(12, 4), pady=(8, 0))
        self.scan_seconds = tk.IntVar(value=DEFAULT_SCAN_SECONDS)
        scan_seconds_box = ttk.Spinbox(toolbar, from_=2, to=60, width=6, textvariable=self.scan_seconds)
        scan_seconds_box.grid(
            row=1,
            column=5,
            pady=(8, 0),
        )
        Tooltip(
            scan_seconds_label,
            "Bluetooth機器を探す目安時間です。\n\n"
            "Windowsがすぐに結果を返した場合も、この秒数までは再スキャンします。",
        )
        Tooltip(
            scan_seconds_box,
            "Bluetooth機器を探す目安時間です。\n\n"
            "Windowsがすぐに結果を返した場合も、この秒数までは再スキャンします。",
        )

        self.enable_spp = tk.BooleanVar(value=True)
        enable_spp_check = ttk.Checkbutton(
            toolbar,
            text="COM作成を促す",
            variable=self.enable_spp,
        )
        enable_spp_check.grid(row=1, column=6, padx=(12, 4), pady=(8, 0))
        Tooltip(
            enable_spp_check,
            "ペアリング後に、Windowsへ「この機器のCOMポートを作って」と依頼します。\n\n"
            "COMポートが必要なBluetooth機器ではオン推奨です。\n"
            "機器がCOM接続に対応していない場合は、オンでもCOMは出ません。",
        )

        ttk.Label(toolbar, text="MAC指定").grid(row=2, column=0, padx=(0, 4), pady=(8, 0))
        self.manual_mac_entry = ttk.Entry(toolbar, width=22, textvariable=self.manual_mac_var)
        self.manual_mac_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        self.manual_mac_entry.bind("<Return>", lambda _event: self._add_manual_mac())
        Tooltip(
            self.manual_mac_entry,
            "AA:BB:CC:DD:EE:FF 形式で入力します。\n\n"
            "スキャンに出ない機器でも、MACアドレスが分かっていれば対象に追加できます。",
        )
        self.add_mac_button = ttk.Button(toolbar, text="MACを追加", command=self._add_manual_mac)
        self.add_mac_button.grid(row=2, column=3, padx=6, pady=(8, 0))
        Tooltip(
            self.add_mac_button,
            "入力したMACアドレスを一覧に追加し、チェックを付けます。\n\n"
            "その後、接続ボタンでCOMが出るまで解除とペアリングを繰り返せます。",
        )

        main = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        device_frame = ttk.Frame(main)
        device_frame.columnconfigure(0, weight=1)
        device_frame.rowconfigure(0, weight=1)
        main.add(device_frame, weight=3)

        columns = (
            "checked",
            "name",
            "address",
            "candidate",
            "profile",
            "score",
            "status",
            "com",
            "class",
            "last_seen",
        )
        self.tree = ttk.Treeview(device_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "checked": "選択",
            "name": "名前",
            "address": "MAC",
            "candidate": "COM候補",
            "profile": "プロファイル候補",
            "score": "点数",
            "status": "状態",
            "com": "COM",
            "class": "Class",
            "last_seen": "Last Seen",
        }
        widths = {
            "checked": 64,
            "name": 240,
            "address": 150,
            "candidate": 130,
            "profile": 150,
            "score": 60,
            "status": 180,
            "com": 120,
            "class": 90,
            "last_seen": 160,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._update_selection_detail())
        self.tree.bind("<Button-1>", self._handle_tree_click, add="+")

        scrollbar = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        lower = ttk.Frame(main)
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(1, weight=1)
        main.add(lower, weight=2)

        self.detail_var = tk.StringVar(
            value="同じMACアドレスが複数見える場合も、候補ごとに行を分けて表示します。"
            "COM候補の点数が高い行から選ぶと成功しやすいです。"
            "プロファイル候補でSPP/COMか、FW/DFU系かの目安も見られます。"
            "選択列をクリックすると、複数台を順番に処理できます。"
        )
        ttk.Label(lower, textvariable=self.detail_var, anchor=tk.W).grid(row=0, column=0, sticky="ew", pady=(8, 4))

        self.log = tk.Text(lower, height=12, wrap=tk.WORD)
        self.log.grid(row=1, column=0, sticky="nsew")
        log_scrollbar = ttk.Scrollbar(lower, orient=tk.VERTICAL, command=self.log.yview)
        log_scrollbar.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scrollbar.set)

    def _scan_devices(self) -> None:
        if self._is_worker_running():
            return
        scan_seconds = self._scan_seconds_value()
        timeout_multiplier = timeout_multiplier_from_seconds(scan_seconds)
        self._set_busy(True)
        self._set_status(f"スキャン中: {scan_seconds}秒")
        self._append_log(f"Bluetooth 機器をスキャンします（目安 {scan_seconds} 秒）")

        def work() -> None:
            try:
                devices, elapsed, scan_count = self._scan_with_minimum_duration(
                    scan_seconds=scan_seconds,
                    timeout_multiplier=timeout_multiplier,
                )
                ports = self._backend.list_com_ports()
                self._queue.put(
                    (
                        "log",
                        f"スキャン完了: {len(devices)}台 / {elapsed:.1f}秒 / "
                        f"Windows確認 {scan_count}回 / COM {len(ports)}件",
                    )
                )
                self._queue.put(("devices", (devices, ports)))
            except Exception as exc:
                self._queue.put(("error", exc))
            finally:
                self._queue.put(("busy", False))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _start_retry(self) -> None:
        if self._is_worker_running():
            return
        selected_devices = self._selected_devices_for_retry()
        if not selected_devices:
            messagebox.showinfo("選択してください", "対象の Bluetooth 機器を選択してください。")
            return

        self._stop_event.clear()
        for device in selected_devices:
            self._run_status_by_address[device.address] = "待機中"
        self._set_busy(True, retrying=True)
        self._set_status(f"COM探索中: {len(selected_devices)}台")
        self._refresh_tree_rows()
        config = RetryConfig(
            max_attempts=max(1, int(self.max_attempts.get())),
            inquiry_timeout_multiplier=timeout_multiplier_from_seconds(self._scan_seconds_value()),
            com_wait_seconds=max(3, int(self.wait_seconds.get())),
            unpair_before_each_attempt=True,
            enable_serial_service=bool(self.enable_spp.get()),
        )
        retrier = PairingRetrier(self._backend)
        self._append_log(
            f"{len(selected_devices)} 台を順番に処理します。"
            f"1台につき最大 {config.max_attempts} 回まで試します"
            f"（各回で 解除 -> ペアリング -> COM待ち最大 {config.com_wait_seconds} 秒）"
        )

        def on_event(event: RetryEvent) -> None:
            self._queue.put(("retry_event", event))

        def work() -> None:
            try:
                for index, device in enumerate(selected_devices, start=1):
                    if self._stop_event.is_set():
                        break
                    self._queue.put(("status", f"COM探索中: {index}/{len(selected_devices)} 台目"))
                    self._queue.put(
                        (
                            "log",
                            f"[{index}/{len(selected_devices)}] {device.name or device.address} を処理します",
                        )
                    )
                    self._queue.put(("run_status", (device.address, "処理中")))
                    outcome = retrier.run(device.address, config, on_event, self._stop_event)
                    status_text = "成功" if outcome.success else ("停止" if outcome.stopped else "失敗")
                    self._queue.put(("run_status", (device.address, status_text)))
                    self._queue.put(
                        (
                            "retry_done",
                            f"[{index}/{len(selected_devices)}] {device.name or device.address}: {outcome.message}",
                        )
                    )
                    if outcome.success:
                        self._queue.put(("checked_address", (device.address, False)))
                devices = self._backend.list_devices(issue_inquiry=False)
                ports = self._backend.list_com_ports()
                self._queue.put(("devices", (devices, ports)))
            except Exception as exc:
                self._queue.put(("error", exc))
            finally:
                self._queue.put(("busy", False))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _unpair_selected(self) -> None:
        if self._is_worker_running():
            return
        selected = self._selected_device()
        if selected is None:
            messagebox.showinfo("選択してください", "解除する Bluetooth 機器を選択してください。")
            return
        if not messagebox.askyesno("確認", f"{selected.name or selected.address} のペアリングを解除しますか？"):
            return

        self._set_busy(True)
        self._set_status("登録解除中")

        def work() -> None:
            try:
                result = self._backend.unpair(selected.address)
                self._queue.put(("log", result.message))
                devices = self._backend.list_devices(issue_inquiry=False)
                ports = self._backend.list_com_ports()
                self._queue.put(("devices", (devices, ports)))
            except Exception as exc:
                self._queue.put(("error", exc))
            finally:
                self._queue.put(("busy", False))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _stop_retry(self) -> None:
        self._stop_event.set()
        self._set_status("停止要求を送信しました")
        self._append_log("停止要求を送信しました")

    def _pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "devices":
                    devices, ports = payload  # type: ignore[misc]
                    self._update_devices(devices, ports)
                elif kind == "retry_event":
                    event = payload
                    assert isinstance(event, RetryEvent)
                    prefix = f"[試行 {event.attempt}] " if event.attempt else ""
                    self._append_log(prefix + event.message)
                    if event.ports:
                        self._ports = event.ports
                elif kind == "retry_done" or kind == "log":
                    self._append_log(str(payload))
                elif kind == "error":
                    self._append_log(f"エラー: {payload}")
                    messagebox.showerror("エラー", str(payload))
                elif kind == "checked_address":
                    address, checked = payload  # type: ignore[misc]
                    self._set_checked_for_address(str(address), bool(checked))
                elif kind == "run_status":
                    address, status_text = payload  # type: ignore[misc]
                    self._run_status_by_address[str(address)] = str(status_text)
                    self._refresh_tree_rows()
                elif kind == "busy":
                    self._set_busy(bool(payload))
                elif kind == "status":
                    self._set_status(str(payload))
        except queue.Empty:
            pass
        self.after(100, self._pump_queue)

    def _add_manual_mac(self) -> None:
        if self._is_worker_running():
            return
        raw_address = self.manual_mac_var.get().strip()
        try:
            device = manual_device_from_address(raw_address)
        except ValueError:
            messagebox.showerror(
                "MACアドレスを確認してください",
                "AA:BB:CC:DD:EE:FF のように12桁の16進数で入力してください。",
            )
            return

        self._manual_devices[device.address] = device
        self.manual_mac_var.set("")
        self._update_devices(self._last_scanned_devices, self._ports)
        row_id = self._first_row_id_for_address(device.address)
        if row_id:
            self._checked_rows.add(row_id)
            self.tree.selection_set(row_id)
            self.tree.see(row_id)
            self._refresh_tree_rows()
        self._append_log(f"{device.address} を手入力で追加しました")

    def _update_devices(self, devices: list[BluetoothDevice], ports: list[ComPortInfo]) -> None:
        self._last_scanned_devices = list(devices)
        display_devices = devices_with_manual_devices(devices, self._manual_devices)
        rows = build_device_display_rows(display_devices, ports)
        self._devices = {row.row_id: row.device for row in rows}
        self._same_address_count_by_row = {row.row_id: row.same_address_count for row in rows}
        self._checked_rows.intersection_update(self._devices)
        self._ports = ports
        selected_row_id = self.tree.selection()[0] if self.tree.selection() else ""
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", tk.END, iid=row.row_id, values=self._row_values(row.row_id, row.device))
        if selected_row_id in self._devices:
            self.tree.selection_set(selected_row_id)
        self._append_log(f"{len(rows)} 行を表示しました / COM {len(ports)} 件")
        if not self._is_worker_running():
            self._set_status(f"待機中: {len(rows)}行 / COM {len(ports)}件")
        self._update_selection_detail()

    def _refresh_tree_rows(self) -> None:
        for row_id, device in self._devices.items():
            if self.tree.exists(row_id):
                self.tree.item(row_id, values=self._row_values(row_id, device))

    def _row_values(
        self,
        row_id: str,
        device: BluetoothDevice,
    ) -> tuple[str, str, str, str, str, str, str, str, str, str]:
        matched_ports = find_matching_ports(device.address, self._ports)
        same_address_count = self._same_address_count_by_row.get(row_id, 1)
        assessment = assess_com_candidate(device, self._ports, same_address_count=same_address_count)
        profile = assess_profile_candidate(device, self._ports)
        run_status = self._run_status_by_address.get(device.address, "")
        status_text = device.status_text if not run_status else f"{run_status} / {device.status_text}"
        return (
            "☑" if row_id in self._checked_rows else "☐",
            device.name or "(名前なし)",
            device.address,
            assessment.display_label,
            profile.display_label,
            str(assessment.score),
            status_text,
            ", ".join(port.device for port in matched_ports),
            f"0x{device.class_of_device:06X}" if device.class_of_device else "",
            device.last_seen,
        )

    def _handle_tree_click(self, event: tk.Event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = self.tree.identify_column(event.x)
        if column != "#1":
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self._set_checked(row_id, row_id not in self._checked_rows)

    def _set_checked(self, row_id: str, checked: bool) -> None:
        if checked:
            self._checked_rows.add(row_id)
        else:
            self._checked_rows.discard(row_id)
        if self.tree.exists(row_id):
            values = list(self.tree.item(row_id, "values"))
            if values:
                values[0] = "☑" if checked else "☐"
                self.tree.item(row_id, values=values)
        self._update_selection_detail()

    def _set_checked_for_address(self, address: str, checked: bool) -> None:
        for row_id, device in self._devices.items():
            if device.address == address:
                self._set_checked(row_id, checked)

    def _check_all_visible(self) -> None:
        for row_id in self.tree.get_children():
            self._checked_rows.add(str(row_id))
        self._refresh_tree_rows()
        self._update_selection_detail()

    def _clear_checks(self) -> None:
        self._checked_rows.clear()
        self._refresh_tree_rows()
        self._update_selection_detail()

    def _first_row_id_for_address(self, address: str) -> str:
        for row_id, device in self._devices.items():
            if device.address == address:
                return row_id
        return ""

    def _scan_seconds_value(self) -> int:
        try:
            return max(2, min(60, int(self.scan_seconds.get())))
        except (tk.TclError, ValueError):
            return DEFAULT_SCAN_SECONDS

    def _scan_with_minimum_duration(
        self,
        *,
        scan_seconds: int,
        timeout_multiplier: int,
    ) -> tuple[list[BluetoothDevice], float, int]:
        started = time.perf_counter()
        deadline = started + scan_seconds
        scan_count = 0
        found: dict[tuple[str, str, int, int], BluetoothDevice] = {}

        while True:
            scan_count += 1
            self._queue.put(("log", f"スキャン中... Windows確認 {scan_count}回目"))
            devices = self._backend.list_devices(
                issue_inquiry=True,
                timeout_multiplier=timeout_multiplier,
            )
            occurrence_by_signature: defaultdict[tuple[str, str, int], int] = defaultdict(int)
            for device in devices:
                signature = (device.address, device.name, device.class_of_device)
                occurrence_by_signature[signature] += 1
                found[(*signature, occurrence_by_signature[signature])] = device
            elapsed = time.perf_counter() - started
            if elapsed >= scan_seconds:
                return list(found.values()), elapsed, scan_count
            time.sleep(min(1.0, max(0.1, deadline - time.perf_counter())))

    def _selected_device(self) -> BluetoothDevice | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._devices.get(selection[0])

    def _selected_devices_for_retry(self) -> list[BluetoothDevice]:
        checked = [
            self._devices[row_id]
            for row_id in self.tree.get_children()
            if row_id in self._checked_rows
        ]
        if checked:
            return _dedupe_devices_by_address(checked)
        selected = self._selected_device()
        return [selected] if selected is not None else []

    def _update_selection_detail(self) -> None:
        selected = self._selected_device()
        if selected is None:
            self.detail_var.set(
                "同じMACアドレスが複数見える場合も、候補ごとに行を分けて表示します。"
                "COM候補の点数が高い行から選ぶと成功しやすいです。"
                "プロファイル候補でSPP/COMか、FW/DFU系かの目安も見られます。"
                "選択列をクリックすると、複数台を順番に処理できます。"
            )
            return
        selected_row_id = self.tree.selection()[0]
        same_address_count = self._same_address_count_by_row.get(selected_row_id, 1)
        ports = find_matching_ports(selected.address, self._ports)
        port_text = ", ".join(port.device for port in ports) if ports else "未検出"
        checked_count = len(self._checked_rows)
        assessment = assess_com_candidate(selected, self._ports, same_address_count=same_address_count)
        profile = assess_profile_candidate(selected, self._ports)
        com_reason_text = " / ".join(assessment.reasons)
        profile_reason_text = " / ".join(profile.reasons)
        self.detail_var.set(
            f"{assessment.display_label} {assessment.score}点 / {profile.display_label} {profile.score}点 / "
            f"{selected.address} / "
            f"{selected.name or '(名前なし)'} / {selected.status_text} / "
            f"同じMACの候補: {same_address_count}行 / COM: {port_text} / "
            f"COM理由: {com_reason_text} / プロファイル理由: {profile_reason_text} / "
            f"チェック中: {checked_count}行"
        )

    def _set_busy(self, busy: bool, *, retrying: bool = False) -> None:
        if retrying:
            self._retrying = True
        elif not busy:
            self._retrying = False
        state = tk.DISABLED if busy else tk.NORMAL
        self.scan_button.configure(state=state)
        self.retry_button.configure(state=state)
        self.check_all_button.configure(state=state)
        self.clear_checks_button.configure(state=state)
        self.unpair_button.configure(state=state)
        self.manual_mac_entry.configure(state=state)
        self.add_mac_button.configure(state=state)
        self.stop_button.configure(state=tk.NORMAL if self._retrying else tk.DISABLED)
        if not busy and not self._devices:
            self._set_status("待機中")

    def _is_worker_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _append_log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)

    def _set_status(self, message: str) -> None:
        self.status_var.set(format_status_text(message, mock_mode=self._mock_mode))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="BluetoothAssistant Tkinter app.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use app-only test data. These devices are not Windows Bluetooth devices.",
    )
    parser.add_argument("--mock-target-address", default="AA:BB:CC:DD:EE:FF", help="Target MAC address for --mock.")
    parser.add_argument("--mock-com-port", default="COM12", help="COM port name returned by --mock after success.")
    parser.add_argument(
        "--mock-appear-after",
        type=int,
        default=2,
        help="Number of mock pair attempts before --mock returns a COM port.",
    )
    parser.add_argument("--no-auto-scan", action="store_true", help="Start the app without the initial scan.")
    args = parser.parse_args(argv)

    backend = (
        MockBluetoothBackend(
            target_address=args.mock_target_address,
            target_com_port=args.mock_com_port,
            appear_after_pair_count=args.mock_appear_after,
        )
        if args.mock
        else None
    )
    app = BluetoothAssistantApp(backend=backend, auto_scan=not args.no_auto_scan, mock_mode=args.mock)
    app.mainloop()
