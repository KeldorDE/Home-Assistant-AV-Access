# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project

Custom Home Assistant integration (`av_access`, distributed via HACS) that controls
AV Access HDMI matrix switches (developed against the **4KMX44-H2**) over their
Telnet port. Pure Python, no external requirements. Targets Python 3.13 and
Home Assistant ≥ 2025.8.0 (the first release with `OptionsFlowWithReload`; keep
the minimum in [hacs.json](hacs.json) and the README in sync when using newer APIs).

## Development environment

```bash
make up              # starts the Docker environment (Home Assistant + matrix emulator)
make down            # stops it
make restart         # down + up — needed after code changes, HA loads the integration at startup
make logs            # follow logs of all containers
make emulator-logs   # follow the emulator logs only
make emulator-reset  # return the emulated matrix to its factory state
```

- Home Assistant is reachable at **http://localhost:8124/**
- Login for the AI user: **user `claude`, password `claude`**
- `custom_components/av_access` is bind-mounted into the container; `dev/config` is the HA config directory (mostly git-ignored).
- Add the integration in HA with host `matrix-emulator`, port `23`. From the host machine the emulator listens on `localhost:2323`.
- Talk to the emulator by hand: `printf 'GET MP all\r\n' | nc localhost 2323`
- Emulator behaviour (timeouts, unsupported command groups, front-panel "drift", greeting delay, …) is configured via `AVA_*` env vars in [dev/docker-compose.yml](dev/docker-compose.yml); all of them are documented in [dev/emulator/README.md](dev/emulator/README.md).

## Lint / format

There is no test suite. CI ([.github/workflows](.github/workflows)) runs Ruff, HACS validation and hassfest.

```bash
ruff check custom_components/
ruff format --check custom_components/
```

Ruff config lives in [pyproject.toml](pyproject.toml) (broad rule set incl. pydocstyle pep257 — every module, class and function needs a docstring).

## Architecture

All code is in [custom_components/av_access/](custom_components/av_access/):

- [client.py](custom_components/av_access/client.py) — `AVAccessClient`: Telnet protocol, response parsers, device info (model → port count via `ports_from_model`). Key device quirks it handles:
  - one connection per command; the matrix greets with `Welcome to the <model> matrix!` and closes after answering. The client waits for the greeting before sending (`GREETING_TIMEOUT`), and a greeting-only answer means "discarded" (retried, `DISCARDED_COMMAND_RETRIES`) or "unsupported command".
  - every command goes through a per-host/port `_CommandGate` that sends one command at a time without any pause. A load test with firmware 3.3 (thousands of SET/GET commands back to back, even 4 connections in parallel) showed the matrix needs no pause, so do not reintroduce one without new evidence. `CommandPriority` lets user commands jump ahead of queued polling commands. The gate is shared module-wide so config flow validation and reloads also respect it.
- [coordinator.py](custom_components/av_access/coordinator.py) — `AVAccessCoordinator` (`DataUpdateCoordinator`). Every poll reads the routing (1 command, `scan_interval`); the settings of all ports (EDID/HDCP/mute/CEC, 20 commands) only every `SETTINGS_POLL_INTERVAL` (60 s) or right after a failed settings command (`_settings_stale`). Only the first refresh (`client.async_get_status`) detects HDCP/CEC support; later polls only query ports that already have values and keep the previous value when a read returns nothing. Set-commands go through `_async_set_value`: the requested value is published before the command is sent (optimistic), replaced by the matrix confirmation, and reverted if the command fails or is cancelled; the latest command per port wins. `_PendingState` keeps the value for `COMMAND_CONFIRM_TIMEOUT` so an in-flight poll doesn't overwrite it. Entities pass `self._context` so every entity a command changes (e.g. the input number sensor) carries the service call context into the logbook.
- [entity.py](custom_components/av_access/entity.py) — `AVAccessEntity` base. Detects changes that came from a poll (not from HA) and fires `EVENT_EXTERNAL_CHANGE` so [logbook.py](custom_components/av_access/logbook.py) shows "changed at the matrix". Also handles naming after user-defined port labels.
- Platforms: [select.py](custom_components/av_access/select.py) (output routing, EDID), [switch.py](custom_components/av_access/switch.py) (HDCP, audio mute, CEC auto), [number.py](custom_components/av_access/number.py) (CEC delay), [button.py](custom_components/av_access/button.py) (CEC power on/off), [sensor.py](custom_components/av_access/sensor.py) (port names, routed input number). HDCP/CEC entities are only created when the matrix supports those commands.
- [config_flow.py](custom_components/av_access/config_flow.py) — user step, reconfigure (same model may change host, unique ID from `build_unique_id`), options flow for port labels (`OptionsFlowWithReload`). Label helpers are in [labels.py](custom_components/av_access/labels.py).
- [const.py](custom_components/av_access/const.py) — timing constants, translation keys, EDID value ↔ option mapping.
- [diagnostics.py](custom_components/av_access/diagnostics.py) — redacts addresses.

## Conventions

- Entity names/options come from translation keys; keep [translations/en.json](custom_components/av_access/translations/en.json) and [translations/de.json](custom_components/av_access/translations/de.json) in sync. Ports with a custom label use a second key with the `_named` suffix.
- When adding a matrix command, also implement it in [dev/emulator/emulator.py](dev/emulator/emulator.py) and document it in the emulator README.
- Comments explain *why* (device behaviour) in full sentences — follow that style.
- Add user-facing changes to the `[Unreleased]` section of [CHANGELOG.md](CHANGELOG.md) (Keep a Changelog). Releases: bump `version` in [manifest.json](custom_components/av_access/manifest.json), add a `## [x.y.z]` changelog section, tag `x.y.z` (no `v` prefix) — the release workflow checks that tag and manifest match.
- Work happens on `develop`; `main` is the release branch.
