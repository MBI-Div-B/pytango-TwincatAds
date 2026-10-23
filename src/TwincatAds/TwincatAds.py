""" TwincatAds

Read and write TwinCAT variables via pyADS
"""

import ctypes

import numpy as np
import pyads
from pyads.pyads_ex import type_is_string
from tango import AttrWriteType, CmdArgType, DevState, Util
from tango.server import Device, attribute, command, device_property, run

__all__ = ["TwincatAdsCtrl", "TwincatAdsDevice", "main"]

INT_TYPES = {
    ctypes.c_byte, ctypes.c_ubyte, ctypes.c_short, ctypes.c_ushort,
    ctypes.c_int, ctypes.c_uint, ctypes.c_long, ctypes.c_ulong,
    ctypes.c_longlong, ctypes.c_ulonglong,
}
FLOAT_TYPES = {ctypes.c_float, ctypes.c_double}
ARRAY_DTYPES = {
    bool: CmdArgType.DevVarBooleanArray,
    int: CmdArgType.DevVarLong64Array,
    float: CmdArgType.DevVarDoubleArray,
}
ADS_STATE_NAMES = {
    value: name.removeprefix("ADSSTATE_")
    for name, value in vars(pyads.constants).items()
    if name.startswith("ADSSTATE_")
}
STATE_SEVERITY = {DevState.ON: 0, DevState.ALARM: 1, DevState.FAULT: 2}


def tango_type(plc_type) -> type | str | None:
    """Map a pyads plc_type to str, bool, int or float.

    Returns "array" for ctypes arrays and None for unsupported types.
    """
    if plc_type is None:
        return None
    if type_is_string(plc_type):
        return str
    if hasattr(plc_type, "_length_"):
        return "array"
    if plc_type is ctypes.c_bool:
        return bool
    if plc_type in FLOAT_TYPES:
        return float
    if plc_type in INT_TYPES:
        return int
    return None


def parse_array(symbol_type: str) -> tuple[int, int, str]:
    """Return (lower, upper, element_type) of a 1D array declaration."""
    match = pyads.AdsSymbol._regex_array.fullmatch(symbol_type)
    if match is None:
        if symbol_type.startswith("ARRAY"):
            raise ValueError(f"unsupported array: {symbol_type}")
        raise ValueError(f"not an array: {symbol_type}")
    lower, upper, element_type = match.groups()
    return int(lower), int(upper), element_type


class TwincatAdsCtrl(Device):
    """
    Owns the ADS connection to one TwinCAT PLC.

    The state is ON while the PLC is reachable and in ADS state RUN, FAULT
    otherwise. Provides generic commands to read and write scalar and 1D array
    symbols by name. Array indices follow the PLC declaration, e.g.
    `ARRAY [1..100]` starts at index 1.
    """

    # -----------------
    # Device Properties
    # -----------------

    ams_netid: str = device_property(
        doc="AMS NetID of the PLC. Example: `5.12.82.20.1.1`"
    )
    ams_port: int = device_property(
        default_value=pyads.PORT_TC3PLC1,
        doc="ADS port of the PLC runtime. Typically 801 for TwinCAT 2 and 851 for TwinCAT 3",
    )
    local_ams_netid: str = device_property(
        default_value="",
        doc=(
            "AMS NetID of this machine, e.g. `1.2.3.4.1.1` (Linux only). "
            "Applies to the whole server process. Empty: use the AMS router's NetID"
        ),
    )
    plc_address: str = device_property(
        default_value="",
        doc="IP address or host name of the PLC. Empty: first four octets of ams_netid",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        super().init_device()
        self._symbols: dict[str, pyads.AdsSymbol] = {}
        self._last_state = DevState.FAULT
        self._error = ""
        self.plc = None
        try:
            if self.local_ams_netid:
                pyads.set_local_address(self.local_ams_netid)
            plc = pyads.Connection(self.ams_netid, self.ams_port, self.plc_address or None)
            plc.open()
            self.plc = plc
        except Exception as exc:
            self._error = f"Connection failed: {exc}"
            self.error_stream(self._error)

    def delete_device(self):
        if self.plc is not None:
            self.plc.close()

    def dev_state(self) -> DevState:
        if self.plc is None:
            state, status = DevState.FAULT, self._error
        else:
            try:
                ads_state, device_state = self.plc.read_state()
            except pyads.ADSError as exc:
                state, status = DevState.FAULT, f"PLC not reachable: {exc}"
            else:
                state = DevState.ON if ads_state == pyads.ADSSTATE_RUN else DevState.FAULT
                status = (
                    f"ADS state: {ADS_STATE_NAMES.get(ads_state, ads_state)}, "
                    f"device state: {device_state}"
                )
        if state == DevState.ON and self._last_state != DevState.ON:
            self._symbols.clear()
        self._last_state = state
        self.set_state(state)
        self.set_status(status)
        return state

    def dev_status(self) -> str:
        self.dev_state()
        return self.get_status()

    def get_symbol(self, symbol_name: str) -> pyads.AdsSymbol:
        if self.plc is None:
            raise ConnectionError(self._error)
        if symbol_name not in self._symbols:
            try:
                self._symbols[symbol_name] = self.plc.get_symbol(symbol_name)
            except pyads.ADSError as exc:
                raise ValueError(f"{symbol_name}: {exc}") from exc
        return self._symbols[symbol_name]

    def _array_info(self, symbol_name: str) -> tuple[pyads.AdsSymbol, int, int]:
        sym = self.get_symbol(symbol_name)
        lower, upper, _ = parse_array(sym.symbol_type)
        if sym.plc_type is None:
            raise ValueError(f"unsupported array: {sym.symbol_type}")
        return sym, lower, upper

    def read_array(
        self, symbol_name: str, start: int | None = None, count: int | None = None
    ) -> np.ndarray:
        """Read `count` elements from PLC-declared index `start`, clipped at the upper bound."""
        sym, lower, upper = self._array_info(symbol_name)
        start = lower if start is None else start
        if not lower <= start <= upper:
            raise ValueError(f"start {start} outside bounds [{lower}..{upper}] of {symbol_name}")
        available = upper + 1 - start
        count = available if count is None else min(count, available)
        if count < 1:
            raise ValueError(f"count must be positive, got {count}")
        element = sym.plc_type._type_
        return np.array(self.plc.read(
            sym.index_group,
            sym.index_offset + (start - lower) * ctypes.sizeof(element),
            element * count,
        ))

    def write_array(self, symbol_name: str, values, start: int | None = None) -> None:
        """Write values from PLC-declared index `start`; rejects writes past the upper bound."""
        sym, lower, upper = self._array_info(symbol_name)
        start = lower if start is None else start
        values = np.asarray(values).tolist()
        if not lower <= start <= upper:
            raise ValueError(f"start {start} outside bounds [{lower}..{upper}] of {symbol_name}")
        if not values or start + len(values) - 1 > upper:
            raise ValueError(
                f"{len(values)} values from {start} do not fit bounds [{lower}..{upper}] of {symbol_name}"
            )
        element = sym.plc_type._type_
        self.plc.write(
            sym.index_group,
            sym.index_offset + (start - lower) * ctypes.sizeof(element),
            values,
            element * len(values),
        )

    # --------
    # Commands
    # --------

    @command
    def read_float_value(self, symbol_name: str) -> float:
        """Read a scalar as float."""
        return float(self.get_symbol(symbol_name).read())

    @command
    def read_int_value(self, symbol_name: str) -> int:
        """Read a scalar as integer."""
        return int(self.get_symbol(symbol_name).read())

    @command
    def read_bool_value(self, symbol_name: str) -> bool:
        """Read a scalar as boolean."""
        return bool(self.get_symbol(symbol_name).read())

    @command
    def write_float_value(self, argin: tuple[list[float], list[str]]) -> None:
        """Write a float scalar: ([value], [name])."""
        self.get_symbol(argin[1][0]).write(float(argin[0][0]))

    @command
    def write_int_value(self, argin: tuple[list[int], list[str]]) -> None:
        """Write an integer scalar: ([value], [name])."""
        self.get_symbol(argin[1][0]).write(int(argin[0][0]))

    @command
    def write_bool_value(self, argin: tuple[list[int], list[str]]) -> None:
        """Write a boolean scalar: ([0|1], [name])."""
        self.get_symbol(argin[1][0]).write(bool(argin[0][0]))

    def _read_array_cmd(self, argin: list[str]) -> np.ndarray:
        name, *rest = argin
        start, count = ([int(v) for v in rest] + [None, None])[:2]
        return self.read_array(name, start, count)

    @command
    def read_float_array(self, argin: list[str]) -> list[float]:
        """Read [name, start, count] as floats; start and count are optional."""
        return self._read_array_cmd(argin).astype(float)

    @command
    def read_int_array(self, argin: list[str]) -> list[int]:
        """Read [name, start, count] as integers; start and count are optional."""
        return self._read_array_cmd(argin).astype(int)

    @command
    def read_bool_array(self, argin: list[str]) -> list[bool]:
        """Read [name, start, count] as booleans; start and count are optional."""
        return self._read_array_cmd(argin).astype(bool)

    def _write_array_cmd(self, argin) -> None:
        values, (name, *start) = argin
        self.write_array(name, values, int(start[0]) if start else None)

    @command
    def write_float_array(self, argin: tuple[list[float], list[str]]) -> None:
        """Write ([values], [name, start]) as floats; start is optional."""
        self._write_array_cmd(argin)

    @command
    def write_int_array(self, argin: tuple[list[int], list[str]]) -> None:
        """Write ([values], [name, start]) as integers; start is optional."""
        self._write_array_cmd(argin)

    @command
    def write_bool_array(self, argin: tuple[list[int], list[str]]) -> None:
        """Write ([0|1 values], [name, start]) as booleans; start is optional."""
        self._write_array_cmd(argin)

    @command
    def get_array_bounds(self, symbol_name: str) -> list[int]:
        """Return the declared [lower, upper] bounds of an array."""
        _, lower, upper = self._array_info(symbol_name)
        return [lower, upper]

    @command
    def get_array_type(self, symbol_name: str) -> str:
        """Return the declared element type of an array, e.g. REAL."""
        return parse_array(self._array_info(symbol_name)[0].symbol_type)[2]


class TwincatAdsDevice(Device):
    """
    Groups PLC variables of one TwinCAT PLC into a Tango device.

    Accesses the PLC through a TwincatAdsCtrl in the same device server.
    Scalars become attributes, arrays become read_<alias>/write_<alias>
    commands. Both are created once at server start; skipped entries are
    listed in the status and set the state to ALARM.
    """

    ads_ctrl_device: str = device_property(
        doc="Name of the TwincatAdsCtrl device. Must be served by the same device server"
    )
    scalar_symbols: list[str] = device_property(
        doc=(
            "One line per scalar: <plc_name>, <attr_name>, ro|rw\n"
            "The attribute type follows the PLC declaration (bool, int, float, str)"
        ),
    )
    array_symbols: list[str] = device_property(
        doc=(
            "One line per 1D array: <plc_name>, <alias>, ro|rw\n"
            "Creates read_<alias> and, for rw, write_<alias>. "
            "Indices follow the PLC declaration"
        ),
    )

    def init_device(self):
        super().init_device()
        try:
            self.ctrl: TwincatAdsCtrl = Util.instance().get_device_by_name(self.ads_ctrl_device)
        except Exception as exc:
            raise RuntimeError(
                f"Controller {self.ads_ctrl_device} not found in this device server"
            ) from exc

    def initialize_dynamic_attributes(self):
        self._scalars: dict[str, str] = {}
        self._skipped: list[str] = []
        self._attr_names = {"state", "status"}
        self._cmd_names = {"init", "state", "status"}
        for lines, add in (
            (self.scalar_symbols, self._add_scalar),
            (self.array_symbols, self._add_array),
        ):
            for line in lines or ():
                try:
                    plc_name, name, access = (s.strip() for s in line.split(","))
                    if access not in ("ro", "rw"):
                        raise ValueError(f"access must be ro or rw, got {access}")
                    add(plc_name, name, access == "rw")
                except Exception as exc:
                    self._skipped.append(f"Skipped '{line}': {exc}")
        for line in self._skipped:
            self.warn_stream(line)

    def _claim(self, names: set[str], *new: str) -> None:
        if taken := [n for n in new if n.lower() in names]:
            raise ValueError(f"name already in use: {', '.join(taken)}")
        names.update(n.lower() for n in new)

    def _add_scalar(self, plc_name: str, attr_name: str, writable: bool) -> None:
        sym = self.ctrl.get_symbol(plc_name)
        dtype = tango_type(sym.plc_type)
        if dtype == "array":
            raise ValueError(f"{plc_name} is an array ({sym.symbol_type}), use array_symbols")
        if dtype is None:
            raise ValueError(f"{plc_name} has unsupported type {sym.symbol_type}")
        self._claim(self._attr_names, attr_name)
        self.add_attribute(attribute(
            name=attr_name,
            dtype=dtype,
            access=AttrWriteType.READ_WRITE if writable else AttrWriteType.READ,
            doc=f"{plc_name}: {sym.symbol_type}",
            fget=self._read_scalar,
            fset=self._write_scalar if writable else None,
        ))
        self._scalars[attr_name] = plc_name

    def _read_scalar(self, attr):
        return self.ctrl.get_symbol(self._scalars[attr.get_name()]).read()

    def _write_scalar(self, attr):
        sym = self.ctrl.get_symbol(self._scalars[attr.get_name()])
        value = attr.get_write_value()
        # STRING(n) maps to c_char * n; bare STRING defaults to 80 characters in TwinCAT
        max_len = getattr(sym.plc_type, "_length_", 80)
        if isinstance(value, str) and len(value) > max_len:
            raise ValueError(f"string longer than {max_len} characters")
        sym.write(value)

    def _add_array(self, plc_name: str, alias: str, writable: bool) -> None:
        sym = self.ctrl.get_symbol(plc_name)
        lower, _, _ = parse_array(sym.symbol_type)
        dtype = tango_type(getattr(sym.plc_type, "_type_", None))
        if dtype not in ARRAY_DTYPES:
            raise ValueError(f"{plc_name} has unsupported type {sym.symbol_type}")
        read_name, write_name = f"read_{alias}", f"write_{alias}"
        self._claim(self._cmd_names, read_name, *([write_name] if writable else []))
        declaration = f"{plc_name}: {sym.symbol_type}"

        def read(argin):
            if len(argin) > 2:
                raise ValueError("expected [], [count] or [start, count]")
            start, count = ([None, None] + [int(v) for v in argin])[-2:]
            return self.ctrl.read_array(plc_name, start, count).astype(dtype)

        read.__name__ = read_name
        self.add_command(command(
            f=read,
            dtype_in=CmdArgType.DevVarLongArray,
            dtype_out=ARRAY_DTYPES[dtype],
            doc_in=f"[], [count] or [start, count] of {declaration}",
        ), device_level=True)

        if writable:
            def write(argin):
                self.ctrl.write_array(plc_name, argin)

            write.__name__ = write_name
            self.add_command(command(
                f=write,
                dtype_in=ARRAY_DTYPES[dtype],
                doc_in=f"values written from index {lower} of {declaration}",
            ), device_level=True)

    def dev_state(self) -> DevState:
        own = DevState.ALARM if self._skipped else DevState.ON
        state = max(self.ctrl.dev_state(), own, key=STATE_SEVERITY.get)
        self.set_state(state)
        self.set_status("\n".join([self.ctrl.get_status(), *self._skipped]))
        return state

    def dev_status(self) -> str:
        self.dev_state()
        return self.get_status()


# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    """Run TwincatAdsCtrl and TwincatAdsDevice in one server, controllers first."""
    return run((TwincatAdsCtrl, TwincatAdsDevice), args=args, **kwargs)


if __name__ == '__main__':
    main()
