"""Constants for the AV Access integration."""

from __future__ import annotations

DOMAIN = "av_access"

DEFAULT_PORT = 62225
DEFAULT_NAME = "AV Access"

UPDATE_INTERVAL = 5

# Used when the controller does not report the number of ports.
DEFAULT_INPUT_COUNT = 4
DEFAULT_OUTPUT_COUNT = 4

# Translation keys of the entities. The displayed names and options are
# defined in the files in the translations directory.
TRANSLATION_KEY_OUTPUT_INPUT = "output_input"
TRANSLATION_KEY_INPUT_EDID = "input_edid"

# The API expects and reports the input as a number.
INPUT_OPTION_BY_VALUE: dict[int, str] = {
    1: "hdmi_1",
    2: "hdmi_2",
    3: "hdmi_3",
    4: "hdmi_4",
}

INPUT_VALUE_BY_OPTION: dict[str, int] = {
    option: value for value, option in INPUT_OPTION_BY_VALUE.items()
}

# The API expects and reports the EDID as a number.
EDID_OPTION_BY_VALUE: dict[int, str] = {
    1: "copy_from_output_1",
    2: "copy_from_output_2",
    3: "copy_from_output_3",
    4: "copy_from_output_4",
    5: "4k60_5_1ch_hdr",
    6: "4k60_2_0ch_hdr",
    7: "4k30_7_1ch_hdr",
    8: "4k30_5_1ch_hdr",
    9: "4k30_2_0ch_hdr",
    10: "4k30_8bit_2_0ch",
    11: "1080p60_2_0ch",
    12: "5k_ultra_widescreen_2ch",
    13: "5k_super_widescreen_2ch",
    14: "smart_edid",
    15: "write_edid",
}

EDID_VALUE_BY_OPTION: dict[str, int] = {
    option: value for value, option in EDID_OPTION_BY_VALUE.items()
}
