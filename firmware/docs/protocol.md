# OT2 Stepper Controller Serial Protocol

<!-- TOC -->

## Table of Contents

- [Command Reference](#command-reference)
- [Protocol Overview](#protocol-overview)
- [Serial Response Format](#serial-response-format)
- [Units and Motion Conventions](#units-and-motion-conventions)
- [Coordinate System](#coordinate-system)
- [Default Coordinate Space](#default-coordinate-space)
- [Positioning Modes](#positioning-modes)
- [Motion Commands](#motion-commands)
- [Homing Commands](#homing-commands)
- [Probe Commands](#probe-commands)
- [Configuration Commands](#configuration-commands)
- [Status Commands](#status-commands)
- [Emergency and Control Commands](#emergency-and-control-commands)
- [Future Development](#future-development)

<!-- /TOC -->

---

# Command Reference

Quick links to supported commands:

| Command | Description |
|---------|-------------|
| [G0](#g0--rapid-move) | Rapid movement |
| [G1](#g1--linear-move) | Linear movement with configurable feed rate |
| [G28](#g28--home-axes) | Home one or more axes |
| [G38.2](#g382--probe-toward-error-on-failure) | Probe toward surface with error on failure |
| [G38.3](#g383--probe-toward-no-error) | Probe toward surface without error on failure |
| [G38.4](#g384--probe-away-error-on-failure) | Probe away from surface with error on failure |
| [G38.5](#g385--probe-away-no-error) | Probe away from surface without error on failure |
| [G90](#g90--absolute-positioning) | Set absolute coordinate mode |
| [G91](#g91--relative-positioning) | Set relative coordinate mode |
| [M30](#m30--reset-controller) | Reset controller to firmware defaults |
| [M112](#m112--emergency-stop--kill) | Emergency motor shutdown |
| [M114](#m114--report-current-position) | Report current position |
| [M201](#m201--set-hard-limits) | Configure axis travel limits |
| [M204](#m204--set-accelerations) | Configure acceleration values |
| [M210](#m210--set-homing-speeds) | Configure homing speeds |
| [M220](#m220--set-travel-speeds) | Configure travel speeds |
| [M410](#m410--quick-stop) | Stop motion while preserving position |
| [M411](#m411--query-debug-information) | Query debug information |
| [M421](#m421--set-homing-retraction-distance) | Configure homing retract distance |
| [M911](#m911--disable-blocking-limits) | Disable firmware motion limits |

---

# Protocol Overview

The OT2 Stepper Controller communicates using a serial **G-code** protocol inspired by common CNC and motion-control firmware.

Commands are transmitted as ASCII text terminated with a newline (`\n`).

Example:

```text
G0 X100 Y50 Z10
```

The controller supports motion control, homing, probing, configuration, and status commands for all six OT-2 motion axes.

---

# Serial Response Format

Every command will return one of two final status responses:

Successful command:

```text
ok
```

Failed command:

```text
NOT ok
```

Additional information may be transmitted before the final status response.

Examples:

Successful command with additional information:

```text
X:100 Y:150 Z:5 A:0 B:0 C:0
ok
```

Failed command with error details:

```text
NOT ok (axis Z not homed)
```

Error details are optional and may not be provided for every failure condition.

---

# Units and Motion Conventions

## Position Units

All axis positions and movement distances are specified in:

```
microsteps (1/32 step resolution)
```

The controller does not currently perform unit conversion to physical measurements such as millimeters.

Example:

```text
G0 X3200
```

commands the X-axis to move 3200 microsteps.

---

## Speed Units

All feed rates and configured speeds are specified in:

```
microsteps per second
```

These values correspond directly to the AccelStepper motion control implementation.

Example:

```text
G1 X10000 F5000
```

moves the axis toward the target position with a feed rate of 5000 microsteps/sec.

---

# Coordinate System

The controller supports six motion axes.

| Axis | Function                      |
| ---- | ----------------------------- |
| X    | Gantry X-axis                 |
| Y    | Gantry Y-axis                 |
| Z    | Left pipette vertical motion  |
| A    | Right pipette vertical motion |
| B    | Left pipette plunger          |
| C    | Right pipette plunger         |

Movement interpretation depends on the current positioning mode.

---

# Default Coordinate Space

The controller operates within a defined coordinate space for each axis.

The default firmware travel limits are defined by the `ENDSTOP_LIMITS` configuration values.

| Axis | Function | Default Maximum Position (microsteps) |
|------|----------|--------------------------------------|
| X | Gantry X-axis | 60,000 |
| Y | Gantry Y-axis | 52,000 |
| Z | Left pipette vertical motion | 160,000 |
| A | Right pipette vertical motion | 160,000 |
| B | Left pipette plunger | 20,000 |
| C | Right pipette plunger | 20,000 |

All values are specified in microsteps (1/32 step resolution).

These values define the default firmware travel boundaries for each axis.

The limits may be modified *to stricter limits* at runtime using the `M201` command:

    M201 X[value] Y[value] Z[value] A[value] B[value] C[value]

Example:

    M201 X30000 Y30000

This sets the X and Y maximum travel limits to 30,000 microsteps.

> Note:
>
> The hard limits defined above **cannot be extended** (only further restricted) using the `M201` command. 

> The current implementation stores modified limits only in RAM. They are reset to firmware defaults after a controller reset or power cycle.
>
> Future development may add EEPROM-backed persistent configuration storage.

---

# Positioning Modes

## G90 — Absolute Positioning

Sets all subsequent motion commands to use absolute coordinates.

Example:

```text
G90
G0 X100 Y50 Z10
```

The controller moves to:

```
X = 100
Y = 50
Z = 10
```

---

## G91 — Relative Positioning

Sets all subsequent motion commands to use relative movement.

Example:

```text
G91
G0 X1000
```

Moves the X-axis 1000 microsteps from the current position.

---

# Motion Commands

## G0 — Rapid Move

Moves one or more axes using the configured travel speed.

Movement is interpreted according to the current positioning mode (`G90` or `G91`).

### Syntax

```text
G0 X[value] Y[value] Z[value] A[value] B[value] C[value]
```

### Example

```text
G0 X10000 Y20000 Z5000
```

---

## G1 — Linear Move

Performs a coordinated move while allowing the feed rate to be specified.

### Syntax

```text
G1 X[value] Y[value] Z[value] F[value]
```

### Parameters

| Parameter | Description                        |
| --------- | ---------------------------------- |
| X–C       | Target axis position in microsteps |
| F         | Feed rate in microsteps/sec        |

### Example

```text
G1 X10000 Y5000 F2000
```

---

# Homing Commands

## G28 — Home Axes

Homes one or more axes.

If no axes are specified, all supported axes are homed sequentially.

### Syntax

```text
G28
```

or:

```text
G28 X Y Z
```

### Examples

Home all axes:

```text
G28
```

Home only X and Y:

```text
G28 X Y
```

Home only Z:

```text
G28 Z
```

---

# Probe Commands

The G38 family performs probing operations.

Probe operations move an axis until a probe event occurs or the target position is reached.

---

## G38.2 — Probe Toward (Error on Failure)

Moves toward a surface.

If the probe triggers:

* The trigger position is reported.
* Command returns `ok`.

If the target position is reached without triggering:

* Probe position is reported.
* Command returns `NOT ok`.

Example:

```text
G38.2 Z-20000 F100
```

Success:

```text
[PRB:10500,20320,-5245:1]
ok
```

Failure:

```text
[PRB:10500,20320,-20000:0]
NOT ok
```

---

## G38.3 — Probe Toward (No Error)

Same as `G38.2`, except failure to trigger does not generate an error.

The controller stops at the requested destination and continues execution.

---

## G38.4 — Probe Away (Error on Failure)

Moves away from an object until probe contact is released.

If contact is never released:

```text
NOT ok
```

is returned.

---

## G38.5 — Probe Away (No Error)

Moves away from an object until probe contact is released.

If contact is never released, motion stops at the destination and execution continues.

---

## Probe Response Format

Probe responses use:

```text
[PRB:X,Y,Z:flag]
```

Fields:

| Field    | Description                  |
| -------- | ---------------------------- |
| X        | Probe trigger X coordinate   |
| Y        | Probe trigger Y coordinate   |
| Z        | Probe trigger Z coordinate   |
| flag = 1 | Probe triggered successfully |
| flag = 0 | Probe failed                 |

---

# Configuration Commands

## M201 — Set Hard Limits

Sets maximum allowed axis positions.

### Syntax

```text
M201 X[value] Y[value] Z[value] A[value] B[value] C[value]
```

Example:

```text
M201 X3000 Y3000
```

Sets the X and Y firmware limits to 3000 microsteps.

> Current behavior:
>
> Limits are stored only in RAM and reset to firmware defaults after `M30` or power cycling.

---

## M204 — Set Accelerations

Sets acceleration values for each axis.

### Syntax

```text
M204 X[value] Y[value] Z[value] A[value] B[value] C[value]
```

Values are interpreted according to the AccelStepper implementation.

---

## M210 — Set Homing Speeds

Sets homing speeds.

### Syntax

```text
M210 X[value] Y[value] Z[value] A[value] B[value] C[value]
```

Values are in microsteps/sec.

---

## M220 — Set Travel Speeds

Sets travel speeds.

### Syntax

```text
M220 X[value] Y[value] Z[value] A[value] B[value] C[value]
```

Values are in microsteps/sec.

---

## M421 — Set Homing Retraction Distance

Adjusts the retract distance after a successful homing operation.

### Syntax

```text
M421 X[value] Y[value] Z[value] A[value] B[value] C[value]
```

Values are in microsteps.

---

# Status Commands

## M114 — Report Current Position

Returns the current axis positions.

Command:

```text
M114
```

Response:

```text
X:100 Y:150 Z:5 A:0 B:0 C:0
ok
```

---

## M411 — Query Debug Information

Returns internal debug information.

Syntax:

```text
M411 READ [pin]
```

---

# Emergency and Control Commands

## M410 — Quick Stop

Stops all active motion as quickly as possible while maintaining position tracking.

Unlike an emergency stop:

* Motors remain logically positioned.
* Re-homing is not required.

---

## M112 — Emergency Stop / Kill

Immediately disables motor operation.

After execution:

* Motion stops immediately.
* Motors are disengaged.
* The machine must be re-homed before further operation.

---

## M30 — Reset Controller

Resets all modal settings and returns the controller to firmware defaults.

Current behavior:

* Restores `G90` absolute positioning mode.
* Restores default acceleration values.
* Restores default travel speeds.
* Restores default hard limits.
* Clears temporary runtime configuration.
* Resets motor state.

No EEPROM storage is currently implemented, so all configuration changes are lost after reset.

Future development may include EEPROM-backed configuration storage.

---

## M911 — Disable Blocking Limits

Disables firmware blocking limits.

When enabled:

* Normal hard limits are ignored.
* Multiple axes may move simultaneously during homing.
* Intended for development, troubleshooting, and recovery.

> Warning:
>
> This command bypasses normal motion safety protections. Use only when the operator understands the consequences.

---

# Future Development

Potential future protocol additions include:

* EEPROM-backed configuration storage
* Persistent hard limits and motion settings
* Firmware version query
* Controller capability reporting
* Ethernet communication
* Motion queue management
* Expanded diagnostics
