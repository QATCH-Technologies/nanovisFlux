# OT2-stepper-controller

![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Arduino IDE](https://img.shields.io/badge/Arduino_IDE-2.x-00979D?logo=arduino)
![Teensy](https://img.shields.io/badge/Board-Teensy%204.1-green)
![Language](https://img.shields.io/badge/Language-C%2B%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Opentrons_OT--2-orange)

Firmware for replacing the **5001-stepper-drivers** controller board in the **Opentrons OT-2** liquid handling robot with a **Teensy 4.1** microcontroller.

This project provides a modern, open-source motion controller that interfaces directly with the existing OT-2 wiring harness and connectors, allowing the original stepper driver board to be replaced without modifying the robot's cabling.

The controller communicates over a serial interface using a G-code protocol, making it easy to integrate with host software, automation systems, or custom control applications.

> **Disclaimer:**
> This project is an independent, community-developed firmware implementation compatible with the Opentrons OT-2 platform. It is not affiliated with, endorsed by, or supported by Opentrons. "Opentrons" and "OT-2" are trademarks of their respective owners and are used solely to identify compatible hardware.

---

## Features

* Compatible with **Teensy 4.1**
  * Standard Teensy 4.1
  * Teensy 4.1 with Ethernet
* Arduino IDE compatible
* Uses only a single external library (`AccelStepper`)
* Drop-in replacement for the original **5001-stepper-drivers** board
* Supports the existing OT-2 wiring harness and connectors
* Serial G-code communication protocol
* Open-source firmware licensed under **GPL-3.0**

### Supported Motion Axes

| Axis  | Function                            |
| ----- | ----------------------------------- |
| **X** | Gantry X-axis (left/**right**)      |
| **Y** | Gantry Y-axis (forward/**back**)    |
| **Z** | Left pipette Z (**up**/down)        |
| **A** | Right pipette Z (**up**/down)       |
| **B** | Left pipette plunger (**up**/down)  |
| **C** | Right pipette plunger (*missing*)   |

 **NOTES:**
 * The **bold** position indicates the **home** endstop position.
 * For the plunger axes: **tip ejection** occurs at extreme **down** positon.

---

## Firmware Folder Structure

```text
firmware/
│
├── docs/
│   ├── building.md
│   ├── hardware.md
│   └── protocol.md
│
├── OT2-stepper-controller/
│   ├── DualHBridgeStepper.h
│   ├── OT2-stepper-controller.ino
|
├── README.md
├── LICENSE
├── CHANGELOG.md
│
└── images/
    └── block-diagram.png
```

---

## Requirements

### Hardware

* Teensy 4.1
* Compatible OT-2 motion hardware
* Original OT-2 wiring harness
* Stepper drivers and power electronics appropriate for your controller design

### Software

* Arduino IDE 2.3.x
* Teensyduino board support package
* AccelStepper library

---

## Dependencies

Only one external Arduino library is required.

| Library      | Purpose                                   |
| ------------ | ----------------------------------------- |
| AccelStepper | Motion planning and stepper motor control |

Install the library using the Arduino Library Manager.

No additional third-party libraries are required.

---

## Building

Detailed build instructions are available in:

```
docs/building.md
```

### Quick Start

1. Clone this repository.

```bash
git clone https://github.com/<your-username>/OT2-stepper-controller.git
```

2. Open `OT2-stepper-controller.ino` in the Arduino IDE.

3. Select:

* **Board:** Teensy 4.1
* **USB Type:** Serial
* **COM Port:** Your connected Teensy

4. Install the AccelStepper library if prompted.

5. Click **Verify**.

6. Upload the firmware.

---

## Communication Protocol

The controller communicates using a serial G-code interface.

A complete reference, including supported commands, responses, examples, and error codes, is available in:

```
docs/protocol.md
```

---

## Hardware Documentation

Hardware compatibility, connector information, electrical interfaces, and wiring notes are documented in:

```
docs/hardware.md
```

This project maintains compatibility with the original OT-2 connector layout to simplify installation and integration.

---

## Design Goals

The primary goals of this project are:

* Replace the original OT-2 stepper controller with modern hardware
* Preserve compatibility with existing OT-2 wiring and mechanics
* Minimize software dependencies
* Enable straightforward firmware development using the Arduino ecosystem
* Provide a clean and extensible G-code interface for host applications
* Encourage community contributions and customization

---

## Documentation

| Document           | Description                       |
| ------------------ | --------------------------------- |
| `README.md`        | Project overview                  |
| `docs/building.md` | Build and upload instructions     |
| `docs/hardware.md` | Hardware compatibility and wiring |
| `docs/protocol.md` | Serial G-code protocol reference  |
| `CHANGELOG.md`     | Release history                   |

---

## Related Resources

### Opentrons OT-2 Repository

The original OT-2 hardware design files, documentation, and related resources are available from the official Opentrons repository:

https://github.com/Opentrons/ot2

This firmware references the published connector layout and hardware interfaces for compatibility but is an independent implementation.

---

## Contributing

Contributions are welcome.

Bug reports, feature requests, documentation improvements, and pull requests are encouraged. Please open an issue to discuss significant changes before beginning implementation.

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

See the `LICENSE` file for the complete license text.
