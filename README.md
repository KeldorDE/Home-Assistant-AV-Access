# AV Access for Home Assistant

Custom Home Assistant integration for controlling AV Access HDMI matrix switches.

The integration provides native Home Assistant entities for controlling HDMI routing and other supported matrix functions.

## Features

* HDMI input selection for each output
* EDID selection and management
* HDCP support toggle for each input
* Custom names for inputs and outputs, also available as sensors
* Native Home Assistant entities
* Configuration through the Home Assistant UI
* Local communication
* HACS compatible

## Supported devices

Currently developed and tested with:

* AV Access 4KMX44-H2

Support for additional AV Access devices may be added in the future.

## Requirements

This integration communicates with the AV Access Matrix Controller, which handles communication with the matrix, command serialization, caching and device state.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Go to **Integrations**.
3. Open the menu in the top-right corner and select **Custom repositories**.
4. Add this repository as an **Integration**.
5. Search for **AV Access** and install it.
6. Restart Home Assistant.

After restarting Home Assistant, go to:

**Settings → Devices & services → Add integration → AV Access**

and enter the address of your AV Access Matrix Controller.

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
| Host | yes | Address of the AV Access Matrix Controller. |
| Port | yes | Port of the AV Access Matrix Controller. Defaults to `62225`. |

Model, firmware version, the number of inputs and outputs and the link to the
matrix web interface are read from the controller, so the entities match the
connected matrix.

The connection details can be changed later without losing the entities through
**Settings → Devices & services → AV Access → Reconfigure**.

### Naming the ports

Inputs and outputs can be given your own names through
**Settings → Devices & services → AV Access → Configure**.

An input name replaces `HDMI 1` and so on in the input selection of every
output. Leaving a field empty restores the default name, and every input name
must be unique.

Every port also provides a name sensor, so a name can be used in a dashboard,
for example as a heading above the select of an output. Ports without a name
report `HDMI 1` or `Output 1`.

The EDID options are named by the matrix itself and are therefore not
renameable. Port names only change the options of a select. To rename an entity
itself, use the entity settings in Home Assistant.

### HDCP

Each input provides a switch that enables or disables HDCP support. The
switches are only created if the matrix reports its HDCP state, so a model
without HDCP commands simply has no HDCP entities.

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
