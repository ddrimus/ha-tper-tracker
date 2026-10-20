from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

# Repair issues raised by the integration (also their translation keys)
ISSUE_STOP_NOT_FOUND = "stop_not_found"
ISSUE_LINES_NOT_SERVED = "lines_not_served"
ISSUES = (ISSUE_STOP_NOT_FOUND, ISSUE_LINES_NOT_SERVED)


# Issue id of one kind of issue for one config entry
def issue_id(entry: ConfigEntry, kind: str) -> str:
    return f"{entry.entry_id}_{kind}"


# Create or update an issue when present is true, otherwise delete it
@callback
def async_set_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    kind: str,
    present: bool,
    *,
    fixable: bool = False,
    placeholders: dict[str, str] | None = None,
) -> None:
    if not present:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry, kind))
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(entry, kind),
        is_fixable=fixable,
        severity=ir.IssueSeverity.WARNING,
        translation_key=kind,
        translation_placeholders={"title": entry.title, **(placeholders or {})},
        data={"entry_id": entry.entry_id},
    )


# Delete every issue of a config entry, when the entry is removed
@callback
def async_delete_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    for kind in ISSUES:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry, kind))
