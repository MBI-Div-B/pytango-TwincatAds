# Spec Delta

## Purpose

The controller device owns the ADS connection to one TwinCAT PLC, reports whether that connection is usable, and offers generic commands to read and write scalar and 1D array symbols by name.

## ADDED Requirements

### Requirement: Connection configuration
The controller SHALL connect to the PLC given by the `ams_netid` and `ams_port` device properties. `ams_port` SHALL default to the TwinCAT 3 PLC1 port (851). The optional `plc_address` property SHALL give the PLC's IP address or host name; when unset, the first four octets of `ams_netid` SHALL be used as its IP address. The optional `local_ams_netid` property SHALL set the AMS NetID of the local machine before connecting; when unset, the local AMS router's NetID SHALL be used.

#### Scenario: Default port
- **WHEN** a controller is configured with only `ams_netid`
- **THEN** it connects to port 851 of that AMS NetID

#### Scenario: Explicit PLC address
- **WHEN** `plc_address` is `plc01.example.org`
- **THEN** the controller connects to that host using `ams_netid`

#### Scenario: Local NetID
- **WHEN** `local_ams_netid` is `1.2.3.4.1.1`
- **THEN** ADS requests to the PLC are sent from AMS NetID `1.2.3.4.1.1`

### Requirement: Initialization never fails on connection errors
The controller's initialization (at server start and on the `Init` command) SHALL complete without raising an error when the PLC is unreachable. The resulting condition SHALL be reported through state and status.

#### Scenario: PLC unreachable at server start
- **WHEN** the device server starts while the PLC is unreachable
- **THEN** the controller device exists, its state is FAULT and its status contains the connection error

### Requirement: Connection state
The controller state SHALL be ON while the PLC answers ADS state requests and its ADS state is RUN, and FAULT otherwise. The state SHALL be evaluated whenever it is queried, so changes at run time are reported without an `Init`. If the connection could not be opened during initialization, the state SHALL remain FAULT until the next `Init`. The status SHALL describe the ADS and machine state, or the error.

#### Scenario: PLC stopped
- **WHEN** the PLC is reachable but its ADS state is STOP
- **THEN** the controller state is FAULT and the status names the ADS state

#### Scenario: Connection lost at run time
- **WHEN** the PLC becomes unreachable while the server is running
- **THEN** the next state query returns FAULT

#### Scenario: Connection restored
- **WHEN** the PLC is reachable again and in RUN after it became unreachable at run time
- **THEN** the next state query returns ON without an `Init`

#### Scenario: PLC back after unreachable start
- **WHEN** the PLC was unreachable during initialization and is reachable and in RUN later
- **THEN** the state stays FAULT until the controller's `Init`, after which it is ON

### Requirement: Symbol information is refreshed after recovery
Symbol information (memory locations and types) looked up from the PLC SHALL be discarded whenever the controller state changes from FAULT to ON, so later accesses use the PLC's current symbol layout.

#### Scenario: PLC restarted with a new program
- **WHEN** the PLC goes from FAULT back to ON after a program change
- **THEN** subsequent reads and writes resolve symbols anew

### Requirement: Scalar commands
The controller SHALL provide `read_float_value`, `read_int_value` and `read_bool_value`, each taking a symbol name and returning its value. It SHALL provide `write_float_value`, `write_int_value` and `write_bool_value`, each taking `([value], [name])`, with bool values given as integers.

#### Scenario: Read a scalar
- **WHEN** `read_float_value("MAIN.fSetpoint")` is called
- **THEN** the current value of `MAIN.fSetpoint` is returned as a float

#### Scenario: Write a scalar
- **WHEN** `write_int_value(([42], ["MAIN.nCount"]))` is called
- **THEN** `MAIN.nCount` holds 42

#### Scenario: Unknown symbol
- **WHEN** a command is called with a name that does not exist in the PLC
- **THEN** the command fails with an error naming the symbol

### Requirement: Array indices follow the PLC declaration
Array commands SHALL interpret indices according to the array's declared bounds: for `ARRAY [l..u]`, index `l` is the first element. Only one-dimensional arrays with non-negative bounds SHALL be supported; other symbols SHALL be rejected with an error that includes the symbol's declared type.

#### Scenario: One-based array
- **WHEN** `MAIN.fArr` is declared `ARRAY [1..100] OF REAL` and element 1 is requested
- **THEN** the first element of the array is returned

#### Scenario: Multi-dimensional array
- **WHEN** an array command is called for a symbol declared `ARRAY [1..10, 0..5] OF INT`
- **THEN** the command fails with an error containing `ARRAY [1..10, 0..5] OF INT`

#### Scenario: Not an array
- **WHEN** an array command is called for a scalar symbol
- **THEN** the command fails with an error stating the symbol is not an array

### Requirement: Array read commands
The controller SHALL provide `read_float_array`, `read_int_array` and `read_bool_array`, each taking `[name, start, count]` as strings, where `start` and `count` are optional. `start` SHALL default to the lower bound and `count` to the rest of the array. A `start` outside the bounds SHALL be rejected; a `count` reaching past the upper bound SHALL be clipped.

#### Scenario: Whole array
- **WHEN** `read_float_array(["MAIN.fArr"])` is called for `ARRAY [1..100] OF REAL`
- **THEN** all 100 elements are returned

#### Scenario: Slice
- **WHEN** `read_float_array(["MAIN.fArr", "10", "5"])` is called
- **THEN** elements 10 to 14 are returned

#### Scenario: Count clipped
- **WHEN** `read_float_array(["MAIN.fArr", "98", "10"])` is called for `ARRAY [1..100] OF REAL`
- **THEN** elements 98 to 100 are returned

#### Scenario: Start out of bounds
- **WHEN** `read_float_array(["MAIN.fArr", "0"])` is called for `ARRAY [1..100] OF REAL`
- **THEN** the command fails with an error naming the valid bounds

### Requirement: Array write commands
The controller SHALL provide `write_float_array`, `write_int_array` and `write_bool_array`, each taking `([values...], [name, start])` with `start` optional and defaulting to the lower bound. Writes SHALL be stateless. A write whose values would reach past the upper bound, or whose `start` is outside the bounds, SHALL be rejected without writing.

#### Scenario: Write at offset
- **WHEN** `write_float_array(([1.0, 2.0], ["MAIN.fArr", "50"]))` is called
- **THEN** elements 50 and 51 hold 1.0 and 2.0 and no other element changes

#### Scenario: Write past the end
- **WHEN** 5 values are written at start 98 to `ARRAY [1..100] OF REAL`
- **THEN** the command fails and the array is unchanged

### Requirement: Array declaration helpers
The controller SHALL provide `get_array_bounds`, taking a symbol name and returning `[lower, upper]`, and `get_array_type`, taking a symbol name and returning the declared element type (e.g. `REAL`). Unsupported symbols SHALL be rejected as for the array commands.

#### Scenario: Query bounds and type
- **WHEN** `get_array_bounds("MAIN.fArr")` and `get_array_type("MAIN.fArr")` are called for `ARRAY [1..100] OF REAL`
- **THEN** they return `[1, 100]` and `"REAL"`
