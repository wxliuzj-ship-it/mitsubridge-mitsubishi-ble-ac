from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.json"


@dataclass(frozen=True)
class TargetConfig:
    name: str = "M/R_XXXX"
    address: str = ""
    scan_timeout_seconds: float = 8.0
    connect_timeout_seconds: float = 15.0
    reconnect_delay_seconds: float = 5.0


@dataclass(frozen=True)
class GattConfig:
    service_uuid: str = "0277df18-e796-11e6-bf01-fe55135034f3"
    read_characteristic_1: str = "799e3b22-e797-11e6-bf01-fe55135034f3"
    read_characteristic_2: str = "def9382a-e795-11e6-bf01-fe55135034f3"
    write_characteristic: str = "e48c1528-e795-11e6-bf01-fe55135034f3"
    notify_characteristic: str = "ea1ea690-e795-11e6-bf01-fe55135034f3"


@dataclass(frozen=True)
class BridgeConfig:
    target: TargetConfig
    gatt: GattConfig


def _read_json_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON config file {path}: {exc}") from exc


def _float_value(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_value(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value).strip() or default


def load_config(path: str | Path | None = None) -> BridgeConfig:
    """Load MitsuBridge public config with environment overrides.

    The repository ships only config.example.json. Each installation should copy
    it to config.json and adjust the target device name/address locally.
    """

    config_path = Path(
        path
        or os.environ.get("MITSUBRIDGE_CONFIG")
        or DEFAULT_CONFIG_PATH
    ).expanduser()
    raw = _read_json_config(config_path)

    target_raw = raw.get("target", {}) if isinstance(raw.get("target", {}), dict) else {}
    gatt_raw = raw.get("gatt", {}) if isinstance(raw.get("gatt", {}), dict) else {}

    target_defaults = TargetConfig()
    gatt_defaults = GattConfig()

    target = TargetConfig(
        name=_string_value(
            os.environ.get("MITSUBRIDGE_TARGET_NAME", target_raw.get("name")),
            target_defaults.name,
        ),
        address=_string_value(
            os.environ.get("MITSUBRIDGE_TARGET_ADDRESS", target_raw.get("address")),
            target_defaults.address,
        ).upper(),
        scan_timeout_seconds=_float_value(
            os.environ.get("MITSUBRIDGE_SCAN_TIMEOUT", target_raw.get("scan_timeout_seconds")),
            target_defaults.scan_timeout_seconds,
        ),
        connect_timeout_seconds=_float_value(
            os.environ.get("MITSUBRIDGE_CONNECT_TIMEOUT", target_raw.get("connect_timeout_seconds")),
            target_defaults.connect_timeout_seconds,
        ),
        reconnect_delay_seconds=_float_value(
            os.environ.get("MITSUBRIDGE_RECONNECT_DELAY", target_raw.get("reconnect_delay_seconds")),
            target_defaults.reconnect_delay_seconds,
        ),
    )

    gatt = GattConfig(
        service_uuid=_string_value(
            os.environ.get("MITSUBRIDGE_SERVICE_UUID", gatt_raw.get("service_uuid")),
            gatt_defaults.service_uuid,
        ).lower(),
        read_characteristic_1=_string_value(
            os.environ.get("MITSUBRIDGE_READ_CHARACTERISTIC_1", gatt_raw.get("read_characteristic_1")),
            gatt_defaults.read_characteristic_1,
        ).lower(),
        read_characteristic_2=_string_value(
            os.environ.get("MITSUBRIDGE_READ_CHARACTERISTIC_2", gatt_raw.get("read_characteristic_2")),
            gatt_defaults.read_characteristic_2,
        ).lower(),
        write_characteristic=_string_value(
            os.environ.get("MITSUBRIDGE_WRITE_CHARACTERISTIC", gatt_raw.get("write_characteristic")),
            gatt_defaults.write_characteristic,
        ).lower(),
        notify_characteristic=_string_value(
            os.environ.get("MITSUBRIDGE_NOTIFY_CHARACTERISTIC", gatt_raw.get("notify_characteristic")),
            gatt_defaults.notify_characteristic,
        ).lower(),
    )

    return BridgeConfig(target=target, gatt=gatt)
