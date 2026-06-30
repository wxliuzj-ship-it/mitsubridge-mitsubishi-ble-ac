# Public Package Notes

MitsuBridge is packaged for community use with Mitsubishi Electric PAR-40MAAC / MELRemo BLE controllers.

## What Is Included

- Python BLE CLI for scan, read, notify, write, replay, and confirmed actions.
- HomeKit / Siri bridge using `hap-nodejs`.
- `config.example.json` for local device and HomeKit setup.
- `profiles/mitsubishi_par40maac_melremo.json` with the public GATT profile and confirmed fixed replay sequences.
- HCI parsing tools under `tools/` for users who want to label new captures.

## What Is Not Included

- Local `config.json`.
- HomeKit pairing state under `.homekit/`.
- HCI btsnoop captures, notify binary streams, session logs, and runtime logs under `logs/`.
- Python virtual environments and Node dependencies.

## Safety Boundary

This project replays confirmed fixed byte sequences only. It does not infer protocol fields, generate new payloads, or promise compatibility beyond the tested PAR-40MAAC / MELRemo family. Users should validate every new action against the physical controller before publishing a new sequence.

## Local Setup Summary

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
cp config.example.json config.json
python main.py scan
```

Edit `config.json` before sending commands. The BLE address can be left empty on macOS if the configured device name is enough to identify the controller.
