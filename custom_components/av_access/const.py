"""Constants for the AV Access integration."""

from __future__ import annotations

DOMAIN = "av_access"

# Fired when a poll finds a state the matrix changed without a command from
# Home Assistant. The logbook names the matrix as the origin of the state
# change, which needs an event sharing the context of that change.
EVENT_EXTERNAL_CHANGE = "av_access_external_change"

# Carries the name of the matrix to the logbook, which shows it as the origin.
ATTR_DEVICE_NAME = "device_name"

# Attributes of the selects mapping the number of an input or an EDID to its
# option, so an automation can select by a number that no name changes.
ATTR_INPUT_OPTIONS = "input_options"
ATTR_EDID_OPTIONS = "edid_options"

# Option keys holding the user defined names of the ports and of the EDIDs.
CONF_INPUT_LABELS = "input_labels"
CONF_OUTPUT_LABELS = "output_labels"
CONF_EDID_LABELS = "edid_labels"

# Shown by the name sensors while a port has no user defined name.
DEFAULT_INPUT_NAME = "HDMI {number}"
DEFAULT_OUTPUT_NAME = "Output {number}"

# Telnet port of the matrix, and the range a TCP port can have.
DEFAULT_PORT = 23
MIN_PORT = 1
MAX_PORT = 65535
DEFAULT_NAME = "AV Access"

MANUFACTURER = "AV Access"

# Seconds between two polls of the routing. Somebody switches it at the front
# panel or with the remote control, which only a poll notices, so a short
# interval keeps Home Assistant in sync. A poll of the routing is one command.
DEFAULT_SCAN_INTERVAL = 3
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 300

# Seconds between two reads of the settings of all ports, that is EDID, HDCP,
# audio mute and the CEC settings. They are hardly ever changed at the matrix
# itself and cost twenty commands, while every poll is a connection of its own,
# so reading them once a minute spares the matrix most of the load.
SETTINGS_POLL_INTERVAL = 60

# Seconds a value a command confirmed wins over a value read from the matrix.
# A poll that started before the command still reports the previous value and
# would otherwise look like a change made at the front panel. The window
# therefore has to outlast a whole poll of about two seconds, with room for a
# matrix that answers more slowly. After it the matrix is believed again, so a
# change made at the front panel right after a command is not hidden for long.
COMMAND_CONFIRM_TIMEOUT = 5.0
CONNECT_TIMEOUT = 3.0
READ_TIMEOUT = 3.0
CLOSE_TIMEOUT = 1.0

# The matrix normally closes the connection once it has answered, which ends the
# read. A firmware that keeps the connection open instead is detected by a short
# pause after the response, so a command does not run into READ_TIMEOUT.
IDLE_TIMEOUT = 0.3

# The matrix greets every connection with its welcome line and occasionally
# discards a command that arrives before it, answering with nothing but the
# greeting. A command is therefore only sent once the greeting is in. A firmware
# without a greeting is recognized when none arrives within this time.
GREETING_TIMEOUT = 0.5

# A command the matrix discarded is sent this many times more.
DISCARDED_COMMAND_RETRIES = 1

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

# Entry data holding the EDIDs the matrix offers, read from its web interface
# while the entry is set up, and whether the matrix really provided them.
CONF_EDID_OPTIONS = "edid_options"
CONF_EDID_OPTIONS_SOURCE = "edid_options_source"
EDID_SOURCE_DEVICE = "device"
EDID_SOURCE_FALLBACK = "fallback"

# Seconds the web interface may take to hand out its page with the EDID list.
EDID_LIST_TIMEOUT = 10.0

# Seconds between two attempts to read the EDID list while the built-in list
# stands in for it, for example because the matrix was switched off while Home
# Assistant started.
EDID_LIST_RETRY_INTERVAL = 900

# Repair issues, raised once per entry. The ID of an issue ends with the ID of
# its entry.
ISSUE_EDID_LIST_FALLBACK = "edid_list_fallback"
ISSUE_EDID_LABELS_CHANGED = "edid_labels_changed"

# Stands in for the list of a matrix whose web interface cannot be read. It is
# the list of the 4KMX44-H2 with firmware ARM 2.8, MCU 3.3 and WEB 1.08, keyed
# by the number the matrix expects and reports.
DEFAULT_EDID_OPTIONS: dict[str, str] = {
    "1": "Copy from output 1",
    "2": "Copy from output 2",
    "3": "Copy from output 3",
    "4": "Copy from output 4",
    "5": "4K@60Hz 5.1ch audio With HDR",
    "6": "4K@60Hz 2.0ch audio With HDR",
    "7": "4K@30Hz 7.1ch audio With HDR",
    "8": "4K@30Hz 5.1ch audio With HDR",
    "9": "4K@30Hz 2.0ch audio With HDR",
    "10": "4K@30Hz/8bit only 2.0ch audio Without HDR",
    "11": "1080P@60Hz 2.0ch audio",
    "12": "5K Ultra Wide_2CH",
    "13": "5K Super Wide_2CH",
    "14": "Smart EDID",
}
