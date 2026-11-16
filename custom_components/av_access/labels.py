"""Resolve the user defined names of the matrix ports and EDIDs.

An input without a name is offered as "HDMI 1" and so on, the same text its
name sensor reports, so an automation can pass the state of the sensor to the
select. As soon as a name is configured it is shown as entered. An EDID without
a name is shown the way the matrix itself names it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import (
    CONF_EDID_LABELS,
    CONF_EDID_OPTIONS,
    CONF_INPUT_LABELS,
    CONF_OUTPUT_LABELS,
    DEFAULT_EDID_OPTIONS,
    DEFAULT_INPUT_NAME,
    DEFAULT_OUTPUT_NAME,
)


def input_label_key(number: int) -> str:
    """Return the key holding the name of an input."""
    return f"input_{number}"


def output_label_key(number: int) -> str:
    """Return the key holding the name of an output."""
    return f"output_{number}"


_EDID_LABEL_PREFIX = "edid_"


def edid_label_key(value: int) -> str:
    """Return the key holding the name of an EDID."""
    return f"{_EDID_LABEL_PREFIX}{value}"


def stored_labels(options: Mapping[str, Any], key: str) -> dict[str, str]:
    """Return the non-empty names stored under the given option key."""
    stored = options.get(key)

    if not isinstance(stored, Mapping):
        return {}

    return {
        name: value.strip()
        for name, value in stored.items()
        if isinstance(value, str) and value.strip()
    }


def input_options(
    options: Mapping[str, Any],
    input_count: int,
) -> dict[int, str]:
    """Return the options of an output select, keyed by input number."""
    return {number: input_name(options, number) for number in range(1, input_count + 1)}


def device_edid_options(data: Mapping[str, Any]) -> dict[int, str]:
    """Return the EDIDs of the matrix as it names them, keyed by their value.

    An entry that was set up before the list was read from the matrix has
    none, so the built-in list stands in for it.
    """
    stored = data.get(CONF_EDID_OPTIONS)

    if not isinstance(stored, Mapping) or not stored:
        stored = DEFAULT_EDID_OPTIONS

    # Home Assistant stores the keys of the entry data sorted as text, which
    # puts 10 ahead of 2. The web interface lists the EDIDs by their number.
    return dict(
        sorted(
            (int(value), description)
            for value, description in stored.items()
            if str(value).isdecimal() and isinstance(description, str)
        )
    )


def edid_options(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
) -> dict[int, str]:
    """Return the options of an EDID select, keyed by EDID value."""
    names = stored_labels(options, CONF_EDID_LABELS)

    return {
        value: names.get(edid_label_key(value)) or description
        for value, description in device_edid_options(data).items()
    }


def values_by_option(options_by_value: Mapping[int, str]) -> dict[str, int]:
    """Return the reverse mapping used to translate a selection back."""
    return {option: value for value, option in options_by_value.items()}


def input_custom_name(options: Mapping[str, Any], number: int) -> str | None:
    """Return the user defined name of an input, if there is one."""
    return stored_labels(options, CONF_INPUT_LABELS).get(input_label_key(number))


def output_custom_name(options: Mapping[str, Any], number: int) -> str | None:
    """Return the user defined name of an output, if there is one."""
    return stored_labels(options, CONF_OUTPUT_LABELS).get(output_label_key(number))


def input_name(options: Mapping[str, Any], number: int) -> str:
    """Return the name of an input as shown by its name sensor."""
    return input_custom_name(options, number) or DEFAULT_INPUT_NAME.format(
        number=number
    )


def output_name(options: Mapping[str, Any], number: int) -> str:
    """Return the name of an output as shown by its name sensor."""
    return output_custom_name(options, number) or DEFAULT_OUTPUT_NAME.format(
        number=number
    )


def remap_edid_labels(
    labels: Mapping[str, str],
    previous: Mapping[int, str],
    current: Mapping[int, str],
) -> tuple[dict[str, str], list[tuple[str, str | None, str | None]]]:
    """Move the names of the EDIDs along when the matrix changes its list.

    A name is stored under the number of its EDID, while a new firmware may
    offer the same EDID under another number. Every name therefore follows the
    description it was given for. A name whose description is gone stays with
    its number if the matrix still offers it, and is dropped otherwise.

    Returns the names to store and every name that could not follow its
    description, with the description it was given for and the one of the EDID
    it ends up with, which is None once it is dropped.
    """
    value_by_description: dict[str, int] = {}

    for value, description in current.items():
        value_by_description.setdefault(description, value)

    remapped: dict[str, str] = {}
    unmatched: list[tuple[int, str, str | None]] = []

    for key, name in labels.items():
        number = key.removeprefix(_EDID_LABEL_PREFIX)

        if not key.startswith(_EDID_LABEL_PREFIX) or not number.isdecimal():
            continue

        value = int(number)
        description = previous.get(value)
        target = value_by_description.get(description) if description else None

        if target is not None and edid_label_key(target) not in remapped:
            remapped[edid_label_key(target)] = name
        else:
            unmatched.append((value, name, description))

    # Names that found their description go first, so one that stays with its
    # number does not take the place of one that moved there.
    changed: list[tuple[str, str | None, str | None]] = []

    for value, name, description in unmatched:
        key = edid_label_key(value)

        if value in current and key not in remapped:
            remapped[key] = name
            changed.append((name, description, current[value]))
        else:
            changed.append((name, description, None))

    return remapped, changed


def has_duplicates(options_by_value: Mapping[int, str]) -> bool:
    """Return whether two values resolve to the same option."""
    return len(set(options_by_value.values())) != len(options_by_value)
