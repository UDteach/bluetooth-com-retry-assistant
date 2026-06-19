from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .models import BluetoothDevice, ComPortInfo, find_matching_ports
from .retry import PairingRetrier, RetryConfig, RetryEvent
from .windows_bluetooth import BluetoothError, UnsupportedPlatformError, WindowsBluetoothBackend


class BluetoothAssistantApp(tk.Tk):
    def __init__(self) -> None:
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

        try:
            self._backend = WindowsBluetoothBackend()
        except UnsupportedPlatformError as exc:
            messagebox.showerror("未対応", str(exc))
            raise
        except BluetoothError as exc:
            messagebox.showerror("Bluetooth 初期化エラー", str(exc))
            raise

        self._build_ui()
        self.after(100, self._pump_queue)
        self._scan_devices()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(12, weight=1)

        self.scan_button = ttk.Button(toolbar, text="スキャン", command=self._scan_devices)
        self.scan_button.grid(row=0, column=0, padx=(0, 6))

        self.retry_button = ttk.Button(toolbar, text="COMが出るまでリトライ", command=self._start_retry)
        self.retry_button.grid(row=0, column=1, padx=6)

        self.unpair_button = ttk.Button(toolbar, text="選択を解除", command=self._unpair_selected)
        self.unpair_button.grid(row=0, column=2, padx=6)

        self.stop_button = ttk.Button(toolbar, text="停止", command=self._stop_retry, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=3, padx=6)

        ttk.Label(toolbar, text="回数").grid(row=0, column=4, padx=(18, 4))
        self.max_attempts = tk.IntVar(value=5)
        ttk.Spinbox(toolbar, from_=1, to=50, width=5, textvariable=self.max_attempts).grid(row=0, column=5)

        ttk.Label(toolbar, text="COM待ち秒").grid(row=0, column=6, padx=(12, 4))
        self.wait_seconds = tk.IntVar(value=20)
        ttk.Spinbox(toolbar, from_=3, to=300, width=5, textvariable=self.wait_seconds).grid(row=0, column=7)

        ttk.Label(toolbar, text="探索").grid(row=0, column=8, padx=(12, 4))
        self.inquiry_multiplier = tk.IntVar(value=8)
        ttk.Spinbox(toolbar, from_=1, to=48, width=5, textvariable=self.inquiry_multiplier).grid(row=0, column=9)

        self.clean_first = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="初回も解除", variable=self.clean_first).grid(row=0, column=10, padx=(12, 4))

        self.enable_spp = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="SPP有効化", variable=self.enable_spp).grid(row=0, column=11, padx=4)

        main = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        device_frame = ttk.Frame(main)
        device_frame.columnconfigure(0, weight=1)
        device_frame.rowconfigure(0, weight=1)
        main.add(device_frame, weight=3)

        columns = ("name", "address", "status", "com", "class", "last_seen")
        self.tree = ttk.Treeview(device_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "name": "名前",
            "address": "MAC",
            "status": "状態",
            "com": "COM",
            "class": "Class",
            "last_seen": "Last Seen",
        }
        widths = {"name": 260, "address": 150, "status": 180, "com": 120, "class": 90, "last_seen": 160}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._update_selection_detail())

        scrollbar = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        lower = ttk.Frame(main)
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(1, weight=1)
        main.add(lower, weight=2)

        self.detail_var = tk.StringVar(value="同じ MAC の候補は 1 行に統合します。COM は MAC で照合します。")
        ttk.Label(lower, textvariable=self.detail_var, anchor=tk.W).grid(row=0, column=0, sticky="ew", pady=(8, 4))

        self.log = tk.Text(lower, height=12, wrap=tk.WORD)
        self.log.grid(row=1, column=0, sticky="nsew")
        log_scrollbar = ttk.Scrollbar(lower, orient=tk.VERTICAL, command=self.log.yview)
        log_scrollbar.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scrollbar.set)

    def _scan_devices(self) -> None:
        if self._is_worker_running():
            return
        self._set_busy(True)
        self._append_log("Bluetooth 機器をスキャンします")

        def work() -> None:
            try:
                devices = self._backend.list_devices(
                    issue_inquiry=True,
                    timeout_multiplier=max(1, int(self.inquiry_multiplier.get())),
                )
                ports = self._backend.list_com_ports()
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
        selected = self._selected_device()
        if selected is None:
            messagebox.showinfo("選択してください", "対象の Bluetooth 機器を選択してください。")
            return

        self._stop_event.clear()
        self._set_busy(True, retrying=True)
        config = RetryConfig(
            max_attempts=max(1, int(self.max_attempts.get())),
            inquiry_timeout_multiplier=max(1, min(int(self.inquiry_multiplier.get()), 48)),
            com_wait_seconds=max(3, int(self.wait_seconds.get())),
            clean_before_first_attempt=bool(self.clean_first.get()),
            enable_serial_service=bool(self.enable_spp.get()),
        )
        retrier = PairingRetrier(self._backend)
        self._append_log(f"{selected.name or selected.address} のリトライを開始します")

        def on_event(event: RetryEvent) -> None:
            self._queue.put(("retry_event", event))

        def work() -> None:
            try:
                outcome = retrier.run(selected.address, config, on_event, self._stop_event)
                self._queue.put(("retry_done", outcome.message))
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
                elif kind == "retry_done":
                    self._append_log(str(payload))
                elif kind == "log":
                    self._append_log(str(payload))
                elif kind == "error":
                    self._append_log(f"エラー: {payload}")
                    messagebox.showerror("エラー", str(payload))
                elif kind == "busy":
                    self._set_busy(bool(payload))
        except queue.Empty:
            pass
        self.after(100, self._pump_queue)

    def _update_devices(self, devices: list[BluetoothDevice], ports: list[ComPortInfo]) -> None:
        self._devices = {device.address: device for device in devices}
        self._ports = ports
        selected_address = self.tree.selection()[0] if self.tree.selection() else ""
        self.tree.delete(*self.tree.get_children())
        for device in devices:
            matched_ports = find_matching_ports(device.address, ports)
            self.tree.insert(
                "",
                tk.END,
                iid=device.address,
                values=(
                    device.name or "(名前なし)",
                    device.address,
                    device.status_text,
                    ", ".join(port.device for port in matched_ports),
                    f"0x{device.class_of_device:06X}" if device.class_of_device else "",
                    device.last_seen,
                ),
            )
        if selected_address in self._devices:
            self.tree.selection_set(selected_address)
        self._append_log(f"{len(devices)} 台を表示しました / COM {len(ports)} 件")
        self._update_selection_detail()

    def _selected_device(self) -> BluetoothDevice | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._devices.get(selection[0])

    def _update_selection_detail(self) -> None:
        selected = self._selected_device()
        if selected is None:
            self.detail_var.set("同じ MAC の候補は 1 行に統合します。COM は MAC で照合します。")
            return
        ports = find_matching_ports(selected.address, self._ports)
        names = ", ".join(selected.raw_names) if selected.raw_names else selected.name
        port_text = ", ".join(port.device for port in ports) if ports else "未検出"
        self.detail_var.set(
            f"{selected.address} / {names or '(名前なし)'} / {selected.status_text} / COM: {port_text}"
        )

    def _set_busy(self, busy: bool, *, retrying: bool = False) -> None:
        if retrying:
            self._retrying = True
        elif not busy:
            self._retrying = False
        state = tk.DISABLED if busy else tk.NORMAL
        self.scan_button.configure(state=state)
        self.retry_button.configure(state=state)
        self.unpair_button.configure(state=state)
        self.stop_button.configure(state=tk.NORMAL if self._retrying else tk.DISABLED)

    def _is_worker_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _append_log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)


def main() -> None:
    app = BluetoothAssistantApp()
    app.mainloop()
