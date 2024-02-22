# -*- coding: utf-8 -*-
#
# This file is part of the TwincatAds project
#
#
#
# Distributed under the terms of the MIT license.
# See LICENSE for more info.

""" TwincatAds

Read and write TwinCAT variables via pyADS
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import command
from tango.server import device_property, attribute
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(TwincatAds.additionnal_import) ENABLED START #
import pyads
import numpy as np
# PROTECTED REGION END #    //  TwincatAds.additionnal_import

__all__ = ["TwincatAds", "main"]


class TwincatAds(Device):
    """
    Read and write TwinCAT variables via pyADS

    **Properties:**

    - Device Property
        ams_netid
            - AMS NetID for an established route. Examples: `127.0.0.1.1.1`,  `5.12.82.20.1.1`
            - Type:'DevString'
        ams_port
            - Port to use for ADS connection.\nTypically 801 for TwinCAT2 and 851 for TwinCAT3
            - Type:'DevLong'
        scalar_symbols
            - List of ADS symbols.
            Dynamic attributes are created for each entry on device start.
            Write each symbol description as a line with comma-separated fields:
            <ads_name>, <label>, <access>
            Example: MAIN.subroutine.bOutputActive, output, rw
            <access> is either ``rw`` or ``ro``
            - Type:'DevString'
    """
    # PROTECTED REGION ID(TwincatAds.class_variable) ENABLED START #
    symbols = {}
    # PROTECTED REGION END #    //  TwincatAds.class_variable

    # -----------------
    # Device Properties
    # -----------------

    ams_netid = device_property(
        dtype='DevString',
    )

    ams_port = device_property(
        dtype='DevLong',
    )

    scalar_symbols = device_property(
        dtype=(str,),
        default_value="MAIN.subroutine.bOutputActive, output, ro"
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        """Initialises the attributes and properties of the TwincatAds."""
        Device.init_device(self)
        # PROTECTED REGION ID(TwincatAds.init_device) ENABLED START #
        
        self.plc = pyads.Connection(self.ams_netid, self.ams_port)
        self.plc.open()
        ads_state, machine_state = self.plc.read_state()
        print(f"states: ads: {ads_state}, machine: {machine_state}", file=self.log_debug)
        self.set_state(DevState.ON)
    
    def initialize_dynamic_attributes(self):
        for line in self.scalar_symbols:
            name, label, access = [s.strip() for s in line.split(',')]
            print(f"init: {name}, {label}, {access}", file=self.log_debug)
            symbol = self.plc.get_symbol(name)
            self.symbols[label] = symbol
            size = symbol.array_size
            if size > 1:
                print(f"{name} is not a scalar. Ignoring.", file=self.log_warning)
                continue
            value = symbol.read()
            attr = attribute(
                name=label,
                dtype=type(value),
                access=AttrWriteType.READ_WRITE if access == "rw" else AttrWriteType.READ,
                fget=self.generic_read,
                fset=self.generic_write,
            )
            self.add_attribute(attr)
    
    def generic_read(self, attr):
        name = attr.get_name()
        return self.symbols[name].read()
    
    def generic_write(self, attr):
        name = attr.get_name()
        value = attr.get_write_value()
        self.symbols[name].write(value)
        
        # PROTECTED REGION END #    //  TwincatAds.init_device

    def always_executed_hook(self):
        """Method always executed before any TANGO command is executed."""
        # PROTECTED REGION ID(TwincatAds.always_executed_hook) ENABLED START #
        # PROTECTED REGION END #    //  TwincatAds.always_executed_hook

    def delete_device(self):
        """Hook to delete resources allocated in init_device.

        This method allows for any memory or other resources allocated in the
        init_device method to be released.  This method is called by the device
        destructor and by the device Init command.
        """
        # PROTECTED REGION ID(TwincatAds.delete_device) ENABLED START #
        self.plc.close()
        # PROTECTED REGION END #    //  TwincatAds.delete_device
    # --------
    # Commands
    # --------

    @command(
        dtype_in='DevVarLongStringArray',
        doc_in=("Number of array values to read and ADS symbol name.\n"
               "[<num>, ] [<name>, ]\n"
               "Example: [200, ] [``MAIN.array1``, ]"),
        dtype_out='DevVarFloatArray',
        doc_out="array of float values",
    )
    @DebugIt()
    def read_float_array(self, argin):
        # PROTECTED REGION ID(TwincatAds.read_float_array) ENABLED START #
        """
        Read array of float values. Returns entire array if <num> is negative

        :param argin: 'DevVarLongStringArray'
            Number of array values to read and ADS symbol name.
            [<num>, ] [<name>, ]
            Example: [200, ] [``MAIN.array1``, ]

        :return:'DevVarFloatArray'
        array of float values
        """
        npts = argin[0][0]
        name = argin[1][0]
        values = self.plc.read_by_name(name, npts * pyads.PLCTYPE_REAL)
        return np.array(values)
        # PROTECTED REGION END #    //  TwincatAds.read_float_array

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    """Main function of the TwincatAds module."""
    # PROTECTED REGION ID(TwincatAds.main) ENABLED START #
    return run((TwincatAds,), args=args, **kwargs)
    # PROTECTED REGION END #    //  TwincatAds.main


if __name__ == '__main__':
    main()
