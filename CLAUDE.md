# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project

Custom Home Assistant integration (`av_access`, distributed via HACS) that controls
AV Access HDMI matrix switches (developed against the **4KMX44-H2**) over their
Telnet port. Pure Python, no external requirements. Targets Python 3.13 and
Home Assistant ≥ 2025.2.0.

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
  - the matrix freezes on back-to-back commands, so every command goes through a per-host/port `_CommandGate` that serializes them with `COMMAND_DELAY` pauses. `CommandPriority` lets user commands jump ahead of queued polling commands. The gate is shared module-wide so config flow validation and reloads also respect it.
- [coordinator.py](custom_components/av_access/coordinator.py) — `AVAccessCoordinator` (`DataUpdateCoordinator`). Polls routing every interval, but EDID/HDCP (per input) and mute/CEC (per output) round-robin one port per poll. Set-commands update state immediately from the matrix confirmation; `_PendingState` keeps a confirmed value for `COMMAND_CONFIRM_TIMEOUT` so an in-flight poll doesn't overwrite it.
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
