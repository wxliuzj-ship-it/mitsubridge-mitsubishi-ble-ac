#!/usr/bin/env python3
"""Find byte-level differences between ATT Write Command entries.

This tool consumes the timeline exported by tools/analyze_btsnoop.py. It does
not parse the device protocol and does not infer fields. It only compares raw
bytes from ATT Write Command payloads in chronological order.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


FIELD_NAMES = {"TIME", "Direction", "Opcode", "Handle", "Length", "HEX", "ASCII", "Note"}
SEPARATOR = "-" * 72


class DiffError(Exception):
    """Raised when the input timeline cannot be read or parsed."""


@dataclass(frozen=True)
class Command:
    number: int
    time: str
    length: int
    hex_text: str
    data: bytes

    @property
    def label(self) -> str:
        return f"CMD{self.number:03d}"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def latest_timeline(root: Path) -> Path | None:
    timelines = sorted((root / "logs").glob("hci_att_timeline_*.txt"), key=lambda path: path.stat().st_mtime)
    return timelines[-1] if timelines else None


def resolve_input_path(arg: str | None, root: Path) -> Path:
    if arg:
        path = Path(arg).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise DiffError(f"input file does not exist: {path}")
        return path

    path = latest_timeline(root)
    if path is None:
        raise DiffError("no input file provided and no logs/hci_att_timeline_*.txt file was found")
    return path


def parse_hex_bytes(hex_text: str, command_hint: str) -> bytes:
    values: list[int] = []
    for token in hex_text.split():
        try:
            value = int(token, 16)
        except ValueError as exc:
            raise DiffError(f"{command_hint}: invalid HEX byte {token!r}") from exc
        if not 0 <= value <= 0xFF:
            raise DiffError(f"{command_hint}: HEX byte out of range {token!r}")
        values.append(value)
    return bytes(values)


def parse_entry_fields(block: str) -> dict[str, str]:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    fields: dict[str, str] = {}
    index = 0

    while index < len(lines):
        label = lines[index]
        if label in FIELD_NAMES and index + 1 < len(lines):
            fields[label] = lines[index + 1]
            index += 2
            continue
        index += 1

    return fields


def parse_write_commands(timeline_path: Path) -> tuple[list[Command], list[str]]:
    try:
        text = timeline_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiffError(f"failed to read {timeline_path}: {exc}") from exc

    commands: list[Command] = []
    warnings: list[str] = []

    for block in text.split(SEPARATOR):
        fields = parse_entry_fields(block)
        opcode = fields.get("Opcode", "")
        if "ATT Write Command" not in opcode:
            continue

        number = len(commands) + 1
        label = f"CMD{number:03d}"
        hex_text = fields.get("HEX", "")
        data = parse_hex_bytes(hex_text, label)

        length_text = fields.get("Length", "")
        try:
            length = int(length_text)
        except ValueError:
            warnings.append(f"{label}: invalid Length {length_text!r}; using HEX byte count")
            length = len(data)

        if length != len(data):
            warnings.append(f"{label}: Length says {length}, HEX has {len(data)} byte(s)")

        commands.append(
            Command(
                number=number,
                time=fields.get("TIME", "-"),
                length=length,
                hex_text=hex_text,
                data=data,
            )
        )

    if not commands:
        raise DiffError("no ATT Write Command entries were found in the timeline")

    return commands, warnings


def byte_at(data: bytes, offset: int) -> int | None:
    return data[offset] if offset < len(data) else None


def byte_text(value: int | None) -> str:
    return "--" if value is None else f"{value:02X}"


def byte_offsets(length: int) -> str:
    return " ".join(str(offset) for offset in range(length))


def diff_offsets(left: bytes, right: bytes) -> list[tuple[int, int | None, int | None]]:
    max_len = max(len(left), len(right))
    diffs: list[tuple[int, int | None, int | None]] = []

    for offset in range(max_len):
        left_value = byte_at(left, offset)
        right_value = byte_at(right, offset)
        if left_value != right_value:
            diffs.append((offset, left_value, right_value))

    return diffs


def offset_statistics(commands: list[Command]) -> tuple[list[int], list[int]]:
    if len(commands) < 2:
        max_len = max((len(command.data) for command in commands), default=0)
        return [], list(range(max_len))

    max_len = max(len(command.data) for command in commands)
    comparison_count = len(commands) - 1
    changed_counts = {offset: 0 for offset in range(max_len)}

    for left, right in zip(commands, commands[1:]):
        for offset in range(max_len):
            if byte_at(left.data, offset) != byte_at(right.data, offset):
                changed_counts[offset] += 1

    always_changed = [offset for offset, count in changed_counts.items() if count == comparison_count]
    never_changed = [offset for offset, count in changed_counts.items() if count == 0]
    return always_changed, never_changed


def format_offset_list(offsets: list[int]) -> str:
    return ", ".join(f"Offset {offset}" for offset in offsets) if offsets else "(none)"


def build_report(input_path: Path, commands: list[Command], warnings: list[str]) -> str:
    lines: list[str] = [
        "ATT Write Command Byte Diff",
        f"Input: {input_path}",
        f"Write Command Count: {len(commands)}",
    ]

    if warnings:
        lines.append(f"Warnings: {len(warnings)}")
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.extend(["", "COMMANDS", "=" * 72])
    for command in commands:
        lines.extend(
            [
                command.label,
                f"TIME: {command.time}",
                f"Length: {command.length}",
                "Byte Offset:",
                byte_offsets(len(command.data)),
                "HEX:",
                command.hex_text,
                "",
            ]
        )

    lines.extend(["PAIRWISE DIFF", "=" * 72])
    if len(commands) < 2:
        lines.append("Only one command was found; no pairwise diff can be calculated.")
    else:
        for left, right in zip(commands, commands[1:]):
            lines.append(f"{left.label} vs {right.label}")
            diffs = diff_offsets(left.data, right.data)
            if not diffs:
                lines.append("(no byte difference)")
            for offset, left_value, right_value in diffs:
                lines.extend(
                    [
                        f"Offset {offset}",
                        f"{byte_text(left_value)} -> {byte_text(right_value)}",
                    ]
                )
            lines.append("")

    always_changed, never_changed = offset_statistics(commands)
    lines.extend(
        [
            "OFFSET STATISTICS",
            "=" * 72,
            "Offsets changed in every adjacent comparison:",
            format_offset_list(always_changed),
            "Offsets never changed:",
            format_offset_list(never_changed),
            "",
        ]
    )

    return "\n".join(lines)


def write_report(root: Path, report: str) -> Path:
    output_path = root / "logs" / "command_diff.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report + "\n", encoding="utf-8")
    return output_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare ATT Write Command bytes from an exported HCI ATT timeline."
    )
    parser.add_argument(
        "timeline",
        nargs="?",
        help="Path to logs/hci_att_timeline_YYYYMMDD_HHMMSS.txt. Defaults to the latest timeline in logs/.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = project_root()

    try:
        input_path = resolve_input_path(args.timeline, root)
        commands, warnings = parse_write_commands(input_path)
        report = build_report(input_path, commands, warnings)
        output_path = write_report(root, report)

        print("ATT Write Command Byte Diff")
        print(f"Input: {input_path}")
        print(f"Write Command Count: {len(commands)}")
        if warnings:
            print(f"Warnings: {len(warnings)} (see exported report)")
        print(f"Exported diff: {output_path}")
        return 0
    except DiffError as exc:
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
