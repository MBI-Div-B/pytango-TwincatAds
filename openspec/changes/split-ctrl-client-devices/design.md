# Design

## Context

`src/TwincatAds/TwincatAds.py` on the `separate_ctrl` branch already contains `TwincatAdsCtrl` (connection, symbol cache, typed commands, `_read_array_from_plc` with raw offset reads) and a `TwincatAdsDevice` skeleton whose `generic_read`/`generic_write` reference a `_symbols` dict it never has. `__init__.py` still imports the removed `TwincatAds` class. pyads cannot read slices by name (pyads#406); the existing raw `plc.read(index_group, index_offset + start * elsize, elem * n)` approach is kept.

Relevant pyads behavior (read from pyads master, Oct 2026):
- `AdsSymbol.plc_type` is derived from the textual `symbol_type`. `ARRAY [l..u] OF T` becomes `T * (u-l+1)`; the regex `ARRAY \[(\d+)..(\d+)\] OF (.*)` does not match negative bounds or multiple dimensions, leaving `plc_type = None`.
- `STRING(n)` becomes `c_char * n`, bare `STRING` becomes `c_char`; `pyads_ex.type_is_string()` detects both and reads decode to `str`.
- String writes send `len(value) + 1` bytes with no size check.
- `AdsSymbol.array_size` is only for arrays of structures and is 1 for normal arrays.

## Goals / Non-Goals

**Goals:**
- One ADS connection per PLC, shared in-process by any number of clients.
- Typed client attributes and commands without a manual type field.

**Non-Goals:**
- Clients in a different process or host than their controller.
- Rebuilding client attributes or commands without a server restart.
- WSTRING, arrays of STRING or structures, multi-dimensional arrays, negative bounds.
- Detecting a PLC program download that happens without a connection loss (ADS symbol version, index group 0xF008).
- Change events through ADS notifications; throttling of state queries.
- Creating the route on the PLC side (`pyads.add_route_to_plc`). The route to this machine's `local_ams_netid` must be configured in TwinCAT.

## Decisions

### In-process controller lookup
The client gets the controller's Python object with `tango.Util.instance().get_device_by_name(ads_ctrl_device)` in `init_device` and calls its methods directly. Alternative: `DeviceProxy` to the controller's commands, which would require one Tango round trip per access, manual dtypes and per-type command families. The object stays valid across the controller's `Init`, since Tango re-runs `delete_device`/`init_device` on the same instance. `run()` lists `TwincatAdsCtrl` before `TwincatAdsDevice` so controllers are created first.

### Clients store names, not symbols
Clients keep `{attr_or_alias: plc_name}` and call `ctrl.get_symbol(plc_name)` on every access. The controller cache is the only place holding `AdsSymbol`s, so clearing it (on FAULT to ON, and in `init_device`) is enough to invalidate stale offsets everywhere.

### Connection setup
`init_device` calls `pyads.set_local_address(local_ams_netid)` if the property is set. It then creates `Connection(ams_netid, ams_port, plc_address or None)`, all inside the existing `try/except`. With `ip_address=None` pyads uses the first four octets of `ams_netid`. `set_local_address` applies process-wide, so all controllers in one server instance must use the same value. On Windows it raises, and that error is reported like any other connection error.

### Controller state computed on demand
`TwincatAdsCtrl.dev_state()` calls `plc.read_state()`. `ADSError` or an ADS state other than `ADSSTATE_RUN` gives FAULT; otherwise ON. The status is set in the same call. The previous state is remembered so a FAULT to ON transition clears `_symbols`. `init_device` wraps `Connection(...)`/`open()` in `try/except` and records the error for the status instead of raising. Alternative: catching `ADSError` in every command and setting FAULT; rejected because recovery would then need its own detection.

On Linux, `open()` adds the route with `adsAddRoute`, which opens the TCP connection to the PLC immediately, so it fails when the PLC is unreachable. The PLC is assumed to be on the same subnet without a firewall, so an unreachable PLC fails within about 3 s (ARP timeout). If `open()` fails, the controller has no connection and stays FAULT until its next `Init`; it does not retry, which keeps state queries free of connection attempts and avoids custom networking code. Once open, `read_state()` is the reachability check.

### Client state and status
`TwincatAdsDevice.dev_state()` returns the more severe of `ctrl.dev_state()` and its own state, using the order FAULT > ALARM > ON. `dev_status()` returns the controller status plus the client's skip lines, which are collected once in `initialize_dynamic_attributes`.

### Type mapping
One helper maps a scalar `plc_type` to a Tango type: string types first (`type_is_string`), then any ctypes array (has `_length_`) is "array", then `c_bool` gives `bool`, `c_float`/`c_double` give `float`, the `c_(u)int*` types give `int`. Anything else, including `None`, is unsupported. Array element types use the same mapping on `plc_type._type_`, with strings unsupported. Client array commands use `DevVarBooleanArray`, `DevVarLong64Array` and `DevVarDoubleArray` so all integer widths, including LINT/ULINT, fit one type.

### Array declaration parsing
One controller helper parses `symbol_type` with `AdsSymbol._regex_array` and returns `(lower, upper, element_type)`, or raises `ValueError` with the `symbol_type` for non-arrays and unsupported arrays. Read, write, `get_array_bounds` and `get_array_type` all use it, and so do the client's array commands, through the controller. The element offset is `(start - lower) * sizeof(plc_type._type_)`.

### Command signatures
Controller commands use the declared Tango mixed types (`DevVarDoubleStringArray`, `DevVarLongStringArray`, numbers first). If PyTango type hints do not resolve to these types, explicit `dtype_in`/`dtype_out` in `@command(...)` are used. Client array commands are added with `self.add_command(command(f=..., name=..., dtype_in=..., dtype_out=..., doc_in=...), device_level=True)` from `initialize_dynamic_attributes`. `read_<alias>` takes one `DevVarLongArray` of length 0, 1 (`count`) or 2 (`start, count`), see the `ads-client` *Array read command* requirement; the controller's internal read is called with `start = lower` when only `count` is given. Whether a PyTango client can call it with no argument or must pass `[]` is checked during implementation.

### Client properties
`scalar_symbols` keeps its name with the three-field format `<plc_name>, <attr_name>, ro|rw`; `array_symbols` is new with the same format. The WIP default value is dropped so an empty client has no entries.

## Risks / Trade-offs

- [PLC unreachable at server start: the controller stays FAULT and all client entries are skipped] → the status lists every skipped entry; a controller `Init` restores the connection and a server restart restores the client entries (decided).
- [PLC behind a router or firewall that drops packets] → `open()` blocks for minutes during `init_device`; out of scope by the same-subnet assumption.
- [Every client state query triggers an ADS `read_state`] → negligible for typical polling; add a short cache if it shows up on the PLC.
- [Program download without connection loss leaves stale offsets in the cache] → out of scope; a controller `Init` clears the cache manually.
- [Relying on the private `AdsSymbol._regex_array`] → if pyads renames it, a local copy of the one-line regex replaces it.
- [Generated command names may collide] → collisions are skipped with a status line.
- [Controllers in one process with different `local_ams_netid`] → the last one wins; documented as one value per server instance.

## Migration Plan

Replace each existing `TwincatAds` device in the Tango database with one `TwincatAdsCtrl` (same `ams_netid`/`ams_port`) and one or more `TwincatAdsDevice`s in the same server instance, with `ads_ctrl_device` set and `scalar_symbols` lines rewritten to `<plc_name>, <attr_name>, ro|rw`. Set `local_ams_netid` and `plc_address` on the controller where the old setup relied on defaults or an external router. Rollback means reinstalling the previous version and the old device definitions.
