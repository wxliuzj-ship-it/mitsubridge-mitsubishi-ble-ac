# MitsuBridge

MitsuBridge is a local macOS BLE reverse engineering and HomeKit bridge tool for Mitsubishi Electric PAR-40MAAC / MELRemo Bluetooth controllers.

This project scans, connects, reads, subscribes, logs, and manually writes user-provided hex payloads. It also exposes replay commands for power, mode, target temperature, and fan speed using captured PAR-40MAAC byte sequences. It does not implement Home Assistant, MQTT, or any guessed control commands.

This is an independent community project. It is not affiliated with or endorsed by Mitsubishi Electric.

## Supported Device Family

- Mitsubishi Electric PAR-40MAAC / MELRemo BLE controller family.
- Typical BLE local name pattern: `M/R_*`.
- A ready-to-use public profile is included at `profiles/mitsubishi_par40maac_melremo.json`.

macOS usually does not expose the real public BLE MAC address through CoreBluetooth. On macOS, MitsuBridge therefore prioritizes matching by the configured device name; address matching is kept as a fallback for platforms where Bleak exposes it.

## GATT UUIDs

- Service: `0277df18-e796-11e6-bf01-fe55135034f3`
- Read Characteristic 1: `799e3b22-e797-11e6-bf01-fe55135034f3`
- Read Characteristic 2: `def9382a-e795-11e6-bf01-fe55135034f3`
- Write Characteristic: `e48c1528-e795-11e6-bf01-fe55135034f3`
- Notify Characteristic: `ea1ea690-e795-11e6-bf01-fe55135034f3`

## macOS Setup

Install Python 3.10 or newer. Then run:

```bash
cd MitsuBridge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
npm install
```

If macOS asks for Bluetooth permission, allow Terminal, iTerm, VS Code, or the app you use to run Python:

`System Settings` -> `Privacy & Security` -> `Bluetooth`

## Run

Copy the public template to a local config file first:

```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "target": {
    "name": "M/R_XXXX",
    "address": ""
  },
  "homekit": {
    "name": "Mitsubishi AC"
  }
}
```

`config.json` is intentionally ignored by git. Do not commit your real BLE address, room name, HomeKit pairing state, or HCI capture logs.

```bash
cd MitsuBridge
source .venv/bin/activate
python main.py
```

Enable Bleak debug logging:

```bash
python main.py --debug
```

## CLI Commands

```text
scan          Scan nearby BLE devices
connect       Connect to configured target device
disconnect    Stop notify, disconnect, wait 2 seconds, keep CLI open
status        Show current BLE lifecycle status
read          Read both configured characteristics
notify        Subscribe to notification characteristic
monitor       Connect, read both characteristics, enable notify, then keep listening
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
dump          Dump all GATT services, characteristics, descriptors, properties
save_session  Save TX/RX packet session to logs/session_xxx.txt
export        Export the current session to logs/session_xxx.txt
help          Show help
exit          Disconnect and quit
```

Examples:

```text
mitsubridge> scan
mitsubridge> monitor
mitsubridge> status
mitsubridge> on
mitsubridge> off
mitsubridge> dry
mitsubridge> fan
mitsubridge> heat
mitsubridge> cooling
mitsubridge> mode_auto
mitsubridge> mode_cooling
mitsubridge> mode_heat
mitsubridge> mode_fan
mitsubridge> mode_dry
mitsubridge> fan_auto
mitsubridge> fan_low
mitsubridge> fan_medium
mitsubridge> fan_high
mitsubridge> temp_260
mitsubridge> temp_280
mitsubridge> write 01 02 0a ff
mitsubridge> write AABBCCDD
mitsubridge> sendfile payload.bin
mitsubridge> save_session
mitsubridge> replay logs/session_20260629_201829.txt
mitsubridge> stop
mitsubridge> disconnect
mitsubridge> dump
mitsubridge> export
mitsubridge> exit
```

The `monitor` command automatically runs:

1. `connect`
2. `read`
3. `notify`

After that, notifications continue streaming while you can keep sending manual `write <hex>` commands. TX generated by MitsuBridge and RX from read/notify are written to the packet session file.

## Replay Mode

MitsuBridge automatically saves a packet session to:

```text
logs/session_YYYYMMDD_HHMMSS.txt
```

Each packet uses this format:

```text
TIME
2026-06-29T20:00:00.000
Direction:
TX
UUID
e48c1528-e795-11e6-bf01-fe55135034f3
Length
4
HEX
0000  01 02 03 04
ASCII
....
-------------------------------------------------
```

Replay sends only TX payloads from the session file, in saved order:

```text
mitsubridge> replay logs/session_20260629_201829.txt
```

Replay does not modify bytes, does not infer commands, and does not implement control logic. It simply re-sends the captured TX payloads.

## Confirmed Replay Commands

User-confirmed PAR-40MAAC replay actions are exposed as narrow safety commands:

```text
mitsubridge> on
mitsubridge> off
mitsubridge> dry
mitsubridge> fan
mitsubridge> heat
mitsubridge> cooling
mitsubridge> mode_auto
mitsubridge> mode_cooling
mitsubridge> mode_heat
mitsubridge> mode_fan
mitsubridge> mode_dry
mitsubridge> fan_auto
mitsubridge> fan_low
mitsubridge> fan_medium
mitsubridge> fan_high
mitsubridge> temp_235
mitsubridge> temp_240
mitsubridge> temp_245
mitsubridge> temp_250
mitsubridge> temp_255
mitsubridge> temp_260
mitsubridge> temp_265
mitsubridge> temp_270
mitsubridge> temp_275
mitsubridge> temp_280
```

They can also be run once from the shell:

```bash
python main.py on
python main.py off
python main.py dry
python main.py fan
python main.py heat
python main.py cooling
python main.py mode_auto
python main.py fan_high
python main.py fan_low
python main.py temp_260
python main.py temp_280
```

These commands only send confirmed byte sequences recorded from phone HCI captures and validated on the physical controller:

- `on`: CL37 / CMD292-CMD300
- `off`: CL39 / CMD308-CMD316
- `dry`: CL29 / CMD226-CMD234
- `fan`: CL30 / CMD235-CMD243
- `heat`: CL32 / CMD251-CMD259
- `cooling`: CL35 / CMD274-CMD282
- `mode_auto`: composite `mode_cooling` + `fan_auto`; no standalone AUTO-mode byte sequence is guessed
- `mode_cooling`: alias of `cooling`
- `mode_heat`: alias of `heat`
- `mode_fan`: alias of `fan`
- `mode_dry`: alias of `dry`
- `fan_auto`: CL10 / CMD380-CMD388
- `fan_low`: CL06 / CMD346-CMD354
- `fan_medium`: CL07 / CMD355-CMD363
- `fan_high`: CL09 / CMD371-CMD379
- `temp_235`: CL14 / CMD107-CMD115
- `temp_240`: CL15 / CMD116-CMD124
- `temp_245`: CL17 / CMD132-CMD140
- `temp_250`: CL18 / CMD141-CMD149
- `temp_255`: CL20 / CMD157-CMD165
- `temp_260`: CL22 / CMD173-CMD181
- `temp_265`: CMD100-CMD108 from `hci_att_timeline_20260630_211927.txt`
- `temp_270`: CMD034-CMD042 from `hci_att_timeline_20260630_211927.txt`
- `temp_275`: CMD050-CMD058 from `hci_att_timeline_20260630_211927.txt`
- `temp_280`: CMD059-CMD067 from `hci_att_timeline_20260630_211927.txt`

They connect if needed, read the two configured characteristics, enable notify, then send the confirmed sequence as ATT Write Command / no-response writes. They do not decode fields, infer protocol meaning, or generate new control bytes.

In the validation session `logs/session_20260630_192440.txt`, the `fan` command changed the real controller state correctly, but its notify response could lag or repeat the previous mode. Treat physical controller state as the validation source for these replay commands.

`fan` / `mode_fan` means fan-only mode. `fan_auto`, `fan_low`, `fan_medium`, and `fan_high` mean fan speed while preserving the current operating mode. In the validation sessions `logs/session_20260630_193823.txt` and `logs/session_20260630_194032.txt`, the user confirmed low fan speed, cooling mode, and 25.0 C setpoint were correct. A heat-mode 26.0 C combination was not confirmed in summer conditions; do not treat that combination as separately validated without a fresh capture and physical confirmation.

The earlier `CL04 / CMD025-CMD033` 26.5 C startup/display candidate is intentionally not used. It was replayed on 2026-06-30 and did not change the real controller temperature. The exposed `temp_265` command now uses the later explicit 26.5 C action window `CMD100-CMD108` from `hci_att_timeline_20260630_211927.txt`.

All sending commands wait up to 2 seconds for a notify response:

```text
ACK
```

or:

```text
Timeout
```

If a notify arrives, MitsuBridge prints the notify content.

`sendfile <bin>` sends the exact bytes in the file to the configured write characteristic:

```text
mitsubridge> sendfile payload.bin
```

## HomeKit / Siri Control

MitsuBridge now includes a local HomeKit bridge for HomePod / Siri control:

```bash
npm run homekit
```

The installed LaunchAgent keeps it running in the background:

```bash
launchctl print gui/$(id -u)/com.mitsubridge.homekit
```

Current HomeKit accessory:

```text
Name: configured by homekit.name in config.json, default Mitsubishi AC
Pairing Code: 031-45-154
Setup URI: printed by npm run homekit
Port: 51827
```

Add it in the iPhone Home app:

```text
Home app -> Add Accessory -> More Options -> Mitsubishi AC -> enter 031-45-154
```

The bridge exposes one HomeKit air-conditioner accessory for power, native mode, target temperature, and fan speed. Power ON sends `on`; power OFF sends `off`. For a Siri temperature request such as 28 C, HomeKit sends `temp_280`. For AUTO mode, HomeKit sends `mode_cooling` followed by `fan_auto`; no unobserved AUTO-mode packet is generated.

Siri feedback is handled through one-shot HomeKit state feedback. For each voice command, the bridge computes the final target state, updates HomeKit once to match that requested state, then logs one feedback line such as `Mitsubishi AC温度已设为26度`. HomeKit / Siri controls the spoken wording, but the state it reads back is kept aligned with the voice command instead of the intermediate BLE replay steps.

Siri examples:

```text
Hey Siri, turn on Mitsubishi AC
Hey Siri, turn off Mitsubishi AC
Hey Siri, set Mitsubishi AC to cooling
Hey Siri, set Mitsubishi AC to heating
嘿 Siri，打开三菱空调
嘿 Siri，关闭三菱空调
嘿 Siri，把三菱空调设为制冷
嘿 Siri，把三菱空调温度设为26度
嘿 Siri，空调温度26度
嘿 Siri，空调温度28度
```

HomeKit services exposed:

```text
Mitsubishi AC   HeaterCooler, Active / COOL / HEAT / AUTO, threshold temperature 23.5-28.0 C, rotation speed
```

Optional command switches for debug and non-native HomeKit modes can be exposed with `MITSUBRIDGE_HOMEKIT_SWITCHES=1`. They are disabled by default so Home and Siri see the bridge as one air-conditioner device instead of many separate switch tiles.

Safety limits:

- Target temperature is limited to captured 23.5 C, 24.0 C, 24.5 C, 25.0 C, 25.5 C, 26.0 C, 26.5 C, 27.0 C, 27.5 C, and 28.0 C replay paths.
- If the accessory is off, a mode, temperature, or fan-speed request first sends `on`, then the requested captured command.
- AUTO mode is a captured-command composite: `mode_cooling` + `fan_auto`; it is not a guessed standalone AUTO-mode protocol packet.
- HomeKit's native air-conditioner service supports AUTO / COOL / HEAT. Captured dry and fan-only commands remain available through CLI and optional debug switches, not as guessed native HomeKit modes.
- Heat plus 26.0 C was not confirmed in summer conditions, so Siri heat mode does not promise a 26.0 C setpoint.
- The bridge does not parse protocol fields or generate new byte payloads.

Logs:

```text
logs/homekit_bridge.log
logs/homekit_launchd.out.log
logs/homekit_launchd.err.log
```

If Home app cannot find the accessory after an old failed pairing, stop the LaunchAgent, reset HomeKit storage, and start it again:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.mitsubridge.homekit.plist
npm run homekit:reset
```

## BLE Lifecycle

Use `disconnect` when you want to release the BLE session without exiting MitsuBridge:

```text
mitsubridge> disconnect
Connected=False
Notify=False
```

The disconnect sequence is:

1. Stop notify if it is enabled.
2. Wait for `stop_notify()` to finish.
3. Call `client.disconnect()`.
4. Wait for disconnect to finish.
5. Wait 2 seconds to let macOS/CoreBluetooth release the peripheral.
6. Print `Connected=False` and `Notify=False`.

Use `stop` to stop an active monitor session and release the BLE connection. `exit`, `quit`, EOF, or Ctrl+C also run the same cleanup path before the program ends.

The `status` command prints:

```text
Device Name: M/R_XXXX
Connected: False
Paired/Bonded: unknown
RSSI: -72
Notify Enabled: False
Current Service UUID: 0277df18-e796-11e6-bf01-fe55135034f3
Current Write UUID: e48c1528-e795-11e6-bf01-fe55135034f3
Current Notify UUID: ea1ea690-e795-11e6-bf01-fe55135034f3
```

On macOS, Bleak/CoreBluetooth may not expose real bonded status or current RSSI after connection. MitsuBridge reports those fields when available and otherwise prints `unknown`.

## Logging

Main BLE traffic is saved to:

```text
logs/mitsubridge.log
```

Notify binary payloads are appended to:

```text
logs/notify_YYYYMMDD_HHMMSS.bin
```

GATT dumps are saved to:

```text
logs/gatt_dump.txt
```

Session exports are saved to:

```text
logs/session_YYYYMMDD_HHMMSS.txt
```

The exported session includes scan, connect, read, write, notify, TX/RX association, payload hex, payload length, ASCII preview, and hexdump output.

Notify output format:

```text
------------------------------------------------
Time: 2026-06-29T10:00:00.000
Timestamp: 2026-06-29T10:00:00.000
Notify UUID: ea1ea690-e795-11e6-bf01-fe55135034f3
UUID: ea1ea690-e795-11e6-bf01-fe55135034f3
Length: 8
HEX:
0000  01 02 03 04 05 06 07 08
ASCII: ........
------------------------------------------------
```

If a notify arrives after a write, MitsuBridge records the association:

```text
TX -> id=1 time=... uuid=e48c1528-e795-11e6-bf01-fe55135034f3 hex=01 02 03 04
RX <- time=... uuid=ea1ea690-e795-11e6-bf01-fe55135034f3 hex=...
```

## Safety Boundary

MitsuBridge does not guess PAR-40MAAC / MELRemo control commands.

- `on` and `off` send only the user-confirmed fixed byte sequences listed in `logs/confirmed_mr_actions_20260629.txt`.
- `write <hex>` sends only the exact hex payload typed by the user.
- No command decodes fields, infers protocol meaning, or generates new control bytes.
