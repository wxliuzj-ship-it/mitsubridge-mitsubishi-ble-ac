#!/usr/bin/env python3
"""Filter PAR-40MAAC ATT Write Commands and export byte-only statistics.

Input is the timeline produced by tools/analyze_btsnoop.py. This script keeps
only ATT Write Command packets written to handle 0x0017, then groups and
compares raw bytes. It does not parse, infer, or implement the device protocol.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


FIELD_NAMES = {"TIME", "Direction", "Opcode", "Handle", "Length", "HEX", "ASCII", "Note"}
SEPARATOR = "-" * 72
TARGET_OPCODE = "0x52 ATT Write Command"
TARGET_HANDLE = "0x0017"
PRIMARY_LENGTHS = (8, 9, 13)


class FilterError(Exception):
    """Raised when the input timeline cannot be read or filtered."""


@dataclass(frozen=True)
class MrCommand:
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
            raise FilterError(f"input file does not exist: {path}")
        return path

    path = latest_timeline(root)
    if path is None:
        raise FilterError("no input file provided and no logs/hci_att_timeline_*.txt file was found")
    return path


def parse_hex_bytes(hex_text: str, command_hint: str) -> bytes:
    values: list[int] = []
    for token in hex_text.split():
        try:
            value = int(token, 16)
        except ValueError as exc:
            raise FilterError(f"{command_hint}: invalid HEX byte {token!r}") from exc
        if not 0 <= value <= 0xFF:
            raise FilterError(f"{command_hint}: HEX byte out of range {token!r}")
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


def is_target_command(fields: dict[str, str]) -> bool:
    return fields.get("Opcode") == TARGET_OPCODE and fields.get("Handle") == TARGET_HANDLE


def parse_filtered_commands(timeline_path: Path) -> tuple[list[MrCommand], list[str], int]:
    try:
        text = timeline_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FilterError(f"failed to read {timeline_path}: {exc}") from exc

    commands: list[MrCommand] = []
    warnings: list[str] = []
    write_command_count = 0

    for block in text.split(SEPARATOR):
        fields = parse_entry_fields(block)
        if fields.get("Opcode") == TARGET_OPCODE:
            write_command_count += 1
        if not is_target_command(fields):
            continue

        number = len(commands) + 1
        label = f"CMD{number:03d}"
        data = parse_hex_bytes(fields.get("HEX", ""), label)

        length_text = fields.get("Length", "")
        try:
            length = int(length_text)
        except ValueError:
            warnings.append(f"{label}: invalid Length {length_text!r}; using HEX byte count")
            length = len(data)

        if length != len(data):
            warnings.append(f"{label}: Length says {length}, HEX has {len(data)} byte(s)")

        commands.append(
            MrCommand(
                number=number,
                time=fields.get("TIME", "-"),
                length=length,
                hex_text=fields.get("HEX", ""),
                data=data,
            )
        )

    if not commands:
        raise FilterError(f"no {TARGET_OPCODE} entries with Handle {TARGET_HANDLE} were found")

    return commands, warnings, write_command_count


def grouped_commands(commands: list[MrCommand]) -> dict[str, list[MrCommand]]:
    groups: dict[str, list[MrCommand]] = {f"Length={length}": [] for length in PRIMARY_LENGTHS}
    groups["Other Length"] = []

    for command in commands:
        key = f"Length={command.length}" if command.length in PRIMARY_LENGTHS else "Other Length"
        groups[key].append(command)

    return groups


def byte_at(data: bytes, offset: int) -> int:
    return data[offset]


def byte_text(value: int) -> str:
    return f"{value:02X}"


def format_hex(data: bytes) -> str:
    return " ".join(byte_text(byte) for byte in data)


def offset_line(length: int) -> str:
    return " ".join(f"{offset:02d}" for offset in range(length))


def byte_offset_table(data: bytes) -> list[str]:
    return [
        "Byte Offset Table:",
        "Offset: " + offset_line(len(data)),
        "Byte:   " + format_hex(data),
    ]


def diff_offsets(left: MrCommand, right: MrCommand) -> list[tuple[int, int, int]]:
    if left.length != right.length:
        raise FilterError(f"{left.label} and {right.label} have different Length values")

    diffs: list[tuple[int, int, int]] = []
    for offset in range(left.length):
        left_value = byte_at(left.data, offset)
        right_value = byte_at(right.data, offset)
        if left_value != right_value:
            diffs.append((offset, left_value, right_value))
    return diffs


def commands_by_actual_length(commands: list[MrCommand]) -> dict[int, list[MrCommand]]:
    buckets: dict[int, list[MrCommand]] = {}
    for command in commands:
        buckets.setdefault(command.length, []).append(command)
    return dict(sorted(buckets.items()))


def offset_change_frequency(commands: list[MrCommand]) -> list[tuple[int, int, int, float]]:
    if len(commands) < 2:
        return []

    comparison_count = len(commands) - 1
    counts = [0] * commands[0].length

    for left, right in zip(commands, commands[1:]):
        for offset, left_value, right_value in diff_offsets(left, right):
            if left_value != right_value:
                counts[offset] += 1

    return [
        (offset, count, comparison_count, count / comparison_count * 100)
        for offset, count in enumerate(counts)
    ]


def most_common_prefix_lines(commands: list[MrCommand]) -> list[str]:
    if not commands:
        return ["(none)"]

    max_prefix_len = min(4, max(command.length for command in commands))
    lines: list[str] = []

    for prefix_len in range(1, max_prefix_len + 1):
        counter = Counter(command.data[:prefix_len] for command in commands if command.length >= prefix_len)
        if not counter:
            continue
        prefix, count = counter.most_common(1)[0]
        ratio = count / len(commands) * 100
        lines.append(f"{prefix_len} byte(s): {format_hex(prefix)} ({count}/{len(commands)}, {ratio:.1f}%)")

    return lines or ["(none)"]


def summary_lines(input_path: Path, commands: list[MrCommand], warnings: list[str], write_command_count: int) -> list[str]:
    groups = grouped_commands(commands)
    lines = [
        "MR ATT Write Commands Filtered",
        f"Input: {input_path}",
        f"Filter: Opcode = {TARGET_OPCODE}; Handle = {TARGET_HANDLE}",
        "Excluded by filter: scanning/system Bluetooth/phone/non-target records not matching both fields",
        f"All ATT Write Command count: {write_command_count}",
        f"Filtered MR command count: {len(commands)}",
    ]

    for key, group in groups.items():
        lines.append(f"{key}: {len(group)}")

    if warnings:
        lines.append(f"Warnings: {len(warnings)}")
        for warning in warnings:
            lines.append(f"- {warning}")

    return lines


def build_filtered_report(
    input_path: Path,
    commands: list[MrCommand],
    warnings: list[str],
    write_command_count: int,
) -> str:
    groups = grouped_commands(commands)
    lines = summary_lines(input_path, commands, warnings, write_command_count)
    lines.extend(["", "COMMANDS BY LENGTH", "=" * 72])

    for group_name, group in groups.items():
        lines.extend(["", group_name, "-" * 72])
        if not group:
            lines.append("(none)")
            continue

        for command in group:
            lines.extend(
                [
                    command.label,
                    f"TIME: {command.time}",
                    f"Length: {command.length}",
                    f"HEX: {command.hex_text}",
                ]
            )
            lines.extend(byte_offset_table(command.data))
            lines.append("")

    return "\n".join(lines)


def build_diff_report(
    input_path: Path,
    commands: list[MrCommand],
    warnings: list[str],
    write_command_count: int,
) -> str:
    groups = grouped_commands(commands)
    lines = summary_lines(input_path, commands, warnings, write_command_count)
    lines.extend(["", "DIFF BY LENGTH", "=" * 72])

    for group_name, group in groups.items():
        lines.extend(["", group_name, "-" * 72])
        if not group:
            lines.append("(none)")
            continue

        # The named groups are already a single length. The "Other Length"
        # group is split again so pairwise diffs are only within equal lengths.
        for actual_length, length_group in commands_by_actual_length(group).items():
            if group_name == "Other Length":
                lines.extend(["", f"Actual Length={actual_length}", "." * 72])

            lines.append(f"Command Count: {len(length_group)}")
            lines.append("Most Common Prefix:")
            lines.extend(most_common_prefix_lines(length_group))

            lines.append("Offset Change Frequency:")
            frequencies = offset_change_frequency(length_group)
            if not frequencies:
                lines.append("(need at least 2 commands)")
            else:
                for offset, count, total, percent in frequencies:
                    lines.append(f"Offset {offset}: {count}/{total} ({percent:.1f}%)")

            lines.append("Adjacent Byte Diff:")
            if len(length_group) < 2:
                lines.append("(need at least 2 commands)")
            else:
                for left, right in zip(length_group, length_group[1:]):
                    lines.append(f"{left.label} vs {right.label}")
                    diffs = diff_offsets(left, right)
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

    return "\n".join(lines)


def write_outputs(root: Path, filtered_report: str, diff_report: str) -> tuple[Path, Path]:
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    filtered_path = logs_dir / "mr_commands_filtered.txt"
    diff_path = logs_dir / "mr_command_diff_by_length.txt"
    filtered_path.write_text(filtered_report + "\n", encoding="utf-8")
    diff_path.write_text(diff_report + "\n", encoding="utf-8")
    return filtered_path, diff_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter ATT Write Commands for handle 0x0017 and export byte-only grouping/diff reports."
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
        commands, warnings, write_command_count = parse_filtered_commands(input_path)
        filtered_report = build_filtered_report(input_path, commands, warnings, write_command_count)
        diff_report = build_diff_report(input_path, commands, warnings, write_command_count)
        filtered_path, diff_path = write_outputs(root, filtered_report, diff_report)

        groups = grouped_commands(commands)
        print("MR ATT Write Commands Filtered")
        print(f"Input: {input_path}")
        print(f"Filtered MR command count: {len(commands)}")
        for key, group in groups.items():
            print(f"{key}: {len(group)}")
        if warnings:
            print(f"Warnings: {len(warnings)} (see exported reports)")
        print(f"Exported commands: {filtered_path}")
        print(f"Exported diff: {diff_path}")
        return 0
    except FilterError as exc:
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
