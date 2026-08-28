# Hardware

## Supported Controller

- Teensy 4.1

## Supported Robot

- Opentrons OT-2

## Supported H-Bridge Motor Driver

- 4 x MDV 2x2A DC Motor Controller (L298N)
> https://www.dfrobot.com/product-66.html

## Supported Motion Axes

| Axis  | Function                            |
| ----- | ----------------------------------- |
| **X** | Gantry X-axis (left/**right**)      |
| **Y** | Gantry Y-axis (forward/**back**)    |
| **Z** | Left pipette Z (**up**/down)        |
| **A** | Right pipette Z (**up**/down)       |
| **B** | Left pipette plunger (**up**/down)  |
| **C** | Right pipette plunger (*missing*)   |

## Rear-Mounted Sensor

A fixed ultrasonic distance sensor is mounted on the rear of the gantry, behind the Z and A mounts. It has no dedicated motion axis -- it's rigidly fixed to the gantry frame and travels only with X/Y -- and is queried over serial with `M412` (see `firmware/docs/protocol.md`). Trigger/echo pin assignment (`ULTRASONIC_TRIG`/`ULTRASONIC_ECHO` in the `.ino`) is a placeholder pending final sensor selection and wiring.

 **NOTES:**
 * The **bold** position indicates the **home** endstop position.
 * For the plunger axes: **tip ejection** occurs at extreme **down** positon.

## Connectors

This firmware is designed to use the existing OT-2 wiring harness and connector layout.

No rewiring of the existing wiring harnesses should be necessary when replacing the original controller.

## Hardware References

The connector layout and board interfaces are based on the publicly available hardware documentation published by Opentrons.

See:

https://github.com/Opentrons/ot2

## Future Documentation

This document will eventually include:

- Connector pinouts
- Electrical specifications
- Limit switch inputs
- Motor driver assignments
- Power requirements
- Ethernet configuration (if used)

For now, these can be derived using logical deduction and/or directly from the source code.
