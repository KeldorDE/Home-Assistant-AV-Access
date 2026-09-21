"""Constants for the AV Access integration."""

from __future__ import annotations

DOMAIN = "av_access"

# Fired when a poll finds a state the matrix changed without a command from
# Home Assistant. The logbook names the matrix as the origin of the state
# change, which needs an event sharing the context of that change.
EVENT_EXTERNAL_CHANGE = "av_access_external_change"

# Carries the name of the matrix to the logbook, which shows it as the origin.
ATTR_DEVICE_NAME = "device_name"

# Option keys holding the user defined names of the ports.
CONF_INPUT_LABELS = "input_labels"
CONF_OUTPUT_LABELS = "output_labels"

# Shown by the name sensors while a port has no user defined name.
DEFAULT_INPUT_NAME = "HDMI {number}"
DEFAULT_OUTPUT_NAME = "Output {number}"

# Telnet port of the matrix.
DEFAULT_PORT = 23
DEFAULT_NAME = "AV Access"

MANUFACTURER = "AV Access"

# Seconds between two polls. The routing is read on every poll, EDID and HDCP
# for one input per poll. Changes made at the front panel or with the remote
# control are only noticed by a poll, so a short interval keeps Home Assistant
# in sync. Every command occupies the matrix for at least COMMAND_DELAY
# seconds, which is the lower bound of a useful interval.
DEFAULT_SCAN_INTERVAL = 3
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 300

# The matrix accepts one command at a time and needs a pause afterwards.
# Sending commands back to back has been observed to freeze the device.
COMMAND_DELAY = 1.0

# Seconds a value a command confirmed wins over a value read from the matrix.
# A poll that started before the command still reports the previous value and
# would otherwise look like a change made at the front panel. The window
# therefore has to outlast a whole poll, which takes about six seconds with all
# the commands of a rotation. After it the matrix is believed again, so a state
# it really keeps is not hidden.
COMMAND_CONFIRM_TIMEOUT = 15.0
CONNECT_TIMEOUT = 3.0
READ_TIMEOUT = 3.0
CLOSE_TIMEOUT = 1.0

# The matrix normally closes the connection once it has answered, which ends the
# read. A firmware that keeps the connection open instead is detected by a short
# pause after the response, so a command does not run into READ_TIMEOUT.
IDLE_TIMEOUT = 0.3

# Used until the matrix reports a model the port count can be derived from.
DEFAULT_INPUT_COUNT = 4
DEFAULT_OUTPUT_COUNT = 4

# Translation keys of the entities. The displayed names and options are
# defined in the files in the translations directory.
TRANSLATION_KEY_OUTPUT_INPUT = "output_input"
TRANSLATION_KEY_INPUT_EDID = "input_edid"
TRANSLATION_KEY_INPUT_HDCP = "input_hdcp"
TRANSLATION_KEY_OUTPUT_AUDIO_MUTE = "output_audio_mute"
TRANSLATION_KEY_OUTPUT_CEC_AUTO = "output_cec_auto"
TRANSLATION_KEY_OUTPUT_CEC_DELAY = "output_cec_delay"
TRANSLATION_KEY_OUTPUT_CEC_POWER_ON = "output_cec_power_on"
TRANSLATION_KEY_OUTPUT_CEC_POWER_OFF = "output_cec_power_off"
TRANSLATION_KEY_INPUT_NAME = "input_name"
TRANSLATION_KEY_OUTPUT_NAME = "output_name"
TRANSLATION_KEY_OUTPUT_INPUT_NUMBER = "output_input_number"

# A port with a user defined name is named after it, which needs a second
# translation of every entity name. The keys of those only differ by a suffix.
TRANSLATION_KEY_NAMED_SUFFIX = "_named"

# Placeholders of the entity names.
PLACEHOLDER_INPUT = "input"
PLACEHOLDER_OUTPUT = "output"
PLACEHOLDER_NAME = "name"

# Minutes without an active signal after which the automatic CEC power off of
# an output is triggered. The matrix accepts whole minutes in this range only.
CEC_DELAY_MIN = 1
CEC_DELAY_MAX = 30

# The matrix expects and reports the EDID as a number.
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
