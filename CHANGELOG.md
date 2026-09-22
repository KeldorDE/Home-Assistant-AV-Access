# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The section of the version that is tagged is used as the body of the GitHub
release, so every release needs a heading of the form `## [1.0.0] - 2026-09-18`.
Tags are named after the version itself, for example `1.0.0`.

## [Unreleased]

## [1.0.1] - 2026-09-22

### Added

- Add audio mute toggle entities for outputs 1-4
- Add CEC entities for every output
- Add buttons for manual power on and off
- Add a switch for the automatic power function
- Add a number field for the automatic power delay time

### Changed

- Extend the confirmation window of a command to 15 seconds
- Skip sending an HDCP command when the input is already in the requested state
- Skip extra polling after commands; regular polling verifies confirmed changes
- Detect response completion by idle pause or connection closure to prevent read timeouts
- Expire confirmed values to avoid masking changes made at the matrix

### Fixed

- Keep an EDID or HDCP value a command confirmed from being reverted by a poll
  that started before the command and did not read that input in its rotation

## [1.0.0] - 2026-09-20

### Fixed

- Prevent stale polls from reverting confirmed states or falsely reporting external changes

### Changed

- Name the matrix itself as the origin of a change made at the front panel or
  with the remote control, instead of the integration

## [0.4.1] - 2026-09-20

### Fixed
- Add a value check to the EDID switch command to prevent redundant EDID updates
- Add a value check to the output switch command to prevent redundant output updates


## [0.4.0] - 2026-09-17

### Added

- Added select entities to change the outputs.
- Added select entities to change the EDID of the inputs.
- Added toggle entities to change the HDCP status of the inputs.
- Added config dialog to define input and output names
