from __future__ import annotations

import argparse
import math
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .mock_backend import MockBluetoothBackend
from .models import BluetoothDevice, ComPortInfo, find_matching_ports, merge_duplicate_devices
from .retry import BluetoothBackend, PairingRetrier, RetryConfig, RetryEvent
from .windows_bluetooth import BluetoothError, UnsupportedPlatformError, WindowsBluetoothBackend

BLUETOOTH_INQUIRY_UNIT_SECONDS = 1.28
DEFAULT_SCAN_SECONDS = 10


def timeout_multiplier_from_seconds(seconds: int) -> int:
    return max(1, min(48, math.ceil(max(1, seconds) / BLUETOOTH_INQUIRY_UNIT_SECONDS)))


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
    def __init__(self, backend: BluetoothBackend | None = None, *, auto_scan: bool = True) -> None:
        super().__init__()
        self.title("BluetoothAssistant")
        self.geometry("1040x680")
        self.minsize(900, 560)

        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._retrying = False
        self._devices: dict[str, BluetoothDevice] = {}
        self._ports: list[ComPortInfo] = []
        self._checked_addresses: set[str] = set()
        self._run_status_by_address: dict[str, str] = {}

        if backend is None:
            try:
                self._backend = WindowsBluetoothBackend()
            except UnsupportedPlatformError as exc:
                messagebox.showerror("未対応", str(exc))
                raise
            except BluetoothError as exc:
                messagebox.showerror("Bluetooth 初期化エラー", str(exc))
                raise
        else:
            self._backend = backend

        self._build_ui()
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

        self.retry_button = ttk.Button(toolbar, text="選択した機器を順番に接続", command=self._start_retry)
        self.retry_button.grid(row=0, column=1, padx=6)
        Tooltip(
            self.retry_button,
            "チェックした機器を上から順番に処理します。\n\n"
            "1台ずつペアリングし、COMポートが見つかったら次の機器へ進みます。",
        )

        self.check_all_button = ttk.Button(toolbar, text="全選択", command=self._check_all_visible)
        self.check_all_button.grid(row=0, column=2, padx=6)
        Tooltip(self.check_all_button, "現在表示されている機器をすべてチェックします。")

        self.clear_checks_button = ttk.Button(toolbar, text="選択クリア", command=self._clear_checks)
        self.clear_checks_button.grid(row=0, column=3, padx=6)
        Tooltip(self.clear_checks_button, "チェックをすべて外します。")

        self.unpair_button = ttk.Button(toolbar, text="選択を解除", command=self._unpair_selected)
        self.unpair_button.grid(row=0, column=4, padx=6)

        self.stop_button = ttk.Button(toolbar, text="停止", command=self._stop_retry, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=5, padx=6)

        ttk.Label(toolbar, text="回数").grid(row=1, column=0, padx=(0, 4), pady=(8, 0))
        self.max_attempts = tk.IntVar(value=5)
        ttk.Spinbox(toolbar, from_=1, to=50, width=5, textvariable=self.max_attempts).grid(row=1, column=1, pady=(8, 0))

        ttk.Label(toolbar, text="COM待ち秒").grid(row=1, column=2, padx=(12, 4), pady=(8, 0))
        self.wait_seconds = tk.IntVar(value=20)
        ttk.Spinbox(toolbar, from_=3, to=300, width=5, textvariable=self.wait_seconds).grid(
            row=1,
            column=3,
            pady=(8, 0),
        )

        ttk.Label(toolbar, text="スキャン秒").grid(row=1, column=4, padx=(12, 4), pady=(8, 0))
        self.scan_seconds = tk.IntVar(value=DEFAULT_SCAN_SECONDS)
        scan_seconds_box = ttk.Spinbox(toolbar, from_=2, to=60, width=5, textvariable=self.scan_seconds)
        scan_seconds_box.grid(
            row=1,
            column=5,
            pady=(8, 0),
        )
        Tooltip(
            scan_seconds_box,
            "Bluetooth機器を探す目安時間です。\n\n"
            "Windowsがすぐに結果を返した場合も、この秒数までは再スキャンします。",
        )

        self.clean_first = tk.BooleanVar(value=False)
        clean_first_check = ttk.Checkbutton(
            toolbar,
            text="最初に接続情報を消す",
            variable=self.clean_first,
        )
        clean_first_check.grid(row=1, column=6, padx=(12, 4), pady=(8, 0))
        Tooltip(
            clean_first_check,
            "1回目のペアリング前に、Windows側に残っているこの機器の登録情報を消します。\n\n"
            "同じ機器が何度も失敗する、古い接続情報が残っていそうな時に使います。\n"
            "迷う場合はオフのままで大丈夫です。",
        )

        self.enable_spp = tk.BooleanVar(value=True)
        enable_spp_check = ttk.Checkbutton(
            toolbar,
            text="COM作成を促す",
            variable=self.enable_spp,
        )
        enable_spp_check.grid(row=1, column=7, padx=4, pady=(8, 0))
        Tooltip(
            enable_spp_check,
            "ペアリング後に、Windowsへ「この機器のCOMポートを作って」と依頼します。\n\n"
            "COMポートが必要なBluetooth機器ではオン推奨です。\n"
            "機器がCOM接続に対応していない場合は、オンでもCOMは出ません。",
        )

        main = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        device_frame = ttk.Frame(main)
        device_frame.columnconfigure(0, weight=1)
        device_frame.rowconfigure(0, weight=1)
        main.add(device_frame, weight=3)

        columns = ("checked", "name", "address", "status", "com", "class", "last_seen")
        self.tree = ttk.Treeview(device_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "checked": "選択",
            "name": "名前",
            "address": "MAC",
            "status": "状態",
            "com": "COM",
            "class": "Class",
            "last_seen": "Last Seen",
        }
        widths = {
            "checked": 64,
            "name": 240,
            "address": 150,
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
            value="同じ機器が複数見えても、同じMACアドレスなら1行にまとめます。"
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
                        f"スキャン完了: {len(devices)}台 / {elapsed:.1f}秒 / API {scan_count}回 / COM {len(ports)}件",
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
        self._refresh_tree_rows()
        config = RetryConfig(
            max_attempts=max(1, int(self.max_attempts.get())),
            inquiry_timeout_multiplier=timeout_multiplier_from_seconds(self._scan_seconds_value()),
            com_wait_seconds=max(3, int(self.wait_seconds.get())),
            clean_before_first_attempt=bool(self.clean_first.get()),
            enable_serial_service=bool(self.enable_spp.get()),
        )
        retrier = PairingRetrier(self._backend)
        self._append_log(f"{len(selected_devices)} 台を順番に処理します")

        def on_event(event: RetryEvent) -> None:
            self._queue.put(("retry_event", event))

        def work() -> None:
            try:
                for index, device in enumerate(selected_devices, start=1):
                    if self._stop_event.is_set():
                        break
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
                        self._queue.put(("checked", (device.address, False)))
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
                    prefix = f"[{event.attempt}] " if event.attempt else ""
                    self._append_log(prefix + event.message)
                    if event.ports:
                        self._ports = event.ports
                elif kind == "retry_done" or kind == "log":
                    self._append_log(str(payload))
                elif kind == "error":
                    self._append_log(f"エラー: {payload}")
                    messagebox.showerror("エラー", str(payload))
                elif kind == "checked":
                    address, checked = payload  # type: ignore[misc]
                    self._set_checked(str(address), bool(checked))
                elif kind == "run_status":
                    address, status_text = payload  # type: ignore[misc]
                    self._run_status_by_address[str(address)] = str(status_text)
                    self._refresh_tree_rows()
                elif kind == "busy":
                    self._set_busy(bool(payload))
        except queue.Empty:
            pass
        self.after(100, self._pump_queue)

    def _update_devices(self, devices: list[BluetoothDevice], ports: list[ComPortInfo]) -> None:
        self._devices = {device.address: device for device in devices}
        self._checked_addresses.intersection_update(self._devices)
        self._ports = ports
        selected_address = self.tree.selection()[0] if self.tree.selection() else ""
        self.tree.delete(*self.tree.get_children())
        for device in devices:
            self.tree.insert("", tk.END, iid=device.address, values=self._row_values(device))
        if selected_address in self._devices:
            self.tree.selection_set(selected_address)
        self._append_log(f"{len(devices)} 台を表示しました / COM {len(ports)} 件")
        self._update_selection_detail()

    def _refresh_tree_rows(self) -> None:
        for address, device in self._devices.items():
            if self.tree.exists(address):
                self.tree.item(address, values=self._row_values(device))

    def _row_values(self, device: BluetoothDevice) -> tuple[str, str, str, str, str, str, str]:
        matched_ports = find_matching_ports(device.address, self._ports)
        run_status = self._run_status_by_address.get(device.address, "")
        status_text = device.status_text if not run_status else f"{run_status} / {device.status_text}"
        return (
            "☑" if device.address in self._checked_addresses else "☐",
            device.name or "(名前なし)",
            device.address,
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
        self._set_checked(row_id, row_id not in self._checked_addresses)

    def _set_checked(self, address: str, checked: bool) -> None:
        if checked:
            self._checked_addresses.add(address)
        else:
            self._checked_addresses.discard(address)
        if self.tree.exists(address):
            values = list(self.tree.item(address, "values"))
            if values:
                values[0] = "☑" if checked else "☐"
                self.tree.item(address, values=values)
        self._update_selection_detail()

    def _check_all_visible(self) -> None:
        for address in self.tree.get_children():
            self._checked_addresses.add(str(address))
        self._refresh_tree_rows()
        self._update_selection_detail()

    def _clear_checks(self) -> None:
        self._checked_addresses.clear()
        self._refresh_tree_rows()
        self._update_selection_detail()

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
        found: dict[str, BluetoothDevice] = {}

        while True:
            scan_count += 1
            self._queue.put(("log", f"スキャン中... {scan_count}回目"))
            devices = self._backend.list_devices(
                issue_inquiry=True,
                timeout_multiplier=timeout_multiplier,
            )
            for device in devices:
                found[device.address] = device
            elapsed = time.perf_counter() - started
            if elapsed >= scan_seconds:
                return merge_duplicate_devices(found.values()), elapsed, scan_count
            time.sleep(min(1.0, max(0.1, deadline - time.perf_counter())))

    def _selected_device(self) -> BluetoothDevice | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._devices.get(selection[0])

    def _selected_devices_for_retry(self) -> list[BluetoothDevice]:
        checked = [self._devices[address] for address in self.tree.get_children() if address in self._checked_addresses]
        if checked:
            return checked
        selected = self._selected_device()
        return [selected] if selected is not None else []

    def _update_selection_detail(self) -> None:
        selected = self._selected_device()
        if selected is None:
            self.detail_var.set(
                "同じ機器が複数見えても、同じMACアドレスなら1行にまとめます。"
                "選択列をクリックすると、複数台を順番に処理できます。"
            )
            return
        ports = find_matching_ports(selected.address, self._ports)
        names = ", ".join(selected.raw_names) if selected.raw_names else selected.name
        port_text = ", ".join(port.device for port in ports) if ports else "未検出"
        checked_count = len(self._checked_addresses)
        self.detail_var.set(
            f"{selected.address} / {names or '(名前なし)'} / {selected.status_text} / "
            f"COM: {port_text} / チェック中: {checked_count}台"
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
        self.stop_button.configure(state=tk.NORMAL if self._retrying else tk.DISABLED)

    def _is_worker_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _append_log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="BluetoothAssistant Tkinter app.")
    parser.add_argument("--mock", action="store_true", help="Use an in-memory mock Bluetooth backend.")
    parser.add_argument("--no-auto-scan", action="store_true", help="Start the app without the initial scan.")
    args = parser.parse_args(argv)

    backend = MockBluetoothBackend() if args.mock else None
    app = BluetoothAssistantApp(backend=backend, auto_scan=not args.no_auto_scan)
    app.mainloop()
