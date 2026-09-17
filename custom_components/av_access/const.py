"""Constants for the AV Access integration."""

from __future__ import annotations

DOMAIN = "av_access"

# Option keys holding the user defined names of the ports.
CONF_INPUT_LABELS = "input_labels"
CONF_OUTPUT_LABELS = "output_labels"

# Shown by the name sensors while a port has no user defined name.
DEFAULT_INPUT_NAME = "HDMI {number}"
DEFAULT_OUTPUT_NAME = "Output {number}"

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
TRANSLATION_KEY_INPUT_NAME = "input_name"
TRANSLATION_KEY_OUTPUT_NAME = "output_name"
TRANSLATION_KEY_OUTPUT_INPUT_NUMBER = "output_input_number"

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