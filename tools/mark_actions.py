#!/usr/bin/env python3
"""Mark filtered MR commands with manually supplied action windows.

Input is logs/mr_commands_filtered.txt from tools/filter_mr_commands.py. This
script keeps only Length=13 and Length=8 commands, assigns them to manually
filled ACTION time windows, and compares bytes against the previous ACTION's
same-Length command. It does not parse, infer, or implement the device
protocol.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path


ACTION_DEFINITIONS = [
    ("ACTION01", "开机"),
    ("ACTION02", "温度 23.5->24.0"),
    ("ACTION03", "温度 24.0->24.5"),
    ("ACTION04", "温度 24.5->25.0"),
    ("ACTION05", "风量 自动->低"),
    ("ACTION06", "风量 低->中"),
    ("ACTION07", "风量 中->高"),
    ("ACTION08", "风量 高->自动"),
    ("ACTION09", "模式 制冷->除湿"),
    ("ACTION10", "模式 除湿->制热"),
    ("ACTION11", "模式 制热->制冷"),
    ("ACTION12", "关机"),
]

TARGET_LENGTHS = {8, 13}
CMD_RE = re.compile(r"^CMD\d{3}$")
WINDOW_RE = re.compile(r"^(ACTION\d{2})\s+(.+?)\s+START=(\S*)\s+END=(\S*)\s*$")


class MarkError(Exception):
    """Raised when commands or action windows cannot be parsed."""


@dataclass(frozen=True)
class Command:
    label: str
    timestamp: datetime
    time_text: str
    length: int
    hex_text: str
    data: bytes


@dataclass(frozen=True)
class ActionWindow:
    action_id: str
    name: str
    start: datetime | None
    end: datetime | None

    @property
    def is_filled(self) -> bool:
        return self.start is not None and self.end is not None


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_input(root: Path) -> Path:
    return root / "logs" / "mr_commands_filtered.txt"


def default_template(root: Path) -> Path:
    return root / "logs" / "action_windows_template.txt"


def default_output(root: Path) -> Path:
    return root / "logs" / "action_marked_commands.txt"


def resolve_input_path(arg: str | None, root: Path) -> Path:
    path = Path(arg).expanduser() if arg else default_input(root)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise MarkError(f"input file does not exist: {path}")
    return path


def resolve_path(arg: str | None, fallback: Path) -> Path:
    path = Path(arg).expanduser() if arg else fallback
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def template_text() -> str:
    return "\n".join(f"{action_id} {name} START= END=" for action_id, name in ACTION_DEFINITIONS) + "\n"


def write_template(template_path: Path, force: bool) -> bool:
    if template_path.exists() and not force:
        return False
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(template_text(), encoding="utf-8")
    return True


def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise MarkError(f"invalid command TIME {value!r}") from exc


def parse_window_time(value: str, default_date: date) -> datetime:
    value = value.strip()
    if not value:
        raise MarkError("empty window time")

    if "T" in value:
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise MarkError(f"invalid window time {value!r}") from exc

    try:
        return datetime.combine(default_date, time.fromisoformat(value))
    except ValueError as exc:
        raise MarkError(f"invalid window time {value!r}; use ISO time or HH:MM:SS[.mmm]") from exc


def parse_hex_bytes(hex_text: str, command_hint: str) -> bytes:
    values: list[int] = []
    for token in hex_text.split():
        try:
            value = int(token, 16)
        except ValueError as exc:
            raise MarkError(f"{command_hint}: invalid HEX byte {token!r}") from exc
        if not 0 <= value <= 0xFF:
            raise MarkError(f"{command_hint}: HEX byte out of range {token!r}")
        values.append(value)
    return bytes(values)


def parse_filtered_commands(path: Path) -> list[Command]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MarkError(f"failed to read {path}: {exc}") from exc

    commands: list[Command] = []
    index = 0
    while index < len(lines):
        label = lines[index].strip()
        if not CMD_RE.match(label):
            index += 1
            continue

        fields: dict[str, str] = {}
        scan = index + 1
        while scan < len(lines):
            line = lines[scan].strip()
            if CMD_RE.match(line) or line.startswith("Length=") or line.startswith("Other Length"):
                break
            if line.startswith("TIME:"):
                fields["TIME"] = line.split(":", 1)[1].strip()
            elif line.startswith("Length:"):
                fields["Length"] = line.split(":", 1)[1].strip()
            elif line.startswith("HEX:"):
                fields["HEX"] = line.split(":", 1)[1].strip()
            scan += 1

        if {"TIME", "Length", "HEX"} <= fields.keys():
            try:
                length = int(fields["Length"])
            except ValueError as exc:
                raise MarkError(f"{label}: invalid Length {fields['Length']!r}") from exc

            if length in TARGET_LENGTHS:
                data = parse_hex_bytes(fields["HEX"], label)
                if len(data) != length:
                    raise MarkError(f"{label}: Length says {length}, HEX has {len(data)} byte(s)")
                commands.append(
                    Command(
                        label=label,
                        timestamp=parse_timestamp(fields["TIME"]),
                        time_text=fields["TIME"],
                        length=length,
                        hex_text=fields["HEX"],
                        data=data,
                    )
                )

        index = max(scan, index + 1)

    if not commands:
        raise MarkError("no Length=13 or Length=8 commands were found")

    return sorted(commands, key=lambda command: command.timestamp)


def parse_action_windows(template_path: Path, default_date: date) -> list[ActionWindow]:
    try:
        lines = template_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MarkError(f"failed to read {template_path}: {exc}") from exc

    windows: list[ActionWindow] = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = WINDOW_RE.match(stripped)
        if not match:
            raise MarkError(f"{template_path}:{line_number}: invalid action window line")

        action_id, name, start_text, end_text = match.groups()
        start = parse_window_time(start_text, default_date) if start_text else None
        end = parse_window_time(end_text, default_date) if end_text else None
        if (start is None) != (end is None):
            raise MarkError(f"{action_id}: START and END must both be filled or both be empty")
        if start is not None and end is not None and start > end:
            raise MarkError(f"{action_id}: START is later than END")
        windows.append(ActionWindow(action_id=action_id, name=name, start=start, end=end))

    expected_ids = [action_id for action_id, _name in ACTION_DEFINITIONS]
    found_ids = [window.action_id for window in windows]
    missing = [action_id for action_id in expected_ids if action_id not in found_ids]
    if missing:
        raise MarkError("missing action window(s): " + ", ".join(missing))

    return windows


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


def diff_lines(previous: Command | None, current: Command) -> list[str]:
    if previous is None:
        return ["Diff vs previous ACTION same Length:", "(none)"]

    lines = [f"Diff vs previous ACTION same Length ({previous.label} -> {current.label}):"]
    diffs = []
    for offset, (left, right) in enumerate(zip(previous.data, current.data)):
        if left != right:
            diffs.append((offset, left, right))

    if not diffs:
        lines.append("(no byte difference)")
        return lines

    for offset, left, right in diffs:
        lines.extend([f"Offset {offset}", f"{byte_text(left)} -> {byte_text(right)}"])
    return lines


def commands_in_window(commands: list[Command], window: ActionWindow) -> list[Command]:
    if window.start is None or window.end is None:
        return []
    return [command for command in commands if window.start <= command.timestamp <= window.end]


def build_marked_report(
    input_path: Path,
    template_path: Path,
    commands: list[Command],
    windows: list[ActionWindow],
) -> str:
    lines = [
        "Action Marked MR Commands",
        f"Input: {input_path}",
        f"Action Windows: {template_path}",
        "Included Length: 8, 13",
        "Diff rule: compare each command with the previous ACTION's latest command of the same Length",
        "",
    ]

    previous_action_latest_by_length: dict[int, Command] = {}
    assigned_labels: set[str] = set()

    for window in windows:
        action_commands = commands_in_window(commands, window)
        assigned_labels.update(command.label for command in action_commands)
        lines.extend(
            [
                f"{window.action_id} {window.name}",
                f"START={window.start.isoformat(timespec='milliseconds') if window.start else ''}",
                f"END={window.end.isoformat(timespec='milliseconds') if window.end else ''}",
                f"Command Count: {len(action_commands)}",
                "-" * 72,
            ]
        )

        if not action_commands:
            lines.append("(no Length=8/13 command in this window)")
        else:
            for command in action_commands:
                previous = previous_action_latest_by_length.get(command.length)
                lines.extend(
                    [
                        command.label,
                        f"TIME: {command.time_text}",
                        f"Length: {command.length}",
                        f"HEX: {command.hex_text}",
                    ]
                )
                lines.extend(byte_offset_table(command.data))
                lines.extend(diff_lines(previous, command))
                lines.append("")

        current_latest_by_length: dict[int, Command] = {}
        for command in action_commands:
            current_latest_by_length[command.length] = command
        previous_action_latest_by_length = current_latest_by_length
        lines.append("")

    unassigned = [command for command in commands if command.label not in assigned_labels]
    lines.extend(["UNASSIGNED LENGTH=8/13 COMMANDS", "=" * 72, f"Command Count: {len(unassigned)}"])
    for command in unassigned:
        lines.extend([command.label, f"TIME: {command.time_text}", f"Length: {command.length}", f"HEX: {command.hex_text}", ""])

    return "\n".join(lines)


def write_marked_output(output_path: Path, report: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create action window template and mark Length=8/13 MR commands by manual action windows."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to logs/mr_commands_filtered.txt. Defaults to logs/mr_commands_filtered.txt.",
    )
    parser.add_argument(
        "--template",
        help="Path to action_windows_template.txt. Defaults to logs/action_windows_template.txt.",
    )
    parser.add_argument(
        "--output",
        help="Path to action_marked_commands.txt. Defaults to logs/action_marked_commands.txt.",
    )
    parser.add_argument(
        "--force-template",
        action="store_true",
        help="Regenerate the action window template even if it already exists.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = project_root()

    try:
        input_path = resolve_input_path(args.input, root)
        template_path = resolve_path(args.template, default_template(root))
        output_path = resolve_path(args.output, default_output(root))

        commands = parse_filtered_commands(input_path)
        template_created = write_template(template_path, args.force_template)
        windows = parse_action_windows(template_path, commands[0].timestamp.date())
        incomplete = [window.action_id for window in windows if not window.is_filled]

        print("Action Window Marking")
        print(f"Input: {input_path}")
        print(f"Template: {template_path}")
        print(f"Length=8/13 command count: {len(commands)}")

        if template_created:
            print("Template created. Fill START/END and run this command again.")
            return 0

        if incomplete:
            print("Template exists but has empty window(s): " + ", ".join(incomplete))
            print("Fill START/END and run this command again.")
            return 0

        report = build_marked_report(input_path, template_path, commands, windows)
        write_marked_output(output_path, report)
        print(f"Exported marked commands: {output_path}")
        return 0
    except MarkError as exc:
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
