"""Repair issues of the AV Access HDMI matrix integration.

Every issue belongs to one entry, so its ID ends with the ID of the entry and
two matrices do not share an issue.
"""

from __future__ import annotations

from collections.abc import Sequence

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_EDID_LABELS_CHANGED, ISSUE_EDID_LIST_FALLBACK

# Shown for a description that does not exist, which is the case for a name
# that was dropped.
_NO_DESCRIPTION = "\u2013"


def _issue_id(issue: str, entry: ConfigEntry) -> str:
    """Return the ID of an issue of an entry."""
    return f"{issue}_{entry.entry_id}"


@callback
def async_create_edid_list_fallback_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Report that the built-in EDID list stands in for the one of the matrix."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(ISSUE_EDID_LIST_FALLBACK, entry),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_EDID_LIST_FALLBACK,
        translation_placeholders={
            "name": entry.title,
            "host": entry.data[CONF_HOST],
        },
    )


@callback
def async_delete_edid_list_fallback_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Withdraw the issue about the built-in EDID list."""
    ir.async_delete_issue(hass, DOMAIN, _issue_id(ISSUE_EDID_LIST_FALLBACK, entry))


@callback
def async_create_edid_labels_changed_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    changed: Sequence[tuple[str, str | None, str | None]],
) -> None:
    """Ask the user to check the names of EDIDs the matrix no longer offers.

    The list is built here instead of in the translation, as its length is only
    known now. It only holds names and descriptions, which need no translation.
    """
    lines = "\n".join(
        f"- **{name}**: {previous or _NO_DESCRIPTION} → {current or _NO_DESCRIPTION}"
        for name, previous, current in changed
    )

    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(ISSUE_EDID_LABELS_CHANGED, entry),
        is_fixable=False,
        # The names are stored in the options of the entry, so the issue has to
        # survive a restart until the user has looked at them.
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_EDID_LABELS_CHANGED,
        translation_placeholders={"name": entry.title, "labels": lines},
    )


@callback
def async_delete_edid_labels_changed_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Withdraw the issue about the names of the EDIDs."""
    ir.async_delete_issue(hass, DOMAIN, _issue_id(ISSUE_EDID_LABELS_CHANGED, entry))


@callback
def async_delete_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Withdraw every issue of an entry that is removed."""
    async_delete_edid_list_fallback_issue(hass, entry)
    async_delete_edid_labels_changed_issue(hass, entry)
