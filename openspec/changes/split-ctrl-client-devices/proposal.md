# Proposal

## Why

The original single `TwincatAds` device put every ADS variable of a PLC into one flat set of attributes, mixing unrelated subsystems. Splitting it into one controller device that owns the ADS connection and several client devices that group related variables gives the Tango control system meaningful organizational units. The work-in-progress branch started this split, but clients cannot yet reach the PLC, and array access uses 0-based indices and a stateful write target.

## What Changes

- **BREAKING** The `TwincatAds` device class is replaced by two classes served from one device server process: `TwincatAdsCtrl` (controller) and `TwincatAdsDevice` (client). The package entry point and console script run both.
- The controller owns the single `pyads.Connection` and a symbol cache. Its state is computed from the PLC connection: ON only while the ADS state is RUN, FAULT otherwise (including at run time). The symbol cache is cleared on every FAULT to ON transition. Connection errors never raise out of `init_device`.
- The controller gets two optional connection properties: `local_ams_netid` (AMS NetID of this machine, needed when pyads uses its built-in router on Linux) and `plc_address` (IP or host name of the PLC; defaults to the first four octets of `ams_netid`).
- The controller provides generic scalar read/write commands (`read_<t>_value`, `write_<t>_value`) and array commands (`read_<t>_array`, `write_<t>_array`) for `float`, `int` and `bool`.
- **BREAKING** Array indices follow the PLC declaration (e.g. `ARRAY [1..100]` is 1-based) instead of always being 0-based.
- **BREAKING** Array writes are stateless and take `(values, [name, start])`. The `array_write_symbol` property and attribute are removed. Scalar writes take `(values, [name])`.
- New controller helper commands `get_array_bounds` and `get_array_type`.
- Clients find their controller in the same process by device name and access the PLC through it, without keeping their own symbol objects.
- Clients create scalar attributes from a `scalar_symbols` property (`<plc_name>, <attr_name>, ro|rw`), with the Tango type taken from the PLC declaration (`bool`, `int`, `float`, `str`). The explicit `<type>` field of the WIP is dropped.
- Clients create per-array commands `read_<alias>` / `write_<alias>` from a new `array_symbols` property (`<plc_name>, <alias>, ro|rw`) instead of attributes, to keep generic GUIs from reading large arrays periodically.
- A client reports the more severe of its controller's state and its own (FAULT > ALARM > ON). It is ALARM when configured symbols were skipped, and appends its own lines to the controller's status.

## Capabilities

### New Capabilities
- `ads-controller`: The controller device: PLC connection, connection state, symbol cache, and the generic scalar and array commands including PLC-declared index handling.
- `ads-client`: The client device: binding to a controller, statically configured scalar attributes and array commands, and combined state and status reporting.

### Modified Capabilities

None. The project has no existing specs.

## Impact

- `src/TwincatAds/TwincatAds.py`: both device classes are reworked.
- `src/TwincatAds/__init__.py`: the import of the removed `TwincatAds` class is replaced so the package and console script work again.
- Tango database configuration: existing `TwincatAds` device definitions must be recreated as one `TwincatAdsCtrl` plus `TwincatAdsDevice` clients, with properties renamed and reformatted as above, and `local_ams_netid`/`plc_address` set where needed.
- Callers of the array commands must switch to PLC-declared indices and the new write signature.
- No new dependencies (`pytango`, `pyads`).
