from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfirmedStep:
    label: str
    payload: bytes
    delay_after_seconds: float


@dataclass(frozen=True)
class ConfirmedAction:
    name: str
    description: str
    source_cluster: str
    steps: tuple[ConfirmedStep, ...]


def step(label: str, hex_payload: str, delay_after_seconds: float) -> ConfirmedStep:
    return ConfirmedStep(
        label=label,
        payload=bytes.fromhex(hex_payload),
        delay_after_seconds=delay_after_seconds,
    )


# These are replay-only, user-confirmed PAR-40MAAC action sequences.
# Do not infer field meanings from the byte positions here.
CONFIRMED_ACTIONS: dict[str, ConfirmedAction] = {
    "on": ConfirmedAction(
        name="on",
        description="Confirmed ON sequence",
        source_cluster="CL37 / CMD292-CMD300 / hci_att_timeline_20260629_222354.txt",
        steps=(
            step("CMD292", "0B 00 02 01 00 01 00 00 00 00 00 0F 00", 0.07),
            step("CMD293", "0B 00 03 03 00 01 00 00 00 00 00 12 00", 0.06),
            step("CMD294", "0B 00 04 01 04 01 00 00 00 00 00 15 00", 0.06),
            step("CMD295", "17 00 05 05 01 01 01 00 00 09 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD296", "34 00 00 96 01", 0.06),
            step("CMD297", "06 00 06 05 02 00 13 00", 0.24),
            step("CMD298", "0B 00 07 03 04 01 00 00 00 00 00 1A 00", 0.06),
            step("CMD299", "0B 00 00 01 01 01 00 00 00 00 00 0E 00", 0.06),
            step("CMD300", "0B 00 01 03 01 01 00 00 00 00 00 11 00", 0.0),
        ),
    ),
    "off": ConfirmedAction(
        name="off",
        description="Confirmed OFF sequence",
        source_cluster="CL39 / CMD308-CMD316 / hci_att_timeline_20260629_222354.txt",
        steps=(
            step("CMD308", "0B 00 01 01 00 01 00 00 00 00 00 0E 00", 0.13),
            step("CMD309", "0B 00 02 03 00 01 00 00 00 00 00 11 00", 0.12),
            step("CMD310", "0B 00 03 01 04 01 00 00 00 00 00 14 00", 0.09),
            step("CMD311", "17 00 04 05 01 01 01 00 00 08 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD312", "34 00 00 94 01", 0.06),
            step("CMD313", "06 00 05 05 02 00 12 00", 0.12),
            step("CMD314", "0B 00 06 03 04 01 00 00 00 00 00 19 00", 0.06),
            step("CMD315", "0B 00 07 01 01 01 00 00 00 00 00 15 00", 0.06),
            step("CMD316", "0B 00 00 03 01 01 00 00 00 00 00 10 00", 0.0),
        ),
    ),
    "dry": ConfirmedAction(
        name="dry",
        description="Confirmed DRY mode sequence",
        source_cluster="CL29 / CMD226-CMD234 / hci_att_timeline_20260630_191923.txt / validated in session_20260630_192440.txt",
        steps=(
            step("CMD226", "0B 00 04 01 00 01 00 00 00 00 00 11 00", 0.06),
            step("CMD227", "0B 00 05 03 00 01 00 00 00 00 00 14 00", 0.06),
            step("CMD228", "0B 00 06 01 04 01 00 00 00 00 00 17 00", 0.06),
            step("CMD229", "17 00 07 05 01 01 02 00 00 31 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD230", "34 00 00 C1 01", 0.06),
            step("CMD231", "06 00 00 05 02 00 0D 00", 0.24),
            step("CMD232", "0B 00 01 03 04 01 00 00 00 00 00 14 00", 0.06),
            step("CMD233", "0B 00 02 01 01 01 00 00 00 00 00 10 00", 0.06),
            step("CMD234", "0B 00 03 03 01 01 00 00 00 00 00 13 00", 0.0),
        ),
    ),
    "fan": ConfirmedAction(
        name="fan",
        description="Confirmed FAN mode sequence; notify response may lag or repeat previous mode",
        source_cluster="CL30 / CMD235-CMD243 / hci_att_timeline_20260630_191923.txt / validated in session_20260630_192440.txt",
        steps=(
            step("CMD235", "0B 00 04 01 00 01 00 00 00 00 00 11 00", 0.06),
            step("CMD236", "0B 00 05 03 00 01 00 00 00 00 00 14 00", 0.06),
            step("CMD237", "0B 00 06 01 04 01 00 00 00 00 00 17 00", 0.06),
            step("CMD238", "17 00 07 05 01 01 02 00 00 01 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD239", "64 00 00 C1 01", 0.06),
            step("CMD240", "06 00 00 05 02 00 0D 00", 0.24),
            step("CMD241", "0B 00 01 03 04 01 00 00 00 00 00 14 00", 0.06),
            step("CMD242", "0B 00 02 01 01 01 00 00 00 00 00 10 00", 0.06),
            step("CMD243", "0B 00 03 03 01 01 00 00 00 00 00 13 00", 0.0),
        ),
    ),
    "heat": ConfirmedAction(
        name="heat",
        description="Confirmed HEAT mode sequence",
        source_cluster="CL32 / CMD251-CMD259 / hci_att_timeline_20260630_191923.txt / validated in session_20260630_192440.txt",
        steps=(
            step("CMD251", "0B 00 03 01 00 01 00 00 00 00 00 10 00", 0.06),
            step("CMD252", "0B 00 04 03 00 01 00 00 00 00 00 13 00", 0.06),
            step("CMD253", "0B 00 05 01 04 01 00 00 00 00 00 16 00", 0.06),
            step("CMD254", "17 00 06 05 01 01 02 00 00 11 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD255", "64 00 00 D0 01", 0.06),
            step("CMD256", "06 00 07 05 02 00 14 00", 0.24),
            step("CMD257", "0B 00 00 03 04 01 00 00 00 00 00 13 00", 0.06),
            step("CMD258", "0B 00 01 01 01 01 00 00 00 00 00 0F 00", 0.06),
            step("CMD259", "0B 00 02 03 01 01 00 00 00 00 00 12 00", 0.0),
        ),
    ),
    "cooling": ConfirmedAction(
        name="cooling",
        description="Confirmed COOLING mode sequence",
        source_cluster="CL35 / CMD274-CMD282 / hci_att_timeline_20260630_191923.txt / validated in session_20260630_192440.txt",
        steps=(
            step("CMD274", "0B 00 01 01 00 01 00 00 00 00 00 0E 00", 0.06),
            step("CMD275", "0B 00 02 03 00 01 00 00 00 00 00 11 00", 0.06),
            step("CMD276", "0B 00 03 01 04 01 00 00 00 00 00 14 00", 0.06),
            step("CMD277", "17 00 04 05 01 01 02 00 00 09 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD278", "64 00 00 C6 01", 0.06),
            step("CMD279", "06 00 05 05 02 00 12 00", 0.24),
            step("CMD280", "0B 00 06 03 04 01 00 00 00 00 00 19 00", 0.06),
            step("CMD281", "0B 00 07 01 01 01 00 00 00 00 00 15 00", 0.06),
            step("CMD282", "0B 00 00 03 01 01 00 00 00 00 00 10 00", 0.0),
        ),
    ),
    "fan_low": ConfirmedAction(
        name="fan_low",
        description="Confirmed LOW fan-speed sequence",
        source_cluster="CL06 / CMD346-CMD354 / hci_att_timeline_20260630_193305.txt / validated in session_20260630_193823.txt and session_20260630_194032.txt",
        steps=(
            step("CMD346", "0B 00 06 01 00 01 00 00 00 00 00 13 00", 0.06),
            step("CMD347", "0B 00 07 03 00 01 00 00 00 00 00 16 00", 0.06),
            step("CMD348", "0B 00 00 01 04 01 00 00 00 00 00 11 00", 0.06),
            step("CMD349", "17 00 01 05 01 01 00 00 01 09 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD350", "61 00 00 BF 01", 0.06),
            step("CMD351", "06 00 02 05 02 00 0F 00", 0.24),
            step("CMD352", "0B 00 03 03 04 01 00 00 00 00 00 16 00", 0.06),
            step("CMD353", "0B 00 04 01 01 01 00 00 00 00 00 12 00", 0.06),
            step("CMD354", "0B 00 05 03 01 01 00 00 00 00 00 15 00", 0.0),
        ),
    ),
    "fan_medium": ConfirmedAction(
        name="fan_medium",
        description="Captured MEDIUM fan-speed sequence",
        source_cluster="CL07 / CMD355-CMD363 / hci_att_timeline_20260630_193305.txt / user action order fan low -> medium",
        steps=(
            step("CMD355", "0B 00 06 01 00 01 00 00 00 00 00 13 00", 0.06),
            step("CMD356", "0B 00 07 03 00 01 00 00 00 00 00 16 00", 0.06),
            step("CMD357", "0B 00 00 01 04 01 00 00 00 00 00 11 00", 0.06),
            step("CMD358", "17 00 01 05 01 01 00 00 01 09 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD359", "62 00 00 C0 01", 0.06),
            step("CMD360", "06 00 02 05 02 00 0F 00", 0.24),
            step("CMD361", "0B 00 03 03 04 01 00 00 00 00 00 16 00", 0.06),
            step("CMD362", "0B 00 04 01 01 01 00 00 00 00 00 12 00", 0.06),
            step("CMD363", "0B 00 05 03 01 01 00 00 00 00 00 15 00", 0.0),
        ),
    ),
    "fan_high": ConfirmedAction(
        name="fan_high",
        description="Captured HIGH fan-speed sequence",
        source_cluster="CL09 / CMD371-CMD379 / hci_att_timeline_20260630_193305.txt / user action order fan medium -> high",
        steps=(
            step("CMD371", "0B 00 05 01 00 01 00 00 00 00 00 12 00", 0.06),
            step("CMD372", "0B 00 06 03 00 01 00 00 00 00 00 15 00", 0.06),
            step("CMD373", "0B 00 07 01 04 01 00 00 00 00 00 18 00", 0.06),
            step("CMD374", "17 00 00 05 01 01 00 00 01 09 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD375", "63 00 00 C0 01", 0.06),
            step("CMD376", "06 00 01 05 02 00 0E 00", 0.24),
            step("CMD377", "0B 00 02 03 04 01 00 00 00 00 00 15 00", 0.06),
            step("CMD378", "0B 00 03 01 01 01 00 00 00 00 00 11 00", 0.06),
            step("CMD379", "0B 00 04 03 01 01 00 00 00 00 00 14 00", 0.0),
        ),
    ),
    "fan_auto": ConfirmedAction(
        name="fan_auto",
        description="Captured AUTO fan-speed sequence",
        source_cluster="CL10 / CMD380-CMD388 / hci_att_timeline_20260630_193305.txt / user action order fan high -> auto",
        steps=(
            step("CMD380", "0B 00 05 01 00 01 00 00 00 00 00 12 00", 0.06),
            step("CMD381", "0B 00 06 03 00 01 00 00 00 00 00 15 00", 0.06),
            step("CMD382", "0B 00 07 01 04 01 00 00 00 00 00 18 00", 0.06),
            step("CMD383", "17 00 00 05 01 01 00 00 01 09 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD384", "64 00 00 C1 01", 0.06),
            step("CMD385", "06 00 01 05 02 00 0E 00", 0.24),
            step("CMD386", "0B 00 02 03 04 01 00 00 00 00 00 15 00", 0.06),
            step("CMD387", "0B 00 03 01 01 01 00 00 00 00 00 11 00", 0.06),
            step("CMD388", "0B 00 04 03 01 01 00 00 00 00 00 14 00", 0.0),
        ),
    ),
    "temp_235": ConfirmedAction(
        name="temp_235",
        description="Captured 23.5 C target-temperature sequence",
        source_cluster="CL14 / CMD107-CMD115 / hci_att_timeline_20260630_185628.txt / user action order target 23.5 C",
        steps=(
            step("CMD107", "0B 00 04 01 00 01 00 00 00 00 00 11 00", 0.06),
            step("CMD108", "0B 00 05 03 00 01 00 00 00 00 00 14 00", 0.06),
            step("CMD109", "0B 00 06 01 04 01 00 00 00 00 00 17 00", 0.06),
            step("CMD110", "17 00 07 05 01 01 00 01 00 09 35 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD111", "34 00 00 7D 01", 0.06),
            step("CMD112", "06 00 00 05 02 00 0D 00", 0.24),
            step("CMD113", "0B 00 01 03 04 01 00 00 00 00 00 14 00", 0.06),
            step("CMD114", "0B 00 02 01 01 01 00 00 00 00 00 10 00", 0.06),
            step("CMD115", "0B 00 03 03 01 01 00 00 00 00 00 13 00", 0.0),
        ),
    ),
    "temp_240": ConfirmedAction(
        name="temp_240",
        description="Captured 24.0 C target-temperature sequence",
        source_cluster="CL15 / CMD116-CMD124 / hci_att_timeline_20260630_185628.txt / user action order target 24.0 C",
        steps=(
            step("CMD116", "0B 00 04 01 00 01 00 00 00 00 00 11 00", 0.06),
            step("CMD117", "0B 00 05 03 00 01 00 00 00 00 00 14 00", 0.06),
            step("CMD118", "0B 00 06 01 04 01 00 00 00 00 00 17 00", 0.06),
            step("CMD119", "17 00 07 05 01 01 00 01 00 09 40 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD120", "34 00 00 88 01", 0.06),
            step("CMD121", "06 00 00 05 02 00 0D 00", 0.24),
            step("CMD122", "0B 00 01 03 04 01 00 00 00 00 00 14 00", 0.06),
            step("CMD123", "0B 00 02 01 01 01 00 00 00 00 00 10 00", 0.06),
            step("CMD124", "0B 00 03 03 01 01 00 00 00 00 00 13 00", 0.0),
        ),
    ),
    "temp_245": ConfirmedAction(
        name="temp_245",
        description="Captured 24.5 C target-temperature sequence",
        source_cluster="CL17 / CMD132-CMD140 / hci_att_timeline_20260630_185628.txt / user action order target 24.5 C",
        steps=(
            step("CMD132", "0B 00 03 01 00 01 00 00 00 00 00 10 00", 0.06),
            step("CMD133", "0B 00 04 03 00 01 00 00 00 00 00 13 00", 0.06),
            step("CMD134", "0B 00 05 01 04 01 00 00 00 00 00 16 00", 0.06),
            step("CMD135", "17 00 06 05 01 01 00 01 00 09 45 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD136", "34 00 00 8C 01", 0.06),
            step("CMD137", "06 00 07 05 02 00 14 00", 0.24),
            step("CMD138", "0B 00 00 03 04 01 00 00 00 00 00 13 00", 0.06),
            step("CMD139", "0B 00 01 01 01 01 00 00 00 00 00 0F 00", 0.06),
            step("CMD140", "0B 00 02 03 01 01 00 00 00 00 00 12 00", 0.0),
        ),
    ),
    "temp_250": ConfirmedAction(
        name="temp_250",
        description="Captured 25.0 C target-temperature sequence",
        source_cluster="CL18 / CMD141-CMD149 / hci_att_timeline_20260630_185628.txt / user action order target 25.0 C",
        steps=(
            step("CMD141", "0B 00 03 01 00 01 00 00 00 00 00 10 00", 0.06),
            step("CMD142", "0B 00 04 03 00 01 00 00 00 00 00 13 00", 0.06),
            step("CMD143", "0B 00 05 01 04 01 00 00 00 00 00 16 00", 0.06),
            step("CMD144", "17 00 06 05 01 01 00 01 00 09 50 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD145", "34 00 00 97 01", 0.06),
            step("CMD146", "06 00 07 05 02 00 14 00", 0.24),
            step("CMD147", "0B 00 00 03 04 01 00 00 00 00 00 13 00", 0.06),
            step("CMD148", "0B 00 01 01 01 01 00 00 00 00 00 0F 00", 0.06),
            step("CMD149", "0B 00 02 03 01 01 00 00 00 00 00 12 00", 0.0),
        ),
    ),
    "temp_255": ConfirmedAction(
        name="temp_255",
        description="Captured 25.5 C target-temperature sequence",
        source_cluster="CL20 / CMD157-CMD165 / hci_att_timeline_20260630_185628.txt / user action order target 25.5 C",
        steps=(
            step("CMD157", "0B 00 02 01 00 01 00 00 00 00 00 0F 00", 0.06),
            step("CMD158", "0B 00 03 03 00 01 00 00 00 00 00 12 00", 0.06),
            step("CMD159", "0B 00 04 01 04 01 00 00 00 00 00 15 00", 0.06),
            step("CMD160", "17 00 05 05 01 01 00 01 00 09 55 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD161", "34 00 00 9B 01", 0.06),
            step("CMD162", "06 00 06 05 02 00 13 00", 0.24),
            step("CMD163", "0B 00 07 03 04 01 00 00 00 00 00 1A 00", 0.06),
            step("CMD164", "0B 00 00 01 01 01 00 00 00 00 00 0E 00", 0.06),
            step("CMD165", "0B 00 01 03 01 01 00 00 00 00 00 11 00", 0.0),
        ),
    ),
    "temp_260": ConfirmedAction(
        name="temp_260",
        description="Captured 26.0 C target-temperature sequence",
        source_cluster="CL22 / CMD173-CMD181 / hci_att_timeline_20260630_185628.txt / user action order target 26.0 C",
        steps=(
            step("CMD173", "0B 00 01 01 00 01 00 00 00 00 00 0E 00", 0.06),
            step("CMD174", "0B 00 02 03 00 01 00 00 00 00 00 11 00", 0.06),
            step("CMD175", "0B 00 03 01 04 01 00 00 00 00 00 14 00", 0.06),
            step("CMD176", "17 00 04 05 01 01 00 01 00 09 60 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD177", "34 00 00 A5 01", 0.06),
            step("CMD178", "06 00 05 05 02 00 12 00", 0.24),
            step("CMD179", "0B 00 06 03 04 01 00 00 00 00 00 19 00", 0.06),
            step("CMD180", "0B 00 07 01 01 01 00 00 00 00 00 15 00", 0.06),
            step("CMD181", "0B 00 00 03 01 01 00 00 00 00 00 10 00", 0.0),
        ),
    ),
    "temp_265": ConfirmedAction(
        name="temp_265",
        description="Captured 26.5 C target-temperature sequence",
        source_cluster="CMD100-CMD108 / hci_att_timeline_20260630_211927.txt / user action order target 26.5 C",
        steps=(
            step("CMD100", "0B 00 05 01 00 01 00 00 00 00 00 12 00", 0.06),
            step("CMD101", "0B 00 06 03 00 01 00 00 00 00 00 15 00", 0.06),
            step("CMD102", "0B 00 07 01 04 01 00 00 00 00 00 18 00", 0.06),
            step("CMD103", "17 00 00 05 01 01 00 01 00 09 65 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD104", "33 00 00 A5 01", 0.06),
            step("CMD105", "06 00 01 05 02 00 0E 00", 0.24),
            step("CMD106", "0B 00 02 03 04 01 00 00 00 00 00 15 00", 0.06),
            step("CMD107", "0B 00 03 01 01 01 00 00 00 00 00 11 00", 0.06),
            step("CMD108", "0B 00 04 03 01 01 00 00 00 00 00 14 00", 0.0),
        ),
    ),
    "temp_270": ConfirmedAction(
        name="temp_270",
        description="Captured 27.0 C target-temperature sequence",
        source_cluster="CMD034-CMD042 / hci_att_timeline_20260630_211927.txt / user action order target 27.0 C",
        steps=(
            step("CMD034", "0B 00 00 01 00 01 00 00 00 00 00 0D 00", 0.06),
            step("CMD035", "0B 00 01 03 00 01 00 00 00 00 00 10 00", 0.06),
            step("CMD036", "0B 00 02 01 04 01 00 00 00 00 00 13 00", 0.06),
            step("CMD037", "17 00 03 05 01 01 00 01 00 09 70 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD038", "33 00 00 B3 01", 0.06),
            step("CMD039", "06 00 04 05 02 00 11 00", 0.24),
            step("CMD040", "0B 00 05 03 04 01 00 00 00 00 00 18 00", 0.06),
            step("CMD041", "0B 00 06 01 01 01 00 00 00 00 00 14 00", 0.06),
            step("CMD042", "0B 00 07 03 01 01 00 00 00 00 00 17 00", 0.0),
        ),
    ),
    "temp_275": ConfirmedAction(
        name="temp_275",
        description="Captured 27.5 C target-temperature sequence",
        source_cluster="CMD050-CMD058 / hci_att_timeline_20260630_211927.txt / user action order target 27.5 C",
        steps=(
            step("CMD050", "0B 00 07 01 00 01 00 00 00 00 00 14 00", 0.06),
            step("CMD051", "0B 00 00 03 00 01 00 00 00 00 00 0F 00", 0.06),
            step("CMD052", "0B 00 01 01 04 01 00 00 00 00 00 12 00", 0.06),
            step("CMD053", "17 00 02 05 01 01 00 01 00 09 75 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD054", "33 00 00 B7 01", 0.06),
            step("CMD055", "06 00 03 05 02 00 10 00", 0.24),
            step("CMD056", "0B 00 04 03 04 01 00 00 00 00 00 17 00", 0.06),
            step("CMD057", "0B 00 05 01 01 01 00 00 00 00 00 13 00", 0.06),
            step("CMD058", "0B 00 06 03 01 01 00 00 00 00 00 16 00", 0.0),
        ),
    ),
    "temp_280": ConfirmedAction(
        name="temp_280",
        description="Captured 28.0 C target-temperature sequence",
        source_cluster="CMD059-CMD067 / hci_att_timeline_20260630_211927.txt / user action order target 28.0 C",
        steps=(
            step("CMD059", "0B 00 07 01 00 01 00 00 00 00 00 14 00", 0.06),
            step("CMD060", "0B 00 00 03 00 01 00 00 00 00 00 0F 00", 0.06),
            step("CMD061", "0B 00 01 01 04 01 00 00 00 00 00 12 00", 0.06),
            step("CMD062", "17 00 02 05 01 01 00 01 00 09 80 02 50 02 90 01 00 00 00 00", 0.003),
            step("CMD063", "33 00 00 C2 01", 0.06),
            step("CMD064", "06 00 03 05 02 00 10 00", 0.24),
            step("CMD065", "0B 00 04 03 04 01 00 00 00 00 00 17 00", 0.06),
            step("CMD066", "0B 00 05 01 01 01 00 00 00 00 00 13 00", 0.06),
            step("CMD067", "0B 00 06 03 01 01 00 00 00 00 00 16 00", 0.0),
        ),
    ),
}


def _alias_action(alias: str, source: str, description: str) -> None:
    base = CONFIRMED_ACTIONS[source]
    CONFIRMED_ACTIONS[alias] = ConfirmedAction(
        name=alias,
        description=description,
        source_cluster=f"alias of {source}: {base.source_cluster}",
        steps=base.steps,
    )


_alias_action("mode_dry", "dry", "DRY mode sequence alias")
_alias_action("mode_fan", "fan", "FAN-only mode sequence alias")
_alias_action("mode_heat", "heat", "HEAT mode sequence alias")
_alias_action("mode_cooling", "cooling", "COOLING mode sequence alias")
