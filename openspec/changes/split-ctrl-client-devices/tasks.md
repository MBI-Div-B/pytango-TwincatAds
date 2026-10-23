# Tasks

## 1. Packaging and shared helpers

- [x] 1.1 Fix `src/TwincatAds/__init__.py` to export `main` from `TwincatAds.py` (running both classes, controller first); verify `python -c "import TwincatAds"` succeeds and the `TwincatAds` console script prints Tango's usage message
- [x] 1.2 Add the scalar type mapping helper (string first, then array, bool, float, int, else unsupported) per design; verify with a small pytest over pyads `PLCTYPE_*` constants, `c_char * 80` and an array type
- [x] 1.3 Add the array declaration parser returning `(lower, upper, element_type)` and raising `ValueError` with `symbol_type` for scalars, multi-dim and negative bounds; verify with a pytest over sample `symbol_type` strings

## 2. Controller connection and state

- [x] 2.1 Make `init_device` apply `local_ams_netid` (via `set_local_address`) and `plc_address`, catch connection errors, clear the symbol cache, and never raise; verify by starting the server with an unreachable `ams_netid`, checking the controller exists in FAULT with the error in its status, then connecting with explicit `local_ams_netid`/`plc_address`
- [x] 2.2 Implement `dev_state`/`dev_status` from `plc.read_state()` (ON only for `ADSSTATE_RUN`) and clear the symbol cache on FAULT to ON; verify manually by stopping and restarting the PLC and watching the state change without `Init`
- [x] 2.3 Update the controller class docstring and property docs for `ams_netid`, `ams_port`, `local_ams_netid` and `plc_address`; verify they show in Jive/`DevInfo`

## 3. Controller commands

- [x] 3.1 Fix `write_<t>_value` to take `([value], [name])` with explicit mixed `dtype_in` where hints do not resolve; verify a write and read-back on the PLC
- [x] 3.2 Rework `_read_array_from_plc` to use `get_symbol`, the declaration parser, PLC-declared `start`, start validation and count clipping (fixing the `plctype` typo); verify the `ads-controller` array read scenarios against a 1-based PLC array
- [x] 3.3 Rework `write_<t>_array` to take `([values], [name, start])` with bounds checking, and remove `array_write_symbol`; verify the offset and past-the-end write scenarios on the PLC
- [x] 3.4 Add `get_array_bounds` and `get_array_type`; verify they return `[l, u]` and the element type for a PLC array and fail for a scalar

## 4. Client device

- [x] 4.1 Bind to the controller via `Util.instance().get_device_by_name` in `init_device`, failing with the controller name if absent; verify with a wrong `ads_ctrl_device`
- [x] 4.2 Create scalar attributes from `scalar_symbols` (3-field format, dtype from the mapping, names only, STRING length check on write), collecting skip lines; verify read/write of a BOOL, DINT, REAL and STRING attribute and a rejected over-long string
- [x] 4.3 Add `array_symbols` and create `read_<alias>`/`write_<alias>` commands (`device_level=True`, declaration in the doc string, write from the lower bound), collecting skip lines for unsupported entries and name collisions; verify the `ads-client` array scenarios on the PLC
- [x] 4.4 Implement `dev_state`/`dev_status` combining controller and own state (FAULT > ALARM > ON) and appending skip lines; verify with one missing symbol (ALARM) and with the PLC stopped (FAULT)
- [x] 4.5 Update the client class docstring and property docs for `ads_ctrl_device`, `scalar_symbols` and `array_symbols`; verify they show in Jive

## 5. Documentation and integration

- [x] 5.1 Add `README.md` (already referenced by `setup.cfg`) with the device server setup, property formats, index semantics and the migration steps from `design.md`; verify `pip install .` succeeds
- [ ] 5.2 Run one server instance with a controller and two clients against the PLC; verify attributes, array commands and state follow the PLC through a stop/start cycle
  - Verified on the PLC (2026-10-23): connecting with `ams_netid` and `plc_address`; BOOL, INT and REAL scalar attributes; client array reads
  - Still open: STRING attributes and over-long writes; controller `write_<t>_value`; controller array slice/clip/bounds reads, offset and past-the-end writes, `get_array_bounds`/`get_array_type`; client `write_<alias>`; state through PLC stop/start and cable loss; unreachable PLC at start then `Init`; two clients on one controller
