from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from .config import load_config
from .confirmed_actions import CONFIRMED_ACTIONS
from .logger import LOG_DIR, LOG_FILE, setup_logger
from .protocol import ascii_preview, hexdump, now_compact, now_iso


CONFIG = load_config()
TARGET_NAME = CONFIG.target.name
TARGET_ADDRESS = CONFIG.target.address

SERVICE_UUID = CONFIG.gatt.service_uuid
READ_CHARACTERISTIC_1 = CONFIG.gatt.read_characteristic_1
READ_CHARACTERISTIC_2 = CONFIG.gatt.read_characteristic_2
WRITE_CHARACTERISTIC = CONFIG.gatt.write_characteristic
NOTIFY_CHARACTERISTIC = CONFIG.gatt.notify_characteristic


@dataclass(frozen=True)
class ScanResult:
    name: str
    address: str
    rssi: Optional[int]
    matched: bool


@dataclass(frozen=True)
class TxEvent:
    tx_id: int
    timestamp: str
    uuid: str
    payload: bytes


@dataclass(frozen=True)
class PacketEvent:
    timestamp: str
    direction: str
    uuid: str
    payload: bytes


class MitsuBridgeClient:
    def __init__(
        self,
        target_name: str | None = None,
        target_address: str | None = None,
        scan_timeout: float | None = None,
        connect_timeout: float | None = None,
        reconnect_delay: float | None = None,
        debug: bool = False,
    ) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        runtime_config = load_config()
        self.target_name = target_name or runtime_config.target.name
        self.target_address = (target_address if target_address is not None else runtime_config.target.address).upper()
        self.scan_timeout = scan_timeout if scan_timeout is not None else runtime_config.target.scan_timeout_seconds
        self.connect_timeout = (
            connect_timeout if connect_timeout is not None else runtime_config.target.connect_timeout_seconds
        )
        self.reconnect_delay = (
            reconnect_delay if reconnect_delay is not None else runtime_config.target.reconnect_delay_seconds
        )
        self.logger = setup_logger(debug=debug)

        self.session_id = now_compact()
        self.notify_bin_path = LOG_DIR / f"notify_{self.session_id}.bin"
        self.session_log_path = LOG_DIR / f"session_{self.session_id}.txt"
        self.gatt_dump_path = LOG_DIR / "gatt_dump.txt"

        self._client: BleakClient | None = None
        self._device: BLEDevice | None = None
        self._last_rssi: Optional[int] = None
        self._notify_enabled = False
        self._notify_requested = False
        self._manual_disconnect = False
        self._monitor_active = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._connect_lock = asyncio.Lock()
        self._disconnect_lock = asyncio.Lock()
        self._events: list[str] = []
        self._packet_events: list[PacketEvent] = []
        self._notify_queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self._last_tx: TxEvent | None = None
        self._tx_counter = 0

        self._record_event(
            "SESSION",
            "\n".join(
                [
                    f"Session ID: {self.session_id}",
                    f"Target Name: {self.target_name}",
                    f"Target Address: {self.target_address}",
                    f"Notify Bin: {self.notify_bin_path}",
                    f"Session Log: {self.session_log_path}",
                    f"Main Log: {LOG_FILE}",
                ]
            ),
        )
        self._write_session_log()

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    async def scan(self) -> list[ScanResult]:
        started = now_iso()
        self.logger.info("SCAN start timeout=%.1fs", self.scan_timeout)
        self._record_event("SCAN", f"Start: {started}\nTimeout: {self.scan_timeout:.1f}s")

        seen: list[tuple[BLEDevice, AdvertisementData]] = []

        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData) -> None:
            seen.append((device, advertisement_data))

        scanner = BleakScanner(detection_callback)
        try:
            await scanner.start()
            await asyncio.sleep(self.scan_timeout)
        except Exception as exc:
            self.logger.exception("SCAN failed error=%s", exc)
            self._record_event("SCAN_ERROR", f"Error: {exc}")
            print(f"Scan failed: {exc}")
            return []
        finally:
            with contextlib.suppress(Exception):
                await scanner.stop()

        unique: dict[str, ScanResult] = {}
        for device, advertisement in seen:
            name = device.name or advertisement.local_name or "(unknown)"
            address = device.address
            matched = self._matches(device, advertisement)
            rssi = getattr(advertisement, "rssi", None)
            if matched:
                self._device = device
                self._last_rssi = rssi
            unique[address] = ScanResult(name=name, address=address, rssi=rssi, matched=matched)

        results = sorted(unique.values(), key=lambda item: (not item.matched, item.name, item.address))
        event_lines = [f"Found: {len(results)}"]
        for result in results:
            mark = "*" if result.matched else " "
            line = f"{mark} name={result.name} address={result.address} rssi={result.rssi}"
            event_lines.append(line)
            self.logger.info("SCAN result %s", line)

        self._record_event("SCAN_RESULTS", "\n".join(event_lines))

        print(f"Found {len(results)} BLE device(s). '*' marks the target candidate.")
        for result in results:
            mark = "*" if result.matched else " "
            print(f"{mark} {result.name:30} {result.address:40} RSSI={result.rssi}")

        return results

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self.is_connected or self._client is not None:
                await self.disconnect(reason="reconnect before connect", print_status=False)

            self._manual_disconnect = False
            device = self._device or await self._find_target()
            if not device:
                message = f"Target not found. Run scan again or move closer to {self.target_name}."
                print(message)
                self.logger.warning("CONNECT target_not_found name=%s address=%s", self.target_name, self.target_address)
                self._record_event("CONNECT_FAILED", message)
                return False

            self._device = device
            self.logger.info("CONNECT start name=%s address=%s", device.name, device.address)
            self._record_event("CONNECT", f"Start\nName: {device.name}\nAddress: {device.address}")

            client = BleakClient(
                device,
                timeout=self.connect_timeout,
                disconnected_callback=self._handle_disconnect,
            )

            try:
                await asyncio.wait_for(client.connect(), timeout=self.connect_timeout + 2)
            except Exception as exc:
                self.logger.exception("CONNECT failed error=%s", exc)
                self._record_event("CONNECT_FAILED", f"Error: {exc}")
                print(f"Connect failed: {exc}")
                try:
                    await client.disconnect()
                except Exception as disconnect_exc:
                    self.logger.warning("CONNECT cleanup_disconnect_failed error=%s", disconnect_exc)
                finally:
                    self._client = None
                    self._notify_enabled = False
                    self._notify_requested = False
                    self._monitor_active = False
                    self._log_disconnect(reason=f"connect failed: {exc}")
                    await asyncio.sleep(2)
                return False

            self._client = client
            self.logger.info("CONNECT ok address=%s", device.address)
            self._record_event("CONNECT_OK", f"Name: {device.name}\nAddress: {device.address}")
            print(f"Connected: {device.name or '(unknown)'} [{device.address}]")
            return True

    async def stop_notify(self, reason: str = "manual stop_notify", clear_request: bool = True) -> None:
        client = self._client
        if client and self._notify_enabled:
            try:
                self.logger.info("NOTIFY stop start uuid=%s reason=%s", NOTIFY_CHARACTERISTIC, reason)
                await client.stop_notify(NOTIFY_CHARACTERISTIC)
                self.logger.info("NOTIFY stop ok uuid=%s", NOTIFY_CHARACTERISTIC)
                self._record_event("NOTIFY_STOP", f"Reason: {reason}\nUUID: {NOTIFY_CHARACTERISTIC}")
            except Exception as exc:
                self.logger.exception("NOTIFY stop_failed uuid=%s error=%s", NOTIFY_CHARACTERISTIC, exc)
                self._record_event("NOTIFY_STOP_FAILED", f"Reason: {reason}\nError: {exc}")
        self._notify_enabled = False
        if clear_request:
            self._notify_requested = False

    async def disconnect(
        self,
        reason: str = "manual disconnect",
        *,
        clear_notify_request: bool = True,
        print_status: bool = True,
        settle_delay: float = 2.0,
    ) -> None:
        async with self._disconnect_lock:
            self._manual_disconnect = True

            current_task = asyncio.current_task()
            if (
                self._reconnect_task
                and not self._reconnect_task.done()
                and self._reconnect_task is not current_task
            ):
                self._reconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._reconnect_task

            await self.stop_notify(reason=reason, clear_request=clear_notify_request)

            client = self._client
            if client:
                try:
                    await client.disconnect()
                except Exception as exc:
                    self.logger.warning("DISCONNECT client_disconnect_failed reason=%s error=%s", reason, exc)
                    self._record_event("DISCONNECT_ERROR", f"Reason: {reason}\nError: {exc}")

            self._client = None
            self._notify_enabled = False
            if clear_notify_request:
                self._notify_requested = False
                self._monitor_active = False

            if settle_delay > 0:
                await asyncio.sleep(settle_delay)

            self._log_disconnect(reason=reason)
            if print_status:
                print("Connected=False")
                print("Notify=False")

    async def read_characteristics(self) -> tuple[bytes, bytes] | None:
        if not await self._ensure_connected():
            return None

        assert self._client is not None
        cleanup_reason: str | None = None
        try:
            first = bytes(await self._client.read_gatt_char(READ_CHARACTERISTIC_1))
            second = bytes(await self._client.read_gatt_char(READ_CHARACTERISTIC_2))
        except Exception as exc:
            self.logger.exception("READ failed error=%s", exc)
            self._record_event("READ_FAILED", f"Error: {exc}")
            print(f"Read failed: {exc}")
            cleanup_reason = f"read failed: {exc}"
            return None
        finally:
            if cleanup_reason:
                await self.disconnect(reason=cleanup_reason, print_status=False)

        self._log_rx("READ1", READ_CHARACTERISTIC_1, first)
        self._log_rx("READ2", READ_CHARACTERISTIC_2, second)
        self._record_packet("RX", READ_CHARACTERISTIC_1, first)
        self._record_packet("RX", READ_CHARACTERISTIC_2, second)
        self._record_event(
            "READ",
            "\n\n".join(
                [
                    self._payload_report("READ1", READ_CHARACTERISTIC_1, first),
                    self._payload_report("READ2", READ_CHARACTERISTIC_2, second),
                ]
            ),
        )
        print(self._payload_report("READ1", READ_CHARACTERISTIC_1, first))
        print(self._payload_report("READ2", READ_CHARACTERISTIC_2, second))
        return first, second

    async def start_notify(self) -> bool:
        if not await self._ensure_connected():
            return False
        if self._notify_enabled:
            print("Notify already enabled.")
            return True

        assert self._client is not None
        cleanup_reason: str | None = None
        try:
            await self._client.start_notify(NOTIFY_CHARACTERISTIC, self._notification_handler)
        except Exception as exc:
            self.logger.exception("NOTIFY start_failed error=%s", exc)
            self._record_event("NOTIFY_FAILED", f"Error: {exc}")
            print(f"Notify failed: {exc}")
            cleanup_reason = f"notify start failed: {exc}"
            return False
        finally:
            if cleanup_reason:
                await self.disconnect(reason=cleanup_reason, print_status=False)

        self._notify_requested = True
        self._notify_enabled = True
        self.logger.info("NOTIFY start uuid=%s bin=%s", NOTIFY_CHARACTERISTIC, self.notify_bin_path)
        self._record_event(
            "NOTIFY_START",
            f"UUID: {NOTIFY_CHARACTERISTIC}\nNotify Bin: {self.notify_bin_path}",
        )
        print(f"Notify enabled: {NOTIFY_CHARACTERISTIC}")
        print(f"Notify binary stream: {self.notify_bin_path}")
        return True

    async def monitor(self) -> bool:
        self._record_event("MONITOR", "Start monitor: connect, read, enable notify")
        self._monitor_active = True
        success = False
        try:
            if not await self.connect():
                return False
            if await self.read_characteristics() is None:
                return False
            if not await self.start_notify():
                return False
            success = True
            print("Monitor running. Notifications will stream until stop, disconnect, or exit.")
            print(f"Session packet log: {self.session_log_path}")
            print("You can keep using write <hex> while monitor is active.")
            return True
        except Exception as exc:
            self.logger.exception("MONITOR failed error=%s", exc)
            self._record_event("MONITOR_FAILED", f"Error: {exc}")
            print(f"Monitor failed: {exc}")
            return False
        finally:
            if not success:
                await self.disconnect(reason="monitor failed", print_status=False)

    async def stop_monitor(self, reason: str = "monitor stop") -> None:
        await self.disconnect(reason=reason)

    async def write_hex(self, hex_payload: str) -> bool:
        try:
            payload = bytes.fromhex(hex_payload)
        except ValueError as exc:
            print(f"Invalid hex payload: {exc}")
            self._record_event("WRITE_REJECTED", f"Input: {hex_payload}\nError: {exc}")
            return False

        if not payload:
            print("Refusing to write empty payload.")
            self._record_event("WRITE_REJECTED", "Empty payload")
            return False

        return await self.send_payload(payload, source="write")

    async def send_file(self, file_path: str) -> bool:
        path = Path(file_path).expanduser()
        try:
            payload = path.read_bytes()
        except OSError as exc:
            print(f"Cannot read file: {exc}")
            self._record_event("SENDFILE_FAILED", f"Path: {path}\nError: {exc}")
            return False

        if not payload:
            print("Refusing to send empty file.")
            self._record_event("SENDFILE_REJECTED", f"Path: {path}\nReason: empty file")
            return False

        return await self.send_payload(payload, source=f"sendfile {path}")

    async def send_confirmed_action(
        self,
        action_name: str,
        *,
        settle_seconds: float = 8.0,
    ) -> bool:
        action_key = action_name.lower()
        action = CONFIRMED_ACTIONS.get(action_key)
        if not action:
            allowed = ", ".join(sorted(CONFIRMED_ACTIONS))
            print(f"Unknown confirmed action: {action_name}. Allowed: {allowed}")
            self._record_event("CONFIRMED_ACTION_REJECTED", f"Action: {action_name}\nAllowed: {allowed}")
            return False

        if not await self._ensure_connected():
            return False

        if await self.read_characteristics() is None:
            return False

        if not await self.start_notify():
            return False

        self._drain_notify_queue()
        await asyncio.sleep(0.25)

        assert self._client is not None
        self._record_event(
            "CONFIRMED_ACTION_START",
            "\n".join(
                [
                    f"Action: {action.name}",
                    f"Description: {action.description}",
                    f"Source: {action.source_cluster}",
                    f"Steps: {len(action.steps)}",
                    "Boundary: confirmed replay only; no protocol inference",
                ]
            ),
        )
        print(f"Sending confirmed {action.name.upper()} action ({len(action.steps)} packets).")

        try:
            for index, confirmed_step in enumerate(action.steps, start=1):
                self._tx_counter += 1
                tx = TxEvent(
                    tx_id=self._tx_counter,
                    timestamp=now_iso(),
                    uuid=WRITE_CHARACTERISTIC,
                    payload=confirmed_step.payload,
                )
                self._last_tx = tx
                await self._client.write_gatt_char(
                    WRITE_CHARACTERISTIC,
                    confirmed_step.payload,
                    response=False,
                )
                event_name = f"CONFIRMED_{action.name.upper()}_{confirmed_step.label}"
                self._log_tx(event_name, WRITE_CHARACTERISTIC, confirmed_step.payload)
                self._record_packet("TX", WRITE_CHARACTERISTIC, confirmed_step.payload, timestamp=tx.timestamp)
                self._record_event(
                    "CONFIRMED_ACTION_TX",
                    "\n".join(
                        [
                            f"Action: {action.name}",
                            f"Step: {index}/{len(action.steps)} {confirmed_step.label}",
                            f"TX ID: {tx.tx_id}",
                            f"UUID: {tx.uuid}",
                            f"Payload Hex: {confirmed_step.payload.hex(' ').upper()}",
                        ]
                    ),
                )
                if confirmed_step.delay_after_seconds > 0:
                    await asyncio.sleep(confirmed_step.delay_after_seconds)
        except Exception as exc:
            self.logger.exception("CONFIRMED_ACTION failed action=%s error=%s", action.name, exc)
            self._record_event("CONFIRMED_ACTION_FAILED", f"Action: {action.name}\nError: {exc}")
            print(f"Confirmed action failed: {exc}")
            await self.disconnect(reason=f"confirmed action failed: {action.name}: {exc}", print_status=False)
            return False

        if settle_seconds > 0:
            await asyncio.sleep(settle_seconds)

        self._record_event("CONFIRMED_ACTION_DONE", f"Action: {action.name}")
        print(f"Confirmed {action.name.upper()} action sent.")
        return True

    async def send_payload(
        self,
        payload: bytes,
        *,
        uuid: str = WRITE_CHARACTERISTIC,
        source: str = "send",
        ack_timeout: float = 2.0,
    ) -> bool:
        if not await self._ensure_connected():
            return False

        if not self._notify_enabled:
            if not await self.start_notify():
                return False

        self._drain_notify_queue()

        assert self._client is not None
        cleanup_reason: str | None = None
        self._tx_counter += 1
        tx = TxEvent(
            tx_id=self._tx_counter,
            timestamp=now_iso(),
            uuid=uuid,
            payload=payload,
        )
        self._last_tx = tx
        try:
            await self._client.write_gatt_char(uuid, payload, response=True)
        except Exception as exc:
            self.logger.exception("SEND failed source=%s uuid=%s error=%s", source, uuid, exc)
            self._record_event("SEND_FAILED", f"Source: {source}\nUUID: {uuid}\nError: {exc}")
            print(f"Send failed: {exc}")
            cleanup_reason = f"send failed: {exc}"
            return False
        finally:
            if cleanup_reason:
                await self.disconnect(reason=cleanup_reason, print_status=False)

        self._log_tx(source.upper(), uuid, payload)
        self._record_packet("TX", uuid, payload, timestamp=tx.timestamp)
        self._record_event(
            "SEND",
            "\n".join(
                [
                    f"Source: {source}",
                    f"TX ID: {tx.tx_id}",
                    f"Time: {tx.timestamp}",
                    f"UUID: {tx.uuid}",
                    f"Payload Hex: {payload.hex(' ').upper()}",
                    "HEX:",
                    hexdump(payload),
                    f"ASCII: {ascii_preview(payload)}",
                ]
            ),
        )
        print(f"TX tx_id={tx.tx_id} source={source} uuid={uuid}")
        print(f"Payload Hex: {payload.hex(' ').upper()}")
        await self._wait_for_notify_ack(timeout=ack_timeout)
        return True

    async def replay_session(self, session_path: str) -> bool:
        path = Path(session_path).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Cannot read session: {exc}")
            self._record_event("REPLAY_FAILED", f"Path: {path}\nError: {exc}")
            return False

        packets = self._parse_tx_packets(text)
        if not packets:
            print("No TX packets found in session.")
            self._record_event("REPLAY_EMPTY", f"Path: {path}")
            return False

        if not await self._ensure_connected():
            return False
        if not self._notify_enabled and not await self.start_notify():
            return False

        self._record_event("REPLAY", f"Path: {path}\nTX Count: {len(packets)}")
        print(f"Replaying {len(packets)} TX packet(s) from {path}")
        for index, packet in enumerate(packets, start=1):
            print(f"Replay {index}/{len(packets)} UUID={packet.uuid} Length={len(packet.payload)}")
            ok = await self.send_payload(
                packet.payload,
                uuid=packet.uuid,
                source=f"replay {path.name} #{index}",
                ack_timeout=2.0,
            )
            if not ok:
                return False
        return True

    async def dump_services(self) -> Path | None:
        if not await self._ensure_connected():
            return None

        assert self._client is not None
        cleanup_reason: str | None = None
        try:
            services = self._client.services
            service_list = list(services)
        except Exception as exc:
            self.logger.exception("DUMP services_failed error=%s", exc)
            self._record_event("DUMP_FAILED", f"Error: {exc}")
            print(f"Dump failed: {exc}")
            cleanup_reason = f"dump failed: {exc}"
            return None
        finally:
            if cleanup_reason:
                await self.disconnect(reason=cleanup_reason, print_status=False)

        lines = [
            f"MitsuBridge GATT Dump",
            f"Time: {now_iso()}",
            f"Target Name: {self.target_name}",
            f"Target Address: {self.target_address}",
            "",
        ]

        for service in service_list:
            lines.append(f"Service: {service.uuid}")
            lines.append(f"  Description: {getattr(service, 'description', '')}")
            for characteristic in service.characteristics:
                properties = ", ".join(characteristic.properties)
                lines.append(f"  Characteristic: {characteristic.uuid}")
                lines.append(f"    Handle: {characteristic.handle}")
                lines.append(f"    Property: {properties}")
                for descriptor in characteristic.descriptors:
                    lines.append(f"    Descriptor: {descriptor.uuid}")
                    lines.append(f"      Handle: {descriptor.handle}")
            lines.append("")

        text = "\n".join(lines).rstrip() + "\n"
        self.gatt_dump_path.write_text(text, encoding="utf-8")
        self.logger.info("DUMP written path=%s", self.gatt_dump_path)
        self._record_event("DUMP", f"Path: {self.gatt_dump_path}\n\n{text}")
        print(text)
        print(f"Saved GATT dump: {self.gatt_dump_path}")
        return self.gatt_dump_path

    def status(self) -> str:
        device_name = self._device.name if self._device and self._device.name else self.target_name
        paired_status = self._paired_status()
        rssi = self._last_rssi if self._last_rssi is not None else "unknown"
        lines = [
            f"Device Name: {device_name}",
            f"Connected: {self.is_connected}",
            f"Paired/Bonded: {paired_status}",
            f"RSSI: {rssi}",
            f"Notify Enabled: {self._notify_enabled}",
            f"Current Service UUID: {SERVICE_UUID}",
            f"Current Write UUID: {WRITE_CHARACTERISTIC}",
            f"Current Notify UUID: {NOTIFY_CHARACTERISTIC}",
        ]
        text = "\n".join(lines)
        self._record_event("STATUS", text)
        print(text)
        return text

    def export_session(self) -> Path:
        export_path = LOG_DIR / f"events_{now_compact()}.txt"
        header = "\n".join(
            [
                "MitsuBridge Session Export",
                f"Export Time: {now_iso()}",
                f"Session ID: {self.session_id}",
                f"Target Name: {self.target_name}",
                f"Target Address: {self.target_address}",
                f"Main Log: {LOG_FILE}",
                f"Notify Bin: {self.notify_bin_path}",
                f"GATT Dump: {self.gatt_dump_path}",
                "",
                "Events:",
                "",
            ]
        )
        body = "\n\n".join(self._events)
        export_path.write_text(header + body + "\n", encoding="utf-8")
        self.logger.info("EXPORT session path=%s", export_path)
        print(f"Exported session: {export_path}")
        return export_path

    def save_session(self) -> Path:
        self._write_session_log()
        print(f"Saved session: {self.session_log_path}")
        return self.session_log_path

    async def _ensure_connected(self) -> bool:
        if self.is_connected:
            return True
        print("Not connected. Connecting first...")
        return await self.connect()

    async def _find_target(self) -> BLEDevice | None:
        try:
            devices = await BleakScanner.discover(timeout=self.scan_timeout, return_adv=True)
        except Exception as exc:
            self.logger.exception("FIND_TARGET scan_failed error=%s", exc)
            self._record_event("SCAN_ERROR", f"Find target failed: {exc}")
            return None

        fallback_by_address: BLEDevice | None = None
        for device, advertisement in devices.values():
            rssi = getattr(advertisement, "rssi", None)
            if (device.name or advertisement.local_name) == self.target_name:
                self._device = device
                self._last_rssi = rssi
                return device
            if self.target_address and device.address.upper() == self.target_address:
                fallback_by_address = device
                self._last_rssi = rssi

        return fallback_by_address

    def _matches(self, device: BLEDevice, advertisement: AdvertisementData) -> bool:
        name = device.name or advertisement.local_name
        address_matches = bool(self.target_address) and device.address.upper() == self.target_address
        return name == self.target_name or address_matches

    def _notification_handler(self, sender: int | str, data: bytearray) -> None:
        payload = bytes(data)
        timestamp = now_iso()
        self._append_notify_payload(payload)
        self._log_rx("NOTIFY", NOTIFY_CHARACTERISTIC, payload)
        self._record_packet("RX", NOTIFY_CHARACTERISTIC, payload, timestamp=timestamp)
        self._notify_queue.put_nowait((timestamp, payload))

        association = self._association_report(timestamp, payload)
        report = self._notify_report(timestamp, NOTIFY_CHARACTERISTIC, payload, association)
        self._record_event("NOTIFY", report)
        print(report)

    def _handle_disconnect(self, client: BleakClient) -> None:
        self.logger.warning("DISCONNECT callback address=%s manual=%s", client.address, self._manual_disconnect)
        self._record_event("DISCONNECT", f"Callback address={client.address} manual={self._manual_disconnect}")
        self._log_disconnect(reason=f"callback address={client.address} manual={self._manual_disconnect}")
        self._client = None
        self._notify_enabled = False

        if self._manual_disconnect:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = loop.create_task(self._auto_reconnect())

    async def _auto_reconnect(self) -> None:
        while not self._manual_disconnect and not self.is_connected:
            try:
                self.logger.info("RECONNECT waiting %.1fs", self.reconnect_delay)
                self._record_event("RECONNECT", f"Waiting: {self.reconnect_delay:.1f}s")
                await asyncio.sleep(self.reconnect_delay)
                print("Disconnected. Attempting automatic reconnect...")
                if await self.connect():
                    if self._notify_requested:
                        await self.start_notify()
                    return
                self._device = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("RECONNECT unexpected_error=%s", exc)
                self._record_event("RECONNECT_ERROR", f"Error: {exc}")

    def _append_notify_payload(self, payload: bytes) -> None:
        try:
            with self.notify_bin_path.open("ab") as file:
                file.write(payload)
        except OSError as exc:
            self.logger.exception("NOTIFY bin_write_failed path=%s error=%s", self.notify_bin_path, exc)

    def _association_report(self, rx_time: str, rx_payload: bytes) -> str:
        if not self._last_tx:
            return ""

        tx = self._last_tx
        report = "\n".join(
            [
                f"TX -> id={tx.tx_id} time={tx.timestamp} uuid={tx.uuid} hex={tx.payload.hex(' ').upper()}",
                f"RX <- time={rx_time} uuid={NOTIFY_CHARACTERISTIC} hex={rx_payload.hex(' ').upper()}",
            ]
        )
        self.logger.info("ASSOC %s", report.replace("\n", " | "))
        return report

    def _notify_report(self, timestamp: str, uuid: str, payload: bytes, association: str = "") -> str:
        parts = [
            "------------------------------------------------",
            f"Time: {timestamp}",
            f"Timestamp: {timestamp}",
            f"Notify UUID: {uuid}",
            f"UUID: {uuid}",
            f"Length: {len(payload)}",
            "HEX:",
            hexdump(payload),
            f"ASCII: {ascii_preview(payload)}",
        ]
        if association:
            parts.extend(["", association])
        parts.append("------------------------------------------------")
        return "\n".join(parts)

    def _payload_report(self, label: str, uuid: str, payload: bytes) -> str:
        return "\n".join(
            [
                f"{label}",
                f"Timestamp: {now_iso()}",
                f"UUID: {uuid}",
                f"Length: {len(payload)}",
                "HEX:",
                hexdump(payload),
                f"ASCII: {ascii_preview(payload)}",
            ]
        )

    async def _wait_for_notify_ack(self, timeout: float = 2.0) -> tuple[str, bytes] | None:
        try:
            timestamp, payload = await asyncio.wait_for(self._notify_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            print("Timeout")
            self._record_event("ACK_TIMEOUT", f"Timeout: {timeout:.1f}s")
            return None

        print("ACK")
        print("Notify content:")
        print(self._notify_report(timestamp, NOTIFY_CHARACTERISTIC, payload))
        self._record_event(
            "ACK",
            f"Time: {timestamp}\nLength: {len(payload)}\nHEX:\n{hexdump(payload)}\nASCII: {ascii_preview(payload)}",
        )
        return timestamp, payload

    def _drain_notify_queue(self) -> None:
        while True:
            try:
                self._notify_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    def _record_packet(
        self,
        direction: str,
        uuid: str,
        payload: bytes,
        *,
        timestamp: str | None = None,
    ) -> None:
        packet = PacketEvent(
            timestamp=timestamp or now_iso(),
            direction=direction.upper(),
            uuid=uuid,
            payload=payload,
        )
        self._packet_events.append(packet)
        self._write_session_log()

    def _write_session_log(self) -> None:
        header = "\n".join(
            [
                "MitsuBridge Packet Session",
                f"Session ID: {self.session_id}",
                f"Updated: {now_iso()}",
                f"Target Name: {self.target_name}",
                f"Target Address: {self.target_address}",
                f"Write UUID: {WRITE_CHARACTERISTIC}",
                f"Notify UUID: {NOTIFY_CHARACTERISTIC}",
                "",
            ]
        )
        body = "\n".join(self._format_packet(packet) for packet in self._packet_events)
        self.session_log_path.write_text(header + body, encoding="utf-8")

    def _format_packet(self, packet: PacketEvent) -> str:
        return "\n".join(
            [
                "TIME",
                packet.timestamp,
                "Direction:",
                packet.direction,
                "UUID",
                packet.uuid,
                "Length",
                str(len(packet.payload)),
                "HEX",
                hexdump(packet.payload),
                "ASCII",
                ascii_preview(packet.payload),
                "-------------------------------------------------",
                "",
            ]
        )

    def _parse_tx_packets(self, session_text: str) -> list[PacketEvent]:
        packets: list[PacketEvent] = []
        for block in session_text.split("-------------------------------------------------"):
            lines = [line.rstrip() for line in block.splitlines()]
            direction = self._field_after(lines, "Direction:")
            if direction != "TX":
                continue

            timestamp = self._field_after(lines, "TIME") or now_iso()
            uuid = self._field_after(lines, "UUID") or WRITE_CHARACTERISTIC
            payload = self._parse_hex_block(lines)
            if payload:
                packets.append(PacketEvent(timestamp=timestamp, direction="TX", uuid=uuid, payload=payload))
        return packets

    def _field_after(self, lines: list[str], label: str) -> str | None:
        for index, line in enumerate(lines):
            if line.strip() == label:
                for value in lines[index + 1 :]:
                    stripped = value.strip()
                    if stripped:
                        return stripped
        return None

    def _parse_hex_block(self, lines: list[str]) -> bytes:
        try:
            start = next(index for index, line in enumerate(lines) if line.strip() == "HEX") + 1
        except StopIteration:
            return b""

        end = len(lines)
        for index in range(start, len(lines)):
            if lines[index].strip() == "ASCII":
                end = index
                break

        values: list[int] = []
        for line in lines[start:end]:
            tokens = line.strip().split()
            if tokens and len(tokens[0]) == 4 and all(char in "0123456789abcdefABCDEF" for char in tokens[0]):
                tokens = tokens[1:]
            for token in tokens:
                if len(token) == 2 and all(char in "0123456789abcdefABCDEF" for char in token):
                    values.append(int(token, 16))
        return bytes(values)

    def _paired_status(self) -> str:
        client = self._client
        if not client:
            return "unknown"

        for attr_name in ("is_paired", "paired", "bonded"):
            value = getattr(client, attr_name, None)
            if isinstance(value, bool):
                return str(value)

        return "unknown (not exposed by Bleak/CoreBluetooth)"

    def _log_disconnect(self, reason: str) -> None:
        details = "\n".join(
            [
                f"TIME: {now_iso()}",
                "Disconnect",
                f"Reason: {reason}",
                "Connected=False",
            ]
        )
        self.logger.info(
            "DISCONNECT time=%s reason=%s Connected=False",
            now_iso(),
            reason,
        )
        self._record_event("DISCONNECT", details)

    def _record_event(self, kind: str, details: str) -> None:
        self._events.append(f"[{now_iso()}] {kind}\n{details}")

    def _log_rx(self, event: str, characteristic: str, payload: bytes) -> None:
        self.logger.info(
            "RX %s uuid=%s length=%d bytes=%r hex=%s ascii=%s",
            event,
            characteristic,
            len(payload),
            payload,
            payload.hex(" ").upper(),
            ascii_preview(payload),
        )

    def _log_tx(self, event: str, characteristic: str, payload: bytes) -> None:
        self.logger.info(
            "TX %s uuid=%s length=%d bytes=%r hex=%s ascii=%s",
            event,
            characteristic,
            len(payload),
            payload,
            payload.hex(" ").upper(),
            ascii_preview(payload),
        )
