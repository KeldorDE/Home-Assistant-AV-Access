"""Resolve the user defined names of the matrix ports.

An input without a name falls back to a translation key, so the default select
options stay localized. As soon as a name is configured it is shown as entered.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import (
    CONF_INPUT_LABELS,
    CONF_OUTPUT_LABELS,
    DEFAULT_INPUT_NAME,
    DEFAULT_OUTPUT_NAME,
)


def input_label_key(number: int) -> str:
    """Return the key holding the name of an input."""
    return f"input_{number}"


def output_label_key(number: int) -> str:
    """Return the key holding the name of an output."""
    return f"output_{number}"


def default_input_option(number: int) -> str:
    """Return the option used while an input has no name."""
    return f"hdmi_{number}"


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
    names = stored_labels(options, CONF_INPUT_LABELS)

    return {
        number: names.get(input_label_key(number)) or default_input_option(number)
        for number in range(1, input_count + 1)
    }


def values_by_option(options_by_value: Mapping[int, str]) -> dict[str, int]:
    """Return the reverse mapping used to translate a selection back."""
    return {option: value for value, option in options_by_value.items()}


def input_name(options: Mapping[str, Any], number: int) -> str:
    """Return the name of an input as shown by its name sensor."""
    names = stored_labels(options, CONF_INPUT_LABELS)

    return names.get(input_label_key(number)) or DEFAULT_INPUT_NAME.format(
        number=number
    )


def output_name(options: Mapping[str, Any], number: int) -> str:
    """Return the name of an output as shown by its name sensor."""
    names = stored_labels(options, CONF_OUTPUT_LABELS)

    return names.get(output_label_key(number)) or DEFAULT_OUTPUT_NAME.format(
        number=number
    )


def has_duplicates(options_by_value: Mapping[int, str]) -> bool:
    """Return whether two ports resolve to the same option."""
    return len(set(options_by_value.values())) != len(options_by_value)
