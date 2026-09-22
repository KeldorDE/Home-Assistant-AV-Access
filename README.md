# AV Access for Home Assistant

Custom Home Assistant integration for controlling AV Access HDMI matrix switches.

The integration provides native Home Assistant entities for controlling HDMI routing and other supported matrix functions.

![Showcase Quick Profiles](https://raw.githubusercontent.com/KeldorDE/Home-Assistant-AV-Access/refs/heads/main/docs/images/showcase-quick-profiles.png)

![Showcase EDID Select](https://raw.githubusercontent.com/KeldorDE/Home-Assistant-AV-Access/refs/heads/main/docs/images/showcase-edid-select.png)

## Features

* HDMI input selection for each output
* EDID selection and management
* HDCP support toggle for each input
* Audio mute toggle for each output
* CEC control for each output: manual power on/off, automatic power function and delay time
* Custom names for inputs and outputs, also available as sensors
* Native Home Assistant entities
* Configuration through the Home Assistant UI
* Local communication
* HACS compatible

![Entities](https://raw.githubusercontent.com/KeldorDE/Home-Assistant-AV-Access/refs/heads/main/docs/images/entities.webp)

## Supported devices

Currently developed and tested with:

* AV Access 4KMX44-H2

Support for additional AV Access devices may be added in the future.

## Requirements

The integration talks to the matrix directly over its Telnet port, so nothing
else has to be installed. The matrix only has to be reachable from Home
Assistant.

## State updates

The matrix accepts a single command at a time and needs a short pause
afterwards, so all communication is serialized and spaced out by the
integration. Sending commands back to back has been observed to freeze the
device.

The routing is polled every 3 seconds by default, which is the value that also
changes when somebody switches at the front panel of the matrix or with the
remote control. The interval can be changed in the configuration dialog of the
integration, next to the host and the port. EDID and HDCP cost one command per
input, so they are read for one input per poll instead of for all of them at
once. Audio mute states and the CEC settings are read for one output per poll
as well. A change made
at the device is therefore visible after one rotation over all inputs or
outputs at the latest. A command issued by Home Assistant is confirmed by the
matrix and applied immediately, so an entity never waits for the next poll.

A change the integration finds during a poll was made at the front panel or with
the remote control, so it is reported to the logbook as "was changed at the
matrix" and the state change itself names the matrix as its origin. A change
Home Assistant itself performed keeps showing the user or the automation that
triggered it.

![Log Book](https://raw.githubusercontent.com/KeldorDE/Home-Assistant-AV-Access/main/docs/images/logbook.webp)

## Installation

### HACS

This integration is not part of the HACS default store, so the repository has to
be added as a custom repository once. [HACS](https://hacs.xyz) has to be
installed in Home Assistant beforehand.

1. Open **HACS** in the sidebar of Home Assistant.
2. Open the menu in the top-right corner (⋮) and select **Custom repositories**.
3. Paste the repository URL into the **Repository** field:

   ```text
   https://github.com/KeldorDE/Home-Assistant-AV-Access.git
   ```

4. Select **Integration** as the **Type** and confirm with **Add**.
5. Close the dialog, search for **AV Access** in HACS and open the repository.
6. Select **Download** and confirm the version that is offered.
7. Restart Home Assistant.

The repository stays in the list, so updates are offered by HACS like for any
other integration. Only tagged releases are offered as updates, never single
commits of the default branch.

After restarting Home Assistant, go to:

**Settings → Devices & services → Add integration → AV Access**

and enter the address of your AV Access HDMI matrix.

## Manual installation

Copy the directory:

```text
custom_components/av_access
```

to:

```text
/config/custom_components/av_access
```

Restart Home Assistant afterwards.

## Configuration

The integration is configured through the Home Assistant UI:

| Field | Required | Description |
| --- | --- | --- |
| Host | yes | Address of the AV Access HDMI matrix. |
| Port | yes | Telnet port of the matrix. Defaults to `23`. |

Model, firmware version, the number of inputs and outputs and the link to the
matrix web interface are read from the matrix, so the entities match the
connected device.

The connection details can be changed later without losing the entities through
**Settings → Devices & services → AV Access → Reconfigure**.

### Naming the ports

Inputs and outputs can be given your own names through
**Settings → Devices & services → AV Access → Configure**.

An input name replaces `HDMI 1` and so on in the input selection of every
output. Leaving a field empty restores the default name, and every input name
must be unique.

A name is also used by the entities that control the port. An output named
`Living room` turns the select `Output 2` into `Output 2 - Living room`, and an
input named `Apple TV` turns `EDID - Input 1` into `EDID - Input 1 - Apple TV`
and `HDCP Input 1` into `HDCP Input 1 - Apple TV`. An output name is also added
to its audio mute switch and to its CEC entities. Ports without a name keep the
plain name. The name
sensors always keep their plain name, because they report the port name as
their state.

Every port also provides a name sensor, so a name can be used in a dashboard,
for example as a heading above the select of an output. Ports without a name
report `HDMI 1` or `Output 1`.

The EDID options are named by the matrix itself and are therefore not
renameable. Renaming a port only changes the name of its entities and the
options of a select, not the entity ID. To change the name or the entity ID of
a single entity, use the entity settings in Home Assistant.

### HDCP

Each input provides a switch that enables or disables HDCP support. The
switches are only created if the matrix reports its HDCP state, so a model
without HDCP commands simply has no HDCP entities.

### Audio mute

Each output provides a switch that mutes or unmutes its audio. The switch is
on while the audio is muted.

### CEC

Each output provides the CEC functions of the matrix, mirroring the CEC section
of its web interface:

* Two buttons that power the connected sink on or off over CEC. The matrix only
  passes the command on to the sink and never reports its power state, which is
  why these are buttons instead of a switch.
* A switch for the automatic CEC power function. While it is on, the matrix
  powers the sink off once the output has been without an active signal for the
  delay time.
* A number with the delay time in minutes, between 1 and 30 minutes.

The CEC entities are only created if the matrix reports its CEC state, so a
model without CEC commands simply has no CEC entities.

## Templates

Every output provides a diagnostic sensor with the number of the input that is
currently routed to it. It is the raw counterpart of the select, which reports
the name of the input.

Combined with `state_translated`, the EDID that currently applies to an output
can be resolved without a helper entity:

```jinja
{% set input = states('sensor.av_access_output_1_input_number') %}
{{ state_translated('select.av_access_input_' ~ input ~ '_edid') }}
```

## Diagnostics

Device information and the current routing state can be downloaded through
**Settings → Devices & services → AV Access → Download diagnostics**.

Addresses are redacted, so the file can be attached to a bug report.

## License

This project is licensed under the MIT License.
