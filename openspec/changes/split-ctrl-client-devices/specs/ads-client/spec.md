# Spec Delta

## Purpose

Client devices group related PLC variables into one Tango device each, exposing configured scalars as attributes and configured arrays as commands, all through a controller device in the same server.

## ADDED Requirements

### Requirement: Controller binding
A client SHALL use the controller named by its `ads_ctrl_device` property, which MUST be served by the same device server process. If that controller is not found there, the client's initialization SHALL fail with an error naming the controller.

#### Scenario: Controller in another server
- **WHEN** `ads_ctrl_device` names a device not served by this process
- **THEN** client initialization fails with an error naming that device

### Requirement: Scalar attributes from configuration
For each line `<plc_name>, <attr_name>, ro|rw` of the `scalar_symbols` property, the client SHALL create an attribute `<attr_name>`, read-only for `ro` and read-write for `rw`, that reads and writes the PLC symbol `<plc_name>`. Attributes SHALL be created once, when the server starts.

#### Scenario: Read-write scalar
- **WHEN** `scalar_symbols` contains `MAIN.fSetpoint, setpoint, rw`
- **THEN** the client has a read-write attribute `setpoint` reflecting `MAIN.fSetpoint`

### Requirement: Scalar attribute types follow the PLC declaration
The attribute type SHALL be derived from the symbol's declared type: `BOOL` as boolean, integer and time/date types as integer, `REAL`/`LREAL` as floating point, and `STRING(n)` as string. Writing a string longer than `n` characters SHALL be rejected without writing.

#### Scenario: STRING attribute
- **WHEN** a configured symbol is declared `STRING(80)`
- **THEN** its attribute has string type and returns the PLC's text

#### Scenario: String too long
- **WHEN** an 81-character string is written to an attribute bound to a `STRING(80)`
- **THEN** the write fails and the PLC value is unchanged

### Requirement: Array commands from configuration
For each line `<plc_name>, <alias>, ro|rw` of the `array_symbols` property, the client SHALL create a command `read_<alias>` and, for `rw`, a command `write_<alias>`. No attribute SHALL be created for arrays. Each command's description SHALL show the array's declaration. Commands SHALL be created once, when the server starts.

#### Scenario: Read-only array
- **WHEN** `array_symbols` contains `MAIN.fSpectrum, spectrum, ro`
- **THEN** the client has a command `read_spectrum` and no command `write_spectrum`

### Requirement: Array read command
`read_<alias>` SHALL take an integer list: `[]` reads the whole array, `[count]` reads `count` elements from the lower bound, and `[start, count]` reads from `start` in PLC-declared indices. Unlike the controller, a single value is a count, not a start. Longer lists and an out-of-bounds `start` SHALL be rejected; `count` past the upper bound SHALL be clipped. Values SHALL be returned as boolean, integer or floating point per the element type.

#### Scenario: Whole array through alias
- **WHEN** `read_spectrum([])` is called for `ARRAY [1..512] OF REAL`
- **THEN** all 512 elements are returned as floating point values

#### Scenario: Leading elements through alias
- **WHEN** `read_spectrum([10])` is called for `ARRAY [1..512] OF REAL`
- **THEN** elements 1 to 10 are returned

#### Scenario: Slice through alias
- **WHEN** `read_spectrum([10, 5])` is called for `ARRAY [1..512] OF REAL`
- **THEN** elements 10 to 14 are returned

#### Scenario: Count clipped through alias
- **WHEN** `read_spectrum([510, 10])` is called for `ARRAY [1..512] OF REAL`
- **THEN** elements 510 to 512 are returned

#### Scenario: Start out of bounds through alias
- **WHEN** `read_spectrum([0, 5])` is called for `ARRAY [1..512] OF REAL`
- **THEN** the command fails with an error naming the valid bounds

#### Scenario: Too many arguments
- **WHEN** `read_spectrum([1, 5, 3])` is called
- **THEN** the command fails and nothing is read

### Requirement: Array write command
`write_<alias>` SHALL take a list of values and write them starting at the array's lower bound. Fewer values than the array length SHALL write only the leading elements; more values SHALL be rejected without writing.

#### Scenario: Partial write
- **WHEN** 3 values are written with `write_spectrum` to `ARRAY [1..512] OF REAL`
- **THEN** elements 1 to 3 hold those values and no other element changes

#### Scenario: Too many values
- **WHEN** 513 values are written with `write_spectrum` to `ARRAY [1..512] OF REAL`
- **THEN** the command fails and the array is unchanged

### Requirement: Skipped configuration entries
A configuration line SHALL be skipped, with a line added to the client's status naming the symbol and the reason, when the symbol does not exist, its type is unsupported, a scalar entry names an array, an array entry names a scalar or unsupported array, or a generated name collides with an existing attribute or command. Other entries SHALL still be created.

#### Scenario: Missing symbol
- **WHEN** `scalar_symbols` contains a line for `MAIN.bGone`, which does not exist in the PLC
- **THEN** no attribute is created for it, the other attributes exist, and the status names `MAIN.bGone`

#### Scenario: Array listed as scalar
- **WHEN** `scalar_symbols` names a symbol declared as an array
- **THEN** no attribute is created for it and the status states that it is an array

### Requirement: Combined state and status
The client's own state SHALL be ALARM if any configuration entry was skipped and ON otherwise. The reported state SHALL be the more severe of the controller's current state and the client's own state, ordered FAULT > ALARM > ON. The reported status SHALL be the controller's current status followed by the client's own status lines.

#### Scenario: Controller fault dominates
- **WHEN** the controller is FAULT and the client had skipped entries
- **THEN** the client state is FAULT and its status contains both the controller status and the skipped-entry lines

#### Scenario: Skipped entry with healthy controller
- **WHEN** the controller is ON and the client skipped an entry
- **THEN** the client state is ALARM

#### Scenario: All healthy
- **WHEN** the controller is ON and no entry was skipped
- **THEN** the client state is ON and its status equals the controller status
