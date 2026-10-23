import ctypes

import pyads
import pytest

from TwincatAds.TwincatAds import parse_array, tango_type


@pytest.mark.parametrize(
    "plc_type, expected",
    [
        (pyads.PLCTYPE_BOOL, bool),
        (pyads.PLCTYPE_SINT, int),
        (pyads.PLCTYPE_UINT, int),
        (pyads.PLCTYPE_DINT, int),
        (pyads.PLCTYPE_ULINT, int),
        (pyads.PLCTYPE_TIME, int),
        (pyads.PLCTYPE_REAL, float),
        (pyads.PLCTYPE_LREAL, float),
        (pyads.PLCTYPE_STRING, str),
        (ctypes.c_char * 80, str),
        (pyads.PLCTYPE_REAL * 10, "array"),
        (pyads.PLCTYPE_WSTRING, None),
        (None, None),
    ],
)
def test_tango_type(plc_type, expected):
    assert tango_type(plc_type) == expected


@pytest.mark.parametrize(
    "symbol_type, expected",
    [
        ("ARRAY [1..100] OF REAL", (1, 100, "REAL")),
        ("ARRAY [0..9] OF STRING(80)", (0, 9, "STRING(80)")),
    ],
)
def test_parse_array(symbol_type, expected):
    assert parse_array(symbol_type) == expected


@pytest.mark.parametrize(
    "symbol_type, message",
    [
        ("REAL", "not an array"),
        ("ARRAY [1..10, 0..5] OF INT", "unsupported array"),
        ("ARRAY [-5..5] OF INT", "unsupported array"),
    ],
)
def test_parse_array_rejects(symbol_type, message):
    with pytest.raises(ValueError, match=message) as exc:
        parse_array(symbol_type)
    assert symbol_type in str(exc.value)
