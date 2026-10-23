# TwincatAds

Tango device server to read and write variables on a TwinCAT PLC via ADS ([pyads](https://github.com/stlehmann/pyads)).

One server instance runs two device classes:

- `TwincatAdsCtrl` owns the ADS connection to one PLC and provides generic read/write commands.
- `TwincatAdsDevice` groups related PLC variables into one device, accessing the PLC through a controller in the same server instance.

## Installation

```
pip install .
```

Start the server with `TwincatAds <instance_name>`.

## TwincatAdsCtrl

| Property | Description |
|---|---|
| `ams_netid` | AMS NetID of the PLC, e.g. `5.12.82.20.1.1` |
| `ams_port` | ADS port of the PLC runtime, default 851 (TwinCAT 3 PLC1); 801 for TwinCAT 2 |
| `local_ams_netid` | Optional. AMS NetID of this machine, e.g. `1.2.3.4.1.1` (Linux only). Applies to the whole server process, so all controllers of one instance must use the same value |
| `plc_address` | Optional. IP address or host name of the PLC. Default: the first four octets of `ams_netid` |

A route from the PLC to `local_ams_netid` must be configured in TwinCAT.

The state is ON while the PLC answers and is in ADS state RUN, and FAULT otherwise; it is evaluated on each query. If the PLC is unreachable when the controller initializes, it stays FAULT until the controller's `Init` command.

Commands (`<t>` is `float`, `int` or `bool`):

| Command | Argument | Result |
|---|---|---|
| `read_<t>_value` | `name` | scalar value |
| `write_<t>_value` | `([value], [name])` | |
| `read_<t>_array` | `[name, start, count]`, `start` and `count` optional | array |
| `write_<t>_array` | `([values...], [name, start])`, `start` optional | |
| `get_array_bounds` | `name` | `[lower, upper]` |
| `get_array_type` | `name` | element type, e.g. `REAL` |

Bool values are written as integers 0/1.

### Array indices

Indices follow the PLC declaration: for `ARRAY [1..100] OF REAL`, index 1 is the first element. `start` defaults to the lower bound. A read `count` past the upper bound is clipped; a write past the upper bound is rejected. Only one-dimensional arrays with non-negative bounds of BOOL, integer and floating point types are supported.

## TwincatAdsDevice

| Property | Description |
|---|---|
| `ads_ctrl_device` | Name of the `TwincatAdsCtrl` device, served by the same server instance |
| `scalar_symbols` | One line per scalar: `<plc_name>, <attr_name>, ro\|rw` |
| `array_symbols` | One line per array: `<plc_name>, <alias>, ro\|rw` |

Each scalar becomes an attribute whose type follows the PLC declaration: BOOL as boolean, integer and time/date types as integer, REAL/LREAL as floating point, `STRING(n)` as string (writes longer than `n` characters are rejected).

Each array becomes a command `read_<alias>` and, for `rw`, `write_<alias>`, so generic GUIs do not poll large arrays:

- `read_<alias>([])` reads the whole array, `read_<alias>([count])` the first `count` elements, `read_<alias>([start, count])` from `start` in PLC-declared indices.
- `write_<alias>(values)` writes from the lower bound; fewer values write only the leading elements.

Attributes and commands are created once at server start. Entries that cannot be created (missing symbol, unsupported type, name collision, PLC unreachable at start) are skipped and listed in the status; the device is then ALARM. A server restart retries them.

The reported state is the more severe of the controller's state and the device's own (FAULT > ALARM > ON), and the status is the controller's status followed by the device's own lines.

## Example configuration

```
TwincatAds/beamline/DEVICE/TwincatAdsCtrl:   beamline/ads/plc1
    ams_netid:       5.12.82.20.1.1
    local_ams_netid: 192.168.1.10.1.1
    plc_address:     192.168.1.20

TwincatAds/beamline/DEVICE/TwincatAdsDevice: beamline/ads/motor1
    ads_ctrl_device: beamline/ads/plc1
    scalar_symbols:  MAIN.fSetpoint, setpoint, rw
                     MAIN.bReady, ready, ro
    array_symbols:   MAIN.fSpectrum, spectrum, ro
```

## Migration from the single `TwincatAds` class

1. Replace each `TwincatAds` device with one `TwincatAdsCtrl` (same `ams_netid`/`ams_port`) and one or more `TwincatAdsDevice`s in the same server instance, with `ads_ctrl_device` set.
2. Rewrite `scalar_symbols` lines from `<plc_name>, <attr_name>, <type>, <access>` to `<plc_name>, <attr_name>, ro|rw`; the type now follows the PLC declaration.
3. Set `local_ams_netid` and `plc_address` on the controller where the old setup relied on defaults or an external router.
4. Array command callers: use PLC-declared indices, and replace `array_write_symbol` plus `write_<t>_array(values)` with `write_<t>_array(([values], [name, start]))`.

Rollback: reinstall the previous version and restore the old device definitions.
