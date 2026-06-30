from __future__ import annotations

from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def now_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ascii_preview(payload: bytes) -> str:
    """Return printable ASCII characters and replace others with dots."""
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in payload)


def hexdump(payload: bytes, width: int = 8) -> str:
    """Format bytes as an offset-based hex dump."""
    if not payload:
        return ""

    rows: list[str] = []
    for offset in range(0, len(payload), width):
        chunk = payload[offset : offset + width]
        hex_bytes = " ".join(f"{byte:02X}" for byte in chunk)
        rows.append(f"{offset:04X}  {hex_bytes}")
    return "\n".join(rows)
