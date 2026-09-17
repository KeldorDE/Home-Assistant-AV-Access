# AV Access for Home Assistant

Custom Home Assistant integration for controlling AV Access HDMI matrix switches.

The integration provides native Home Assistant entities for controlling HDMI routing and other supported matrix functions.

## Features

* HDMI input selection for each output
* EDID selection and management
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

## Diagnostics

Device information and the current routing state can be downloaded through
**Settings → Devices & services → AV Access → Download diagnostics**.

Addresses are redacted, so the file can be attached to a bug report.

## License

This project is licensed under the MIT License.
