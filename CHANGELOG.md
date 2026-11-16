# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The section of the version that is tagged is used as the body of the GitHub
release, so every release needs a heading of the form `## [1.0.0] - 2026-09-18`.
Tags are named after the version itself, for example `1.0.0`.

## [Unreleased]

## [3.0.0] - 2026-11-17

### Added

- Repair issue while the EDID list cannot be read, retried every 15 minutes and on every start
- EDID names follow their EDID when the matrix offers a different list, names without a match are reported as a repair issue
- Attributes `input_options` and `edid_options` on the selects to select an input or EDID by its number

### Changed

- **Breaking:** Inputs without a name are offered as `HDMI 1` instead of `hdmi_1`, matching their name sensor; adapt automations that select `hdmi_1` and so on
- Read the EDID list of older entries in the background instead of delaying the start

### Fixed

- Send a command even if Home Assistant already shows the requested value
- Keep reading the routing with a single command after one lost answer
- Keep the input of an output missing from an answer instead of showing it as unknown
- Create the HDCP and CEC entities of every port even if an answer got lost during setup

## [2.0.0] - 2026-11-15

### Added

- Read the list of EDIDs from the web interface of the matrix while setting up and reconfiguring, instead of a fixed list
- Name every EDID yourself in the configuration dialog of the integration
- Serve the page with the EDID list in the emulator (`AVA_HTTP_PORT`)

### Changed

- **Breaking:** The options of the EDID selects are the names of the matrix, such as `4K@60Hz 5.1ch audio With HDR`, instead of keys like `4k60_5_1ch_hdr`, and are no longer translated; adapt automations that select an EDID
- No longer offer `EDID Write`, which only opens an upload dialog in the web interface

### Fixed

- Only accept a device in the configuration dialog that names a matrix model with its port layout, such as `4KMX44-H2`, instead of setting up anything that answers on the port and then failing to load

## [1.1.0] - 2026-11-04

### Changed

- Send commands issued from Home Assistant ahead of waiting polling commands
- Drop the pause of one second between two commands, as a load test showed the matrix handles commands back to back, which makes a poll take well below a second instead of about six seconds
- Read the routing on every poll and the other settings of all ports once a minute instead of one input and one output per poll, so a change of the routing at the matrix shows up sooner while the matrix gets far fewer commands
- Let the value of a command win over a poll for 5 instead of 15 seconds, so a change made at the matrix right after a command is no longer hidden as long
- Show the value of a command right away instead of after the confirmation of the matrix, and restore the previous value if the command fails
- Greet every connection in the emulator like the real matrix, and reproduce a discarded command with `AVA_GREETING_DELAY`
- Describe the installation through the Marketplace of Home Assistant 2026.11 in the README and add a button that opens the integration directly in Home Assistant

### Fixed

- Send one command at a time also while the configuration dialog checks a matrix that is already set up and while the integration reloads
- Wait for the welcome line of the matrix before sending a command, as the matrix occasionally discards a command that arrives earlier and answers with the welcome line alone
- Send a discarded command once more instead of failing or taking the command as unsupported by the matrix
- Show a failed command as an error message instead of an unexpected error with a traceback
- Name the user or automation that changed the routing in the logbook of the input number sensor, and report a change at the matrix there as well
- Show the icons of the output and EDID selects also for ports with a user defined name
- Reject a port outside of 1 to 65535 in the configuration dialog with a message at the field instead of a failed connection
- Require Home Assistant 2025.8 or later, the first release that provides everything the integration uses, so HACS no longer offers it to older versions on which it fails to load

## [1.0.3] - 2026-10-24

### Added

- Add an AV Access matrix emulator for development testing

### Fixed

- Allow the reconfigure flow to change the address of the matrix without losing the entities

## [1.0.2] - 2026-09-22

### Changed

- Update the changelog with some showcase images

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
