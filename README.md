# AV Access Matrix for Home Assistant

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

Support for additional AV Access matrix switches may be added in the future.

## Requirements

This integration communicates with the AV Access Matrix Controller, which handles communication with the matrix, command serialization, caching and device state.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Go to **Integrations**.
3. Open the menu in the top-right corner and select **Custom repositories**.
4. Add this repository as an **Integration**.
5. Search for **AV Access Matrix** and install it.
6. Restart Home Assistant.

After restarting Home Assistant, go to:

**Settings → Devices & services → Add integration → AV Access Matrix**

and enter the address of your AV Access Matrix Controller.

## Manual installation

Copy the directory:

```text
custom_components/av_access_matrix
```

to:

```text
/config/custom_components/av_access_matrix
```

Restart Home Assistant afterwards.

## License

This project is licensed under the MIT License.
