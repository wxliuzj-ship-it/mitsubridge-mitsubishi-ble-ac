from __future__ import annotations

import argparse
import asyncio
import shlex

from mitsubridge.confirmed_actions import CONFIRMED_ACTIONS
from mitsubridge.ble_client import MitsuBridgeClient


COMPOSITE_ACTIONS: dict[str, tuple[str, ...]] = {
    # No standalone AUTO-mode capture exists. This is a replay-only comfort profile
    # built from captured commands: cooling mode plus automatic fan speed.
    "mode_auto": ("mode_cooling", "fan_auto"),
}

ACTION_CHOICES = sorted(set(CONFIRMED_ACTIONS) | set(COMPOSITE_ACTIONS))

HELP_TEXT = """Commands:
  scan          Scan nearby BLE devices
  connect       Connect to configured target device
  disconnect    Stop notify, disconnect, wait 2 seconds, keep CLI open
  status        Show current BLE lifecycle status
  read          Read both configured characteristics
  notify        Subscribe to notification characteristic
  monitor       Connect, read, enable notify, then keep listening
  stop          Stop monitor/notify and disconnect, keep CLI open
  on            Send confirmed ON sequence only
  off           Send confirmed OFF sequence only
  dry           Send confirmed DRY mode sequence only
  fan           Send confirmed FAN mode sequence only
  heat          Send confirmed HEAT mode sequence only
  cooling       Send confirmed COOLING mode sequence only
  mode_auto     Send captured COOLING mode + AUTO fan-speed sequence
  mode_cooling  Send confirmed COOLING mode sequence only
  mode_heat     Send confirmed HEAT mode sequence only
  mode_fan      Send confirmed FAN-only mode sequence only
  mode_dry      Send confirmed DRY mode sequence only
  fan_auto      Send captured AUTO fan-speed sequence only
  fan_low       Send confirmed LOW fan-speed sequence only
  fan_medium    Send captured MEDIUM fan-speed sequence only
  fan_high      Send captured HIGH fan-speed sequence only
  temp_235      Send captured 23.5 C target-temperature sequence only
  temp_240      Send captured 24.0 C target-temperature sequence only
  temp_245      Send captured 24.5 C target-temperature sequence only
  temp_250      Send captured 25.0 C target-temperature sequence only
  temp_255      Send captured 25.5 C target-temperature sequence only
  temp_260      Send captured 26.0 C target-temperature sequence only
  temp_265      Send captured 26.5 C target-temperature sequence only
  temp_270      Send captured 27.0 C target-temperature sequence only
  temp_275      Send captured 27.5 C target-temperature sequence only
  temp_280      Send captured 28.0 C target-temperature sequence only
  write <hex>   Write manual hex payload to write characteristic
  sendfile <bin> Send a binary file to write characteristic
  replay <file> Replay all TX payloads from a session file
  dump          Dump all GATT services, characteristics, descriptors
  save_session  Save TX/RX packet session to logs/session_xxx.txt
  export        Export the current session to logs/session_xxx.txt
  help          Show this help
  exit          Disconnect and quit
"""


async def async_input(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MitsuBridge BLE reverse engineering tool")
    parser.add_argument("--debug", action="store_true", help="Enable bleak DEBUG logging")
    parser.add_argument(
        "action",
        nargs="?",
        choices=ACTION_CHOICES,
        help="One-shot confirmed action to send, then disconnect and exit",
    )
    return parser.parse_args()


async def send_action(client: MitsuBridgeClient, action: str) -> bool:
    action_key = action.lower()
    if action_key in COMPOSITE_ACTIONS:
        print(f"Sending composite {action_key.upper()} action: {' -> '.join(COMPOSITE_ACTIONS[action_key])}")
        for part in COMPOSITE_ACTIONS[action_key]:
            ok = await client.send_confirmed_action(part, settle_seconds=1.0)
            if not ok:
                return False
        return True

    return await client.send_confirmed_action(action_key)


async def run_confirmed_action_once(action: str, debug: bool = False) -> None:
    client = MitsuBridgeClient(debug=debug)
    try:
        ok = await send_action(client, action)
        client.save_session()
        if not ok:
            raise SystemExit(1)
    finally:
        await client.disconnect(reason=f"one-shot {action} command complete", print_status=False)


async def main(debug: bool = False) -> None:
    client = MitsuBridgeClient(debug=debug)
    cleanup_done = False
    print("MitsuBridge BLE debug CLI")
    if debug:
        print("Bleak DEBUG logging enabled.")
    print(HELP_TEXT)

    try:
        while True:
            try:
                raw = (await async_input("mitsubridge> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                raw = "exit"

            if not raw:
                continue

            try:
                parts = shlex.split(raw)
            except ValueError as exc:
                print(f"Invalid command: {exc}")
                continue

            command = parts[0].lower()
            args = parts[1:]

            try:
                if command == "scan":
                    await client.scan()
                elif command == "connect":
                    await client.connect()
                elif command == "disconnect":
                    await client.disconnect(reason="disconnect command")
                elif command == "status":
                    client.status()
                elif command == "read":
                    await client.read_characteristics()
                elif command == "notify":
                    await client.start_notify()
                elif command == "monitor":
                    await client.monitor()
                elif command == "stop":
                    await client.stop_monitor(reason="stop command")
                elif command in ACTION_CHOICES:
                    await send_action(client, command)
                elif command == "write":
                    if not args:
                        print("Usage: write <hex>")
                        continue
                    await client.write_hex(" ".join(args))
                elif command == "sendfile":
                    if not args:
                        print("Usage: sendfile <file.bin>")
                        continue
                    await client.send_file(" ".join(args))
                elif command == "replay":
                    if not args:
                        print("Usage: replay logs/session_xxx.txt")
                        continue
                    await client.replay_session(" ".join(args))
                elif command == "dump":
                    await client.dump_services()
                elif command == "save_session":
                    client.save_session()
                elif command == "export":
                    client.export_session()
                elif command in {"help", "?"}:
                    print(HELP_TEXT)
                elif command in {"exit", "quit"}:
                    await client.disconnect(reason="exit command")
                    cleanup_done = True
                    print("Bye.")
                    return
                else:
                    print(f"Unknown command: {command}")
                    print(HELP_TEXT)
            except Exception as exc:
                print(f"Command failed: {exc}")
                await client.disconnect(reason=f"command exception: {command}: {exc}", print_status=False)
    finally:
        if not cleanup_done:
            try:
                await client.disconnect(reason="program shutdown", print_status=False)
            except Exception as exc:
                print(f"Shutdown cleanup failed: {exc}")


if __name__ == "__main__":
    cli_args = parse_args()
    if cli_args.action:
        asyncio.run(run_confirmed_action_once(cli_args.action, debug=cli_args.debug))
    else:
        asyncio.run(main(debug=cli_args.debug))
