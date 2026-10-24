# AV Access matrix emulator

Emulates the Telnet port of an **AV Access 4KMX44-H2** HDMI matrix, so the
integration can be developed and tested without the hardware.

The commands and the answers follow the official
*API Command Set 4KMX44-H2 V1.0.0* and the behaviour the
[client](../../custom_components/av_access/client.py) of the integration
relies on:

* every command is answered on the connection it arrived on, and the matrix
  closes that connection afterwards,
* a command the matrix does not know is answered with its welcome line
  (`Welcome to the 4KMX44-H2 matrix!`), which is the only place the model is
  reported without being asked,
* the lines of a multi line answer are separated by a single carriage return
  and only the last one ends with CRLF,
* every command ends with CRLF and is case insensitive.

## Running it

The emulator is part of the development compose project:

```bash
make up          # starts Home Assistant and the emulator
make logs        # follows the logs of both
make down        # stops both
```

Add the integration in Home Assistant through
**Settings → Devices & services → Add integration → AV Access** with:

| Field | Value |
| --- | --- |
| Host | `matrix-emulator` |
| Port | `23` |

Home Assistant running outside of the compose project reaches the emulator at
the address of this machine on port `2323`.

The emulator can also be started without Docker, it only needs Python 3.13 and
no dependencies:

```bash
AVA_PORT=2323 python dev/emulator/emulator.py
```

## Trying it by hand

```bash
printf 'GET VER\r\n' | nc localhost 2323
printf 'GET MP all\r\n' | nc localhost 2323
printf 'SET SW hdmiin3 hdmiout1\r\n' | nc localhost 2323
printf 'help\r\n' | nc localhost 2323
```

An interactive `telnet localhost 2323` works as well, but the matrix closes
the connection after the first command unless
`AVA_CLOSE_AFTER_RESPONSE=false` is set.

## Settings

All settings are environment variables of the container.

### Device

| Variable | Default | Description |
| --- | --- | --- |
| `AVA_HOST` | `0.0.0.0` | Address the emulator listens on. |
| `AVA_PORT` | `23` | Port the emulator listens on. |
| `AVA_MODEL` | `4KMX44-H2` | Model reported by `GET VER` and the welcome line. The digits after `MX` define the number of ports, so `4KMX88-H2` emulates an 8x8 matrix. |
| `AVA_INPUT_COUNT` | from the model | Number of HDMI inputs. |
| `AVA_OUTPUT_COUNT` | from the model | Number of HDMI outputs. |
| `AVA_SW_VERSION` | `1.0` | Firmware version reported by `GET VER`. |
| `AVA_ARM_VERSION` | `1.0` | ARM version reported by `GET VER`. |
| `AVA_IP_ADDRESS` | `192.168.1.4` | Address reported by `GET IPADDR`. |
| `AVA_NETMASK` | `255.255.255.0` | Netmask reported by `GET IPADDR`. |
| `AVA_GATEWAY` | `192.168.1.1` | Gateway reported by `GET IPADDR`. |
| `AVA_IP_MODE` | `dhcp` | Mode reported by `GET IP MODE`. |

### Supported commands

Turning a command group off makes the matrix answer it with its welcome line,
exactly like a model that does not know the command. The integration then
creates no entities for that group, which is the path these switches are there
to test.

| Variable | Default | Description |
| --- | --- | --- |
| `AVA_HDCP_SUPPORTED` | `true` | Answer `GET/SET HDCP_S`. |
| `AVA_CEC_SUPPORTED` | `true` | Answer `GET/SET AUTOCEC_FN`, `GET/SET AUTOCEC_D` and `SET CEC_PWR`. |
| `AVA_SCALER_SUPPORTED` | `true` | Answer `GET/SET SCALER`. |
| `AVA_BULK_ROUTING_SUPPORTED` | `true` | Answer `GET MP all`. With `false` the integration falls back to one `GET MP hdmiout<x>` per output. |
| `AVA_CEC_AUTO_SHORT_REPLY` | `false` | Answer `GET AUTOCEC_FN` with `AUTOCEC_FN on` instead of `AUTOCEC_FN hdmiout1 on`, as the example in the command set shows. |

### Behaviour

| Variable | Default | Description |
| --- | --- | --- |
| `AVA_CLOSE_AFTER_RESPONSE` | `true` | Close the connection after the answer, like the real matrix. With `false` the connection stays open, which emulates a firmware the client has to detect by the pause after the answer. |
| `AVA_GREETING_ON_CONNECT` | `false` | Send the welcome line as soon as a client connects. |
| `AVA_RESPONSE_DELAY` | `0` | Seconds the matrix takes before it answers. Useful to provoke timeouts. |
| `AVA_IDLE_TIMEOUT` | `300` | Seconds an open connection may stay idle before it is dropped. |
| `AVA_MIN_COMMAND_GAP` | `0` | Seconds between two commands below which the matrix logs that it is overloaded. `1` matches the pause the integration keeps. |
| `AVA_FREEZE_DURATION` | `0` | Seconds the matrix stops answering after it was overloaded, which is how the real device reacts to commands that arrive back to back. Needs `AVA_MIN_COMMAND_GAP`. |
| `AVA_DRIFT_INTERVAL` | `30` in compose, `0` otherwise | Seconds between two changes the emulator performs on its own, which is what a switch at the front panel or on the remote control looks like. The integration reports those to the logbook as changes at the matrix. |
| `AVA_DRIFT_SEED` | random | Seed of those changes, so a run can be repeated. |
| `AVA_STATE_FILE` | unset | File the state is written to, so it survives a restart. The compose project uses `/data/state.json` in a named volume. |
| `AVA_LOG_LEVEL` | `INFO` | `DEBUG` also logs connections without commands. |

## Supported commands

| Command | Answer |
| --- | --- |
| `SET SW hdmiin<x> hdmiout<y>` | `SW hdmiin<x> hdmiout<y>` |
| `SET SW hdmiin<x> all` | `SW hdmiin<x> all` |
| `GET MP hdmiout<y>` | `MP hdmiin<x> hdmiout<y>` |
| `GET MP all` | one `MP hdmiin<x> hdmiout<y>` per output |
| `SET EDID hdmiin<x> <1-15>` | `EDID hdmiin<x> <n>` |
| `GET EDID hdmiin<x>` | `EDID hdmiin<x> <n>` |
| `GET EDID all` | one `EDID hdmiin<x> <nn>` per input |
| `SET HDCP_S hdmiin<x> on\|off` | `HDCP_S hdmiin<x> on\|off` |
| `GET HDCP_S hdmiin<x>` | `HDCP_S hdmiin<x> on\|off` |
| `SET MUTE audioout<y> on\|off` | `MUTE audioout<y> on\|off` |
| `SET MUTE all on\|off` | `MUTE all on\|off` |
| `GET MUTE audioout<y>` | `MUTE audioout<y> on\|off` |
| `SET CEC_PWR hdmiout<y>\|all on\|off` | `CEC_PWR hdmiout<y>\|all on\|off` |
| `SET AUTOCEC_FN hdmiout<y> on\|off` | `AUTOCEC_FN hdmiout<y> on\|off` |
| `GET AUTOCEC_FN hdmiout<y>` | `AUTOCEC_FN hdmiout<y> on\|off` |
| `SET AUTOCEC_D hdmiout<y> <1-30>` | `AUTOCEC_D hdmiout<y> <minutes>` |
| `GET AUTOCEC_D hdmiout<y>` | `AUTOCEC_D hdmiout<y> <minutes>` |
| `SET SCALER hdmiout<y>\|all on\|off` | `SCALER hdmiout<y>\|all on\|off` |
| `GET SCALER hdmiout<y>` | `SCALER hdmiout<y> on\|off` |
| `SAVE PRESET <1-3>` | `PRESET <n>` |
| `RESTORE PRESET <1-3>` | `PRESET <n>` |
| `SET IPADDR <ip> <mask> <gateway>` | `IPADDR IP:<ip> MASK:<mask> GATE:<gateway>` |
| `GET IPADDR` | `IPADDR IP:<ip> MASK:<mask> GATE:<gateway>` |
| `SET IP MODE static\|dhcp` | `IP MODE static\|dhcp` |
| `GET IP MODE` | `IP MODE static\|dhcp` |
| `GET VER` | `4KMX44-H2 VER 1.0, ARM VER 1.0` |
| `UPG MASTER\|ARM` | `UPG MASTER\|ARM` |
| `RESET` | `RESET`, and the matrix returns to its factory state |
| `REBOOT` | `REBOOT` |
| `help` | the list of the commands above |

Anything else, including a port the matrix does not have and a value outside
its range, is answered with `Welcome to the 4KMX44-H2 matrix!`.

### EDID values

| Value | Meaning |
| --- | --- |
| 1 – 4 | Copy from output 1 – 4 |
| 5 | 4K@60Hz 5.1ch audio With HDR |
| 6 | 4K@60Hz 2.0ch audio With HDR |
| 7 | 4K@30Hz 7.1ch audio With HDR |
| 8 | 4K@30Hz 5.1ch audio With HDR |
| 9 | 4K@30Hz 2.0ch audio With HDR |
| 10 | 4K@30Hz/8bit only 2.0ch audio Without HDR |
| 11 | 1080P@60Hz 2.0ch audio |
| 12 | 5K Ultra Wide_2CH |
| 13 | 5K Super Wide_2CH |
| 14 | Smart EDID |
| 15 | EDID Write |

The command set of the first firmware only documents 1 to 13 and names 12
*Smart EDID* and 13 *EDID Write*. The emulator follows the firmware the
integration was developed against, which offers the 15 values above.

### Defaults after a factory reset

Input *n* is routed to output *n*, every input uses EDID 5 with HDCP on, every
audio output is unmuted, the automatic CEC power function is on with a delay
of 2 minutes and the scaler is on.
