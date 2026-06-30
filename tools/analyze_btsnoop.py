#!/usr/bin/env python3
"""Parse BTSnoop HCI logs and export a BLE ATT/GATT timeline.

This is a standalone analysis tool. It does not import or modify the
MitsuBridge BLE runtime, and it does not infer or implement any device
control protocol. The output intentionally stays at ATT opcode/handle/value
level.
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


BTSNOOP_MAGIC = b"btsnoop\x00"
BTSNOOP_HEADER_LEN = 16
BTSNOOP_RECORD_HEADER_LEN = 24
BTSNOOP_EPOCH_DELTA_US = 0x00DCDDB30F2F8000

HCI_H4_ACL = 0x02
L2CAP_CID_ATT = 0x0004


ATT_OPCODE_NAMES = {
    0x01: "ATT Error Response",
    0x02: "ATT Exchange MTU Request",
    0x03: "ATT Exchange MTU Response",
    0x04: "ATT Find Information Request",
    0x05: "ATT Find Information Response",
    0x06: "ATT Find By Type Value Request",
    0x07: "ATT Find By Type Value Response",
    0x08: "ATT Read By Type Request",
    0x09: "ATT Read By Type Response",
    0x0A: "ATT Read Request",
    0x0B: "ATT Read Response",
    0x0C: "ATT Read Blob Request",
    0x0D: "ATT Read Blob Response",
    0x0E: "ATT Read Multiple Request",
    0x0F: "ATT Read Multiple Response",
    0x10: "ATT Read By Group Type Request",
    0x11: "ATT Read By Group Type Response",
    0x12: "ATT Write Request",
    0x13: "ATT Write Response",
    0x16: "ATT Prepare Write Request",
    0x17: "ATT Prepare Write Response",
    0x18: "ATT Execute Write Request",
    0x19: "ATT Execute Write Response",
    0x1B: "ATT Notification",
    0x1D: "ATT Indication",
    0x1E: "ATT Confirmation",
    0x52: "ATT Write Command",
    0xD2: "ATT Signed Write Command",
}


class ParseError(Exception):
    """Raised when the input is not a readable BTSnoop file."""


@dataclass(frozen=True)
class BtsnoopRecord:
    index: int
    flags: int
    timestamp_us: int
    packet: bytes


@dataclass(frozen=True)
class AclPacket:
    record_index: int
    timestamp_us: int
    direction: str
    connection_handle: int
    pb_flag: int
    payload: bytes


@dataclass(frozen=True)
class L2capPdu:
    record_index: int
    timestamp_us: int
    direction: str
    connection_handle: int
    cid: int
    payload: bytes


@dataclass(frozen=True)
class AttEvent:
    record_index: int
    timestamp_us: int
    direction: str
    opcode: int
    opcode_name: str
    handle: str
    value: bytes
    note: str = ""


class L2capReassembler:
    """Reassemble basic L2CAP PDUs from HCI ACL fragments."""

    def __init__(self) -> None:
        self._pending: dict[tuple[int, str], tuple[bytearray, int, int, int]] = {}
        self.warnings: list[str] = []

    def feed(self, acl: AclPacket) -> list[L2capPdu]:
        key = (acl.connection_handle, acl.direction)
        payload = acl.payload
        pdus: list[L2capPdu] = []

        # PB flag 0b10 is a first automatically flushable packet. Some
        # controllers also use 0b00 for a first non-flushable packet, so accept
        # both as L2CAP starts.
        if acl.pb_flag in (0x00, 0x02):
            if len(payload) < 4:
                self.warnings.append(
                    f"record {acl.record_index}: ACL start fragment is too short for L2CAP header"
                )
                return pdus

            l2cap_len = u16le(payload, 0)
            cid = u16le(payload, 2)
            total_needed = 4 + l2cap_len

            if len(payload) >= total_needed:
                complete = payload[:total_needed]
                pdus.append(
                    L2capPdu(
                        record_index=acl.record_index,
                        timestamp_us=acl.timestamp_us,
                        direction=acl.direction,
                        connection_handle=acl.connection_handle,
                        cid=cid,
                        payload=complete[4:],
                    )
                )
            else:
                self._pending[key] = (bytearray(payload), total_needed, cid, acl.record_index)
            return pdus

        # PB flag 0b01 is a continuation fragment.
        if acl.pb_flag == 0x01:
            pending = self._pending.get(key)
            if not pending:
                self.warnings.append(
                    f"record {acl.record_index}: continuation fragment without a stored L2CAP start"
                )
                return pdus

            buffer, total_needed, cid, start_record = pending
            buffer.extend(payload)
            if len(buffer) >= total_needed:
                complete = bytes(buffer[:total_needed])
                pdus.append(
                    L2capPdu(
                        record_index=start_record,
                        timestamp_us=acl.timestamp_us,
                        direction=acl.direction,
                        connection_handle=acl.connection_handle,
                        cid=cid,
                        payload=complete[4:],
                    )
                )
                del self._pending[key]
            return pdus

        self.warnings.append(f"record {acl.record_index}: unsupported ACL PB flag {acl.pb_flag}")
        return pdus


class AttParser:
    """Parse ATT PDUs while keeping simple request/response handle context."""

    def __init__(self) -> None:
        self._pending_read: dict[int, str] = {}
        self._pending_write: dict[int, str] = {}

    def parse(self, pdu: L2capPdu) -> AttEvent | None:
        if not pdu.payload:
            return None

        opcode = pdu.payload[0]
        opcode_name = ATT_OPCODE_NAMES.get(opcode, f"ATT Unknown Opcode 0x{opcode:02X}")
        payload = pdu.payload[1:]
        handle = "-"
        value = payload
        note = ""

        if opcode in (0x0A, 0x0C):  # Read Request / Read Blob Request
            handle = handle_at(pdu.payload, 1)
            value = b""
            self._pending_read[pdu.connection_handle] = handle

        elif opcode in (0x0B, 0x0D):  # Read Response / Read Blob Response
            handle = self._pending_read.pop(pdu.connection_handle, "-")
            value = payload

        elif opcode in (0x12, 0x52, 0xD2):  # Write Request / Command
            handle = handle_at(pdu.payload, 1)
            value = pdu.payload[3:] if len(pdu.payload) >= 3 else b""
            self._pending_write[pdu.connection_handle] = handle

        elif opcode == 0x13:  # Write Response
            handle = self._pending_write.pop(pdu.connection_handle, "-")
            value = b""

        elif opcode in (0x16, 0x17):  # Prepare Write Request / Response
            handle = handle_at(pdu.payload, 1)
            offset = u16le(pdu.payload, 3) if len(pdu.payload) >= 5 else None
            value = pdu.payload[5:] if len(pdu.payload) >= 5 else b""
            if offset is not None:
                note = f"offset=0x{offset:04X}"

        elif opcode in (0x1B, 0x1D):  # Notification / Indication
            handle = handle_at(pdu.payload, 1)
            value = pdu.payload[3:] if len(pdu.payload) >= 3 else b""

        elif opcode == 0x01:  # Error Response
            if len(pdu.payload) >= 5:
                request_opcode = pdu.payload[1]
                handle = handle_at(pdu.payload, 2)
                error_code = pdu.payload[4]
                note = f"request=0x{request_opcode:02X} error=0x{error_code:02X}"
                value = b""

        elif opcode in (0x04, 0x06, 0x08, 0x10):  # Range-based requests
            if len(pdu.payload) >= 5:
                start = u16le(pdu.payload, 1)
                end = u16le(pdu.payload, 3)
                handle = f"0x{start:04X}-0x{end:04X}"
                value = pdu.payload[5:]

        elif opcode in (0x05, 0x07, 0x09, 0x11):  # Discovery responses
            handles = extract_response_handles(opcode, pdu.payload)
            if handles:
                handle = ",".join(handles[:4])
                if len(handles) > 4:
                    handle += ",..."
            value = payload

        return AttEvent(
            record_index=pdu.record_index,
            timestamp_us=pdu.timestamp_us,
            direction=pdu.direction,
            opcode=opcode,
            opcode_name=opcode_name,
            handle=handle,
            value=value,
            note=note,
        )


def u16le(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        raise ParseError(f"cannot read uint16 at offset {offset}")
    return data[offset] | (data[offset + 1] << 8)


def handle_at(data: bytes, offset: int) -> str:
    if offset + 2 > len(data):
        return "-"
    return f"0x{u16le(data, offset):04X}"


def extract_response_handles(opcode: int, att: bytes) -> list[str]:
    handles: list[str] = []
    if len(att) < 2:
        return handles

    if opcode in (0x09, 0x11):  # First byte after opcode is entry length.
        entry_len = att[1]
        if entry_len < 2:
            return handles
        offset = 2
        while offset + 2 <= len(att):
            handles.append(handle_at(att, offset))
            offset += entry_len
        return handles

    if opcode == 0x05:  # Format byte, then handle/UUID pairs.
        fmt = att[1]
        entry_len = 4 if fmt == 0x01 else 18 if fmt == 0x02 else 0
        offset = 2
        while entry_len and offset + 2 <= len(att):
            handles.append(handle_at(att, offset))
            offset += entry_len
        return handles

    if opcode == 0x07:  # Pairs of found handle and group end handle.
        offset = 1
        while offset + 4 <= len(att):
            handles.append(handle_at(att, offset))
            offset += 4
        return handles

    return handles


def parse_btsnoop_records(path: Path) -> tuple[list[BtsnoopRecord], list[str]]:
    warnings: list[str] = []
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ParseError(f"failed to read {path}: {exc}") from exc

    if len(data) < BTSNOOP_HEADER_LEN:
        raise ParseError("file is too small to be a BTSnoop log")

    magic = data[:8]
    if magic != BTSNOOP_MAGIC:
        raise ParseError("invalid BTSnoop magic header")

    version, datalink = struct.unpack(">II", data[8:16])
    if version != 1:
        warnings.append(f"unexpected BTSnoop version {version}; attempting to parse anyway")

    # 1002 is HCI UART (H4), which is what Samsung bugreports normally export.
    if datalink != 1002:
        warnings.append(f"unexpected BTSnoop datalink {datalink}; expected 1002 for HCI UART (H4)")

    records: list[BtsnoopRecord] = []
    offset = BTSNOOP_HEADER_LEN
    index = 0
    while offset + BTSNOOP_RECORD_HEADER_LEN <= len(data):
        index += 1
        try:
            _orig_len, included_len, flags, _drops, timestamp_us = struct.unpack(
                ">IIIIQ", data[offset : offset + BTSNOOP_RECORD_HEADER_LEN]
            )
        except struct.error as exc:
            warnings.append(f"record {index}: malformed header: {exc}")
            break

        offset += BTSNOOP_RECORD_HEADER_LEN
        end = offset + included_len
        if end > len(data):
            warnings.append(f"record {index}: included length exceeds remaining file bytes")
            break

        records.append(BtsnoopRecord(index=index, flags=flags, timestamp_us=timestamp_us, packet=data[offset:end]))
        offset = end

    if offset != len(data):
        warnings.append(f"{len(data) - offset} trailing byte(s) were not parsed")

    return records, warnings


def parse_acl(record: BtsnoopRecord, warnings: list[str]) -> AclPacket | None:
    packet = record.packet
    if not packet or packet[0] != HCI_H4_ACL:
        return None

    if len(packet) < 5:
        warnings.append(f"record {record.index}: ACL packet is too short")
        return None

    handle_and_flags = u16le(packet, 1)
    connection_handle = handle_and_flags & 0x0FFF
    pb_flag = (handle_and_flags >> 12) & 0x03
    acl_len = u16le(packet, 3)
    payload = packet[5 : 5 + acl_len]

    if len(payload) < acl_len:
        warnings.append(f"record {record.index}: ACL payload is shorter than advertised length")

    # Android BTSnoop commonly stores sent packets with flags bit 0 clear and
    # received packets with flags bit 0 set. Report direction from the phone's
    # perspective because that is the useful view for reverse engineering.
    direction = "TX Host->Controller" if (record.flags & 0x01) == 0 else "RX Controller->Host"

    return AclPacket(
        record_index=record.index,
        timestamp_us=record.timestamp_us,
        direction=direction,
        connection_handle=connection_handle,
        pb_flag=pb_flag,
        payload=payload,
    )


def parse_att_events(records: Iterable[BtsnoopRecord]) -> tuple[list[AttEvent], list[str]]:
    warnings: list[str] = []
    reassembler = L2capReassembler()
    att_parser = AttParser()
    events: list[AttEvent] = []

    for record in records:
        try:
            acl = parse_acl(record, warnings)
            if acl is None:
                continue

            for pdu in reassembler.feed(acl):
                if pdu.cid != L2CAP_CID_ATT:
                    continue
                event = att_parser.parse(pdu)
                if event is not None:
                    events.append(event)
        except Exception as exc:
            warnings.append(f"record {record.index}: parse error: {exc}")

    warnings.extend(reassembler.warnings)
    return events, warnings


def btsnoop_time_to_text(timestamp_us: int) -> str:
    unix_us = timestamp_us - BTSNOOP_EPOCH_DELTA_US
    try:
        # Android bugreport BTSnoop timestamps commonly line up with the
        # device/log clock. Keep that clock as-is instead of applying the
        # host computer's timezone offset during offline analysis.
        dt = datetime.utcfromtimestamp(unix_us / 1_000_000)
        return dt.isoformat(timespec="milliseconds")
    except (OverflowError, OSError, ValueError):
        return f"raw_us={timestamp_us}"


def ascii_preview(payload: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in payload)


def hex_preview(payload: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in payload)


def build_summary(input_path: Path, records: list[BtsnoopRecord], events: list[AttEvent]) -> list[str]:
    counts: dict[int, int] = {}
    for event in events:
        counts[event.opcode] = counts.get(event.opcode, 0) + 1

    return [
        "BTSnoop ATT/GATT Analysis",
        f"Input: {input_path}",
        f"Total packets: {len(records)}",
        f"BLE ATT packets: {len(events)}",
        f"ATT Write Request: {counts.get(0x12, 0)}",
        f"ATT Write Command: {counts.get(0x52, 0)}",
        f"ATT Notification: {counts.get(0x1B, 0)}",
        f"ATT Read Request / Response: {counts.get(0x0A, 0)} / {counts.get(0x0B, 0)}",
    ]


def build_timeline(input_path: Path, records: list[BtsnoopRecord], events: list[AttEvent], warnings: list[str]) -> str:
    lines: list[str] = []
    lines.extend(build_summary(input_path, records, events))
    if warnings:
        lines.append(f"Warnings: {len(warnings)}")
        for warning in warnings[:50]:
            lines.append(f"- {warning}")
        if len(warnings) > 50:
            lines.append(f"- ... {len(warnings) - 50} more warning(s)")

    lines.append("=" * 72)

    for event in events:
        lines.extend(
            [
                "TIME",
                btsnoop_time_to_text(event.timestamp_us),
                "Direction",
                event.direction,
                "Opcode",
                f"0x{event.opcode:02X} {event.opcode_name}",
                "Handle",
                event.handle,
                "Length",
                str(len(event.value)),
                "HEX",
                hex_preview(event.value),
                "ASCII",
                ascii_preview(event.value),
            ]
        )
        if event.note:
            lines.extend(["Note", event.note])
        lines.append("-" * 72)

    return "\n".join(lines) + "\n"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def compact_now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def default_input_candidates(root: Path) -> list[Path]:
    names = ["btsnoop_hci.log", "btsnoop_hci(1).log"]
    candidates: list[Path] = []
    for base in [Path("/mnt/data"), root, root / "logs", Path.cwd(), Path.cwd() / "logs"]:
        for name in names:
            candidates.append(base / name)
    return candidates


def resolve_input_path(arg: str | None, root: Path) -> Path:
    if arg:
        path = Path(arg).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise ParseError(f"input file does not exist: {path}")
        return path

    for candidate in default_input_candidates(root):
        if candidate.exists():
            return candidate

    searched = "\n".join(str(path) for path in default_input_candidates(root))
    raise ParseError("no input file provided and no default BTSnoop log was found. Searched:\n" + searched)


def write_timeline(root: Path, timeline: str) -> Path:
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_path = logs_dir / f"hci_att_timeline_{compact_now()}.txt"
    output_path.write_text(timeline, encoding="utf-8")
    return output_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a BTSnoop HCI UART log and export BLE ATT/GATT packet timeline."
    )
    parser.add_argument(
        "logfile",
        nargs="?",
        help="Path to btsnoop_hci.log, for example logs/btsnoop_hci.log",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = project_root()

    try:
        input_path = resolve_input_path(args.logfile, root)
        records, file_warnings = parse_btsnoop_records(input_path)
        events, parse_warnings = parse_att_events(records)
        warnings = file_warnings + parse_warnings
        timeline = build_timeline(input_path, records, events, warnings)
        output_path = write_timeline(root, timeline)

        for line in build_summary(input_path, records, events):
            print(line)
        if warnings:
            print(f"Warnings: {len(warnings)} (see exported timeline)")
        print(f"Exported timeline: {output_path}")
        return 0
    except ParseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
