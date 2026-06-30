# v0.1.0

Initial public MitsuBridge package for Mitsubishi Electric PAR-40MAAC / MELRemo BLE controllers.

## Included

- Confirmed replay commands for power, mode, fan speed, and target temperature 23.5-28.0 C.
- HomeKit / Siri bridge exposing one Air Conditioner accessory by default.
- Public `config.example.json` and local `config.json` workflow.
- Public profile bundle at `profiles/mitsubishi_par40maac_melremo.json`.
- HCI parsing and byte-diff helper tools.

## Safety Notes

- Confirmed actions use ATT Write Command / no-response writes.
- No protocol fields are guessed.
- Runtime logs, HCI captures, local device identity, and HomeKit pairing files are excluded from the public package.
